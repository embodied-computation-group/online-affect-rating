/**
 * Timeline: consent -> device check -> questionnaires "intro" -> fullscreen -> instructions
 * -> practice (repeated once if inaccurate; 2D: placement practice) -> film download wait if needed
 * -> questionnaires "before_film" -> film with continuous rating -> questionnaires "after_film"
 * -> leave fullscreen -> questionnaires "end" -> debrief -> save -> redirect to Prolific.
 *
 * Everything study-specific (film, texts, questionnaires, codes) comes from the study file
 * (studies/<name>/study.yaml, read by study.js); the questionnaire pages are built by questionnaires.js.
 * For the heights study (studies/heights-film) the questionnaires are: intro = fear of heights +
 * attention check 1; before_film = STICSA (pre); after_film = STICSA (post); end = post-film questions,
 * written description and feedback.
 *
 * Runs on JATOS (jatos.js present) or locally (data downloaded as JSON at the end).
 *
 * Reload handling: progress is kept in JATOS study session data (localStorage when
 * local). A participant who reloads after the practice goes straight back to the
 * film, resuming CONFIG.resumeRewindSeconds before the last saved position; the
 * gap and the number of loads are logged. Locally, ?reset=1 clears the session.
 *
 * Testing URL parameters (start_time, max_wait_s, video) work only locally or in test mode
 * (study file test_mode: true, or JATOS Study input {"testMode": true}); see StudyFile.testParams.
 *
 * Result data are newline-delimited JSON appended to the JATOS result:
 *   {"type":"meta",...}    once at start
 *   {"type":"chunk",...}   every CONFIG.chunkSeconds during practice/film (crash backup)
 *   {"type":"final",...}   full jsPsych data at the end
 */
