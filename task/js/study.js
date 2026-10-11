/**
 * The study file: everything specific to one study (film, rating scales, texts, questionnaires,
 * Prolific codes) is in studies/<name>/study.yaml. This file loads it and turns it into the settings
 * the task uses.
 *
 *   On JATOS:  study.yaml next to index.html (uploaded by scripts/deploy_jatos.py --study ...).
 *   Locally:   index.html?study=<name> loads ../studies/<name>/study.yaml.
 *
 * The task settings keep the names they had in v1.0 (config.js), so JATOS study properties ->
 * "Study input" can still override them without redeploying, e.g. {"videoUrl": "https://.../film.mp4"}
 * or {"testMode": true} for a test run.
 */
var StudyFile = (function () {
  "use strict";

  const PROLIFIC_COMPLETE_URL = "https://app.prolific.com/submissions/complete?cc=";

  /** Address of the study file, or null when running locally without ?study=<name>. */
  function studyFileUrl(onJatos, params) {
    if (onJatos) return "study.yaml";
    const name = params.study;
    if (!name || !/^[\w-]+$/.test(name)) return null;
    return `../studies/${name}/study.yaml`;
  }

  /** Download the study file and read it (YAML, read with js-yaml). */
  async function loadStudy(url) {
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) throw new Error(`could not load the study file ${url} (HTTP ${resp.status})`);
    return jsyaml.load(await resp.text());
  }

  /** Replace {placeholders} in a text with values; placeholders without a value are left as they are. */
  function fillText(text, values) {
    return String(text).replace(/\{(\w+)\}/g, (whole, key) => (key in values ? String(values[key]) : whole));
  }

  /** snake_case -> camelCase (x_low -> xLow), for the rating-dimension settings. */
  const camel = (key) => key.replace(/_(\w)/g, (m, c) => c.toUpperCase());

  /** The task settings (v1.0 CONFIG names) from the study file. */
  function buildConfig(study) {
    const film = study.film;
    const rating = study.rating;
    const practice = study.practice;
    const codes = study.prolific.completion_codes;
    const dimensions = {};
    for (const [name, dim] of Object.entries(rating.dimensions)) {
      dimensions[name] = Object.fromEntries(Object.entries(dim).map(([k, v]) => [camel(k), v]));
    }
    return {
      videoUrl: film.file,
      // the local film path is relative to the repository folder; index.html is in task/
      localVideoUrl: `../${film.local_file}`,
      filmLengthText: film.length_text,
      preload: film.preload,
      preloadMaxWaitMs: film.preload_max_wait_minutes * 60 * 1000,
      returnOnSlowDownload: film.return_on_slow_download,
      muted: film.muted,
      inputMode: rating.input_mode,
      joystickFullScaleFrac: rating.joystick_full_scale_frac,
      resumeRewindSeconds: rating.resume_rewind_seconds,
      sampleRateHz: rating.sample_rate_hz,
      chunkSeconds: rating.chunk_seconds,
      practiceMaxMae: practice.max_error_1d,
      practiceMaxErr2D: practice.max_error_2d,
      practiceKeyframes2D: practice.keyframes_2d,
      practiceKeyframes: practice.keyframes_1d,
      minScreen: { width: rating.min_screen_width, height: rating.min_screen_height },
      prolific: {
        completeUrl: PROLIFIC_COMPLETE_URL + codes.complete.code,
        noConsentUrl: PROLIFIC_COMPLETE_URL + codes.no_consent.code,
        slowDownloadUrl: PROLIFIC_COMPLETE_URL + codes.slow_download.code,
      },
      assignable: rating.assignable,
      dimensions,
      testMode: study.test_mode === true,
    };
  }

  /**
   * The testing URL parameters start_time (start the film late), max_wait_s (shorter download wait) and
   * video (another film). They only work when running locally or in test mode, so a participant on
   * JATOS cannot use them. Returns {} otherwise.
   */
  function testParams(params, onJatos, cfg) {
    if (onJatos && cfg.testMode !== true) return {};
    return { start_time: params.start_time, max_wait_s: params.max_wait_s, video: params.video };
  }

  return { studyFileUrl, loadStudy, fillText, buildConfig, testParams };
})();

if (typeof module !== "undefined") module.exports = StudyFile; // for the tests (node)
