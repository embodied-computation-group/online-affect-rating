# online-affect-rating

A browser-based platform for **continuous, time-locked affect ratings while people watch a video**, run online
(jsPsych 8 on a JATOS server, recruited through Prolific). Participants move a dot within a small affect grid
(valence x arousal) or a 1D bar overlaid on the video; the position is sampled at 20 Hz against film time.

The platform was developed for a validation study of a first-person heights film (see
[heights-film-paper](https://github.com/embodied-computation-group/heights-film-paper) and the preregistration
[osf.io/s2yvb](https://osf.io/s2yvb)). That study is the worked example in this repository
([`studies/heights-film`](studies/heights-film)); tag `v1.0-heights-film` is the exact code used to collect its data.

| 1D bar (`?dim=anxiety`) | 2D affect grid (`?dim=affect2d`) |
|---|---|
| ![Film with the anxiety bar overlay](docs/img/study1_anxiety.png) | ![Film with the affect-grid overlay](docs/img/study2_affect2d.png) |

## What it does

- **Continuous rating** during the video: the mouse pointer is hidden and locked, so moving the mouse moves the
  bar or dot without clicking. Ratings are stored with the presented video frame time; leaving full screen or
  switching tabs pauses the video. Sessions resume after a page reload.
- **Practice** (target tracking; for the grid, placing example states) and **attention checks**.
- **Questionnaires** before and after the video, defined as lists in the study file (Likert, multiple choice,
  multi-select, text, a free-text description with typing statistics, rating tables such as the STICSA somatic
  subscale used in the example).
- **Data quality checks** (`qc/`): per-session coverage, interruptions, rating bouts, and flags for scripted or
  automated input (mouse "teleporting", identical steps, untyped text).
- **Deployment helpers**: upload the task to JATOS and create Prolific draft studies from the command line.

## One study file

Everything specific to a study is in one human-editable file, `studies/<name>/study.yaml`: the film, the rating
dimensions, the participant information, consent and debrief texts, the questionnaires, the Prolific listing and
completion codes, the JATOS study and the QC thresholds. The task in the browser, the deploy scripts and the QC
scripts all read that file. Start from the commented example [`studies/heights-film/study.yaml`](studies/heights-film/study.yaml)
and check your edits with `python scripts/check_study.py --study studies/<name>`.

**To run your own film or study, follow the [tutorial](docs/tutorial.md).**

## Layout

| folder | contents |
|---|---|
| `studies/` | one folder per study with its `study.yaml`; `heights-film/` is the example (plus its [design notes](studies/heights-film/design.md)) |
| `task/` | the jsPsych task: `js/study.js` (reads the study file), `js/questionnaires.js` (builds the questionnaire pages), `js/experiment.js` (the session flow), `js/texts.js` (platform messages and the 2D practice), and the two rating plugins |
| `scripts/` | check a study file, local server, JATOS deployment, Prolific draft studies, video encoding |
| `qc/` | read the study file (`study_config.py`), download results (`review.py`), read raw files and compute QC measures (`qc_lib.py`), engagement check |
| `tests/` | pytest known-answer tests (`python -m pytest tests`); end-to-end run-through in headless Chrome (`e2e_local.py`) |
| `docs/` | [tutorial](docs/tutorial.md), [raw data format](docs/data.md), [operations](docs/operations.md) |

## Quick start (local)

```bash
python -m pip install -r requirements.txt
scripts/serve_local.sh      # serves the repository on http://localhost:8000 (needs Node.js)
```

Put the film in `media/` (not included; the path is `film.local_file` in the study file) and open
`http://localhost:8000/task/index.html?study=heights-film&dim=affect2d&reset=1`. Automated run-through:
`python tests/e2e_local.py --dim affect2d` (needs Playwright and Chrome). See [docs/operations.md](docs/operations.md)
for deployment to JATOS and Prolific; secrets go in a git-ignored `secrets.env` (template: `secrets.env.example`).

## Licence

Code: MIT (see `LICENSE`). The example film is a third-party video and is not included.
