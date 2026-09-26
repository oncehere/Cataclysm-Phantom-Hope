#!/usr/bin/env python3
"""Fetch pinned compiled translations without a token or prior Actions artifacts.

Only resources listed in the lock are extracted. No archive code is executed.
This temporary MO input does not provide a maintainable PO source pipeline.
"""

import argparse
import gettext
import gzip
import hashlib
import json
import re
import shutil
import struct
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath


class ResourceError(ValueError):
    """The declared resource cannot be verified safely."""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name):
    if not name or "\\" in name or "\x00" in name or name.startswith("/"):
        raise ResourceError("unsafe archive path")
    parts = PurePosixPath(name).parts
    if ".." in parts or (parts and ":" in parts[0]):
        raise ResourceError("unsafe archive path")
    return str(PurePosixPath(name))


def read_lock(path):
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1 or lock.get("kind") != "compiled-gettext-mo":
        raise ResourceError("unsupported resource lock")
    source = lock["source"]
    if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
        raise ResourceError("invalid archive SHA256")
    expected_url = ("https://github.com/" + source["repository"] +
                    "/releases/download/" + source["release_tag"] + "/" + source["name"])
    if source["url"] != expected_url or not source["url"].startswith("https://github.com/"):
        raise ResourceError("unexpected download URL")
    paths = set()
    archive_names = set()
    for entry in lock["files"]:
        if safe_name(entry["path"]) != entry["path"] or entry["path"] == ".":
            raise ResourceError("noncanonical resource output path")
        if safe_name(entry["archive_path"]) != entry["archive_path"]:
            raise ResourceError("noncanonical archive resource path")
        if entry["path"] in paths or entry["archive_path"] in archive_names:
            raise ResourceError("duplicate locked resource")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) or entry["bytes"] <= 0:
            raise ResourceError("invalid resource digest or size")
        paths.add(entry["path"])
        archive_names.add(entry["archive_path"])
    if not paths or not lock["required_locales"]:
        raise ResourceError("empty resource or required locale list")
    return lock


def verify_archive(path, lock):
    if not path.is_file() or path.is_symlink():
        raise ResourceError("archive must be a regular file")
    if path.stat().st_size != lock["source"]["bytes"]:
        raise ResourceError("archive byte size mismatch")
    if sha256(path) != lock["source"]["sha256"]:
        raise ResourceError("archive SHA256 mismatch")


def download_archive(path, lock):
    request = urllib.request.Request(lock["source"]["url"],
                                     headers={"User-Agent": "CPH-translation-bootstrap/1"})
    expected = lock["source"]["bytes"]
    downloaded = 0
    # urllib does not read GH_TOKEN, GITHUB_TOKEN, TX_TOKEN or Actions caches.
    with urllib.request.urlopen(request, timeout=120) as response, path.open("xb") as out:
        if not response.geturl().startswith("https://"):
            raise ResourceError("download redirected away from HTTPS")
        while chunk := response.read(1024 * 1024):
            downloaded += len(chunk)
            if downloaded > expected:
                raise ResourceError("download exceeds locked archive size")
            out.write(chunk)
    verify_archive(path, lock)


class BoundedReader:
    """Limit total decompression, including ignored archive members and padding."""

    def __init__(self, stream, limit):
        self.stream = stream
        self.remaining = limit

    def read(self, size=-1):
        size = min(size, self.remaining + 1) if size >= 0 else self.remaining + 1
        value = self.stream.read(size)
        self.remaining -= len(value)
        if self.remaining < 0:
            raise ResourceError("archive exceeds decompression limit")
        return value


def extract_verified(archive, destination, lock):
    # Digest verification always precedes opening the untrusted tar payload.
    verify_archive(archive, lock)
    limits = lock["limits"]
    wanted = {entry["archive_path"]: entry for entry in lock["files"]}
    seen = set()
    found = set()
    with gzip.open(archive, "rb") as compressed:
        bounded = BoundedReader(compressed, limits["uncompressed_bytes"])
        with tarfile.open(fileobj=bounded, mode="r|") as bundle:
            for member in bundle:
                name = safe_name(member.name)
                if name in seen:
                    raise ResourceError("duplicate archive member: " + name)
                seen.add(name)
                if len(seen) > limits["members"]:
                    raise ResourceError("archive member limit exceeded")
                if member.issym() and name not in wanted:
                    # A pinned upstream documentation link is inert input only.
                    # It is never extracted, followed or allowed to alias an output.
                    ignored = lock.get("ignored_symlinks", {})
                    if name in ignored and member.linkname == ignored[name]:
                        continue
                if not (member.isfile() or member.isdir()) or member.issparse():
                    raise ResourceError("unsupported archive member type: " + name)
                if member.size < 0 or member.size > limits["member_bytes"]:
                    raise ResourceError("archive member size limit exceeded")
                if name not in wanted:
                    continue
                entry = wanted[name]
                if not member.isfile() or member.size != entry["bytes"]:
                    raise ResourceError("locked resource size/type mismatch: " + name)
                target = destination / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise ResourceError("missing resource payload: " + name)
                with source, target.open("xb") as out:
                    shutil.copyfileobj(source, out, 1024 * 1024)
                if sha256(target) != entry["sha256"]:
                    raise ResourceError("resource SHA256 mismatch: " + name)
                found.add(name)
    if found != set(wanted):
        raise ResourceError("archive is missing locked resources")


