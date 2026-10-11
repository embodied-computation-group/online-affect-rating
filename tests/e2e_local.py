"""End-to-end smoke test of the task in local mode using installed Chrome (headless).

Usage:
  python tests/e2e_local.py [--study heights-film] [--dim anxiety|affect2d] [--input joystick|slider] [--reload] [--base URL]

Requires scripts/serve_local.sh running and the study's film in media/. The film starts near its end
(start_time) so a run takes ~2 min. With --reload the page is reloaded mid-film to test resume. Writes the
downloaded NDJSON to tests/out/ and prints a summary. The answers it gives follow the heights study's
questionnaires (studies/heights-film); for another study, adapt the questionnaire steps.
With --live (a JATOS study link), start_time only works if test mode is on: JATOS study properties ->
Study input {"testMode": true}; otherwise the whole film plays.
"""
import argparse, json, pathlib, time
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--input", default="joystick", choices=["joystick", "slider"])
ap.add_argument("--reload", action="store_true")
ap.add_argument("--throttle-mbps", type=float, default=0, help="emulate a slow connection (Mbit/s)")
ap.add_argument("--dim", default="anxiety", choices=["anxiety", "affect2d"])
ap.add_argument("--study", default="heights-film", help="folder in studies/ (local runs)")
ap.add_argument("--base", default="http://localhost:8000/task/index.html")
ap.add_argument("--real-lock", action="store_true",
                help="use Chrome's real Pointer Lock (captures the OS cursor while running!)")
ap.add_argument("--live", action="store_true", help="base is a JATOS study link: expect a Prolific redirect, not a download")
a = ap.parse_args()

START = 760 if a.reload else 795
URL = (f"{a.base}?dim={a.dim}&input={a.input}&reset=1&PROLIFIC_PID=TESTPID&STUDY_ID=TESTSTUDY"
       f"&SESSION_ID=TESTSESS&start_time={START}&study={a.study}")
OUT = pathlib.Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
VIEW = {"width": 1400, "height": 900}
mouse_y = VIEW["height"] / 2
mouse_x = VIEW["width"] / 2
IS2D = a.dim == "affect2d"


def click(page, text):
    page.get_by_role("button", name=text).click()


def joy_value(page):
    return page.evaluate("() => parseFloat(document.querySelector('.cr-bar-level').style.bottom)")


def joy_target(page):
    return page.evaluate("() => parseFloat(getComputedStyle(document.querySelector('.cr-bar-target')).getPropertyValue('--v'))")


def move_by(page, dy, dx=0):
    global mouse_y, mouse_x
    mouse_y += dy
    mouse_x += dx
    page.mouse.move(mouse_x, mouse_y, steps=2)


def grid_state(page):
    return page.evaluate("""() => { const d=document.querySelector('.cr-grid-dot'), t=document.querySelector('.cr-grid-target');
        const cs=getComputedStyle(t); return [parseFloat(d.style.left), parseFloat(d.style.bottom),
        parseFloat(cs.getPropertyValue('--x')), parseFloat(cs.getPropertyValue('--y'))]; }""")


STICSA_ITEMS = [1, 2, 6, 7, 8, 12, 14, 15, 18, 20, 21]
STICSA_PRE = [1, 2, 1, 1, 2, 1, 1, 1, 1, 2, 1]    # total 14
STICSA_POST = [2, 3, 2, 1, 2, 2, 1, 2, 3, 2, 2]   # total 22 -> change +8


def fill_sticsa(page, values, timepoint):
    if page.locator("#dl-fill").count():
        print("download gate shown:", page.locator("#dl-text").inner_text())
    page.wait_for_selector(".sticsa-table", timeout=900000)
    assert page.locator(".sticsa-table input:checked").count() == 0, "STICSA must start unselected"
    assert page.evaluate("document.pointerLockElement") is None, "mouse still locked on the STICSA page"
    assert page.locator(".sticsa-head h2").inner_text() == "Current feelings"
    # submitting incomplete must be blocked by required radios
    page.locator("#jspsych-survey-html-form-next").click()
    page.wait_for_timeout(300)
    assert page.locator(".sticsa-table").count() == 1, "incomplete STICSA was accepted"
    for item, v in zip(STICSA_ITEMS, values):
        page.locator(f"input[name='sticsa_{item}'][value='{v}']").check()
    page.locator("#jspsych-survey-html-form-next").click()
    print(f"STICSA {timepoint} filled")


