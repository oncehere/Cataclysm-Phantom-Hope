import json
from pathlib import Path
from unittest.mock import Mock

import polib
import pytest

from pokeeper.catalog import entry_id, identity, json_bytes, parse_po, serialize
from pokeeper.config import KeeperError, load_config
from pokeeper.gemini import (RejectedRequest, RetryableError, UnknownOutcome,
                            _google_transport, fill)
from pokeeper.transaction import TransactionError, digest


FIXTURES = json.loads((Path(__file__).parent / "fixtures/compatibility.json").read_text())
PLURAL = "nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);"


def project(tmp_path, selected=None, extra=""):
    selected = FIXTURES if selected is None else selected
    po = polib.POFile()
    po.metadata = {"Project-Id-Version": "sample 1", "Content-Type": "text/plain; charset=UTF-8"}
    for f in selected:
        e = polib.POEntry(msgctxt=f["context"], msgid=f["msgid"], msgid_plural=f["plural"] or "",
                         comment=f["comments"], tcomment="Confirmed translator note",
                         occurrences=[tuple(o) for o in f["occurrences"]])
        if "%d" in f["msgid"]:
            e.flags = ["c-format"]
        if "%(name)s" in f["msgid"]:
            e.flags = ["python-format"]
        po.append(e)
    (tmp_path / "messages.pot").write_bytes(serialize(po))
    config = tmp_path / "project.toml"
    config.write_text('version=1\nproject="sample"\nlanguage="pl"\n'
                      f'plural_forms={json.dumps(PLURAL)}\n'
                      'template="messages.pot"\ncatalog="pl.po"\nstate="state/current.json"\n'
                      '[rules]\npreserve_newlines=true\n[gemini]\nmodel="fake-model"\n'
                      + extra)
    return config


def response(prompt, overrides=None):
    payload = json.loads(prompt)
    by_identity = {json.dumps([f["context"], f["msgid"], f["plural"]]): f for f in FIXTURES}
    rows = []
    for entry in payload["entries"]:
        f = by_identity[json.dumps(entry["identity"])]
        rows.append({"id": entry["id"], "identity": entry["identity"],
                     "values": (overrides or {}).get(f["name"], f["translations"])})
    return {"translations": rows[::-1]}


class Fake:
    def __init__(self, override=None):
        self.calls = []
        self.override = override

    def __call__(self, model, prompt, timeout):
        self.calls.append((model, json.loads(prompt), timeout))
        return response(prompt, self.override)


def report(candidate):
    return json.loads((candidate / "report.json").read_text())


def test_shared_fixtures_roundtrip_prompt_and_completed_cache(tmp_path, monkeypatch):
    config = project(tmp_path, extra='terms={Open="Otwórz", Unrelated="omit"}\n'
                                  'examples=[{source="Open",translation="Otwórz"}]\n')
    cache = tmp_path / "cache.json"
    fake = Fake()
    one = tmp_path / "candidate-1"
    fill(config, one, cache, transport=fake)
    po = parse_po((one / "candidate.po").read_bytes())
    expected = {json.dumps([f["context"], f["msgid"], f["plural"]]): f["translations"] for f in FIXTURES}
    for entry in po:
        got = [entry.msgstr_plural[i] for i in range(3)] if entry.msgid_plural else [entry.msgstr]
        assert got == expected[json.dumps(identity(entry))]
    assert len({entry_id(e) for e in po}) == len(FIXTURES)
    assert not report(one)["gaps"]
    assert {e.msgctxt for e in po} >= {None, "", "audit:verb", "audit:adjective"}
    entries = [e for _, p, _ in fake.calls for e in p["entries"]]
    assert all(e["developer_comments"] and e["occurrences"] for e in entries)
    assert all(e["translator_comments"] == "Confirmed translator note" for e in entries)
    assert all("Unrelated" not in e["terms"] for e in entries)
    assert all(len(e["confirmed_examples"]) <= 3 for e in entries)
    assert all(len(p["entries"]) <= 4 for _, p, _ in fake.calls)
    assert all(len({json.dumps(e["context"]) for e in p["entries"]}) == 1 for _, p, _ in fake.calls)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    two = tmp_path / "candidate-2"
    fill(config, two, cache)  # No transport/key: complete cache is enough.
    assert (one / "candidate.po").read_bytes() == (two / "candidate.po").read_bytes()
    assert {r["status"] for r in report(two)["gemini"]} == {"cached"}
    state = json.loads((two / "state.json").read_text())
    assert all(r["kind"] == "gemini" and r["name"] == "fake-model" for r in state["references"].values())
    assert all((two / "snapshots" / (r["sha256"] + ".po")).exists() for r in state["references"].values())


