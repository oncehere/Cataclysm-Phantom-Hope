"""The checked-in wire contract, shared with the native CPH implementation."""
from __future__ import annotations

import hashlib
import json
import math
from importlib.resources import files
from typing import Any

PROTOCOL_VERSION = "1.2"
MAX_MESSAGE_BYTES = 1048576


class ProtocolError(ValueError):
    def __init__(self, code: str = "invalid_protocol_value", path: str = "$") -> None:
        self.code = code
        self.path = path
        super().__init__(code)


def _resource(name: str) -> bytes:
    return files("cph_ai_companion").joinpath("resources/protocol", name).read_bytes()


def schema_digest() -> str:
    return hashlib.sha256(_resource("protocol.json")).hexdigest()


def contract() -> dict[str, Any]:
    return json.loads(_resource("protocol.json"))


def action_catalog() -> list[dict[str, Any]]:
    return contract()["actions"]


def task_catalog() -> list[dict[str, Any]]:
    return contract()["tasks"]


def _validate(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            raise ProtocolError("object_required", path)
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise ProtocolError("missing_field", path + "." + name)
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            # Report only the trusted container path, never an unknown key.
            raise ProtocolError("unknown_field", path)
        for name, item in value.items():
            if name in properties:
                _validate(item, properties[name], path + "." + name)
    elif kind == "array":
        if not isinstance(value, list):
            raise ProtocolError("array_required", path)
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", MAX_MESSAGE_BYTES):
            raise ProtocolError("array_size", path)
        for index, item in enumerate(value):
            _validate(item, schema.get("items", {}), f"{path}[{index}]")
    elif kind == "string":
        if not isinstance(value, str) or "\x00" in value:
            raise ProtocolError("string_required", path)
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", MAX_MESSAGE_BYTES):
            raise ProtocolError("string_size", path)
    elif kind == "integer":
        if type(value) is not int:
            raise ProtocolError("integer_required", path)
        if not schema.get("minimum", -2**63) <= value <= schema.get("maximum", 2**63 - 1):
            raise ProtocolError("integer_range", path)
    elif kind == "number":
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ProtocolError("number_required", path)
    elif kind == "boolean" and type(value) is not bool:
        raise ProtocolError("boolean_required", path)
    if "enum" in schema and value not in schema["enum"]:
        raise ProtocolError("invalid_enum", path)


def validate_plan(plan: Any) -> dict[str, Any]:
    spec = contract()
    _validate(plan, spec["schemas"]["plan"])
    catalog = {entry["name"]: entry for entry in spec["actions"]}
    seen: set[str] = set()
    requirements: dict[str, set[str]] = {}
    for index, step in enumerate(plan["steps"]):
        path = f"$.steps[{index}]"
        if step["id"] in seen:
            raise ProtocolError("duplicate_step", path + ".id")
        if "from_step" in step and step["from_step"] not in seen:
            raise ProtocolError("invalid_dependency", path + ".from_step")
        seen.add(step["id"])
        requirement_id = step.get("requirement_id")
        if step["action"] == "refuse" and not requirement_id:
            raise ProtocolError("requirement_required")
        if step["action"] != "refuse" and step.get("intent") == "refuse":
            raise ProtocolError("requirement_required")
        if requirement_id:
            requirements.setdefault(requirement_id, set()).add(step["action"])
        _validate(step["args"], catalog[step["action"]]["args"], path + ".args")
        if step["action"] == "attack":
            args = step["args"]
            character = "target" in args
            monster = all(k in args for k in ("x", "y", "z", "monster_type"))
            if character == monster or (character and any(k in args for k in ("x", "y", "z", "monster_type"))):
                raise ProtocolError("invalid_attack_target")
        if step["action"] == "talk" and (("topic" in step["args"]) != ("option" in step["args"])):
            raise ProtocolError("incomplete_dialogue_option")
    if any("refuse" in actions and len(actions) > 1 for actions in requirements.values()):
        raise ProtocolError("contradictory_requirement_decision")
    if plan.get("intent") == "refuse":
        raise ProtocolError("requirement_required")
    try:
        encoded = json.dumps(plan, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError):
        raise ProtocolError("invalid_json") from None
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message_too_large")
    return plan


def validate_status_parameters(params: Any) -> dict[str, Any]:
    _validate(params, contract()["schemas"]["status_params"])
    return params


def validate_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ProtocolError("invalid_request")
    _validate(request.get("context"), contract()["schemas"]["context"], "$.context")
    if not isinstance(request.get("observations"), dict):
        raise ProtocolError("invalid_observations")
    events = request.get("events", [])
    if not isinstance(events, list) or len(events) > 256 or any(not isinstance(e, dict) for e in events):
        raise ProtocolError("invalid_events")
    if not isinstance(request.get("action_catalog", []), list):
        raise ProtocolError("invalid_action_catalog")
    if not isinstance(request.get("task_catalog", []), list):
        raise ProtocolError("invalid_task_catalog")
    return request


def validate_tasks(candidate: Any) -> dict[str, Any]:
    """Check a bounded task offer; native admission resolves durable dependencies."""
    spec = contract()
    _validate(candidate, spec["schemas"]["tasks"])
    catalog = {entry["name"]: entry for entry in spec["tasks"]}
    seen: set[str] = set()
    for index, task in enumerate(candidate["tasks"]):
        path = f"$.tasks[{index}]"
        if task["id"] in seen:
            raise ProtocolError("duplicate_task", path + ".id")
        seen.add(task["id"])
        _validate(task["args"], catalog[task["kind"]]["args"], path + ".args")
        if "quantity_mode" in task and task["kind"] != "gather":
            raise ProtocolError("invalid_quantity_mode", path + ".quantity_mode")
        if task["kind"] == "gather":
            position = {name for name in ("x", "y", "z") if name in task["args"]}
            if position and len(position) != 3:
                raise ProtocolError("incomplete_gather_position", path + ".args")
        dependencies = task.get("depends_on", [])
        if task["id"] in dependencies:
            raise ProtocolError("invalid_dependency", path + ".depends_on")
        if len(set(dependencies)) != len(dependencies):
            raise ProtocolError("duplicate_dependency", path + ".depends_on")
    try:
        encoded = json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError):
        raise ProtocolError("invalid_json") from None
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message_too_large")
    return candidate
