# Data format

Each JATOS study result holds **newline-delimited JSON** (one object per line), appended as the session runs.
Locally (no JATOS) the same lines are downloaded as `vmp_local_<ms>.ndjson` at the end.
`qc/qc_lib.py` (`load_session`) reads this format; field names below are as saved by `task/js/experiment.js`
(unchanged since `v1.0-heights-film`). Examples refer to the heights study (`studies/heights-film`).

| `type` | When | Contents |
|---|---|---|
| `meta` | each page load | IDs (`prolific_pid`, `prolific_study_id`, `prolific_session_id`, `jatos_study_result_id`), `dimension` (a rating dimension of the study file, e.g. `anxiety`/`affect2d`), `study` (its `study` number), `dimension_assigned_by` (`url`/`random`), `input_mode`, `user_agent`, `screen`, `config_version`, `n_loads`, `resumed_film_from`, `skipped_to_questions` |
| `preload` | film download in the background | `e`: `start` (`url`), `done` (`ms`, `bytes`, `mbps`), `failed` (`error`, `bytes`), `gave_up` (`waited_ms`, `bytes`, `total`, `failed`) |
| `chunk` | every 30 s (`rating.chunk_seconds`) during practice and film, and at the end of each | `tag`, `chunk` index, and the new `samples`, `inputs`, `events` since the last chunk, **as rows** (see below) – a crash backup |
| `trial` | as each non-rating trial finishes | `trial`: that trial's data (consent, questionnaires, scales, texts…) – survives reloads |
| `final` | end of session (also on exclusion / no consent) | `summary`, `integrity`, `data` (all jsPsych trials of this page load). On exclusion: `excluded` (`true`, or `"slow_download"` together with a `summary`) |

A reloaded session has several `meta` lines and, for the film, trials tagged `film` and `film_resume_<n>`.

Fetch results: `python qc/review.py --study studies/<name>`, the JATOS GUI, or `POST /jatos/api/v1/results/data`
(see `qc/review.py` for auth).

## Rating trials (`task` = `practice` or `film`)
The same rating data come in two shapes:
- in `chunk` lines, as **rows**: film `samples` rows are `[t_stim, t_frame, t_wall, value(s)…, playing]`, practice
  rows `[t_stim, t_wall, value(s)…, playing, target(s)…]`; `inputs` rows are `[t_stim, t_wall, value(s)…, src, dx, dy]`;
- in the trial data of the `final` line, **column-wise**: `samples` and `inputs` are objects whose keys are the
  column names below, each a list of equal length.

The film rating data are rebuilt from the chunks, which survive reloads (`load_session` does this).

### `samples` (20 Hz timer)
| column | meaning |
|---|---|
| `t_stim` | stimulus clock (s): `video.currentTime` for the film; for practice, a clock that only runs while unpaused |
| `t_frame` | film only: media time (s) of the last frame actually presented (`requestVideoFrameCallback`); null if unsupported |
| `t_wall` | ms since the trial started (performance clock) |
| `value` | one-scale dimension (e.g. `anxiety`): rating 0–100 |
| `value_x`, `value_y` | 2D dimension (e.g. `affect2d`): x (valence) 0–100 (50 = neutral), y (arousal) 0–100 |
| `playing` | 1 if the stimulus was advancing (film: not paused, not ended, not stalled) |
| `target` / `target_x`, `target_y` | practice only: target position |

Use `t_stim` (or `t_frame`) for alignment to the film/fMRI; drop rows with `playing == 0` or treat them as gaps.

### `inputs` (every input event – the raw, unsmoothed trajectory)
| column | meaning |
|---|---|
| `t_stim`, `t_wall` | as above |
| `value` or `value_x`, `value_y` | value(s) after the event (clamped 0–100) |
| `src` | `m` mouse, `k` key, `s` slider |
| `dx`, `dy` | raw mouse movement in px (unclamped; `movementX/Y`, screen y down), 0 for keys |

### `events`
`{e, t_stim, t_wall, ...}` with `e` in: `can_play` (with `duration`), `arming`, `start` (with `initial_value`),
`playing`, `pause`, `stall` / `stall_end` (buffering), `interrupt` (with `reason`: `hidden`, `fs_exit`,
`pointer_unlock`, `play_rejected`), `resume`, `hidden`/`visible`, `blur`/`focus`, `fs_enter`/`fs_exit`,
`lock`/`unlock`, `seek_blocked`, `video_error`, `ended`, `end`.

