"""Synthetic cases shared by optional real-provider acceptance and native replay.

No player profiles, saves or private memories are read by these cases.
"""
from copy import deepcopy
import json
import re
from cph_ai_companion.protocol import ProtocolError, task_catalog, validate_request, validate_tasks
from cph_ai_companion.runtime import build_messages, conservative_input_tokens

INPUT_LIMIT = 4096
VALIDATION_CODES = frozenset({
    "candidate_invalid", "object_required", "missing_field", "unknown_field", "array_required",
    "array_size", "string_required", "string_size", "integer_required", "integer_range",
    "number_required", "boolean_required", "invalid_enum", "invalid_json", "message_too_large",
    "duplicate_task", "invalid_quantity_mode", "incomplete_gather_position", "invalid_dependency",
    "duplicate_dependency", "context_mismatch", "unexpected_task_kind_or_count", "requirement_required",
    "requirement_mismatch", "mode_mismatch", "gather_target_mismatch", "unobserved_gather_position",
    "missing_existing_task_dependency", "duplicate_existing_task_id", "unexpected_task_dependency",
})
_PATH_FIELDS = (
    "context|world_id|branch_id|actor_id|load_epoch|request_id|event_watermark|policy_version|"
    "memory_version|game_time|mode|tasks|id|kind|args|x|y|z|item_type|count|recipe|batch|"
    "quantity_mode|requirement_id|depends_on|constraints|max_distance"
)
_SAFE_PATH = re.compile(r"\$(?:\.(?:" + _PATH_FIELDS + r")|\[[0-4]\])*\Z")


class CandidateError(ValueError):
    def __init__(self, code, path="$"):
        self.code = code if isinstance(code, str) and code in VALIDATION_CODES else "candidate_invalid"
        self.path = path if isinstance(path, str) and len(path) <= 96 and _SAFE_PATH.fullmatch(path) else "$"
        super().__init__(self.code)


def validation_diagnostics(error):
    """Copy fixed labels only, never exception text, offending keys or values."""
    safe = CandidateError(getattr(error, "code", None), getattr(error, "path", "$"))
    return {"code": safe.code, "path": safe.path}


def synthetic_cases():
    context = {"world_id": "S", "branch_id": "B", "actor_id": 7,
               "load_epoch": "L", "request_id": "R1", "event_watermark": 1,
               "policy_version": "P", "memory_version": "M", "game_time": 0}
    active = {"id": "gather-active", "kind": "gather", "state": "running",
              "reason": "executing", "progress": 1, "target": 2, "requirement_id": "q1"}
    entries = {entry["name"]: entry for entry in task_catalog()}
    definitions = [
        ("gather", "gather", "q1", "Gather 2 new rocks (acquired).", []),
        ("prefetch", "follow", "q2", "After gather-active finishes, follow me. Append one follow task depending on gather-active.", [active]),
        ("change_goal", "guard", "q3", "Change of plan: stop gathering and guard here. Prioritize one guard task now.", [active]),
    ]
    cases = []
    for index, (name, kind, requirement, message, summary) in enumerate(definitions, 1):
        observed_context = {**context, "request_id": "R" + str(index), "event_watermark": index}
        request = {"context": observed_context, "observations": {
                   "nearby": {"items": [{"item_type": "rock", "count": 3, "position": {"x": 1, "y": 0, "z": 0}}]}},
                   "events": [], "action_catalog": [], "task_catalog": [deepcopy(entries[kind])],
                   "task_summary": deepcopy(summary), "decision_reason": "player_message",
                   "decision_id": "L." + str(index), "requirement_decisions": [
                       {"requirement_id": requirement, "decision": "pending", "text": message}]}
        validate_request(request)
        expected = {"kind": kind, "requirement_id": requirement,
                    "mode": "prioritize" if name == "change_goal" else "append"}
        tasks = [{"id": name + "-candidate", "kind": kind, "args": {}, "requirement_id": requirement}]
        if kind == "gather":
            tasks[0].update(args={"item_type": "rock", "count": 2}, quantity_mode="acquired")
        if name == "prefetch":
            tasks[0]["depends_on"] = ["gather-active"]
        fixture = {"context": observed_context, "mode": expected["mode"], "tasks": tasks}
        cases.append({"name": name, "request": request, "expected": expected, "fixture": fixture})
    return cases


def prompt_config():
    # Synthetic prompt fixture, not a loaded profile or a native configure command.
    # This minimal personality prevents irrelevant social policy consuming smoke quota.
    # No autonomous work is authorized; build_messages supplies its conservative
    # allowed_tasks:[] default. Every proposed task has a player requirement.
    return {"personality": {}, "limits": {"max_input_tokens": INPUT_LIMIT, "max_steps": 5}}


