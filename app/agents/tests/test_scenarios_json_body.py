"""Marqueurs Step Functions encodés deux fois (ancien ``$string``) : lecture tolérante."""

import json
import subprocess
import sys
from pathlib import Path

from alphaforge.scenarios.tool_table import _json_object

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scenarios-run.sh"


def test_json_object_decodes_double_encoded_string():
    doc = {"run_id": "small-1", "status": "ok"}
    assert _json_object(json.dumps(doc)) == doc
    assert _json_object(doc) == doc
    assert _json_object("pas du json") == "pas du json"
    assert _json_object(None) is None


def _params_snippet() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("<<'PY'\n") + len("<<'PY'\n")
    return text[start : text.index("\nPY\n", start)]


def test_run_sh_parses_double_encoded_request(tmp_path):
    request = {"run_id": "small-1", "params": {"config": "small", "workers": 8}}
    for body in (json.dumps(request), json.dumps(json.dumps(request))):
        path = tmp_path / "request.json"
        path.write_text(body, encoding="utf-8")
        out = subprocess.run(
            [sys.executable, "-I", "-", str(path)], input=_params_snippet(), capture_output=True, text=True, check=True
        )
        assert out.stdout.split() == ["--config", "small", "--workers", "8"]
