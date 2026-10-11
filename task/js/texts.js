/**
 * Participant-facing texts of the platform itself (the same for every study): messages when someone does
 * not consent, is excluded by the device check or cannot download the film, and the 2D affect-grid
 * placement practice.
 *
 * Study-specific texts (information sheet, consent statements, debrief, questionnaires) are in the
 * study file: studies/<name>/study.yaml.
 */
var TEXTS = {
  noConsent: `<div class="text-page"><h2>Thank you</h2>
    <p>You chose not to take part. No data will be used. You will now be returned to Prolific;
    please return the study there.</p></div>`,

  deviceExclusionMobile:
    "<p>This study needs a desktop or laptop computer. Please return the study on Prolific. Thank you for your interest.</p>",
  deviceExclusionSize:
    "<p>Your browser window is too small for this study. Please return the study on Prolific. Thank you for your interest.</p>",

  /** 2D mode: introduction to the grid before the placement practice. */
  quadrantIntro: `<div class="text-page"><h2>Practice: where do feelings go?</h2>
    <p>During the film you will use a square to show how you feel:</p>
    <ul>
      <li><b>Left &ndash; right:</b> unpleasant &ndash; pleasant, with neutral in the centre.</li>
      <li><b>Down &ndash; up:</b> low &ndash; high activation. Activation means feeling activated or stirred up,
      regardless of whether the feeling is pleasant or unpleasant.</li>
    </ul>
    <p>The same area of the square can hold quite different feelings. For example, being nervous and being
    angry are both <i>unpleasant with high activation</i> (upper-left), while being sad or bored is
    <i>unpleasant with low activation</i> (lower-left).</p>
    <p>Next you will read six short situations. For each one, move the dot to where that feeling belongs and press
    <b>SPACE</b>. You'll see where most people would put it.</p></div>`,

  /** 2D placement practice. Two items per unpleasant quadrant; upper-left is deliberately not only fear. */
  quadrantScenarios: [
    {
      scenario: "You are waiting for important test results and your heart is pounding.",
      expected: { valence: "neg", arousal: "high" },
      explanation: "Feeling nervous or tense is unpleasant, with high activation.",
    },
    {
      scenario: "Someone pushes in front of you in a long queue and you feel your face getting hot.",
      expected: { valence: "neg", arousal: "high" },
      explanation: "Anger is also unpleasant with high activation &ndash; this area holds many different feelings, not just fear.",
    },
    {
      scenario: "After a long, disappointing day you feel tired and low.",
      expected: { valence: "neg", arousal: "low" },
      explanation: "Feeling sad or drained is unpleasant, with low activation.",
    },
    {
      scenario: "You are stuck at home on a grey afternoon with nothing to do, feeling bored and sluggish.",
      expected: { valence: "neg", arousal: "low" },
      explanation: "Boredom is unpleasant, with low activation.",
    },
    {
      scenario: "Your favourite team scores the winning goal in the last minute.",
      expected: { valence: "pos", arousal: "high" },
      explanation: "Excitement is pleasant, with high activation.",
    },
    {
      scenario: "You are lying in a warm bath after a good day.",
      expected: { valence: "pos", arousal: "low" },
      explanation: "Relaxed contentment is pleasant, with low activation.",
    },
  ],

  /** Shown when the film cannot be downloaded in time (study ends, participant asked to return). */
  slowDownload: `<div class="text-page"><h2>Sorry &ndash; the film could not be downloaded</h2>
    <p>Unfortunately your internet connection could not download the film quickly enough, so the study cannot
    continue. This is not your fault.</p>
    <p>You will now be sent back to Prolific. <b>Please return the study</b> there &ndash; returning does not count
    against you. Thank you for your time.</p></div>`,
};