@pytest.mark.parametrize("bad", ["%d plik", ["%d plik"], ["%d plik"] * 4, ["plik"] * 3, [""] * 3])
def test_reject_plural_scalar_short_long_placeholders_and_empty(tmp_path, bad):
    config = project(tmp_path, [FIXTURES[4]])
    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=Fake({"three-plurals": bad}))
    assert len(report(candidate)["gaps"]) == 1
    assert report(candidate)["gemini"][0]["status"] in {"plural_count", "gettext_format", "empty"}


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "identity", "missing"])
def test_response_identity_exact(tmp_path, mutation):
    config = project(tmp_path, [FIXTURES[0], FIXTURES[5]])
    def fake(model, prompt, timeout):
        value = response(prompt)
        if mutation == "unknown":
            value["translations"][0]["id"] = "wrong"
        elif mutation == "duplicate":
            value["translations"][0] = value["translations"][1]
        elif mutation == "identity":
            value["translations"][0]["identity"][0] = ""
        else:
            value["translations"].pop()
        return value
    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=fake)
    assert len(report(candidate)["gaps"]) == 2
    assert {r["status"] for r in report(candidate)["gemini"]} == {"response_identity"}


def test_partial_results_resume_only_failure(tmp_path):
    config = project(tmp_path, [FIXTURES[0], FIXTURES[5]])
    cache = tmp_path / "cache"
    first = Fake({"newlines": ["lost newline"]})
    one = tmp_path / "candidate-1"
    fill(config, one, cache, transport=first)
    assert len(report(one)["gaps"]) == 1
    assert len(first.calls[0][1]["entries"]) == 2
    second = Fake()
    two = tmp_path / "candidate-2"
    fill(config, two, cache, transport=second)
    assert len(second.calls) == 1
    assert len(second.calls[0][1]["entries"]) == 1
    assert second.calls[0][1]["entries"][0]["singular"] == FIXTURES[5]["msgid"]
    assert not report(two)["gaps"]


@pytest.mark.parametrize("retries", [0, 2])
def test_bounded_definite_retries(tmp_path, monkeypatch, retries):
    config = project(tmp_path, [FIXTURES[0]], extra=f"retries={retries}\n")
    fake = Mock(side_effect=RetryableError("SECRET must not be persisted"))
    monkeypatch.setattr("pokeeper.gemini.time.sleep", lambda _: None)
    candidate = tmp_path / "candidate"
    cache = tmp_path / "cache"
    fill(config, candidate, cache, transport=fake)
    assert fake.call_count == retries + 1
    assert report(candidate)["gemini"][0]["status"] == "retry_exhausted"
    assert "SECRET" not in cache.read_text() + (candidate / "report.json").read_text()


