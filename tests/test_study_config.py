"""Tests for the study file loader (qc/study_config.py) and the heights example study file.

The heights values are the ones hard-coded in v1.0-heights-film (task/js/config.js, qc/qc_lib.py,
qc/review.py, prolific/*.json); moving them into studies/heights-film/study.yaml must not change them.
"""
import copy

import pytest

from study_config import (ROOT, StudyFileError, attention_checks, check_study, dimension_axes, load_study,
                          questionnaire_pages, scale_pages)

HEIGHTS = ROOT / "studies" / "heights-film"


@pytest.fixture(scope="module")
def heights():
    return load_study(HEIGHTS)


# ------------------------------------------------------- heights values equal v1.0 values ---
def test_film_settings_match_v1(heights):
    film = heights["film"]
    assert film["duration_s"] == 808.9                              # qc_lib.FILM_DURATION_S
    assert film["file"] == "towerClimb_crf29.mp4"                   # config.js videoUrl
    assert film["local_file"] == "media/towerClimb_crf29.mp4"       # config.js localVideoUrl (from task/)
    assert film["length_text"] == "about 13½ minutes"
    assert (film["muted"], film["preload"], film["return_on_slow_download"]) == (True, True, True)
    assert film["preload_max_wait_minutes"] == 5


def test_completion_codes_match_v1(heights):
    codes = {k: v["code"] for k, v in heights["prolific"]["completion_codes"].items()}
    assert codes == {"complete": "VMPDONE1", "slow_download": "VMPSLOWD", "no_consent": "VMPNOCON"}


def test_dimensions_match_v1(heights):
    assert heights["rating"]["assignable"] == ["anxiety", "affect2d"]
    assert dimension_axes(heights, "anxiety") == 1
    assert dimension_axes(heights, "affect2d") == 2
    assert heights["rating"]["dimensions"]["affect2d"]["start_x"] == 50


def test_qc_thresholds_match_v1(heights):
    v1 = {"teleport_px": 250, "teleport_isolation_ms": 100, "stalled_s_review": 30, "teleport_count_review": 3,
          "identical_run_review": 30, "identical_min_px": 3, "big_step_frac_review": 0.10,
          "pure_axis_review": 0.98, "pure_axis_min_events": 200, "coverage_min": 0.95,
          "interruptions_review": 3, "interrupted_s_review": 60, "no_input_s_review": 180,
          "away_s_review": 120, "practice_mae_review": 15, "practice_err2d_review": 20, "quadrant_min": 3,
          "text_keys_per_char_reject": 0.2, "text_min_chars_for_key_check": 200, "typing_cpm_review": 700,
          "ai_markers_review": 2, "duplicate_text_ratio": 0.8}
    thresholds = heights["qc"]["thresholds"]
    for key, value in v1.items():
        assert thresholds[key] == value, key


def test_questionnaires_are_in_v1_order(heights):
    names = {slot: [p.get("name") or p.get("scale") for p in pages]
             for slot, pages in heights["questionnaires"].items()}
    assert names == {
        "intro": ["pre_film"],
        "before_film": ["sticsa"],
        "after_film": ["sticsa"],
        "end": ["post_feelings", "post_body", "usability", "post_mc", "final_text", "feedback"],
    }


def test_sticsa_items_match_v1(heights):
    items = heights["scales"]["sticsa"]["items"]
    assert [i["item"] for i in items] == [1, 2, 6, 7, 8, 12, 14, 15, 18, 20, 21]
    assert items[0]["text"] == "My heart beats fast."
    assert [o["value"] for o in heights["scales"]["sticsa"]["options"]] == [1, 2, 3, 4]
    assert [(p["scale"], p["timepoint"]) for p in scale_pages(heights)] == [("sticsa", "pre"), ("sticsa", "post")]


def test_attention_checks_match_v1(heights):
    checks = attention_checks(heights)
    assert [(c["name"], c["correct"]) for c in checks] == [("attention_1", 0), ("attention_2", 6)]


def test_post_mc_options_are_text_not_true_false(heights):
    post_mc = next(p for p in questionnaire_pages(heights) if p.get("name") == "post_mc")
    assert post_mc["questions"][0]["options"] == ["Yes", "No", "Not sure"]


# --------------------------------------------------------------- check_study finds mistakes ---
def problems_after(heights, change):
    """Apply `change` to a copy of the heights study and return check_study's list of problems."""
    study = copy.deepcopy(heights)
    change(study)
    return check_study(study)


def test_heights_study_has_no_problems(heights):
    assert check_study(heights) == []


def test_unquoted_yes_no_is_reported(heights):
    # In YAML, an unquoted Yes or No is read by Python as true/false; the text must be quoted.
    def change(s):
        next(p for p in s["questionnaires"]["end"] if p["name"] == "post_mc")["questions"][0]["options"] = [True, False]
    problems = problems_after(heights, change)
    assert len(problems) == 1 and "quote" in problems[0] and "post_mc" in problems[0]


def test_missing_film_duration_is_reported(heights):
    problems = problems_after(heights, lambda s: s["film"].pop("duration_s"))
    assert problems == ["film: missing setting 'duration_s'"]


def test_unknown_page_type_is_reported(heights):
    problems = problems_after(heights, lambda s: s["questionnaires"]["end"][0].update(type="slider"))
    assert len(problems) == 1 and "unknown type 'slider'" in problems[0]


def test_attention_answer_outside_the_labels_is_reported(heights):
    def change(s):
        s["questionnaires"]["intro"][0]["questions"][1]["correct"] = 4  # only 4 labels: 0-3
    problems = problems_after(heights, change)
    assert len(problems) == 1 and "attention_1" in problems[0]


def test_scale_page_must_name_a_defined_scale(heights):
    problems = problems_after(heights, lambda s: s["questionnaires"]["before_film"][0].update(scale="stai"))
    assert len(problems) == 1 and "'stai'" in problems[0]


def test_assignable_dimension_must_exist(heights):
    problems = problems_after(heights, lambda s: s["rating"]["assignable"].append("fear"))
    assert problems == ["rating: assignable dimension 'fear' is not defined under rating.dimensions"]


def test_load_study_raises_a_friendly_error(tmp_path):
    (tmp_path / "study.yaml").write_text("film:\n  file: x.mp4\n", encoding="utf8")
    with pytest.raises(StudyFileError) as err:
        load_study(tmp_path)
    assert "missing section 'about'" in str(err.value)


def test_missing_qc_threshold_is_reported(heights):
    problems = problems_after(heights, lambda s: s["qc"]["thresholds"].pop("coverage_min"))
    assert problems == ["qc.thresholds: missing setting 'coverage_min'"]
