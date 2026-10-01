"""File edits, history deletion and save recovery are observable contracts."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cph_ai_companion.memory import MAX_EVENT_DATA_BYTES, MAX_MANDATORY_RECORDS, MemoryStore, MemoryStoreError


CONTEXT = {"world_id": "world-a", "branch_id": "branch-a", "actor_id": "npc-7",
           "game_time": 100, "event_watermark": 4}


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.profile = self.base / "profile"
        self.stores = []

    def tearDown(self):
        for store in reversed(self.stores):
            store.close()
        self.temp.cleanup()

    def open(self, config=None, profile=None):
        store = MemoryStore(profile or self.profile, config)
        self.stores.append(store)
        return store

    def record_paths(self, store, record_id):
        return list((store.memory_root / "records" / record_id).glob("*.json"))

    def edit(self, path, **changes):
        value = json.loads(path.read_text(encoding="utf-8"))
        value.update(changes)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_single_writer_locks_profile_and_shared_memory_but_not_editors(self):
        memory = str(self.base / "shared")
        first = self.open({"paths": {"memory": memory}})
        with self.assertRaisesRegex(MemoryStoreError, "writer_locked"):
            self.open({"paths": {"memory": memory}})
        with self.assertRaisesRegex(MemoryStoreError, "writer_locked"):
            self.open({"paths": {"memory": memory}}, self.base / "other-profile")
        first.close()
        self.open({"paths": {"memory": memory}}, self.base / "other-profile")

    def test_configured_paths_and_background_edit_invalidate_snapshot(self):
        background = self.base / "person.md"
        background.write_text("固定人物背景", encoding="utf-8")
        store = self.open({"paths": {"memory": str(self.base / "custom-records"),
                                     "background": str(background)}})
        store.ingest(CONTEXT, [{"id": "seen", "kind": "observation", "text": "药柜"}])
        before = store.snapshot(CONTEXT)
        self.assertEqual(before["background"], "固定人物背景")
        self.assertFalse((self.profile / "memory").exists())
        background.write_text("人物背景手工修订", encoding="utf-8")
        self.assertFalse(store.is_current(before["revision"]))
        self.assertEqual(store.snapshot(CONTEXT)["background"], "人物背景手工修订")
        store.checkpoint(CONTEXT)
        self.assertEqual(background.read_text(encoding="utf-8"), "人物背景手工修订")
        self.assertTrue(list((self.base / "custom-records" / "checkpoints").glob("*.json")))

    def test_redelivery_is_idempotent_without_retiming_or_revision_changes(self):
        store = self.open()
        event = {"id": "player-claim", "kind": "statement", "text": "这里没有敌人"}
        ids = store.ingest(CONTEXT, [event])
        revision = store.revision
        self.assertEqual(store.ingest({**CONTEXT, "game_time": 200, "event_watermark": 10}, [event]), ids)
        self.assertEqual(store.revision, revision)
        record = store.retrieve(CONTEXT)[0]
        self.assertEqual(record["kind"], "statement")
        self.assertEqual(record["context"]["game_time"], 100)
        with self.assertRaisesRegex(MemoryStoreError, "memory_event_kind_changed"):
            store.ingest(CONTEXT, [{**event, "kind": "receipt"}])

    def test_manual_edit_wins_and_replayed_event_does_not_loop_revisions(self):
        store = self.open()
        event = {"id": "opinion", "kind": "belief", "text": "玩家可信"}
        rid = store.ingest(CONTEXT, [event])[0]
        path = self.record_paths(store, rid)[0]
        self.edit(path, text="我对玩家仍有疑虑", confidence=0.2)
        self.assertTrue(store.refresh())
        revision = store.revision
        store.ingest(CONTEXT, [event])
        self.assertEqual(store.revision, revision)
        store.ingest(CONTEXT, [{**event, "text": "自动判断玩家非常可信"}])
        self.assertEqual(store.retrieve(CONTEXT)[0]["text"], "我对玩家仍有疑虑")
        self.assertEqual(store.retrieve(CONTEXT)[0]["provenance"], "manual")
        self.assertEqual(len(self.record_paths(store, rid)), 2)
        revision = store.revision
        store.ingest(CONTEXT, [{**event, "text": "自动判断玩家非常可信"}])
        self.assertEqual(store.revision, revision)
        store.close()
        recovered = self.open()
        self.assertEqual(recovered.retrieve(CONTEXT)[0]["text"], "我对玩家仍有疑虑")

    def test_delete_removes_all_managed_versions_and_dependent_memories(self):
        store = self.open()
        event = {"id": "claim", "kind": "statement", "text": "玩家保证没有危险"}
        claim = store.ingest(CONTEXT, [event])[0]
        belief = store.ingest(CONTEXT, [{"id": "belief", "kind": "belief", "text": "这里安全",
                                         "source_ids": [claim]}])[0]
        summary = store.ingest(CONTEXT, [{"id": "summary", "kind": "summary", "text": "安全路线",
                                          "source_ids": [belief]}])[0]
        checkpoint = store.checkpoint(CONTEXT)
        old_bytes = self.record_paths(store, claim)[0].read_bytes()
        self.record_paths(store, claim)[0].unlink()
        revision = store.revision
        self.assertTrue(store.refresh())
        self.assertFalse(store.is_current(revision))
        self.assertEqual(store.retrieve(CONTEXT), [])
        for rid in (claim, belief, summary):
            self.assertEqual(self.record_paths(store, rid), [])
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])
        store.ingest(CONTEXT, [event])
        self.assertEqual(store.retrieve(CONTEXT), [])
        # Copying an archived body back cannot remove the durable tombstone.
        copied = store.memory_root / "records" / claim / "copied.json"
        copied.write_bytes(old_bytes)
        store.refresh()
        self.assertFalse(copied.exists())
        # Human audit is preserved; it is never an automatic learning source.
        self.assertTrue(list((store.memory_root / "evidence").glob("*/*.json")))
        store.close()
        reopened = self.open()
        self.assertEqual(reopened.restore(CONTEXT, checkpoint)["records"], [])

    def test_source_edit_invalidates_derived_summary(self):
        store = self.open()
        source = store.ingest(CONTEXT, [{"id": "seen", "kind": "observation", "text": "药柜是空的"}])[0]
        child = store.ingest(CONTEXT, [{"id": "guess", "kind": "belief", "text": "没有药了",
                                       "source_ids": [source]}])[0]
        self.edit(self.record_paths(store, source)[0], text="药柜尚未检查")
        store.refresh()
        self.assertEqual(self.record_paths(store, child), [])
        self.assertEqual([r["text"] for r in store.retrieve(CONTEXT)], ["药柜尚未检查"])

    def test_delete_invalidates_historical_summary_even_after_its_head_changed(self):
        store = self.open()
        source = store.ingest(CONTEXT, [{"id": "seen", "kind": "observation", "text": "药柜"}])[0]
        summary = {"id": "summary", "kind": "summary", "text": "有药柜", "source_ids": [source]}
        derived = store.ingest(CONTEXT, [summary])[0]
        checkpoint = store.checkpoint(CONTEXT)
        store.ingest(CONTEXT, [{**summary, "text": "新的无引用摘要", "source_ids": []}])
        self.record_paths(store, source)[0].unlink()
        store.refresh()
        self.assertEqual(self.record_paths(store, derived), [])
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])

    def test_entire_batch_is_validated_before_writes(self):
        store = self.open()
        revision = store.revision
        with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_record"):
            store.ingest(CONTEXT, [{"id": "first", "kind": "observation", "text": "valid"},
                                    {"id": "last", "kind": "belief", "text": 42}])
        self.assertEqual(store.revision, revision)
        self.assertEqual(list((store.memory_root / "records").glob("*/*.json")), [])
        self.assertEqual(store.retrieve(CONTEXT), [])

    def test_actor_branch_and_time_boundaries_are_checked_before_retrieval(self):
        store = self.open()
        store.ingest(CONTEXT, [{"id": "own", "kind": "observation", "text": "我的见闻"}])
        store.ingest({**CONTEXT, "actor_id": "other-npc"}, [{"id": "secret", "kind": "observation", "text": "他人秘密"}])
        store.ingest({**CONTEXT, "branch_id": "other-branch"}, [{"id": "branch", "kind": "observation", "text": "别的分支"}])
        store.ingest({**CONTEXT, "game_time": 200}, [{"id": "future", "kind": "observation", "text": "未来见闻"}])
        self.assertEqual([r["text"] for r in store.retrieve(CONTEXT)], ["我的见闻"])

    def test_checkpoint_selects_old_cognition_and_preserves_manual_changes(self):
        store = self.open()
        event = {"id": "belief", "kind": "belief", "text": "值得信任"}
        rid = store.ingest(CONTEXT, [event])[0]
        checkpoint = store.checkpoint(CONTEXT)
        store.ingest({**CONTEXT, "game_time": 110}, [{**event, "text": "可疑"}])
        restored = store.restore({**CONTEXT, "branch_id": "load-branch"}, {"id": checkpoint["id"]})
        self.assertEqual(restored["records"][0]["text"], "值得信任")
        self.assertEqual(restored["records"][0]["continuity"], "imported_experience_not_current_world_fact")
        self.assertEqual(restored["records"][0]["context"]["branch_id"], "branch-a")
        self.assertTrue(all("continuity" not in json.loads(path.read_text()) for path in self.record_paths(store, rid)))
        with self.assertRaisesRegex(MemoryStoreError, "checkpoint_context_mismatch"):
            store.restore({**CONTEXT, "actor_id": "other-npc"}, checkpoint)
        paths = self.record_paths(store, rid)
        current = next(p for p in paths if json.loads(p.read_text())["text"] == "可疑")
        self.edit(current, text="手工决定暂不信任")
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"][0]["text"], "手工决定暂不信任")

    def test_retain_policy_does_not_roll_back_to_checkpoint(self):
        store = self.open({"memory": {"continuity": {"load_experiences": "retain"}}})
        event = {"id": "belief", "kind": "belief", "text": "过去的判断"}
        store.ingest(CONTEXT, [event])
        checkpoint = store.checkpoint(CONTEXT)
        store.ingest({**CONTEXT, "game_time": 110}, [{**event, "text": "现在的判断"}])
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"][0]["text"], "现在的判断")

    def test_new_world_experiences_require_explicit_archive_and_are_labelled(self):
        store = self.open()
        store.ingest(CONTEXT, [{"id": "seen", "kind": "observation", "text": "旧世界的药柜"}])
        checkpoint = store.checkpoint(CONTEXT)
        other = {**CONTEXT, "world_id": "new-world", "actor_id": "npc-99"}
        self.assertEqual(store.retrieve(other), [])
        store.close()
        store = self.open({"memory": {"continuity": {"new_world_experiences": "selected_archives",
                                                       "selected_archives": [checkpoint["id"]]}}})
        imported = store.retrieve(other)[0]
        self.assertEqual(imported["continuity"], "imported_experience_not_current_world_fact")
        self.assertEqual(imported["context"]["world_id"], "world-a")

    def test_new_world_growth_can_retain_without_importing_world_events(self):
        store = self.open({"memory": {"continuity": {"new_world_personality_growth": "retain"}}})
        store.ingest(CONTEXT, [{"id": "growth", "kind": "growth", "text": "学会谨慎"},
                                {"id": "event", "kind": "observation", "text": "药柜的位置"}])
        self.assertEqual([r["text"] for r in store.retrieve({**CONTEXT, "world_id": "new-world"})], ["学会谨慎"])

    def test_foreign_growth_entry_is_frozen_across_updates_loads_and_restarts(self):
        config = {"memory": {"continuity": {"new_world_personality_growth": "retain"}}}
        store = self.open(config)
        store.ingest(CONTEXT, [{"id": "danger", "kind": "receipt", "text": "Saw danger"},
                                {"id": "lesson", "kind": "growth", "text": "Entry lesson", "source_ids": ["danger"]}])
        other = {**CONTEXT, "world_id": "new-world"}
        first = store.snapshot(other)
        self.assertEqual([r["text"] for r in first["records"]], ["Entry lesson"])
        store.ingest({**CONTEXT, "game_time": 200},
                     [{"id": "lesson", "kind": "growth", "text": "Later foreign lesson", "source_ids": ["danger"]}])
        reloaded = {**other, "branch_id": "new-load"}
        self.assertEqual([r["text"] for r in store.retrieve(reloaded)], ["Entry lesson"])
        store.close()
        reopened = self.open(config)
        records = reopened.snapshot(reloaded)["records"]
        self.assertEqual([r["text"] for r in records], ["Entry lesson"])
        self.assertEqual(records[0]["context"], CONTEXT)
        self.assertEqual(records[0]["continuity"], "imported_experience_not_current_world_fact")

    def test_explicit_growth_policy_and_archive_expansion_choose_new_entry_versions(self):
        store = self.open()
        other = {**CONTEXT, "world_id": "new-world"}
        self.assertEqual(store.retrieve(other), [])
        event = {"id": "lesson", "kind": "growth", "text": "Enabled entry"}
        store.ingest(CONTEXT, [event])
        store.continuity["new_world_personality_growth"] = "retain"
        self.assertEqual([r["text"] for r in store.retrieve(other)], ["Enabled entry"])
        later = {**CONTEXT, "game_time": 200}
        store.ingest(later, [{**event, "text": "Explicit archive entry"}])
        archive = store.checkpoint(later)
        self.assertEqual([r["text"] for r in store.retrieve(other)], ["Enabled entry"])
        store.continuity["selected_archives"] = [archive["id"]]
        self.assertEqual([r["text"] for r in store.retrieve(other)], ["Explicit archive entry"])
        store.continuity["new_world_personality_growth"] = "reset"
        self.assertEqual(store.retrieve(other), [])

    def test_frozen_foreign_growth_still_honors_manual_edits_and_source_deletion(self):
        store = self.open({"memory": {"continuity": {"new_world_personality_growth": "retain"}}})
        source, growth = store.ingest(CONTEXT, [
            {"id": "danger", "kind": "receipt", "text": "Saw danger"},
            {"id": "lesson", "kind": "growth", "text": "Entry lesson", "source_ids": ["danger"]}])
        other = {**CONTEXT, "world_id": "new-world"}
        store.retrieve(other)
        store.ingest({**CONTEXT, "game_time": 200},
                     [{"id": "lesson", "kind": "growth", "text": "Automatic later lesson", "source_ids": ["danger"]}])
        self.edit(store._safe(store._state["heads"][growth]), text="Human correction")
        self.assertEqual(store.retrieve(other)[0]["text"], "Human correction")
        self.assertEqual(store.retrieve(other)[0]["provenance"], "manual")
        self.record_paths(store, source)[0].unlink()
        self.assertEqual(store.retrieve(other), [])
        self.assertEqual(self.record_paths(store, growth), [])
        store.ingest(CONTEXT, [{"id": "danger", "kind": "receipt", "text": "Saw danger"}])
        self.assertEqual(store.retrieve(other), [])

    def test_schema_one_without_import_entries_migrates_without_changing_format(self):
        config = {"memory": {"continuity": {"new_world_personality_growth": "retain"}}}
        store = self.open(config)
        store.ingest(CONTEXT, [{"id": "lesson", "kind": "growth", "text": "Legacy lesson"}])
        manifest = sorted((store.memory_root / "manifests").glob("*.json"))[-1]
        store.close()
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value.pop("imports", None)
        manifest.write_text(json.dumps(value), encoding="utf-8")
        migrated = self.open(config)
        other = {**CONTEXT, "world_id": "new-world"}
        self.assertEqual([r["text"] for r in migrated.retrieve(other)], ["Legacy lesson"])
        current = json.loads(sorted((migrated.memory_root / "manifests").glob("*.json"))[-1].read_text())
        self.assertEqual(current["schema_version"], 1)
        self.assertTrue(current["imports"])

    def test_snapshot_protects_pending_commitment_and_goal_receipt_from_irrelevant_summaries(self):
        store = self.open()
        events = [{"id": f"diary-{i}", "kind": "summary", "text": "Unrelated diary", "importance": 1}
                  for i in range(120)]
        events.extend([
            {"id": "crafted", "kind": "receipt", "text": "crafted", "importance": 0.1,
             "data": {"state": "succeeded", "action": "craft", "detail": {"item_type": "bandages"}}},
            {"id": "promise", "kind": "commitment", "status": "accepted", "text": "Deliver bandages",
             "importance": 0.1, "source_ids": ["crafted"]}])
        ids = store.ingest(CONTEXT, events)
        request = {"observations": {"actor": {"known_information": {"goal": "Deliver bandages"}}}}
        snapshot = store.snapshot({**CONTEXT, "game_time": 10000000}, request)
        self.assertEqual(set(snapshot["mandatory_record_ids"]), set(ids[-2:]))
        self.assertEqual({record["id"] for record in snapshot["records"]}, set(ids[-2:]))
        self.assertTrue(all(record["recall_weight"] < 0.05 for record in snapshot["records"]))
        self.assertEqual(len(self.record_paths(store, ids[0])), 1)  # forgetting retains audit/records

    def test_snapshot_preserves_more_than_one_hundred_obligations_and_bounds_overflow(self):
        store = self.open()
        ids = store.ingest(CONTEXT, [{"id": f"promise-{i}", "kind": "commitment", "status": "accepted",
                                      "text": f"Promise number {i}"} for i in range(101)])
        snapshot = store.snapshot(CONTEXT)
        self.assertEqual(set(snapshot["mandatory_record_ids"]), set(ids))
        self.assertEqual(len(snapshot["records"]), 101)
        store.ingest(CONTEXT, [{"id": f"extra-{i}", "kind": "commitment", "status": "accepted",
                                "text": f"Extra obligation {i}"}
                               for i in range(MAX_MANDATORY_RECORDS - 100)])
        with self.assertRaisesRegex(MemoryStoreError, "mandatory_context_too_large"):
            store.snapshot(CONTEXT)

    def test_pending_requirement_selects_relevant_receipts_and_not_whole_diary(self):
        store = self.open()
        ids = store.ingest(CONTEXT, [
            {"id": "crafted", "kind": "receipt", "text": "crafted",
             "data": {"state": "succeeded", "detail": {"item_type": "bandages"}}},
            {"id": "diary", "kind": "summary", "text": "Unrelated sunny afternoon", "importance": 1}])
        request = {"requirement_decisions": [{"requirement_id": "ask", "decision": "pending"}],
                   "events": [{"kind": "statement", "text": "Please bring bandages", "data": {"requirement_id": "ask"}}]}
        snapshot = store.snapshot(CONTEXT, request)
        self.assertEqual(snapshot["mandatory_record_ids"], [ids[0]])
        self.assertEqual([record["id"] for record in snapshot["records"]], [ids[0]])

    def test_pending_requirement_text_protects_receipt_after_its_source_event_is_acked(self):
        store = self.open()
        events = [{"id": f"diary-{i}", "kind": "summary", "text": "Unrelated diary", "importance": 1}
                  for i in range(120)]
        events.append({"id": "crafted", "kind": "receipt", "text": "crafted", "importance": 0.1,
                       "data": {"state": "succeeded", "detail": {"item_type": "bandages"}}})
        receipt = store.ingest(CONTEXT, events)[-1]
        request = {"events": [], "requirement_decisions": [
            {"requirement_id": "ask", "source_event_id": "ask", "source_sequence": 1,
             "decision": "pending", "text": "Please deliver bandages"}]}
        snapshot = store.snapshot(CONTEXT, request)
        self.assertEqual(snapshot["mandatory_record_ids"], [receipt])
        self.assertEqual([record["id"] for record in snapshot["records"]], [receipt])
        for text in (None, "", "bad\0text", "x" * 4097):
            with self.subTest(text_type=type(text).__name__, length=len(text) if isinstance(text, str) else None):
                request["requirement_decisions"][0]["text"] = text
                with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_request"):
                    store.snapshot(CONTEXT, request)

    def test_pending_requirement_count_matches_native_limit_without_trimming_goal_text(self):
        store = self.open()
        receipt = store.ingest(CONTEXT, [{"id": "crafted", "kind": "receipt", "text": "crafted",
                                        "data": {"detail": {"item_type": "bandages"}}}])[0]
        rows = [{"requirement_id": f"ask-{i}", "decision": "pending", "text": "Wait here"}
                for i in range(257)]
        rows[-1]["text"] = "Deliver bandages"
        snapshot = store.snapshot(CONTEXT, {"events": [], "requirement_decisions": rows})
        self.assertEqual(snapshot["mandatory_record_ids"], [receipt])
        rows.extend({"requirement_id": f"extra-{i}", "decision": "pending", "text": "Wait here"}
                    for i in range(4097 - len(rows)))
        with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_request"):
            store.snapshot(CONTEXT, {"events": [], "requirement_decisions": rows})

    def test_pending_requirement_identity_protects_failure_receipts_across_languages(self):
        store = self.open({"memory": {"cognition": {"forgetting_enabled": False},
                                      "continuity": {"load_experiences": "retain"}}})
        events = [{"id": f"diary-{i}", "kind": "summary", "importance": 1,
                   "text": "Bring bandages 请拿绷带, unrelated diary"} for i in range(120)]
        requirement = "load-epoch.1"
        failure = {"id": "receipt.gather-1", "kind": "receipt", "text": "gather_stock_changed",
                   "importance": 0.1,
                   "data": {"operation_id": "gather-1", "action": "gather", "intent": "",
                            "requirement_id": requirement, "origin": "incoming_message",
                            "state": "failed", "code": "gather_stock_changed", "detail": {}}}
        events.extend([failure, {**failure, "id": "receipt.unrelated",
                                "data": {**failure["data"], "requirement_id": "other.1"}}])
        ids = store.ingest(CONTEXT, events)
        stale = store.ingest({**CONTEXT, "branch_id": "other-branch"},
                             [{**failure, "id": "receipt.other-branch"}])[0]
        request = {"events": [], "requirement_decisions": [
            {"requirement_id": requirement, "decision": "pending", "text": "Bring bandages"}]}
        for text in ("Bring bandages", "请拿绷带"):
            with self.subTest(text=text):
                request["requirement_decisions"][0]["text"] = text
                snapshot = store.snapshot(CONTEXT, request)
                self.assertEqual(snapshot["mandatory_record_ids"], [ids[-2]])
                self.assertIn(ids[-2], {record["id"] for record in snapshot["records"]})
                self.assertNotIn(ids[-1], {record["id"] for record in snapshot["records"]})
                self.assertNotIn(stale, snapshot["mandatory_record_ids"])
        request["requirement_decisions"][0]["decision"] = "accepted"
        self.assertEqual(store.snapshot(CONTEXT, request)["mandatory_record_ids"], [])
        request["requirement_decisions"][0]["decision"] = "pending"
        self.record_paths(store, ids[-2])[0].unlink()
        self.assertEqual(store.snapshot(CONTEXT, request)["mandatory_record_ids"], [])

    def test_pending_requirement_identity_respects_identifier_and_mandatory_bounds(self):
        store = self.open()
        requirement = "load-epoch.1"
        ids = store.ingest(CONTEXT, [{"id": f"receipt-{i}", "kind": "receipt", "text": "gather_stock_changed",
                                     "data": {"requirement_id": requirement}}
                                    for i in range(MAX_MANDATORY_RECORDS)])
        request = {"events": [], "requirement_decisions": [
            {"requirement_id": requirement, "decision": "pending", "text": "请拿绷带"}]}
        self.assertEqual(set(store.snapshot(CONTEXT, request)["mandatory_record_ids"]), set(ids))
        store.ingest(CONTEXT, [{"id": "receipt-overflow", "kind": "receipt", "text": "gather_stock_changed",
                               "data": {"requirement_id": requirement}}])
        with self.assertRaisesRegex(MemoryStoreError, "mandatory_context_too_large"):
            store.snapshot(CONTEXT, request)
        for invalid in (None, "", "bad\0id", "x" * 257):
            with self.subTest(identity=invalid):
                request["requirement_decisions"][0]["requirement_id"] = invalid
                self.assertEqual(store.snapshot(CONTEXT, request)["mandatory_record_ids"], [])

    def test_goal_relevance_keeps_recalled_personality_growth_without_relearning_its_raw_source(self):
        store = self.open()
        ids = store.ingest(CONTEXT, [
            {"id": "danger", "kind": "observation", "text": "Danger at an unrelated location"},
            {"id": "growth", "kind": "growth", "text": "I learned caution", "source_ids": ["danger"],
             "preferences": {"caution": 0.9}}])
        snapshot = store.snapshot(CONTEXT, {"observations": {"goal": "Deliver bandages"}})
        self.assertEqual([record["id"] for record in snapshot["records"]], [ids[1]])
        self.assertEqual(snapshot["mandatory_record_ids"], [])

    def test_imported_old_obligations_and_receipts_are_not_current_mandatory_state(self):
        store = self.open()
        store.ingest(CONTEXT, [
            {"id": "crafted", "kind": "receipt", "text": "Crafted bandages"},
            {"id": "promise", "kind": "commitment", "status": "accepted", "text": "Deliver bandages",
             "source_ids": ["crafted"]}])
        archive = store.checkpoint(CONTEXT)
        store.close()
        store = self.open({"memory": {"continuity": {"new_world_experiences": "selected_archives",
                                                       "selected_archives": [archive["id"]]}}})
        snapshot = store.snapshot({**CONTEXT, "world_id": "new-world"}, {"observations": {"goal": "Deliver bandages"}})
        self.assertEqual(snapshot["mandatory_record_ids"], [])
        self.assertTrue(all(record["continuity"] == "imported_experience_not_current_world_fact"
                            for record in snapshot["records"]))

    def test_closed_obligations_do_not_reserve_context_but_checkpoint_pending_ones_do(self):
        store = self.open()
        ids = store.ingest(CONTEXT, [
            {"id": "done", "kind": "commitment", "status": "fulfilled", "text": "Delivered medicine"},
            {"id": "cancelled", "kind": "commitment", "status": "cancelled", "text": "Cancelled delivery"},
            {"id": "done-goal", "kind": "goal", "status": "completed", "text": "Finished goal"},
            {"id": "pending", "kind": "commitment", "status": "accepted", "text": "Bring bandages"}])
        self.assertEqual(store.snapshot(CONTEXT)["mandatory_record_ids"], [ids[-1]])
        checkpoint = store.checkpoint(CONTEXT)
        loaded = {**CONTEXT, "branch_id": "loaded-branch"}
        snapshot = store.restore(loaded, checkpoint)
        self.assertEqual(snapshot["mandatory_record_ids"], [ids[-1]])

    def test_retained_old_branch_and_future_events_are_labelled_only_in_retrieval_view(self):
        store = self.open({"memory": {"continuity": {"load_experiences": "retain"}}})
        ids = store.ingest(CONTEXT, [
            {"id": "receipt", "kind": "receipt", "text": "Old physical reward",
             "data": {"state": "succeeded", "item_type": "antibiotics", "count": 1}},
            {"id": "belief", "kind": "belief", "text": "A subjective lesson", "source_ids": ["receipt"]}])
        paths = {rid: self.record_paths(store, rid)[0] for rid in ids}
        bodies = {rid: path.read_bytes() for rid, path in paths.items()}
        revision = store.revision
        for current in ({**CONTEXT, "branch_id": "reloaded-branch"}, {**CONTEXT, "game_time": 50}):
            with self.subTest(context=current):
                records = store.retrieve(current)
                self.assertEqual({record["id"] for record in records}, set(ids))
                self.assertTrue(all(record["continuity"] == "imported_experience_not_current_world_fact"
                                    for record in records))
                self.assertTrue(all(record["context"] == CONTEXT for record in records))
                self.assertEqual(store.revision, revision)
                self.assertEqual({rid: path.read_bytes() for rid, path in paths.items()}, bodies)
        self.assertTrue(all("continuity" not in record for record in store.retrieve(CONTEXT)))

    def test_retained_future_personality_growth_does_not_import_its_physical_source(self):
        store = self.open({"memory": {"continuity": {"load_personality_growth": "retain"}}})
        future = {**CONTEXT, "game_time": 200}
        source, growth = store.ingest(future, [
            {"id": "danger", "kind": "receipt", "text": "Future observed danger"},
            {"id": "lesson", "kind": "growth", "text": "Learned caution", "source_ids": ["danger"],
             "preferences": {"caution": 0.9}}])
        stored = self.record_paths(store, growth)[0].read_bytes()
        record, = store.retrieve(CONTEXT)
        self.assertEqual(record["id"], growth)
        self.assertEqual(record["source_ids"], [source])
        self.assertEqual(record["context"], future)
        self.assertEqual(record["preferences"], {"caution": 0.9})
        self.assertEqual(record["continuity"], "imported_experience_not_current_world_fact")
        self.assertEqual(self.record_paths(store, growth)[0].read_bytes(), stored)
        self.assertNotIn("continuity", next(record for record in store.retrieve(future) if record["id"] == growth))

    def test_forgetting_uses_game_time_and_keeps_raw_events_traceable(self):
        store = self.open({"memory": {"cognition": {"half_life_seconds": 10, "recall_threshold": 0.1}}})
        rid = store.ingest(CONTEXT, [{"id": "seen", "kind": "observation", "text": "旧见闻"}])[0]
        self.assertEqual(store.retrieve({**CONTEXT, "game_time": 200}), [])
        self.assertEqual(len(self.record_paths(store, rid)), 1)
        self.assertTrue(list((store.memory_root / "evidence").glob("*/*.json")))

    def test_disabling_subjective_interpretation_excludes_beliefs_from_context(self):
        store = self.open({"memory": {"cognition": {"subjective_interpretation_enabled": False}}})
        store.ingest(CONTEXT, [{"id": "claim", "kind": "statement", "text": "玩家声称安全"},
                                {"id": "guess", "kind": "belief", "text": "安全"}])
        self.assertEqual([r["kind"] for r in store.retrieve(CONTEXT)], ["statement"])

    def test_invalid_manual_json_fails_closed_without_applying_other_deletions(self):
        store = self.open()
        ids = store.ingest(CONTEXT, [{"id": "a", "kind": "observation", "text": "a"},
                                   {"id": "b", "kind": "observation", "text": "b"}])
        before = store.revision
        self.record_paths(store, ids[0])[0].unlink()
        damaged = self.record_paths(store, ids[1])[0]
        damaged.write_text("{ unfinished editor write", encoding="utf-8")
        with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_json"):
            store.refresh()
        self.assertEqual(store.revision, before)
        self.assertEqual(list((store.memory_root / "revisions").glob("*.json")), [])

    def test_future_schema_is_rejected_without_rewriting_and_lock_is_released(self):
        store = self.open()
        store.close()
        manifest = sorted((store.memory_root / "manifests").glob("*.json"))[-1]
        self.edit(manifest, schema_version=2)
        original = manifest.read_bytes()
        with self.assertRaisesRegex(MemoryStoreError, "unsupported_memory_schema"):
            self.open()
        self.assertEqual(manifest.read_bytes(), original)
        self.edit(manifest, schema_version=1)
        self.open()

    def test_record_symlink_is_rejected_and_external_target_unchanged(self):
        store = self.open()
        rid = store.ingest(CONTEXT, [{"id": "seen", "kind": "observation", "text": "见闻"}])[0]
        path = self.record_paths(store, rid)[0]
        outside = self.base / "outside.json"
        outside.write_bytes(path.read_bytes())
        original = outside.read_bytes()
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_path"):
            store.refresh()
        self.assertEqual(outside.read_bytes(), original)

    def test_expected_revision_guards_inflight_output(self):
        store = self.open()
        revision = store.snapshot(CONTEXT)["revision"]
        store.ingest(CONTEXT, [{"id": "new", "kind": "observation", "text": "重要变化"}])
        with self.assertRaisesRegex(MemoryStoreError, "stale_memory_context"):
            store.ingest(CONTEXT, [{"id": "model", "kind": "belief", "text": "旧判断"}], expected_revision=revision)

    def test_personal_goals_are_typed_and_distinct_from_other_peoples_promises(self):
        store = self.open()
        store.ingest(CONTEXT, [{"id": "goal", "kind": "goal", "text": "我想学习制作药物", "status": "active"},
                                {"id": "promise", "kind": "commitment", "text": "玩家许诺给我药物"}])
        goals = [record for record in store.retrieve(CONTEXT) if record["kind"] == "goal"]
        self.assertEqual([record["text"] for record in goals], ["我想学习制作药物"])
        self.assertEqual(goals[0]["status"], "active")
        with self.assertRaisesRegex(MemoryStoreError, "invalid_goal_status"):
            store.ingest(CONTEXT, [{"id": "bad", "kind": "goal", "text": "错误", "status": "fulfilled"}])

    def test_native_structured_data_survives_versions_audit_and_reopen(self):
        store = self.open()
        events = [
            {"id": "seen", "kind": "observation", "text": "Visible medicine",
             "data": {"actor": {"id": 7}, "nearby": {"items": [{"item_type": "antibiotics",
                      "count": 1, "available_to_take": True, "position": {"x": 4, "y": 5, "z": 0}}]}}},
            {"id": "done", "kind": "receipt", "text": "craft_complete",
             "data": {"step_id": "craft-1", "state": "succeeded", "detail": {
                 "produced": [{"item_type": "bandages", "count": 1, "location": "inventory"}]}}},
        ]
        expected = deepcopy(events)
        ids = store.ingest(CONTEXT, events)
        events[0]["data"]["nearby"]["items"][0]["count"] = 999
        records = {record["id"]: record for record in store.retrieve(CONTEXT)}
        for rid, event in zip(ids, expected):
            self.assertEqual(records[rid]["data"], event["data"])
            audit = next((store.memory_root / "evidence").glob(f"*/{rid}-*.json"))
            self.assertEqual(json.loads(audit.read_text())["data"], event["data"])
        revision = store.revision
        self.assertEqual(store.ingest({**CONTEXT, "game_time": 110}, expected), ids)
        self.assertEqual(store.revision, revision)
        store.close()
        reopened = self.open()
        self.assertEqual({r["id"]: r["data"] for r in reopened.retrieve(CONTEXT)},
                         {rid: event["data"] for rid, event in zip(ids, expected)})

    def test_data_rejects_invalid_json_and_subjective_fact_channels_before_writes(self):
        store = self.open()
        for data in (None, [], {1: "bad key"}, {"number": float("nan")},
                     {"number": float("inf")}, {"number": 2 ** 63}, {"bad": (1, 2)}):
            with self.subTest(data_type=type(data).__name__):
                revision = store.revision
                with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_data"):
                    store.ingest(CONTEXT, [{"id": "valid", "kind": "observation", "text": "first"},
                                         {"id": "bad", "kind": "observation", "data": data}])
                self.assertEqual(store.revision, revision)
                self.assertEqual(store.retrieve(CONTEXT), [])
        for kind in ("belief", "growth", "relationship", "summary"):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_data_kind"):
                    store.ingest(CONTEXT, [{"id": "model", "kind": kind, "text": "imagined",
                                         "data": {"state": "succeeded", "produced": "invented reward"}}])
        with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_event"):
            store.ingest(CONTEXT, [{"id": "model", "kind": "belief", "provenance": "observed"}])
        self.assertEqual(list((store.memory_root / "records").glob("*/*.json")), [])

    def test_data_byte_boundary_and_manual_validation_fail_closed(self):
        store = self.open()
        # Compact UTF-8 JSON, not Python character count, defines the wire limit.
        data = {"payload": "x" * (MAX_EVENT_DATA_BYTES - len(b'{"payload":""}'))}
        rid = store.ingest(CONTEXT, [{"id": "boundary", "kind": "receipt", "data": data}])[0]
        self.assertEqual(store.retrieve(CONTEXT)[0]["data"], data)
        revision = store.revision
        with self.assertRaisesRegex(MemoryStoreError, "memory_data_too_large"):
            store.ingest(CONTEXT, [{"id": "too-large", "kind": "receipt",
                                 "data": {"payload": data["payload"] + "中"}}])
        self.assertEqual(store.revision, revision)
        path = self.record_paths(store, rid)[0]
        self.edit(path, data={"number": float("nan")})
        with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_data"):
            store.refresh()
        self.assertEqual(store.revision, revision)

    def test_deleted_data_and_derived_bodies_are_purged_by_id_without_background_edits(self):
        store = self.open()
        background = self.profile / "background.md"
        background.write_text("Background keeps SENTINEL_DELETED_DATA as authored text")
        source_event = {"id": "receipt", "kind": "receipt", "text": "Native result",
                        "data": {"private_known_note": "SENTINEL_DELETED_DATA", "count": 1}}
        source = store.ingest(CONTEXT, [source_event])[0]
        source_event["data"]["count"] = 2
        store.ingest(CONTEXT, [source_event])
        derived = store.ingest(CONTEXT, [{"id": "summary", "kind": "summary",
                                       "text": "SENTINEL_DELETED_DATA", "source_ids": [source]}])[0]
        unrelated = store.ingest(CONTEXT, [{"id": "independent", "kind": "belief",
                                         "text": "Unrelated SENTINEL_DELETED_DATA"}])[0]
        checkpoint = store.checkpoint(CONTEXT)
        head = store.memory_root / store._state["heads"][source].removeprefix("memory/")
        head.unlink()
        store.refresh()
        self.assertEqual(self.record_paths(store, source), [])
        self.assertEqual(self.record_paths(store, derived), [])
        self.assertTrue(self.record_paths(store, unrelated))
        for rid in (source, derived):
            self.assertEqual(list((store.memory_root / "evidence").glob(f"*/{rid}-*.json")), [])
        traces = list((store.memory_root / "evidence/deletions").glob("*.json"))
        self.assertTrue(traces)
        for trace in traces:
            value = json.loads(trace.read_text())
            self.assertEqual(set(value), {"schema_version", "id", "body_sha256", "reason"})
            self.assertNotIn("SENTINEL_DELETED_DATA", trace.read_text())
        self.assertEqual(background.read_text(), "Background keeps SENTINEL_DELETED_DATA as authored text")
        self.assertEqual([record["id"] for record in store.restore(CONTEXT, checkpoint)["records"]], [unrelated])
        store.ingest(CONTEXT, [source_event])
        self.assertFalse(any(record["id"] == source for record in store.retrieve(CONTEXT)))

    def test_same_event_id_new_data_is_not_silently_deduplicated_and_manual_wins(self):
        store = self.open()
        event = {"id": "done", "kind": "receipt", "text": "result", "data": {"count": 1}}
        rid = store.ingest(CONTEXT, [event])[0]
        checkpoint = store.checkpoint(CONTEXT)
        self.edit(self.record_paths(store, rid)[0], data={"count": 7})
        store.refresh()
        revision = store.revision
        store.ingest(CONTEXT, [event])  # exact original engine payload is known
        self.assertEqual(store.revision, revision)
        changed = {**event, "data": {"count": 3}}
        store.ingest(CONTEXT, [changed])
        self.assertEqual(len(self.record_paths(store, rid)), 2)
        self.assertEqual(store.retrieve(CONTEXT)[0]["data"], {"count": 7})
        self.assertTrue(any(conflict["id"] == rid for conflict in store._state["conflicts"]))
        revision = store.revision
        store.ingest(CONTEXT, [changed])
        self.assertEqual(store.revision, revision)
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"][0]["data"], {"count": 7})

    def test_preferences_are_limited_to_caution_on_growth_or_relationship(self):
        store = self.open()
        source = store.ingest(CONTEXT, [{"id": "experience", "kind": "receipt", "text": "Native danger"}])[0]
        for kind in ("growth", "relationship"):
            for caution in (0, 0.25, 1):
                event = {"id": f"{kind}-{caution}", "kind": kind, "text": "Subjective judgment",
                         "preferences": {"caution": caution}, "confidence": 0.8,
                         "source_ids": [source]}
                rid = store.ingest(CONTEXT, [event])[0]
                record = next(record for record in store.retrieve(CONTEXT) if record["id"] == rid)
                self.assertEqual(record["preferences"], {"caution": caution})
                self.assertEqual(record["confidence"], 0.8)
                self.assertEqual(record["provenance"], "subjective")
        for kind in ("belief", "observation", "receipt", "statement", "commitment", "summary", "goal"):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_preferences"):
                    store.ingest(CONTEXT, [{"id": f"invalid-{kind}", "kind": kind,
                                         "preferences": {"caution": 0.5}}])
        for preference in (None, {}, {"honesty": 0.5}, {"caution": 0.5, "faction": "hostile"},
                           {"caution": True}, {"caution": -0.1}, {"caution": 1.1},
                           {"caution": float("nan")}, {"caution": float("inf")},
                           {"caution": "0.5"}, {"caution": 10 ** 2000}):
            with self.subTest(preference_type=type(preference).__name__):
                with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_preferences"):
                    store.ingest(CONTEXT, [{"id": "invalid-preference", "kind": "growth",
                                         "preferences": preference}])
        with self.assertRaisesRegex(MemoryStoreError, "memory_source_unavailable"):
            store.ingest(CONTEXT, [{"id": "unsupported", "kind": "growth",
                                  "preferences": {"caution": 0.8}}])
        with self.assertRaisesRegex(MemoryStoreError, "memory_source_unavailable"):
            store.ingest(CONTEXT, [{"id": "invented", "kind": "relationship",
                                  "preferences": {"caution": 0.8}, "source_ids": ["imagined"]}])

    def test_preference_changes_have_distinct_fingerprints_and_manual_revision_priority(self):
        store = self.open()
        source = store.ingest(CONTEXT, [{"id": "experience", "kind": "observation", "text": "Nearby danger"}])[0]
        event = {"id": "caution", "kind": "growth", "text": "Caution learned",
                 "preferences": {"caution": 0.2}, "confidence": 0.6, "source_ids": [source]}
        rid = store.ingest(CONTEXT, [event])[0]
        self.edit(self.record_paths(store, rid)[0], preferences={"caution": 0.1})
        store.refresh()
        revision = store.revision
        store.ingest(CONTEXT, [event])
        self.assertEqual(store.revision, revision)
        store.ingest(CONTEXT, [{**event, "preferences": {"caution": 0.9}, "confidence": 0.8}])
        self.assertEqual(len(self.record_paths(store, rid)), 2)
        record = next(record for record in store.retrieve(CONTEXT) if record["id"] == rid)
        self.assertEqual(record["preferences"], {"caution": 0.1})
        self.assertEqual(record["provenance"], "manual")
        self.assertTrue(any(conflict["id"] == rid for conflict in store._state["conflicts"]))
        revision = store.revision
        self.edit(self.record_paths(store, rid)[0], preferences={"caution": True})
        with self.assertRaisesRegex(MemoryStoreError, "invalid_memory_preferences"):
            store.refresh()
        self.assertEqual(store.revision, revision)

    def test_native_goal_data_requires_a_matching_successful_receipt(self):
        store = self.open()
        receipt = {"operation_id": "request.goal", "action": "propose_own_goals",
                   "state": "succeeded", "code": "goal_accepted", "detail": {"goal": "Learn first aid"}}
        events = [{"id": "receipt.request.goal", "kind": "receipt", "text": "goal_accepted", "data": receipt},
                  {"id": "goal", "kind": "goal", "text": "Learn first aid", "status": "active",
                   "source_ids": ["receipt.request.goal"], "data": receipt}]
        source, goal = store.ingest(CONTEXT, events)
        record = next(record for record in store.retrieve(CONTEXT) if record["id"] == goal)
        self.assertEqual(record["source_ids"], [source])
        self.assertEqual(record["data"], receipt)
        self.assertEqual(record["provenance"], "subjective")
        revision = store.revision
        for changed in ({"state": "failed"}, {"action": "claim_reward"}, {"operation_id": "imagined"}):
            with self.subTest(change=changed):
                with self.assertRaisesRegex(MemoryStoreError, "invalid_goal_evidence"):
                    store.ingest(CONTEXT, [{**events[1], "id": "invalid", "data": {**receipt, **changed}}])
        with self.assertRaisesRegex(MemoryStoreError, "invalid_goal_evidence"):
            store.ingest(CONTEXT, [{**events[1], "id": "unsupported", "source_ids": []}])
        self.assertEqual(store.revision, revision)
        self.record_paths(store, source)[0].unlink()
        store.refresh()
        self.assertEqual(store.retrieve(CONTEXT), [])

    def test_tombstoned_sources_suppress_derived_redelivery_without_blocking_other_events(self):
        store = self.open()
        receipt = {"id": "receipt.operation", "kind": "receipt", "text": "Native output",
                   "data": {"operation_id": "operation", "state": "succeeded", "count": 1}}
        source = store.ingest(CONTEXT, [receipt])[0]
        self.record_paths(store, source)[0].unlink()
        store.refresh()
        for source_id in (source, receipt["id"]):
            with self.subTest(source_id=source_id):
                suffix = "stable" if source_id == source else "wire"
                events = [receipt,
                          {"id": "reflection." + suffix, "kind": "growth", "text": "Deleted experience",
                           "source_ids": [source_id], "preferences": {"caution": 0.9}},
                          {"id": "summary." + suffix, "kind": "summary", "text": "Derived twice",
                           "source_ids": ["reflection." + suffix]},
                          {"id": "independent." + suffix, "kind": "observation", "text": "New valid experience"}]
                result = store.ingest(CONTEXT, events)
                self.assertEqual(len(result), 1)
                records = store.retrieve(CONTEXT)
                self.assertFalse(any(record["kind"] in {"growth", "summary", "receipt"} for record in records))
                revision = store.revision
                self.assertEqual(store.ingest(CONTEXT, events), result)
                self.assertEqual(store.revision, revision)
        store.close()
        reopened = self.open()
        self.assertEqual({record["kind"] for record in reopened.retrieve(CONTEXT)}, {"observation"})
        self.assertEqual(len(reopened.retrieve(CONTEXT)), 2)

    def test_unknown_source_later_in_batch_leaves_no_files_or_new_tombstones(self):
        store = self.open()
        source = store.ingest(CONTEXT, [{"id": "experience", "kind": "receipt"}])[0]
        self.record_paths(store, source)[0].unlink()
        store.refresh()
        revision, deleted = store.revision, list(store._state["deleted"])
        with self.assertRaisesRegex(MemoryStoreError, "memory_source_unavailable"):
            store.ingest(CONTEXT, [{"id": "suppressed", "kind": "summary", "source_ids": [source]},
                                   {"id": "new", "kind": "observation", "text": "Must remain unwritten"},
                                   {"id": "unknown", "kind": "belief", "source_ids": ["not-ever-seen"]}])
        self.assertEqual(store.revision, revision)
        self.assertEqual(store._state["deleted"], deleted)
        self.assertEqual(list((store.memory_root / "records").glob("*/*.json")), [])

    def test_status_and_event_delivery_share_one_receipt_and_deletion_survives_both_paths(self):
        store = self.open()
        receipt = {"operation_id": "request.step", "state": "succeeded", "action": "craft",
                   "code": "craft_complete", "game_time": 100,
                   "detail": {"produced": [{"item_type": "bandages", "count": 1}]}}
        status = {"id": "receipt.request.step", "kind": "receipt", "text": "craft_complete",
                  "game_time": 100, "data": deepcopy(receipt)}
        event = {**deepcopy(status), "sequence": 4}
        rid = store.ingest(CONTEXT, [status])[0]
        revision = store.revision
        self.assertEqual(store.ingest({**CONTEXT, "game_time": 200}, [event]), [rid])
        self.assertEqual(store.revision, revision)
        self.assertEqual(len(self.record_paths(store, rid)), 1)
        checkpoint = store.checkpoint(CONTEXT)
        self.record_paths(store, rid)[0].unlink()
        store.refresh()
        revision = store.revision
        self.assertEqual(store.ingest(CONTEXT, [event, status]), [])
        self.assertEqual(store.revision, revision)
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])
        self.assertEqual(list((store.memory_root / "evidence").glob(f"*/{rid}-*.json")), [])
        self.assertEqual(set(json.loads((store.memory_root / "checkpoints" / (checkpoint["id"] + ".json")).read_text())),
                         {"schema_version", "id", "context", "revision", "state", "heads"})

    def test_interrupted_delete_finishes_purging_bodies_on_reopen(self):
        store = self.open()
        event = {"id": "receipt.operation", "kind": "receipt", "text": "DELETED_PRIVATE_TEXT",
                 "data": {"private": "DELETED_PRIVATE_TEXT", "count": 1}}
        source = store.ingest(CONTEXT, [event])[0]
        event["data"]["count"] = 2
        store.ingest(CONTEXT, [event])
        derived = store.ingest(CONTEXT, [{"id": "summary", "kind": "summary",
                                        "text": "DELETED_PRIVATE_TEXT", "source_ids": [source]}])[0]
        checkpoint = store.checkpoint(CONTEXT)
        (store.memory_root / store._state["heads"][source].removeprefix("memory/")).unlink()
        original = store._purge_audit_bodies

        def simulate_crash(ids, reason):
            if ids:
                raise MemoryStoreError("simulated_delete_interruption")
            return original(ids, reason)

        with patch.object(store, "_purge_audit_bodies", simulate_crash):
            with self.assertRaisesRegex(MemoryStoreError, "simulated_delete_interruption"):
                store.refresh()
        self.assertTrue(list((store.memory_root / "revisions").glob("*.json")))
        self.assertTrue(list((store.memory_root / "evidence").glob(f"*/{source}-*.json")))
        store.close()
        reopened = self.open()
        self.assertEqual(reopened.restore(CONTEXT, checkpoint)["records"], [])
        for rid in (source, derived):
            self.assertEqual(self.record_paths(reopened, rid), [])
            self.assertEqual(list((reopened.memory_root / "evidence").glob(f"*/{rid}-*.json")), [])
        self.assertEqual(reopened.ingest(CONTEXT, [event]), [])
        self.assertEqual(reopened.retrieve(CONTEXT), [])
        for path in reopened.memory_root.rglob("*.json"):
            self.assertNotIn("DELETED_PRIVATE_TEXT", path.read_text())

    def test_record_size_limit_is_independent_of_compact_event_size(self):
        store = self.open()
        revision = store.revision
        # Pretty, human-editable records need a separate bound: this compact
        # payload is below 1 MiB, but its indented record exceeds 2 MiB.
        data = {"values": [0] * 300000}
        self.assertLess(len(json.dumps(data, separators=(",", ":")).encode()), MAX_EVENT_DATA_BYTES)
        with self.assertRaisesRegex(MemoryStoreError, "memory_record_too_large"):
            store.ingest(CONTEXT, [{"id": "large", "kind": "observation", "data": data}])
        self.assertEqual(store.revision, revision)
        self.assertEqual(list((store.memory_root / "records").glob("*/*.json")), [])

    def test_restore_redelivery_reenters_checkpoint_view_without_copying_body(self):
        store = self.open()
        checkpoint = store.checkpoint(CONTEXT)
        later = {**CONTEXT, "game_time": 110, "event_watermark": 5}
        event = {"id": "receipt.request.gather", "kind": "receipt", "text": "gathered",
                 "game_time": 110, "data": {"operation_id": "request.gather", "state": "succeeded",
                 "action": "gather", "detail": {"item_type": "bandages", "count": 1}}}
        rid = store.ingest(later, [event])[0]
        original = {path: path.read_bytes() for path in self.record_paths(store, rid)}
        self.assertEqual(store.restore(later, checkpoint)["records"], [])
        revision = store.revision
        self.assertEqual(store.ingest(later, [event]), [rid])
        self.assertNotEqual(store.revision, revision)
        self.assertEqual([record["id"] for record in store.retrieve(later)], [rid])
        self.assertEqual({path: path.read_bytes() for path in self.record_paths(store, rid)}, original)
        revision = store.revision
        store.ingest(later, [event])
        self.assertEqual(store.revision, revision)
        store.close()
        reopened = self.open()
        self.assertEqual([record["id"] for record in reopened.retrieve(later)], [rid])

    def test_checkpoint_delta_redelivery_keeps_manual_head_and_tombstones(self):
        store = self.open()
        checkpoint = store.checkpoint(CONTEXT)
        event = {"id": "belief", "kind": "belief", "text": "Original judgment"}
        rid = store.ingest(CONTEXT, [event])[0]
        path = self.record_paths(store, rid)[0]
        self.edit(path, text="User's judgment takes priority", confidence=0.2)
        store.refresh()
        original = path.read_bytes()
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])
        store.ingest(CONTEXT, [event])
        selected = store.retrieve(CONTEXT)[0]
        self.assertEqual(selected["text"], "User's judgment takes priority")
        self.assertEqual(selected["provenance"], "manual")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(self.record_paths(store, rid)), 1)
        path.unlink()
        store.refresh()
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])
        revision = store.revision
        self.assertEqual(store.ingest(CONTEXT, [event]), [])
        self.assertEqual(store.revision, revision)
        self.assertEqual(store.retrieve(CONTEXT), [])

    def test_checkpoint_delta_receipt_redelivery_is_a_valid_goal_source_in_same_batch(self):
        store = self.open()
        checkpoint = store.checkpoint(CONTEXT)
        receipt = {"operation_id": "request.goal", "action": "propose_own_goals",
                   "state": "succeeded", "code": "propose_own_goals"}
        events = [{"id": "receipt.request.goal", "kind": "receipt", "text": "Goal proposed",
                   "data": deepcopy(receipt)},
                  {"id": "goal", "kind": "goal", "text": "Find medicine", "status": "active",
                   "source_ids": ["receipt.request.goal"], "data": deepcopy(receipt)}]
        ids = store.ingest(CONTEXT, events)
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])
        self.assertEqual(store.ingest(CONTEXT, events), ids)
        self.assertEqual({record["id"] for record in store.retrieve(CONTEXT)}, set(ids))
        self.assertTrue(all(len(self.record_paths(store, rid)) == 1 for rid in ids))

    def test_invalid_delta_batch_does_not_partially_rehydrate_checkpoint_view(self):
        store = self.open()
        checkpoint = store.checkpoint(CONTEXT)
        event = {"id": "receipt.request.gather", "kind": "receipt", "text": "gathered"}
        rid = store.ingest(CONTEXT, [event])[0]
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])
        revision = store.revision
        with self.assertRaisesRegex(MemoryStoreError, "memory_source_unavailable"):
            store.ingest(CONTEXT, [event,
                                   {"id": "invalid", "kind": "belief", "source_ids": ["unknown"]}])
        self.assertEqual(store.revision, revision)
        self.assertEqual(store.retrieve(CONTEXT), [])
        self.assertEqual(len(self.record_paths(store, rid)), 1)

    def test_redelivery_does_not_select_a_future_head_into_a_checkpoint_view(self):
        store = self.open()
        checkpoint = store.checkpoint(CONTEXT)
        event = {"id": "future.receipt", "kind": "receipt", "text": "Future native outcome",
                 "game_time": 200}
        rid = store.ingest({**CONTEXT, "game_time": 200}, [event])[0]
        self.assertEqual(store.restore(CONTEXT, checkpoint)["records"], [])
        revision = store.revision
        store.ingest(CONTEXT, [event])
        self.assertEqual(store.revision, revision)
        self.assertEqual(store.retrieve(CONTEXT), [])
        later = {**CONTEXT, "game_time": 200}
        store.ingest(later, [event])
        self.assertEqual([record["id"] for record in store.retrieve(later)], [rid])


if __name__ == "__main__":
    unittest.main()
