import json
import sys
from pathlib import Path

def show_batch(batch_id: str):
    path = Path(f"cph-translation/antigravity-batch-01/requests/{batch_id}.json")
    if not path.exists():
        print(f"File {path} does not exist")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"=== Batch {batch_id} ({len(data['entries'])} entries) ===")
    if data.get("terms"):
        print("Terms:", json.dumps(data["terms"], ensure_ascii=False))
    for i, e in enumerate(data["entries"], 1):
        print(f"[{i}] ID: {e['id']}")
        if e.get("context"):
            print(f"    Context: {e['context']}")
        if e.get("developer_comments"):
            print(f"    Dev Comments: {e['developer_comments']}")
        if e.get("flags"):
            print(f"    Flags: {e['flags']}")
        print(f"    Singular: {repr(e['singular'])}")
        if e.get("plural"):
            print(f"    Plural: {repr(e['plural'])}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        for b in sys.argv[1:]:
            show_batch(b)
