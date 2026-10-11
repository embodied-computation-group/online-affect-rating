"""Known-answer tests for the quality-control library (qc/qc_lib.py).

Every test uses small made-up data whose correct answer can be worked out by hand. Study settings
(film length, thresholds, questionnaire names) come from the heights example study file.
Run from the repository folder:  python -m pytest tests
"""
import copy
import json
import math

import numpy as np
import pandas as pd
import pytest

import qc_lib
from qc_lib import (add_duplicate_text_flags, ai_marker_hits, flags, load_session, prereg_hard_exclusion,
                    scope_filter, session_metrics)
from study_config import ROOT, load_study

STUDY = load_study(ROOT / "studies" / "heights-film")


# ----------------------------------------------------------------------------- helpers ---
def write_ndjson(path, lines):
    """Write a list of dicts as a newline-delimited JSON result file."""
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf8")
    return path


def run_flags(row):
    """The advisory flags for a report row, with the heights thresholds."""
    return flags(row, STUDY)


def metrics_of(session):
    """The QC measures of a session, with the heights study settings."""
    return session_metrics(session, STUDY)


def ok_row(**changes):
    """A qc_report row for a clean, completed session; `changes` overrides single fields."""
    row = {"completed": True, "coverage": 1.0, "study": "anxiety", "n_loads": 1, "att_failed": 0, "att_total": 2}
    row.update(changes)
    return row


# ------------------------------------------------------------------- small metric helpers ---
def test_longest_identical_run_counts_only_big_enough_steps():
    # steps: (0,-3) (0,-3) (0,-3) (0,-1) (0,-3) (1,-3); the 1-px step is below min_px and breaks the run
    dx = np.array([0, 0, 0, 0, 0, 1])
    dy = np.array([-3, -3, -3, -1, -3, -3])
    assert qc_lib._longest_identical_run(dx, dy, min_px=3) == 3


def test_coverage_is_share_of_whole_film_seconds_with_playing_samples():
    # playing samples every 0.5 s from 0 to 403.5 s -> 404 distinct seconds; the film has floor(808.9) = 808
    t = np.arange(0, 404, 0.5)
    samples = pd.DataFrame({"t_stim": t, "playing": 1})
    # samples that were not playing do not count
    paused = pd.DataFrame({"t_stim": np.arange(500, 600, 0.5), "playing": 0})
    assert qc_lib._coverage(pd.concat([samples, paused]), 808.9) == pytest.approx(404 / 808)
    # a 404.2-s film is fully covered by the same samples
    assert qc_lib._coverage(samples, 404.2) == 1.0


def test_interrupted_seconds_pairs_interrupt_with_resume_or_end():
    events = pd.DataFrame([
        {"segment": "film", "e": "interrupt", "t_wall": 1000},
        {"segment": "film", "e": "resume", "t_wall": 4000},        # 3 s
        {"segment": "film", "e": "interrupt", "t_wall": 10000},
        {"segment": "film", "e": "end", "t_wall": 12000},          # 2 s
        {"segment": "film_resume_2", "e": "interrupt", "t_wall": 0},  # never closed: not counted
    ])
    assert qc_lib._interrupted_s(events) == pytest.approx(5.0)


def test_stalled_seconds_pairs_stall_with_stall_end():
    events = pd.DataFrame([
        {"segment": "film", "e": "stall", "t_wall": 500},
        {"segment": "film", "e": "stall_end", "t_wall": 2500},     # 2 s
        {"segment": "film", "e": "stall", "t_wall": 3000},
        {"segment": "film", "e": "end", "t_wall": 3500},           # 0.5 s
    ])
    assert qc_lib._paired_s(events, "stall", ("stall_end", "end")) == pytest.approx(2.5)


def test_longest_no_input_includes_film_start_and_end():
    samples = pd.DataFrame({"t_stim": np.arange(0, 100.5, 0.5), "playing": 1})
    inputs = pd.DataFrame({"t_stim": [10.0, 70.0]})
    # gaps: 0-10, 10-70, 70-100 -> longest 60 s
    assert qc_lib._longest_no_input(inputs, samples) == pytest.approx(60.0)


