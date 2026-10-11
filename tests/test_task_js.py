"""Runs the node checks of the browser modules (tests/js/check_task.js) on the heights study file.

Skipped when node is not installed. The study file is read with PyYAML and handed to node as JSON
(the browser itself reads the YAML with js-yaml).
"""
import json
import shutil
import subprocess

import pytest

from study_config import ROOT, load_study


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_task_modules_with_the_heights_study(tmp_path):
    study = load_study(ROOT / "studies" / "heights-film")
    study.pop("_file")
    study_json = tmp_path / "study.json"
    study_json.write_text(json.dumps(study), encoding="utf8")
    result = subprocess.run(["node", str(ROOT / "tests" / "js" / "check_task.js"), str(study_json)],
                            capture_output=True, text=True, encoding="utf8")
    print(result.stdout)
    assert result.returncode == 0, result.stderr
    assert "checks passed" in result.stdout