### Per-trial scalars
`tag`, `mode` (video/practice), `input_mode`, `axes`, `joystick_px_full_scale`, `start_time`,
`initial_value`, `stimulus_duration`, `n_interruptions`, `interrupted_ms`, `n_stalls`, `stalled_ms`,
`wall_duration_ms`, `n_untrusted_events` (script-generated input events), `max_mouse_step_px` (largest raw mouse
movement in one event), `practice_mae` (practice: 1D mean absolute error or 2D mean Euclidean distance,
excluding 1.5 s after the start and after each step change), `practice_run`, `practice_passed`.
Film only: `resumed` (true after a reload), `video_source` (`download` or `stream`).

## Other trials (by `task`)
| task | fields |
|---|---|
| `consent` | `consent` (bool), `consent_statements` |
| `browser_check` | jsPsych browser-check fields (browser, mobile, width, height, …) |
| `download_gate` | `wait_ms`, `gave_up` (only shown when the film was not yet downloaded) |
| `fullscreen`, `instructions`, `resume_notice`, `quadrant_intro`, `end` | standard jsPsych fields |
| `quadrant_practice` (2D only) | `scenario`, `expected_valence`, `expected_arousal`, `x`, `y`, `correct`, `rt`, `trajectory` [[ms, x, y], …] |

### Questionnaire pages (from the study file)
Every questionnaire page is saved with `task` = the page `name`, and its answers in `response` (keyed by
question `name`), as the jsPsych survey plugins save them:
- **likert**: answers are 0-based indices (0 = leftmost label).
- **multi_choice**: the chosen option text; **multi_select**: a list of the ticked options; **text**: the typed text.
- A **likert page with an attention check** (a question with `correct`) is saved with `task` = `attention`,
  `page` = the page name, the answers also in a field named after the page, plus `n_checks`, `n_failed` and
  `attention` ({check name: passed}).
- **free_text**: `text`, `n_words`, `n_chars`, `n_keys` (keystrokes), `input_types` (counts of browser input
  types: typing, dictation/IME, …), `away_ms` (time unfocused while writing).
- **scale** (rating table, e.g. STICSA): `task` = the scale name, `timepoint` (e.g. `pre`/`post`), `items`
  [{`item` (the item number from the study file), `text`, `response` (option value or null)}], `n_answered`,
  `total` (null unless every item is answered), `onset`, `completion` (ISO timestamps), `duration_ms`;
  a `post` page also has `pre_total` and `change` (post − pre, or null); raw form values in `response`
  (`<scale>_<item>`).

Heights study (`studies/heights-film`): `attention` with `page` `pre_film` (field `pre_film`: `height_fear` 0–6 and
`attention_1`) and with `page` `usability` (field `usability`: `distracting`, `difficult` 0–6 and `attention_2`);
`post_feelings` (`anxiety_overall`, `concern_safety`, `body_intensity`, 0–6); `post_body` (`body_sensations`);
`post_mc` (`seen_before`, `full_attention`, `input_device`); `sticsa` pre and post (11 items, values 1–4,
total 11–44); `final_text`; `feedback` (`response.feedback`).

## `summary` (in the `final` line)
`attention_checks_failed` / `_total`, `practice_mae_last`, `quadrant_correct` / `_total`,
`film_interruptions`, `film_stalled_ms`, `film_untrusted_events`, `film_max_mouse_step_px`,
for each scale `<scale>_<timepoint>_total` and, with pre and post, `<scale>_change` (heights study:
`sticsa_pre_total`, `sticsa_post_total`, `sticsa_change`), `preload_ms`, `preload_mbps`, `preload_failed`,
`gate_wait_ms`, `video_source`, `final_text_words`, `final_text_keystrokes`, `final_text_away_ms` (from the
first free_text page), `paste_blocked`, `drop_blocked`, `copy_blocked`, `n_window_blur`, `n_page_hidden`,
`away_ms_total`.

## `integrity` (in the `final` line)
Counters (`paste_blocked`, `drop_blocked`, `copy_blocked`, `n_hidden`, `n_blur`, `away_ms`) plus
`events`: `{e, t (s since page load), task}` for every blur/focus, hidden/visible, and blocked paste/drop/copy
across the whole session (capped at 2000).