def test_retry_recovers_success_and_api_rejection_no_retry(tmp_path, monkeypatch):
    config = project(tmp_path, [FIXTURES[0]])
    monkeypatch.setattr("pokeeper.gemini.time.sleep", lambda _: None)
    calls = []
    def send(model, prompt, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise RetryableError()
        return response(prompt)
    fill(config, tmp_path / "candidate-1", tmp_path / "cache-1", transport=send)
    assert len(calls) == 2
    rejected = Mock(side_effect=RejectedRequest())
    fill(config, tmp_path / "candidate-2", tmp_path / "cache-2", transport=rejected)
    assert rejected.call_count == 1


@pytest.mark.parametrize("error,status,failed_attempts", [
    (RetryableError, "retry_exhausted", 2),
    (RejectedRequest, "rejected", 1),
    (UnknownOutcome, "unknown", 1),
])
def test_provider_failure_stops_unsent_batches_and_resume_reuses_completed(
        tmp_path, monkeypatch, error, status, failed_attempts):
    config = project(tmp_path, FIXTURES[:3], extra="batch_size=1\nretries=1\n")
    cache = tmp_path / "cache"
    monkeypatch.setattr("pokeeper.gemini.time.sleep", lambda _: None)
    called = []

    def send(model, prompt, timeout):
        called.append(json.loads(prompt)["entries"][0]["id"])
        if len(called) > 1:
            raise error()
        return response(prompt)

    first = tmp_path / "candidate-1"
    fill(config, first, cache, transport=send)
    assert len(called) == 1 + failed_attempts
    assert len(set(called[1:])) == 1
    first_report = {record["id"]: record for record in report(first)["gemini"]}
    assert first_report[called[0]]["status"] == "completed"
    assert first_report[called[1]]["status"] == status
    unsent_id = (first_report.keys() - set(called)).pop()
    assert first_report[unsent_id] == {"id": unsent_id, "status": "not_requested",
                                       "reason": "provider_unavailable"}
    saved = json.loads(cache.read_bytes())
    assert len(saved["entries"]) == 2
    assert unsent_id not in {record["scope"][-1] for record in saved["entries"].values()}
    assert len(parse_po((first / "candidate.po").read_bytes())) == 3
    assert len(report(first)["gaps"]) == 2

    resumed = Fake()
    second = tmp_path / "candidate-2"
    fill(config, second, cache, transport=resumed)
    second_report = {record["id"]: record for record in report(second)["gemini"]}
    assert second_report[called[0]]["status"] == "cached"
    assert second_report[unsent_id]["status"] == "completed"
    resumed_ids = {payload["id"] for _, prompt, _ in resumed.calls for payload in prompt["entries"]}
    assert called[0] not in resumed_ids
    if status == "unknown":
        assert resumed_ids == {unsent_id}
        assert second_report[called[1]]["status"] == "unknown"
        assert len(report(second)["gaps"]) == 1
        third = tmp_path / "candidate-3"
        explicit = Fake()
        fill(config, third, cache, transport=explicit, retry_unknown=True)
        assert len(explicit.calls) == 1
        assert explicit.calls[0][1]["entries"][0]["id"] == called[1]
        assert not report(third)["gaps"]
    else:
        assert resumed_ids == {called[1], unsent_id}
        assert not report(second)["gaps"]


def test_invalid_response_still_allows_later_batches(tmp_path):
    config = project(tmp_path, FIXTURES[:3], extra="batch_size=1\n")
    called = []

    def send(model, prompt, timeout):
        called.append(json.loads(prompt)["entries"][0]["id"])
        if len(called) == 1:
            return {"translations": []}
        return response(prompt)

    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=send)
    assert len(called) == 3
    records = {record["id"]: record for record in report(candidate)["gemini"]}
    assert records[called[0]]["status"] == "response_identity"
    assert all(records[key]["status"] == "completed" for key in called[1:])
    assert len(report(candidate)["gaps"]) == 1


@pytest.mark.parametrize("interrupt", [False, True])
def test_unknown_interruption_requires_explicit_retry(tmp_path, monkeypatch, interrupt):
    config = project(tmp_path, [FIXTURES[0]])
    cache = tmp_path / "cache"
    fake = Mock(side_effect=KeyboardInterrupt() if interrupt else UnknownOutcome("SECRET"))
    first = tmp_path / "candidate-1"
    if interrupt:
        with pytest.raises(KeyboardInterrupt):
            fill(config, first, cache, transport=fake)
        assert not first.exists()
        assert list(json.loads(cache.read_text())["entries"].values())[0]["status"] == "inflight"
    else:
        fill(config, first, cache, transport=fake)
        assert report(first)["gemini"][0]["status"] == "unknown"
    assert fake.call_count == 1
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    second = tmp_path / "candidate-2"
    fill(config, second, cache)
    assert report(second)["gemini"][0] == {"id": report(second)["gaps"][0]["id"],
                                           "status": "unknown", "reason": "retry_may_charge_again"}
    fresh = Fake()
    fill(config, tmp_path / "candidate-3", cache, retry_unknown=True, transport=fresh)
    assert len(fresh.calls) == 1
    assert "SECRET" not in cache.read_text()


def test_missing_key_and_po_input_concurrency(tmp_path, monkeypatch):
    config = project(tmp_path, [FIXTURES[0]])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(KeeperError, match="GEMINI_API_KEY"):
        fill(config, tmp_path / "no-key", tmp_path / "cache")
    def mutating(model, prompt, timeout):
        with (tmp_path / "messages.pot").open("ab") as f:
            f.write(b"\n# changed concurrently\n")
        return response(prompt)
    with pytest.raises(TransactionError, match="changed"):
        fill(config, tmp_path / "candidate", tmp_path / "cache", transport=mutating)
    assert not (tmp_path / "candidate").exists()
    assert list(json.loads((tmp_path / "cache").read_text())["entries"].values())[0]["status"] == "complete"


