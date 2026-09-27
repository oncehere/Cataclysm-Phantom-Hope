#!/usr/bin/env python3
"""Trusted, read-only GitHub PR planning and disposable native CI execution.

Run this file from the control checkout. Candidate project code receives no
repository credentials. Reports describe focused regression and explicit
user-directory isolation, not packaging, GUI play or release acceptance.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request

import bootstrap_translations
from linux_probe import check_junit


CONTROL = Path(__file__).resolve().parents[2]
REPOSITORY = "oncehere/Cataclysm-Phantom-Hope"
SHA = re.compile(r"[0-9a-f]{40}")
SDL_REVISIONS = (
    ("SDL", "8e37db5e797b6167f3a00d697d816a684bd259c7", []),
    (
        "SDL_image",
        "bec9134a26c7d0f31b36d6083c25296e04cabff5",
        [
            "-DSDLIMAGE_VENDORED=OFF",
            "-DSDLIMAGE_DEPS_SHARED=OFF",
            "-DSDLIMAGE_STRICT=ON",
            "-DSDLIMAGE_PNG=ON",
            "-DSDLIMAGE_PNG_LIBPNG=ON",
            "-DSDLIMAGE_JPG=ON",
            "-DSDLIMAGE_AVIF=OFF",
            "-DSDLIMAGE_JXL=OFF",
            "-DSDLIMAGE_TIF=OFF",
            "-DSDLIMAGE_WEBP=OFF",
        ],
    ),
    (
        "SDL_ttf",
        "a1ce3670aec736ecbf0936c43f2f0cc53aa61e5b",
        [
            "-DSDLTTF_VENDORED=OFF",
            "-DSDLTTF_STRICT=ON",
            "-DSDLTTF_PLUTOSVG=OFF",
        ],
    ),
    (
        "SDL_mixer",
        "72a81869b45e249e8e67102db4e98dd2441f05a1",
        [
            "-DSDLMIXER_VENDORED=OFF",
            "-DSDLMIXER_DEPS_SHARED=OFF",
            "-DSDLMIXER_STRICT=ON",
            "-DSDLMIXER_FLAC=ON",
            "-DSDLMIXER_FLAC_LIBFLAC=ON",
            "-DSDLMIXER_FLAC_DRFLAC=OFF",
            "-DSDLMIXER_MP3=ON",
            "-DSDLMIXER_MP3_MPG123=ON",
            "-DSDLMIXER_MP3_DRMP3=OFF",
            "-DSDLMIXER_VORBIS_VORBISFILE=ON",
            "-DSDLMIXER_VORBIS_STB=OFF",
            "-DSDLMIXER_VORBIS_TREMOR=OFF",
            "-DSDLMIXER_WAVPACK=ON",
            "-DSDLMIXER_OPUS=OFF",
            "-DSDLMIXER_MOD=OFF",
            "-DSDLMIXER_MIDI=OFF",
            "-DSDLMIXER_GME=OFF",
        ],
    ),
)


def digest(path):
    return bootstrap_translations.sha256(path)


def write_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def require_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("expected a complete commit SHA")
    return value


def api(path):
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CPH-native-ci",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def validate_pr(pr, merge, number, base, head):
    if (
        pr["number"] != number or
        pr["state"] != "open" or
        pr["base"]["repo"]["full_name"] != REPOSITORY or
        pr["base"]["ref"] != "main" or
        pr["base"]["sha"] != base or
        pr["head"]["sha"] != head
    ):
        raise ValueError("PR state, repository, base or head changed")
    require_sha(merge["sha"])
    require_sha(merge["tree"]["sha"])
    if [item["sha"] for item in merge["parents"]] != [base, head]:
        raise ValueError("merge reference parents do not match current PR")


def plan():
    if os.environ["GITHUB_REPOSITORY"] != REPOSITORY:
        raise ValueError("wrong CI repository")
    event = os.environ["GITHUB_EVENT_NAME"]
    if event not in ("workflow_dispatch", "pull_request"):
        raise ValueError("unsupported CI event")
    if (
        event == "workflow_dispatch" and
        os.environ["GITHUB_REF"] != "refs/heads/main"
    ):
        raise ValueError("dispatch controller must come from main")
    number_text = os.environ["CPH_PR_NUMBER"]
    if not re.fullmatch(r"[1-9][0-9]*", number_text):
        raise ValueError("invalid PR number")
    number = int(number_text)
    base = require_sha(os.environ["CPH_BASE_SHA"])
    head = require_sha(os.environ["CPH_HEAD_SHA"])
    control = require_sha(os.environ["CPH_CONTROL_SHA"])
    # This also binds the selected trusted control revision to this main base.
    if control != base:
        raise ValueError("trusted control revision differs from expected main")
    pr = api("/pulls/" + str(number))
    reference = "refs/pull/" + str(number) + "/merge"
    remote = (
        subprocess.check_output(
            [
                "git",
                "ls-remote",
                "https://github.com/" + REPOSITORY + ".git",
                reference,
            ],
            env=clean_environment(),
            text=True,
            timeout=90,
        )
        .strip()
        .split()
    )
    if len(remote) != 2 or remote[1] != reference:
        raise ValueError("pull request has no unique merge reference")
    merge = api("/git/commits/" + require_sha(remote[0]))
    validate_pr(pr, merge, number, base, head)
    # Reread after resolving the merge ref; stale synthetic merges fail closed.
    validate_pr(api("/pulls/" + str(number)), merge, number, base, head)
    manifest = {
        "repository": REPOSITORY,
        "repository_id": str(os.environ["GITHUB_REPOSITORY_ID"]),
        "pr_number": number,
        "base_sha": base,
        "head_sha": head,
        "merge_sha": merge["sha"],
        "merge_tree": merge["tree"]["sha"],
        "control_sha": control,
        "event": event,
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "workflow_ref": os.environ["GITHUB_WORKFLOW_REF"],
        "policy_sha": digest(CONTROL / "project/check-policy.json"),
    }
    with Path(os.environ["GITHUB_OUTPUT"]).open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(
            "manifest=" + json.dumps(manifest, separators=(",", ":")) + "\n"
        )
        stream.write("merge_sha=" + merge["sha"] + "\n")
        stream.write("control_sha=" + control + "\n")
    print(json.dumps(manifest, indent=2))


def clean_environment():
    # Keep the selected compiler environment, but strip credentials and runner
    # command-file paths before running any candidate code.
    blocked = (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "PRIVATE_KEY",
        "KEYSTORE",
        "CREDENTIAL",
        "ACCESS_KEY",
        "SIGNING",
        "SSH_AUTH",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(word in key.upper() for word in blocked) and
        not key.startswith(("ACTIONS_", "GITHUB_", "GIT_", "CPH_"))
    }
    environment.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        VCPKG_BINARY_SOURCES="clear",
        VCPKG_DISABLE_METRICS="1",
    )
    return environment


def git(source, env, *arguments):
    return subprocess.check_output(
        [
            "git",
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-C",
            str(source),
            *arguments,
        ],
        env=env,
        text=True,
        encoding="utf-8",
    ).strip()


def verify_checkout(source, env, identity):
    expected = {
        "HEAD": identity["merge_sha"],
        "HEAD^{tree}": identity["merge_tree"],
        "HEAD^1": identity["base_sha"],
        "HEAD^2": identity["head_sha"],
    }
    for revision, value in expected.items():
        require_sha(value)
        if git(source, env, "rev-parse", revision) != value:
            raise ValueError("candidate identity mismatch: " + revision)
    if git(
        source,
        env,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "HEAD",
        "--",
        ".",
        ":(exclude)obj-lua",
    ):
        raise ValueError("tracked candidate source changed")


class Runner:
    def __init__(self, evidence, env):
        self.evidence = evidence
        self.env = env

    def run(self, name, arguments, cwd):
        log = self.evidence / (name + ".log")
        started = time.monotonic()
        argv = [str(item) for item in arguments]
        print("Running " + name, flush=True)
        with log.open("xb") as output:
            result = subprocess.run(
                argv,
                cwd=cwd,
                env=self.env,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )
        record = {
            "argv": argv,
            "cwd": str(cwd),
            "exit_code": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "log": log.name,
            "log_sha256": digest(log),
        }
        with (self.evidence / "commands.jsonl").open(
            "a", encoding="utf-8"
        ) as output:
            output.write(json.dumps(record) + "\n")
        print(json.dumps(record), flush=True)
        if result.returncode:
            print(
                log.read_text(encoding="utf-8", errors="replace")[-16000:],
                flush=True,
            )
            raise RuntimeError(
                name + " failed with exit " + str(result.returncode)
            )


def checkout_dependency(
    runner, work, name, repository, commit, *, shallow=True,
):
    source = work / name
    source.mkdir()
    runner.run(name + "-init", ["git", "init", str(source)], work)
    runner.run(
        name + "-fetch",
        [
            "git",
            "-C",
            source,
            "fetch",
            *(["--depth=1"] if shallow else []),
            "https://github.com/" + repository + ".git",
            commit,
        ],
        work,
    )
    runner.run(
        name + "-checkout",
        ["git", "-C", source, "checkout", "--detach", "FETCH_HEAD"],
        work,
    )
    if git(source, runner.env, "rev-parse", "HEAD") != commit:
        raise ValueError("dependency revision mismatch")
    return source


def dependencies(runner, work, target, parallel):
    if target["os"] == "linux":
        prefix = work / "sdl-prefix"
        runner.env.update(
            CMAKE_PREFIX_PATH=str(prefix),
            PKG_CONFIG_PATH=str(prefix / "lib/pkgconfig") + ":" +
            str(prefix / "lib/x86_64-linux-gnu/pkgconfig"),
            LD_LIBRARY_PATH=str(prefix / "lib") + ":" +
            str(prefix / "lib/x86_64-linux-gnu"),
        )
        runner.run("apt-versions", ["dpkg-query", "-W"], work)
        for name, commit, options in SDL_REVISIONS:
            source = checkout_dependency(
                runner, work, name, "libsdl-org/" + name, commit
            )
            build = work / (name + "-build")
            runner.run(
                name + "-configure",
                [
                    "cmake",
                    "-S",
                    source,
                    "-B",
                    build,
                    "-G",
                    "Ninja",
                    "-DCMAKE_BUILD_TYPE=Release",
                    "-DCMAKE_INSTALL_PREFIX=" + str(prefix),
                    "-DBUILD_SHARED_LIBS=ON",
                    *options,
                ],
                work,
            )
            runner.run(
                name + "-build",
                ["cmake", "--build", build, "--parallel", str(parallel)],
                work,
            )
            runner.run(name + "-install", ["cmake", "--install", build], work)
        return {}
    root = checkout_dependency(
        runner, work, "vcpkg", "microsoft/vcpkg", target["vcpkg_commit"],
        shallow=False,
    )
    installed = work / "vcpkg-installed"
    runner.env.update(VCPKG_ROOT=str(root), VCPKG_INSTALLATION_ROOT=str(root))
    runner.run(
        "vcpkg-bootstrap",
        ["cmd", "/c", root / "bootstrap-vcpkg.bat", "-disableMetrics"],
        work,
    )
    runner.run(
        "vcpkg-install",
        [
            root / "vcpkg.exe",
            "install",
            "--triplet=" + target["vcpkg_triplet"],
            "--x-feature=sdl2",
            "--x-manifest-root=" + str(CONTROL / "msvc-full-features"),
            "--overlay-triplets=" + str(CONTROL / ".github/vcpkg_triplets"),
            "--x-install-root=" + str(installed),
            "--clean-after-build",
        ],
        work,
    )
    return {"VCPKG_ROOT": str(root), "VCPKG_INSTALLED_DIR": str(installed)}


def configure(runner, source, build, target, dependency_paths, msgfmt):
    command = [
        "cmake",
        "--preset",
        target["preset"],
        "-S",
        source,
        "-B",
        build,
    ]
    command += ["-G", target["generator"]]
    if target["os"] == "windows":
        command += [
            "-A",
            "x64",
            "-DVCPKG_MANIFEST_FEATURES=sdl2",
            "-DGETTEXT_MSGFMT_BINARY=" + msgfmt,
            "-DGETTEXT_MSGFMT_EXECUTABLE=" + msgfmt,
            "-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO=" +
            str(build / "bin"),
        ]
        command += [
            "-D" + key + "=" + value for key, value in dependency_paths.items()
        ]
    else:
        command += [
            "-DCMAKE_BUILD_TYPE=" + target["configuration"],
            "-DCMAKE_C_FLAGS_RELWITHDEBINFO=" + target["c_flags"],
            "-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=" + target["cxx_flags"],
        ]
    command += ["-DCATA_CCACHE=OFF"]
    command += [
        "-D" + key + "=" + ("ON" if value else "OFF")
        for key, value in target["options"].items()
    ]
    runner.run("configure", command, source)
    cache = {}
    for line in (
        (build / "CMakeCache.txt").read_text(encoding="utf-8").splitlines()
    ):
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cache[key.split(":", 1)[0]] = value
    for key, value in target["options"].items():
        accepted = (
            ("ON", "TRUE", "YES", "1")
            if value
            else ("OFF", "FALSE", "NO", "0", "")
        )
        if cache.get(key, "MISSING").upper() not in accepted:
            raise ValueError(
                "configured option differs from trusted policy: " + key
            )
    if cache.get("CMAKE_GENERATOR") != target["generator"]:
        raise ValueError("incorrect CMake generator")
    if Path(cache["CMAKE_HOME_DIRECTORY"]).resolve() != source:
        raise ValueError("incorrect CMake source")
    for key in ("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER"):
        if not cache.get(key):
            raise ValueError("missing compiler in CMake cache")
    return {
        "target_id": target["target_id"],
        "preset": target["preset"],
        "generator": target["generator"],
        "configuration": target["configuration"],
        "options": target["options"],
        "cache": cache,
        "cache_sha256": digest(build / "CMakeCache.txt"),
    }


def create_sentinels(evidence):
    root = evidence / "mock-ccb"
    expected = {}
    for relative in (
        "program/ccb",
        "config/options.json",
        "save/world/player.sav",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            b"CCB isolation sentinel: " + relative.encode("ascii")
        )
        expected[relative] = digest(path)
    return root, expected


def verify_sentinels(root, expected):
    actual = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("CCB sentinel replaced with a symlink")
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = digest(path)
    if actual != expected:
        raise ValueError("mock CCB program/config/save changed")


def build(args):
    source = args.source.resolve()
    work = args.work.resolve()
    evidence = args.evidence.resolve()
    if work.exists() or evidence.exists():
        raise ValueError("work and evidence must be fresh directories")
    if work.is_relative_to(source) or evidence.is_relative_to(source):
        raise ValueError("build and evidence must be outside candidate source")
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    report = {
        "schema_version": 1,
        "kind": "cph-native-ci",
        "status": "FAIL",
        "platform": os.environ["CPH_CI_PLATFORM"],
        "tests": [],
        "checks": {},
        "isolation_scope": "explicit-userdir-sentinels",
    }
    try:
        identity = json.loads(os.environ["CPH_CI_PLAN"])
        report["identity"] = identity
        if identity["policy_sha"] != digest(
            CONTROL / "project/check-policy.json"
        ):
            raise ValueError("control policy changed")
        policy = json.loads(
            (CONTROL / "project/check-policy.json").read_text(encoding="utf-8")
        )
        target = policy["targets"][report["platform"]]
        native_os = "windows" if sys.platform == "win32" else sys.platform
        if native_os != target["os"] or platform.machine().lower() not in (
            "amd64",
            "x86_64",
        ):
            raise ValueError(
                "native operating system or architecture mismatch"
            )
        env = clean_environment()
        runner = Runner(evidence, env)
        verify_checkout(source, env, identity)
        if git(CONTROL, env, "rev-parse", "HEAD") != identity["control_sha"]:
            raise ValueError("unexpected control checkout")
        report["runner"] = {
            "os": platform.platform(),
            "arch": platform.machine(),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
        }
        runner.run("cmake-version", ["cmake", "--version"], work)
        runner.run("python-version", [sys.executable, "--version"], work)
        runner.run("git-version", ["git", "--version"], work)
        if native_os == "windows":
            # Do not prepend MSYS usr/bin to PATH: its link.exe shadows MSVC.
            msgfmt = str(
                Path(os.environ["CPH_MSYS_ROOT"]) / "usr/bin/msgfmt.exe"
            )
        else:
            msgfmt = shutil.which("msgfmt", path=env.get("PATH"))
        if not msgfmt or not Path(msgfmt).is_file():
            raise ValueError("gettext msgfmt is missing")
        runner.run("msgfmt-version", [msgfmt, "--version"], work)
        lock = bootstrap_translations.read_lock(
            CONTROL / "project/assets.lock.json"
        )
        if digest(source / "project/assets.lock.json") != digest(
            CONTROL / "project/assets.lock.json"
        ):
            raise ValueError(
                "candidate resources differ from trusted asset lock"
            )
        report["resources"] = bootstrap_translations.bootstrap(
            lock, work / "resources"
        )
        for entry in lock["files"]:
            if entry["kind"] != "gettext-mo":
                continue
            destination = source / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise ValueError(
                    "candidate already contains generated translation"
                )
            shutil.copyfile(work / "resources" / entry["path"], destination)
        (source / "data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES").mkdir(
            parents=True, exist_ok=True
        )
        dependency_paths = dependencies(runner, work, target, args.parallel)
        build_dir = work / "build"
        report["configuration"] = configure(
            runner, source, build_dir, target, dependency_paths, msgfmt
        )
        report["checks"]["configure"] = "PASS"
        runner.run(
            "build",
            [
                "cmake",
                "--build",
                build_dir,
                "--config",
                target["configuration"],
                "--parallel",
                str(args.parallel),
                "--target",
                "cataclysm-tiles",
                "cata_test-tiles",
            ],
            source,
        )
        report["checks"]["build"] = "PASS"
        binaries = []
        for relative in target["binaries"]:
            binary = build_dir / relative
            if not binary.is_file() or binary.stat().st_size <= 0:
                raise ValueError("empty or missing executable")
            binaries.append(
                {
                    "path": relative,
                    "bytes": binary.stat().st_size,
                    "sha256": digest(binary),
                }
            )
        report["binaries"] = binaries
        sentinel_root, sentinels = create_sentinels(evidence)
        for kind in ("DATA", "CONFIG", "CACHE"):
            xdg = evidence / ("xdg-" + kind.lower())
            xdg.mkdir()
            env["XDG_" + kind + "_HOME"] = str(xdg)
        version_user = evidence / "version-user"
        version_user.mkdir()
        runner.run(
            "game-version",
            [
                build_dir / binaries[0]["path"],
                "--userdir",
                version_user,
                "--version",
            ],
            source,
        )
        if (
            not (evidence / "game-version.log")
            .read_text(encoding="utf-8")
            .strip()
        ):
            raise ValueError("empty game version response")
        report["checks"]["version"] = "PASS"
        for name, selection in target["tests"].items():
            user = evidence / (name + "-user")
            user.mkdir()
            xml = evidence / (name + ".xml")
            runner.run(
                name,
                [
                    build_dir / binaries[1]["path"],
                    selection,
                    "--rng-seed",
                    "4902",
                    "--order",
                    "lex",
                    "--user-dir",
                    user,
                    "--reporter",
                    "junit",
                    "--out",
                    xml,
                ],
                source,
            )
            report["tests"].append(
                {
                    "check": name,
                    "selection": selection,
                    **check_junit(xml),
                    "status": "PASS",
                    "report": xml.name,
                    "report_sha256": digest(xml),
                }
            )
        verify_sentinels(sentinel_root, sentinels)
        report["isolation"] = {
            "status": "PASS",
            "scope": report["isolation_scope"],
            "sentinels": sentinels,
        }
        report["checks"]["isolation"] = "PASS"
        verify_checkout(source, env, identity)
        for binary in binaries:
            if digest(build_dir / binary["path"]) != binary["sha256"]:
                raise ValueError("executable changed during tests")
        for entry in lock["files"]:
            if (
                entry["kind"] == "gettext-mo" and
                digest(source / entry["path"]) != entry["sha256"]
            ):
                raise ValueError("translation changed during tests")
        if (
            digest(build_dir / "CMakeCache.txt") !=
            report["configuration"]["cache_sha256"]
        ):
            raise ValueError("CMake cache changed during tests")
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        print(report["error"], file=sys.stderr, flush=True)
    finally:
        write_json(evidence / "report.json", report)
    return 0 if report["status"] == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    native = sub.add_parser("build")
    native.add_argument("--source", type=Path, required=True)
    native.add_argument("--work", type=Path, required=True)
    native.add_argument("--evidence", type=Path, required=True)
    native.add_argument("--parallel", type=int, default=2, choices=range(1, 9))
    args = parser.parse_args(argv)
    if args.command == "plan":
        plan()
        return 0
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
