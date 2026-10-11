"""Deploy task/ and the study file to the JATOS study via the JATOS API (v1).

Usage (--study is the study folder):
  python scripts/deploy_jatos.py --study studies/heights-film           # upload task files + study.yaml,
                                                                       # ensure the component exists
  python scripts/deploy_jatos.py --study studies/heights-film --video   # also upload the film (film.local_file,
                                                                       # uploaded under the name film.file)
  python scripts/deploy_jatos.py --study studies/heights-film --check   # only check token + list study/components/assets
  python scripts/deploy_jatos.py --study studies/heights-film --link    # also enable General Single links in the
                                                                       # default batch and write the study link to
                                                                       # prolific/jatos_link.txt

The JATOS study is jatos.study_id in the study file. JATOS_URL and JATOS_TOKEN are read from secrets.env
(JATOS_STUDY_ID there is only used if the study file has no jatos.study_id).
The study file is uploaded as study.yaml next to index.html, where the task reads it.
"""
import argparse
import http.cookiejar
import json
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASK = ROOT / "task"
sys.path.insert(0, str(ROOT / "qc"))
from study_config import StudyFileError, load_study  # noqa: E402


def load_env():
    """secrets.env as a dict; stops if the JATOS address or token is missing."""
    env = {}
    for line in (ROOT / "secrets.env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    missing = [k for k in ("JATOS_URL", "JATOS_TOKEN") if not env.get(k)]
    if missing:
        sys.exit(f"Missing in secrets.env: {', '.join(missing)}")
    return env


def video_upload(study):
    """(local film file, name in the JATOS study assets) for --video."""
    film = study["film"]
    return ROOT / film["local_file"], film["file"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True, help="study folder, e.g. studies/heights-film")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--link", action="store_true")
    a = ap.parse_args()

    try:
        study = load_study(a.study)  # stops here if the study file has mistakes
    except StudyFileError as err:
        sys.exit(str(err))
    if study.get("test_mode"):
        print("WARNING: test_mode is on in the study file - the testing URL parameters (start_time, max_wait_s, video)\n"
              "         will work on JATOS. Switch it off before real participants take part.")
    env = load_env()
    base = env["JATOS_URL"].rstrip("/") + "/jatos/api/v1"
    sid = str((study.get("jatos") or {}).get("study_id") or env.get("JATOS_STUDY_ID") or "")
    if not sid:
        sys.exit("No JATOS study: set jatos.study_id in the study file")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {env['JATOS_TOKEN']}"
    # Don't keep JATOS session cookies: once a cookie is sent, JATOS ignores the Bearer token -> 401.
    s.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))

    def call(method, path, **kw):
        r = s.request(method, base + path, timeout=kw.pop("timeout", 60), **kw)
        if r.status_code >= 400:
            sys.exit(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else r

    def upload(path, name, content_type=None, timeout=60):
        with path.open("rb") as fh:
            file_part = (path.name, fh, content_type) if content_type else (path.name, fh)
            call("POST", f"/studies/{sid}/assets/{name}", files={"studyAssetsFile": file_part}, timeout=timeout)
        print("uploaded", name)

    tok = call("GET", "/admin/token")
    print("token ok:", json.dumps(tok.get("data", tok))[:200])
    # Resolve the study (numeric id or UUID) and use the UUID from here on.
    allp = call("GET", "/studies/properties").get("data", [])
    d = next((x for x in allp if str(x.get("id")) == sid or x.get("uuid") == sid), None)
    if d is None:
        sys.exit(f"Study {sid} not found among studies this token can access")
    sid = d["uuid"]
    print(f"study {sid}: {d.get('title')!r} uuid={d.get('uuid')} dir={d.get('dirName')}")
    comps = call("GET", f"/studies/{sid}/components").get("data", [])
    print("components:", [(c.get("id"), c.get("title"), c.get("htmlFilePath")) for c in comps])
    if a.check:
        assets = call("GET", f"/studies/{sid}/assets/structure")
        print("assets:", json.dumps(assets.get("data", assets))[:1500])
        return

    for p in sorted(p for p in TASK.rglob("*") if p.is_file()):
        upload(p, p.relative_to(TASK).as_posix())
    upload(study["_file"], "study.yaml")  # the task reads study.yaml next to index.html
    if a.video:
        video, name = video_upload(study)
        if name.startswith("http"):
            sys.exit(f"film.file is a web address ({name}): upload the film there, not to JATOS")
        print(f"uploading {video.name} as {name} ({video.stat().st_size / 1e6:.0f} MB)...")
        upload(video, name, "video/mp4", timeout=3600)

    if not any(c.get("htmlFilePath") == "index.html" for c in comps):
        title = (study.get("jatos") or {}).get("component_title", "Film rating")
        c = call("POST", f"/studies/{sid}/components",
                 json={"title": title, "htmlFilePath": "index.html", "reloadable": True, "active": True})
        print("created component:", json.dumps(c.get("data", c))[:200])
    if a.link:
        make_link(call, sid, env)
    print("done")


def make_link(call, sid, env):
    """Enable General Single in the default batch and get its study link (one run per browser;
    reloads within a run are allowed because the component is reloadable)."""
    batches = call("GET", f"/studies/{sid}/batches").get("data", [])
    b = batches[0]
    types = set(b.get("allowedWorkerTypes") or [])
    if "GeneralSingle" not in types:
        types.add("GeneralSingle")
        call("PATCH", f"/batches/{b['id']}", json={"allowedWorkerTypes": sorted(types)})
        print("enabled GeneralSingle in batch", b["id"])
    r = call("POST", f"/studies/{sid}/studyCodes", params={"type": "GeneralSingle", "batchId": b["id"]})
    payload = r.get("data", r)
    code = payload[0] if isinstance(payload, list) else payload
    if isinstance(code, dict):
        code = code.get("code") or code.get("studyCode")
    link = f"{env['JATOS_URL'].rstrip('/')}/publix/{code}"
    (ROOT / "prolific").mkdir(exist_ok=True)
    (ROOT / "prolific" / "jatos_link.txt").write_text(link + "\n")
    print("study link:", link, "-> prolific/jatos_link.txt")


if __name__ == "__main__":
    main()