def test_config_fingerprint_changes_and_cache_input_alias_refused(tmp_path):
    config = project(tmp_path, [FIXTURES[0]])
    cache = tmp_path / "cache"
    fill(config, tmp_path / "candidate-1", cache, transport=Fake())
    with config.open("a") as f:
        f.write('prompt="More formal"\n')
    fake = Fake()
    fill(config, tmp_path / "candidate-2", cache, transport=fake)
    assert len(fake.calls) == 1
    before = config.read_bytes()
    with pytest.raises(KeeperError, match="overwrite"):
        fill(config, tmp_path / "candidate-3", config, transport=fake)
    assert config.read_bytes() == before


def test_google_sdk_retry_disabled_and_error_redacted(monkeypatch):
    from google import genai
    from google.genai import errors
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret-value")
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.models.generate_content.return_value.text = "{}"
    constructor = Mock(return_value=client)
    monkeypatch.setattr(genai, "Client", constructor)
    assert _google_transport("fake-model", "prompt", 2) == "{}"
    kwargs = constructor.call_args.kwargs
    assert kwargs["http_options"].retry_options.attempts == 1
    assert kwargs["http_options"].timeout == 2000
    assert kwargs["api_key"] == "test-secret-value"
    generation = client.models.generate_content.call_args.kwargs["config"]
    assert generation.model_dump(exclude_unset=True) == {"response_mime_type": "application/json"}
    assert generation.temperature is None and generation.top_p is None and generation.top_k is None
    client.models.generate_content.side_effect = errors.ServerError(503, {"error": {"message": "test-secret-value"}})
    with pytest.raises(RetryableError) as exc:
        _google_transport("fake-model", "prompt", 2)
    assert exc.value.http_code == 503
    assert exc.value.retry_after_seconds is None
    assert "test-secret-value" not in str(exc.value)


@pytest.mark.parametrize("code,expected", [(429, 429), (503, 503), (401, None),
                                          (429.0, None), (True, None), ("429", None), ("SECRET", None)])
def test_retryable_error_exposes_only_safe_code_and_bounded_hint(code, expected):
    error = RetryableError(code, retry_after_seconds=1000)
    assert error.http_code == expected
    assert error.retry_after_seconds == 60
    assert error.args == ()
    assert "SECRET" not in str(error) + repr(error)
    for invalid in ("SECRET", float("inf"), float("nan"), -1, True, {}):
        assert RetryableError(503, invalid).retry_after_seconds is None


@pytest.mark.parametrize("header,duration,expected", [
    ("7", None, 7),
    (None, "3.5s", 3.5),
    ("2", "34s", 34),
    ("120", None, 60),
    (None, "999s", 60),
    ("SECRET", "SECRET", None),
    ("Thu, 01 Jan 1970 00:01:30 GMT", None, 60),
])
def test_google_sdk_retry_metadata_is_sanitized(monkeypatch, header, duration, expected):
    import httpx
    from google import genai
    from google.genai import errors
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret-value")
    monkeypatch.setattr("pokeeper.gemini.time.time", lambda: 0)
    body = {"error": {"message": "SECRET SDK body", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": duration}]}}
    headers = {"Authorization": "SECRET"}
    if header is not None:
        headers["Retry-After"] = header
    response = httpx.Response(429, headers=headers, json=body)
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.models.generate_content.side_effect = errors.ClientError(429, body, response)
    monkeypatch.setattr(genai, "Client", Mock(return_value=client))
    with pytest.raises(RetryableError) as raised:
        _google_transport("fake-model", "prompt", 2)
    error = raised.value
    assert error.http_code == 429 and error.retry_after_seconds == expected
    assert error.args == ()
    assert "SECRET" not in str(error) + repr(error) + repr(vars(error))


@pytest.mark.parametrize("hint,delays", [(None, [2, 4]), (7, [7, 7]), (1000, [60, 60])])
def test_fill_retry_respects_safe_delay_with_bounded_attempts(tmp_path, monkeypatch, hint, delays):
    config = project(tmp_path, [FIXTURES[0]], extra="retries=2\n")
    sleep = Mock()
    monkeypatch.setattr("pokeeper.gemini.time.sleep", sleep)
    transport = Mock(side_effect=RetryableError(429, hint))
    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=transport)
    assert transport.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == delays
    assert report(candidate)["gemini"][0]["status"] == "retry_exhausted"


@pytest.mark.parametrize("which", ["state-lock", "state-pending", "input-lock", "candidate-lock", "hardlink", "symlink"])
def test_cache_transaction_alias_is_refused_without_spending(tmp_path, which):
    config = project(tmp_path, [FIXTURES[0]])
    candidate = tmp_path / "candidate"
    targets = {"state-lock": tmp_path / "state/current.json.lock",
               "state-pending": tmp_path / "state/current.json.pending",
               "input-lock": tmp_path / "messages.pot.lock",
               "candidate-lock": tmp_path / "candidate.lock",
               "hardlink": tmp_path / "hardlink", "symlink": tmp_path / "symlink"}
    cache = targets[which]
    if which == "hardlink":
        cache.hardlink_to(config)
    elif which == "symlink":
        cache.symlink_to(config)
    fake = Fake()
    with pytest.raises((KeeperError, TransactionError)):
        fill(config, candidate, cache, transport=fake)
    assert not fake.calls


def test_existing_candidate_and_offline_format_failure_never_spend(tmp_path, monkeypatch):
    config = project(tmp_path, [FIXTURES[0]])
    fake = Fake()
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(KeeperError, match="candidate already exists"):
        fill(config, existing, tmp_path / "cache", transport=fake)
    monkeypatch.setattr("pokeeper.gemini.gettext_check", Mock(side_effect=KeeperError("msgfmt unavailable")))
    with pytest.raises(KeeperError, match="msgfmt unavailable"):
        fill(config, tmp_path / "candidate", tmp_path / "cache", transport=fake)
    assert not fake.calls


def test_unflagged_placeholders_are_checked_for_model_results(tmp_path):
    config = project(tmp_path, [FIXTURES[6]])
    po = polib.pofile(str(tmp_path / "messages.pot"))
    po[0].flags = []
    (tmp_path / "messages.pot").write_bytes(serialize(po))
    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=Fake({"named-placeholder": ["Witaj"]}))
    assert report(candidate)["gemini"][0]["status"] == "placeholders_or_tokens"