def messages_for(case, correction=None):
    messages = build_messages(case["request"], {"background": "", "records": [], "revision": "M"},
                              prompt_config())
    if correction:
        source = correction if isinstance(correction, dict) else {"code": correction}
        diagnostic = validation_diagnostics(CandidateError(source.get("code"), source.get("path", "$")))
        code = diagnostic["code"]
        hints = {
            "mode_mismatch": "Use the example's mode to queue or replace work.",
            "missing_existing_task_dependency": "Depend on gather-active, exactly as shown.",
            "unexpected_task_dependency": "Remove depends_on; this case has no dependency.",
            "requirement_required": "Copy the shown requirement_id onto the task.",
            "requirement_mismatch": "Copy the shown requirement_id onto the task.",
            "missing_field": "Add the required field using the example and catalog.",
            "unknown_field": "Remove fields absent from the task schema/example.",
            "incomplete_gather_position": "Omit coordinates or provide all of x/y/z.",
        }
        example = deepcopy(case["fixture"])
        example.pop("context")  # Runtime binds omitted context from this request.
        example["tasks"][0]["id"] = "e"
        example["tasks"][0].pop("quantity_mode", None)  # acquired is the schema default.
        feedback = {"path": diagnostic["path"], "instruction": hints.get(code, "Match the example and catalog's JSON types and bounds."),
                    "example": example}
        if code == "mode_mismatch":
            feedback["expected_mode"] = case["expected"]["mode"]
            if source.get("actual_mode") in ("append", "prioritize"):
                feedback["actual_mode"] = source["actual_mode"]
        payload = json.loads(messages[-1]["content"])
        # Only this synthetic tool's known-empty optional fields and prose are
        # omitted. Keep context, requirements, permissions and full args schemas.
        for key in ("background", "memory_records", "mandatory_record_ids", "local_queries", "events"):
            if payload.get(key) in ("", []):
                payload.pop(key, None)
        if payload.get("action_catalog") == {"actions": [], "argument_schemas": {}}:
            payload.pop("action_catalog")
        for entry in payload.get("task_catalog", []):
            entry.pop("description", None)
        payload["previous_candidate_error"] = code
        payload["previous_candidate_feedback"] = feedback
        messages[-1]["content"] = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if conservative_input_tokens(messages) > INPUT_LIMIT:
        raise ValueError("input_limit_exceeded")
    return messages


def correction_for(error, raw, case):
    correction = validation_diagnostics(error)
    if correction["code"] == "mode_mismatch":
        correction["expected_mode"] = case["expected"]["mode"]
        mode = raw.get("mode", "append") if isinstance(raw, dict) else None
        if mode in ("append", "prioritize"):
            correction["actual_mode"] = mode
    return correction


def validate_candidate(raw, case):
    candidate = deepcopy(raw)
    if not isinstance(candidate, dict):
        # Preserve the production validator's rejection and fixed code.
        try:
            validate_tasks(candidate)
        except ProtocolError as error:
            raise CandidateError(error.code, error.path) from None
    context = case["request"]["context"]
    if "context" in candidate and candidate["context"] != context:
        raise CandidateError("context_mismatch", "$.context")
    # Same binding rule as runtime: omitted context is filled only from the request.
    candidate["context"] = deepcopy(context)
    try:
        validate_tasks(candidate)
    except ProtocolError as error:
        raise CandidateError(error.code, error.path) from None
    tasks = candidate["tasks"]
    expected = case["expected"]
    if len(tasks) != 1:
        raise CandidateError("unexpected_task_kind_or_count", "$.tasks")
    if tasks[0]["kind"] != expected["kind"]:
        raise CandidateError("unexpected_task_kind_or_count", "$.tasks[0].kind")
    task = tasks[0]
    if task.get("requirement_id") != expected["requirement_id"]:
        raise CandidateError("requirement_required" if "requirement_id" not in task else "requirement_mismatch",
                             "$.tasks[0].requirement_id")
    if candidate.get("mode", "append") != expected["mode"]:
        raise CandidateError("mode_mismatch", "$.mode")
    if case["name"] == "gather":
        if (task["args"].get("item_type") != "rock" or task["args"].get("count") != 2
                or task.get("quantity_mode", "acquired") != "acquired"):
            raise CandidateError("gather_target_mismatch", "$.tasks[0].args")
        if "x" in task["args"] and any(task["args"][key] != value for key, value in (("x", 1), ("y", 0), ("z", 0))):
            raise CandidateError("unobserved_gather_position", "$.tasks[0].args")
    if case["name"] == "prefetch" and task.get("depends_on") != ["gather-active"]:
        raise CandidateError("missing_existing_task_dependency", "$.tasks[0].depends_on")
    old_ids = {item["id"] for item in case["request"]["task_summary"]}
    if task["id"] in old_ids:
        raise CandidateError("duplicate_existing_task_id", "$.tasks[0].id")
    if case['name'] != 'prefetch' and task.get('depends_on'):
        raise CandidateError('unexpected_task_dependency', '$.tasks[0].depends_on')
    return candidate
