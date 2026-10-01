from copy import deepcopy
import unittest

from cph_ai_companion.personality import BEHAVIORS, DEFAULT_POLICY, PersonalityError, PersonalityPolicy


class PersonalityTests(unittest.TestCase):
    def test_all_fifteen_behaviors_have_explicit_effective_permissions(self):
        policy = PersonalityPolicy()
        self.assertEqual(len(BEHAVIORS), 15)
        self.assertEqual(set(policy.effective()), BEHAVIORS)
        allowed = {"refuse", "argue", "propose_own_goals", "lie_in_dialogue", "conceal_information",
                   "false_promise", "break_commitment", "aid_conflicting_party", "disclose_known_information"}
        self.assertEqual({name for name, enabled in policy.effective().items() if enabled}, allowed)

    def test_step_intent_is_checked_even_on_a_normal_action(self):
        policy = PersonalityPolicy()
        step = {"id": "step-1", "action": "speak", "args": {"text": "借我看看你的东西"},
                "intent": "misappropriate_items"}
        with self.assertRaisesRegex(PersonalityError, "behavior_disabled"):
            policy.validate_plan([step])
        policy.validate_plan([{**step, "intent": "argue"}])

    def test_each_permission_can_be_enabled_and_parent_disable_wins(self):
        data = deepcopy(DEFAULT_POLICY)
        social = data["social_behavior"]
        for section in ("deception", "betrayal"):
            for name in social[section]:
                social[section][name] = True
        policy = PersonalityPolicy(data)
        for name in BEHAVIORS:
            policy.validate_plan([{"id": name, "action": "speak", "args": {}, "intent": name}])
        social["betrayal"]["enabled"] = False
        policy = PersonalityPolicy(data)
        for name in social["betrayal"]:
            if name != "enabled":
                with self.assertRaisesRegex(PersonalityError, "behavior_disabled"):
                    policy.validate_plan([{"action": "walk", "intent": name}])
        self.assertTrue(policy.allows("lie_in_dialogue"))

    def test_action_and_legacy_intents_are_also_checked(self):
        policy = PersonalityPolicy()
        for step in ({"action": "attack_player"}, {"social_intent": "transaction_fraud"},
                     {"social_intents": ["argue", "sabotage"]}):
            with self.assertRaisesRegex(PersonalityError, "behavior_disabled"):
                policy.validate_plan([step])

    def test_disabled_leaf_cannot_hide_behind_enabled_parent(self):
        policy = PersonalityPolicy({"social_behavior": {"deception": {"lie_in_dialogue": False}}})
        self.assertFalse(policy.allows("lie_in_dialogue"))
        self.assertTrue(policy.allows("conceal_information"))

    def test_unknown_and_malformed_intents_fail_closed(self):
        policy = PersonalityPolicy()
        for intent in (None, [], {}, 1):
            with self.assertRaisesRegex(PersonalityError, "invalid_social_intent"):
                policy.validate_plan([{"intent": intent}])
        with self.assertRaisesRegex(PersonalityError, "unknown_social_intent"):
            policy.validate_plan([{"intent": "grant_inventory"}])
        for steps in ("argue", {"intent": "argue"}, [None]):
            with self.assertRaisesRegex(PersonalityError, "invalid_plan"):
                policy.validate_plan(steps)

    def test_policy_configuration_errors_are_rejected(self):
        for config in ({"schema_version": True}, {"schema_version": 2}, {"applies_to": "all_npcs"},
                       {"social_behavior": {"refuse": 1}}, {"social_behavior": {"unknown": True}},
                       {"social_behavior": {"deception": {"enabled": "yes"}}},
                       {"traits": {"honesty": float("nan")}}, {"expression_policy": "unchecked"}):
            with self.assertRaises(PersonalityError):
                PersonalityPolicy(config)

    def test_filter_does_not_silently_drop_disallowed_steps_or_mutate_input(self):
        policy = PersonalityPolicy()
        steps = [{"id": "step-1", "action": "speak", "args": {"text": "我不愿意"}, "intent": "refuse"}]
        returned = policy.filter_plan(steps)
        returned[0]["args"]["text"] = "edited"
        self.assertEqual(steps[0]["args"]["text"], "我不愿意")
        with self.assertRaisesRegex(PersonalityError, "behavior_disabled"):
            policy.filter_plan([*steps, {"intent": "attack_player"}])

    def test_permissions_do_not_claim_to_classify_unannotated_natural_speech(self):
        policy = PersonalityPolicy({"social_behavior": {"deception": {"enabled": False}}})
        # This residual semantic limitation is explicitly accepted in the spec.
        policy.validate_plan([{"id": "speech", "action": "speak", "args": {"text": "相信我"}}])


if __name__ == "__main__":
    unittest.main()
