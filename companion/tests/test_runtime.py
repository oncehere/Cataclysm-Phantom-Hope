from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from cph_ai_companion.config import default_config, load_config
from cph_ai_companion.memory import MemoryStore
from cph_ai_companion.protocol import action_catalog
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

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def request(self, method, params=None):
        self.calls.append((method, deepcopy(params)))
        if method == "status":
            return {"context": deepcopy(self.context), "state": self.state,
                    "profile_id": self.profile_id, "actor_id": self.context["actor_id"],
                    "checkpoint_requested": self.checkpoint_requested,
                    "checkpoint_context": deepcopy(self.context), "saved_checkpoint": self.saved_checkpoint,
                    "receipts": deepcopy(self.receipts)}
        if method == "configure":
            self.profile_id = params["profile_id"]
            return {}
        if method == "sync_memory":
            self.context["memory_version"] = params["version"]
            return {}
        if method == "take_request":
            return {"context": deepcopy(self.context), "observations": deepcopy(self.observations),
                    "events": deepcopy(self.events), "action_catalog": action_catalog()[:1]}
        if method == "offer_plan":
            self.offers.append(deepcopy(params))
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


if __name__ == "__main__":
    unittest.main()