def test_ai_markers_find_llm_phrases():
    hits = ai_marker_hits("Overall, the film was a testament to courage — truly palpable.")
    assert len(hits) == 4  # "overall,", "testament to", "palpable", the long dash
    assert ai_marker_hits("I felt sick when they looked down.") == []


def test_duplicate_text_flags_name_the_most_similar_participant():
    rows = [{"prolific_pid": "A", "text": "I felt very scared on the roof."},
            {"prolific_pid": "B", "text": "I felt very scared on the roof!"},
            {"prolific_pid": "C", "text": "Completely different words here about nothing."}]
    add_duplicate_text_flags(rows, STUDY)
    assert rows[0]["text_most_similar_to"] == "B"
    assert rows[1]["text_most_similar_to"] == "A"
    assert rows[2]["text_most_similar_to"] == ""


# --------------------------------------------------------------------------------- flags ---
def test_clean_session_is_ok():
    assert run_flags(ok_row()) == ("OK", [], [])


def test_both_attention_checks_failed_is_reject_eligible():
    verdict, rej, _ = run_flags(ok_row(att_failed=2))
    assert verdict == "REJECT-ELIGIBLE"
    assert rej == ["failed both attention checks"]


def test_one_attention_check_failed_is_review_only():
    verdict, rej, rev = run_flags(ok_row(att_failed=1))
    assert (verdict, rej, rev) == ("REVIEW", [], ["failed 1 attention check"])


def test_untyped_text_is_reject_eligible_only_with_paste_attempts_or_time_away():
    untyped = dict(text_chars=300, text_keys=30, text_keys_per_char=0.1)
    verdict, rej, rev = run_flags(ok_row(**untyped))  # possibly dictation
    assert verdict == "REVIEW" and rej == [] and "possibly dictation" in rev[0]
    verdict, rej, _ = run_flags(ok_row(**untyped, text_paste_drop_attempts=1))
    assert verdict == "REJECT-ELIGIBLE" and "after paste/drop attempts" in rej[0]


def test_practice_threshold_depends_on_the_number_of_rating_axes():
    # error 18 passes the 2D threshold (20) but not the 1D threshold (15)
    assert run_flags(ok_row(study="affect2d", practice_err_last=18, practice_runs=2))[0] == "OK"
    verdict, _, rev = run_flags(ok_row(study="anxiety", practice_err_last=18, practice_runs=2))
    assert verdict == "REVIEW" and rev == ["practice error 18 after 2 runs"]


def test_low_coverage_and_seen_before_are_review_reasons():
    _, _, rev = run_flags(ok_row(coverage=0.9, q_seen_before="Yes"))
    assert rev == ["film coverage 90%", "had seen the film"]


# -------------------------------------------------------------- preregistered exclusions ---
@pytest.mark.parametrize("changes, expected", [
    ({}, ""),
    ({"att_failed": 2}, "both attention checks failed"),
    ({"att_failed": 1}, ""),
    ({"untrusted_events": 1}, "script-generated input"),
    ({"text_chars": 200, "text_keys_per_char": 0.19}, "free text not typed"),
    ({"text_chars": 199, "text_keys_per_char": 0.19}, ""),     # too short to judge
    ({"frac_big_steps": 0.11}, "erratic input"),
    ({"frac_big_steps": 0.10}, ""),                            # rule is "more than 10%"
    ({"stalled_s": 31}, "disrupted viewing"),
    ({"interrupted_s": 61}, "disrupted viewing"),
    ({"coverage": 0.949}, "film coverage < 95%"),
    ({"q_seen_before": "Yes"}, "seen the film before"),
    ({"att_failed": 2, "coverage": 0.5}, "both attention checks failed; film coverage < 95%"),
])
def test_prereg_hard_exclusion(changes, expected):
    row = {"att_failed": 0, "untrusted_events": 0, "coverage": 1.0, "stalled_s": 0, "interrupted_s": 0}
    row.update(changes)
    assert prereg_hard_exclusion(row, STUDY) == expected


