"""Exercise public commands as separate processes without any model credential."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run(tmp_path, *args):
    env = dict(os.environ)
    env.pop("GEMINI_API_KEY", None)
    env.pop("GOOGLE_API_KEY", None)
    return subprocess.run([sys.executable, "-m", "pokeeper", *args], cwd=tmp_path,
                          env=env, capture_output=True, text=True)


def demo(tmp_path):
    source = Path(__file__).parents[1] / "examples" / "demo"
    for name in ("project.toml", "messages.pot", "upstream.po"):
        shutil.copyfile(source / name, tmp_path / name)


def test_public_offline_workflow_and_missing_key(tmp_path):
    demo(tmp_path)
    for args in [
        ["plan", "--config", "project.toml", "--candidate", "review"],
        ["apply", "review"],
        ["check", "--config", "project.toml"],
        ["compile", "--config", "project.toml", "--output", "result.mo"],
    ]:
        result = run(tmp_path, *args)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)
    assert (tmp_path / "result.mo").stat().st_size > 0
    before = (tmp_path / "output.po").read_bytes()
    result = run(tmp_path, "fill", "--config", "project.toml", "--candidate", "ai-review", "--cache", "cache.json")
    assert result.returncode == 2
    assert "GEMINI_API_KEY" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "ai-review").exists()
    assert (tmp_path / "output.po").read_bytes() == before


def test_plan_does_not_import_google_sdk(tmp_path):
    demo(tmp_path)
    code = """
import sys
from pokeeper.cli import main
assert main(['plan', '--config', 'project.toml', '--candidate', 'review']) == 0
assert 'google.genai' not in sys.modules
assert 'pokeeper.gemini' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_invalid_options_show_help_without_traceback(tmp_path):
    assert run(tmp_path, "--help").returncode == 0
    result = run(tmp_path, "plan", "--config", "missing.toml", "--candidate", "review")
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
