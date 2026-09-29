import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

def save_and_validate(batch_id: str, translations: list[dict]):
    bundle_dir = Path("cph-translation/antigravity-batch-01")
    req_file = bundle_dir / "requests" / f"{batch_id}.json"
    if not req_file.exists():
        raise FileNotFoundError(f"Request file {req_file} not found")

    raw = req_file.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    req = json.loads(raw)

    expected_ids = [e["id"] for e in req["entries"]]
    assert len(translations) == len(expected_ids), f"Expected {len(expected_ids)} translations, got {len(translations)}"

    formatted_translations = []
    for item, exp_id in zip(translations, expected_ids):
        if isinstance(item, str):
            formatted_translations.append({"id": exp_id, "values": [item]})
        elif isinstance(item, dict):
            assert item.get("id") == exp_id, f"ID mismatch: got {item.get('id')}, expected {exp_id}"
            assert "values" in item and isinstance(item["values"], list) and len(item["values"]) == 1
            formatted_translations.append(item)
        else:
            raise ValueError(f"Unexpected item type {type(item)}")
    translations = formatted_translations

    resp = {
        "request_sha256": sha,
        "producer": {
            "tool": "Antigravity",
            "model": "Gemini 3.8 Flash"
        },
        "translations": translations
    }

    resp_dir = bundle_dir / "responses"
    resp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = resp_dir / f".{batch_id}.json.tmp"
    final_path = resp_dir / f"{batch_id}.json"

    tmp_path.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, final_path)

    env = dict(os.environ)
    env["PATH"] = f"/nix/store/518bcx82g8m9cyji47sprx9ajmadjk8s-gettext-1.0/bin:{env.get('PATH', '')}"
    cmd = [".venv/bin/pokeeper", "responses", "cph-translation/antigravity-batch-01", "--batch", batch_id]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python save_batch_response.py <batch_id> [json_file or stdin]", file=sys.stderr)
        sys.exit(1)
    b_id = sys.argv[1]
    if len(sys.argv) >= 3:
        data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    else:
        data = json.load(sys.stdin)
    save_and_validate(b_id, data)