def test_prereg_hard_exclusion_treats_missing_values_as_zero():
    # a pandas row with NaN (e.g. no free text) must not crash or exclude on the NaN
    row = pd.Series({"att_failed": 0, "untrusted_events": np.nan, "text_keys_per_char": np.nan,
                     "text_chars": np.nan, "frac_big_steps": np.nan, "stalled_s": 0, "interrupted_s": 0,
                     "coverage": 1.0, "q_seen_before": "No"})
    assert prereg_hard_exclusion(row, STUDY) == ""


# -------------------------------------------------------------------------- load_session ---
def small_session_lines():
    """A tiny made-up 1D session: two film chunks, a practice chunk, questionnaires and a final line."""
    sticsa_pre = {"task": "sticsa", "timepoint": "pre", "total": 11, "trial_index": 8, "time_elapsed": 100,
                  "response": {}, "items": [{"item": n, "response": 1} for n in range(11)]}
    sticsa_post = {"task": "sticsa", "timepoint": "post", "total": 20, "trial_index": 10, "time_elapsed": 900,
                   "response": {}, "items": [{"item": n, "response": 1 + (n % 2)} for n in range(11)]}
    return [
        {"type": "meta", "prolific_pid": "P1", "dimension": "anxiety", "n_loads": 1, "prolific_study_id": "S1"},
        {"type": "chunk", "t": "2026-10-04T00:00", "tag": "practice_1", "chunk": 0,
         "samples": [[0, 0, 50, 1]], "inputs": [], "events": []},
        {"type": "chunk", "t": "2026-10-04T00:01", "tag": "film", "chunk": 0,
         # one old-style row without t_frame (4 values) and one new-style row (5 values)
         "samples": [[0.0, 0.0, 10.0, 1], [0.05, 0.04, 50.0, 12.0, 1]],
         "inputs": [[0.05, 50.0, 12.0, "m", 0, -4]],
         "events": [{"e": "start", "t_stim": 0, "t_wall": 0}]},
        {"type": "chunk", "t": "2026-10-04T00:02", "tag": "film", "chunk": 1,
         "samples": [[0.10, 0.08, 100.0, 15.0, 1]], "inputs": [], "events": []},
        {"type": "trial", "trial": {"task": "consent", "consent": True, "trial_index": 0, "time_elapsed": 1}},
        {"type": "trial", "trial": {"task": "attention", "page": "pre_film", "n_checks": 1, "n_failed": 0,
                                    "trial_index": 2, "time_elapsed": 5, "response": {"height_fear": 2}}},
        {"type": "trial", "trial": sticsa_pre},
        {"type": "trial", "trial": sticsa_post},
        {"type": "trial", "trial": {"task": "post_feelings", "trial_index": 12, "time_elapsed": 950,
                                    "response": {"anxiety_overall": 3, "concern_safety": 4}}},
        {"type": "trial", "trial": {"task": "attention", "page": "usability", "n_checks": 1, "n_failed": 1,
                                    "usability": {"distracting": 1, "attention_2": 5}, "trial_index": 14,
                                    "time_elapsed": 990, "response": {"distracting": 1, "attention_2": 5}}},
        {"type": "trial", "trial": {"task": "post_mc", "trial_index": 15, "time_elapsed": 1000,
                                    "response": {"seen_before": "No", "full_attention": "Yes"}}},
        {"type": "trial", "trial": {"task": "end", "trial_index": 19, "time_elapsed": 1100}},
        # the final line repeats the consent trial (must be de-duplicated) and holds the practice trial
        {"type": "final", "summary": {}, "integrity": {},
         "data": [{"task": "consent", "consent": True, "trial_index": 0, "time_elapsed": 1},
                  {"task": "practice", "practice_mae": 7.5, "samples": {"t_stim": [0]}, "trial_index": 6},
                  {"task": "film", "samples": {}}]},
    ]


