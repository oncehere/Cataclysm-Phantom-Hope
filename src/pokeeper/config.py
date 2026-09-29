"""Small, versioned TOML configuration; paths are project local."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import tomllib


class KeeperError(ValueError):
    """Actionable error safe to show to an operator."""


def plural_rule(value):
    if not isinstance(value, str):
        raise KeeperError("Plural-Forms must be a string")
    normalized = re.sub(r"\s+", "", value)
    match = re.fullmatch(r"nplurals=(\d+);plural=([^;]+);?", normalized)
    if not match or not 1 <= int(match[1]) <= 20:
        raise KeeperError("invalid Plural-Forms (expected nplurals=...; plural=...;)")
    # Formula evaluation and range checks belong to GNU gettext, never eval().
    return int(match[1]), normalized.rstrip(";")


@dataclass
class Config:
    path: Path
    data: dict

    def resolve(self, key):
        return Path(os.path.abspath(self.path.parent / self.data[key]))

    @property
    def snapshots(self):
        return self.resolve("state").parent / "snapshots"

    @property
    def nplurals(self):
        return plural_rule(self.data["plural_forms"])[0]

    @property
    def sources(self):
        return [dict(s, path=Path(os.path.abspath(self.path.parent / s["path"])))
                for s in self.data.get("sources", [])]


def load_config(path):
    path = Path(os.path.abspath(path))
    _no_symlinks(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    allowed = {"version", "project", "language", "plural_forms", "template", "catalog",
               "state", "sources", "rules", "gemini"}
    if set(data) - allowed:
        raise KeeperError("unknown config keys: " + ", ".join(sorted(set(data) - allowed)))
    if data.get("version") != 1:
        raise KeeperError("config version must be 1")
    for k in ("project", "language", "plural_forms", "template", "catalog", "state"):
        if not isinstance(data.get(k), str) or not data[k]:
            raise KeeperError(f"config requires nonempty {k}")
    plural_rule(data["plural_forms"])
    names = set()
    if not isinstance(data.get("sources", []), list):
        raise KeeperError("sources must be an array of tables")
    for s in data.get("sources", []):
        if not isinstance(s, dict) or set(s) - {"name", "path", "revision"} or any(not isinstance(s.get(k), str) or not s[k] for k in ("name", "path")):
            raise KeeperError("sources require name/path and optional revision")
        if "revision" in s and not isinstance(s["revision"], str):
            raise KeeperError("source revision must be a string")
        if s["name"] in names:
            raise KeeperError("duplicate source name")
        names.add(s["name"])
    rules = data.get("rules", {})
    if not isinstance(rules, dict) or set(rules) - {"preserve_newlines", "token_patterns"}:
        raise KeeperError("unknown rules setting")
    if "preserve_newlines" in rules and not isinstance(rules["preserve_newlines"], bool):
        raise KeeperError("preserve_newlines must be true or false")
    if not isinstance(rules.get("token_patterns", []), list) or any(not isinstance(p, str) for p in rules.get("token_patterns", [])):
        raise KeeperError("token_patterns must be an array of regular expressions")
    for pattern in rules.get("token_patterns", []):
        try:
            re.compile(pattern)
        except re.error as exc:
            raise KeeperError(f"invalid token pattern: {exc}") from None
    gemini = data.get("gemini", {})
    if not isinstance(gemini, dict) or set(gemini) - {"model", "batch_size", "retries", "timeout_seconds", "prompt", "terms", "examples"}:
        raise KeeperError("unknown gemini setting (API keys belong only in the environment)")
    cfg = Config(path, data)
    paths = [cfg.resolve(k) for k in ("template", "catalog", "state")]
    paths += [s["path"] for s in cfg.sources]
    if len(paths) != len(set(paths)) or path in paths:
        raise KeeperError("config, template, catalog, state and sources must be distinct files")
    for p in [path, *paths]:
        _no_symlinks(p)
        if p.exists() and not p.is_file():
            raise KeeperError(f"input/output path is not a regular file: {p}")
        if p.exists() and any(p.samefile(other) for other in [path, *paths] if other != p and other.exists()):
            raise KeeperError("input/output files must not alias")
    reserved = [Path(str(cfg.resolve("state")) + suffix) for suffix in (".lock", ".pending")]
    for p in [path, *paths]:
        if p in reserved or p == cfg.snapshots or cfg.snapshots in p.parents:
            raise KeeperError("inputs must not overlap reserved state files or the snapshot directory")
        if any(p in other.parents or other in p.parents for other in [path, *paths] if p != other):
            raise KeeperError("input/output file paths must not overlap")
    return cfg


def _no_symlinks(path):
    for component in [*reversed(path.parents), path]:
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise KeeperError(f"symlink input/output paths are not supported: {component}")


def checked_output_path(cfg, output, inputs=()):
    """Normalize and reject output aliases of project inputs and journal files."""
    destination = Path(os.path.abspath(output))
    _no_symlinks(destination)
    protected = {cfg.path, *(cfg.resolve(k) for k in ("template", "catalog", "state")),
                 *(s["path"] for s in cfg.sources), *(Path(p) for p in inputs),
                 *(Path(str(cfg.resolve("state")) + suffix) for suffix in (".pending", ".lock"))}
    if destination == cfg.snapshots or cfg.snapshots in destination.parents:
        raise KeeperError("output must not overwrite a snapshot")
    for path in protected:
        if destination == path or destination in path.parents or path in destination.parents:
            raise KeeperError(f"output must not overwrite or overlap an input or reserved path: {path}")
        if destination.exists() and path.exists() and destination.samefile(path):
            raise KeeperError(f"output must not alias an input or reserved path: {path}")
    return destination
