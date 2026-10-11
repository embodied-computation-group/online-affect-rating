# Operations

Reference for running a study. For a first study, follow the step-by-step [tutorial](tutorial.md).
Every script takes the study folder: `--study studies/<name>` (examples below use the heights study).

## Secrets
`secrets.env` (gitignored; template `secrets.env.example`): `PROLIFIC_TOKEN`, `JATOS_URL`
(e.g. `https://jatos.mindprobe.eu`), `JATOS_TOKEN` (JATOS → your name → My API tokens). The JATOS study itself is
`jatos.study_id` in the study file (UUID or numeric id; `JATOS_STUDY_ID` in `secrets.env` is only a fallback).

## Checking the study file
```bash
python scripts/check_study.py --study studies/heights-film
```
Lists mistakes in plain words, or prints an overview of the session.

## Local testing
```bash
scripts/serve_local.sh        # serves the repo root on :8000 (range requests for the video)
```
Open `http://localhost:8000/task/index.html?study=heights-film&dim=anxiety&reset=1` (or `dim=affect2d`).
`study` names the folder in `studies/`; the film must be at `film.local_file` (e.g. `media/…`, not in git).

URL parameters:
- Everywhere: `dim=<dimension>` (which rating; Prolific links set it), `input=slider` (1D only).
- Locally only: `study=<folder>`, `reset=1` clears the saved session, `skip=intro` jumps to the film.
- Testing only: `start_time=<s>` starts the film late, `max_wait_s=<s>` shortens the wait for the film download,
  `video=<url>` plays another film. These work locally, and on JATOS **only in test mode** (`test_mode: true` in
  the study file, or JATOS study properties → Study input `{"testMode": true}`), so participants cannot use them.
  Switch test mode off before real participants take part (`deploy_jatos.py` warns when it is on).

Automated run-through (headless Chrome, Playwright; film starts at 795 s so a run takes ~2 min; the answers
follow the heights study's questionnaires):
```bash
python tests/e2e_local.py --dim anxiety
python tests/e2e_local.py --dim affect2d
python tests/e2e_local.py --dim anxiety --reload          # reload mid-film, check resume
python tests/e2e_local.py --dim anxiety --live --base "$(cat prolific/jatos_link.txt)"   # against JATOS
```
`--live` needs test mode on JATOS for `start_time` (otherwise the whole film plays) and leaves a test result
(`PROLIFIC_PID=TESTPID`) in JATOS – delete it, and switch test mode off, before launch.

Unit tests: `python -m pytest tests` (QC known-answer tests, study-file checks, Prolific draft, and – with
node installed – the browser modules).

## Deploying to JATOS (tested with MindProbe, JATOS 3.11.3)
```bash
python scripts/deploy_jatos.py --study studies/heights-film --check   # token, study, components, assets
python scripts/deploy_jatos.py --study studies/heights-film           # upload task/ + study.yaml, create the component if missing
python scripts/deploy_jatos.py --study studies/heights-film --video   # also upload the film (film.local_file, as film.file)
python scripts/deploy_jatos.py --study studies/heights-film --link    # enable General Single links, write prolific/jatos_link.txt
```
Notes: the study file is checked first and uploaded as `study.yaml` next to `index.html`. The script resolves the
study UUID and does not keep cookies (JATOS ignores the Bearer token once a session cookie is sent). The component
is reloadable (needed for resume). Task settings can be overridden without redeploying via JATOS study properties →
Study input (JSON), with the setting names of `task/js/study.js` (`buildConfig`), e.g.
`{"videoUrl": "https://…/film.mp4"}` or `{"testMode": true}`.

## Prolific
Settings are in the study file's `prolific` section: `listing` (heights study: description, £4.80, 30 min, desktop
only), `completion_codes`, `filters` (fluent English, normal/corrected vision, approval ≥ 95%, ≥ 20 previous
submissions), `project`. The task redirects with the same completion codes, so they always match. Heights study:
`VMPDONE1` (completed → manual review), `VMPNOCON` (no consent → request return) and `VMPSLOWD` (film could not be
downloaded in time → request return, no penalty).

```bash
python scripts/create_prolific_study.py --study studies/heights-film --dim anxiety  --places 6 --tag pilot
python scripts/create_prolific_study.py --study studies/heights-film --dim affect2d --places 6 --tag pilot --block <study-1-id>
```
This only creates **drafts** (add `--dry-run` to only write `prolific/generated/<tag>_<dim>.json`). Preview in the
Prolific web UI, then publish there (or `scripts/prolific.sh study publish <id>`). Add Study 2 to Study 1's
blocklist in the web UI too, so the exclusion works in both directions. Avoid `prolific studies list` in scripts
(it did not return in testing). Add each new Prolific study id to `prolific.studies` in the study file so
`qc/review.py` downloads its submissions.

## Reviewing submissions
`python qc/review.py --study studies/heights-film` downloads results and writes the QC report (see
[qc/README.md](../qc/README.md)). Completed submissions arrive on Prolific as "awaiting review". Per session, the
`summary` in the `final` line has the key numbers.
- **Rejection** (Prolific policy: only with clear evidence that the participant broke the study's terms; the task is
  off-platform, so Prolific's own authenticity checks do not apply and the evidence must come from our data):
  - `attention_checks_failed == 2`, or
  - clear evidence of AI or automated tools, which the consent forbids: e.g. `film_untrusted_events > 0`
    (script-generated input), mouse "teleporting" in the raw trajectory (`inputs.dx/dy`, `film_max_mouse_step_px`,
    implausibly regular movement), or a free-text answer with few/no keystrokes for its length after blocked paste
    attempts or time in another window. Document the evidence when rejecting.
  - Merely suspicious data -> exclude (pay), don't reject.
- **Demographics:** `scripts/prolific.sh study demographic-export <study_id>` (Prolific profile data: age, sex,
  first language, countries, student/employment status; returned submissions show "CONSENT REVOKED").
- **Data exclusion** (still pay): many interruptions/long `away_ms_total`, `practice_mae_last` high after the
  repeat, long flat-lined rating stretches, `seen_before`, `final_text_keystrokes` far below the character count
  without paste attempts (possibly dictation – read the text), free text that reads as generated.
Approve/reject in the Prolific UI or with `scripts/prolific.sh submission …`.
