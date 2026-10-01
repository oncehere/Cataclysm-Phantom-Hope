"""Readable, versioned companion memory; never a source of game-world facts.

Only this process writes automatic revisions. Ordinary editors remain usable.
Evidence is retained for human audit until its source is deleted; audit traces
never provide a source for automatic memory reconstruction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any
from uuid import uuid4


KINDS = frozenset({"observation", "statement", "belief", "commitment", "receipt", "relationship", "growth", "summary", "goal"})
SUBJECTIVE = frozenset({"belief", "relationship", "growth", "summary", "goal"})
_MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_EVENT_DATA_BYTES = 1024 * 1024
_DATA_KINDS = frozenset({"observation", "statement", "receipt", "commitment", "goal"})
_RECORD_FIELDS = frozenset({"schema_version", "id", "source_event_id", "kind", "context", "text",
                            "source_ids", "importance", "confidence", "provenance", "status",
                            "data", "preferences"})
_EVENT_FIELDS = frozenset({"id", "sequence", "kind", "text", "game_time", "source_ids", "importance",
                           "confidence", "status", "data", "preferences"})
_ID = re.compile(r"^[a-f0-9]{32}$")


class MemoryStoreError(ValueError):
    """Messages deliberately contain codes only, never user text or paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encoded(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError):
        raise MemoryStoreError("invalid_memory_value") from None


