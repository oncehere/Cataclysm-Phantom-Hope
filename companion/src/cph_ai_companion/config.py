"""Validated, user-editable configuration; importing this module has no I/O."""
from __future__ import annotations

import copy
import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """A configuration error whose message never includes secret values."""


def default_config() -> dict[str, Any]:
    return json.loads(files("cph_ai_companion").joinpath("resources/templates/config.json").read_text(encoding="utf-8"))


def load_config(profile: Path | str) -> dict[str, Any]:
    root = Path(profile).expanduser().resolve()
    try:
        value = json.loads((root / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError("cannot read valid profile config.json") from exc
    return validate_config(value, root)


def validate_config(value: Any, root: Path | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ConfigError("unsupported configuration schema")
    result = copy.deepcopy(value)
    defaults = default_config()
    if not isinstance(result.get("profile_id"), str) or not result["profile_id"]:
        raise ConfigError("profile_id must be a nonempty string")
    actor = result.get("actor_id")
    if actor is not None and (type(actor) is not int or actor < 0):
        raise ConfigError("actor_id must be a nonnegative integer or null")
    for section in ("llm", "limits", "personality", "memory", "paths", "binding"):
        if not isinstance(result.get(section, defaults[section]), dict):
            raise ConfigError(f"{section} must be an object")
        result[section] = {**defaults[section], **result.get(section, {})}
    limits = result["limits"]
    bounds = {"max_steps": (1, 5), "max_calls": (1, 3), "max_queries": (0, 4),
              "request_timeout": (1, 30), "episode_timeout": (1, 90), "cooldown": (1, 3600),
              "max_input_tokens": (256, 32768), "session_max_calls": (1, 10000),
              "session_max_tokens": (1024, 10000000)}
    for key, (low, high) in bounds.items():
        number = limits.get(key)
        if type(number) not in (int, float) or not low <= number <= high:
            raise ConfigError(f"limits.{key} is out of bounds")
        if (key.startswith("max_") or key.startswith("session_")) and type(number) is not int:
            raise ConfigError(f"limits.{key} must be an integer")
    if limits["episode_timeout"] < limits["request_timeout"]:
        raise ConfigError("episode_timeout must cover request_timeout")
    llm = result["llm"]
    for key in ("base_url", "model", "api_key_env"):
        if not isinstance(llm.get(key), str) or "\x00" in llm[key]:
            raise ConfigError(f"llm.{key} must be a string")
    if not llm["api_key_env"].isidentifier():
        raise ConfigError("api_key_env must name an environment variable")
    if type(llm.get("max_output_tokens")) is not int or not 1 <= llm["max_output_tokens"] <= 16384:
        raise ConfigError("max_output_tokens must be between 1 and 16384")
    if "api_key" in llm or "api_key" in result:
        raise ConfigError("use api_key_env; keys must not be stored in configuration")
    for key in ("background", "memory"):
        path = result["paths"].get(key)
        if not isinstance(path, str) or not path or "\x00" in path:
            raise ConfigError(f"paths.{key} must be a nonempty path")
        if root is not None:
            candidate = Path(path).expanduser()
            result["paths"][key] = str((candidate if candidate.is_absolute() else root / candidate).resolve())
    # Validate the complete permission tree, including disabled leaves.
    from .personality import PersonalityPolicy
    PersonalityPolicy(result["personality"])
    return result


def online_ready(config: dict[str, Any]) -> bool:
    llm = config["llm"]
    return bool(llm["base_url"] and llm["model"] and os.environ.get(llm["api_key_env"]))
