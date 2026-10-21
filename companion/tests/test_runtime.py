from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from cph_ai_companion.config import default_config, load_config
from cph_ai_companion.memory import MemoryStore
from cph_ai_companion.protocol import (action_catalog, contract, task_catalog, validate_tasks,
                                      validate_status_parameters)
from cph_ai_companion.provider import Completion, ProviderError
from cph_ai_companion.runtime import (AgentRuntime, RuntimeErrorCode, build_messages,
                                      conservative_input_tokens, _engine_cognition, _reflections)
from cph_ai_companion.transport import TransportError


class FakeClient:
    def __init__(self, context):
        self.context = deepcopy(context)
        self.events = []
        self.observations = {"actor": {"id": 7}}
        self.calls = []
        self.offers = []
        self.connected = False
        self.state = "active"
        self.checkpoint_requested = False
        self.saved_checkpoint = None
        self.receipts = []
        self.profile_id = "profile"
        self.strict_checkpoint = False
        self.task_catalog = None
        self.action_catalog = action_catalog()[:1]
        self.task_summary = []
        self.decision_id = None
        self.planning_state = None
        self.planning_reason = ""
        self.offer_methods = []
        self.offer_errors = []

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def request(self, method, params=None):
        self.calls.append((method, deepcopy(params)))
        if method == "status":
            validate_status_parameters(params or {})
            if params and "planning_report" in params:
                report = params["planning_report"]
                if (report["decision_id"] != self.decision_id
                        or report["request_id"] != self.context["request_id"]):
                    raise TransportError("stale_request")
                self.planning_state = report["state"]
                self.planning_reason = report["reason"]
            result = {"context": deepcopy(self.context), "state": self.state,
                    "profile_id": self.profile_id, "actor_id": self.context["actor_id"],
                    "checkpoint_requested": self.checkpoint_requested,
                    "checkpoint_context": deepcopy(self.context), "saved_checkpoint": self.saved_checkpoint,
                    "receipts": deepcopy(self.receipts)}
            if self.decision_id is not None:
                result["decision_id"] = self.decision_id
            if self.planning_state is not None:
                result["planning_state"] = self.planning_state
                result["planning_reason"] = self.planning_reason
            if self.task_catalog is not None:
                result["task_summary"] = deepcopy(self.task_summary)
            return result
        if method == "configure":
            self.profile_id = params["profile_id"]
            return {}
        if method == "sync_memory":
            self.context["memory_version"] = params["version"]
            return {}
        if method == "take_request":
            result = {"context": deepcopy(self.context), "observations": deepcopy(self.observations),
                    "events": deepcopy(self.events), "action_catalog": deepcopy(self.action_catalog)}
            if self.task_catalog is not None:
                result.update(task_catalog=deepcopy(self.task_catalog), task_summary=deepcopy(self.task_summary),
                              decision_reason="task_boundary", decision_id=self.decision_id)
            return result
        if method in {"offer_plan", "offer_tasks"}:
            self.offers.append(deepcopy(params))
            self.offer_methods.append(method)
            if self.offer_errors:
                error = self.offer_errors.pop(0)
                if error:
                    raise TransportError(error)
            return {"state": "accepted", "plan_id": "p"}
        if method == "checkpoint":
            if self.strict_checkpoint and (params["version"] != self.context["memory_version"]
                                           or params["reference"].get("projection_version") != self.context["memory_version"]
                                           or not params["reference"].get("revision")):
                raise TransportError("stale_checkpoint")
            self.checkpoint_requested = False
            self.saved_checkpoint = params["reference"]
            return {"prepared": True}
        if method == "cancel":
            return {"detach_state": "attached"}
        if method == "stop":
            self.state = "detached"
            return {"detach_state": "detached"}
        return {}


class FakeProvider:
    def __init__(self, values=None, before=None):
        self.values = list(values or [{"steps": [{"id": "one", "action": "wait", "args": {}}]}])
        self.before = before
        self.messages = []
        self.cancelled = False
        self.closed = False

    def complete(self, messages, **kwargs):
        self.messages.append(deepcopy(messages))
        if self.before:
            self.before()
        if kwargs["on_wait"]() is False:
            raise ProviderError("request_invalidated")
        return Completion(deepcopy(self.values.pop(0)), None)

    def cancel(self):
        self.cancelled = True

    def close(self):
        self.closed = True