@pytest.mark.parametrize("original,translated,expected", [
    ("25% of Dexterity", "敏捷的25%", "completed"),
    ("15% faster", "加快15%", "completed"),
    ("50% higher", "提高50%", "completed"),
    ("25% of %s", "%s的25%", "completed"),
    ("25% of %s", "数值的25%", "placeholders_or_tokens"),
    ("Hello %s", "你好%s", "completed"),
    ("Hello %s", "你好", "placeholders_or_tokens"),
    ("Hello %(name)s", "你好%(name)s", "completed"),
    ("Hello %(name)s", "你好", "placeholders_or_tokens"),
    ("Hello %1$s", "你好%1$s", "completed"),
    ("Hello %1$s", "你好", "placeholders_or_tokens"),
    ("Uses 3%s", "使用3%s", "completed"),
    ("Uses 3%s", "使用3个", "placeholders_or_tokens"),
    ("Value: % d", "数值：% d", "completed"),
    ("Value: % d", "数值", "placeholders_or_tokens"),
])
def test_unflagged_numeric_percentages_and_real_placeholders(tmp_path, original, translated, expected):
    fixture = {"context": None, "msgid": original, "plural": None,
               "comments": "Unflagged game prose.", "occurrences": [["data/test.json", "1"]]}
    config = project(tmp_path, [fixture])
    template = tmp_path / "messages.pot"
    po = polib.pofile(str(template))
    po[0].flags = []
    template.write_bytes(serialize(po))

    def send(model, prompt, timeout):
        payload = json.loads(prompt)["entries"][0]
        return {"translations": [{"id": payload["id"], "identity": payload["identity"],
                                   "values": [translated]}]}

    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=send)
    assert report(candidate)["gemini"][0]["status"] == expected
    result = parse_po((candidate / "candidate.po").read_bytes())
    assert result[0].msgstr == (translated if expected == "completed" else "")


@pytest.mark.parametrize("translated,expected", [
    ("%2$s otrzymuje od %1$s %3$d strzałów.", "completed"),
    ("%1$s strzela.", "gettext_format"),
    ("%2$s otrzymuje od %1$s %3$s strzałów.", "gettext_format"),
])
def test_c_format_model_reordering_acceptance_and_invalid_arguments(tmp_path, translated, expected):
    fixture = {"context": None, "msgid": "%s shoots %s with %d rounds.", "plural": None,
               "comments": "First argument is shooter, second target, third round count.",
               "occurrences": [["src/combat.cpp", "1"]]}
    config = project(tmp_path, [fixture])

    def send(model, prompt, timeout):
        payload = json.loads(prompt)["entries"][0]
        return {"translations": [{"id": payload["id"], "identity": payload["identity"],
                                   "values": [translated]}]}

    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=send)
    assert report(candidate)["gemini"][0]["status"] == expected
    po = parse_po((candidate / "candidate.po").read_bytes())
    assert po[0].msgstr == (translated if expected == "completed" else "")