def test_load_session_rebuilds_film_data_and_deduplicates_trials(tmp_path):
    s = load_session(write_ndjson(tmp_path / "s.ndjson", small_session_lines()), STUDY)
    assert s.pid == "P1" and s.dimension == "anxiety" and not s.is2d
    assert list(s.film_samples["t_stim"]) == [0.0, 0.05, 0.10]       # practice chunk ignored
    assert s.film_samples["t_frame"].isna().tolist() == [True, False, False]  # old row gets t_frame = None
    assert list(s.film_samples["value"]) == [10.0, 12.0, 15.0]
    assert len(s.film_inputs) == 1 and s.film_inputs["dy"].iloc[0] == -4
    assert [t["task"] for t in s.trials].count("consent") == 1          # duplicate removed
    assert s.practice == [{"task": "practice", "practice_mae": 7.5, "trial_index": 6}]  # samples dropped


def test_session_metrics_on_small_session(tmp_path):
    r = metrics_of(load_session(write_ndjson(tmp_path / "s.ndjson", small_session_lines()), STUDY))
    assert r["completed"] is True and r["consent"] is True
    assert (r["att_failed"], r["att_total"]) == (1, 2)
    assert r["practice_err_last"] == 7.5 and r["practice_runs"] == 1
    assert (r["sticsa_pre"], r["sticsa_post"], r["sticsa_change"]) == (11, 20, 9)
    assert r["sticsa_pre_straightline"] is True and r["sticsa_post_straightline"] is False
    # answers to the post-film pages appear as q_<question> columns
    assert r["q_anxiety_overall"] == 3 and r["q_distracting"] == 1 and r["q_seen_before"] == "No"
    assert "q_height_fear" not in r  # pre-film answers are not copied into the report (as in v1.0)
    assert r["n_inputs"] == 1 and r["max_step_px"] == 4


# ------------------------------------------------------ human-like vs scripted sessions ---
TEXT_HUMAN = ("I saw people climbing up a very tall building in a city with lots of skyscrapers. At first it was "
              "just stairs and corridors but then they got onto the roof and the edge. My hands got sweaty when "
              "the camera looked straight down and I felt a bit sick. The woman leaning over the edge made me "
              "really tense. Towards the end I calmed down when they were back inside. The rating was a bit hard "
              "at first but I got used to it after a few minutes and it was fine.")


def make_synthetic_session(path, scripted, seed=1):
    """A whole-film 1D session: human-like (small irregular moves) or scripted (regular, vertical, jumps)."""
    rng = np.random.default_rng(seed)
    lines = [{"type": "meta", "prolific_pid": "BOT" if scripted else "HUMAN", "dimension": "anxiety", "n_loads": 1}]
    t = np.arange(0, 808.9, 0.05)
    value = 0.0
    samples, inputs = [], []
    for i, ts in enumerate(t):
        if scripted:
            # constant-velocity, perfectly vertical moves every 0.5 s, plus periodic jumps
            if i % 10 == 0:
                dx, dy = 0, (-400 if i % 4000 == 0 else -3)
                value = min(100, max(0, value - dy * 100 / 518))
                inputs.append((i, [round(ts, 3), ts * 1000, round(value, 1), "m", dx, dy]))
        elif rng.random() < 0.15:
            dx, dy = int(rng.normal(0, 2)), int(rng.normal(0, 6))
            if dx or dy:
                value = min(100, max(0, value - dy * 100 / 518))
                inputs.append((i, [round(ts, 3), ts * 1000, round(value, 1), "m", dx, dy]))
        samples.append([round(ts, 3), round(ts, 2), ts * 1000, round(value, 1), 1])
    # 30-s chunks of 600 samples; each input goes into the chunk of the sample it happened at
    for k in range(0, len(samples), 600):
        lines.append({"type": "chunk", "t": f"2026-10-04T00:{k // 600:02d}", "tag": "film", "chunk": k // 600,
                      "samples": samples[k:k + 600],
                      "inputs": [row for i, row in inputs if k <= i < k + 600], "events": []})
    n_chars = len(TEXT_HUMAN)
    trials = [
        {"task": "consent", "consent": True},
        {"task": "attention", "n_checks": 1, "n_failed": 0},
        {"task": "attention", "n_checks": 1, "n_failed": 0},
        {"task": "final_text", "text": TEXT_HUMAN, "n_words": len(TEXT_HUMAN.split()), "n_chars": n_chars,
         "n_keys": 3 if scripted else int(n_chars * 1.1), "rt": 240000, "away_ms": 0},
        {"task": "end"},
    ]
    lines += [{"type": "trial", "trial": tr} for tr in trials]
    lines.append({"type": "final", "summary": {"film_untrusted_events": 120 if scripted else 0},
                  "integrity": {}, "data": []})
    return write_ndjson(path, lines)


