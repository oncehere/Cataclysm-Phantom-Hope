import json
from unittest.mock import Mock

import pytest

from pokeeper.catalog import entry_id, json_bytes, parse_po, serialize
from pokeeper.cli import main
from pokeeper.config import KeeperError
from pokeeper.core import plan
from pokeeper.exchange import export_bundle, import_bundle, response_status
from pokeeper.gemini import fill
from pokeeper.transaction import TransactionError, apply_candidate, digest
from test_gemini import FIXTURES, Fake, project, response


@pytest.fixture(autouse=True)
def no_api(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    blocked = Mock(side_effect=AssertionError("offline operation attempted a network request"))
    monkeypatch.setattr("pokeeper.gemini._google_transport", blocked)
    monkeypatch.setattr("socket.socket.connect", blocked)
    yield
    blocked.assert_not_called()


def bundle(tmp_path, **kwargs):
    config = project(tmp_path)
    base = tmp_path / "base"
    plan(config, base)
    pack = tmp_path / "pack"
    export_bundle(base, pack, **kwargs)
    return config, base, pack


def answer(pack, key):
    request = (pack / "requests" / f"{key}.json").read_bytes()
    rows = response(request)["translations"]
    value = {"request_sha256": digest(request),
             "producer": {"tool": "Antigravity", "model": "not-reported"},
             "translations": [{"id": r["id"], "values": r["values"]} for r in rows]}
    path = pack / "responses" / f"{key}.json"
    path.write_bytes(json_bytes(value))
    return path, value


def answer_all(pack):
    manifest = json.loads((pack / "manifest.json").read_bytes())
    for key in manifest["batches"]:
        answer(pack, key)


def test_same_compatibility_fixtures_offline_roundtrip(tmp_path):
    config, base, pack = bundle(tmp_path, batch_size=2)
    packets = [json.loads(p.read_bytes()) for p in (pack / "requests").glob("*.json")]
    assert all(len(p["entries"]) <= 2 and len({r["context"] for r in p["entries"]}) == 1 for p in packets)
    contexts = {r["context"] for p in packets for r in p["entries"]}
    assert {None, "", "audit:verb", "audit:adjective"} <= contexts
    assert all(r["developer_comments"] and r["occurrences"] for p in packets for r in p["entries"])
    answer_all(pack)
    assert response_status(pack)["status"] == "PASS"
    candidate = tmp_path / "imported"
    import_bundle(pack, candidate)
    po = parse_po((candidate / "candidate.po").read_bytes())
    expected = {f["msgid"] + str(f["context"]): f["translations"] for f in FIXTURES}
    for entry in po:
        got = [entry.msgstr_plural[i] for i in range(3)] if entry.msgid_plural else [entry.msgstr]
        assert got == expected[entry.msgid + str(entry.msgctxt)]
    state = json.loads((candidate / "state.json").read_bytes())
    assert all(not r["protected"] for r in state["entries"].values())
    assert all(r["kind"] == "external" and r["name"] == "Antigravity / not-reported" for r in state["references"].values())
    apply_candidate(candidate)
    next_candidate = tmp_path / "next"
    plan(config, next_candidate)
    assert (candidate / "candidate.po").read_bytes() == (next_candidate / "candidate.po").read_bytes()
    report = json.loads((next_candidate / "report.json").read_bytes())
    assert not report["human_changes"] and not report["updates"] and not report["gaps"]


def test_partial_resume_reuses_files_and_preserves_protected_blanks(tmp_path):
    config = project(tmp_path)
    first = tmp_path / "first"
    fill(config, first, tmp_path / "cache", transport=Fake())
    apply_candidate(first)
    catalog = tmp_path / "pl.po"
    po = parse_po(catalog.read_bytes())
    protected_id = entry_id(po[0])
    po[0].msgstr = ""
    # A newly added template identity remains an ordinary unprotected gap.
    template = parse_po((tmp_path / "messages.pot").read_bytes())
    template.append(type(po[0])(msgid="New untranslated message"))
    (tmp_path / "messages.pot").write_bytes(serialize(template))
    catalog.write_bytes(serialize(po))
    base, pack = tmp_path / "base", tmp_path / "pack"
    plan(config, base)
    result = export_bundle(base, pack)
    assert result["entries"] == 1
    assert response_status(pack)["status"] == "INCOMPLETE"
    candidate = tmp_path / "partial"
    import_bundle(pack, candidate)
    state = json.loads((candidate / "state.json").read_bytes())
    assert state["entries"][protected_id]["protected"]
    assert len(json.loads((candidate / "report.json").read_bytes())["gaps"]) == 2
    # Creating a response after import invalidates the earlier candidate.
    packet_path = pack / "requests" / "0001.json"
    payload = json.loads(packet_path.read_bytes())
    (pack / "responses" / "0001.json").write_bytes(json_bytes({
        "request_sha256": digest(packet_path.read_bytes()), "producer": {"tool": "Editor", "model": "not-reported"},
        "translations": [{"id": payload["entries"][0]["id"], "values": ["Nowa wiadomość"]}]}))
    with pytest.raises(TransactionError, match="input changed"):
        apply_candidate(candidate)
    resumed = tmp_path / "resumed"
    import_bundle(pack, resumed)
    assert response_status(pack)["completed_entries"] == 1
    apply_candidate(resumed)
    assert parse_po(catalog.read_bytes())[0].msgstr == ""


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_id", "wrong_hash", "wrong_plural", "placeholder", "newline", "extra_field", "invalid_json"])
def test_reject_invalid_response_without_changing_po(tmp_path, mutation):
    config, base, pack = bundle(tmp_path)
    answer_all(pack)
    paths = list((pack / "responses").glob("*.json"))
    path = paths[0]
    if mutation in ("wrong_plural", "placeholder", "newline"):
        path = next(p for p in paths if any(
            len(r["values"]) == 3 if mutation == "wrong_plural" else
            any("%d" in v for v in r["values"]) if mutation == "placeholder" else
            any("\n" in v for v in r["values"])
            for r in json.loads(p.read_bytes())["translations"]))
    value = json.loads(path.read_bytes())
    rows = value["translations"]
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "wrong_id":
        rows[0]["id"] = "0" * 64
    elif mutation == "wrong_hash":
        value["request_sha256"] = "0" * 64
    elif mutation == "wrong_plural":
        next(r for r in rows if len(r["values"]) == 3)["values"].pop()
    elif mutation == "placeholder":
        for r in rows:
            r["values"] = [v.replace("%d", "%s") for v in r["values"]]
    elif mutation == "newline":
        for r in rows:
            r["values"] = [v.replace("\n", "") for v in r["values"]]
    elif mutation == "extra_field":
        rows[0]["identity"] = [None, "injected", None]
    path.write_bytes(b"{" if mutation == "invalid_json" else json_bytes(value))
    assert response_status(pack)["status"] == "FAIL"
    with pytest.raises(KeeperError, match="invalid response batch"):
        import_bundle(pack, tmp_path / "bad")
    assert not (tmp_path / "pl.po").exists() and not (tmp_path / "bad").exists()


@pytest.mark.parametrize("changed", ["config", "request", "response", "po"])
def test_stale_input_rejected(tmp_path, changed):
    config, base, pack = bundle(tmp_path)
    answer_all(pack)
    candidate = tmp_path / "candidate"
    import_bundle(pack, candidate)
    if changed == "po":
        path = tmp_path / "pl.po"
    elif changed == "config":
        path = config
    else:
        path = next((pack / (changed + "s")).glob("*.json"))
    path.write_bytes((path.read_bytes() if path.exists() else b"") + b"\n")
    with pytest.raises(TransactionError, match="input changed"):
        apply_candidate(candidate)


def test_external_replaced_by_upstream_then_history_retained(tmp_path):
    config, base, pack = bundle(tmp_path)
    answer_all(pack)
    candidate = tmp_path / "candidate"
    import_bundle(pack, candidate)
    apply_candidate(candidate)
    po = parse_po((tmp_path / "pl.po").read_bytes())
    po[0].msgstr = "Nowe upstream"
    (tmp_path / "donor.po").write_bytes(serialize(po))
    config.write_text(config.read_text().replace("[rules]", '[[sources]]\nname="upstream"\npath="donor.po"\n[rules]'))
    second = tmp_path / "second"
    plan(config, second)
    apply_candidate(second)
    assert parse_po((tmp_path / "pl.po").read_bytes())[0].msgstr == "Nowe upstream"
    before = json.loads((second / "state.json").read_bytes())
    po.clear()
    (tmp_path / "donor.po").write_bytes(serialize(po))
    third = tmp_path / "third"
    plan(config, third)
    after = json.loads((third / "state.json").read_bytes())
    assert before["entries"] == after["entries"]
    assert before["references"] == after["references"]


def test_cache_only_never_sends_and_does_not_mutate_cache(tmp_path):
    config = project(tmp_path)
    cache = tmp_path / "cache.json"
    fill(config, tmp_path / "online-fake", cache, transport=Fake())
    saved = json.loads(cache.read_bytes())
    records = list(saved["entries"].values())
    records[0]["status"] = "unknown"
    records[1]["status"] = "inflight"
    cache.write_bytes(json_bytes(saved))
    before = cache.read_bytes()
    candidate = tmp_path / "offline"
    fill(config, candidate, cache, cache_only=True)
    assert cache.read_bytes() == before
    report = json.loads((candidate / "report.json").read_bytes())
    assert len(report["gaps"]) == 2
    assert sum(r["status"] == "cached" for r in report["gemini"]) == len(FIXTURES) - 2
    apply_candidate(candidate)
    with pytest.raises(KeeperError, match="cannot retry"):
        fill(config, tmp_path / "bad", cache, retry_unknown=True, cache_only=True)


def test_cli_missing_response_and_overwrite_rejection(tmp_path, capsys):
    config, base, pack = bundle(tmp_path)
    assert main(["responses", str(pack)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "INCOMPLETE"
    with pytest.raises(KeeperError, match="already exists"):
        export_bundle(base, pack)
    with pytest.raises(KeeperError, match="separate"):
        export_bundle(base, base / "pack")
    assert main(["responses", str(pack), "--batch", "../bad"]) == 2


def test_interrupted_export_does_not_publish_partial_bundle(tmp_path, monkeypatch):
    config = project(tmp_path)
    base, pack = tmp_path / "base", tmp_path / "pack"
    plan(config, base)
    from pokeeper import exchange
    write = exchange.atomic_write
    def interrupted(path, data):
        if path.parent.name == "requests":
            raise KeyboardInterrupt()
        write(path, data)
    monkeypatch.setattr(exchange, "atomic_write", interrupted)
    with pytest.raises(KeyboardInterrupt):
        export_bundle(base, pack)
    assert not pack.exists() and not list(tmp_path.glob(".pack.*"))
    assert not (tmp_path / "pl.po").exists()


def test_rehashed_request_tamper_cannot_change_identity_or_rules(tmp_path):
    config, base, pack = bundle(tmp_path)
    path = next((pack / "requests").glob("*.json"))
    packet = json.loads(path.read_bytes())
    packet["entries"][0]["context"] = "forged context"
    path.write_bytes(json_bytes(packet))
    manifest_path = pack / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["batches"][path.stem] = digest(path.read_bytes())
    manifest_path.write_bytes(json_bytes(manifest))
    with pytest.raises(KeeperError, match="no longer matches"):
        import_bundle(pack, tmp_path / "forged")


def test_configured_tags_and_bad_json_field_duplicates_are_rejected(tmp_path):
    selected = [{"context": None, "msgid": "<name> waves", "plural": None,
                 "comments": "Runtime token", "occurrences": [["sample.c", "2"]]}]
    config = project(tmp_path, selected)
    config.write_text(config.read_text().replace("preserve_newlines=true", "preserve_newlines=true\ntoken_patterns=['<[^>]+>']"))
    base, pack = tmp_path / "base", tmp_path / "pack"
    plan(config, base)
    export_bundle(base, pack)
    raw = (pack / "requests" / "0001.json").read_bytes()
    item = json.loads(raw)["entries"][0]
    response_path = pack / "responses" / "0001.json"
    value = {"request_sha256": digest(raw), "producer": {"tool": "Agent", "model": "not-reported"},
             "translations": [{"id": item["id"], "values": ["<other> macha"]}]}
    response_path.write_bytes(json_bytes(value))
    assert response_status(pack)["failures"][0]["errors"][0]["reason"] == "placeholders_or_tokens"
    response_path.write_text('{"translations": [], "translations": []}')
    assert response_status(pack)["status"] == "FAIL"
