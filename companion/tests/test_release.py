import importlib.util
import io
import json
from pathlib import Path
import tarfile
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
        self.record = {"schema_version": 1, "package_version": "0.1.2.dev0", "protocol_version": "1.1",
                       "candidate": {"status": "LOCAL_CANDIDATE", "native_head": None},
                       "validated_combinations": [], "acceptance": {"gameplay": "NOT_RUN"}}
        (self.root / "docs/compatibility.json").write_text(json.dumps(self.record))
        for name in ("requirements.lock", "build-requirements.lock", "uv.lock", "LICENSE", "NOTICE", "THIRD_PARTY.md", "README.md"):
            (self.root / name).write_text("test " + name)
        self.sdist = self.dist / "cph_ai_companion-0.1.2.dev0.tar.gz"
        self.wheel = self.dist / "cph_ai_companion-0.1.2.dev0-py3-none-any.whl"
        self.write_sdist()

    def tearDown(self):
        self.temp.cleanup()

    def write_wheel(self, *, main=True, unsafe=False):
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr("cph_ai_companion-0.1.2.dev0.dist-info/METADATA", "Name: cph-ai-companion\nVersion: 0.1.2.dev0\nRequires-Python: <3.13,>=3.12\n")
            archive.writestr(release.PROTOCOL_FILE, '{"protocol_version":"1.1"}')
            archive.writestr(release.MOD_PREFIX + "mod.lua", "return { id='cph_ai_companion' }")
            if main:
                archive.writestr(release.MOD_PREFIX + "main.lua", "return {}")
            if unsafe:
                archive.writestr(release.MOD_PREFIX + "../../outside", "unsafe")

    def write_sdist(self, *, metadata=None, protocol=None, mods=None, extra=None, nonregular=None,
                    root_type=tarfile.DIRTYPE):
        prefix = "cph_ai_companion-0.1.2.dev0/"
        body = metadata if metadata is not None else b"Name: cph-ai-companion\nVersion: 0.1.2.dev0\nRequires-Python: <3.13,>=3.12\n"
        records = [(prefix + "PKG-INFO", body),
                   (prefix + "src/" + release.PROTOCOL_FILE,
                    protocol if protocol is not None else b'{"protocol_version":"1.1"}')]
        resources = mods if mods is not None else {"mod.lua": b"return { id='cph_ai_companion' }", "main.lua": b"return {}"}
        records.extend((prefix + "src/" + release.MOD_PREFIX + name, content)
                       for name, content in resources.items())
        records.extend(extra or [])
        with tarfile.open(self.sdist, "w:gz") as archive:
            root = tarfile.TarInfo(prefix[:-1])
            root.type = root_type
            if root_type == tarfile.SYMTYPE:
                root.linkname = "other-directory"
            archive.addfile(root)
            for name, content in records:
                info = tarfile.TarInfo(name)
                if name == prefix + str(nonregular):
                    info.type = tarfile.SYMTYPE
                    info.linkname = "other-file"
                    archive.addfile(info)
                else:
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))

    def test_mod_is_extracted_from_wheel_as_an_unvalidated_candidate(self):
        self.write_wheel()
        result = release.assemble(self.dist, root=self.root)
        self.assertFalse(result["published"])
        manifest = json.loads((self.dist / "compatibility.json").read_text())
        self.assertEqual(manifest["validated_combinations"], [])
        self.assertEqual(manifest["acceptance"]["gameplay"], "NOT_RUN")
        self.assertEqual(manifest["candidate"]["native_head"], None)
        with zipfile.ZipFile(self.dist / "cph_ai_companion-0.1.2.dev0-mod.zip") as archive:
            self.assertEqual(archive.read("cph_ai_companion/main.lua"), b"return {}")
        for line in (self.dist / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, release.sha256(self.dist / name))

    def test_default_and_candidate_only_do_not_inherit_old_wheel_pass(self):
        self.write_wheel()
        self.record["candidate"] = {"status": "VERIFIED", "native_head": "old-native-head"}
        self.record["acceptance"] = {"python_tests": "PASS", "installed_native_joint": "PASS"}
        self.record["validated_combinations"] = [{"wheel_sha256": "0" * 64, "native_head": "old-native-head"}]
        self.record["evidence"] = {"joint": "old-joint.json"}
        recorded = json.dumps(self.record)
        source = self.root / "docs/compatibility.json"
        source.write_text(recorded)
        for candidate_only in (False, True):
            with self.subTest(candidate_only=candidate_only):
                result = release.assemble(self.dist, root=self.root, candidate_only=candidate_only)
                manifest = json.loads((self.dist / "compatibility.json").read_text())
                self.assertEqual(result["validated_combinations"], [])
                self.assertEqual(manifest["validated_combinations"], [])
                self.assertEqual(manifest["candidate"]["status"], "UNVALIDATED_PACKAGE_CANDIDATE")
                self.assertIsNone(manifest["candidate"]["native_head"])
                self.assertEqual(manifest["acceptance"]["python_tests"], "NOT_RUN")
                self.assertEqual(manifest["acceptance"]["installed_native_joint"], "NOT_RUN")
                self.assertNotIn("evidence", manifest)
                self.assertNotIn("PASS", json.dumps(manifest))
                self.assertEqual(manifest["artifacts"][self.wheel.name]["sha256"], release.sha256(self.wheel))
        self.assertEqual(source.read_text(), recorded)

    def test_explicit_compatibility_preserves_only_exact_wheel_evidence(self):
        self.write_wheel()
        self.record["candidate"] = {"status": "VERIFIED", "native_head": "tested-native-head"}
        self.record["acceptance"] = {"installed_native_joint": "PASS"}
        source = self.root / "explicit-compatibility.json"
        for combination in ({"wheel_sha256": "0" * 64}, {"native_head": "tested-native-head"}):
            with self.subTest(combination=combination):
                self.record["validated_combinations"] = [combination]
                source.write_text(json.dumps(self.record))
                with self.assertRaisesRegex(release.ReleaseError, "^compatibility_wheel_mismatch$"):
                    release.assemble(self.dist, root=self.root, compatibility=source)
                self.assertFalse((self.dist / "compatibility.json").exists())
                self.assertFalse((self.dist / "cph_ai_companion-0.1.2.dev0-mod.zip").exists())
        self.record["validated_combinations"] = [{"wheel_sha256": release.sha256(self.wheel),
                                                 "native_head": "tested-native-head"}]
        source.write_text(json.dumps(self.record))
        release.assemble(self.dist, root=self.root, compatibility=source)
        manifest = json.loads((self.dist / "compatibility.json").read_text())
        self.assertEqual(manifest["validated_combinations"], self.record["validated_combinations"])
        self.assertEqual(manifest["candidate"], self.record["candidate"])
        self.assertEqual(manifest["acceptance"]["installed_native_joint"], "PASS")
        self.record["validated_combinations"] = []
        source.write_text(json.dumps(self.record))
        release.assemble(self.dist, root=self.root, compatibility=source)
        manifest = json.loads((self.dist / "compatibility.json").read_text())
        self.assertEqual(manifest["acceptance"]["installed_native_joint"], "NOT_RUN")
        self.assertEqual(manifest["candidate"]["status"], "UNVALIDATED_PACKAGE_CANDIDATE")

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
        first = (self.dist / "cph_ai_companion-0.1.2.dev0-mod.zip").read_bytes()
        checksums = (self.dist / "SHA256SUMS").read_bytes()
        release.assemble(self.dist, root=self.root)
        self.assertEqual((self.dist / "cph_ai_companion-0.1.2.dev0-mod.zip").read_bytes(), first)
        self.assertEqual((self.dist / "SHA256SUMS").read_bytes(), checksums)

    def test_sdist_must_be_valid_tar_with_matching_identity_and_python_requirement(self):
        self.write_wheel()
        self.sdist.write_bytes(b"source-fixture")
        with self.assertRaisesRegex(release.ReleaseError, "invalid_sdist_archive"):
            release.assemble(self.dist, root=self.root)
        for metadata, code in ((b"Name: another-project\nVersion: 0.1.2.dev0\nRequires-Python: <3.13,>=3.12\n", "wrong_project_sdist"),
                               (b"Name: cph-ai-companion\nVersion: 0.1.1\nRequires-Python: <3.13,>=3.12\n", "wrong_project_sdist"),
                               (b"Name: cph-ai-companion\nVersion: 0.1.2.dev0\nRequires-Python: >=3.10\n", "wrong_python_requirement"),
                               (b"Name: cph-ai-companion\nName: another-project\nVersion: 0.1.2.dev0\nRequires-Python: <3.13,>=3.12\n", "invalid_sdist_metadata")):
            with self.subTest(code=code):
                self.write_sdist(metadata=metadata)
                with self.assertRaisesRegex(release.ReleaseError, code):
                    release.assemble(self.dist, root=self.root)
        self.assertFalse((self.dist / "SHA256SUMS").exists())

    def test_sdist_protocol_and_mod_bytes_must_equal_exact_wheel_resources(self):
        self.write_wheel()
        self.write_sdist(protocol=b'{"protocol_version":"1.1","different_snapshot":true}')
        with self.assertRaisesRegex(release.ReleaseError, "sdist_protocol_mismatch"):
            release.assemble(self.dist, root=self.root)
        for mods in ({"mod.lua": b"return { id='cph_ai_companion' }"},
                     {"mod.lua": b"return { id='cph_ai_companion' }", "main.lua": b"old main"},
                     {"mod.lua": b"return { id='cph_ai_companion' }", "main.lua": b"return {}", "extra.lua": b"not in wheel"}):
            with self.subTest(mods=mods):
                self.write_sdist(mods=mods)
                with self.assertRaisesRegex(release.ReleaseError, "sdist_mod_mismatch"):
                    release.assemble(self.dist, root=self.root)
        self.assertFalse((self.dist / "cph_ai_companion-0.1.2.dev0-mod.zip").exists())

    def test_duplicate_unsafe_and_nonregular_sdist_members_prevent_assembly_without_extraction(self):
        self.write_wheel()
        prefix = "cph_ai_companion-0.1.2.dev0/"
        self.write_sdist(extra=[(prefix + "PKG-INFO", b"duplicate")])
        with self.assertRaisesRegex(release.ReleaseError, "duplicate_sdist_entries"):
            release.assemble(self.dist, root=self.root)
        for name in ("/outside", prefix + "../outside", prefix + "src/./outside",
                     prefix + "src//outside", prefix + "src\\outside", "other-root/PKG-INFO"):
            with self.subTest(name=name):
                self.write_sdist(extra=[(name, b"unsafe")])
                with self.assertRaisesRegex(release.ReleaseError, "invalid_sdist_path"):
                    release.assemble(self.dist, root=self.root)
        for name in ("PKG-INFO", "src/" + release.PROTOCOL_FILE, "src/" + release.MOD_PREFIX + "main.lua"):
            with self.subTest(nonregular=name):
                self.write_sdist(nonregular=name)
                with self.assertRaisesRegex(release.ReleaseError, "nonregular_sdist_resource"):
                    release.assemble(self.dist, root=self.root)
        for root_type in (tarfile.REGTYPE, tarfile.SYMTYPE):
            with self.subTest(root_type=root_type):
                self.write_sdist(root_type=root_type)
                with self.assertRaisesRegex(release.ReleaseError, "invalid_sdist_path"):
                    release.assemble(self.dist, root=self.root)
        self.write_sdist(extra=[(prefix + "src", b"not a directory")])
        with self.assertRaisesRegex(release.ReleaseError, "invalid_sdist_path"):
            release.assemble(self.dist, root=self.root)
        self.write_sdist(extra=[(prefix + "src", b"")], nonregular="src")
        with self.assertRaisesRegex(release.ReleaseError, "invalid_sdist_path"):
            release.assemble(self.dist, root=self.root)
        self.assertFalse((self.root / "outside").exists())
        self.assertFalse((self.root / prefix).exists())

    def test_supplied_protocol_evidence_digest_cannot_be_silently_replaced(self):
        self.write_wheel()
        self.record["schema_digest"] = "different-tested-protocol"
        source = self.root / "docs/compatibility.json"
        source.write_text(json.dumps(self.record))
        with self.assertRaisesRegex(release.ReleaseError, "compatibility_schema_mismatch"):
            release.assemble(self.dist, root=self.root, compatibility=source)
        self.assertFalse((self.dist / "compatibility.json").exists())
        _, digest = release.mod_payloads(self.wheel)
        self.record["schema_digest"] = digest
        source.write_text(json.dumps(self.record))
        release.assemble(self.dist, root=self.root, compatibility=source)
        self.assertEqual(json.loads((self.dist / "compatibility.json").read_text())["schema_digest"], digest)


if __name__ == "__main__":
    unittest.main()
