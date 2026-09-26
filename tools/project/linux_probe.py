#!/usr/bin/env python3
"""Run the inherited Linux graphical build and E1 tests; never publish."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


TESTS = (
    ("translations", "[translations]~[.]"),
    ("chinese-runtime", "TranslationPluralRulesEvaluatorPerformance"),
    ("horde-map", "horde_map_*"),
    ("lua-callback", (
        "lua_platform_callback_errors_name_the_trigger_and_continue_dispatch"
    )),
    ("lua-task", (
        "lua_platform_task_failure_message_identifies_the_scheduled_instance"
    )),
)
OPTIONS = {
    "TILES": True, "SOUND": True, "LOCALIZE": True, "USE_SDL3": True,
    "CATA_ENABLE_LUA_PLATFORM": True, "TESTS": True, "BUILD_TESTING": True,
    "CURSES": False, "USE_PREFIX_DATA_DIR": False, "USE_XDG_DIR": False,
    "CPH_TEST_IDENTITY": False,
}
BUILD_SETTINGS = {
    "CMAKE_BUILD_TYPE": "RelWithDebInfo",
    "CMAKE_CXX_FLAGS_RELWITHDEBINFO": "-O1 -g0 -DNDEBUG",
    "CMAKE_C_FLAGS_RELWITHDEBINFO": "-O1 -g0 -DNDEBUG",
}
BINARIES = ("src/cataclysm-tiles", "tests/cata_test-tiles")
BUILD_MANIFEST = "cph-probe-build.json"
SAFE_GIT_ENV = {
    "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH",
    "GIT_TERMINAL_PROMPT", "GIT_PAGER",
}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def environment(evidence):
    if not os.environ.get("HOME"):
        raise ValueError(
            "HOME is required; preserve the existing value with "
            "nix develop --keep HOME (do not replace HOME)"
        )
    unexpected = sorted(
        key for key in os.environ
        if key.startswith("GIT_") and key not in SAFE_GIT_ENV
    )
    if unexpected:
        raise ValueError(
            "refusing Git environment overrides: " + ", ".join(unexpected)
        )
    # Retain the actual compiler toolchain and HOME, but not credentials.
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_") and not any(
            word in key.upper() for word in (
                "TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY", "KEYSTORE",
                "CREDENTIAL", "ACCESS_KEY", "SIGNING", "SSH_AUTH",
            )
        )
    }
    env.update(
        LC_ALL="C.UTF-8", LANG="C.UTF-8", GIT_OPTIONAL_LOCKS="0",
        GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat",
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
    )
    for name in ("DATA", "CONFIG", "CACHE"):
        path = evidence / ("xdg-" + name.lower())
        path.mkdir()
        env["XDG_" + name + "_HOME"] = str(path)
    return env


def git(source, env, *args):
    result = subprocess.run(
        ["git", "--no-replace-objects", "-c", "core.fsmonitor=false",
         "-c", "core.untrackedCache=false", "-c",
         "core.hooksPath=" + os.devnull, "-c", "protocol.allow=never",
         "-C", str(source), *args],
        env=env, capture_output=True, check=False, timeout=120,
    )
    if result.returncode:
        raise RuntimeError(
            f"git {args[0]} failed with exit code {result.returncode}"
        )
    return result.stdout.decode("utf-8").strip()


def regular_file(root, relative):
    path = root
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("symlink input is not accepted: " + str(relative))
    if not path.is_file():
        raise ValueError("missing regular file: " + str(relative))
    return path


def mo_inputs(source):
    lock_path = regular_file(source, "project/assets.lock.json")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if not isinstance(lock, dict) or not isinstance(lock.get("files"), list):
        raise ValueError("invalid assets lock file inventory")
    inputs = []
    paths = set()
    locales = set()
    for entry in lock["files"]:
        if not isinstance(entry, dict):
            raise ValueError("invalid asset entry")
        if entry.get("kind") != "gettext-mo":
            continue
        name = entry.get("path", "")
        locale = entry.get("locale")
        if not isinstance(name, str) or not isinstance(locale, str):
            raise ValueError("invalid MO path or locale in assets lock")
        relative = PurePosixPath(name)
        if (
            relative.is_absolute() or ".." in relative.parts or
            "\\" in name or relative.parts != (
                "lang", "mo", locale, "LC_MESSAGES", "cataclysm-dda.mo"
            ) or name in paths
        ):
            raise ValueError("unsafe or duplicate MO path in assets lock")
        path = regular_file(source, name)
        size = path.stat().st_size
        sha256 = digest(path)
        if size != entry.get("bytes") or sha256 != entry.get("sha256"):
            raise ValueError("MO input differs from assets lock: " + name)
        paths.add(name)
        locales.add(locale)
        inputs.append({"path": name, "bytes": size, "sha256": sha256})
    required = lock.get("required_locales")
    if (
        not inputs or not isinstance(required, list) or not required or
        not all(isinstance(item, str) for item in required) or
        not set(required).issubset(locales)
    ):
        raise ValueError("missing locked MO inputs or required locales")
    # This is the explicitly locked runtime resource directory, not a cache.
    actual = set()
    for path in (source / "lang/mo").rglob("*"):
        if path.is_symlink():
            raise ValueError("symlink in runtime MO directory")
        if path.suffix == ".mo":
            actual.add(path.relative_to(source).as_posix())
    if actual != paths:
        raise ValueError("runtime MO inventory differs from assets lock")
    return {
        "assets_lock_sha256": digest(lock_path),
        "mo_inputs": sorted(inputs, key=lambda item: item["path"]),
    }


def source_state(source, env):
    root = Path(git(source, env, "rev-parse", "--show-toplevel"))
    if root.resolve() != source.resolve():
        raise ValueError("--source must name the Git repository root")
    replacements = git(
        source, env, "for-each-ref", "--format=%(refname)", "refs/replace/"
    )
    if replacements:
        raise ValueError("replacement refs are not accepted")
    common = source / git(source, env, "rev-parse", "--git-common-dir")
    grafts = common / "info/grafts"
    if grafts.exists() or grafts.is_symlink():
        raise ValueError("legacy graft file is not accepted")
    flags = git(
        source, env, "ls-files", "-v", "-z", "--", ".", ":(exclude)obj-lua"
    )
    if any(
        entry and (entry[0].islower() or entry[0] == "S")
        for entry in flags.split("\0")
    ):
        raise ValueError(
            "assume-unchanged or skip-worktree source is rejected"
        )
    status = git(
        source, env, "status", "--porcelain=v1", "--untracked-files=all",
        "--", ".", ":(exclude)obj-lua",
    )
    if status:
        raise ValueError("source must be clean, including untracked files")
    return {
        "directory": str(source.resolve()),
        "head": git(source, env, "rev-parse", "HEAD"),
        "committed_tree": git(source, env, "rev-parse", "HEAD^{tree}"),
        "clean": True,
        **mo_inputs(source),
    }


def unchanged(source, env, expected):
    actual = source_state(source, env)
    if actual != expected:
        raise ValueError("source or locked MO inputs changed during probe")
    return actual


def check_cache(source, build):
    path = regular_file(build, "CMakeCache.txt")
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith(("#", "//")):
            continue
        key, separator, value = line.partition("=")
        if separator:
            entries[key.partition(":")[0]] = value
    home = entries.get("CMAKE_HOME_DIRECTORY")
    if not home or Path(home).resolve() != source.resolve():
        raise ValueError("CMake cache belongs to a different source directory")
    for name, expected in OPTIONS.items():
        value = entries.get(name, "MISSING").upper()
        accepted = {"1", "ON", "YES", "TRUE", "Y"} if expected else {
            "0", "OFF", "NO", "FALSE", "N", ""
        }
        if value not in accepted:
            raise ValueError("CMake cache has missing or incorrect " + name)
    for name, expected in BUILD_SETTINGS.items():
        if entries.get(name) != expected:
            raise ValueError("CMake cache has missing or incorrect " + name)
    toolchain = dict(BUILD_SETTINGS)
    for name in ("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER"):
        if not entries.get(name):
            raise ValueError("CMake cache has no " + name)
        toolchain[name] = entries[name]
    return {
        "source_directory": str(source.resolve()),
        "options": OPTIONS,
        "toolchain": toolchain,
        "sha256": digest(path),
    }


def binary_inputs(build):
    inputs = []
    for name in BINARIES:
        path = regular_file(build, name)
        if not os.access(path, os.X_OK):
            raise ValueError("binary is not executable: " + name)
        inputs.append({
            "path": name, "bytes": path.stat().st_size,
            "sha256": digest(path),
        })
    return inputs


def check_build_manifest(source, build, expected):
    path = regular_file(build, BUILD_MANIFEST)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict) or
        manifest.get("schema_version") != 1 or
        manifest.get("kind") != "cph-linux-e1-build" or
        manifest.get("build_directory") != str(build.resolve()) or
        manifest.get("source_state") != expected or
        manifest.get("cache") != check_cache(source, build) or
        manifest.get("binaries") != binary_inputs(build)
    ):
        raise ValueError("missing, stale or mismatched build evidence")
    command = manifest.get("build_command", {})
    if (
        not isinstance(command, dict) or command.get("exit_code") != 0 or
        command.get("status") != "PASS" or
        not isinstance(command.get("log"), str) or
        digest(Path(command["log"])) != command.get("log_sha256")
    ):
        raise ValueError("successful build command evidence is missing")
    return manifest


def check_junit(path):
    """Catch2's JUnit 'tests' count is assertions, not just case names."""
    root = ET.parse(path).getroot()
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("not a JUnit test report")
    cases = list(root.iter("testcase"))
    suites = list(root.iter("testsuite"))
    if not cases or not suites:
        raise ValueError("zero executed test cases")
    assertions = 0
    contained_cases = 0
    for element in root.iter():
        if element.tag in ("failure", "error", "skipped"):
            raise ValueError("test report contains " + element.tag)
        if element.tag in ("testsuite", "testsuites"):
            for field in ("failures", "errors", "skipped", "disabled"):
                if int(element.get(field, "0")) != 0:
                    raise ValueError("nonzero " + field + " in test report")
        if element.tag == "testsuite":
            count = int(element.get("tests", "0"))
            direct_cases = len(element.findall("testcase"))
            if count <= 0 or direct_cases == 0:
                raise ValueError("zero executed cases or assertions in suite")
            assertions += count
            contained_cases += direct_cases
    if contained_cases != len(cases):
        raise ValueError("test case outside an assertion-bearing suite")
    if root.tag == "testsuites" and "tests" in root.attrib:
        if int(root.attrib["tests"]) != assertions:
            raise ValueError("inconsistent aggregate assertion count")
    return {"test_cases": len(cases), "assertions": assertions}


