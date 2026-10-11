/**
 * Questionnaire pages from the study file (section `questionnaires`: intro, before_film, after_film, end).
 * Each page in the study file becomes one jsPsych trial, built from a standard survey plugin:
 *
 *   likert        jsPsych survey-likert; questions with `correct: <index>` are attention checks
 *   multi_choice  jsPsych survey-multi-choice
 *   multi_select  jsPsych survey-multi-select
 *   text          jsPsych survey-text
 *   free_text     a longer written answer with a minimum word count and typing statistics
 *   scale         a rating table from the study file's `scales` (e.g. the STICSA), saved per item with a total
 *   html_form     jsPsych survey-html-form with the page's own `html`
 *
 * How pages are saved (field names as in v1.0, see docs/data.md):
 *   - every page: task = the page name (a scale page: task = the scale name, plus its timepoint)
 *   - a likert page with an attention check: task = "attention", page = the page name, the answers also in a
 *     field named after the page, plus n_checks, n_failed and attention ({check name: passed})
 *
 * `ctx` gives each page what it needs from the running session:
 *   { study, fill (fills {placeholders} in a text), session (saved progress), setSession, integrity }
 */
var Questionnaires = (function () {
  "use strict";

  const required = (q) => q.required !== false; // questions are required unless they say otherwise

  /** The jsPsych trial for one questionnaire page. */
  function makePage(page, ctx) {
    if (page.type === "likert") return likertPage(page, ctx);
    if (page.type === "multi_choice") return choicePage(jsPsychSurveyMultiChoice, page, ctx);
    if (page.type === "multi_select") return choicePage(jsPsychSurveyMultiSelect, page, ctx);
    if (page.type === "text") return textPage(page, ctx);
    if (page.type === "free_text") return freeTextPage(page, ctx);
    if (page.type === "scale") return scalePage(page, ctx);
    if (page.type === "html_form") return htmlFormPage(page, ctx);
    throw new Error(`unknown questionnaire page type "${page.type}" (page "${page.name}")`);
  }

  /** Session key of a page that is shown once (also after a reload): e.g. sticsa_pre, or the page name. */
  function pageKey(page) {
    if (page.type !== "scale") return page.name;
    return page.timepoint ? `${page.scale}_${page.timepoint}` : page.scale;
  }

  /** Like makePage, but the page is remembered as done (`<key>_done` in the session) once answered. */
  function makeOncePage(page, ctx) {
    const trial = makePage(page, ctx);
    if (page.type === "scale") return trial; // scale pages save <key>_done and <key>_total themselves
    const onFinish = trial.on_finish;
    trial.on_finish = (d) => {
      if (onFinish) onFinish(d);
      ctx.setSession({ [`${pageKey(page)}_done`]: true });
    };
    return trial;
  }

  // ---- likert (with optional attention checks) ------------------------------------------
  function likertPage(page, ctx) {
    const trial = {
      type: jsPsychSurveyLikert,
      questions: page.questions.map((q) => ({ name: q.name, prompt: ctx.fill(q.prompt), labels: q.labels, required: required(q) })),
    };
    if (page.preamble) trial.preamble = ctx.fill(page.preamble);
    const checks = page.questions.filter((q) => q.correct !== undefined);
    if (!checks.length) {
      trial.data = { task: page.name };
      return trial;
    }
    trial.data = { page: page.name };
    trial.on_finish = (d) => {
      d[page.name] = d.response;
      scoreAttention(d, checks);
    };
    return trial;
  }

  /** Score instructed-response attention checks (`correct` = index of the right option, 0 = leftmost). */
  function scoreAttention(d, checks) {
    d.n_checks = checks.length;
    d.n_failed = checks.filter((c) => d.response[c.name] !== c.correct).length;
    d.attention = Object.fromEntries(checks.map((c) => [c.name, d.response[c.name] === c.correct]));
    d.task = "attention";
    d.page = d.page || "";
  }

  // ---- multiple choice / multi-select ---------------------------------------------------
  function choicePage(plugin, page, ctx) {
    const trial = {
      type: plugin,
      questions: page.questions.map((q) => ({ name: q.name, prompt: ctx.fill(q.prompt), options: q.options, required: required(q) })),
      data: { task: page.name },
    };
    if (page.preamble) trial.preamble = ctx.fill(page.preamble);
    return trial;
  }

  // ---- short typed answers ----------------------------------------------------------------
  function textPage(page, ctx) {
    const questions = page.questions.map((q) => {
      const out = { name: q.name, prompt: ctx.fill(q.prompt), required: required(q) };
      if (q.rows) out.rows = q.rows;
      return out;
    });
    const trial = { type: jsPsychSurveyText, questions, data: { task: page.name } };
    if (page.preamble) trial.preamble = ctx.fill(page.preamble);
    return trial;
  }

  // ---- longer written answer: minimum word count, paste blocked, typing counted ------------
  function freeTextPage(page, ctx) {
    let text = "";
    let nKeys = 0;
    let inputTypes = {}; // InputEvent.inputType counts: distinguishes typing, IME/dictation and other insertions
    let awayStart = 0;
    const minWords = page.min_words;
    const countWords = (t) => (t.trim().match(/\S+/g) || []).length;
    return {
      type: jsPsychHtmlButtonResponse,
      stimulus: `<div class="text-page">${ctx.fill(page.prompt)}
        <textarea id="final-text" rows="10" style="width:100%;font-size:1em"></textarea>
        <p class="muted" id="final-count">0 / ${minWords} words</p></div>`,
      choices: ["Continue"],
      on_load: () => {
        const ta = document.getElementById("final-text");
        const cnt = document.getElementById("final-count");
        const btn = document.querySelector("#jspsych-html-button-response-btngroup button");
        const update = () => {
          text = ta.value;
          const n = countWords(text);
          cnt.textContent = `${n} / ${minWords} words`;
          btn.disabled = n < minWords;
        };
        ta.addEventListener("input", update);
        ta.addEventListener("keydown", () => nKeys++);
        ta.addEventListener("beforeinput", (ev) => {
          const k = ev.inputType || "unknown";
          inputTypes[k] = (inputTypes[k] || 0) + 1;
        });
        ta.addEventListener("compositionend", () => (inputTypes.compositionend = (inputTypes.compositionend || 0) + 1));
        awayStart = ctx.integrity.away_ms;
        update();
        ta.focus();
      },
      data: { task: page.name },
      on_finish: (d) => {
        d.text = text;
        d.n_words = countWords(text);
        d.n_chars = text.length;
        d.n_keys = nKeys; // far fewer keystrokes than characters = text inserted, not typed
        d.input_types = inputTypes;
        d.away_ms = ctx.integrity.away_ms - awayStart; // time spent in other windows while writing
      },
    };
  }

  // ---- rating table (e.g. STICSA somatic subscale) ----------------------------------------
  // Responses start unselected and are required; previous answers/scores are never shown.
  // Missing answers stay null (never 0). The total needs every item answered.
  // (The CSS class names sticsa-* are kept from v1.0 so the page looks exactly the same.)
  function scalePage(page, ctx) {
    const S = ctx.study.scales[page.scale];
    const name = page.scale;
    const timepoint = page.timepoint;
    const key = pageKey(page);
    let onsetIso = null;
    let onsetPerf = 0;
    const head = S.options.map((o) => `<th scope="col">${o.label}</th>`).join("");
    const rows = S.items
      .map(
        ({ item, text }) => `<tr><th scope="row" class="sticsa-item">${text}</th>${S.options
          .map(
            (o) => `<td><label class="sticsa-cell"><input type="radio" name="${name}_${item}" value="${o.value}"
              aria-label="${text} ${o.label}" required></label></td>`
          )
          .join("")}</tr>`
      )
      .join("");
    return {
      type: jsPsychSurveyHtmlForm,
      preamble: `<div class="text-page sticsa-head"><h2>${S.title}</h2><p>${S.instruction}</p></div>`,
      html: `<table class="sticsa-table"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table>`,
      button_label: "Continue",
      data: timepoint ? { task: name, timepoint } : { task: name },
      on_load: () => {
        onsetIso = new Date().toISOString();
        onsetPerf = performance.now();
      },
      on_finish: (d) => {
        d.onset = onsetIso;
        d.completion = new Date().toISOString();
        d.duration_ms = Math.round(performance.now() - onsetPerf);
        d.items = S.items.map(({ item, text }) => {
          const v = d.response[`${name}_${item}`];
          return { item, text, response: v === undefined || v === "" ? null : Number(v) };
        });
        d.n_answered = d.items.filter((i) => i.response !== null).length;
        d.total = d.n_answered === S.items.length ? d.items.reduce((a, i) => a + i.response, 0) : null;
        if (timepoint === "post") {
          d.pre_total = ctx.session[`${name}_pre_total`] ?? null;
          d.change = d.total !== null && d.pre_total !== null ? d.total - d.pre_total : null;
        }
        ctx.setSession({ [`${key}_done`]: true, [`${key}_total`]: d.total });
      },
    };
  }

  // ---- your own HTML form -----------------------------------------------------------------
  function htmlFormPage(page, ctx) {
    const trial = { type: jsPsychSurveyHtmlForm, html: ctx.fill(page.html), button_label: page.button_label || "Continue", data: { task: page.name } };
    if (page.preamble) trial.preamble = ctx.fill(page.preamble);
    return trial;
  }

  return { makePage, makeOncePage, pageKey };
})();

if (typeof module !== "undefined") module.exports = Questionnaires; // for the tests (node)
