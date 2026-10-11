# qc/ – data-quality checks

Quick, practical checks for incoming data: is each session complete, attentive, and human? Analysis
(time-series plotting, group means, fMRI regressors, summaries) belongs in a separate analysis repository;
`qc_lib.load_session` plus [docs/data.md](../docs/data.md) document how to read the raw format there.

```bash
python qc/review.py --study studies/heights-film              # fetch JATOS results + Prolific submissions into data/raw/, then review
python qc/review.py --study studies/heights-film --no-fetch   # re-review what is already downloaded
python qc/engagement.py --study studies/heights-film          # 2D ratings: were people watching? (after review.py)
python -m pytest tests                                        # known-answer tests of the QC code
```
Outputs (gitignored, contain Prolific IDs): `qc/out/qc_report.csv`, `qc/out/texts.md`,
`qc/out/plots/<pid>_<study>_*.png` (rating trajectory with interruptions/stalls, raw mouse step sizes on a log
scale with the teleport line, input density), `qc/out/overview_<dimension>.png` (all trajectories + mean, sanity
only), `qc/out/engagement.csv`.

Study-specific settings come from the study file (`studies/<name>/study.yaml`, section `qc`): the advisory
thresholds (`qc.thresholds`), answers that need a look (`qc.review_answers`), preregistered hard exclusions
(`qc.hard_exclusions`, applied by `qc_lib.prereg_hard_exclusion`), engagement settings (`qc.engagement`) and,
optionally, which Prolific studies form the exploratory sample (`qc.exploratory_studies`; `engagement.py` uses
it by default, `--confirmatory` / `--all` to change). `study_config.py` reads and checks the study file.

## Verdicts (advisory – you decide)
Numbers below are the heights study's thresholds.

**REJECT-ELIGIBLE** – objective evidence the participant broke the study terms (Prolific requires clear evidence;
the task is off-platform, so the evidence is ours – keep the plot/report row when rejecting):
- failed both attention checks
- script-generated input events during the film (`isTrusted == false`)
- free text not typed – far fewer keystrokes than characters (< 0.2 per character, texts of ≥ 200 characters) –
  **and** blocked paste/drop attempts or > 10 s in another window while writing. Without those, the same pattern is
  only REVIEW ("possibly dictation": voice input or an IME also gives few keystrokes for the participant's own words)

**REVIEW** – look at the plot / text before deciding; usually exclusion (pay) rather than rejection:
- automation patterns: repeated isolated mouse jumps > 250 px ("teleporting"); long runs of identical mouse steps
  (constant-velocity scripting); no off-axis jitter (perfectly vertical moves – human hands always wobble);
  erratic input (> 10% of mouse steps > 250 px; likely exclusion, not evidence of misconduct)
- text: implausibly fast typing, LLM-style phrasing markers, near-duplicate of another participant, copy or paste
  attempts
- engagement: one failed attention check, film coverage < 95%, many/long interruptions, buffering, long stretch
  with no rating input, lots of time away from the window, poor practice/quadrant performance, seen the film before,
  self-reported inattention, page reloads, incomplete session

LLM phrasing markers are in `qc_lib.AI_MARKERS` (a hit is a reason to read, not proof).
Note: browser-automation tools that drive a real browser produce "trusted" events; judge those by the movement
patterns in the plot (straight lines, identical steps, jumps, ratings that never react to the film).
