# Study design: heights film (example study)

The design of the study that `studies/heights-film/study.yaml` configures (tag `v1.0-heights-film` is the code
used to collect its data). Settings named below are in that study file.

## Goal
Continuous, time-locked self-report of affect while watching `towerClimb.mp4` (808.9 s, H.264, 25 fps,
played **muted** as in the fMRI session). Group-level rating time series become fMRI regressors (and control
regressors) and describe the psychological dynamics of the film. Temporal fidelity and between-rater
consensus are the priorities.

## Two studies, one per participant
| | Study 1 (`dim=anxiety`) | Study 2 (`dim=affect2d`) |
|---|---|---|
| Rating | "How tense or anxious do you feel right now?" 0 "Not at all" – 100 "Extremely". Includes anxiety for the people on screen. | 2D affect grid. x: unpleasant – pleasant (neutral at centre). y: low – high activation ("feeling activated or stirred up, regardless of whether the feeling is pleasant or unpleasant"). |
| Feedback overlay | Small translucent vertical bar (thermometer fill), lower-right of the frame | Small translucent square (22% of frame height, max 170 px) with a dot, lower-right |

The Study 2 Prolific study blocks Study 1 participants (`previous_studies_blocklist`).

## Input: mouse "joystick"
The pointer is locked and hidden (Pointer Lock API). Mouse movement moves the rating (position control),
clamped to 0–100, holding when the hand rests; no clicking. Full scale = 60% of screen height of mouse
travel. Arrow keys also work. Esc releases the lock and pauses the film. The first movement event after each
(re)lock is ignored (browsers can report a spurious jump there). A drag-slider mode exists for 1D
(`?input=slider`) but is not used.

Usability caveat: favourable usability results for continuous affect rating in the literature come from a VR
touchpad implementation (AffectTracker), not a browser mouse interface, so usability and interference are
measured here (post-film questions below) and should be checked in the pilot.

## Timeline
1. **Information + consent** (study file, `texts`). Seven statements must be ticked, including not using AI.
   Prominent "Please do not use AI" notice. Decline → no-consent code.
2. **Device check**: desktop, window ≥ 1000×600. Deliberately strict (decided 2026-10-04 after a pilot
   Chromebook with a 533 px-high window was excluded): small screens are not wanted.
3. **Pre-film questions**: fear of heights in everyday life (7-pt); **attention check 1**.
4. **Fullscreen** (required throughout the film).
5. **Instructions** (study-specific; Study 1 notes it includes anxiety for the people on screen; Study 2
   explains valence, neutral centre, and activation).
6. **Tracking practice** (40 s): follow an orange target with the bar/dot. Step changes and ramps (allow
   per-participant response-lag estimation). Repeated once if error > 15 (1D mean absolute error) or > 20
   (2D mean Euclidean distance), 0–100 units.
7. **Study 2 only – placement practice**: intro, then 6 scenarios in random order; place the dot, Space,
   feedback with the expected quadrant highlighted. Two unpleasant/high-activation items (nervous, **angry** –
   so upper-left is not taught as "anxiety"), two unpleasant/low-activation (sad/drained, bored), one
   pleasant/high, one pleasant/low.
8. **Pre-STICSA**: "Current feelings" – see below.
9. **Film**: set a baseline, press Space, rate continuously until the end. Muted. No seeking. Leaving
   fullscreen, switching tab, or releasing the mouse pauses the film until "Continue".
10. **Post-STICSA** immediately after playback, before any other question.
11. **Post-film questionnaire** (same for both studies):
   - overall tense/anxious; concern for the safety of the people in the film; strength of bodily sensations (7-pt)
   - bodily sensations checklist (palms, feet/legs, heart, stomach, muscle tension, breathing, dizziness, none)
   - rating-task interference: how distracting; how difficult (7-pt); **attention check 2**
   - seen the film before; watched without doing anything else; mouse vs trackpad
12. **Video response** (required, ≥ 100 words, live counter):
    "Please describe what you saw in the video and how it made you feel. You may describe particular moments,
    thoughts, or physical sensations, including if you felt little or no emotional response. Please write at
    least 100 words."
13. **Study feedback** (optional): "Do you have any comments or feedback about the study, the rating task, or
    any technical difficulties you experienced?"
14. **Debrief**, then redirect to Prolific with the completion code.

## STICSA somatic subscale (pre and post)
All 11 somatic items of the STICSA state form (Ree, French, MacLeod & Locke, 2008), original item numbers,
wording and order: 1 My heart beats fast. 2 My muscles are tense. 6 I feel dizzy. 7 My muscles feel weak.
8 I feel trembly and shaky. 12 My face feels hot. 14 My arms and legs feel stiff. 15 My throat feels dry.
18 My breathing is fast and shallow. 20 I have butterflies in the stomach. 21 My palms feel clammy.

