"""Per-companion policy. Permissions never imply knowledge or action support."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


class PersonalityError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "applies_to": "bound_companion_only",
    "expression_policy": "natural_with_intent_checks",
    "traits": {"honesty": 0.45, "self_interest": 0.65, "commitment": 0.55, "caution": 0.6},
    "social_behavior": {
        "refuse": True, "argue": True, "propose_own_goals": True,
        "deception": {
            "enabled": True, "lie_in_dialogue": True, "conceal_information": True,
            "false_promise": True, "transaction_fraud": False,
        },
        "betrayal": {
            "enabled": True, "break_commitment": True, "aid_conflicting_party": True,
            "disclose_known_information": True, "leave_group": False,
            "misappropriate_items": False, "sabotage": False,
            "attack_player": False, "attack_allies": False,
        },
    },
}

BEHAVIOR_PARENTS = {
    key: parent
    for parent in ("deception", "betrayal")
    for key in DEFAULT_POLICY["social_behavior"][parent]
    if key != "enabled"
}
BEHAVIORS = frozenset({"refuse", "argue", "propose_own_goals", *BEHAVIOR_PARENTS})


class PersonalityPolicy:
    """Validate all explicit social intents; never silently shorten a plan.

    This checks structured intent, not the truth or meaning of arbitrary prose.
    The game separately checks capabilities, targets, and actual effects.
    """

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        data = deepcopy(DEFAULT_POLICY)
        config = dict(config or {})
        if type(config.get("schema_version", 1)) is not int or config.get("schema_version", 1) != 1:
            raise PersonalityError("unsupported_personality_schema")
        if config.get("applies_to", "bound_companion_only") != "bound_companion_only":
            raise PersonalityError("invalid_personality_scope")
        if config.get("expression_policy", "natural_with_intent_checks") != "natural_with_intent_checks":
            raise PersonalityError("invalid_expression_policy")
        social = config.get("social_behavior", {})
        if not isinstance(social, Mapping) or set(social) - set(data["social_behavior"]):
            raise PersonalityError("invalid_behavior_policy")
        for name, value in social.items():
            if name in ("deception", "betrayal"):
                if not isinstance(value, Mapping) or set(value) - set(data["social_behavior"][name]):
                    raise PersonalityError("invalid_behavior_policy")
                if any(type(v) is not bool for v in value.values()):
                    raise PersonalityError("invalid_behavior_policy")
                data["social_behavior"][name].update(value)
            else:
                if type(value) is not bool:
                    raise PersonalityError("invalid_behavior_policy")
                data["social_behavior"][name] = value
        traits = config.get("traits", {})
        if not isinstance(traits, Mapping) or set(traits) - set(data["traits"]):
            raise PersonalityError("invalid_traits")
        for name, value in traits.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise PersonalityError("invalid_traits")
            data["traits"][name] = value
        self._data = data

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any] | None = None) -> PersonalityPolicy:
        return cls(config)

    def allows(self, behavior: str) -> bool:
        if behavior not in BEHAVIORS:
            return False
        social = self._data["social_behavior"]
        parent = BEHAVIOR_PARENTS.get(behavior)
        if parent:
            return social[parent]["enabled"] and social[parent][behavior]
        return social[behavior]

    def effective(self) -> dict[str, bool]:
        return {name: self.allows(name) for name in sorted(BEHAVIORS)}

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)

    def validate_plan(self, steps: Sequence[Mapping[str, Any]]) -> None:
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
            raise PersonalityError("invalid_plan")
        for step in steps:
            if not isinstance(step, Mapping):
                raise PersonalityError("invalid_plan")
            intents = step.get("social_intents", [])
            if not isinstance(intents, list) or any(not isinstance(i, str) for i in intents):
                raise PersonalityError("invalid_social_intent")
            intents = list(intents)
            for field in ("intent", "behavior", "social_intent"):
                if field in step:
                    if not isinstance(step[field], str):
                        raise PersonalityError("invalid_social_intent")
                    intents.append(step[field])
            # A social action itself is also an intent; a normal action such as
            # walk/craft has no social policy entry.
            action = step.get("action", step.get("type"))
            if isinstance(action, str) and action in BEHAVIORS:
                intents.append(action)
            for intent in intents:
                if intent not in BEHAVIORS:
                    raise PersonalityError("unknown_social_intent")
                if not self.allows(intent):
                    raise PersonalityError("behavior_disabled")

    def filter_plan(self, steps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        self.validate_plan(steps)
        return deepcopy(list(steps))