def _context(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MemoryStoreError("invalid_actor_context")
    result = {}
    for key in ("world_id", "branch_id", "actor_id"):
        item = value.get(key)
        if not isinstance(item, (str, int)) or isinstance(item, bool) or not str(item) or len(str(item)) > 256:
            raise MemoryStoreError("invalid_actor_context")
        result[key] = str(item)
    game_time = value.get("game_time", value.get("turn", 0))
    if isinstance(game_time, bool) or not isinstance(game_time, (int, float)) or not math.isfinite(game_time) or game_time < 0:
        raise MemoryStoreError("invalid_actor_context")
    result["game_time"] = game_time
    result["event_watermark"] = value.get("event_watermark", 0)
    if type(result["event_watermark"]) is not int or result["event_watermark"] < 0:
        raise MemoryStoreError("invalid_actor_context")
    return result


def _scope(context: Mapping[str, Any]) -> str:
    return _digest(_encoded([context[k] for k in ("world_id", "branch_id", "actor_id")]))[:32]


def _record_id(context: Mapping[str, Any], source_id: str) -> str:
    return _digest(_encoded([_scope(context), source_id]))[:32]


def _event_fingerprint(record: Mapping[str, Any]) -> str:
    value = dict(record)
    value["context"] = {key: record["context"][key] for key in ("world_id", "branch_id", "actor_id")}
    return _digest(_encoded(value))


def _validate_data(value: Any) -> None:
    """Keep actor-delivered JSON intact with the same byte ceiling as the wire.

    JSON object keys, finite numbers and bounded nesting are checked before
    serialization, so a local caller cannot sneak in Python objects or cycles.
    This validates a received payload, never its truth outside actor perception.
    """
    if type(value) is not dict:
        raise MemoryStoreError("invalid_memory_data")
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise MemoryStoreError("invalid_memory_data")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise MemoryStoreError("invalid_memory_data")
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is float:
            if not math.isfinite(item):
                raise MemoryStoreError("invalid_memory_data")
        elif type(item) is int:
            if not -(2 ** 63) <= item < 2 ** 63:
                raise MemoryStoreError("invalid_memory_data")
        elif item is not None and type(item) not in (str, bool):
            raise MemoryStoreError("invalid_memory_data")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise MemoryStoreError("invalid_memory_data") from None
    if len(encoded) > MAX_EVENT_DATA_BYTES:
        raise MemoryStoreError("memory_data_too_large")


def _validate_preferences(kind: str, value: Any) -> None:
    if kind not in ("growth", "relationship") or type(value) is not dict or set(value) != {"caution"}:
        raise MemoryStoreError("invalid_memory_preferences")
    caution = value["caution"]
    if type(caution) not in (float, int) or not 0 <= caution <= 1 or not math.isfinite(caution):
        raise MemoryStoreError("invalid_memory_preferences")


class MemoryStore:
    """File-authoritative memory with manual-edit precedence and checkpoints.

    ``context`` requires world_id/branch_id/actor_id and accepts game_time and
    event_watermark. Ingest is for trusted observations or explicitly typed
    subjective records; a belief or a statement is never promoted to a receipt.
    Call ``is_current(snapshot['revision'])`` before accepting model output.
    """

    def __init__(self, profile_dir: str | Path, config: Mapping[str, Any] | None = None) -> None:
        self.root = Path(profile_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._lock_fd = -1
        self._memory_lock_fd = -1
        self.config = deepcopy(dict(config or {}))
        self.options = self.config.get("memory", self.config)
        if not isinstance(self.options, dict):
            raise MemoryStoreError("invalid_memory_config")
        self.continuity = self.options.get("continuity", {})
        self.cognition = self.options.get("cognition", {})
        if not isinstance(self.continuity, dict) or not isinstance(self.cognition, dict):
            raise MemoryStoreError("invalid_memory_config")
        for name in ("load_experiences", "load_personality_growth"):
            if self.continuity.get(name, "checkpoint") not in ("checkpoint", "retain"):
                raise MemoryStoreError("invalid_memory_config")
        if self.continuity.get("new_world_experiences", "none") not in ("none", "selected_archives"):
            raise MemoryStoreError("invalid_memory_config")
        if self.continuity.get("new_world_personality_growth", "reset") not in ("reset", "retain"):
            raise MemoryStoreError("invalid_memory_config")
        for name in ("forgetting_enabled", "subjective_interpretation_enabled"):
            if type(self.cognition.get(name, True)) is not bool:
                raise MemoryStoreError("invalid_memory_config")
        for name, default in (("half_life_seconds", 604800.0), ("recall_threshold", 0.05)):
            number = self.cognition.get(name, default)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
                raise MemoryStoreError("invalid_memory_config")
        if self.cognition.get("half_life_seconds", 604800.0) <= 0:
            raise MemoryStoreError("invalid_memory_config")
        archives = self.continuity.get("selected_archives", [])
        if not isinstance(archives, list) or any(not isinstance(item, str) or not _ID.fullmatch(item) for item in archives):
            raise MemoryStoreError("invalid_memory_config")
        paths = self.config.get("paths", {})
        if not isinstance(paths, Mapping):
            raise MemoryStoreError("invalid_memory_config")
        self.memory_root = self._configured_path(paths.get("memory", "memory"))
        self.background_path = self._configured_path(paths.get("background", "background.md"))
        self.memory_root.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_fd = os.open(self.root / ".writer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Two different profiles must not concurrently write one configured
            # memory directory. Locks never prohibit ordinary text editors.
            self._memory_lock_fd = os.open(self.memory_root / ".writer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self._memory_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise MemoryStoreError("writer_locked") from None
        try:
            for directory in ("memory/records", "memory/manifests", "memory/revisions", "evidence", "checkpoints"):
                path = self._safe(directory)
                path.mkdir(parents=True, exist_ok=True)
            self._state: dict[str, Any] = {
                "schema_version": 1, "sequence": 0, "heads": {}, "files": {},
                "manual": [], "deleted": [], "conflicts": [], "views": {}, "watched": {},
            }
            manifests = sorted(self._safe("memory/manifests").glob("*.json"))
            if manifests:
                self._state = self._json(self._relative(manifests[-1]))
                self._validate_state()
                self._revision = manifests[-1].stem
            else:
                self._revision = ""
                self._publish()
            self._records: dict[str, dict[str, Any]] = {}
            self.refresh()
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        for attribute in ("_lock_fd", "_memory_lock_fd"):
            fd = getattr(self, attribute, -1)
            if fd >= 0:
                os.close(fd)
                setattr(self, attribute, -1)
        self._closed = True

    @property
    def revision(self) -> str:
        return self._revision

    def _configured_path(self, value: Any) -> Path:
        if not isinstance(value, (str, Path)) or not str(value) or "\x00" in str(value):
            raise MemoryStoreError("invalid_memory_path")
        path = Path(value).expanduser()
        return (path if path.is_absolute() else self.root / path).resolve()

    def _relative(self, path: Path) -> str:
        return "memory/" + path.relative_to(self.memory_root).as_posix()

    def _safe(self, relative: str) -> Path:
        part = Path(relative)
        if part.is_absolute() or ".." in part.parts:
            raise MemoryStoreError("invalid_memory_path")
        if part.parts and part.parts[0] == "memory":
            path, parts = self.memory_root, part.parts[1:]
        elif part.parts and part.parts[0] in ("evidence", "checkpoints"):
            path, parts = self.memory_root, part.parts
        else:
            path, parts = self.root, part.parts
        for item in parts:
            path = path / item
            if path.is_symlink():
                raise MemoryStoreError("invalid_memory_path")
        return path

    def _read(self, relative: str) -> bytes:
        return self._read_path(self._safe(relative))

    def _read_path(self, path: Path) -> bytes:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
                    raise MemoryStoreError("invalid_memory_file")
                data = stream.read(_MAX_FILE_BYTES + 1)
            if len(data) > _MAX_FILE_BYTES:
                raise MemoryStoreError("invalid_memory_file")
            return data
        except OSError:
            raise MemoryStoreError("memory_file_unavailable") from None

    def _json(self, relative: str) -> dict[str, Any]:
        data = self._read(relative)
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError):
            raise MemoryStoreError("invalid_memory_json") from None
        if not isinstance(result, dict):
            raise MemoryStoreError("invalid_memory_json")
        if type(result.get("schema_version")) is not int or result["schema_version"] != 1:
            raise MemoryStoreError("unsupported_memory_schema")
        return result

    def _write_new(self, relative: str, value: Any) -> str:
        data = _encoded(value)
        if len(data) > _MAX_FILE_BYTES:
            raise MemoryStoreError("memory_record_too_large")
        path = self._safe(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            raise MemoryStoreError("memory_write_failed") from None
        return _digest(data)

    def _validate_state(self) -> None:
        for key in ("heads", "files", "views", "watched"):
            if not isinstance(self._state.get(key), dict):
                raise MemoryStoreError("invalid_memory_manifest")
        for key in ("manual", "deleted", "conflicts"):
            if not isinstance(self._state.get(key), list):
                raise MemoryStoreError("invalid_memory_manifest")
        if type(self._state.get("sequence")) is not int or self._state["sequence"] < 0:
            raise MemoryStoreError("invalid_memory_manifest")
        if any(not isinstance(rid, str) or not _ID.fullmatch(rid)
               for key in ("manual", "deleted") for rid in self._state[key]):
            raise MemoryStoreError("invalid_memory_manifest")
        for rid, path in self._state["heads"].items():
            if not isinstance(rid, str) or not _ID.fullmatch(rid) or not isinstance(path, str) or not path.startswith(f"memory/records/{rid}/"):
                raise MemoryStoreError("invalid_memory_manifest")
            self._safe(path)
        for path, metadata in self._state["files"].items():
            self._safe(path)
            if not path.startswith("memory/records/") or not isinstance(metadata, dict) or not _ID.fullmatch(str(metadata.get("id", ""))):
                raise MemoryStoreError("invalid_memory_manifest")

    def _publish(self) -> None:
        self._state["sequence"] += 1
        revision = f"{self._state['sequence']:012d}-{uuid4().hex}"
        self._write_new(f"memory/manifests/{revision}.json", self._state)
        self._revision = revision

    def _validate_record(self, record: dict[str, Any], rid: str) -> None:
        if set(record) - _RECORD_FIELDS or record.get("id") != rid or record.get("kind") not in KINDS:
            raise MemoryStoreError("invalid_memory_record")
        _context(record.get("context", {}))
        if not isinstance(record.get("text"), str):
            raise MemoryStoreError("invalid_memory_record")
        if record.get("provenance") not in ("subjective", "observed", "manual"):
            raise MemoryStoreError("invalid_memory_record")
        sources = record.get("source_ids", [])
        if not isinstance(sources, list) or any(not isinstance(s, str) or not _ID.fullmatch(s) for s in sources):
            raise MemoryStoreError("invalid_memory_record")
        for field in ("importance", "confidence"):
            number = record.get(field, 0.5)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not 0 <= number <= 1:
                raise MemoryStoreError("invalid_memory_record")
        if record.get("kind") == "belief" and record.get("status", "believed") not in ("believed", "suspected", "rejected"):
            raise MemoryStoreError("invalid_belief_status")
        if record.get("kind") == "commitment" and record.get("status", "proposed") not in (
            "proposed", "accepted", "fulfilled", "overdue", "disputed", "cancelled"
        ):
            raise MemoryStoreError("invalid_commitment_status")
        if record.get("kind") == "goal" and record.get("status", "proposed") not in (
            "proposed", "active", "completed", "abandoned"
        ):
            raise MemoryStoreError("invalid_goal_status")
        if "data" in record:
            if record["kind"] not in _DATA_KINDS:
                raise MemoryStoreError("invalid_memory_data_kind")
            _validate_data(record["data"])
            if record["kind"] == "goal":
                # The subjective goal is separate from evidence that the
                # native actor accepted it. Models cannot submit goal events.
                data = record["data"]
                if (not sources or data.get("action") != "propose_own_goals"
                        or data.get("state") != "succeeded"
                        or not isinstance(data.get("operation_id"), str)
                        or not 1 <= len(data["operation_id"]) <= 230):
                    raise MemoryStoreError("invalid_goal_evidence")
        if "preferences" in record:
            _validate_preferences(record["kind"], record["preferences"])
            if not sources:
                raise MemoryStoreError("memory_source_unavailable")
        if len(_encoded(record)) > _MAX_FILE_BYTES:
            raise MemoryStoreError("memory_record_too_large")

    def _purge_audit_bodies(self, ids: set[str], reason: str) -> None:
        # Match stable IDs in filenames, not body text or keywords. The deletion
        # trace has only hashes and identifiers, never deleted experience text.
        for rid in sorted(ids):
            for path in sorted(self._safe("evidence").glob(f"*/{rid}-*.json")):
                if not _ID.fullmatch(path.parent.name) or not _ID.fullmatch(path.name[len(rid) + 1:-5]):
                    continue
                relative = "evidence/" + path.relative_to(self._safe("evidence")).as_posix()
                digest = _digest(self._read(relative))
                self._write_new(f"evidence/deletions/{uuid4().hex}.json", {
                    "schema_version": 1, "id": rid, "body_sha256": digest, "reason": reason,
                })
                try:
                    self._safe(relative).unlink()
                except OSError:
                    raise MemoryStoreError("memory_delete_failed") from None

    def _descendants(self, roots: set[str]) -> set[str]:
        affected = set(roots)
        dependencies = [(rid, record.get("source_ids", [])) for rid, record in self._records.items()]
        # Checkpoints can name older revisions. Dependency invalidation must
        # cover their bodies too, even if a newer head stopped citing a source.
        for path, metadata in self._state["files"].items():
            sources = metadata.get("source_ids")
            if sources is None:
                sources = self._json(path).get("source_ids", [])
            dependencies.append((metadata["id"], sources))
        changed = True
        while changed:
            changed = False
            for rid, sources in dependencies:
                if rid not in affected and affected.intersection(sources):
                    affected.add(rid)
                    changed = True
        return affected

    def _delete(self, ids: set[str], reason: str) -> None:
        if not ids:
            return
        # The suppression marker is durable before any body is removed. Neither
        # checkpoints nor evidence may later undo this user revision.
        marker = {"schema_version": 1, "ids": sorted(ids), "reason": reason}
        self._write_new(f"memory/revisions/{uuid4().hex}.json", marker)
        self._purge_audit_bodies(ids, reason)
        self._state["deleted"] = sorted(set(self._state["deleted"]) | ids)
        for rid in ids:
            self._state["heads"].pop(rid, None)
            self._records.pop(rid, None)
        for path, meta in list(self._state["files"].items()):
            if meta["id"] in ids:
                try:
                    self._safe(path).unlink(missing_ok=True)
                except OSError:
                    raise MemoryStoreError("memory_delete_failed") from None
                del self._state["files"][path]

    def refresh(self) -> bool:
        if self._closed:
            raise MemoryStoreError("memory_store_closed")
        if not self._safe("memory/records").is_dir():
            raise MemoryStoreError("memory_directory_unavailable")
        changed = False
        suppressed = set(self._state["deleted"])
        for path in self._safe("memory/revisions").glob("*.json"):
            marker = self._json(self._relative(path))
            ids = marker.get("ids")
            if not isinstance(ids, list) or any(not isinstance(i, str) or not _ID.fullmatch(i) for i in ids):
                raise MemoryStoreError("invalid_memory_revision")
            suppressed.update(ids)
        if suppressed != set(self._state["deleted"]):
            self._state["deleted"] = sorted(suppressed)
            changed = True
        # Complete an interrupted delete before scanning any retained bodies.
        # Deletion traces are separate and cannot be used to reconstruct data.
        self._purge_audit_bodies(suppressed, "complete durable deletion")
        records = {}
        changed_ids: set[str] = set()
        removed: set[str] = set()
        edited: dict[str, list[str]] = {}
        # Validate all changed files before applying any detected deletion.
        scanned: dict[str, tuple[str, dict[str, Any]]] = {}
        for path in sorted(self._safe("memory/records").glob("*/*.json")):
            rel = self._relative(path)
            rid = path.parent.name
            if not _ID.fullmatch(rid):
                raise MemoryStoreError("invalid_memory_record")
            if rid in suppressed:
                self._safe(rel).unlink(missing_ok=True)
                self._state["files"].pop(rel, None)
                changed = True
                continue
            record = self._json(rel)
            self._validate_record(record, rid)
            scanned[rel] = (_digest(self._read(rel)), record)
        for rel, meta in list(self._state["files"].items()):
            if rel not in scanned:
                if self._state["heads"].get(meta["id"]) == rel:
                    removed.add(meta["id"])
                del self._state["files"][rel]
                changed = True
        for rel, (digest, record) in scanned.items():
            rid = record["id"]
            if rid in suppressed:
                # A copied old revision is not permission to resurrect a record.
                self._safe(rel).unlink(missing_ok=True)
                self._state["files"].pop(rel, None)
                changed = True
                continue
            old = self._state["files"].get(rel)
            if old is None or old["hash"] != digest:
                edited.setdefault(rid, []).append(rel)
                metadata = {"id": rid, "hash": digest, "source_ids": record.get("source_ids", [])}
                if old is not None and "source_fingerprint" in old:
                    metadata["source_fingerprint"] = old["source_fingerprint"]
                self._state["files"][rel] = metadata
                changed = True
        for rid, rel in self._state["heads"].items():
            if rel in scanned and rid not in suppressed:
                records[rid] = scanned[rel][1]
        self._records = records
        for rid, candidates in edited.items():
            # Prefer the edited current revision, else keep every conflict and
            # select deterministically. Automatic publication never overwrites it.
            current = self._state["heads"].get(rid)
            selected = current if current in candidates else sorted(candidates)[-1]
            self._state["heads"][rid] = selected
            self._records[rid] = scanned[selected][1]
            if rid not in self._state["manual"]:
                self._state["manual"].append(rid)
            if len(candidates) > 1:
                self._state["conflicts"].append({"id": rid, "paths": candidates})
            changed_ids.add(rid)
        if removed or suppressed:
            affected = self._descendants(removed | suppressed)
            if affected - set(self._state["deleted"]):
                self._delete(affected, "manual_delete")
                changed = True
            else:
                for rid in suppressed:
                    self._state["heads"].pop(rid, None)
                    self._records.pop(rid, None)
        invalidated = self._descendants(changed_ids) - changed_ids
        if invalidated:
            self._delete(invalidated, "source_edited")
            changed = True
        watched = {}
        for name in ("personality.json", "personality-config.json", "config.json", "agent-config.json"):
            if self._safe(name).exists():
                watched[name] = _digest(self._read(name))
        if self.background_path.exists():
            watched["background"] = _digest(self._read_path(self.background_path))
        if watched != self._state["watched"]:
            self._state["watched"] = watched
            changed = True
        if changed:
            self._publish()
        return changed

    def is_current(self, revision: str) -> bool:
        self.refresh()
        return revision == self.revision

    def ingest(self, context: Mapping[str, Any], events: Sequence[Mapping[str, Any]], *, expected_revision: str | None = None) -> list[str]:
        context = _context(context)
        self.refresh()
        if expected_revision is not None and expected_revision != self.revision:
            raise MemoryStoreError("stale_memory_context")
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            raise MemoryStoreError("invalid_memory_events")
        result = []
        prepared: list[dict[str, Any]] = []
        prospective = dict(self._records)
        suppressed = set(self._state["deleted"])
        invalidated: set[str] = set()
        replayed_ids: set[str] = set()
        # Validate the entire batch before creating records. A malformed later
        # event must not leave an uncommitted earlier file interpreted as manual.
        for event in events:
            if not isinstance(event, Mapping) or set(event) - _EVENT_FIELDS or event.get("kind") not in KINDS:
                raise MemoryStoreError("invalid_memory_event")
            source_id = event.get("id", uuid4().hex)
            if not isinstance(source_id, (str, int)) or isinstance(source_id, bool) or not str(source_id) or len(str(source_id)) > 256:
                raise MemoryStoreError("invalid_memory_event_id")
            source_id = str(source_id)
            rid = _record_id(context, source_id)
            if rid in suppressed:
                continue
            sources = event.get("source_ids", [])
            if not isinstance(sources, list) or any(not isinstance(i, str) for i in sources):
                raise MemoryStoreError("invalid_memory_sources")
            # A source ID can be either its original event ID or its stable
            # local record ID. Durable tombstones remain known sources: their
            # dependants are suppressed instead of blocking unrelated events.
            sources = [i if i in prospective or i in suppressed else _record_id(context, i) for i in sources]
            if any(i not in prospective and i not in suppressed for i in sources):
                raise MemoryStoreError("memory_source_unavailable")
            permitted_sources = set(self._selected(context))
            permitted_sources.update(item["id"] for item in prepared)
            permitted_sources.update(replayed_ids)
            if any((i not in permitted_sources and i not in suppressed) or i == rid for i in sources):
                raise MemoryStoreError("memory_source_unavailable")
            existing = prospective.get(rid)
            if existing is not None and existing["kind"] != event["kind"]:
                raise MemoryStoreError("memory_event_kind_changed")
            record_context = dict(context)
            if "game_time" in event:
                record_context["game_time"] = event["game_time"]
                _context(record_context)
            elif existing is not None:
                # Redelivery in a later request does not re-date the event.
                record_context = deepcopy(existing["context"])
            record = {
                "schema_version": 1, "id": rid, "source_event_id": source_id,
                "kind": event["kind"], "context": record_context, "text": event.get("text", ""),
                "source_ids": sources, "importance": event.get("importance", 0.5),
                "confidence": event.get("confidence", 0.5),
                "provenance": "subjective" if event["kind"] in SUBJECTIVE else "observed",
            }
            if event["kind"] == "belief":
                record["status"] = event.get("status", "believed")
            if event["kind"] == "commitment":
                status = event.get("status", "proposed")
                if status not in ("proposed", "accepted", "fulfilled", "overdue", "disputed", "cancelled"):
                    raise MemoryStoreError("invalid_commitment_status")
                record["status"] = status
            if event["kind"] == "goal":
                record["status"] = event.get("status", "proposed")
            if "data" in event:
                record["data"] = deepcopy(event["data"])
            if "preferences" in event:
                record["preferences"] = deepcopy(event["preferences"])
            self._validate_record(record, rid)
            if suppressed.intersection(sources):
                suppressed.add(rid)
                invalidated.add(rid)
                prospective.pop(rid, None)
                continue
            if record["kind"] == "goal" and "data" in record:
                if not any(prospective[source]["kind"] == "receipt"
                           and prospective[source].get("data") == record["data"]
                           for source in sources):
                    raise MemoryStoreError("invalid_goal_evidence")
            fingerprint = _event_fingerprint(record)
            delivered = any(meta.get("source_fingerprint") == fingerprint
                            for meta in self._state["files"].values() if meta["id"] == rid)
            if existing == record or delivered:
                # A complete native save can redeliver an acknowledged delta
                # after restoring an older checkpoint view. Deduplicate its
                # body while reselecting the legitimate current head (including
                # manual edits). Stage this until the entire batch is valid.
                view = self._state["views"].get(_scope(context))
                head = self._state["heads"].get(rid)
                current = self._records.get(rid)
                if view is not None and head is not None and current is not None:
                    origin = _context(current["context"])
                    policy = self.continuity.get(
                        "load_personality_growth" if current["kind"] == "growth" else "load_experiences",
                        "checkpoint")
                    if (all(origin[key] == context[key] for key in ("world_id", "branch_id", "actor_id"))
                            and (policy == "retain" or origin["game_time"] <= context["game_time"])
                            and view.get(rid) != head):
                        replayed_ids.add(rid)
                result.append(rid)
                continue
            prepared.append(record)
            prospective[rid] = record
            result.append(rid)
        if invalidated:
            # Publish durable suppression only after every event was validated.
            # Include older heads and earlier prepared dependants in the same
            # deletion, so neither delivery order nor a checkpoint resurrects
            # a subjective interpretation of a removed source.
            affected = self._descendants(invalidated)
            changed = True
            while changed:
                changed = False
                for record in prepared:
                    if record["id"] not in affected and affected.intersection(record["source_ids"]):
                        affected.add(record["id"])
                        changed = True
            self._delete(affected, "source_deleted")
            prepared = [record for record in prepared if record["id"] not in affected]
            result = [rid for rid in result if rid not in affected]
        for record in prepared:
            rid = record["id"]
            version = uuid4().hex
            rel = f"memory/records/{rid}/{version}.json"
            digest = self._write_new(rel, record)
            self._state["files"][rel] = {"id": rid, "hash": digest,
                                        "source_fingerprint": _event_fingerprint(record),
                                        "source_ids": record["source_ids"]}
            if rid in self._state["manual"]:
                self._state["conflicts"].append({"id": rid, "paths": [self._state["heads"][rid], rel]})
            else:
                self._state["heads"][rid] = rel
                self._records[rid] = record
            if record["provenance"] == "observed":
                # Audit batches contain only what was delivered to this actor.
                # They are not scanned by retrieve(), refresh(), or restore().
                self._write_new(f"evidence/{_scope(context)}/{rid}-{version}.json", record)
            view = self._state["views"].get(_scope(context))
            if view is not None:
                view[rid] = self._state["heads"][rid]
        rehydrated = False
        view = self._state["views"].get(_scope(context))
        if view is not None:
            for rid in replayed_ids:
                if rid in self._state["deleted"]:
                    continue
                head = self._state["heads"].get(rid)
                if head is not None and view.get(rid) != head:
                    view[rid] = head
                    rehydrated = True
        if prepared or invalidated or rehydrated:
            self._publish()
        # Catch an editor's change to the previous revision during publication.
        self.refresh()
        return result

    def _imports(self) -> dict[str, str]:
        paths: dict[str, str] = {}
        if self.continuity.get("new_world_experiences", "none") != "selected_archives" and self.continuity.get("new_world_personality_growth", "reset") != "retain":
            return paths
        archives = self.continuity.get("selected_archives", [])
        if not isinstance(archives, list):
            raise MemoryStoreError("invalid_memory_config")
        for checkpoint_id in archives:
            checkpoint = self._load_checkpoint(checkpoint_id)
            paths.update(checkpoint["heads"])
        return paths

    def _selected(self, context: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
        selected = {}
        view = self._state["views"].get(_scope(context))
        candidates = dict(self._state["heads"])
        imports = self._imports()
        for rid, path in imports.items():
            if rid in self._state["deleted"]:
                continue
            # Selecting an archive for a new world must not roll back cognition
            # in the original world merely because its ID is also current.
            origin = self._json(path)["context"]
            if origin["world_id"] != context["world_id"] or rid not in candidates:
                candidates[rid] = path
        if view is not None:
            # Checkpoint policy selects historical heads; retain policy selects
            # current heads. Do not apply a checkpoint to both indiscriminately.
            for rid, path in view.items():
                current = self._records.get(rid)
                growth = current is not None and current["kind"] == "growth"
                if self.continuity.get("load_personality_growth" if growth else "load_experiences", "checkpoint") == "checkpoint":
                    candidates[rid] = path
        for rid, path in candidates.items():
            if rid in self._state["deleted"]:
                continue
            if rid in self._state["manual"]:
                path = self._state["heads"].get(rid, path)
            record = deepcopy(self._json(path))
            self._validate_record(record, rid)
            origin = record["context"]
            same_world = origin["world_id"] == context["world_id"]
            growth = record["kind"] == "growth"
            if record["kind"] == "belief" and not self.cognition.get("subjective_interpretation_enabled", True):
                continue
            if same_world:
                if origin["actor_id"] != context["actor_id"]:
                    continue
                policy = self.continuity.get("load_personality_growth" if growth else "load_experiences", "checkpoint")
                if policy == "checkpoint":
                    if view is not None:
                        if rid not in view:
                            continue
                    elif origin["branch_id"] != context["branch_id"] or origin["game_time"] > context["game_time"]:
                        continue
            else:
                if growth:
                    if self.continuity.get("new_world_personality_growth", "reset") != "retain":
                        continue
                elif self.continuity.get("new_world_experiences", "none") != "selected_archives" or rid not in imports:
                    continue
            if any(origin[key] != context[key] for key in ("world_id", "branch_id", "actor_id")) or origin["game_time"] > context["game_time"]:
                # Explicit retention or a selected checkpoint preserves the
                # old experience without promoting another save scope/future
                # outcome to a current physical fact. Mark the view, not disk.
                record["continuity"] = "imported_experience_not_current_world_fact"
            if rid in self._state["manual"]:
                record["provenance"] = "manual"
            selected[rid] = (path, record)
        return selected

    def retrieve(self, context: Mapping[str, Any], query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        context = _context(context)
        if not isinstance(query, str) or type(limit) is not int or not 0 <= limit <= 1000:
            raise MemoryStoreError("invalid_memory_query")
        self.refresh()
        words = set(re.findall(r"\w+", query.casefold()))
        ranked = []
        for rid, (_, record) in self._selected(context).items():
            age = max(0, context["game_time"] - record["context"]["game_time"])
            weight = record.get("importance", 0.5)
            if self.cognition.get("forgetting_enabled", True):
                weight *= 2 ** (-age / self.cognition.get("half_life_seconds", 604800.0))
                if weight < self.cognition.get("recall_threshold", 0.05):
                    continue
            matches = sum(word in record["text"].casefold() for word in words)
            if words and not matches:
                continue
            record["recall_weight"] = weight
            ranked.append((matches, weight, record["context"]["game_time"], rid, record))
        ranked.sort(key=lambda item: item[:4], reverse=True)
        return [item[4] for item in ranked[:limit]]

    def snapshot(self, context: Mapping[str, Any]) -> dict[str, Any]:
        records = self.retrieve(context, limit=100)
        try:
            background = self._read_path(self.background_path).decode("utf-8") if self.background_path.exists() else ""
        except UnicodeError:
            raise MemoryStoreError("invalid_background_encoding") from None
        # A second refresh closes the usual editor/read window. The runtime
        # still rechecks revision after its asynchronous model call.
        if self.refresh():
            raise MemoryStoreError("memory_changed_during_snapshot")
        return {"revision": self.revision, "background": background, "records": records,
                "cognition": deepcopy(self.cognition)}

    def checkpoint(self, context: Mapping[str, Any]) -> dict[str, Any]:
        context = _context(context)
        self.refresh()
        checkpoint_id = uuid4().hex
        heads = {rid: path for rid, (path, _) in self._selected(context).items()}
        result = {"schema_version": 1, "id": checkpoint_id, "context": context,
                  "revision": self.revision, "state": "prepared", "heads": heads}
        self._write_new(f"checkpoints/{checkpoint_id}.json", result)
        return deepcopy(result)

    def _load_checkpoint(self, checkpoint: Mapping[str, Any] | str) -> dict[str, Any]:
        checkpoint_id = checkpoint.get("id") if isinstance(checkpoint, Mapping) else checkpoint
        if not isinstance(checkpoint_id, str) or not _ID.fullmatch(checkpoint_id):
            raise MemoryStoreError("invalid_checkpoint")
        result = self._json(f"checkpoints/{checkpoint_id}.json")
        if result.get("id") != checkpoint_id or not isinstance(result.get("heads"), dict):
            raise MemoryStoreError("invalid_checkpoint")
        _context(result.get("context", {}))
        for rid, path in result["heads"].items():
            if not isinstance(rid, str) or not _ID.fullmatch(rid) or not isinstance(path, str) or not path.startswith(f"memory/records/{rid}/"):
                raise MemoryStoreError("invalid_checkpoint")
            self._safe(path)
        return result

    def restore(self, context: Mapping[str, Any], checkpoint: Mapping[str, Any] | str) -> dict[str, Any]:
        context = _context(context)
        self.refresh()
        saved = self._load_checkpoint(checkpoint)
        if any(saved["context"][key] != context[key] for key in ("world_id", "actor_id")):
            raise MemoryStoreError("checkpoint_context_mismatch")
        if saved["context"]["game_time"] > context["game_time"]:
            raise MemoryStoreError("checkpoint_time_mismatch")
        heads = {}
        for rid, path in saved["heads"].items():
            if rid not in self._state["deleted"]:
                if rid in self._state["manual"]:
                    path = self._state["heads"].get(rid, path)
                self._validate_record(self._json(path), rid)
                heads[rid] = path
        self._state["views"][_scope(context)] = heads
        self._publish()
        return self.snapshot(context)
