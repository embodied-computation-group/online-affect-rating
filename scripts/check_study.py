"""Check a study file and print a short overview of the session it describes.

Usage (from the repository folder):
  python scripts/check_study.py --study studies/heights-film

Run it after every edit of study.yaml. It reports mistakes in plain words (missing settings,
unknown page types, Yes/No answers that need quotes, attention-check answers that do not exist).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "qc"))
from study_config import SLOTS, StudyFileError, load_study  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True, help="study folder, e.g. studies/heights-film")
    a = ap.parse_args()
    try:
        study = load_study(a.study)
    except StudyFileError as err:
        sys.exit(str(err))

    film = study["film"]
    print(f"{study['_file']}: no problems found\n")
    print(f"film:        {film['file']} ({film['duration_s']} s, local copy {film['local_file']})")
    for name, dim in study["rating"]["dimensions"].items():
        print(f"dimension:   {name} ({dim.get('axes', 1)} axis/axes, study {dim['study']})")
    codes = {k: v["code"] for k, v in study["prolific"]["completion_codes"].items()}
    print(f"codes:       {codes}")
    print(f"test mode:   {study.get('test_mode', False)}")
    print("questionnaire pages:")
    for slot in SLOTS:
        for page in study["questionnaires"].get(slot) or []:
            label = page.get("name") or f"{page['scale']} ({page.get('timepoint', '')})"
            print(f"  {slot:12s} {page['type']:13s} {label}")


if __name__ == "__main__":
    main()