def answer_likert(page, overrides=None, default=3):
    """Answer every Q<n> radio group on a survey-likert page; overrides = {index: option}."""
    overrides = overrides or {}
    n = page.locator("input[type=radio]").evaluate_all("els => new Set(els.map(e => e.name)).size")
    for i in range(n):
        page.locator(f"input[name='Q{i}']").nth(overrides.get(i, default)).check()
    page.locator("#jspsych-survey-likert-next").click()


def track_practice(page, px_full):
    t0 = time.time()
    while time.time() - t0 < 45 and page.locator(".cr-practice").count():
        try:
            if IS2D:
                x, y, tx, ty = grid_state(page)
                move_by(page, -(ty - y) * px_full / 100 * 0.8, (tx - x) * px_full / 100 * 0.8)
            elif a.input == "joystick":
                err = joy_target(page) - joy_value(page)
                move_by(page, -err * px_full / 100 * 0.8)
            else:
                page.evaluate("""() => { const t=document.querySelector('.cr-target'), s=document.querySelector('.cr-slider');
                    if (!t||!s) return; s.value=parseFloat(getComputedStyle(t).getPropertyValue('--v'));
                    s.dispatchEvent(new Event('input',{bubbles:true})); }""")
        except Exception:
            pass
        page.wait_for_timeout(120)


def wiggle_film(page, seconds, stop_on_end=True):
    t0 = time.time()
    while time.time() - t0 < seconds and page.locator(".cr-video").count():
        if IS2D:
            sgn = 1 if int(time.time()) % 6 < 3 else -1
            move_by(page, -10 * sgn, 8 * sgn)
        elif a.input == "joystick":
            move_by(page, -12 if int(time.time()) % 6 < 3 else 12)
        else:
            page.keyboard.press("ArrowRight" if int(time.time()) % 4 < 2 else "ArrowLeft")
        page.wait_for_timeout(200)