def verify_output(output, lock):
    if output.is_symlink() or not output.is_dir():
        raise ResourceError("resource output must be an existing regular directory")
    actual_files = set()
    for path in output.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ResourceError("resource output contains an unsupported file type")
        if path.is_file():
            actual_files.add(path.relative_to(output).as_posix())
    if actual_files != {entry["path"] for entry in lock["files"]}:
        raise ResourceError("resource output file inventory differs from lock")
    catalogs = []
    locales = set()
    for entry in lock["files"]:
        relative = Path(entry["path"])
        if any((output / parent).is_symlink() for parent in [relative, *relative.parents]):
            raise ResourceError("resource output contains a symbolic link")
        path = output / relative
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ResourceError("resource missing or wrong size: " + entry["path"])
        if sha256(path) != entry["sha256"]:
            raise ResourceError("resource SHA256 mismatch: " + entry["path"])
        if entry["kind"] != "gettext-mo":
            continue
        with path.open("rb") as stream:
            catalog = gettext.GNUTranslations(stream)
        entries = sum(1 for key, value in catalog._catalog.items() if key and value)
        if entries == 0 and entry["locale"] in lock["required_locales"]:
            raise ResourceError("empty compiled translation: " + entry["path"])
        locale = entry["locale"]
        locales.add(locale)
        catalogs.append({"locale": locale, "entries": entries, "sha256": entry["sha256"]})
    missing = set(lock["required_locales"]) - locales
    if missing:
        raise ResourceError("required locale missing: " + ", ".join(sorted(missing)))
    probe = lock["probe"]
    # A real locale lookup, without fallback, rather than just checking magic bytes.
    catalog = gettext.translation(lock["gettext_domain"], str(output / "lang/mo"),
                                  languages=[probe["locale"]], fallback=False)
    actual = catalog.gettext(probe["msgid"])
    if actual != probe["msgstr"] or actual == probe["msgid"]:
        raise ResourceError("real translated-message lookup failed")
    return {"status": "PASS", "kind": lock["kind"], "source_commit": lock["source"]["commit"],
            "archive_sha256": lock["source"]["sha256"], "gettext_domain": lock["gettext_domain"],
            "files": len(lock["files"]), "catalogs": catalogs,
            "probe": {**probe, "actual": actual},
            "limitations": "Compiled MO resources only; not a PO maintenance pipeline or game runtime test."}


def bootstrap(lock, output, archive=None):
    if output.exists() or output.is_symlink():
        raise ResourceError("output exists; use --check or choose a new isolated directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cph-translations-", dir=output.parent) as temporary:
        stage = Path(temporary) / "resources"
        stage.mkdir()
        if archive is None:
            archive = Path(temporary) / "input.tar.gz"
            download_archive(archive, lock)
        extract_verified(archive, stage, lock)
        report = verify_output(stage, lock)
        # Reserve the destination exclusively; never replace an existing directory.
        output.mkdir()
        try:
            for entry in lock["files"]:
                target = output / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                with (stage / entry["path"]).open("rb") as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
        except BaseException:
            shutil.rmtree(output)
            raise
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path,
                        default=Path(__file__).resolve().parents[2] / "project/assets.lock.json")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", type=Path, help="verify a local raw archive instead of downloading")
    parser.add_argument("--check", action="store_true", help="read-only verification; no download or writes")
    args = parser.parse_args(argv)
    try:
        lock = read_lock(args.lock)
        if args.check and args.archive:
            raise ResourceError("--check cannot be combined with --archive")
        report = verify_output(args.output, lock) if args.check else bootstrap(lock, args.output, args.archive)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, EOFError, struct.error, tarfile.TarError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