class RuntimeTests(unittest.TestCase):
    def test_native_projection_preserves_subjective_origin_and_imported_experience_label(self):
        record = {"id": "known-source", "kind": "growth", "text": "I learned caution",
                  "context": {"world_id": "old-world", "actor_id": "old-actor"},
                  "source_ids": ["observed-source"], "provenance": "subjective",
                  "continuity": "imported_experience_not_current_world_fact",
                  "preferences": {"caution": 0.8}}
        projected = _engine_cognition({"revision": "v", "records": [record]}, self.context)
        self.assertEqual(projected["context"], self.context)
        self.assertEqual(projected["records"], [{**record, "origin_context": record["context"],
                                                "context": self.context, "imported": True}])
        self.assertEqual(record["context"]["actor_id"], "old-actor")
        self.assertNotIn("origin_context", record)

    def test_imported_physical_facts_do_not_enter_native_cache_or_change_local_memory(self):
        snapshot = {"revision": "v", "records": [
            {"id": kind, "kind": kind, "text": "Old experience", "source_ids": [],
             "context": {"world_id": "old-world", "actor_id": "old-actor"},
             "continuity": "imported_experience_not_current_world_fact"}
            for kind in ("observation", "statement", "receipt", "goal", "commitment",
                         "belief", "relationship", "growth", "summary")]}
        original = deepcopy(snapshot)
        projected = _engine_cognition(snapshot, self.context)
        self.assertEqual([record["kind"] for record in projected["records"]],
                         ["belief", "relationship", "growth", "summary"])
        self.assertTrue(all(record["imported"] is True and record["context"] == self.context
                            for record in projected["records"]))
        self.assertEqual(snapshot, original)
        self.assertEqual(_engine_cognition(snapshot)["records"], [])

    def test_unmarked_foreign_actor_is_not_silently_rebound_by_projection(self):
        record = {"id": "foreign", "kind": "belief", "text": "Someone else's belief",
                  "context": {"world_id": "world", "actor_id": "different-actor"}}
        projected = _engine_cognition({"revision": "v", "records": [record]}, self.context)
        self.assertEqual(projected["records"], [record])
        self.assertNotIn("imported", projected["records"][0])

    def test_retained_growth_sync_uses_current_binding_without_rewriting_its_origin(self):
        self.memory.continuity["new_world_personality_growth"] = "retain"
        old_context = {**self.context, "world_id": "old-world", "actor_id": 99}
        ids = self.memory.ingest(old_context, [
            {"id": "danger", "kind": "receipt", "text": "Danger observed"},
            {"id": "lesson", "kind": "growth", "text": "I learned caution",
             "source_ids": ["danger"], "preferences": {"caution": 0.8}}])
        snapshot = self.runtime()._sync(self.context)
        synced = next(params["snapshot"] for method, params in self.client.calls if method == "sync_memory")
        self.assertEqual(synced["context"], self.context)
        self.assertEqual(len(synced["records"]), 1)
        growth = synced["records"][0]
        self.assertEqual(growth["id"], ids[1])
        self.assertEqual(growth["context"]["actor_id"], 7)
        self.assertEqual(growth["origin_context"]["actor_id"], "99")
        self.assertEqual(growth["preferences"], {"caution": 0.8})
        self.assertEqual(snapshot["records"][0]["context"]["world_id"], "old-world")
        self.assertNotIn("imported", snapshot["records"][0])

    def test_native_cognition_cache_is_bounded_without_erasing_local_bodies(self):
        snapshot = {"revision": "version", "background": "private fixed biography", "records": [
            {"id": str(index), "kind": "observation", "text": "中" * 22000,
             "context": {"world_id": "w", "actor_id": 7}, "data": {"raw": "x" * 900000},
             "source_ids": [], "confidence": 1} for index in range(100)]}
        projected = _engine_cognition(snapshot)
        import json
        self.assertLess(len(json.dumps(projected, ensure_ascii=False).encode()), 1024 * 1024)
        self.assertNotIn("background", projected)
        self.assertLess(len(projected["records"]), 100)
        self.assertNotIn("data", projected["records"][0])
        self.assertLessEqual(len(projected["records"][0]["text"].encode()), 65536)
        self.assertEqual(len(snapshot["records"][0]["data"]["raw"]), 900000)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = default_config()
        self.config["profile_id"] = "profile"
        self.config["actor_id"] = 7
        self.config["limits"]["max_calls"] = 1
        self.config["limits"]["max_input_tokens"] = 20000
        self.context = {"world_id": "world", "branch_id": "branch", "actor_id": 7,
                        "load_epoch": "load", "request_id": "request", "event_watermark": 1,
                        "policy_version": "policy", "memory_version": "", "game_time": 100}
        self.memory = MemoryStore(self.directory.name, self.config)
        self.addCleanup(self.memory.close)
        self.client = FakeClient(self.context)
        self.provider = FakeProvider()
        self.now = 0.0

    def runtime(self):
        runtime = AgentRuntime(self.config, self.memory, self.client, self.provider, clock=lambda: self.now)
        self.addCleanup(runtime.close)
        return runtime

    def test_plan_is_proposal_with_engine_context_and_unknown_usage_reserves_budget(self):
        runtime = self.runtime()
        result = runtime.run_once()
        self.assertEqual(result["state"], "submitted")
        self.assertEqual(self.client.offers[0]["context"], self.client.context)
        self.assertGreater(runtime._tokens, 0)
        self.assertEqual(runtime._calls, 1)
        self.assertEqual(self.memory.retrieve(self.context), [])  # model isn't an action receipt

    def test_provider_failure_reports_terminal_state_without_claiming_a_worker_is_waiting(self):
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.failure"

        def fail(messages, **kwargs):
            self.provider.messages.append(deepcopy(messages))
            self.assertTrue(kwargs["on_wait"]())
            self.assertEqual(self.client.planning_state, "thinking")
            raise ProviderError("provider_request_failed", diagnostics={"http_status": 401})

        self.provider.complete = fail
        runtime = self.runtime()
        self.assertEqual(runtime.run_once(), {"state": "rejected", "code": "provider_request_failed"})
        self.assertEqual((self.client.planning_state, self.client.planning_reason), ("failed", "provider_failed"))
        self.assertEqual(self.client.offers, [])
        self.assertEqual(runtime._calls, 1)
        self.assertEqual(runtime.run_once()["state"], "cooldown")
        self.now = 11
        self.assertEqual(runtime.run_once()["state"], "waiting_for_information")
        self.assertEqual(self.client.planning_state, "failed")
        reports = [params["planning_report"] for method, params in self.client.calls
                   if method == "status" and params and "planning_report" in params]
        self.assertEqual([report["state"] for report in reports], ["thinking", "pending", "failed"])
        self.assertNotIn("401", json.dumps(reports))
        self.assertEqual(len(self.provider.messages), 1)

    def test_terminal_worker_report_does_not_overwrite_a_new_decision(self):
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.old"

        def change_decision():
            self.client.decision_id = "load.new"
            self.client.context["request_id"] = "new-request"
            self.client.planning_state = "pending"

        self.provider.before = change_decision
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "discarded")
        self.assertEqual(self.client.planning_state, "pending")
        self.assertEqual(self.client.offers, [])

    def test_events_are_ingested_once_and_memory_change_fetches_fresh_request(self):
        self.client.events = [{"id": "event-one", "kind": "statement", "text": "Player says the cellar is safe"}]
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "memory_resynced")
        self.assertEqual(len(self.provider.messages), 0)
        self.assertEqual(runtime.run_once()["state"], "submitted")
        records = self.memory.retrieve(self.context)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "statement")

    def test_disabled_intent_is_rejected_without_partial_submission(self):
        self.provider = FakeProvider([{"steps": [{"id": "a", "action": "wait", "args": {}, "intent": "attack_player"}]}])
        result = self.runtime().run_once()
        self.assertEqual(result, {"state": "rejected", "code": "behavior_disabled"})
        self.assertEqual(self.client.offers, [])

    def test_load_change_invalidates_worker_and_never_submits(self):
        self.provider.before = lambda: self.client.context.update(load_epoch="new-load")
        result = self.runtime().run_once()
        self.assertEqual(result["state"], "discarded")
        self.assertEqual(self.client.offers, [])

    def test_human_edit_during_thinking_invalidates_candidate(self):
        self.provider.before = lambda: (Path(self.directory.name) / "background.md").write_text("Edited by user")
        result = self.runtime().run_once()
        self.assertEqual(result["state"], "discarded")
        self.assertEqual(self.client.offers, [])

    def test_queries_only_retrieve_local_memory_and_share_call_budget(self):
        self.config["limits"]["max_calls"] = 2
        self.provider = FakeProvider([{"queries": [{"query": "medicine", "limit": 3}]},
                                      {"steps": [{"id": "a", "action": "wait", "args": {}}]}])
        result = self.runtime().run_once()
        self.assertEqual(result["state"], "submitted")
        self.assertEqual(len(self.provider.messages), 2)
        self.assertIn('"local_queries"', self.provider.messages[1][1]["content"])
        self.assertEqual([m for m, _ in self.client.calls if m == "query"], [])

    def test_session_budget_refuses_additional_call(self):
        self.config["limits"]["session_max_calls"] = 1
        runtime = self.runtime()
        runtime.run_once()
        self.now = 20
        self.client.observations["actor"]["position"] = [1, 2, 0]
        with self.assertRaisesRegex(RuntimeErrorCode, "session_call_budget_exhausted"):
            runtime.run_once()
        self.assertEqual(len(self.provider.messages), 1)

    def test_final_observer_rpc_cannot_submit_a_plan_after_episode_deadline(self):
        runtime = self.runtime()
        original_alive = runtime._alive
        checks = []

        def delayed_final_observer(context, revision):
            valid = original_alive(context, revision)
            checks.append(valid)
            # Provider poll and post-completion checks finish in time. The
            # final observer RPC consumes the last time before submission.
            if len(checks) == 3:
                self.now = self.config["limits"]["episode_timeout"]
            return valid

        runtime._alive = delayed_final_observer
        self.assertEqual(runtime.run_once(), {"state": "rejected", "code": "episode_timeout"})
        self.assertEqual(checks, [True, True, True])
        self.assertEqual(self.client.offers, [])
        self.assertEqual(runtime._calls, 1)

    def test_explicit_stop_cancels_worker_and_requests_native_detach(self):
        runtime = self.runtime()
        runtime.start()
        runtime.request_stop()
        result = runtime.run_once()
        self.assertEqual(result["state"], "stopped")
        self.assertTrue(self.provider.cancelled)
        self.assertEqual(self.client.state, "detached")
        self.assertEqual([method for method, _ in self.client.calls if method in ("cancel", "stop")], ["cancel", "stop"])

    def test_local_stop_notification_prevents_new_model_calls(self):
        runtime = AgentRuntime(self.config, self.memory, self.client, self.provider,
                               clock=lambda: self.now, stop_requested=lambda: True)
        self.addCleanup(runtime.close)
        result = runtime.run_once()
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(self.provider.messages, [])
        self.assertTrue(self.provider.cancelled)
        self.assertEqual(self.client.state, "detached")

    def test_subjective_reflection_uses_real_source_and_cannot_become_a_receipt(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "Player says cellar is safe"}])
        source = self.memory.retrieve(self.context)[0]["id"]
        self.provider = FakeProvider([{"steps": [], "reflections": [{"kind": "belief", "text": "I trust the player about the cellar", "source_ids": [source], "confidence": 0.8}]}])
        result = self.runtime().run_once()
        self.assertEqual(result["state"], "submitted")
        self.assertNotIn("reflections", self.client.offers[0])
        records = self.memory.retrieve(self.context)
        belief = next(record for record in records if record["kind"] == "belief")
        self.assertEqual(belief["provenance"], "subjective")
        self.assertEqual(belief["source_ids"], [source])
        self.assertFalse(any(record["kind"] == "receipt" for record in records))

    def test_reflection_with_invented_source_or_fact_kind_is_rejected(self):
        for kind, sources in (("receipt", ["fake"]), ("belief", ["fake"]), ("growth", [])):
            with self.subTest(kind=kind):
                self.client.observations["new_event"] = kind
                self.provider = FakeProvider([{"steps": [], "reflections": [{"kind": kind, "text": "imagined", "source_ids": sources}]}])
                self.assertEqual(self.runtime().run_once()["state"], "rejected")
        self.assertEqual(self.client.offers, [])

    def test_task_candidate_acknowledgement_cannot_commit_reflection_or_change_revision(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "Gather rocks"}])
        source = self.memory.retrieve(self.context)[0]["id"]
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.one"
        self.provider = FakeProvider([{"tasks": [{"id": "follow", "kind": "follow", "args": {}}],
                                      "reflections": [{"kind": "belief", "text": "I accepted the task",
                                                       "source_ids": [source]}]}])
        original = self.client.request

        def acknowledge_candidate(method, params=None):
            result = original(method, params)
            return {"accepted": True, "state": "candidate"} if method == "offer_tasks" else result

        self.client.request = acknowledge_candidate
        runtime = self.runtime()
        runtime.start()
        before = self.memory.snapshot(self.client.context)["revision"]
        result = runtime.run_once()
        self.assertEqual(result["state"], "submitted")
        self.assertEqual(result["cognition"], {"state": "discarded", "code": "task_adoption_unconfirmed"})
        self.assertEqual(self.memory.snapshot(self.client.context)["revision"], before)
        self.assertFalse(any(record["kind"] in {"belief", "receipt", "commitment"}
                             for record in self.memory.retrieve(self.client.context)))
        self.assertEqual(len(self.client.offers), 1)

    def test_human_edit_after_native_acceptance_discards_reflection_without_replay(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "A statement"}])
        source = self.memory.retrieve(self.context)[0]["id"]
        self.provider = FakeProvider([{"steps": [], "reflections": [{"kind": "growth", "text": "I should be cautious", "source_ids": [source]}]}])
        original = self.client.request

        def edit_after_acceptance(method, params=None):
            result = original(method, params)
            if method == "offer_plan":
                (Path(self.directory.name) / "background.md").write_text("Human edit during handoff")
            return result
        self.client.request = edit_after_acceptance
        result = self.runtime().run_once()
        self.assertEqual(result["state"], "submitted")
        self.assertEqual(result["cognition"]["state"], "discarded")
        self.assertEqual(len(self.client.offers), 1)
        self.assertFalse(any(record["kind"] == "growth" for record in self.memory.retrieve(self.context)))

    def test_preference_reflection_is_bounded_and_world_setters_are_rejected(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "Player deceived me"}])
        source = self.memory.retrieve(self.context)[0]["id"]
        self.provider = FakeProvider([{"steps": [], "reflections": [{"kind": "relationship", "text": "I should keep some distance", "source_ids": [source], "preferences": {"caution": 0.9}}]}])
        self.assertEqual(self.runtime().run_once()["state"], "submitted")
        record = next(r for r in self.memory.retrieve(self.context) if r["kind"] == "relationship")
        self.assertEqual(record["preferences"], {"caution": 0.9})
        self.client.observations["new_event"] = "another interaction"
        self.provider = FakeProvider([{"steps": [], "reflections": [{"kind": "growth", "text": "Become powerful", "source_ids": [source], "preferences": {"strength": 999}}]}])
        self.assertEqual(self.runtime().run_once()["state"], "rejected")

    def test_prompt_omits_duplicate_raw_observation_but_preserves_real_receipt(self):
        request = {"context": self.context, "observations": {"visible": "present"}, "action_catalog": action_catalog()[:1],
                   "events": [{"id": "observed", "kind": "observation", "text": "perception changed", "data": {"unique_full_raw": "duplicate"}},
                              {"id": "done", "kind": "receipt", "text": "crafted", "data": {"item_type": "bandages"}}]}
        messages = build_messages(request, {"records": [], "revision": "r"}, self.config)
        self.assertNotIn("unique_full_raw", messages[1]["content"])
        self.assertIn('"item_type":"bandages"', messages[1]["content"])
        self.assertEqual(request["events"][0]["data"], {"unique_full_raw": "duplicate"})

    def test_prompt_preserves_bounded_native_action_semantics_without_private_fields(self):
        import json
        descriptions = {"gather": "Pick up observed ground items; this is not general harvesting.",
                        "attack": "Use native melee against a sensed target; no ranged attack."}
        catalog = [{**entry, "description": descriptions[entry["name"]],
                    "engine_private_state": "unauthorized_hidden_state"}
                   for entry in action_catalog() if entry["name"] in descriptions]
        catalog.append({"name": "wait", "args": {}, "description": "中" * 600})
        original = deepcopy(catalog)
        request = {"context": self.context, "observations": {}, "action_catalog": catalog}
        messages = build_messages(request, {"records": [], "revision": "r"}, self.config)
        actions = {entry["name"]: entry for entry in json.loads(messages[1]["content"])["action_catalog"]["actions"]}
        for name, description in descriptions.items():
            self.assertEqual(actions[name].get("description"), description)
            self.assertNotIn("engine_private_state", actions[name])
        self.assertEqual(actions["wait"].get("description"), "中" * 512)
        self.assertNotIn("unauthorized_hidden_state", messages[1]["content"])
        self.assertEqual(request["action_catalog"], original)

    def test_native_ability_query_is_visible_without_additional_tools_or_model_calls(self):
        abilities = [{"id": "known_spell", "name": "Known spell", "supported": True,
                      "castable": True, "energy_source": "MANA", "energy_cost": 40},
                     {"id": "unsupported_spell", "supported": False, "castable": False,
                      "reason": "unsupported_spell_effect"}]
        self.client.observations["actor"].update(
            abilities=abilities, mana=100, mana_max=200, ability_count=2, abilities_truncated=False)
        self.client.action_catalog = [entry for entry in action_catalog() if entry["name"] == "cast_spell"]
        step = {"id": "cast", "action": "cast_spell",
                "args": {"spell": "known_spell", "x": 10, "y": 20, "z": 0}}
        self.provider = FakeProvider([{"steps": [step]}])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.assertEqual(self.client.offers[0]["steps"], [step])
        self.assertEqual(runtime._calls, 1)
        self.assertEqual(len(self.provider.messages), 1)
        payload = json.loads(self.provider.messages[0][-1]["content"])
        self.assertIn("observations.actor.abilities", self.provider.messages[0][0]["content"])
        actor = payload["observations"]["actor"]
        self.assertEqual(actor["abilities"], abilities)
        self.assertEqual(actor["mana"], 100)
        self.assertNotIn("query", {method for method, _ in self.client.calls})
        self.assertEqual(self.memory.retrieve(self.context), [])

    def test_cast_prompt_requires_supported_known_abilities_without_code_or_guessed_ids(self):
        cast = next(entry for entry in action_catalog() if entry["name"] == "cast_spell")
        request = {"context": self.context, "observations": {}, "action_catalog": [cast]}
        messages = build_messages(request, {"revision": "r", "records": []}, self.config)
        self.assertIn("observations.actor.abilities", messages[0]["content"])
        self.assertIn("castable true", messages[0]["content"])
        self.assertIn("absolute map-square", messages[0]["content"])
        self.assertIn("Unsupported effects are final", messages[0]["content"])
        self.assertIn("never guess IDs, retry them or substitute Lua/EOC", messages[0]["content"])
        payload = json.loads(messages[-1]["content"])
        catalog = payload["action_catalog"]
        entry = catalog["actions"][0]
        self.assertEqual(entry["name"], "cast_spell")
        schema = catalog["argument_schemas"][entry["args_schema"]]
        self.assertEqual(schema["required"], ["spell", "x", "y", "z"])
        self.assertFalse(schema["extra_fields"])
        for request_catalog in ([], [{**cast, "available": False}]):
            request["action_catalog"] = request_catalog
            messages = build_messages(request, {"revision": "r", "records": []}, self.config)
            self.assertNotIn("observations.actor.abilities", messages[0]["content"])

    def test_terminal_native_receipts_are_stored_during_cooldown_without_new_model_call(self):
        runtime = self.runtime()
        runtime.run_once()
        self.client.receipts = [{"operation_id": "request.one", "action": "gather", "state": "succeeded",
                                 "code": "gathered", "game_time": 101, "detail": {"item_type": "rock", "count": 1}}]
        self.assertEqual(runtime.run_once()["state"], "cooldown")
        records = self.memory.retrieve({**self.context, "game_time": 101})
        self.assertEqual(records[0]["kind"], "receipt")
        self.assertEqual(records[0]["data"]["detail"], {"item_type": "rock", "count": 1})
        runtime.run_once()
        self.assertEqual(len(self.memory.retrieve({**self.context, "game_time": 101})), 1)
        self.assertEqual(len(self.provider.messages), 1)

    def test_unexpected_disconnect_does_not_cancel_accepted_engine_queue(self):
        runtime = self.runtime()
        runtime.start()
        self.client.request = lambda *args, **kwargs: (_ for _ in ()).throw(TransportError("disconnected"))
        self.assertEqual(runtime.run()["state"], "disconnected")
        self.assertEqual([method for method, _ in self.client.calls if method == "cancel"], [])
        self.assertTrue(self.provider.closed)

    def _assert_exhausted_run_keeps_receipts_and_checkpoint_until_explicit_stop(self, code):
        if code == "session_call_budget_exhausted":
            self.config["limits"]["session_max_calls"] = 1
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.first"
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        if code == "session_token_budget_exhausted":
            # Actual provider usage can exhaust tokens without exhausting calls.
            runtime._charge_usage(Completion({}, {"total_tokens": runtime.config["limits"]["session_max_tokens"]}), runtime._tokens)
        charged = (runtime._calls, runtime._tokens)
        self.client.decision_id = "load.next"
        self.now = 11
        original = self.client.request
        phase = {"value": "waiting_for_quota", "polls": 0}

        def continue_local_work(method, params=None):
            if method == "status":
                phase["polls"] += 1
                self.assertLess(phase["polls"], 20, "local coordinator did not reach its checkpoint")
                if phase["value"] == "waiting_for_quota" and runtime.last_result.get("state") == "planning_suspended":
                    self.assertEqual(runtime.last_result["code"], code)
                    self.assertEqual(self.client.planning_state, "suspended")
                    self.assertEqual(self.client.planning_reason, "call_budget_exhausted" if
                                     code == "session_call_budget_exhausted" else "token_budget_exhausted")
                    self.assertFalse(self.provider.closed)
                    self.assertFalse(self.provider.cancelled)
                    self.client.receipts = [{"operation_id": "after-quota", "action": "gather",
                                             "state": "succeeded", "code": "gathered", "game_time": 101,
                                             "detail": {"item_type": "rock", "count": 1}}]
                    self.client.context["game_time"] = 101
                    phase["value"] = "receipt_delivered"
                elif phase["value"] == "receipt_delivered":
                    records = self.memory.retrieve(self.client.context)
                    receipt = next(record for record in records if record.get("data", {}).get("operation_id") == "after-quota")
                    phase["receipt_id"] = receipt["id"]
                    self.client.checkpoint_requested = True
                    self.client.strict_checkpoint = True
                    phase["value"] = "checkpoint_requested"
            result = original(method, params)
            if method == "checkpoint":
                checkpoint = json.loads((self.memory.memory_root / "checkpoints" / (params["reference"]["id"] + ".json")).read_text())
                self.assertIn(phase["receipt_id"], checkpoint["heads"])
                self.assertFalse(self.provider.closed)
                self.assertFalse(self.provider.cancelled)
                self.assertEqual([name for name, _ in self.client.calls if name in {"cancel", "stop"}], [])
                self.assertEqual(len(self.provider.messages), 1)
                self.assertEqual((runtime._calls, runtime._tokens), charged)
                phase["value"] = "checkpointed"
                runtime.request_stop()  # The test's explicit user stop, after all checks above.
            return result

        self.client.request = continue_local_work
        self.assertEqual(runtime.run(poll_interval=0)["state"], "stopped")
        self.assertEqual(phase["value"], "checkpointed")
        self.assertEqual(len(self.provider.messages), 1)
        self.assertEqual((runtime._calls, runtime._tokens), charged)
        self.assertEqual([name for name, _ in self.client.calls if name in {"cancel", "stop"}], ["cancel", "stop"])

    def test_run_call_quota_exhaustion_keeps_local_receipts_and_checkpoint_alive(self):
        self._assert_exhausted_run_keeps_receipts_and_checkpoint_until_explicit_stop("session_call_budget_exhausted")

    def test_run_token_quota_exhaustion_keeps_local_receipts_and_checkpoint_alive(self):
        self._assert_exhausted_run_keeps_receipts_and_checkpoint_until_explicit_stop("session_token_budget_exhausted")

    def test_run_can_apply_explicit_budget_period_after_planning_is_suspended(self):
        self.config["limits"]["session_max_calls"] = 1
        root = Path(self.directory.name)
        (root / "config.json").write_text(json.dumps(self.config))
        self.provider = FakeProvider([{"steps": [{"id": name, "action": "wait", "args": {}}]} for name in ("first", "second")])
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.first"
        runtime = AgentRuntime(load_config(root), self.memory, self.client, self.provider,
                               profile=root, clock=lambda: self.now)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.client.decision_id = "load.next"
        self.now = 11
        original = self.client.request
        changed = {"value": False, "polls": 0}

        def human_starts_new_period(method, params=None):
            if method == "status":
                changed["polls"] += 1
                self.assertLess(changed["polls"], 30, "explicit period edit was not applied")
                if runtime.last_result.get("state") == "planning_suspended" and not changed["value"]:
                    self.assertFalse(self.provider.closed)
                    self.assertFalse(self.provider.cancelled)
                    latest = json.loads((root / "config.json").read_text())
                    latest["limits"]["budget_period"] = "explicit-human-next-period"
                    (root / "config.json").write_text(json.dumps(latest))
                    self.now = 22
                    changed["value"] = True
                elif changed["value"]:
                    self.now += 11  # The local cooldown still uses advancing wall time.
            result = original(method, params)
            if method == "offer_plan" and len(self.provider.messages) == 2:
                data = json.loads((root / "runtime-budget.json").read_text())
                self.assertEqual(len(data["accounts"]), 2)
                self.assertEqual(sorted(account["calls"] for account in data["accounts"].values()), [1, 1])
                self.assertFalse(self.provider.closed)
                runtime.request_stop()
            return result

        self.client.request = human_starts_new_period
        self.assertEqual(runtime.run(poll_interval=0)["state"], "stopped")
        self.assertTrue(changed["value"])
        self.assertEqual(len(self.provider.messages), 2)

    def test_save_prepare_records_reference_without_claiming_game_save_success(self):
        self.client.checkpoint_requested = True
        self.client.context["memory_version"] = "native-projection"
        runtime = self.runtime()
        runtime.start()
        prepared = [params for method, params in self.client.calls if method == "checkpoint"]
        self.assertEqual(len(prepared), 1)
        self.assertEqual(set(prepared[0]["reference"]), {"id", "revision", "projection_version"})
        self.assertTrue((Path(self.directory.name) / "memory/checkpoints" / (prepared[0]["reference"]["id"] + ".json")).exists()
                        or (Path(self.directory.name) / "checkpoints" / (prepared[0]["reference"]["id"] + ".json")).exists())

    def test_context_budget_rejects_unsliceable_observation(self):
        request = {"context": self.context, "observations": {"text": "x" * 50000}}
        with self.assertRaisesRegex(RuntimeErrorCode, "context_budget_exceeded"):
            build_messages(request, {"revision": "r", "records": []}, self.config)

    def test_exhausted_event_group_does_not_reset_after_cooldown_or_synthetic_request_change(self):
        self.config["limits"]["max_calls"] = 3
        self.provider = FakeProvider([{"steps": [{"id": "a", "action": "invented", "args": {}}]}] * 6)
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "rejected")
        self.assertEqual(len(self.provider.messages), 3)
        self.now = 11
        self.client.context.update(request_id="synthetic-refresh", game_time=101)
        result = runtime.run_once()
        self.assertEqual(result["state"], "waiting_for_information")
        self.assertEqual(len(self.provider.messages), 3)
        self.assertEqual(runtime._episode["calls"], 3)
        journal = (self.memory.memory_root / "runtime-episodes.json").read_text()
        self.assertNotIn("synthetic-refresh", journal)
        self.assertNotIn("world", journal)

    def test_genuine_new_observation_starts_a_new_episode_after_exhaustion(self):
        self.provider = FakeProvider([{"steps": [{"id": "a", "action": "invented", "args": {}}]},
                                      {"steps": [{"id": "b", "action": "wait", "args": {}}]}])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "rejected")
        self.now = 11
        self.client.observations["visible"] = {"target": "newly sensed"}
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.assertEqual(len(self.provider.messages), 2)

    def test_provider_failures_consume_same_episode_and_restart_remains_waiting(self):
        self.config["limits"]["max_calls"] = 3
        runtime = self.runtime()
        calls = []

        def fail(messages, **kwargs):
            calls.append(messages)
            raise ProviderError("provider_timeout")
        self.provider.complete = fail
        self.assertEqual(runtime.run_once(), {"state": "rejected", "code": "provider_timeout"})
        self.assertEqual(len(calls), 3)
        runtime.close()
        self.now = 11
        self.provider = FakeProvider()
        self.assertEqual(self.runtime().run_once(), {"state": "waiting_for_information", "code": "provider_timeout"})
        self.assertEqual(self.provider.messages, [])

    def test_uncertain_reserved_call_is_not_reissued_after_restart(self):
        runtime = self.runtime()

        def disconnect(messages, **kwargs):
            raise TransportError("disconnected")
        self.provider.complete = disconnect
        with self.assertRaises(TransportError):
            runtime.run_once()
        self.assertEqual(runtime._episode["calls"], 1)
        runtime.close()
        self.provider = FakeProvider()
        self.assertEqual(self.runtime().run_once(), {"state": "waiting_for_information", "code": "planning_interrupted"})
        self.assertEqual(self.provider.messages, [])

    def test_query_budget_is_retained_after_stale_response_and_next_poll(self):
        self.config["limits"].update(max_calls=3, max_queries=1)
        self.provider = FakeProvider([{"queries": [{"query": "medicine", "limit": 1}]},
                                      {"steps": [{"id": "a", "action": "wait", "args": {}}]}])

        def invalidate_second_call():
            if len(self.provider.messages) == 2:
                self.client.context["request_id"] = "synthetic-refresh"
        self.provider.before = invalidate_second_call
        runtime = self.runtime()
        self.assertEqual(runtime.run_once(), {"state": "discarded", "code": "request_invalidated"})
        self.assertEqual(runtime._episode["queries"], 1)
        self.assertEqual(runtime._episode["calls"], 2)
        self.now = 11
        self.assertEqual(runtime.run_once()["state"], "waiting_for_information")
        self.assertEqual(len(self.provider.messages), 2)

    def test_episode_journal_rejects_symlink_and_unknown_format(self):
        path = self.memory.memory_root / "runtime-episodes.json"
        path.write_text('{"schema_version":2,"episodes":{}}')
        path.chmod(0o600)
        with self.assertRaisesRegex(RuntimeErrorCode, "invalid_episode_journal"):
            self.runtime()
        path.write_text('{"schema_version":true,"episodes":{}}')
        with self.assertRaisesRegex(RuntimeErrorCode, "invalid_episode_journal"):
            self.runtime()
        path.write_text('{"schema_version":1,"episodes":{}}')
        path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeErrorCode, "invalid_episode_journal"):
            self.runtime()
        path.unlink()
        target = Path(self.directory.name) / "outside.json"
        target.write_text('{"schema_version":1,"episodes":{}}')
        path.symlink_to(target)
        with self.assertRaisesRegex(RuntimeErrorCode, "invalid_episode_journal"):
            self.runtime()
        self.assertEqual(target.read_text(), '{"schema_version":1,"episodes":{}}')

    def test_time_based_forgetting_resyncs_projection_without_file_revision_change(self):
        self.memory.cognition.update(half_life_seconds=1, recall_threshold=0.1)
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "danger"},
                                          {"id": "lesson", "kind": "growth", "text": "caution",
                                           "source_ids": ["heard"], "preferences": {"caution": 0.9}}])
        runtime = self.runtime()
        first = runtime._sync(self.context)
        versions = [params["version"] for method, params in self.client.calls if method == "sync_memory"]
        second = runtime._sync({**self.context, "game_time": 120})
        syncs = [params for method, params in self.client.calls if method == "sync_memory"]
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(len(syncs), 2)
        self.assertNotEqual(syncs[-1]["version"], versions[0])
        self.assertEqual(syncs[-1]["snapshot"]["records"], [])

    def test_ordinary_clock_advance_keeps_projection_version_and_load_change_resends(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "danger"}])
        runtime = self.runtime()
        runtime._sync(self.context)
        runtime._sync({**self.context, "game_time": 101, "request_id": "fresh", "event_watermark": 2})
        syncs = [params for method, params in self.client.calls if method == "sync_memory"]
        self.assertEqual(len(syncs), 1)
        runtime._sync({**self.context, "load_epoch": "different-load"})
        syncs = [params for method, params in self.client.calls if method == "sync_memory"]
        self.assertEqual(len(syncs), 2)
        self.assertNotEqual(syncs[0]["version"], syncs[1]["version"])

    def test_forgetting_during_model_call_invalidates_the_old_projection(self):
        self.memory.cognition.update(half_life_seconds=1, recall_threshold=0.1)
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "danger"}])
        self.provider.before = lambda: self.client.context.update(game_time=120)
        self.assertEqual(self.runtime().run_once()["state"], "discarded")
        self.assertEqual(self.client.offers, [])

    def test_mandatory_records_survive_prompt_trimming_and_oversize_is_explicit(self):
        request = {"context": self.context, "observations": {}, "action_catalog": action_catalog()[:1]}
        mandatory = {"id": "receipt", "kind": "receipt", "text": "crafted medicine", "data": {"item": "bandages"}}
        snapshot = {"revision": "r", "records": [*[{"id": str(i), "kind": "summary", "text": "x" * 1000}
                                                   for i in range(30)], mandatory],
                    "mandatory_record_ids": ["receipt"]}
        messages = build_messages(request, snapshot, self.config)
        payload = json.loads(messages[1]["content"])
        self.assertIn(mandatory, payload["memory_records"])
        self.assertLess(len(payload["memory_records"]), 31)
        self.assertLessEqual(conservative_input_tokens(messages), self.config["limits"]["max_input_tokens"])
        snapshot["records"][-1]["text"] = "x" * 30000
        with self.assertRaisesRegex(RuntimeErrorCode, "context_budget_exceeded"):
            build_messages(request, snapshot, self.config)

    def test_native_cache_reserves_more_than_100_mandatory_records_without_truncating(self):
        mandatory = [{"id": "receipt-" + str(i), "kind": "receipt", "text": "required", "context": self.context}
                     for i in range(101)]
        snapshot = {"revision": "r", "records": [{"id": "chat", "kind": "summary", "text": "optional", "context": self.context}, *mandatory],
                    "mandatory_record_ids": [record["id"] for record in mandatory]}
        self.assertEqual(_engine_cognition(snapshot)["records"], mandatory)
        snapshot["records"][1]["text"] = "x" * 65537
        with self.assertRaisesRegex(RuntimeErrorCode, "context_budget_exceeded"):
            _engine_cognition(snapshot)

    def test_reflection_sources_must_be_present_after_prompt_and_query_trimming(self):
        request = {"context": self.context, "observations": {}}
        snapshot = {"revision": "r", "records": [{"id": "hidden", "kind": "statement", "text": "x" * 30000}]}
        queries = [{"query": "history", "records": [{"id": "query-hidden", "kind": "statement", "text": "x" * 30000}]}]
        messages = build_messages(request, snapshot, self.config, queries)
        self.assertEqual(json.loads(messages[1]["content"])["memory_records"], [])
        self.assertEqual(json.loads(messages[1]["content"])["local_queries"], [])
        for source in ("hidden", "query-hidden"):
            with self.subTest(source=source), self.assertRaisesRegex(RuntimeErrorCode, "reflection_source_unavailable"):
                _reflections({"reflections": [{"kind": "belief", "text": "interpretation", "source_ids": [source]}]}, messages, self.context)

    def test_real_memory_obligation_and_its_receipt_reach_prompt_and_native_cache(self):
        self.memory.cognition.update(half_life_seconds=1, recall_threshold=0.1)
        events = [{"id": "crafted", "kind": "receipt", "text": "crafted bandages", "importance": 0.01,
                   "data": {"item_type": "bandages", "count": 4}},
                  {"id": "promised", "kind": "commitment", "text": "deliver medicine", "status": "accepted",
                   "importance": 0.01, "source_ids": ["crafted"]}]
        events += [{"id": "chat-" + str(i), "kind": "summary", "text": "unrelated ordinary conversation",
                    "importance": 1} for i in range(120)]
        ids = self.memory.ingest(self.context, events)
        context = {**self.context, "game_time": 120}
        request = {"context": context, "observations": {}, "action_catalog": action_catalog()[:1]}
        snapshot = self.memory.snapshot(context, request)
        self.assertEqual(set(snapshot["mandatory_record_ids"]), set(ids[:2]))
        messages = build_messages(request, snapshot, self.config)
        shown = {record["id"]: record for record in json.loads(messages[1]["content"])["memory_records"]}
        self.assertEqual(shown[ids[0]]["data"], {"item_type": "bandages", "count": 4})
        self.assertEqual(shown[ids[1]]["status"], "accepted")
        cache = _engine_cognition(snapshot, context)
        self.assertEqual({record["id"] for record in cache["records"]}, set(ids[:2]))

    def test_automatic_reflection_and_projection_refresh_do_not_buy_another_episode(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "Player says cellar is safe"}])
        source = self.memory.retrieve(self.context)[0]["id"]
        self.provider = FakeProvider([{"steps": [], "reflections": [{"kind": "belief", "text": "perhaps safe",
                                                                     "source_ids": [source]}]}])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.now = 11
        self.client.context["request_id"] = "projection-refresh"
        self.assertEqual(runtime.run_once()["state"], "waiting_for_information")
        self.assertEqual(len(self.provider.messages), 1)

    def test_ordinary_clock_advance_during_thinking_keeps_candidate_valid(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "danger"}])
        self.provider.before = lambda: self.client.context.update(game_time=101)
        self.assertEqual(self.runtime().run_once()["state"], "submitted")
        self.assertEqual(len(self.client.offers), 1)

    def test_native_requirement_decision_is_kept_as_receipt_without_promoting_model_text(self):
        self.client.events = [{"id": "decided", "kind": "requirement_decision", "text": "refused",
                               "data": {"requirement_id": "incoming", "decision": "refused"}}]
        self.assertEqual(self.runtime().run_once()["state"], "memory_resynced")
        record = self.memory.retrieve(self.context)[0]
        self.assertEqual(record["kind"], "receipt")
        self.assertEqual(record["data"], {"requirement_id": "incoming", "decision": "refused",
                                          "native_event_kind": "requirement_decision"})

    def test_prompt_preserves_stable_requirement_decisions_for_structured_refusal(self):
        decisions = [{"requirement_id": "incoming", "source_event_id": "incoming", "source_sequence": 1,
                      "decision": "pending"}]
        request = {"context": self.context, "observations": {}, "requirement_decisions": decisions}
        messages = build_messages(request, {"revision": "r", "records": []}, self.config)
        self.assertEqual(json.loads(messages[1]["content"])["requirement_decisions"], decisions)
        self.assertIn("requirement_id", messages[0]["content"])

    def test_explicit_config_edit_renews_budget_and_unchanged_config_restart_waits(self):
        profile = Path(self.directory.name)
        (profile / "config.json").write_text(json.dumps(self.config))
        self.provider = FakeProvider([{"steps": [{"id": "a", "action": "invented", "args": {}}]},
                                      {"steps": [{"id": "b", "action": "wait", "args": {}}]}])
        runtime = AgentRuntime(load_config(profile), self.memory, self.client, self.provider,
                               profile=profile, clock=lambda: self.now)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.run_once()["state"], "rejected")
        self.config["personality"]["social_behavior"]["refuse"] = False
        (profile / "config.json").write_text(json.dumps(self.config))
        self.now = 11
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.assertEqual(len(self.provider.messages), 2)
        runtime.close()
        provider = FakeProvider()
        restarted = AgentRuntime(load_config(profile), self.memory, self.client, provider,
                                 profile=profile, clock=lambda: self.now)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.run_once()["state"], "waiting_for_information")
        self.assertEqual(provider.messages, [])

    def test_checkpoint_binds_captured_native_projection_and_preserves_true_file_revision(self):
        self.memory.ingest(self.context, [{"id": "heard", "kind": "statement", "text": "before save"}])
        file_revision = self.memory.revision
        self.client.context["memory_version"] = "captured-projection"
        self.client.checkpoint_requested = True
        self.client.strict_checkpoint = True
        runtime = self.runtime()
        runtime.start()
        params = next(params for method, params in self.client.calls if method == "checkpoint")
        reference = params["reference"]
        self.assertEqual(params["version"], "captured-projection")
        self.assertEqual(reference["projection_version"], "captured-projection")
        self.assertEqual(reference["revision"], file_revision)
        self.assertNotEqual(reference["revision"], reference["projection_version"])
        checkpoint = json.loads((self.memory.memory_root / "checkpoints" / (reference["id"] + ".json")).read_text())
        self.assertEqual(checkpoint["revision"], reference["revision"])
        self.assertEqual(self.client.saved_checkpoint, reference)
        restored = self.memory.restore(self.context, reference)
        self.assertEqual(restored["records"][0]["text"], "before save")

    def test_human_edit_after_checkpoint_creation_prevents_stale_checkpoint_handshake(self):
        self.client.context["memory_version"] = "captured-projection"
        self.client.checkpoint_requested = True
        original = self.memory.checkpoint

        def edit_after_creation(context):
            checkpoint = original(context)
            (Path(self.directory.name) / "background.md").write_text("Human edit after checkpoint capture")
            return checkpoint
        self.memory.checkpoint = edit_after_creation
        with self.assertRaisesRegex(RuntimeErrorCode, "memory_changed_during_checkpoint"):
            self.runtime().start()
        self.assertEqual([params for method, params in self.client.calls if method == "checkpoint"], [])

    def test_finite_tasks_submit_native_context_and_include_catalog_and_duties(self):
        self.config["duties"]["allowed_tasks"] = ["gather"]
        self.config["duties"].update(max_distance=8, item_types=["rock"], recipes=["rock_recipe"])
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.decision-one"
        self.client.task_summary = [{"id": "old", "kind": "gather", "state": "completed", "progress": 2}]
        self.provider = FakeProvider([{"mode": "append", "tasks": [
            {"id": "collect", "kind": "gather", "args": {"item_type": "rock", "count": 3},
             "quantity_mode": "inventory", "constraints": {"max_distance": 12}}]}])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.assertEqual(self.client.offer_methods, ["offer_tasks"])
        self.assertEqual(self.client.offers[0]["context"], self.client.context)
        payload = json.loads(self.provider.messages[0][1]["content"])
        self.assertEqual(payload["task_catalog"], self.client.task_catalog)
        self.assertEqual(payload["task_summary"], self.client.task_summary)
        self.assertEqual(payload["decision_id"], self.client.decision_id)
        self.assertEqual(payload["duties"], self.config["duties"])
        configure = next(params for method, params in self.client.calls if method == "configure")
        self.assertEqual(configure["duties"], self.config["duties"])
        self.assertEqual(self.memory.retrieve(self.context), [])  # Proposal is not a real task receipt.

    def test_task_prompt_allowlists_and_example_match_contract_and_player_requirement(self):
        request = {"context": self.context, "observations": {}, "task_catalog": task_catalog(),
                   "requirement_decisions": [{"requirement_id": "shown-player-requirement", "decision": "pending"}]}
        messages = build_messages(request, {"revision": "memory", "records": []}, self.config)
        system, payload = messages[0]["content"], json.loads(messages[1]["content"])
        top, rest = system.split("Top ONLY ", 1)[1].split(". Task ONLY\n", 1)
        fields = rest.split(".", 1)[0]
        self.assertEqual(set(top.split(",")), set(contract()["schemas"]["tasks"]["properties"]))
        self.assertEqual(set(fields.split(",")), set(contract()["schemas"]["task"]["properties"]))
        self.assertIn("Player tasks MUST each copy shown requirement_id", system)
        self.assertIn("omit only for autonomy", system)
        self.assertIn("Steps-only reflections", system)
        example = json.loads(next(line for line in system.splitlines() if line.startswith('{"tasks":')))
        self.assertEqual(example["tasks"][0]["requirement_id"], "shown")
        # The placeholder must be replaced by the actual shown requirement;
        # the production runtime alone supplies the actual request context.
        example["tasks"][0]["requirement_id"] = payload["requirement_decisions"][0]["requirement_id"]
        example["context"] = payload["context"]
        self.assertEqual(validate_tasks(example), example)

    def test_mixed_task_and_step_or_forged_context_is_not_submitted(self):
        self.client.task_catalog = task_catalog()
        for candidate in ({"tasks": [{"id": "one", "kind": "follow", "args": {}}], "steps": []},
                          {"context": {**self.context, "world_id": "invented"},
                           "tasks": [{"id": "one", "kind": "follow", "args": {}}]}):
            self.provider = FakeProvider([candidate])
            runtime = self.runtime()
            self.client.observations["new_decision"] = str(candidate)
            self.assertEqual(runtime.run_once()["state"], "rejected")
        self.assertEqual(self.client.offers, [])

    def test_mode_correction_guides_replanning_without_rewriting_rejected_candidate(self):
        request = {"context": self.context, "task_catalog": task_catalog(),
                   "task_summary": [{"id": "old-work", "kind": "gather", "state": "running"}]}
        snapshot = {"revision": "memory", "records": []}
        task = {"id": "new-work", "kind": "guard", "args": {}, "requirement_id": "shown"}
        provider = FakeProvider([{"mode": mode, "tasks": [task]} for mode in ("append", "prioritize")])
        first = provider.complete(build_messages(request, snapshot, self.config), on_wait=lambda: True).value
        first["context"] = deepcopy(self.context)
        validate_tasks(first)  # append remains valid wire syntax, not acceptance of a changed goal.
        with self.assertRaisesRegex(RuntimeErrorCode, "^mode_mismatch$"):
            if first.get("mode", "append") != "prioritize":
                raise RuntimeErrorCode("mode_mismatch")
        messages = build_messages(request, snapshot, self.config, correction={
            "code": "mode_mismatch", "expected_mode": "prioritize", "actual_mode": first["mode"]})
        payload = json.loads(messages[-1]["content"])
        self.assertEqual(payload["previous_candidate_error"], "mode_mismatch")
        feedback = payload["previous_candidate_feedback"]
        self.assertEqual(feedback["expected_mode"], "prioritize")
        self.assertEqual(feedback["actual_mode"], "append")
        self.assertIn("Set mode to expected_mode", feedback["instruction"])
        self.assertIn("refuse", feedback["instruction"])
        self.assertIn("append queues", messages[0]["content"])
        self.assertIn("prioritize pauses old work", messages[0]["content"])
        second = provider.complete(messages, on_wait=lambda: True).value
        second["context"] = deepcopy(self.context)
        validate_tasks(second)
        self.assertEqual(second["mode"], "prioritize")
        self.assertEqual(first["mode"], "append")  # No automatic correction or hidden coercion.
        self.assertEqual(request["task_summary"][0]["state"], "running")

    def test_mode_feedback_drops_untrusted_fields_and_invalid_mode_values(self):
        request, snapshot = {"context": self.context}, {"revision": "memory", "records": []}
        messages = build_messages(request, snapshot, self.config, correction={
            "code": "mode_mismatch", "expected_mode": "prioritize", "actual_mode": "raw-model-text",
            "instruction": "raw-model-instruction", "unknown": "raw-model-field"})
        payload = json.loads(messages[-1]["content"])
        feedback = payload["previous_candidate_feedback"]
        self.assertEqual(payload["previous_candidate_error"], "mode_mismatch")
        self.assertEqual(feedback["expected_mode"], "prioritize")
        self.assertNotIn("actual_mode", feedback)
        self.assertNotIn("raw-model", messages[-1]["content"])
        legacy = json.loads(build_messages(request, snapshot, self.config, correction="mode_mismatch")[-1]["content"])
        self.assertEqual(legacy["previous_candidate_error"], "mode_mismatch")
        self.assertIn("append", legacy["previous_candidate_feedback"]["instruction"])
        self.assertIn("prioritize", legacy["previous_candidate_feedback"]["instruction"])

    def test_native_dependency_rejection_sends_fixed_actionable_feedback_in_same_episode(self):
        self.config["limits"]["max_calls"] = 2
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.one"
        self.client.offer_errors = ["invalid_task_dependency", None]
        self.provider = FakeProvider([{"tasks": [{"id": name, "kind": "guard", "args": {}}]}
                                      for name in ("bad-dependency", "fixed")])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        corrected = json.loads(self.provider.messages[1][-1]["content"])
        self.assertEqual(corrected["previous_candidate_error"], "invalid_task_dependency")
        self.assertIn("depends_on", corrected["previous_candidate_feedback"]["instruction"])
        self.assertEqual(runtime._episode["calls"], 2)
        self.assertEqual(runtime._calls, 2)
        self.assertEqual([offer["tasks"][0]["id"] for offer in self.client.offers], ["bad-dependency", "fixed"])

    def test_native_task_rejection_is_corrected_in_same_paid_episode(self):
        self.config["limits"]["max_calls"] = 3
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.one"
        self.client.offer_errors = ["task_outside_duty_scope", None]
        self.provider = FakeProvider([
            {"tasks": [{"id": "bad-target", "kind": "gather", "args": {"item_type": "rock", "count": 1}}]},
            {"tasks": [{"id": "safe", "kind": "follow", "args": {}}]},
        ])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.assertEqual(runtime._episode["calls"], 2)
        self.assertEqual(runtime._calls, 2)
        self.assertEqual(self.client.offer_methods, ["offer_tasks", "offer_tasks"])
        corrected = json.loads(self.provider.messages[1][-1]["content"])
        self.assertEqual(corrected["previous_candidate_error"], "task_outside_duty_scope")
        self.assertEqual(self.client.offers[0]["context"], self.client.offers[1]["context"])

    def test_repeated_native_rejection_exhausts_same_episode_without_renewal(self):
        self.config["limits"]["max_calls"] = 2
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.one"
        self.client.offer_errors = ["task_payload_conflict"] * 2
        self.provider = FakeProvider([{"tasks": [{"id": "old", "kind": "follow", "args": {}}]}] * 2)
        runtime = self.runtime()
        self.assertEqual(runtime.run_once(), {"state": "rejected", "code": "task_payload_conflict"})
        self.assertEqual(runtime._calls, 2)
        self.now = 11
        self.client.context.update(request_id="fresh-poll", game_time=150)
        self.assertEqual(runtime.run_once()["state"], "waiting_for_information")
        self.assertEqual(len(self.provider.messages), 2)
        self.assertEqual(runtime._calls, 2)

    def test_native_dependency_and_task_limit_rejections_allow_same_episode_correction(self):
        self.config["limits"]["max_calls"] = 3
        self.client.task_catalog = task_catalog()
        for index, code in enumerate(("invalid_task_dependency", "task_limit"), 1):
            with self.subTest(code=code):
                self.client.decision_id = "load." + code
                self.client.offer_errors = [code, None]
                self.provider = FakeProvider([{"tasks": [{"id": "follow", "kind": "follow", "args": {}}]}] * 2)
                runtime = self.runtime()
                self.assertEqual(runtime.run_once()["state"], "submitted")
                self.assertEqual(runtime._episode["calls"], 2)
                self.assertEqual(runtime._calls, index * 2)
                corrected = json.loads(self.provider.messages[1][-1]["content"])
                self.assertEqual(corrected["previous_candidate_error"], code)

    def test_legacy_plan_native_rejection_also_has_bounded_correction(self):
        self.config["limits"]["max_calls"] = 2
        self.client.offer_errors = ["plan_not_allowed", None]
        self.provider = FakeProvider([{"steps": [{"id": name, "action": "wait", "args": {}}]} for name in ("one", "two")])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.assertEqual(runtime._calls, 2)
        self.assertEqual(self.client.offer_methods, ["offer_plan", "offer_plan"])

    def test_submit_disconnect_does_not_spend_another_model_call(self):
        self.config["limits"]["max_calls"] = 3
        self.client.offer_errors = ["disconnected"]
        runtime = self.runtime()
        with self.assertRaisesRegex(TransportError, "^disconnected$"):
            runtime.run_once()
        self.assertEqual(runtime._calls, 1)
        self.assertEqual(len(self.provider.messages), 1)

    def test_submit_stale_context_discards_without_correction_call(self):
        self.config["limits"]["max_calls"] = 3
        self.client.offer_errors = ["stale_request"]
        runtime = self.runtime()
        self.assertEqual(runtime.run_once(), {"state": "discarded", "code": "request_invalidated"})
        self.assertEqual(runtime._calls, 1)

    def test_submit_pending_candidate_waits_without_correction_call(self):
        self.config["limits"]["max_calls"] = 3
        self.client.offer_errors = ["candidate_pending"]
        runtime = self.runtime()
        self.assertEqual(runtime.run_once(), {"state": "waiting_for_information", "code": "candidate_pending"})
        self.assertEqual(runtime._calls, 1)

    def test_stable_native_decision_prevents_progress_and_clock_budget_renewal(self):
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.one"
        self.provider = FakeProvider([{"steps": [{"id": "bad", "action": "invented", "args": {}}]}])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "rejected")
        self.now = 11
        self.client.context.update(request_id="new-poll", game_time=120)
        self.client.observations["actor"].update(position=[4, 2, 0], hp=80)
        self.client.task_summary = [{"id": "a", "kind": "gather", "state": "running", "progress": 5}]
        self.assertEqual(runtime.run_once()["state"], "waiting_for_information")
        self.assertEqual(len(self.provider.messages), 1)
        self.client.decision_id = "load.two"
        self.provider.values.append({"steps": [{"id": "one", "action": "wait", "args": {}}]})
        self.assertEqual(runtime.run_once()["state"], "submitted")
        self.assertEqual(len(self.provider.messages), 2)

    def test_new_native_decision_while_thinking_discards_old_candidate(self):
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.one"
        self.provider.before = lambda: setattr(self.client, "decision_id", "load.two")
        self.assertEqual(self.runtime().run_once()["state"], "discarded")
        self.assertEqual(self.client.offers, [])

    def test_prefetch_survives_native_progress_until_the_candidate_is_adopted(self):
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.prefetch"
        self.client.task_summary = [{"id": "g", "kind": "gather", "state": "running",
                                     "progress": 1, "requirement_id": "player-gather"}]

        def advance():
            self.client.task_summary[0]["progress"] = 2
            self.client.receipts = [{"operation_id": "g.2", "action": "gather", "state": "succeeded",
                                     "code": "gathered", "detail": {"count": 1}, "game_time": 100},
                                    {"operation_id": "g.accepted", "action": "task", "state": "succeeded",
                                     "requirement_id": "player-gather", "code": "task_accepted", "game_time": 100,
                                     "detail": {"task_id": "g", "task_kind": "gather", "task_state": "queued",
                                                "reason": "accepted", "progress": 0, "target": 3}}]
        self.provider = FakeProvider([{"tasks": [{"id": "next", "kind": "follow", "args": {}}]}],
                                     before=advance)
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        offered = self.client.offers[0]
        self.assertEqual(offered["context"], self.client.context)
        synced = len([method for method, _ in self.client.calls if method == "sync_memory"])
        self.client.planning_state = "candidate_pending"
        self.assertEqual(runtime.run_once(), {"state": "waiting_for_information", "code": "candidate_pending"})
        self.assertEqual(len([method for method, _ in self.client.calls if method == "sync_memory"]), synced)
        self.client.planning_state = "idle"
        runtime.run_once()
        remembered = self.memory.retrieve(self.client.context, limit=20)
        self.assertTrue(any(record.get("data", {}).get("operation_id") == "g.2" for record in remembered))
        self.assertTrue(any(record["kind"] == "commitment" and record["status"] == "accepted"
                            for record in remembered))
        self.assertEqual(len(self.provider.messages), 1)
        self.assertEqual(len(self.client.offers), 1)
        self.assertEqual(runtime._calls, 1)

    def test_progress_does_not_hide_a_new_context_or_external_memory_edit(self):
        self.client.task_catalog = task_catalog()
        original = deepcopy(self.client.context)
        changes = {
            "world": lambda: self.client.context.update(world_id="new-world"),
            "load": lambda: self.client.context.update(load_epoch="new-load"),
            "policy": lambda: self.client.context.update(policy_version="new-policy"),
            "request": lambda: self.client.context.update(request_id="cancelled-request"),
            "decision": lambda: setattr(self.client, "decision_id", "new-goal"),
            "memory": lambda: (Path(self.directory.name) / "background.md").write_text("Human edit"),
        }
        for name, change in changes.items():
            with self.subTest(change=name):
                self.client.context = deepcopy(original)
                self.client.decision_id = "load." + name
                self.client.receipts = []

                def progress_and_change():
                    self.client.receipts = [{"operation_id": name, "action": "gather", "state": "succeeded",
                                             "code": "gathered", "game_time": 100}]
                    change()
                self.provider = FakeProvider([{"tasks": [{"id": "next", "kind": "follow", "args": {}}]}],
                                             before=progress_and_change)
                result = self.runtime().run_once()
                self.assertEqual(result, {"state": "discarded", "code": "request_invalidated"})
                self.assertEqual(self.client.offers, [])
                self.assertEqual(len(self.provider.messages), 1)

    def test_pending_candidate_does_not_hide_human_memory_edits(self):
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.prefetch"
        self.provider = FakeProvider([{"tasks": [{"id": "next", "kind": "follow", "args": {}}]}])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        version = self.client.context["memory_version"]
        self.client.planning_state = "candidate_pending"
        (Path(self.directory.name) / "background.md").write_text("Human changed the decision background")
        self.assertEqual(runtime.run_once()["state"], "cooldown")
        self.assertNotEqual(self.client.context["memory_version"], version)
        self.assertEqual(len(self.provider.messages), 1)

    def test_checkpoint_during_thinking_captures_progress_and_discards_old_reply(self):
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.prefetch"
        self.client.strict_checkpoint = True

        def progress_and_save():
            self.client.receipts = [{"operation_id": "g.saved", "action": "gather", "state": "succeeded",
                                     "code": "gathered", "game_time": 100}]
            self.client.checkpoint_requested = True
        self.provider = FakeProvider([{"tasks": [{"id": "next", "kind": "follow", "args": {}}]}],
                                     before=progress_and_save)
        result = self.runtime().run_once()
        self.assertEqual(result, {"state": "discarded", "code": "request_invalidated"})
        self.assertEqual(self.client.offers, [])
        reference = self.client.saved_checkpoint
        restored = self.memory.restore(self.client.context, reference)
        self.assertTrue(any(record.get("data", {}).get("operation_id") == "g.saved"
                            for record in restored["records"]))

    def test_withdrawn_requirement_rejection_only_corrects_against_active_requirements(self):
        self.config["limits"]["max_calls"] = 2
        self.client.task_catalog = task_catalog()
        self.client.decision_id = "load.withdrawal"
        self.client.offer_errors = ["requirement_withdrawn", None]
        self.provider = FakeProvider([{"tasks": [{"id": identity, "kind": "follow", "args": {},
                                                   "requirement_id": requirement}]}
                                      for identity, requirement in (("old-task", "withdrawn"), ("new-task", "active"))])
        runtime = self.runtime()
        self.assertEqual(runtime.run_once()["state"], "submitted")
        correction = json.loads(self.provider.messages[1][-1]["content"])
        self.assertEqual(correction["previous_candidate_error"], "requirement_withdrawn")
        self.assertIn("Do not rename", correction["previous_candidate_feedback"]["instruction"])
        self.assertIn("active requirements", correction["previous_candidate_feedback"]["instruction"])
        self.assertEqual(runtime._calls, 2)

    def test_consumption_survives_restart_read_old_branch_and_new_episode(self):
        self.config["limits"]["session_max_calls"] = 1
        runtime = self.runtime()
        runtime.run_once()
        charged_tokens = runtime._tokens
        runtime.close()
        self.provider = FakeProvider()
        self.client.context.update(load_epoch="old-save-reloaded", branch_id="old-branch", request_id="fresh")
        self.client.observations["changed"] = "new decision"
        restarted = self.runtime()
        with self.assertRaisesRegex(RuntimeErrorCode, "session_call_budget_exhausted"):
            restarted.run_once()
        self.assertEqual(restarted._calls, 1)
        self.assertEqual(restarted._tokens, charged_tokens)
        self.assertEqual(self.provider.messages, [])
        body = (self.memory.root / "runtime-budget.json").read_text()
        self.assertNotIn("old-save", body)
        self.assertNotIn("profile", body)

    def test_uncertain_call_is_charged_before_provider_and_survives_restart(self):
        self.config["limits"]["session_max_calls"] = 1
        def uncertain(messages, **kwargs):
            data = json.loads((self.memory.root / "runtime-budget.json").read_text())
            self.assertEqual(next(iter(data["accounts"].values()))["calls"], 1)
            raise TransportError("disconnected")
        self.provider.complete = uncertain
        runtime = self.runtime()
        with self.assertRaises(TransportError):
            runtime.run_once()
        runtime.close()
        self.provider = FakeProvider()
        self.client.observations["new_information"] = "cannot refund an uncertain call"
        with self.assertRaisesRegex(RuntimeErrorCode, "session_call_budget_exhausted"):
            self.runtime().run_once()
        self.assertEqual(self.provider.messages, [])

    def test_explicit_period_grants_new_budget_but_personality_edits_do_not(self):
        self.config["limits"]["session_max_calls"] = 1
        runtime = self.runtime()
        runtime.run_once()
        runtime.close()
        self.config["personality"]["traits"]["caution"] = 0.8
        self.provider = FakeProvider()
        self.client.observations["fresh"] = "information"
        with self.assertRaisesRegex(RuntimeErrorCode, "session_call_budget_exhausted"):
            self.runtime().run_once()
        self.config["limits"]["budget_period"] = "human-selected-new-period"
        self.assertEqual(self.runtime().run_once()["state"], "submitted")
        self.assertEqual(len(self.provider.messages), 1)

    def test_actual_usage_can_only_increase_durable_reservation(self):
        runtime = self.runtime()
        runtime.run_once()
        before = runtime._tokens
        runtime._charge_usage(Completion({}, {"total_tokens": 1}), before)
        self.assertEqual(runtime._tokens, before)
        runtime._charge_usage(Completion({}, {"total_tokens": before + 71}), before)
        self.assertEqual(runtime._tokens, before + 71)
        data = json.loads((self.memory.root / "runtime-budget.json").read_text())
        self.assertEqual(next(iter(data["accounts"].values()))["tokens"], before + 71)

    def test_task_receipts_are_remembered_during_cooldown_without_extra_model_call(self):
        runtime = self.runtime()
        runtime.run_once()
        self.client.receipts = [{"operation_id": "task.complete", "action": "task", "state": "succeeded",
                                 "code": "task_completed", "game_time": 103,
                                 "detail": {"task_id": "collect", "task_kind": "gather", "task_state": "completed",
                                            "reason": "target_reached", "progress": 3, "target": 3}}]
        self.client.context["game_time"] = 103
        self.assertEqual(runtime.run_once()["state"], "cooldown")
        records = self.memory.retrieve(self.client.context, "collect", 20)
        receipt = next(record for record in records if record["kind"] == "receipt")
        self.assertEqual(receipt["data"]["detail"]["progress"], 3)
        self.assertEqual(len(self.provider.messages), 1)


if __name__ == "__main__":
    unittest.main()
