# Run your own film study

This guide takes you from a film file to checked data, step by step. You edit one file – the study file – and
run a few commands. The heights study in `studies/heights-film/` is the worked example; copy it and change it.

Commands are typed in a terminal, in the repository folder. On Windows, use Git Bash (it comes with Git) so the
`scripts/*.sh` commands work.

## What you need

- **Python 3.10 or newer**, **Git**, **Node.js** (for the local test server) and **Google Chrome**.
- **A JATOS server** where you can create studies, with an API token. Many labs use
  [MindProbe](https://mindprobe.eu) (free JATOS hosting for research).
- **A Prolific researcher account** with an API token, and the [Prolific command-line tool](https://docs.prolific.com)
  (`prolific`) installed (or placed in `bin/`).
- **ffmpeg** to prepare the film (or `python -m pip install imageio-ffmpeg`, which includes one).
- **The film**, which you are allowed to show online. Films are not stored in git.

## 1. Get the code and install the Python packages

```bash
git clone https://github.com/embodied-computation-group/online-affect-rating.git
cd online-affect-rating
python -m pip install -r requirements.txt
python -m pytest tests          # everything should pass
```

## 2. Make your study folder

```bash
cp -r studies/heights-film studies/my-film
```

Open `studies/my-film/study.yaml` in a text editor. Every setting has a comment. Go through it from top to bottom:

| section | what to change |
|---|---|
| `test_mode` | keep `false` |
| `about` | study title, institution, your name and e-mail, data controller, duration, payment |
| `film` | file names and length (step 3) |
| `rating` | the rating dimensions (one scale with `axes: 1`, or the 2D grid with `axes: 2`), which can be assigned, and their questions and labels |
| `practice` | usually keep as is |
| `texts` | the information sheet, consent statements and debrief. These are for your ethics review: rewrite them for your study and institution |
| `scales`, `questionnaires` | your questionnaires (see below) |
| `prolific` | listing (name, description, reward, time), completion codes (make up your own, e.g. `ABCDONE1`), filters, project; delete the heights `studies` list (you add your own Prolific study ids later) |
| `jatos` | your JATOS study id (step 5) |
| `qc` | thresholds for the advisory checks. `hard_exclusions` are the heights study's preregistered rules: replace them with your own preregistered rules, or delete the section if you have none. Delete `exploratory_studies` unless you split your sample that way |

Then check the file. It tells you in plain words what is missing or wrong:

```bash
python scripts/check_study.py --study studies/my-film
```

**YAML tips.** Indent with spaces, never tabs. Put text in "double quotes" if it contains `: ` or `#`, or if it is
a word like Yes, No, On, Off (unquoted, they are read as true/false – the checker warns you). Long texts go after
`|` on indented lines. In texts, `{pi_name}`, `{film_length}` and the other names from `about` are filled in for you.

### Questionnaires

Pages are listed at four places in the session:
`intro` (after consent and the device check), `before_film` (right before the film), `after_film` (right after
the film, still full screen) and `end` (then the debrief). A page looks like this:

```yaml
questionnaires:
  end:
    - type: likert
      name: post_feelings            # saved as task "post_feelings"
      preamble: "<h3>How you felt during the film</h3>"
      questions:
        - name: anxiety_overall      # the answer is saved under this name
          prompt: Overall, how tense or anxious did you feel while watching the film?
          labels: [Not at all, "", "", "", "", "", Extremely]   # 7 points, labelled at the ends
        - name: attention_2          # an attention check: `correct` is the right option (0 = leftmost)
          prompt: This is an attention check. Please select <b>Extremely</b>.
          labels: [Not at all, "", "", "", "", "", Extremely]
          correct: 6
    - type: multi_choice
      name: post_mc
      questions:
        - name: seen_before
          prompt: Had you seen this film before?
          options: ["Yes", "No", "Not sure"]
```

Page types: `likert`, `multi_choice`, `multi_select`, `text` (short typed answers), `free_text` (a longer
description with a minimum word count; typing is counted for quality control), `scale` (a rating table defined
under `scales`, e.g. a validated questionnaire given before and after the film with `timepoint: pre` / `post`)
and `html_form` (your own HTML form). All questions are required unless they say `required: false`.
The heights study file shows each type. How answers are saved: [data.md](data.md).

## 3. Prepare the film

Put the original film in `media/` and make a web copy (same frames and timing, no sound, smaller file):

```bash
scripts/encode_film.sh media/my-film.mp4 media/my-film_web.mp4
```

(If ffmpeg is not on your path: `FFMPEG=<path to ffmpeg> scripts/encode_film.sh ...`.) The script prints the
frame count, duration and similarity to the original. In the study file set:

```yaml
film:
  file: my-film_web.mp4              # its name on JATOS
  local_file: media/my-film_web.mp4  # for local runs
  duration_s: 754.2                  # the printed duration in seconds
  length_text: about 12½ minutes
```

## 4. Try it on your own computer

```bash
scripts/serve_local.sh
```

Open `http://localhost:8000/task/index.html?study=my-film&dim=<your dimension>&reset=1` in Chrome and go through
the whole session. At the end the data are downloaded as a file (`vmp_local_<number>.ndjson`); look at them, or
check them with `python qc/review.py --study studies/my-film --raw <folder with the file> --no-fetch`.

Shortcuts for testing (they only work locally or in test mode): add `&start_time=780` to start the film near its
end, `&skip=intro` to jump straight to the film. `reset=1` starts a fresh session.

## 5. Put it on JATOS

1. In JATOS, create a new, empty study. Note its id (the number in the study's address, or its UUID) and put it
   in the study file under `jatos: study_id:`.
2. Copy `secrets.env.example` to `secrets.env` and fill in `JATOS_URL` and `JATOS_TOKEN` (JATOS: your name →
   My API tokens). `secrets.env` is never committed.
3. Upload:
   ```bash
   python scripts/deploy_jatos.py --study studies/my-film --check   # can we reach the study?
   python scripts/deploy_jatos.py --study studies/my-film --video   # task, study file and film
   python scripts/deploy_jatos.py --study studies/my-film --link    # the link Prolific will use
   ```
   After changing only the study file or the task, run it again without `--video`.
4. Test the real thing: open the link in `prolific/jatos_link.txt` with
   `?PROLIFIC_PID=TEST&STUDY_ID=TEST&SESSION_ID=TEST&dim=<dimension>` added. To skip most of the film, switch test
   mode on in JATOS (study properties → Study input: `{"testMode": true}`) and add `&start_time=780`.
   Afterwards **switch test mode off again** and delete the test results in JATOS.

## 6. Set up Prolific

1. Put `PROLIFIC_TOKEN` in `secrets.env`, and your project id in the study file (`prolific: project:`).
2. Make a draft study (nothing is published):
   ```bash
   python scripts/create_prolific_study.py --study studies/my-film --dim <dimension> --places 5 --tag pilot --dry-run
   python scripts/create_prolific_study.py --study studies/my-film --dim <dimension> --places 5 --tag pilot
   ```
   The first command only writes `prolific/generated/pilot_<dimension>.json` so you can read it. Options:
   `--block <Prolific study id>` keeps participants of another study out, `--quota-sex` balances the sample 50/50.
3. Preview the draft in the Prolific web interface and publish it there.
4. Add the new Prolific study id to the study file under `prolific: studies:` (e.g. `pilot: <id>`), so the QC
   script downloads its submissions.

## 7. Download the data and check quality

```bash
python qc/review.py --study studies/my-film
```

This downloads every JATOS result into `data/raw/` and the Prolific submissions, and writes `qc/out/qc_report.csv`
(one row per session, with a verdict: OK, REVIEW or REJECT-ELIGIBLE and the reasons), `qc/out/texts.md` (all
written answers) and a plot per session in `qc/out/plots/`. These files contain Prolific IDs and stay out of git.
Verdicts are advice: look at the plot and text, then approve, reject (only with clear evidence) or exclude in
Prolific. What the verdicts mean: [qc/README.md](../qc/README.md). For 2D ratings,
`python qc/engagement.py --study studies/my-film` adds a check of whether people were actually watching.

## 8. Keep a record

Commit your study folder (`git add studies/my-film`) and tag the version you collect data with (e.g.
`git tag v1.0-my-film`), so you can always say exactly which code and settings were used.