def run_command(argv, cwd, evidence, name, env):
    start = time.time()
    log = evidence / (name + ".log")
    error = None
    code = None
    with log.open("xb") as stream:
        try:
            result = subprocess.run(
                argv, cwd=cwd, env=env, stdout=stream,
                stderr=subprocess.STDOUT, check=False,
            )
            code = result.returncode
        except OSError as failure:
            error = type(failure).__name__ + ": " + str(failure)
            stream.write((error + "\n").encode("utf-8"))
    record = {
        "argv": [str(item) for item in argv], "cwd": str(cwd),
        "platform": platform.platform(), "exit_code": code,
        "status": "PASS" if code == 0 else "FAIL",
        "elapsed_seconds": round(time.time() - start, 3),
        "log": str(log), "log_sha256": digest(log),
    }
    if error:
        record["error"] = error
    with (evidence / "commands.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if code != 0:
        raise RuntimeError(name + " failed; see " + str(log))
    return record


def preserve_old_manifest(build, evidence):
    path = build / BUILD_MANIFEST
    if path.is_symlink():
        raise ValueError("build manifest must not be a symlink")
    if path.exists():
        # Starting another build invalidates the previous success marker.
        # Retain its bytes in this attempt's new evidence directory.
        with (evidence / "previous-build-manifest.json").open("xb") as output:
            output.write(path.read_bytes())
        path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument(
        "--evidence", type=Path, required=True,
        help="new output directory for this attempt",
    )
    parser.add_argument(
        "--phase", choices=("configure", "build", "test", "all"), default="all"
    )
    parser.add_argument("--parallel", type=int, default=2)
    args = parser.parse_args(argv)
    if sys.platform != "linux" or args.parallel < 1:
        parser.error("requires native Linux and a positive parallelism limit")
    # Preserve ASCII aliases for compiler wrappers; resolve only for identity.
    source = args.source.absolute()
    build = args.build.absolute()
    evidence = args.evidence.absolute()
    if evidence.exists() or evidence.is_symlink():
        parser.error("--evidence must be new; old logs are never replaced")
    if (
        build.resolve().is_relative_to(source.resolve()) or
        evidence.resolve().is_relative_to(source.resolve())
    ):
        parser.error("build and evidence must be outside the source")
    evidence.mkdir(parents=True)
    initial = None
    results = []
    summary = {"status": "FAIL", "phase": args.phase, "checks": results}
    try:
        regular_file(source, "CMakePresets.json")
        env = environment(evidence)
        initial = source_state(source, env)
        write_json(evidence / "source-before.json", initial)
        build.mkdir(parents=True, exist_ok=True)
        if args.phase in ("configure", "all"):
            run_command(
                ["cmake", "--preset", "linux-tiles-sounds-x64", "-S",
                 str(source), "-G", "Ninja", "-B", str(build),
                 "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
                 "-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=-O1 -g0 -DNDEBUG",
                 "-DCMAKE_C_FLAGS_RELWITHDEBINFO=-O1 -g0 -DNDEBUG",
                 "-DCATA_CCACHE=OFF", *[
                     "-D" + name + "=" + ("ON" if value else "OFF")
                     for name, value in OPTIONS.items()
                 ]],
                source, evidence, "configure", env,
            )
            check_cache(source, build)
            unchanged(source, env, initial)
        if args.phase in ("build", "all"):
            check_cache(source, build)
            unchanged(source, env, initial)
            preserve_old_manifest(build, evidence)
            command = run_command(
                ["cmake", "--build", str(build), "--parallel",
                 str(args.parallel), "--target", "cataclysm-tiles",
                 "cata_test-tiles"], source, evidence, "build", env,
            )
            unchanged(source, env, initial)
            manifest = {
                "schema_version": 1, "kind": "cph-linux-e1-build",
                "build_directory": str(build.resolve()),
                "source_state": initial,
                "cache": check_cache(source, build),
                "binaries": binary_inputs(build), "build_command": command,
            }
            write_json(build / BUILD_MANIFEST, manifest)
            write_json(evidence / BUILD_MANIFEST, manifest)
        if args.phase in ("test", "all"):
            unchanged(source, env, initial)
            manifest = check_build_manifest(source, build, initial)
            write_json(evidence / "tested-build.json", manifest)
            run_command(
                [str(build / BINARIES[0]), "--version"],
                source, evidence, "game-version", env,
            )
            executable = build / BINARIES[1]
            for name, selection in TESTS:
                user = evidence / (name + "-user")
                user.mkdir()
                report = evidence / (name + ".xml")
                run_command(
                    [str(executable), selection, "--rng-seed", "4902",
                     "--order", "lex", "--user-dir", str(user),
                     "--reporter", "junit", "--out", str(report)],
                    source, evidence, name, env,
                )
                counts = check_junit(report)
                results.append({
                    "check": name, "selection": selection, **counts,
                    "status": "PASS", "report": str(report),
                    "report_sha256": digest(report),
                })
            unchanged(source, env, initial)
            check_build_manifest(source, build, initial)
        summary.update(
            status="PASS",
            scope="Linux E1 only; not a deployed gate or release acceptance",
        )
    except (OSError, RuntimeError, ValueError, ET.ParseError,
            subprocess.TimeoutExpired) as error:
        summary["error"] = str(error)
    finally:
        if initial is not None:
            try:
                after = source_state(source, env)
                write_json(evidence / "source-after.json", after)
                if after != initial:
                    raise ValueError(
                        "source or MO inputs changed during probe"
                    )
            except (OSError, RuntimeError, ValueError,
                    subprocess.TimeoutExpired) as error:
                summary["status"] = "FAIL"
                summary["source_after_error"] = str(error)
    write_json(evidence / "result.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
