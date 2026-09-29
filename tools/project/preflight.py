#!/usr/bin/env python3
"""Read-only E0 history/environment probe; JSON stdout, no fetch or writes."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


SOURCES = {
    "cdda": ("CleverRaven/Cataclysm-DDA", "upstream"),
    "ccb": ("CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb", "ccb"),
}
SAFE_GIT_ENV = {
    "GIT_OPTIONAL_LOCKS",
    "GIT_NO_LAZY_FETCH",
    "GIT_TERMINAL_PROMPT",
    "GIT_PAGER",
}
ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}
PATHS = ["--", ".", ":(top,exclude)obj-lua", ":(top,exclude)obj-lua/**"]


def rejected_git_environment(environment):
    """Accept inherited isolation, not arbitrary Git configuration overrides.

    Callers still discard every inherited GIT_* variable and set their own
    fixed Git environment. Return names only, never potentially secret values.
    """
    return sorted(
        name for name, value in environment.items()
        if name.startswith("GIT_") and name not in SAFE_GIT_ENV and not (
            name in ISOLATED_GIT_ENV and value == ISOLATED_GIT_ENV[name]
        )
    )


def redact(value):
    """Remove URL credentials and query/fragment values from evidence."""
    value = re.sub(
        r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s@]+@", r"\1[REDACTED]@", value
    )
    value = re.sub(r"(https?://[^\s?#]+)[?#][^\s]*", r"\1?[REDACTED]", value)
    return re.sub(r"(?<![\w/])[^\s/:@]+@([^\s:]+:)", r"[REDACTED]@\1", value)


def github_repository(url):
    if url.startswith("git@github.com:"):
        return url[len("git@github.com:"):].removesuffix(".git")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme not in ("https", "ssh") or
        parsed.hostname != "github.com" or
        parsed.password or
        parsed.query or
        parsed.fragment or
        parsed.username not in (None, "git") or
        parsed.port
    ):
        return None
    return parsed.path.strip("/").removesuffix(".git")


def read_lock(path):
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1:
        raise ValueError("unsupported lock schema")
    for name, (repository, remote) in SOURCES.items():
        item = lock[name]
        if item["repository"] != repository or item["remote"] != remote:
            raise ValueError(
                "upstream identity differs from the execution specification"
            )
        for key in ("commit", "tree"):
            if not re.fullmatch(r"[0-9a-f]{40}", item[key]):
                raise ValueError("expected a full SHA-1 object ID")
    if lock["ccb"]["ref"] != "refs/heads/master":
        raise ValueError("unexpected CCB branch")
    return lock


class Probe:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        self.report = {
            "schema_version": 1,
            "platform": platform.platform(),
            "repository_root": str(self.repo),
            "checks": [],
            "commands": [],
        }
        self.env = {
            k: v for k, v in os.environ.items() if not k.startswith("GIT_")
        }
        self.env.update(
            GIT_OPTIONAL_LOCKS="0",
            GIT_NO_LAZY_FETCH="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_PAGER="cat",
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            LC_ALL="C",
        )

    def check(self, name, ok, detail, scope="local"):
        self.report["checks"].append(
            {
                "id": name,
                "scope": scope,
                "status": "PASS" if ok else "FAIL",
                "detail": detail,
            }
        )

    def state(self, name, status, detail, scope="remote"):
        self.report["checks"].append(
            {"id": name, "scope": scope, "status": status, "detail": detail}
        )

    def git(self, *args):
        argv = [
            "git",
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-C",
            str(self.repo),
            *args,
        ]
        result = subprocess.run(
            argv, env=self.env, capture_output=True, timeout=120
        )
        self.report["commands"].append(
            {"argv": argv, "exit_code": result.returncode}
        )
        return result.returncode, result.stdout.decode(
            "utf-8", errors="replace"
        ).strip()

    def run(self, lock, target=None, online=False):
        unexpected = rejected_git_environment(os.environ)
        self.check(
            "git_environment",
            not unexpected,
            {
                "rejected_variable_names": unexpected,
                "values": "never recorded",
            },
        )
        if unexpected:
            return self.finish()
        if not self.repo.is_dir():
            self.check("repository_root", False, "directory does not exist")
            return self.finish()
        code, root = self.git("rev-parse", "--show-toplevel")
        self.check(
            "repository_root",
            code == 0 and Path(root).resolve() == self.repo,
            "explicit --repo must be the Git working-tree root",
        )
        if code or Path(root).resolve() != self.repo:
            return self.finish()
        code, shallow = self.git("rev-parse", "--is-shallow-repository")
        self.check("full_history", code == 0 and shallow == "false", shallow)
        code, replacements = self.git(
            "for-each-ref", "--format=%(refname)", "refs/replace/"
        )
        self.check(
            "no_replace_refs",
            code == 0 and not replacements,
            "replacement refs present"
            if replacements
            else "no replacement refs",
        )
        code, git_dir = self.git("rev-parse", "--git-common-dir")
        common = (self.repo / git_dir).resolve()
        graft = common / "info/grafts"
        self.check(
            "no_grafts",
            code == 0 and not graft.exists(),
            "legacy graft file present"
            if graft.exists()
            else "no legacy graft file",
        )
        if any(c["status"] == "FAIL" for c in self.report["checks"]):
            return self.finish()
        for name in SOURCES:
            item = lock[name]
            code, _ = self.git("cat-file", "-e", item["commit"] + "^{commit}")
            self.check(name + "_commit", code == 0, item["commit"])
            code, tree = self.git("rev-parse", item["commit"] + "^{tree}")
            self.check(
                name + "_tree",
                code == 0 and tree == item["tree"],
                {
                    "expected": item["tree"],
                    "actual": tree if code == 0 else None,
                },
            )
        code, _ = self.git(
            "merge-base",
            "--is-ancestor",
            lock["cdda"]["commit"],
            lock["ccb"]["commit"],
        )
        self.check(
            "cdda_is_ccb_ancestor", code == 0, "original B-to-U history"
        )
        code, _ = self.git(
            "merge-base", "--is-ancestor", lock["ccb"]["commit"], "HEAD"
        )
        self.check("head_contains_baseline", code == 0, "HEAD must retain U")
        code, head = self.git("rev-parse", "HEAD")
        self.report["head"] = head if code == 0 else None
        code, branch = self.git("symbolic-ref", "--quiet", "--short", "HEAD")
        self.report["branch"] = branch if code == 0 else None
        index_code, entries = self.git("ls-files", "-v", "-z", *PATHS)
        # Git status deliberately omits edits hidden by these index flags.
        hidden_entries = [
            entry for entry in entries.split("\0")
            if entry and (entry[0].islower() or entry[0] == "S")
        ]
        code, status = self.git(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", *PATHS
        )
        self.check(
            "clean_worktree",
            index_code == 0 and not hidden_entries and
            code == 0 and not status,
            {
                "entries": status.split("\0") if status else [],
                "hidden_index_entries": hidden_entries,
                "rejected_index_flags": ["assume-unchanged", "skip-worktree"],
                "excluded_without_traversal": "obj-lua/",
            },
        )
        self.remotes(lock, target)
        self.environment()
        if online:
            for name in SOURCES:
                item = lock[name]
                repository, commit = item["repository"], item["commit"]
                data = self.api(
                    f"/repos/{repository}/git/commits/{commit}",
                    name + "_github",
                )
                if data is not None:
                    self.check(
                        name + "_github_object",
                        data.get("sha") == item["commit"] and
                        data.get("tree", {}).get("sha") == item["tree"],
                        {
                            "commit": data.get("sha"),
                            "tree": data.get("tree", {}).get("sha"),
                        },
                        "remote",
                    )
        else:
            self.state(
                "github_source_objects",
                "NOT_RUN",
                "pass --github for anonymous read-only API probes",
            )
        if not target:
            self.state(
                "target_fork",
                "BLOCKED",
                "TARGET_REPOSITORY is unspecified; remote writes blocked",
            )
        elif online:
            data = self.api("/repos/" + target, "target_github")
            if data is not None:
                parent = data.get("parent", {}).get("full_name")
                self.check(
                    "target_fork",
                    data.get("fork") is True and
                    parent == SOURCES["cdda"][0] and
                    data.get("owner", {}).get("type") == "User" and
                    data.get("full_name", "").lower() == target.lower(),
                    {
                        "full_name": data.get("full_name"),
                        "fork": data.get("fork"),
                        "parent": parent,
                        "owner_type": data.get("owner", {}).get("type"),
                    },
                    "remote",
                )
        else:
            self.state(
                "target_fork",
                "NOT_RUN",
                "pass --github to inspect actual GitHub parent metadata",
            )
        self.state(
            "remote_write_authorization",
            "BLOCKED",
            "this read-only probe does not establish write authorization",
        )
        return self.finish()

    def remotes(self, lock, target):
        code, names = self.git("remote")
        actual = {}
        valid = code == 0
        expected = {
            item["remote"]: item["repository"]
            for item in (lock["cdda"], lock["ccb"])
        }
        if target:
            expected["origin"] = target
        for name in names.splitlines():
            fetch_code, fetch = self.git("remote", "get-url", "--all", name)
            push_code, push = self.git(
                "remote", "get-url", "--push", "--all", name
            )
            urls = fetch.splitlines()
            actual[name] = {
                "fetch": [redact(u) for u in urls],
                "push": [redact(u) for u in push.splitlines()],
            }
            valid = valid and fetch_code == 0 and push_code == 0
            if name == "source-cache":
                valid = (
                    valid and
                    len(urls) == 1 and
                    Path(urls[0]).is_absolute() and
                    "://" not in urls[0]
                )
            else:
                valid = (
                    valid and
                    name in expected and
                    len(urls) == 1 and
                    github_repository(urls[0]) == expected.get(name)
                )
            # Initialization remotes are never write destinations.
            valid = valid and push == "DISABLED"
        valid = valid and all(name in actual for name in ("upstream", "ccb"))
        self.check("fixed_read_only_remotes", valid, actual)

    def environment(self):
        disk = shutil.disk_usage(self.repo)
        self.report["disk"] = {
            "total_bytes": disk.total,
            "free_bytes": disk.free,
        }
        self.report["tools"] = {}
        for name in (
            "git",
            "python3",
            "cmake",
            "ninja",
            "make",
            "clang++",
            "g++",
            "msgfmt",
            "java",
            "adb",
        ):
            path = shutil.which(name)
            item = {"path": path, "status": "NOT_RUN"}
            if path:
                argv = [path, "-version" if name == "java" else "--version"]
                try:
                    result = subprocess.run(
                        argv, capture_output=True, timeout=10, env=self.env
                    )
                    lines = (
                        (result.stdout + result.stderr)
                        .decode("utf-8", errors="replace")
                        .splitlines()
                    )
                    item.update(
                        exit_code=result.returncode,
                        version=redact(lines[0]) if lines else "",
                        status="PASS" if result.returncode == 0 else "FAIL",
                    )
                    self.report["commands"].append(
                        {"argv": argv, "exit_code": result.returncode}
                    )
                except (OSError, subprocess.TimeoutExpired):
                    item.update(
                        status="FAIL",
                        detail="tool execution failed or timed out",
                    )
            self.report["tools"][name] = item
        self.report["sdk_environment"] = {
            key: {
                "configured": bool(os.environ.get(key)),
                "directory_exists": Path(os.environ[key]).is_dir()
                if os.environ.get(key)
                else False,
            }
            for key in (
                "ANDROID_HOME",
                "ANDROID_SDK_ROOT",
                "ANDROID_NDK_HOME",
                "SDKROOT",
            )
        }
        self.state(
            "platform_builds",
            "NOT_RUN",
            "availability/version probes are not game or platform acceptance",
            "environment",
        )

    def api(self, path, name):
        url = "https://api.github.com" + path
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CPH-read-only-preflight",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read(2_000_001))
            self.check(name, True, {"url": url, "http_status": 200}, "remote")
            return data
        except (urllib.error.URLError, ValueError, TimeoutError) as error:
            self.check(
                name,
                False,
                {
                    "url": url,
                    "error_type": type(error).__name__,
                    "http_status": getattr(error, "code", None),
                },
                "remote",
            )
            return None

    def finish(self):
        ok = all(
            c["status"] != "FAIL"
            for c in self.report["checks"]
            if c["scope"] == "local"
        )
        self.report["local_status"] = "PASS" if ok else "FAIL"
        self.report["remote_operations"] = "BLOCKED"
        return self.report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        help="explicit isolated Git working-tree root",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).resolve().parents[2] /
        "project/upstreams.lock.json",
    )
    parser.add_argument(
        "--target", help="explicit authorized OWNER/REPO; never inferred"
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="read public GitHub API without credentials",
    )
    args = parser.parse_args(argv)
    if args.target and (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.target) or
        args.target.lower() in {v[0].lower() for v in SOURCES.values()}
    ):
        parser.error("--target must name a distinct project repository")
    try:
        lock = read_lock(args.lock)
        report = Probe(args.repo).run(lock, args.target, args.github)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.TimeoutExpired,
    ) as error:
        report = {
            "local_status": "FAIL",
            "remote_operations": "BLOCKED",
            "error_type": type(error).__name__,
            "detail": "preflight could not complete; no writes attempted",
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["local_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
