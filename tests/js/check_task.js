/**
 * Known-answer checks of the browser modules task/js/study.js and task/js/questionnaires.js, run in node.
 * Usage: node tests/js/check_task.js <study as JSON>   (tests/test_task_js.py runs this)
 *
 * The expected values are those of v1.0-heights-film (task/js/config.js, texts.js and experiment.js),
 * copied by hand: with the heights study file the task must get exactly these settings and pages.
 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");

// The jsPsych plugins are globals in the browser; here plain names stand in for them.
for (const name of ["jsPsychSurveyLikert", "jsPsychSurveyMultiChoice", "jsPsychSurveyMultiSelect", "jsPsychSurveyText",
                    "jsPsychSurveyHtmlForm", "jsPsychHtmlButtonResponse"]) {
  global[name] = name;
}
const StudyFile = require(path.join(__dirname, "../../task/js/study.js"));
const Questionnaires = require(path.join(__dirname, "../../task/js/questionnaires.js"));

const study = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let passed = 0;
function check(name, fn) {
  fn();
  passed++;
  console.log("ok -", name);
}

// ---------------------------------------------------------------- task settings (CONFIG) ---
const V1_CONFIG = {
  videoUrl: "towerClimb_crf29.mp4",
  localVideoUrl: "../media/towerClimb_crf29.mp4",
  filmLengthText: "about 13½ minutes",
  preload: true,
  preloadMaxWaitMs: 5 * 60 * 1000,
  returnOnSlowDownload: true,
  muted: true,
  inputMode: "joystick",
  joystickFullScaleFrac: 0.6,
  resumeRewindSeconds: 5,
  sampleRateHz: 20,
  chunkSeconds: 30,
  practiceMaxMae: 15,
  practiceMaxErr2D: 20,
  practiceKeyframes2D: [[0, 20, 20], [6, 20, 20], [6, 80, 80], [12, 80, 80], [12, 20, 80], [18, 20, 80],
                        [18, 80, 20], [24, 80, 20], [24, 50, 50], [28, 50, 50], [36, 90, 65], [40, 90, 65]],
  practiceKeyframes: [[0, 15], [7, 15], [7, 85], [14, 85], [14, 50], [19, 50], [29, 95], [34, 95], [34, 30], [40, 30]],
  minScreen: { width: 1000, height: 600 },
  prolific: {
    completeUrl: "https://app.prolific.com/submissions/complete?cc=VMPDONE1",
    noConsentUrl: "https://app.prolific.com/submissions/complete?cc=VMPNOCON",
    slowDownloadUrl: "https://app.prolific.com/submissions/complete?cc=VMPSLOWD",
  },
  assignable: ["anxiety", "affect2d"],
  dimensions: {
    anxiety: {
      study: 1,
      axes: 1, // new: v1.0 left it out (meaning 1)
      label: "how tense or anxious you felt",
      question: "How <b>tense or anxious</b> do you feel right now?",
      low: "Not at all",
      high: "Extremely",
      start: 0,
      note: "This is about your own feelings while watching, including feeling anxious for the people on screen.",
    },
    affect2d: {
      study: 2,
      axes: 2,
      label: "how pleasant or unpleasant and how activated you felt",
      question: "How do you feel right now? <b>Left&ndash;right:</b> unpleasant&ndash;pleasant. <b>Down&ndash;up:</b> low&ndash;high activation.",
      xLow: "Unpleasant",
      xHigh: "Pleasant",
      low: "Low activation",
      high: "High activation",
      start: 50,
      startX: 50,
      note: "Left&ndash;right shows how unpleasant or pleasant you feel (neutral in the centre). Down&ndash;up shows how activated you feel: feeling activated or stirred up, regardless of whether the feeling is pleasant or unpleasant.",
    },
  },
  testMode: false, // new
};
const cfg = StudyFile.buildConfig(study);

check("heights study gives the v1.0 task settings", () => assert.deepStrictEqual(cfg, V1_CONFIG));

check("placeholders are filled, unknown ones kept", () => {
  assert.strictEqual(StudyFile.fillText("Contact {pi_name} at {x}.", { pi_name: "A. B." }), "Contact A. B. at {x}.");
});

check("study file address: JATOS, local, local without ?study", () => {
  assert.strictEqual(StudyFile.studyFileUrl(true, { study: "other" }), "study.yaml");
  assert.strictEqual(StudyFile.studyFileUrl(false, { study: "heights-film" }), "../studies/heights-film/study.yaml");
  assert.strictEqual(StudyFile.studyFileUrl(false, {}), null);
  assert.strictEqual(StudyFile.studyFileUrl(false, { study: "../../etc" }), null);
});

// -------------------------------------------------- testing URL parameters (problem 4a) ---
check("testing URL parameters are ignored for participants on JATOS", () => {
  const params = { start_time: "795", max_wait_s: "1", video: "https://x/y.mp4", dim: "anxiety" };
  assert.deepStrictEqual(StudyFile.testParams(params, true, cfg), {});
  // only an explicit true switches test mode on (not a missing setting or the text "true")
  assert.deepStrictEqual(StudyFile.testParams(params, true, {}), {});
  assert.deepStrictEqual(StudyFile.testParams(params, true, { testMode: "true" }), {});
  assert.deepStrictEqual(StudyFile.testParams(params, true, { ...cfg, testMode: true }),
                         { start_time: "795", max_wait_s: "1", video: "https://x/y.mp4" });
  assert.deepStrictEqual(StudyFile.testParams(params, false, cfg),
                         { start_time: "795", max_wait_s: "1", video: "https://x/y.mp4" });
});

// ------------------------------------------------------------------- questionnaire pages ---
let session = {};
const ctx = {
  study,
  fill: (t) => StudyFile.fillText(t, { ...study.about, rating_control: "mouse control" }),
  session,
  setSession: (patch) => Object.assign(session, patch),
  integrity: { away_ms: 0 },
};
const page = (slot, i) => Questionnaires.makePage(study.questionnaires[slot][i], ctx);
const likert7 = (low, high) => [low, "", "", "", "", "", high];

check("pre-film page: v1.0 questions, saved as an attention page", () => {
  const t = page("intro", 0);
  assert.strictEqual(t.type, "jsPsychSurveyLikert");
  assert.strictEqual(t.preamble, "<h3>A few questions about you</h3>");
  assert.deepStrictEqual(t.questions, [
    { name: "height_fear", prompt: "In everyday life, how afraid are you of heights?", labels: likert7("Not at all", "Extremely"), required: true },
    { name: "attention_1", prompt: "To show that you are reading carefully, please select <b>Strongly disagree</b> for this statement.",
      labels: ["Strongly disagree", "Disagree", "Agree", "Strongly agree"], required: true },
  ]);
  assert.deepStrictEqual(t.data, { page: "pre_film" });
  const d = { ...t.data, response: { height_fear: 2, attention_1: 1 } }; // attention check failed
  t.on_finish(d);
  assert.deepStrictEqual(d, {
    page: "pre_film", response: { height_fear: 2, attention_1: 1 }, pre_film: { height_fear: 2, attention_1: 1 },
    n_checks: 1, n_failed: 1, attention: { attention_1: false }, task: "attention",
  });
});

check("usability page: {rating_control} filled, attention check 2 passed at index 6", () => {
  const t = page("end", 2);
  assert.strictEqual(t.questions[1].prompt, "How difficult was it to use the mouse control to give your ratings?");
  const d = { ...t.data, response: { distracting: 0, difficult: 1, attention_2: 6 } };
  t.on_finish(d);
  assert.deepStrictEqual([d.task, d.page, d.n_failed, d.attention], ["attention", "usability", 0, { attention_2: true }]);
  assert.deepStrictEqual(d.usability, { distracting: 0, difficult: 1, attention_2: 6 });
});

check("post-film pages without attention checks are saved by task name", () => {
  assert.deepStrictEqual(page("end", 0).data, { task: "post_feelings" });
  assert.strictEqual(page("end", 0).on_finish, undefined);
  const body = page("end", 1);
  assert.deepStrictEqual([body.type, body.data, body.questions[0].options.length], ["jsPsychSurveyMultiSelect", { task: "post_body" }, 8]);
  const mc = page("end", 3);
  assert.deepStrictEqual(mc.questions.map((q) => [q.name, q.options]), [
    ["seen_before", ["Yes", "No", "Not sure"]], ["full_attention", ["Yes", "Mostly", "No"]],
    ["input_device", ["Mouse", "Trackpad / touchpad", "Other"]]]);
  const fb = page("end", 5);
  assert.deepStrictEqual(fb.questions, [{ name: "feedback", prompt: "Do you have any comments or feedback about the study, the rating task, or any technical difficulties you experienced? (Optional)", required: false, rows: 5 }]);
  assert.deepStrictEqual(page("end", 4).data, { task: "final_text" });
});

check("STICSA pre and post: items, totals, change, session keys", () => {
  const pre = Questionnaires.makeOncePage(study.questionnaires.before_film[0], ctx);
  assert.deepStrictEqual(pre.data, { task: "sticsa", timepoint: "pre" });
  assert.strictEqual((pre.html.match(/name="sticsa_\d+"/g) || []).length, 11 * 4);
  assert.ok(pre.preamble.includes("<h2>Current feelings</h2>"));
  const numbers = [1, 2, 6, 7, 8, 12, 14, 15, 18, 20, 21];
  const answer = (values) => Object.fromEntries(numbers.map((n, i) => [`sticsa_${n}`, String(values[i])]));
  const dPre = { ...pre.data, response: answer([1, 2, 1, 1, 2, 1, 1, 1, 1, 2, 1]) }; // total 14
  pre.on_load();
  pre.on_finish(dPre);
  assert.strictEqual(dPre.total, 14);
  assert.deepStrictEqual(dPre.items[0], { item: 1, text: "My heart beats fast.", response: 1 });
  assert.deepStrictEqual([session.sticsa_pre_done, session.sticsa_pre_total], [true, 14]);

  const post = Questionnaires.makeOncePage(study.questionnaires.after_film[0], ctx);
  const values = [2, 3, 2, 1, 2, 2, 1, 2, 3, 2, 2]; // total 22
  const dPost = { ...post.data, response: answer(values) };
  post.on_load();
  post.on_finish(dPost);
  assert.deepStrictEqual([dPost.total, dPost.pre_total, dPost.change], [22, 14, 8]);

  // one item missing: no total (never counted as 0) and no change
  const missing = answer(values);
  delete missing.sticsa_21;
  const dMissing = { ...post.data, response: missing };
  post.on_finish(dMissing);
  assert.deepStrictEqual([dMissing.n_answered, dMissing.total, dMissing.change], [10, null, null]);
});

check("post STICSA without a saved pre total: pre_total and change are null, not 0", () => {
  const fresh = { ...ctx, session: {}, setSession: () => {} };
  const post = Questionnaires.makePage(study.questionnaires.after_film[0], fresh);
  const numbers = [1, 2, 6, 7, 8, 12, 14, 15, 18, 20, 21];
  const d = { ...post.data, response: Object.fromEntries(numbers.map((n) => [`sticsa_${n}`, "1"])) };
  post.on_load();
  post.on_finish(d);
  assert.deepStrictEqual([d.total, d.pre_total, d.change], [11, null, null]);
});

check("other pages shown once remember <name>_done", () => {
  const t = Questionnaires.makeOncePage({ type: "multi_choice", name: "mood", questions: [{ name: "q", prompt: "?", options: ["a"] }] }, ctx);
  t.on_finish({});
  assert.strictEqual(session.mood_done, true);
});

console.log(`${passed} checks passed`);
