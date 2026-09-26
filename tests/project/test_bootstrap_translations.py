"""Resource-fetcher unit fixtures are not game/platform acceptance evidence."""

import copy
import hashlib
import importlib.util
import io
import json
import struct
import tarfile
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "bootstrap_translations", Path(__file__).resolve().parents[2] /
    "tools/project/bootstrap_translations.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def mo_fixture(messages):
    """Minimal GNU MO syntax fixture, exclusively for parser/policy tests."""
    pairs = sorted((key.encode(), value.encode()) for key, value in messages.items())
    count = len(pairs)
    ids = b"".join(key + b"\0" for key, _ in pairs)
    strings = b"".join(value + b"\0" for _, value in pairs)
    offset = 28 + 16 * count
    id_table = []
    for key, _ in pairs:
        id_table.append(struct.pack("<II", len(key), offset))
        offset += len(key) + 1
    str_table = []
    for _, value in pairs:
        str_table.append(struct.pack("<II", len(value), offset))
        offset += len(value) + 1
    return (struct.pack("<7I", 0x950412DE, 0, count, 28, 28 + count * 8, 0, 0) +
            b"".join(id_table + str_table) + ids + strings)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "resources.tar.gz"
        self.output = self.root / "output"
        self.mo = mo_fixture({"": "Content-Type: text/plain; charset=UTF-8\nLanguage: zh_CN\n",
                              "Unit fixture": "单元测试样本"})
        self.members = [("bundle/lang/mo/zh_CN/LC_MESSAGES/cataclysm-dda.mo", self.mo),
                        ("bundle/LICENSE.txt", b"Unit fixture license\n")]
        self.lock = {
            "schema_version": 1, "kind": "compiled-gettext-mo", "gettext_domain": "cataclysm-dda",
            "required_locales": ["zh_CN"],
            "source": {"commit": "1" * 40, "repository": "example/test", "release_tag": "test",
                       "name": "resources.tar.gz",
                       "url": "https://github.com/example/test/releases/download/test/resources.tar.gz"},
            "limits": {"members": 10, "member_bytes": 1024 * 1024, "uncompressed_bytes": 1024 * 1024},
            "probe": {"locale": "zh_CN", "msgid": "Unit fixture", "msgstr": "单元测试样本"},
            "files": []}
        for source, content in self.members:
            entry = {"archive_path": source, "path": source.removeprefix("bundle/"),
                     "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                     "kind": "gettext-mo" if source.endswith(".mo") else "notice"}
            if entry["kind"] == "gettext-mo":
                entry["locale"] = "zh_CN"
            self.lock["files"].append(entry)
        self.write_archive()

    def write_archive(self, extras=()):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, content in self.members:
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            for member in extras:
                archive.addfile(member, io.BytesIO(b"x" * member.size))
        self.lock["source"]["bytes"] = self.archive.stat().st_size
        self.lock["source"]["sha256"] = bootstrap.sha256(self.archive)

    def run_bootstrap(self):
        return bootstrap.bootstrap(self.lock, self.output, self.archive)

    def assert_rejected(self, expected=""):
        with self.assertRaisesRegex((bootstrap.ResourceError, OSError, struct.error), expected):
            self.run_bootstrap()
        self.assertFalse(self.output.exists())

    def test_valid_resources_and_read_only_check(self):
        report = self.run_bootstrap()
        before = {p: p.stat().st_mtime_ns for p in self.output.rglob("*")}
        self.assertEqual(report["probe"]["actual"], "单元测试样本")
        self.assertEqual(bootstrap.verify_output(self.output, self.lock), report)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in self.output.rglob("*")})

    def test_wrong_archive_hash(self):
        self.lock["source"]["sha256"] = "0" * 64
        self.assert_rejected("archive SHA256")

    def test_wrong_archive_size(self):
        self.lock["source"]["bytes"] += 1
        self.assert_rejected("archive byte size")

    def test_wrong_resource_hash(self):
        self.lock["files"][0]["sha256"] = "0" * 64
        self.assert_rejected("resource SHA256")

    def test_unsafe_paths_even_in_unselected_members(self):
        for name in ["../escape", "/absolute", "bundle/../../escape", "C:/escape", "bad\\path"]:
            with self.subTest(name=name):
                self.write_archive([tarfile.TarInfo(name)])
                self.assert_rejected("unsafe archive path")

    def test_duplicate_member(self):
        self.write_archive([tarfile.TarInfo(self.members[0][0])])
        self.assert_rejected("duplicate archive")

    def test_unsupported_member_types(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]:
            with self.subTest(kind=kind):
                member = tarfile.TarInfo("bundle/unsafe")
                member.type = kind
                member.linkname = "../../outside"
                self.write_archive([member])
                self.assert_rejected("unsupported archive member type")

    def test_pinned_unselected_document_link_is_never_extracted(self):
        member = tarfile.TarInfo("bundle/docs/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../documentation"
        self.lock["ignored_symlinks"] = {member.name: member.linkname}
        self.write_archive([member])
        self.run_bootstrap()
        self.assertFalse((self.output / "docs").exists())

    def test_document_link_exception_requires_exact_target(self):
        member = tarfile.TarInfo("bundle/docs/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        self.lock["ignored_symlinks"] = {member.name: "../documentation"}
        self.write_archive([member])
        self.assert_rejected("unsupported archive member type")

    def test_member_size_limit(self):
        self.lock["limits"]["member_bytes"] = 1
        self.assert_rejected("member size limit")

    def test_member_count_limit(self):
        self.lock["limits"]["members"] = 1
        self.assert_rejected("member limit")

    def test_decompression_limit(self):
        self.lock["limits"]["uncompressed_bytes"] = 100
        self.assert_rejected("decompression limit")

    def test_missing_notice(self):
        self.members.pop()
        self.write_archive()
        self.assert_rejected("missing locked resources")

    def test_invalid_mo(self):
        self.members[0] = (self.members[0][0], b"Invalid MO")
        self.lock["files"][0].update(bytes=10, sha256=hashlib.sha256(b"Invalid MO").hexdigest())
        self.write_archive()
        self.assert_rejected()

    def test_empty_mo(self):
        content = mo_fixture({"": "Content-Type: text/plain; charset=UTF-8\n"})
        self.members[0] = (self.members[0][0], content)
        self.lock["files"][0].update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        self.write_archive()
        self.assert_rejected("empty compiled translation")

    def test_optional_upstream_header_only_catalog_is_reported_as_zero(self):
        content = mo_fixture({"": "Content-Type: text/plain; charset=UTF-8\n"})
        name = "bundle/lang/mo/optional/LC_MESSAGES/cataclysm-dda.mo"
        self.members.append((name, content))
        self.lock["files"].append({"archive_path": name, "path": name.removeprefix("bundle/"),
                                   "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                                   "kind": "gettext-mo", "locale": "optional"})
        self.write_archive()
        report = self.run_bootstrap()
        entry = next(x for x in report["catalogs"] if x["locale"] == "optional")
        self.assertEqual(entry["entries"], 0)

    def test_required_locale_missing(self):
        self.lock["required_locales"].append("fr")
        self.assert_rejected("required locale missing")

    def test_real_lookup_must_match(self):
        self.lock["probe"]["msgstr"] = "Wrong fixture"
        self.assert_rejected("lookup failed")

    def test_existing_output_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "user-save"
        sentinel.write_bytes(b"preserve me")
        with self.assertRaisesRegex(bootstrap.ResourceError, "output exists"):
            self.run_bootstrap()
        self.assertEqual(sentinel.read_bytes(), b"preserve me")

    def test_check_rejects_extra_files(self):
        self.run_bootstrap()
        (self.output / "extra").write_bytes(b"unlisted")
        with self.assertRaisesRegex(bootstrap.ResourceError, "inventory differs"):
            bootstrap.verify_output(self.output, self.lock)

    def test_check_rejects_symbolic_links(self):
        self.run_bootstrap()
        (self.output / "extra-link").symlink_to(self.archive)
        with self.assertRaisesRegex(bootstrap.ResourceError, "unsupported file type"):
            bootstrap.verify_output(self.output, self.lock)

    def test_invalid_lock_paths_or_duplicate_output(self):
        for change in ["../escape", self.lock["files"][1]["path"]]:
            with self.subTest(change=change):
                lock = copy.deepcopy(self.lock)
                lock["files"][0]["path"] = change
                path = self.root / "lock.json"
                path.write_text(json.dumps(lock))
                with self.assertRaises(bootstrap.ResourceError):
                    bootstrap.read_lock(path)

    def test_nonpublic_or_unexpected_download_url_is_rejected(self):
        self.lock["source"]["url"] = "http://localhost/private-input"
        path = self.root / "lock.json"
        path.write_text(json.dumps(self.lock))
        with self.assertRaisesRegex(bootstrap.ResourceError, "unexpected download URL"):
            bootstrap.read_lock(path)


if __name__ == "__main__":
    unittest.main()
