"""Read and check a study file (studies/<name>/study.yaml).

The study file holds everything that is specific to one study. The browser task, the deploy scripts and
the QC scripts all read the same file; this module is the Python side.

    from study_config import load_study
    study = load_study("studies/heights-film")      # a study folder or the study.yaml itself
    study["film"]["duration_s"]                    # -> 808.9

Every Python script takes the study folder as  --study studies/<name>.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Sections and settings every study file needs (optional ones are described in the heights example).
REQUIRED = {
    "about": ["title", "pi_name", "contact_email", "duration", "payment"],
    "film": ["file", "local_file", "duration_s", "length_text", "muted", "preload", "preload_max_wait_minutes",
             "return_on_slow_download"],
    "rating": ["input_mode", "joystick_full_scale_frac", "resume_rewind_seconds", "sample_rate_hz",
               "chunk_seconds", "min_screen_width", "min_screen_height", "assignable", "dimensions"],
    "practice": ["max_error_1d", "max_error_2d", "keyframes_1d", "keyframes_2d"],
    "texts": ["information", "consent_statements", "consent_button", "decline_button", "debrief"],
    "questionnaires": [],
    "prolific": ["completion_codes"],
    "qc": ["thresholds"],
}
COMPLETION_CODES = ["complete", "no_consent", "slow_download"]
SLOTS = ["intro", "before_film", "after_film", "end"]
PAGE_TYPES = ["likert", "multi_choice", "multi_select", "text", "free_text", "scale", "html_form"]


class StudyFileError(Exception):
    """The study file is missing or has mistakes; the message lists them."""


def study_file(path) -> Path:
    """The study.yaml for a study folder (or the file itself)."""
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = ROOT / path
    return path / "study.yaml" if path.is_dir() else path


def load_study(path) -> dict:
    """Read a study file and check it. Raises StudyFileError with a list of problems."""
    file = study_file(path)
    if not file.exists():
        raise StudyFileError(f"No study file at {file}. Pass the study folder, e.g. --study studies/heights-film")
    try:
        study = yaml.safe_load(file.read_text(encoding="utf8"))
    except yaml.YAMLError as err:
        raise StudyFileError(f"{file} is not valid YAML:\n{err}") from err
    problems = check_study(study)
    if problems:
        raise StudyFileError(f"Problems in {file}:\n  - " + "\n  - ".join(problems))
    study["_file"] = file
    return study


# ------------------------------------------------------------------------- small helpers ---
def questionnaire_pages(study: dict) -> list[dict]:
    """All questionnaire pages, in session order."""
    q = study.get("questionnaires") or {}
    return [page for slot in SLOTS for page in (q.get(slot) or [])]


def scale_pages(study: dict) -> list[dict]:
    """The 'scale' pages (e.g. STICSA pre and post), in session order."""
    return [p for p in questionnaire_pages(study) if p.get("type") == "scale"]


def attention_checks(study: dict) -> list[dict]:
    """Questions with a `correct` answer, in session order."""
    return [q for p in questionnaire_pages(study) for q in (p.get("questions") or []) if "correct" in q]


def dimension_axes(study: dict, dimension: str) -> int:
    """1 for a single rating scale, 2 for the 2D grid."""
    return int(study["rating"]["dimensions"][dimension].get("axes", 1))


# ---------------------------------------------------------------------------------- checks ---
def check_study(study) -> list[str]:
    """Return a list of problems in a study file (empty = fine). Plain messages for the person editing it."""
    if not isinstance(study, dict):
        return ["the file is empty or not a set of sections"]
    problems = []
    for section, keys in REQUIRED.items():
        if not isinstance(study.get(section), dict):
            problems.append(f"missing section '{section}'")
            continue
        problems += [f"{section}: missing setting '{k}'" for k in keys if k not in study[section]]
    if problems:
        return problems  # the checks below need the sections
    problems += _check_rating(study)
    problems += _check_codes(study)
    for slot in study["questionnaires"]:
        if slot not in SLOTS:
            problems.append(f"questionnaires: unknown place '{slot}' (use {', '.join(SLOTS)})")
    for page in questionnaire_pages(study):
        problems += _check_page(study, page)
    return problems


def _check_rating(study) -> list[str]:
    rating = study["rating"]
    problems = []
    for dim in rating["assignable"]:
        if dim not in rating["dimensions"]:
            problems.append(f"rating: assignable dimension '{dim}' is not defined under rating.dimensions")
    for name, dim in rating["dimensions"].items():
        for k in ["study", "label", "question", "low", "high", "start"]:
            if k not in dim:
                problems.append(f"rating.dimensions.{name}: missing setting '{k}'")
        if dim.get("axes", 1) == 2:
            problems += [f"rating.dimensions.{name}: missing setting '{k}'" for k in ["x_low", "x_high"] if k not in dim]
    return problems


def _check_codes(study) -> list[str]:
    codes = study["prolific"]["completion_codes"]
    return [f"prolific.completion_codes: missing '{k}' (with a code: ...)" for k in COMPLETION_CODES
            if not isinstance(codes.get(k), dict) or not codes[k].get("code")]


def _not_text(values) -> bool:
    """True if a list of answer options contains something that YAML did not read as text (e.g. Yes -> True)."""
    return any(isinstance(v, bool) or v is None for v in values)


def _check_page(study, page) -> list[str]:
    name = page.get("name") or page.get("scale") or "?"
    where = f"questionnaire page '{name}'"
    kind = page.get("type")
    if kind not in PAGE_TYPES:
        return [f"{where}: unknown type '{kind}' (use one of {', '.join(PAGE_TYPES)})"]
    if kind == "scale":
        if page.get("scale") not in (study.get("scales") or {}):
            return [f"{where}: scale '{page.get('scale')}' is not defined under scales"]
        return []
    if not page.get("name"):
        return [f"a '{kind}' questionnaire page has no name"]
    if kind == "free_text":
        return [f"{where}: missing '{k}'" for k in ("prompt", "min_words") if k not in page]
    if kind == "html_form":
        return [] if "html" in page else [f"{where}: missing 'html'"]
    problems = []
    for q in page.get("questions") or []:
        options = q.get("labels", q.get("options", []))
        if _not_text(options):
            problems.append(f"{where}, question '{q.get('name')}': put the answer options in quotes, "
                            f"e.g. \"Yes\", \"No\" (unquoted they are read as true/false)")
        if "correct" in q and not (isinstance(q["correct"], int) and 0 <= q["correct"] < len(options)):
            problems.append(f"{where}, attention check '{q.get('name')}': correct must be the number of an "
                            f"option, 0 to {len(options) - 1} (0 = first/leftmost)")
    if not page.get("questions"):
        problems.append(f"{where}: no questions")
    return problems
