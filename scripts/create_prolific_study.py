"""Create a Prolific *draft* study (never publishes) for one rating dimension.

Usage (--study is the study folder):
  python scripts/create_prolific_study.py --study studies/heights-film --dim anxiety --places 6 --tag pilot [--dry-run]
  python scripts/create_prolific_study.py --study studies/heights-film --dim random --places 6 --tag pilot
  python scripts/create_prolific_study.py --study studies/heights-film --dim affect2d --places 6 --tag pilot --block <study-1 id>
  python scripts/create_prolific_study.py --study studies/heights-film --dim affect2d --places 20 --tag main_c1 --quota-sex --block <pilot ids>

Builds the study from the `prolific` section of the study file (listing, completion codes, filters, project),
points it at the JATOS study link in prolific/jatos_link.txt (written by scripts/deploy_jatos.py --link), adds
the Prolific URL parameters and ?dim=, writes it to prolific/generated/<tag>_<dim>.json, then runs
`prolific study create` (draft only). With --dry-run it only writes the file.
Publishing is a deliberate manual step:  scripts/prolific.sh study publish <id>  (or the web UI).
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qc"))
from study_config import StudyFileError, load_study  # noqa: E402


def build_prolific_study(study, dim, tag, places, link, project=None, block=(), quota_sex=False):
    """The Prolific draft study (a dict for the Prolific API) for one dimension ("random" = no ?dim=)."""
    p = study["prolific"]
    draft = dict(p.get("listing") or {})
    # The task sends participants back with these codes (same study file), so they always match.
    draft["completion_codes"] = list(p["completion_codes"].values())
    # Prolific fills in the {{%...%}} parts for each participant.
    params = "PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}"
    if dim != "random":
        params += f"&dim={dim}"
    draft["external_study_url"] = f"{link}{'&' if '?' in link else '?'}{params}"
    draft["internal_name"] = f"{p.get('internal_name', 'film rating')} {dim} {tag}"
    draft["total_available_places"] = places
    draft["project"] = project or p.get("project")
    filters = list(p.get("filters") or [])
    if block:  # participants of these Prolific studies cannot take part
        filters.append({"filter_id": "previous_studies_blocklist", "selected_values": list(block)})
    if quota_sex:  # sample balanced 50/50 on Prolific's Sex screener (Male/Female)
        draft["study_type"] = "QUOTA"
        filters.append({"filter_id": "sex", "selected_values": ["0", "1"], "weightings": {"0": 1, "1": 1}})
    draft["filters"] = filters
    return draft


def read_secrets():
    """secrets.env as a dict (PROLIFIC_TOKEN etc.)."""
    env = {}
    for line in (ROOT / "secrets.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True, help="study folder, e.g. studies/heights-film")
    ap.add_argument("--dim", required=True, help="a rating dimension from the study file, or 'random'")
    ap.add_argument("--places", type=int, required=True)
    ap.add_argument("--tag", default="pilot")
    ap.add_argument("--project", help="Prolific project id (default: prolific.project in the study file)")
    ap.add_argument("--block", action="append", default=[], help="Prolific study ID whose participants are excluded")
    ap.add_argument("--quota-sex", action="store_true",
                    help="Quota sample balanced 50/50 on Prolific's Sex screener (Male/Female)")
    ap.add_argument("--link", help="JATOS study link (default: prolific/jatos_link.txt)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    try:
        study = load_study(a.study)
    except StudyFileError as err:
        sys.exit(str(err))
    dims = list(study["rating"]["dimensions"])
    if a.dim not in dims + ["random"]:
        sys.exit(f"--dim must be one of {', '.join(dims)} or random")

    link_file = ROOT / "prolific/jatos_link.txt"
    link = a.link or (link_file.read_text().strip() if link_file.exists() else None)
    if not link:
        sys.exit("No JATOS link: run scripts/deploy_jatos.py --link first, or pass --link")

    draft = build_prolific_study(study, a.dim, a.tag, a.places, link, a.project, a.block, a.quota_sex)
    out = ROOT / "prolific/generated" / f"{a.tag}_{a.dim}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf8")
    print("wrote", out.relative_to(ROOT))
    reward = draft.get("reward", 0) / 100
    print(f"{a.places} places x £{reward:.2f} = £{a.places * reward:.2f} in rewards (plus Prolific fees)")
    if a.dry_run:
        return

    # Call the CLI directly (on Windows a bare "bash" can resolve to WSL), with secrets.env in the environment.
    env = dict(os.environ, **read_secrets())
    cli = shutil.which("prolific") or str(ROOT / "bin" / ("prolific.exe" if os.name == "nt" else "prolific"))
    r = subprocess.run([cli, "study", "create", "-t", str(out)], capture_output=True, text=True, encoding="utf8", env=env)
    print(r.stdout[-3000:], r.stderr[-2000:])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