def test_duplicate_json_keys_and_no_duplicate_update_report(tmp_path):
    config = project(tmp_path, [FIXTURES[0]])
    def duplicate(model, prompt, timeout):
        return '{"translations":[],"translations":' + json.dumps(response(prompt)["translations"]) + '}'
    bad = tmp_path / "candidate-1"
    fill(config, bad, tmp_path / "cache-1", transport=duplicate)
    assert report(bad)["gemini"][0]["status"] == "response_identity"
    good = tmp_path / "candidate-2"
    fill(config, good, tmp_path / "cache-2", transport=Fake())
    assert len(report(good)["updates"]) == 1


def test_configuration_change_cannot_silently_retry_unknown(tmp_path):
    config = project(tmp_path, [FIXTURES[0]])
    cache = tmp_path / "cache"
    fill(config, tmp_path / "candidate-1", cache, transport=Mock(side_effect=UnknownOutcome()))
    with config.open("a") as f:
        f.write('prompt="Now formal"\n')
    fake = Fake()
    second = tmp_path / "candidate-2"
    fill(config, second, cache, transport=fake)
    assert not fake.calls
    assert report(second)["gemini"][0]["status"] == "unknown"
    third = tmp_path / "candidate-3"
    fill(config, third, cache, transport=fake, retry_unknown=True)
    assert len(fake.calls) == 1
    assert report(third)["gemini"][0]["retried_unknown"] is True
    history = json.loads(cache.read_text())["unknown_history"]
    assert len(history) == 1 and history[0]["status"] == "unknown"


@pytest.mark.parametrize("status", ["complete", "unknown"])
def test_sampling_policy_change_separates_old_cache_but_preserves_unknown_guard(tmp_path, status):
    config = project(tmp_path, [FIXTURES[0]])
    cache = tmp_path / "cache"
    first = Fake()

    def send(model, prompt, timeout):
        if status == "unknown":
            first.calls.append((model, json.loads(prompt), timeout))
            raise UnknownOutcome()
        return first(model, prompt, timeout)

    fill(config, tmp_path / "candidate-1", cache, transport=send)
    model, prompt, _ = first.calls[0]
    assert prompt["protocol"] == 2
    assert prompt["generation"] == {"sampling": "server-default-sampling", "response_mime_type": "application/json"}

    # Reconstruct the exact old protocol-1 cache identity: temperature=0 was
    # fixed in the transport, so no generation parameters appeared in its prompt.
    legacy_policy = dict(prompt)
    payloads = legacy_policy.pop("entries")
    del legacy_policy["generation"]
    legacy_policy["protocol"] = 1
    fingerprint = digest(json_bytes({"policy": legacy_policy, "entry": payloads[0],
                                     "model": model, "config": load_config(config).data}))
    legacy_prompt = json_bytes({**legacy_policy, "entries": payloads}).decode()
    legacy_request = digest(json_bytes({"model": model, "prompt": legacy_prompt}))
    saved = json.loads(cache.read_bytes())
    record = next(iter(saved["entries"].values()))
    record["request"] = legacy_request
    saved["entries"] = {fingerprint: record}
    cache.write_bytes(json_bytes(saved))

    second = Fake()
    candidate = tmp_path / "candidate-2"
    fill(config, candidate, cache, transport=second)
    if status == "complete":
        assert len(second.calls) == 1
        assert report(candidate)["gemini"][0]["status"] == "completed"
        assert len(json.loads(cache.read_bytes())["entries"]) == 2
    else:
        assert not second.calls
        assert report(candidate)["gemini"][0]["status"] == "unknown"
        assert report(candidate)["gemini"][0]["reason"] == "retry_may_charge_again"
        fill(config, tmp_path / "candidate-3", cache, transport=second, retry_unknown=True)
        assert len(second.calls) == 1
        history = json.loads(cache.read_bytes())["unknown_history"]
        assert history[0]["request"] == legacy_request and history[0]["status"] == "unknown"


def test_invalid_unicode_response_is_failed_without_losing_candidate(tmp_path):
    config = project(tmp_path, [FIXTURES[0]])
    candidate = tmp_path / "candidate"
    fill(config, candidate, tmp_path / "cache", transport=Fake({"missing-context": ["\ud800"]}))
    assert report(candidate)["gemini"][0]["status"] == "encoding"
    assert len(report(candidate)["gaps"]) == 1