def start_film(page):
    page.wait_for_selector(".cr-video")
    btn = page.locator(".cr-overlay-btn")
    if a.input == "slider" and not IS2D:  # Start is enabled only after the slider has been moved
        page.wait_for_selector("text=Start the film", timeout=60000)
        page.locator(".cr-slider").focus()
        page.keyboard.press("ArrowRight")
    page.wait_for_function("() => !document.querySelector('.cr-overlay-btn').disabled", timeout=60000)
    if a.input == "joystick" or IS2D:
        btn.click()
        page.wait_for_selector(".cr-banner:not([hidden])")
        move_by(page, 1)  # first event after lock is deliberately ignored by the task
        move_by(page, -60)  # set baseline
        page.keyboard.press("Space")
    else:
        btn.click()


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    page = b.new_page(viewport=VIEW, accept_downloads=True)
    if not a.real_lock:
        # Fake Pointer Lock inside the page: the real one grabs the desktop cursor even in headless mode.
        page.add_init_script("""(() => {
          let locked = null;
          Object.defineProperty(Document.prototype, 'pointerLockElement', { get() { return locked; }, configurable: true });
          Element.prototype.requestPointerLock = function () {
            locked = this; setTimeout(() => document.dispatchEvent(new Event('pointerlockchange')), 0);
            return Promise.resolve();
          };
          Document.prototype.exitPointerLock = function () {
            if (!locked) return; locked = null; setTimeout(() => document.dispatchEvent(new Event('pointerlockchange')), 0);
          };
        })();""")
    if a.throttle_mbps:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 20,
                 "downloadThroughput": a.throttle_mbps * 1e6 / 8, "uploadThroughput": 2e6 / 8})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_function("() => window.CONFIG", timeout=30000)  # the study file has loaded
    px_full = page.evaluate("() => Math.round(screen.height * CONFIG.joystickFullScaleFrac)")

    assert page.get_by_role("button", name="I consent, begin the study").is_disabled()
    for cb in page.locator(".consent-cb").all():
        cb.check()
    click(page, "I consent, begin the study")
    page.wait_for_timeout(1500)
    page.wait_for_selector("#jspsych-survey-likert-next")
    answer_likert(page, {1: 0})  # pre-film: attention check 1 = "Strongly disagree"
    click(page, "Switch to full screen")
    page.wait_for_timeout(1000)
    click(page, "Next"); click(page, "Next")

    for run in range(2):
        if not page.get_by_role("button", name="Start practice").count():
            break
        print(f"practice run {run + 1}")
        click(page, "Start practice")
        page.wait_for_timeout(300)
        track_practice(page, px_full)
        page.wait_for_timeout(500)

    if IS2D:
        click(page, "Start")
        for i in range(6):
            page.wait_for_selector(".ap-area")
            page.locator(".ap-area").click()
            page.wait_for_timeout(200)
            move_by(page, 1)
            move_by(page, -80 if i % 2 else 80, -80)
            page.keyboard.press("Space")
            page.get_by_role("button", name="Next").click()

    fill_sticsa(page, STICSA_PRE, "pre")
    start_film(page)
    if a.reload:
        wiggle_film(page, 34)  # past the first 30 s chunk
        print("reloading mid-film")
        page.goto(URL.replace("&reset=1", ""))
        page.wait_for_selector("text=Welcome back", timeout=15000)
        click(page, "Continue")
        click(page, "Switch to full screen")
        page.wait_for_timeout(800)
        start_film(page)
    t0 = time.time()
    wiggle_film(page, 90)
    print(f"film tail took {time.time() - t0:.1f}s")
    # post-STICSA must come immediately after playback
    fill_sticsa(page, STICSA_POST, "post")

    page.wait_for_selector("input[type=radio]")
    answer_likert(page)  # feelings during the film
    page.locator("#jspsych-survey-multi-select-0 input").nth(2).check()
    page.locator("#jspsych-survey-multi-select-next").click()
    page.wait_for_selector("#jspsych-survey-likert-next")
    answer_likert(page, {2: 6})  # usability: attention check 2 = "Extremely"
    page.locator("input[value='No']").first.check()
    page.locator("input[value='Yes']").last.check()
    page.locator("input[value='Mouse']").check()
    page.locator("#jspsych-survey-multi-choice-next").click()
    page.locator("#final-text").fill(" ".join(["word"] * 105))
    click(page, "Continue")
    page.locator("#jspsych-survey-text-next").click()
    if a.live:
        click(page, "Finish and return to Prolific")
        page.wait_for_url("**prolific.com/**", timeout=60000)
        print("redirected to:", page.url)
        print("errors:", errors or "none")
        b.close()
        raise SystemExit(0)
    with page.expect_download() as dl:
        click(page, "Finish and return to Prolific")
    path = OUT / dl.value.suggested_filename
    dl.value.save_as(path)
    b.close()

lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
types = [l["type"] for l in lines]
print("lines:", {t: types.count(t) for t in sorted(set(types))})
for m in (l for l in lines if l["type"] == "meta"):
    print("meta:", {k: m.get(k) for k in ("input_mode", "n_loads", "resumed_film_from", "dimension")})
final_line = [l for l in lines if l["type"] == "final"][0]
print("summary:", final_line.get("summary"))
print("preload lines:", [ {k: v for k, v in l.items() if k != "t"} for l in lines if l["type"] == "preload"])
final = final_line["data"]
order = [d.get("task") for d in final]
print("task order:", [t for t in order if t])
for d in final:
    if d.get("task") == "sticsa":
        print(f"sticsa {d['timepoint']}: items={[(i['item'], i['response']) for i in d['items']]} total={d['total']} "
              f"n={d['n_answered']} change={d.get('change')} onset={d['onset']} completion={d['completion']} dur={d['duration_ms']}ms")
for d in final:
    if d.get("task") in ("practice", "film"):
        s = d["samples"]
        vk = "value_y" if "value_y" in s else "value"
        moving = sum(1 for i in range(1, len(s[vk])) if s[vk][i] != s[vk][i - 1])
        rng = {k: (min(s[k]), max(s[k])) for k in ("value", "value_x", "value_y") if k in s}
        print(f"{d['task']:8s} {d['tag']:16s} mode={d['input_mode']} axes={d.get('axes')} n={len(s['t_stim'])} "
              f"t_stim=({s['t_stim'][0]}, {s['t_stim'][-1]}) ranges={rng} "
              f"changes={moving} init={d['initial_value']} mae={d.get('practice_mae')} "
              f"interrupts={d['n_interruptions']} events={[e['e'] for e in d['events']][:10]}")
print("errors:", errors or "none")
print("saved", path)
