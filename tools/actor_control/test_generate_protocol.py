"""Exercise the generator CLI against editable authority files, without Git."""

import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RESOURCE = Path("companion/src/cph_ai_companion/resources/protocol")


class ProtocolGeneratorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(
            prefix="cph-protocol-generator-"
        )
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.resource = self.root / RESOURCE
        self.resource.mkdir(parents=True)
        self.generator = self.root / "tools/actor_control/generate_protocol.py"
        self.generator.parent.mkdir(parents=True)
        shutil.copyfile(Path(__file__).with_name("generate_protocol.py"),
                        self.generator)
        self.output = self.root / "src/actor_control_protocol_generated.h"
        self.output.parent.mkdir()
        self.inputs = {
            name: (ROOT / RESOURCE / name).read_bytes()
            for name in ("protocol.json", "fixtures.json", "task_fixtures.json")
        }
        for name, raw in self.inputs.items():
            (self.resource / name).write_bytes(raw)

    def invoke(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(self.generator), *arguments],
            cwd=self.root, capture_output=True, text=True, check=False,
        )

    def generate(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.output.read_bytes()

    def test_uncommitted_authority_generates_without_snapshots(self):
        fixtures = json.loads(self.inputs["fixtures.json"])
        fixtures[0]["name"] = "edited-without-a-commit"
        raw = (json.dumps(fixtures) + "\n").encode()
        (self.resource / "fixtures.json").write_bytes(raw)
        header = self.generate().decode()
        self.assertNotIn("\r\n", header)
        self.assertIn("edited-without-a-commit", header)
        self.assertIn(hashlib.sha256(raw).hexdigest(), header)
        self.assertIn(hashlib.sha256(self.inputs["protocol.json"]).hexdigest(),
                      header)
        self.assertIn(hashlib.sha256(self.inputs["task_fixtures.json"]).hexdigest(),
                      header)
        self.assertIn("protocol_task_fixtures_json", header)
        for name in self.inputs:
            self.assertIn((RESOURCE / name).as_posix(), header)
        self.assertFalse((self.root / "data/reference/actor_control").exists())
        result = self.invoke("--check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_large_json_uses_exact_null_terminated_byte_array(self):
        fixtures = json.loads(self.inputs["fixtures.json"])
        fixtures[0]["name"] = "large-" + "x" * 17000
        (self.resource / "fixtures.json").write_text(json.dumps(fixtures), encoding="utf-8")
        header = self.generate().decode()
        for name, value in (("protocol_json", json.loads(self.inputs["protocol.json"])),
                            ("protocol_fixtures_json", fixtures)):
            with self.subTest(name=name):
                match = re.search(r"inline constexpr char " + name +
                                  r"\[\] = \{(.*?)\};", header, re.DOTALL)
                self.assertIsNotNone(match)
                actual = bytes(int(n) for n in re.findall(r"\d+", match.group(1)))
                expected = json.dumps(value, ensure_ascii=True,
                                      separators=(",", ":")).encode("ascii") + b"\0"
                self.assertEqual(actual, expected)
        self.assertEqual(self.invoke("--check").returncode, 0)

    def test_check_detects_either_changed_input_without_writing(self):
        header = self.generate()
        for name, raw in self.inputs.items():
            with self.subTest(name=name):
                (self.resource / name).write_bytes(raw + b"\n")
                result = self.invoke("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("generated protocol header is stale",
                              result.stderr)
                self.assertEqual(self.output.read_bytes(), header)
                (self.resource / name).write_bytes(raw)

    def test_malformed_inputs_do_not_replace_a_valid_header(self):
        header = self.generate()
        invalid = (
            ("fixtures.json", b"[]"),
            ("fixtures.json", b'[{"name":"x","valid":1,"plan":{}}]'),
            ("fixtures.json", b'[{"name":"x","valid":true,"plan":{}},'
             b'{"name":"x","valid":false,"plan":{}}]'),
            ("fixtures.json", b'[{"name":"x","valid":false,"plan":NaN}]'),
            ("task_fixtures.json", b"[]"),
            ("task_fixtures.json", b'[{"name":"x","valid":true,"plan":{}}]'),
            ("task_fixtures.json", b'[{"name":"x","valid":false,"offer":NaN}]'),
            ("protocol.json", b'{"schema_version":1,"protocol_version":"1.2",'
             b'"protocol_version":"1.0"}'),
        )
        for name, raw in invalid:
            with self.subTest(name=name, raw=raw):
                (self.resource / name).write_bytes(raw)
                result = self.invoke()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.output.read_bytes(), header)
                (self.resource / name).write_bytes(self.inputs[name])


if __name__ == "__main__":
    unittest.main()
