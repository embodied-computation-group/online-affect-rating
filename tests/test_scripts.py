"""Known-answer tests for the deploy helpers in scripts/.

The expected Prolific draft is what v1.0-heights-film built from prolific/study_template.json and
prolific/filters.json (copied here by hand), for:
  create_prolific_study.py --dim affect2d --places 20 --tag main_c1 --quota-sex --block <id>
"""
from create_prolific_study import build_prolific_study
from deploy_jatos import video_upload
from study_config import ROOT, load_study

STUDY = load_study(ROOT / "studies" / "heights-film")
LINK = "https://jatos.example.org/publix/abc"

V1_DRAFT = {
    "name": "Feelings while watching a film",
    "description": "Watch a short first-person film (about 13½ minutes) of people climbing a skyscraper (no one is "
                   "hurt), and continuously report how you feel by moving your mouse. Includes a short practice, some "
                   "questions, and a short written description (at least 100 words). The film has no sound. Requires "
                   "a desktop/laptop computer with a physical mouse or trackpad (not a touchscreen, pen/drawing "
                   "tablet, or remote-desktop/virtual-machine session), and watching carefully in a quiet room, in "
                   "full-screen mode, without distractions. Content note: heights footage; please do not take part "
                   "if you have a strong fear of heights.",
    "prolific_id_option": "url_parameters",
    "completion_codes": [
        {"code": "VMPDONE1", "code_type": "COMPLETED", "actions": [{"action": "MANUALLY_REVIEW"}]},
        {"code": "VMPSLOWD", "code_type": "OTHER", "actions": [{"action": "REQUEST_RETURN", "return_reason":
            "The film could not be downloaded quickly enough on your connection, so please return the study "
            "(no penalty)."}]},
        {"code": "VMPNOCON", "code_type": "NO_CONSENT", "actions": [{"action": "REQUEST_RETURN", "return_reason":
            "You chose not to give consent, so please return the study."}]},
    ],
    "estimated_completion_time": 30,
    "maximum_allowed_time": 90,
    "reward": 480,
    "device_compatibility": ["desktop"],
    "peripheral_requirements": [],
    "submissions_config": {"max_submissions_per_participant": 1},
    "external_study_url": LINK + "?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}"
                                 "&SESSION_ID={{%SESSION_ID%}}&dim=affect2d",
    "internal_name": "vmp towerClimb affect2d main_c1",
    "total_available_places": 20,
    "project": "6ac1c23dd2c370786a5fa2fa",
    "study_type": "QUOTA",
    "filters": [
        {"filter_id": "fluent-languages", "selected_values": ["19"]},
        {"filter_id": "vision", "selected_values": ["0"]},
        {"filter_id": "approval_rate", "selected_range": {"lower": 95, "upper": 100}},
        {"filter_id": "approval_numbers", "selected_range": {"lower": 20}},
        {"filter_id": "previous_studies_blocklist", "selected_values": ["6ac1d73ab02248cd4974b96c"]},
        {"filter_id": "sex", "selected_values": ["0", "1"], "weightings": {"0": 1, "1": 1}},
    ],
}


def test_prolific_draft_matches_v1():
    draft = build_prolific_study(STUDY, dim="affect2d", tag="main_c1", places=20, link=LINK,
                                 block=["6ac1d73ab02248cd4974b96c"], quota_sex=True)
    assert draft == V1_DRAFT


def test_random_dimension_has_no_dim_parameter_and_link_with_query_uses_ampersand():
    draft = build_prolific_study(STUDY, dim="random", tag="pilot", places=6, link=LINK + "?x=1")
    assert draft["external_study_url"].startswith(LINK + "?x=1&PROLIFIC_PID=")
    assert "dim=" not in draft["external_study_url"]
    assert "study_type" not in draft and len(draft["filters"]) == 4


def test_video_upload_uses_the_local_film_under_its_jatos_name():
    # v1.0 uploaded media/towerClimb.mp4, which the task never played (it plays towerClimb_crf29.mp4)
    source, name = video_upload(STUDY)
    assert source == ROOT / "media" / "towerClimb_crf29.mp4"
    assert name == "towerClimb_crf29.mp4"
