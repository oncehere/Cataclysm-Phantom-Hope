from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from cph_ai_companion.config import default_config
from cph_ai_companion.memory import MemoryStore
from cph_ai_companion.protocol import action_catalog
from cph_ai_companion.provider import Completion, ProviderError
from cph_ai_companion.runtime import AgentRuntime, RuntimeErrorCode, build_messages, _engine_cognition
from cph_ai_companion.transport import TransportError


class FakeClient:
    def __init__(self, context):
        self.context = deepcopy(context)
        self.events = []
        self.calls = []
        self.offers = []
        self.connected = False
        self.state = "active"
        self.checkpoint_requested = False
        self.saved_checkpoint = None
        self.receipts = []
        self.profile_id = "profile"

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
            return {"context": deepcopy(self.context), "observations": {"actor": {"id": 7}},
                    "events": deepcopy(self.events), "action_catalog": action_catalog()[:1]}
        if method == "offer_plan":
            self.offers.append(deepcopy(params))
            return {"state": "accepted", "plan_id": "p"}
        if method == "checkpoint":
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
        original = self.client.request
        self.client.request = lambda *args, **kwargs: (_ for _ in ()).throw(TransportError("disconnected"))
        self.assertEqual(runtime.run()["state"], "disconnected")
        self.assertEqual([method for method, _ in self.client.calls if method == "cancel"], [])
        self.assertTrue(self.provider.closed)

    def test_save_prepare_records_reference_without_claiming_game_save_success(self):
        self.client.checkpoint_requested = True
        runtime = self.runtime()
        runtime.start()
        prepared = [params for method, params in self.client.calls if method == "checkpoint"]
        self.assertEqual(len(prepared), 1)
        self.assertEqual(set(prepared[0]["reference"]), {"id", "revision"})
        self.assertTrue((Path(self.directory.name) / "memory/checkpoints" / (prepared[0]["reference"]["id"] + ".json")).exists()
                        or (Path(self.directory.name) / "checkpoints" / (prepared[0]["reference"]["id"] + ".json")).exists())

    def test_context_budget_rejects_unsliceable_observation(self):
        request = {"context": self.context, "observations": {"text": "x" * 50000}}
        with self.assertRaisesRegex(RuntimeErrorCode, "context_budget_exceeded"):
            build_messages(request, {"revision": "r", "records": []}, self.config)


if __name__ == "__main__":
    unittest.main()