- **Verification:** wording checked against the published state form reproduced in Roberts (2013, York University
  PhD dissertation, Appendix B; [YorkSpace](https://yorkspace.library.yorku.ca/server/api/core/bitstreams/2cfbcc6f-7a73-4135-9de6-565e6519eadc/content)),
  which matches the supplied psytests.org form for all 11 somatic items; somatic membership 1, 2, 6, 7, 8, 12, 14,
  15, 18, 20, 21 also per [Frontiers in Psychology 2021, 12:644889, Table 2](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2021.644889/full)
  and the dissertation's model figures. The original publication (Behav Cogn Psychother 36:313–332) is paywalled
  and was not read directly.
- **Presentation:** title "Current feelings"; instruction "Please indicate how you feel right now, at this
  moment." (the original reads "...right now, at this very moment"); options 1 Not at all, 2 A little,
  3 Moderately, 4 Very much so; one table, identical at both time points; nothing preselected; all items required;
  previous answers/scores never shown. Both administrations ask about current sensations.
- **Placement:** pre after instructions and practice, right before the film; post immediately after playback.
  A reload before the film re-shows a missing pre-STICSA; a reload after the film shows the post-STICSA first.
- **Scoring:** raw 1–4 per item with original item number and `timepoint` (pre/post), onset and completion
  timestamps; total = sum of the 11 items (11–44) only when all 11 are answered, otherwise null (missing is never
  0); change = post − pre when both totals exist.

## Why these post-film items
Negative valence + high arousal should not be read as anxiety by default: it can reflect concern for the
climbers, disgust, anger, or excitement mixed with discomfort. Overall anxiety, concern for safety, and bodily
sensations help interpret the trajectories; the free-text response gives qualitative context.

## Attention checks (Prolific policy)
Two instructed-response items ("please select *Strongly disagree*" / "*Extremely*"), instruction on the same
page, no memory or time limit. Prolific allows rejection only if **both** are failed (study > 5 min). One is
early (pre-film), one post-film. Engagement measures from the rating data (interruptions, flat-lining,
practice error) are for **data exclusion**, not rejection.

## AI protections
Deterrence plus logging; none of it is proof on its own.
- Consent screen notice + consent statement: do not use AI or automated tools (bots, scripts, auto-clickers,
  browser agents); with clear evidence, answers are not used and the submission may be rejected. The task is
  off-platform, so Prolific's authenticity checks (Qualtrics / AI Task Builder only) do not apply; the evidence is ours.
- Mouse: raw per-event movement is stored (teleport-like jumps visible); script-generated input events
  (`isTrusted == false`) are counted.
- Paste, drop, drag, copy and cut are blocked everywhere (and `beforeinput` paste/drop insertions);
  question text is not selectable. Attempts are counted.
- Window blur (alt-tab), page hidden (tab switch) and total time away are logged for the whole session, with
  the task that was on screen.
- Free text: keystroke count vs characters (text inserted without typing shows few keystrokes), time away
  while writing.

## Reloads
Progress is stored in JATOS study session data. A reload after the practice resumes the film 5 s before the
last saved position (logged as a separate `film_resume_<n>` trial; the meta line records `n_loads` and
`resumed_film_from`). After the film, a reload goes to the questions. Study assignment is fixed across reloads.

## Film delivery (from the main run on)
- **Encoding:** `media/towerClimb_crf29.mp4` (`scripts/encode_film.sh media/towerClimb.mp4 media/towerClimb_crf29.mp4`): same 1280×720, 25 fps, all 20,222 frames
  with original timestamps, audio removed (played muted), H.264 CRF 29. 147 MB instead of 288 MB; SSIM 0.979 vs
  the original; fine detail very slightly softer (see `docs/img/encoding_comparison.png`).
- **Pre-download:** after consent + device check the whole file is fetched in the background and played from
  memory, so playback cannot buffer (one pilot participant had 52 s of stalls while streaming). If it is not ready
  before the pre-film STICSA, a progress page waits for it; after 5 min of waiting, or on a download error, the study
  ends and the participant is asked to return it (completion code `VMPSLOWD`, no penalty). (Settings
  `film.preload_max_wait_minutes` and `film.return_on_slow_download`; with the latter off, the film streams instead.)
  Logged: `preload` lines (duration, MB/s), `download_gate` wait, `video_source` (download/stream) on the film trial.

## Main run (decided 2026-10-04)
Study 2 (valence × arousal) only, N = 60 in three cohorts of 20, each a separate Prolific study with a **50/50 sex
quota** (Prolific Sex screener; balanced so the mean can later be re-weighted, e.g. to the fMRI sample's ~2/3
women), blocking both pilot studies and earlier cohorts. Each cohort is reviewed (qc/review.py) before the next
opens. £4.80 / 30 min estimate (pilot median 24.3 min overall, 24.3–28.6 min for the 2D task).

## Payment and cost
£4.80 for ~30 min (£9.60/h; Prolific recommended £9.00/h, minimum £6.00/h). Prolific academic fee 33.3%.
50 completions per study ≈ £320; budget ~15% extra for exclusions. Revisit the time estimate after the pilot.

## Open points
- Resolved 2026-10-04: the film shows several people, so items refer to "the people in the film" / "the people on screen".
- Resolved: the information sheet states that basic demographic information is received from the Prolific profile
  (age, sex, first language, countries, student and employment status), so Prolific's demographic export can be used.