(function () {
  "use strict";

  const onJatos = typeof window.jatos !== "undefined";

  // ---- persistence --------------------------------------------------------
  const localLines = [];
  let saveChain = Promise.resolve();
  function appendLine(obj) {
    const line = JSON.stringify(obj) + "\n";
    if (!onJatos) {
      localLines.push(line);
      return Promise.resolve();
    }
    // Serialise appends so lines arrive in order; jatos.js itself retries failed requests.
    saveChain = saveChain
      .then(() => jatos.appendResultData(line))
      .catch((err) => console.error("appendResultData failed", err));
    return saveChain;
  }

  let study = null; // the study file, loaded in run()

  /** All questionnaire pages of the study, in session order. */
  function allPages() {
    const q = study.questionnaires || {};
    return ["intro", "before_film", "after_film", "end"].flatMap((slot) => q[slot] || []);
  }

  /** Total of a scale page (last completed administration), or null. */
  function scaleTotal(d, page) {
    const filter = page.timepoint ? { task: page.scale, timepoint: page.timepoint } : { task: page.scale };
    const t = d.filter(filter).values();
    if (t.length) return t[t.length - 1].total;
    // administered before a reload: total kept in the session
    const v = session[`${Questionnaires.pageKey(page)}_total`];
    return v === undefined ? null : v;
  }

  /** Scale totals for the summary, e.g. sticsa_pre_total, sticsa_post_total, sticsa_change. */
  function scaleSummary(d) {
    const out = {};
    const byScale = {};
    for (const page of allPages().filter((p) => p.type === "scale")) {
      (byScale[page.scale] = byScale[page.scale] || []).push(page);
    }
    for (const [name, pages] of Object.entries(byScale)) {
      for (const page of pages) out[`${Questionnaires.pageKey(page)}_total`] = scaleTotal(d, page);
      const pre = pages.find((p) => p.timepoint === "pre");
      const post = pages.find((p) => p.timepoint === "post");
      if (pre && post) {
        const a = scaleTotal(d, pre);
        const b = scaleTotal(d, post);
        out[`${name}_change`] = a !== null && b !== null ? b - a : null;
      }
    }
    return out;
  }

  /** Compact data-quality summary, written with the final data (for reviewing submissions). */
  function qualitySummary(jsPsych) {
    const d = jsPsych.data.get();
    const att = d.filter({ task: "attention" }).values();
    const film = d.filter({ task: "film" }).values();
    const prac = d.filter({ task: "practice" }).values();
    const quad = d.filter({ task: "quadrant_practice" }).values();
    const freeText = allPages().find((p) => p.type === "free_text");
    const ft = freeText ? d.filter({ task: freeText.name }).values()[0] : undefined;
    return {
      attention_checks_failed: att.reduce((n, a) => n + a.n_failed, 0),
      attention_checks_total: att.reduce((n, a) => n + a.n_checks, 0),
      practice_mae_last: prac.length ? prac[prac.length - 1].practice_mae : null,
      quadrant_correct: quad.filter((q) => q.correct).length,
      quadrant_total: quad.length,
      film_interruptions: film.reduce((n, f) => n + f.n_interruptions, 0),
      film_stalled_ms: film.reduce((n, f) => n + f.stalled_ms, 0),
      film_untrusted_events: film.reduce((n, f) => n + (f.n_untrusted_events || 0), 0),
      film_max_mouse_step_px: film.reduce((m, f) => Math.max(m, f.max_mouse_step_px || 0), 0),
      ...scaleSummary(d),
      preload_ms: preload.ms,
      preload_mbps: preload.ms ? Math.round((preload.bytes * 8) / (preload.ms / 1000) / 1e4) / 100 : null,
      preload_failed: preload.failed,
      gate_wait_ms: d.filter({ task: "download_gate" }).values().reduce((n, g) => n + (g.wait_ms || 0), 0),
      video_source: (film[film.length - 1] || {}).video_source || null,
      final_text_words: ft ? ft.n_words : null,
      final_text_keystrokes: ft ? ft.n_keys : null,
      final_text_away_ms: ft ? ft.away_ms : null,
      paste_blocked: integrity.paste_blocked,
      drop_blocked: integrity.drop_blocked,
      copy_blocked: integrity.copy_blocked,
      n_window_blur: integrity.n_blur,
      n_page_hidden: integrity.n_hidden,
      away_ms_total: integrity.away_ms,
    };
  }

  function finishAndRedirect(url, jsPsych) {
    const final = {
      type: "final",
      t: new Date().toISOString(),
      summary: qualitySummary(jsPsych),
      integrity,
      data: jsPsych.data.get().values(),
    };
    if (onJatos) {
      appendLine(final).then(() => jatos.endStudyAndRedirect(url));
      return;
    }
    localLines.push(JSON.stringify(final) + "\n");
    const blob = new Blob(localLines, { type: "application/x-ndjson" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `vmp_local_${Date.now()}.ndjson`;
    a.click();
    document.body.innerHTML = `<div class="end-msg"><p>Local run finished. Data downloaded.</p>
      <p>On Prolific this would redirect to:<br><code>${url}</code></p></div>`;
  }

  // ---- integrity: block paste/drop/copy, log window switching ------------------
  // Blocking is a deterrent, not proof; everything is logged for review alongside the
  // free-text typing statistics.
  const integrity = {
    events: [], // {e, t (s since load), task}
    paste_blocked: 0,
    drop_blocked: 0,
    copy_blocked: 0,
    n_hidden: 0, // page hidden (tab switch, minimise)
    n_blur: 0, // window lost focus (alt-tab, clicking another app)
    away_ms: 0, // total time with the window unfocused or hidden
  };
  let currentTask = "start";
  let awayStart = null;
  const tNow = () => Math.round(performance.now()) / 1000;
  function logIntegrity(e, extra) {
    if (integrity.events.length < 2000) integrity.events.push(Object.assign({ e, t: tNow(), task: currentTask }, extra || {}));
  }
  function goneAway(kind) {
    if (kind === "hidden") integrity.n_hidden++;
    else integrity.n_blur++;
    logIntegrity(kind);
    if (awayStart === null) awayStart = performance.now();
  }
  function cameBack(kind) {
    logIntegrity(kind);
    if (awayStart !== null && document.hasFocus() && !document.hidden) {
      integrity.away_ms += Math.round(performance.now() - awayStart);
      awayStart = null;
    }
  }
  function installIntegrityGuards() {
    const block = (counter, e) => (ev) => {
      ev.preventDefault();
      integrity[counter]++;
      logIntegrity(e);
    };
    document.addEventListener("paste", block("paste_blocked", "paste_blocked"), true);
    document.addEventListener("drop", block("drop_blocked", "drop_blocked"), true);
    document.addEventListener("dragover", (ev) => ev.preventDefault(), true);
    document.addEventListener("dragstart", (ev) => ev.preventDefault(), true);
    document.addEventListener("copy", block("copy_blocked", "copy_blocked"), true);
    document.addEventListener("cut", block("copy_blocked", "cut_blocked"), true);
    // Insertions that bypass the paste event (e.g. some autofill/extension paths) are blocked too.
    document.addEventListener(
      "beforeinput",
      (ev) => {
        if (/^insertFrom(Paste|Drop|Yank|PasteAsQuotation)/.test(ev.inputType || "")) {
          ev.preventDefault();
          integrity.paste_blocked++;
          logIntegrity("insert_blocked", { inputType: ev.inputType });
        }
      },
      true
    );
    window.addEventListener("blur", () => goneAway("blur"));
    window.addEventListener("focus", () => cameBack("focus"));
    document.addEventListener("visibilitychange", () => (document.hidden ? goneAway("hidden") : cameBack("visible")));
  }

  // ---- film pre-download ------------------------------------------------------
  const preload = { started: false, done: false, failed: false, url: null, bytes: 0, total: null, t0: 0, ms: null, error: null };
  async function startPreload(url) {
    if (preload.started) return;
    preload.started = true;
    preload.t0 = performance.now();
    appendLine({ type: "preload", e: "start", t: new Date().toISOString(), url });
    try {
      const resp = await fetch(url);
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      preload.total = Number(resp.headers.get("content-length")) || null;
      const reader = resp.body.getReader();
      const parts = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value);
        preload.bytes += value.length;
      }
      preload.url = URL.createObjectURL(new Blob(parts, { type: "video/mp4" }));
      preload.ms = Math.round(performance.now() - preload.t0);
      preload.done = true;
      appendLine({
        type: "preload",
        e: "done",
        t: new Date().toISOString(),
        ms: preload.ms,
        bytes: preload.bytes,
        mbps: Math.round((preload.bytes * 8) / (preload.ms / 1000) / 1e4) / 100,
      });
    } catch (err) {
      preload.failed = true;
      preload.error = String(err);
      appendLine({ type: "preload", e: "failed", t: new Date().toISOString(), error: preload.error, bytes: preload.bytes });
    }
  }

  // ---- reload-safe session state ---------------------------------------------
  const SESSION_KEY = "vmp_session";
  let session = {};
  function loadSession(reset) {
    if (onJatos) {
      session = Object.assign({}, jatos.studySessionData || {});
    } else {
      try {
        if (reset) localStorage.removeItem(SESSION_KEY);
        session = JSON.parse(localStorage.getItem(SESSION_KEY)) || {};
      } catch (e) {
        session = {};
      }
    }
  }
  function setSession(patch) {
    Object.assign(session, patch);
    if (onJatos) {
      return Promise.resolve(jatos.setStudySessionData(session)).catch((e) => console.error("session save failed", e));
    }
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (e) {
      /* ignore */
    }
    return Promise.resolve();
  }

  /** Message when the study cannot start (no or broken study file). */
  function showStartError(html) {
    document.body.innerHTML = `<div class="end-msg">${html}</div>`;
  }

  // ---- main ---------------------------------------------------------------
  async function run() {
    const params = onJatos ? jatos.urlQueryParameters || {} : Object.fromEntries(new URLSearchParams(location.search));
    const studyUrl = StudyFile.studyFileUrl(onJatos, params);
    if (!studyUrl) {
      showStartError(`<p>Running locally: add the study folder to the address, e.g.
        <code>index.html?study=heights-film&amp;dim=anxiety&amp;reset=1</code> (a folder in <code>studies/</code>).</p>`);
      return;
    }
    try {
      study = await StudyFile.loadStudy(studyUrl);
    } catch (err) {
      showStartError(`<p>The study could not start: ${err.message}</p>`);
      console.error(err);
      return;
    }
    const cfg = Object.assign({}, StudyFile.buildConfig(study), onJatos && jatos.studyInput ? jatos.studyInput : {});
    window.CONFIG = cfg; // for debugging and the automated run-through (tests/e2e_local.py)
    const testing = StudyFile.testParams(params, onJatos, cfg); // {} for participants on JATOS

    loadSession(params.reset === "1");
    setSession({ n_loads: (session.n_loads || 0) + 1 });

    // Dimension and input mode stay fixed across reloads.
    let dimKey = session.dim || params.dim;
    if (!cfg.dimensions[dimKey]) {
      dimKey = cfg.assignable[Math.floor(Math.random() * cfg.assignable.length)];
    }
    const dim = cfg.dimensions[dimKey];
    const inputMode = session.input || (["joystick", "slider"].includes(params.input) ? params.input : cfg.inputMode);
    const is2D = dim.axes === 2;
    const isJoy = inputMode === "joystick" || is2D;
    setSession({ dim: dimKey, input: inputMode });

    const videoUrl = testing.video || (onJatos ? cfg.videoUrl : cfg.localVideoUrl);
    const resumeFilm = !!session.practice_done && !session.film_done;
    const skipToQuestions = !!session.film_done;
    const resumeFrom = resumeFilm && session.film_t ? Math.max(0, session.film_t - cfg.resumeRewindSeconds) : 0;
    const startTime = resumeFrom || parseFloat(testing.start_time) || 0; // start_time param: testing only

    installIntegrityGuards();
    let exitReason = null; // e.g. "slow_download"

    // on_finish also runs after abortExperiment (consent refused, device excluded).
    const jsPsych = initJsPsych({
      // Save every non-rating trial as soon as it finishes (rating trials stream their own chunks), so
      // answers given before a reload (e.g. the pre-film STICSA) are never lost.
      on_trial_finish: (d) => {
        if (d.task !== "film" && d.task !== "practice") appendLine({ type: "trial", t: new Date().toISOString(), trial: d });
      },
      on_trial_start: (t) => {
        if (t.type !== jsPsychContinuousRating && document.pointerLockElement) document.exitPointerLock();
        currentTask = (t.data && t.data.task) || (t.data && t.data.page) || (t.type && t.type.info && t.type.info.name) || "?";
      },
      on_finish: () => {
        const data = jsPsych.data.get();
        const consent = data.filter({ task: "consent" }).values()[0];
        if (data.filter({ task: "end" }).count() > 0) {
          finishAndRedirect(cfg.prolific.completeUrl, jsPsych);
        } else if (exitReason === "slow_download") {
          appendLine({ type: "final", t: new Date().toISOString(), excluded: "slow_download", summary: qualitySummary(jsPsych), data: data.values() });
          setTimeout(() => (onJatos ? jatos.endStudyAndRedirect(cfg.prolific.slowDownloadUrl) : finishAndRedirect(cfg.prolific.slowDownloadUrl, jsPsych)), 8000);
        } else if (consent && !consent.consent) {
          setTimeout(() => finishAndRedirect(cfg.prolific.noConsentUrl, jsPsych), 3000);
        } else {
          // Excluded (e.g. device check): save what we have, leave the message on screen.
          appendLine({ type: "final", t: new Date().toISOString(), excluded: true, data: data.values() });
        }
      },
    });

    const ids = {
      prolific_pid: params.PROLIFIC_PID || null,
      prolific_study_id: params.STUDY_ID || null,
      prolific_session_id: params.SESSION_ID || null,
      jatos_study_result_id: onJatos ? jatos.studyResultId : null,
      dimension: dimKey,
      study: dim.study,
      dimension_assigned_by: params.dim === dimKey ? "url" : "random",
      input_mode: inputMode,
    };
    jsPsych.data.addProperties(ids);
    appendLine({
      type: "meta",
      t: new Date().toISOString(),
      ...ids,
      user_agent: navigator.userAgent,
      screen: [screen.width, screen.height],
      config_version: "0.5.0",
      n_loads: session.n_loads,
      resumed_film_from: resumeFilm ? startTime : null,
      skipped_to_questions: skipToQuestions,
    });

    const onChunk = (c) => appendLine({ type: "chunk", t: new Date().toISOString(), ...c });

    const scaleProps = {
      question: dim.question,
      low_label: dim.low,
      mid_label: dim.mid || "",
      high_label: dim.high,
      input_mode: is2D ? "joystick" : inputMode,
      axes: is2D ? 2 : 1,
      x_low_label: dim.xLow || "",
      x_high_label: dim.xHigh || "",
      start_value_x: dim.startX ?? 50,
      joystick_full_scale_frac: cfg.joystickFullScaleFrac,
      sample_rate_hz: cfg.sampleRateHz,
      chunk_seconds: cfg.chunkSeconds,
      on_chunk: onChunk,
    };

    // Questionnaire pages from the study file. {placeholders} in their texts are filled from the
    // study's "about" section plus these values.
    const textValues = Object.assign({}, study.about, {
      film_length: cfg.filmLengthText,
      dimension_label: dim.label,
      rating_control: isJoy ? "mouse control" : "slider",
    });
    const fill = (text) => StudyFile.fillText(text, textValues);
    const qctx = { study, fill, session, setSession, integrity };
    const questionnaire = (slot) => (study.questionnaires || {})[slot] || [];
    const texts = study.texts;

    // Fresh start: consent .. practice. After a reload past the practice these are skipped.
    const intro = [];
    const timeline = [];

    // Participant information + consent (texts in the study file). The consent button is enabled
    // only once every statement is ticked; declining is always possible.
    intro.push({
      type: jsPsychHtmlButtonResponse,
      stimulus: `<div class="text-page consent">
        <div class="info-sheet">${fill(texts.information)}</div>
        <h3>Consent</h3>
        <p>Please tick each statement to take part:</p>
        <ul class="consent-list">
          ${texts.consent_statements
            .map((t, i) => `<li><label><input type="checkbox" class="consent-cb" data-i="${i}"> ${t}</label></li>`)
            .join("")}
        </ul></div>`,
      choices: [texts.consent_button, texts.decline_button],
      on_load: () => {
        const btns = document.querySelectorAll("#jspsych-html-button-response-btngroup button");
        const boxes = [...document.querySelectorAll(".consent-cb")];
        const update = () => (btns[0].disabled = !boxes.every((b) => b.checked));
        boxes.forEach((b) => b.addEventListener("change", update));
        update();
      },
      data: { task: "consent" },
      on_finish: (d) => {
        d.consent = d.response === 0;
        d.consent_statements = texts.consent_statements;
        if (!d.consent) {
          jsPsych.abortExperiment(TEXTS.noConsent);
        } else {
          setSession({ consented: true });
        }
      },
    });

    // Device check
    intro.push({
      type: jsPsychBrowserCheck,
      minimum_width: cfg.minScreen.width,
      minimum_height: cfg.minScreen.height,
      inclusion_function: (d) => !d.mobile,
      exclusion_message: (d) => (d.mobile ? TEXTS.deviceExclusionMobile : TEXTS.deviceExclusionSize),
      data: { task: "browser_check" },
      on_finish: (d) => {
        if (cfg.preload && !d.mobile) startPreload(videoUrl);
      },
    });


    // Questionnaires before the practice (heights study: fear of heights + attention check 1).
    for (const page of questionnaire("intro")) intro.push(Questionnaires.makePage(page, qctx));

    intro.push({
      type: jsPsychFullscreen,
      fullscreen_mode: true,
      message: `<div class="text-page"><p>The study runs in full-screen mode. Please stay in full screen
        and on this page until the end.</p></div>`,
      button_label: "Switch to full screen",
      data: { task: "fullscreen" },
    });

    // Instructions
    intro.push({
      type: jsPsychInstructions,
      show_clickable_nav: true,
      button_label_next: "Next",
      button_label_previous: "Back",
      data: { task: "instructions" },
      pages: [
        `<div class="text-page"><h2>Your task</h2>
          <p>You will watch a film that lasts ${cfg.filmLengthText}.</p>
          <p class="notice"><b>Please watch the video carefully, in a quiet room without distractions.</b>
          Close other programs and put your phone away until the film has finished.</p>
          <p>The whole time, please use ${isJoy ? "the mouse" : "the slider under the film"} to show</p>
          <p class="big">${dim.question}</p>
          ${dim.note ? `<p>${dim.note}</p>` : ""}
          <p>Change your rating <b>whenever your feelings change</b>, and leave it where it is when they don't.
          There are no right or wrong answers: we are interested in your own experience, moment by moment.</p></div>`,
        is2D
          ? `<div class="text-page"><h2>How to rate</h2>
          <p>During the film the mouse pointer is hidden. A small square in the lower-right corner of the film
          shows a white dot. <b>Move the mouse</b> to move the dot (you don't need to click):</p>
          <ul>
            <li><b>Left &ndash; right:</b> how <i>unpleasant</i> or <i>pleasant</i> you feel. The centre is neutral.</li>
            <li><b>Down &ndash; up:</b> how <i>activated</i> you feel, from low to high activation. Activation means
            feeling activated or stirred up, regardless of whether the feeling is pleasant or unpleasant.</li>
          </ul>
          <p>For example, feeling tense and uneasy is up and to the left; relaxed and content is down and to the right.
          The dot stays where you leave it, so keep your eyes on the film and glance at the square from the corner of
          your eye. Keep your hand on the mouse the whole time.</p>
          <p>The film cannot be paused or skipped. If you press Esc, leave full-screen mode or switch tabs,
          the film pauses until you come back.</p>
          <p>First, a 40-second practice: an orange marker will move around the square and your job is to
          keep the white dot on it.</p></div>`
          : isJoy
          ? `<div class="text-page"><h2>How to rate</h2>
          <p>During the film the mouse pointer is hidden. <b>Moving the mouse up and down</b> moves a white bar
          in a small scale in the lower-right corner of the film: <b>up</b> means more (<i>${dim.high}</i>), <b>down</b> means less
          (<i>${dim.low}</i>). You don't need to click.</p>
          <p>The bar stays where you leave it, so you can keep your eyes on the film and just glance at the bar
          from the corner of your eye. Keep your hand on the mouse the whole time.</p>
          <p>The film cannot be paused or skipped. If you press Esc, leave full-screen mode or switch tabs,
          the film pauses until you come back.</p>
          <p>First, a 40-second practice: an orange marker will move up and down the bar and your job is to
          keep the white bar level with it.</p></div>`
          : `<div class="text-page"><h2>Using the slider</h2>
          <p>Drag the slider with your mouse. The arrow keys also work.</p>
          <p>The film cannot be paused or skipped. If you leave full-screen mode or switch tabs,
          the film will pause until you come back.</p>
          <p>First, a 40-second practice: an orange marker will move along the slider and your job is to
          keep the slider on it.</p></div>`,
      ],
    });

    // Practice (repeat once if tracking error too large)
    let practiceRuns = 0;
    let practicePassed = false;
    intro.push({
      timeline: [
        {
          type: jsPsychContinuousRating,
          practice_keyframes: is2D ? cfg.practiceKeyframes2D : cfg.practiceKeyframes,
          ...scaleProps,
          question: is2D
            ? "Practice: move the mouse to keep the white dot on the orange marker"
            : isJoy
            ? "Practice: move the mouse up and down to keep the white bar level with the orange marker"
            : "Practice: keep the slider on the orange marker",
          low_label: "",
          mid_label: "",
          high_label: "",
          x_low_label: "",
          x_high_label: "",
          start_value: 50,
          require_initial_set: false,
          start_prompt: () =>
            practiceRuns === 0
              ? `<p>Ready for the practice?</p>${isJoy ? `<p>After you click, the pointer disappears. Move the mouse${is2D ? "" : " up and down"} &mdash; no clicking needed.</p>` : ""}`
              : `<p>Let's try that once more. Keep the ${is2D ? "white dot" : isJoy ? "white bar" : "slider"} as close to the orange marker as you can.</p>`,
          start_button_label: "Start practice",
          tag: () => `practice_${practiceRuns + 1}`,
          data: { task: "practice" },
          on_finish: (d) => {
            practiceRuns++;
            d.practice_run = practiceRuns;
            practicePassed = d.practice_mae !== null && d.practice_mae <= (is2D ? cfg.practiceMaxErr2D : cfg.practiceMaxMae);
            d.practice_passed = practicePassed;
          },
        },
      ],
      loop_function: () => {
        const again = !practicePassed && practiceRuns < 2;
        if (!again) setSession({ practice_done: true });
        return again;
      },
    });

    // 2D only: practise placing feelings in the grid, incl. unpleasant/activated vs unpleasant/calm.
    if (is2D) {
      intro.push({
        type: jsPsychHtmlButtonResponse,
        stimulus: TEXTS.quadrantIntro,
        choices: ["Start"],
        data: { task: "quadrant_intro" },
      });
      intro.push({
        timeline: [
          {
            type: jsPsychAffectPlacement,
            scenario: jsPsych.timelineVariable("scenario"),
            expected: jsPsych.timelineVariable("expected"),
            explanation: jsPsych.timelineVariable("explanation"),
            x_low_label: dim.xLow,
            x_high_label: dim.xHigh,
            low_label: dim.low,
            high_label: dim.high,
            joystick_full_scale_frac: cfg.joystickFullScaleFrac,
            data: { task: "quadrant_practice" },
          },
        ],
        timeline_variables: TEXTS.quadrantScenarios,
        randomize_order: true,
      });
    }

    // Wait for the film download if it is not finished yet (skipped when ready).
    const downloadGate = {
      timeline: [
        {
          type: jsPsychHtmlButtonResponse,
          stimulus: `<div class="text-page"><h2>Preparing the film</h2>
            <p>The film is still downloading. This depends on your internet connection &ndash; please wait,
            the study will continue automatically.</p>
            <p class="muted">If the download takes more than ${Math.round(cfg.preloadMaxWaitMs / 60000)} minutes, the
            study will end and you will be asked to return it (without penalty).</p>
            <div class="dl-bar"><div class="dl-fill" id="dl-fill"></div></div>
            <p class="muted" id="dl-text">Starting&hellip;</p></div>`,
          choices: [],
          data: { task: "download_gate" },
          on_load: () => {
            const t0 = performance.now();
            const tick = () => {
              const fill = document.getElementById("dl-fill");
              const txt = document.getElementById("dl-text");
              const waited = performance.now() - t0;
              const maxWait = parseFloat(testing.max_wait_s) * 1000 || cfg.preloadMaxWaitMs; // max_wait_s: testing
              if (!preload.done && (preload.failed || waited > maxWait) && cfg.returnOnSlowDownload) {
                exitReason = "slow_download";
                appendLine({ type: "preload", e: "gave_up", t: new Date().toISOString(), waited_ms: Math.round(waited),
                             bytes: preload.bytes, total: preload.total, failed: preload.failed });
                jsPsych.abortExperiment(TEXTS.slowDownload);
                return;
              }
              if (preload.done || preload.failed || waited > maxWait) {
                jsPsych.finishTrial({ wait_ms: Math.round(waited), gave_up: !preload.done });
                return;
              }
              if (fill && preload.total) fill.style.width = `${Math.min(100, (100 * preload.bytes) / preload.total)}%`;
              if (txt) {
                const mb = (x) => Math.round(x / 1e6);
                txt.textContent = preload.total
                  ? `${mb(preload.bytes)} of ${mb(preload.total)} MB`
                  : `${mb(preload.bytes)} MB downloaded`;
              }
              setTimeout(tick, 250);
            };
            tick();
          },
        },
      ],
      conditional_function: () => {
        if (!cfg.preload) return false;
        if (!preload.started) startPreload(videoUrl); // e.g. after a reload or ?skip=intro
        // Show whenever the film is not fully downloaded - including after an early failure, so that a failed
        // download ends in the return path (or, if returnOnSlowDownload is off, in streaming) via the tick below.
        return !preload.done;
      },
    };

    // Local testing only: ?skip=intro jumps straight to the film.
    const skipIntro = !onJatos && params.skip === "intro";
    if (!resumeFilm && !skipToQuestions && !skipIntro) timeline.push(...intro);
    if (!skipToQuestions) timeline.push(downloadGate);
    // Questionnaires right before the film, each shown once (heights study: STICSA pre).
    for (const page of questionnaire("before_film")) {
      if (!skipToQuestions && !session[`${Questionnaires.pageKey(page)}_done`]) {
        timeline.push(Questionnaires.makeOncePage(page, qctx));
      }
    }

    // Main film
    if (resumeFilm) {
      timeline.push({
        type: jsPsychHtmlButtonResponse,
        stimulus: `<div class="text-page"><h2>Welcome back</h2>
          <p>The film will continue from where you left off (starting a few seconds earlier).</p>
          <p>As before, please rate: <b>${dim.question}</b></p></div>`,
        choices: ["Continue"],
        data: { task: "resume_notice" },
      });
      timeline.push({
        type: jsPsychFullscreen,
        fullscreen_mode: true,
        message: `<div class="text-page"><p>The film runs in full-screen mode.</p></div>`,
        button_label: "Switch to full screen",
        data: { task: "fullscreen" },
      });
    }
    let filmSource = null;
    if (!skipToQuestions) {
      timeline.push({
        type: jsPsychContinuousRating,
        // Play the downloaded copy when available; otherwise stream.
        video_url: () => (preload.done ? preload.url : videoUrl),
        on_start: () => {
          filmSource = preload.done ? "download" : "stream"; // decided when the film trial starts
        },
        muted: cfg.muted,
        start_time: startTime,
        ...scaleProps,
        on_chunk: (c) => {
          onChunk(c);
          if (c.samples.length) setSession({ film_t: c.samples[c.samples.length - 1][0] });
        },
        start_value: dim.start,
        start_prompt: isJoy
          ? `<p><b>Please watch the video carefully, in a quiet room without distractions.</b></p>
             <p>When you click the button the pointer will disappear.</p>
             <p>First move the mouse to set the ${is2D ? "dot" : "bar"} to how you feel <b>right now</b>, then press <b>SPACE</b>
             to start the film. Keep rating until the film ends.</p>`
          : `<p><b>Please watch the video carefully, in a quiet room without distractions.</b></p>
             <p>Before the film starts, set the slider to show how you feel <b>right now</b>.</p>
             <p>Then press Start. Keep rating until the film ends.</p>`,
        start_button_label: isJoy ? "Continue" : "Start the film",
        arming_prompt: `Move the mouse${is2D ? "" : " up or down"} to show how you feel <b>right now</b>.<br>Then press <b>SPACE</b> to start.`,
        tag: resumeFilm ? `film_resume_${session.n_loads}` : "film",
        data: { task: "film", resumed: resumeFilm },
        on_finish: (d) => {
          d.video_source = filmSource;
          setSession({ film_done: true });
        },
      });
    }

    // Questionnaires immediately after playback, each shown once (heights study: STICSA post).
    for (const page of questionnaire("after_film")) {
      if (!session[`${Questionnaires.pageKey(page)}_done`]) timeline.push(Questionnaires.makeOncePage(page, qctx));
    }

    // Post-film questions
    timeline.push({
      type: jsPsychFullscreen,
      fullscreen_mode: false,
      delay_after: 0,
    });
    // Heights study: feelings, bodily sensations, rating task (+ attention check 2), seen before,
    // written description, feedback.
    for (const page of questionnaire("end")) timeline.push(Questionnaires.makePage(page, qctx));


    timeline.push({
      type: jsPsychHtmlButtonResponse,
      stimulus: fill(texts.debrief),
      choices: ["Finish and return to Prolific"],
      data: { task: "end" },
    });

    jsPsych.run(timeline);
  }

  if (onJatos) jatos.onLoad(run);
  else window.addEventListener("load", run);
})();