def test_human_like_session_passes(tmp_path):
    r = metrics_of(load_session(make_synthetic_session(tmp_path / "human.ndjson", scripted=False), STUDY))
    verdict, rej, rev = flags(r, STUDY)
    assert (verdict, rej, rev) == ("OK", [], [])
    assert r["coverage"] == 1.0


def test_scripted_session_is_flagged_on_every_automation_signal(tmp_path):
    r = metrics_of(load_session(make_synthetic_session(tmp_path / "bot.ndjson", scripted=True), STUDY))
    verdict, rej, rev = flags(r, STUDY)
    assert verdict == "REJECT-ELIGIBLE"
    assert "120 script-generated input events" in rej
    assert any(x.startswith("text not typed") for x in rej + rev)
    joined = " ".join(rev)
    assert "identical mouse steps" in joined and "off-axis" in joined and "isolated mouse jumps" in joined
    # one input per 0.5 s with a jump every 4000 samples (200 s): jumps at 0, 200, 400, 600, 800 s
    assert r["n_teleports"] == 5
    assert math.isclose(r["frac_pure_axis"], 1.0)


# ------------------------------------------------- settings come from the study file ---
def other_study():
    """The heights study with a renamed 2D dimension, as another study might define it."""
    study = copy.deepcopy(STUDY)
    dims = study["rating"]["dimensions"]
    dims["valence_arousal"] = dims.pop("affect2d")
    study["rating"]["assignable"] = ["valence_arousal"]
    return study


def test_2d_sessions_are_recognised_from_the_study_file(tmp_path):
    lines = [{"type": "meta", "prolific_pid": "P2", "dimension": "valence_arousal", "n_loads": 1},
             {"type": "chunk", "t": "x", "tag": "film", "chunk": 0,
              "samples": [[0.0, 0.0, 0.0, 40.0, 60.0, 1]], "inputs": [], "events": []}]
    s = load_session(write_ndjson(tmp_path / "s.ndjson", lines), other_study())
    assert s.is2d
    assert (s.film_samples["value_x"].iloc[0], s.film_samples["value_y"].iloc[0]) == (40.0, 60.0)
    # practice error 18 is fine for a 2D dimension, whatever it is called
    assert flags(ok_row(study="valence_arousal", practice_err_last=18), other_study())[0] == "OK"


def test_review_answers_come_from_the_study_file():
    study = copy.deepcopy(STUDY)
    study["qc"]["review_answers"] = [{"question": "seen_before", "answer": "Not sure", "reason": "maybe seen"}]
    assert flags(ok_row(q_seen_before="Not sure"), study) == ("REVIEW", [], ["maybe seen"])
    assert flags(ok_row(q_seen_before="Yes"), study)[0] == "OK"


def test_scope_filter_splits_exploratory_and_confirmatory_sessions():
    explo, confirm = "6ac1d73ab02248cd4974b96c", "a" * 24
    rep = pd.DataFrame({"prolific_study_id": [explo, confirm, "TESTSTUDY", None]})
    assert list(scope_filter(rep, STUDY)["prolific_study_id"]) == [explo]
    assert list(scope_filter(rep, STUDY, "confirmatory")["prolific_study_id"]) == [confirm]
    assert len(scope_filter(rep, STUDY, "all")) == 4
    # a study without an exploratory/confirmatory split: every real Prolific session
    no_split = copy.deepcopy(STUDY)
    del no_split["qc"]["exploratory_studies"]
    assert list(scope_filter(rep, no_split)["prolific_study_id"]) == [explo, confirm]
