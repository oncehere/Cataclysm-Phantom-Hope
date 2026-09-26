#!/usr/bin/env python3
"""Exercise real Linux test-identity binaries in an isolated directory.

Path-only checks do not constitute a game launch. The lifecycle path installs
the actual build, runs its --check-mods entry, and uninstalls its manifest.
Cross-version upgrade is tested only when a real previous build is supplied.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


COMPONENT = "cph-isolation-test"
DESKTOP_ID = "org.example.cph.IsolationTest"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def enabled(value):
    return str(value).upper() in {"ON", "TRUE", "YES", "1", "Y"}


def read_cache(build):
    values = {}
    for line in (build / "CMakeCache.txt").read_text().splitlines():
        if line and not line.startswith(("#", "//")) and "=" in line:
            key, value = line.split("=", 1)
            values[key.split(":", 1)[0]] = value
    if not enabled(values.get("CPH_TEST_IDENTITY")):
        raise ValueError("requires an actual CPH_TEST_IDENTITY=ON build")
    return values


def snapshot(roots):
    result = {}
    for root in roots:
        if root.is_symlink():
            raise ValueError("protected tree contains a symlink")
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if path.is_symlink():
                raise ValueError("protected tree contains a symlink")
            if path.is_file():
                result[str(path)] = digest(path)
    return result


def expected_paths(
    mode, home, xdg_data, xdg_config, cwd, user=None, config=None, save=None
):
    if user is not None:
        user_path = Path(user)
    elif mode == "home":
        user_path = home / ("." + COMPONENT)
    elif mode == "xdg":
        user_path = Path(xdg_data or home / ".local/share") / COMPONENT
    elif mode == "portable":
        user_path = cwd / COMPONENT
    else:
        raise ValueError("unknown compiled path mode")
    if config is not None:
        config_path = Path(config)
    elif mode == "xdg":
        config_path = Path(xdg_config or home / ".config") / COMPONENT
    else:
        config_path = user_path / "config"
    return {
        "user": user_path,
        "config": config_path,
        "save": Path(save) if save else user_path / "save",
    }


def validate_manifest(build, staging, prefix):
    allowed = (staging / prefix.lstrip("/")).resolve()
    entries = (build / "install_manifest.txt").read_text().splitlines()
    if not entries:
        raise ValueError("installation produced an empty manifest")
    result = []
    for entry in entries:
        path = Path(entry)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("unsafe install manifest entry")
        staged = staging / str(path).lstrip("/")
        if not staged.resolve().is_relative_to(allowed):
            raise ValueError("install manifest escaped isolated prefix")
        result.append(staged)
    return result


def installation_scripts(build, source):
    """Record generated installers; this is not a hostile-code sandbox."""
    pending = [build / "cmake_install.cmake"]
    seen = {}
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        if not path.is_relative_to(build):
            raise ValueError(
                "generated install include escaped build directory"
            )
        text = path.read_text()
        seen[path] = digest(path)
        pending.extend(
            Path(item)
            for item in re.findall(
                r'include\("([^"\n]*/cmake_install\.cmake)"\)', text
            )
        )
    cache = read_cache(build)
    binary_dir = cache.get("CMAKE_CACHEFILE_DIR", str(build))
    if Path(binary_dir).resolve() != build:
        raise ValueError("cache points to a different build directory")
    expected = (source / "cmake_uninstall.cmake.in").read_text()
    expected = expected.replace("@CMAKE_CURRENT_BINARY_DIR@", binary_dir)
    expected = expected.replace("@CMAKE_COMMAND@", cache["CMAKE_COMMAND"])
    uninstall = build / "cmake_uninstall.cmake"
    if uninstall.read_text() != expected:
        raise ValueError("uninstall script differs from the reviewed template")
    seen[uninstall] = digest(uninstall)
    return seen


def verify_installed_resources(prefix, source):
    lock = json.loads((source / "project/assets.lock.json").read_text())
    for entry in lock["files"]:
        relative = entry["path"]
        if entry["kind"] == "gettext-mo":
            path = prefix / "share" / COMPONENT / relative
        else:
            path = (
                prefix /
                "share/doc" /
                COMPONENT /
                "translation-inputs" /
                relative
            )
        if (
            not path.is_file() or
            path.is_symlink() or
            path.stat().st_size != entry["bytes"] or
            digest(path) != entry["sha256"]
        ):
            raise ValueError("installed locked resource differs: " + relative)
    return len(lock["files"])


def verify_metadata(prefix, binary_name):
    desktop = prefix / "share/applications" / (DESKTOP_ID + ".desktop")
    values = dict(line.split("=", 1)
                  for line in desktop.read_text().splitlines()
                  if "=" in line)
    if (values.get("Name") != "CPH Isolation Test" or
            values.get("Exec") != binary_name or
            values.get("Icon") != DESKTOP_ID):
        raise ValueError("installed desktop identity mismatch")
    meta = ET.parse(prefix / "share/metainfo" /
                    (DESKTOP_ID + ".metainfo.xml")).getroot()
    if (meta.findtext("id") != DESKTOP_ID or
            meta.findtext("name") != "CPH Isolation Test" or
            meta.findtext("launchable") != DESKTOP_ID + ".desktop"):
        raise ValueError("installed AppStream identity mismatch")


def exercise(args):
    if platform.system() != "Linux":
        raise ValueError("native Linux is required")
    build = args.build_dir.resolve()
    cache = read_cache(build)
    source = Path(cache["CMAKE_HOME_DIRECTORY"]).resolve()
    if source != Path(__file__).resolve().parents[2]:
        raise ValueError("build source differs from this probe's checkout")
    work = args.work_dir.absolute()
    work.mkdir(parents=False, exist_ok=False)
    logs = work / "logs"
    logs.mkdir()
    # Preserve the real HOME value. HOME-mode diagnostics are read-only only;
    # default-HOME game startup needs a separate test user and is NOT_RUN here.
    home = Path(os.environ["HOME"])
    cwd = work / "portable-current"
    cwd.mkdir()
    prefix = work / "prefix"
    env = {
        key: os.environ[key]
        for key in [
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "LD_LIBRARY_PATH",
            "NIX_LD",
            "NIX_LD_LIBRARY_PATH",
        ]
        if key in os.environ
    }
    env.update(
        XDG_DATA_HOME=str(work / "xdg-data"),
        XDG_CONFIG_HOME=str(work / "xdg-config"),
        LOCALAPPDATA=str(work / "local-app-data"),
    )
    env.pop("DESTDIR", None)
    commands = []
    checks = []
    inputs = {
        "cmake_cache_sha256": digest(build / "CMakeCache.txt"),
        "resource_lock_sha256": digest(source / "project/assets.lock.json")
    }
    protected = [
        work / "xdg-data/cataclysm-dda",
        work / "xdg-config/cataclysm-dda",
        cwd / "save",
        cwd / "config",
        prefix / "share/cataclysm-dda",
    ]
    for tree in protected:
        tree.mkdir(parents=True, exist_ok=True)
        (tree / "ccb-preserve.sentinel").write_bytes(
            b"CCB isolation sentinel\n"
        )
    for relative in [
        "bin/cataclysm",
        "bin/cataclysm-tiles",
        "share/applications/org.cataclysmdda.CataclysmDDA.desktop",
        "share/metainfo/org.cataclysmdda.CataclysmDDA.appdata.xml",
        "share/icons/hicolor/scalable/apps/org.cataclysmdda.CataclysmDDA.svg",
    ]:
        path = prefix / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"CCB installed-file sentinel\n")
        protected.append(path)
    baseline = snapshot(set(protected))

    def run(label, command, run_env=None):
        output = logs / (label + ".log")
        with output.open("w") as stream:
            process = subprocess.run(
                [str(part) for part in command],
                cwd=cwd,
                env=run_env or env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
                check=False,
            )
        commands.append(
            {
                "label": label,
                "command": [str(x) for x in command],
                "exit_code": process.returncode,
                "log": str(output),
            }
        )
        if process.returncode:
            raise ValueError(label + " failed; see " + str(output))
        return output.read_text()

    def unchanged(label):
        current = snapshot(set(protected))
        if current != baseline:
            raise ValueError("CCB sentinel tree changed during " + label)
        checks.append({"name": label + "_ccb_sentinels", "status": "PASS"})

    def paths(binary, base, label):
        mode = (
            "xdg"
            if enabled(cache.get("USE_XDG_DIR"))
            else "home"
            if enabled(cache.get("USE_HOME_DIR"))
            else "portable"
        )
        for case in [
            "default",
            "xdg_unset",
            "xdg_empty",
            "userdir",
            "explicit_user_config_save",
        ]:
            current_env = env.copy()
            options = []
            user = config = save = None
            if case == "xdg_unset":
                current_env.pop("XDG_DATA_HOME")
                current_env.pop("XDG_CONFIG_HOME")
            elif case == "xdg_empty":
                current_env["XDG_DATA_HOME"] = ""
                current_env["XDG_CONFIG_HOME"] = ""
            if case in {"userdir", "explicit_user_config_save"}:
                user = work / "explicit user"
                options += ["--userdir", user]
            if case == "explicit_user_config_save":
                config = work / "explicit config"
                save = work / "explicit saves"
                options += ["--configdir", config, "--savedir", save]
            base_args = ["--basepath", base] if base else []
            text = run(
                label + "-paths-" + case,
                [binary, *base_args, "--dump-test-paths", *options],
                current_env,
            )
            report = json.loads(text)
            if report.get("identity") != "CPH Isolation Test":
                raise ValueError("not a real CPH test identity binary")
            if report.get("mode") != mode:
                raise ValueError("binary path mode differs from CMake cache")
            expected = expected_paths(
                mode,
                home,
                current_env.get("XDG_DATA_HOME"),
                current_env.get("XDG_CONFIG_HOME"),
                cwd,
                user,
                config,
                save,
            )
            for name, wanted in expected.items():
                actual = Path(report[name])
                if not actual.is_absolute():
                    actual = cwd / actual
                if actual.resolve() != wanted.resolve():
                    raise ValueError(case + " resolved unexpected " + name)
            if report.get("gettext_domain") != "cataclysm-dda.mo":
                raise ValueError("internal gettext domain changed")
            base_root = Path(base) if base else prefix
            data_root = (base_root / "share" / COMPONENT
                         if report.get("prefix_data") else base_root / "data")
            if Path(report["data"]).resolve() != data_root.resolve():
                raise ValueError("resolved game data path differs from prefix")
            checks.append(
                {
                    "name": label + "_paths_" + case,
                    "mode": mode,
                    "status": "PASS",
                    "actual": report,
                }
            )
        unchanged(label + "_path_resolution")

    def install(candidate, label):
        candidate_cache = read_cache(candidate)
        if (
            not enabled(candidate_cache.get("USE_PREFIX_DATA_DIR")) or
            candidate_cache.get("CMAKE_BUILD_TYPE") == "Debug"
        ):
            raise ValueError("lifecycle probe requires a release prefix build")
        if Path(candidate_cache["CMAKE_INSTALL_PREFIX"]).absolute() != prefix:
            raise ValueError(
                "configure CMAKE_INSTALL_PREFIX as work-dir/prefix"
            )
        candidate_source = Path(
            candidate_cache["CMAKE_HOME_DIRECTORY"]
        ).resolve()
        scripts = installation_scripts(candidate, candidate_source)
        run(label, [args.cmake, "--install", candidate])
        if any(digest(path) != value for path, value in scripts.items()):
            raise ValueError(
                "generated install scripts changed during install"
            )
        files = validate_manifest(candidate, Path("/"), str(prefix))
        if not files or not all(path.is_file() for path in files):
            raise ValueError("installed manifest contains missing files")
        return files

    try:
        if args.paths_only:
            if args.binary is None or args.base_dir is None:
                raise ValueError(
                    "--paths-only requires --binary and --base-dir"
                )
            paths(args.binary.resolve(), args.base_dir.resolve(), "actual")
            inputs["binary_sha256"] = digest(args.binary.resolve())
            upgrade = "NOT_RUN"
            lifecycle = "NOT_RUN"
        else:
            binary_name = COMPONENT + (
                "-tiles" if enabled(cache.get("TILES")) else ""
            )
            binary = prefix / "bin" / binary_name
            old_digest = None
            if args.previous_build_dir:
                previous = args.previous_build_dir.resolve()
                if previous == build:
                    raise ValueError("upgrade requires a distinct real build")
                install(previous, "install-previous")
                old_digest = digest(binary)
                unchanged("install_previous")
            installed = install(build, "install-current")
            inputs["binary_sha256"] = digest(binary)
            manifest_hash = digest(build / "install_manifest.txt")
            uninstall_hash = digest(build / "cmake_uninstall.cmake")
            if old_digest is not None and old_digest == digest(binary):
                raise ValueError(
                    "upgrade inputs contain identical executables"
                )
            unchanged("install_current")
            verify_metadata(prefix, binary_name)
            checks.append({"name": "installed_metadata", "status": "PASS"})
            paths(binary, None, "installed")
            resource_count = verify_installed_resources(prefix, source)
            checks.append(
                {
                    "name": "installed_locked_resources",
                    "files": resource_count,
                    "status": "PASS",
                }
            )
            run(
                "actual-core-startup",
                [
                    binary,
                    "--userdir",
                    work / "game-user",
                    "--configdir",
                    work / "game-config",
                    "--savedir",
                    work / "game-save",
                    "--check-mods",
                    "ccb",
                ],
            )
            unchanged("actual_core_startup")
            if (
                digest(build / "install_manifest.txt") != manifest_hash or
                digest(build / "cmake_uninstall.cmake") != uninstall_hash or
                validate_manifest(build, Path("/"), str(prefix)) !=
                installed
            ):
                raise ValueError("uninstall inputs changed after installation")
            run(
                "uninstall",
                [args.cmake, "-P", build / "cmake_uninstall.cmake"],
            )
            if any(path.exists() for path in installed):
                raise ValueError(
                    "installed package file remains after uninstall"
                )
            unchanged("uninstall")
            lifecycle = "PASS"
            upgrade = "PASS" if old_digest is not None else "NOT_RUN"
        result = {
            "status": "PASS",
            "platform": platform.platform(),
            "path_checks": checks,
            "lifecycle": lifecycle,
            "distinct_build_upgrade": upgrade,
            "cross_version_upgrade": "NOT_RUN",
            "inputs": inputs,
            "commands": commands,
            "default_home_startup": "NOT_RUN",
            "public_release_ready": False,
            "limitations": (
                "Path diagnostics and core-data startup do not prove GUI "
                "gameplay. Other platforms are NOT_RUN."
            ),
        }
        (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        result = {
            "status": "FAIL",
            "error": str(error),
            "commands": commands,
            "checks": checks,
            "public_release_ready": False,
        }
        (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--previous-build-dir", type=Path)
    parser.add_argument("--paths-only", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--base-dir", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(exercise(args), indent=2))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
