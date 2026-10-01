import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_release", ROOT / "tools/build_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        (self.root / "docs").mkdir()
        self.record = {"schema_version": 1, "package_version": "0.1.1", "protocol_version": "1.0",
                       "candidate": {"status": "LOCAL_CANDIDATE", "native_head": None},
                       "validated_combinations": [], "acceptance": {"gameplay": "NOT_RUN"}}
        (self.root / "docs/compatibility.json").write_text(json.dumps(self.record))
        for name in ("requirements.lock", "build-requirements.lock", "uv.lock", "LICENSE", "NOTICE", "THIRD_PARTY.md", "README.md"):
            (self.root / name).write_text("test " + name)
        (self.dist / "cph_ai_companion-0.1.1.tar.gz").write_bytes(b"source-fixture")
        self.wheel = self.dist / "cph_ai_companion-0.1.1-py3-none-any.whl"

    def tearDown(self):
        self.temp.cleanup()

    def write_wheel(self, *, main=True, unsafe=False):
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr("cph_ai_companion-0.1.1.dist-info/METADATA", "Name: cph-ai-companion\nVersion: 0.1.1\nRequires-Python: <3.13,>=3.12\n")
            archive.writestr(release.PROTOCOL_FILE, '{"protocol_version":"1.0"}')
            archive.writestr(release.MOD_PREFIX + "mod.lua", "return { id='cph_ai_companion' }")
            if main:
                archive.writestr(release.MOD_PREFIX + "main.lua", "return {}")
            if unsafe:
                archive.writestr(release.MOD_PREFIX + "../../outside", "unsafe")

    def test_mod_is_extracted_from_wheel_and_claims_are_preserved(self):
        self.write_wheel()
        result = release.assemble(self.dist, root=self.root)
        self.assertFalse(result["published"])
        manifest = json.loads((self.dist / "compatibility.json").read_text())
        self.assertEqual(manifest["validated_combinations"], [])
        self.assertEqual(manifest["acceptance"]["gameplay"], "NOT_RUN")
        self.assertEqual(manifest["candidate"]["native_head"], None)
        with zipfile.ZipFile(self.dist / "cph_ai_companion-0.1.1-mod.zip") as archive:
            self.assertEqual(archive.read("cph_ai_companion/main.lua"), b"return {}")
        for line in (self.dist / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, release.sha256(self.dist / name))

    def test_missing_resources_and_path_traversal_prevent_assembly(self):
        self.write_wheel(main=False)
        with self.assertRaisesRegex(release.ReleaseError, "mod_resources_missing"):
            release.assemble(self.dist, root=self.root)
        self.write_wheel(unsafe=True)
        with self.assertRaisesRegex(release.ReleaseError, "invalid_mod_resource"):
            release.assemble(self.dist, root=self.root)

    def test_mod_archive_and_checksums_are_reproducible(self):
        self.write_wheel()
        release.assemble(self.dist, root=self.root)
        first = (self.dist / "cph_ai_companion-0.1.1-mod.zip").read_bytes()
        checksums = (self.dist / "SHA256SUMS").read_bytes()
        release.assemble(self.dist, root=self.root)
        self.assertEqual((self.dist / "cph_ai_companion-0.1.1-mod.zip").read_bytes(), first)
        self.assertEqual((self.dist / "SHA256SUMS").read_bytes(), checksums)


if __name__ == "__main__":
    unittest.main()
