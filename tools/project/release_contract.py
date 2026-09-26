#!/usr/bin/env python3
"""Read-only local release contracts; no signing, upload or publication."""

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHA = r"[0-9a-f]{40}"
DIGEST = r"[0-9a-f]{64}"
SYSTEMS = {"windows", "linux", "macos", "android"}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def identity(source_sha, inputs_digest):
    require(isinstance(source_sha, str) and
            re.fullmatch(SHA, source_sha) is not None, "invalid source SHA")
    require(isinstance(inputs_digest, str) and
            re.fullmatch(DIGEST, inputs_digest) is not None,
            "invalid inputs digest")
    candidate = "cph-dev-" + digest({
        "schema_version": 1, "source_sha": source_sha,
        "inputs_digest": inputs_digest,
    })
    return {"candidate_id": candidate, "tag": "dev-" + candidate}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def load(path):
    require(path.stat().st_size <= 8 * 1024 * 1024,
            "JSON input exceeds 8 MiB limit")
    return parse_json(path.read_bytes())


def parse_json(payload):
    require(len(payload) <= 8 * 1024 * 1024, "JSON exceeds 8 MiB limit")
    return json.loads(payload, object_pairs_hook=unique_object,
                      parse_constant=lambda value: require(
                          False, "non-finite JSON value: " + value))


def load_pinned(path, expected_sha256):
    require(re.fullmatch(DIGEST, expected_sha256) is not None,
            "trusted input pin must be a SHA256")
    require(path.stat().st_size <= 8 * 1024 * 1024,
            "trusted JSON exceeds 8 MiB limit")
    payload = path.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == expected_sha256,
            "trusted input file differs from independent controller pin")
    return parse_json(payload)


def validate(value, schema, location="manifest"):
    """Validate the bounded JSON Schema subset used by our pinned schema."""
    types = {"object": dict, "array": list, "string": str,
             "integer": int, "boolean": bool, "null": type(None)}
    kind = schema["type"]
    require(type(value) is types[kind], location + ": wrong type")
    if "const" in schema:
        require(value == schema["const"], location + ": wrong constant")
    if "enum" in schema:
        require(value in schema["enum"], location + ": unsupported value")
    if kind == "object":
        properties = schema["properties"]
        require(set(schema["required"]) <= set(value),
                location + ": missing required field")
        require(not (set(value) - set(properties)),
                location + ": unknown field")
        for key, item in value.items():
            validate(item, properties[key], location + "." + key)
    elif kind == "array":
        require(len(value) >= schema.get("minItems", 0),
                location + ": empty required collection")
        require(len(value) <= schema.get("maxItems", 10000),
                location + ": too many items")
        for index, item in enumerate(value):
            validate(item, schema["items"], f"{location}[{index}]")
    elif kind == "string":
        require(len(value) >= schema.get("minLength", 0),
                location + ": empty required string")
        if schema.get("minLength", 0):
            require(bool(value.strip()), location + ": whitespace-only string")
        require(len(value) <= schema.get("maxLength", 4096),
                location + ": string too long")
        if "pattern" in schema:
            require(re.fullmatch(schema["pattern"], value) is not None,
                    location + ": invalid string")
    elif kind == "integer":
        require(value >= schema.get("minimum", 0),
                location + ": value below minimum")
        require(value <= schema.get("maximum", 2 ** 63 - 1),
                location + ": value above maximum")


def unique(items, key, label):
    result = {item[key]: item for item in items}
    require(len(result) == len(items), "duplicate " + label)
    return result


def file_digest(root, relative):
    path = Path(relative)
    require(relative and not path.is_absolute() and
            ".." not in path.parts and "\\" not in relative,
            "unsafe artifact/evidence path")
    root = root.resolve(strict=True)
    target = root / path
    require(all(not (root / part).is_symlink()
                for part in [path, *path.parents]),
            "artifact/evidence symlink rejected")
    require(target.resolve(strict=True).is_relative_to(root) and
            target.is_file(), "artifact/evidence is not a regular file")
    require(target.stat().st_size > 0, "empty artifact/evidence")
    with target.open("rb") as stream:
        result = hashlib.file_digest(stream, "sha256").hexdigest()
    return target.stat().st_size, result


def verify(manifest, expected, artifacts_root, evidence_root):
    """Expected facts must come from an independent trusted controller."""
    require(expected.get("configuration_status") == "READY",
            "trusted release targets/identity/signing are not configured")
    require(set(expected) == {
        "schema_version", "configuration_status", "decision_reference",
        "inputs", "manifest", "signing_requirements", "android_allocation",
    }, "unknown or missing expected-input field")
    require(expected["schema_version"] == 1 and
            type(expected["schema_version"]) is int,
            "unsupported expected schema")
    require(isinstance(expected["decision_reference"], str) and
            expected["decision_reference"].strip(),
            "independent policy decision reference required")
    schema = load(ROOT / "project/release-manifest.schema.json")
    validate(manifest, schema)
    validate(expected["manifest"], schema, "expected.manifest")
    require(manifest == expected["manifest"],
            "candidate differs from independent expected facts")
    inputs = expected["inputs"]
    require(type(inputs) is dict and set(inputs) == {
        "asset_lock_sha256", "target_config_sha256",
        "check_policy_sha256", "toolchain_config_sha256", "policy_sha",
    }, "complete locked input digests required")
    for key, value in inputs.items():
        pattern = SHA if key == "policy_sha" else DIGEST
        require(isinstance(value, str) and re.fullmatch(pattern, value),
                "invalid trusted input " + key)
    require(inputs["policy_sha"] == manifest["policy_sha"] and
            digest(inputs) == manifest["inputs_digest"],
            "policy/resource/target/toolchain inputs do not match")
    stable = identity(manifest["source_sha"], manifest["inputs_digest"])
    require(all(manifest[key] == value for key, value in stable.items()),
            "candidate/tag does not match stable input identity")
    platforms = unique(manifest["platforms"], "target_id", "target")
    require(len(platforms) >= 4 and
            {item["os"] for item in platforms.values()} == SYSTEMS,
            "configured targets must cover all four platforms")
    artifacts = unique(manifest["artifacts"], "name", "artifact name")
    require({item["target_id"] for item in artifacts.values()} ==
            set(platforms), "missing platform artifact")
    checks = unique(manifest["checks"], "check_id", "check ID")
    require({item["target_id"] for item in checks.values()} == set(platforms),
            "missing required platform checks")
    signing = expected["signing_requirements"]
    require(type(signing) is dict and set(signing) == set(platforms),
            "explicit signing policy needed for every target")
    for target in platforms.values():
        require(target["identity_status"] == "permanent",
                "temporary/test application identity cannot be released")
    for check in checks.values():
        require(check["repository_id"] == manifest["repository_id"] and
                check["tested_source"] == manifest["source_sha"] and
                check["tested_tree"] == manifest["source_tree"] and
                check["inputs_digest"] == manifest["inputs_digest"] and
                check["policy_sha"] == manifest["policy_sha"],
                "check source/tree/inputs/policy mismatch")
        if check["kind"] == "test":
            require(check["test_count"] > 0 and
                    check["assertion_count"] > 0, "zero-test PASS rejected")
        _, actual = file_digest(evidence_root, check["evidence_reference"])
        require(actual == check["evidence_sha256"],
                "check evidence digest mismatch")
    for name, artifact in artifacts.items():
        require(Path(name).name == name and name not in {".", ".."},
                "artifact name must be a basename")
        size, actual = file_digest(artifacts_root, name)
        require(size == artifact["size"] and actual == artifact["sha256"],
                "actual package size/digest mismatch")
        require(artifact["repository_id"] == manifest["repository_id"] and
                artifact["tested_source"] == manifest["source_sha"] and
                artifact["tested_tree"] == manifest["source_tree"] and
                artifact["inputs_digest"] == manifest["inputs_digest"],
                "artifact source/tree/resources mismatch")
        policy = signing[artifact["target_id"]]
        require(type(policy) is dict and set(policy) ==
                {"required", "identity"} and
                type(policy["required"]) is bool and
                isinstance(policy["identity"], str),
                "invalid trusted signing requirement")
        if platforms[artifact["target_id"]]["os"] == "android":
            require(policy["required"],
                    "Android requires its permanent signing identity")
        proof = artifact["signing"]
        require(proof["payload_sha256"] == actual,
                "package changed after signature verification")
        if policy["required"]:
            require(policy["identity"] and proof["status"] == "VERIFIED" and
                    proof["identity"] == policy["identity"],
                    "required permanent signing identity mismatch")
            _, actual_proof = file_digest(
                evidence_root, proof["evidence_reference"])
            require(actual_proof == proof["evidence_sha256"],
                    "signature-verifier evidence digest mismatch")
        else:
            require(proof["status"] == "NOT_REQUIRED" and
                    proof["identity"] == policy["identity"] == "" and
                    proof["evidence_reference"] == "" and
                    proof["evidence_sha256"] == "",
                    "unrequested signing claim rejected")
    allocation = expected["android_allocation"]
    require(type(allocation) is dict and set(allocation) == {
        "candidate_id", "version_code", "last_published_version_code",
    }, "independent persistent Android allocation required")
    require(type(allocation["version_code"]) is int and
            type(allocation["last_published_version_code"]) is int and
            allocation["last_published_version_code"] >= 0 and
            allocation["candidate_id"] == manifest["candidate_id"] and
            allocation["version_code"] == manifest["android_version_code"] and
            allocation["version_code"] >
            allocation["last_published_version_code"],
            "Android versionCode is unallocated, reused, or decreasing")
    return {
        "status": "PASS", "local_contract_verified": True,
        "manifest_sha256": digest(manifest), **stable,
        "public_release_ready": False,
        "deployment": "IMPLEMENTED_NOT_DEPLOYED",
        "scope": "Local contract only; expected facts require an independent "
                 "trusted controller. No platform/signature tools run here.",
    }


def release_state(pages, trusted):
    """Classify complete recorded API pages without publishing anything."""
    require(type(pages) is list and 0 < len(pages) <= 100,
            "a complete bounded page sequence is required")
    require(type(trusted) is dict and set(trusted) == {
        "repository_id", "requested", "verified_receipts",
        "blocked_candidates", "superseded_candidates",
        "draft_visibility_verified", "observations_digest",
    }, "independent state receipts/configuration required")
    require(trusted["observations_digest"] == digest(pages),
            "API observations differ from independently pinned snapshot")
    require(trusted["draft_visibility_verified"] is True,
            "draft visibility is unverified; absence cannot mean no candidate")
    repository = trusted["repository_id"]
    require(type(repository) is int and repository > 0,
            "explicit target repository ID required")
    requested = trusted["requested"]
    validate_identity_record(requested)
    for key in ["blocked_candidates", "superseded_candidates"]:
        require(type(trusted[key]) is list and all(
            isinstance(item, str) and re.fullmatch("cph-dev-" + DIGEST, item)
            for item in trusted[key]), "invalid candidate-control list")
    excluded = (trusted["blocked_candidates"] +
                trusted["superseded_candidates"])
    require(type(trusted["verified_receipts"]) is list,
            "trusted receipts must be a list")
    for receipt in trusted["verified_receipts"]:
        require(type(receipt) is dict and set(receipt) == {
            "release_id", "identity", "manifest_sha256", "contract_verified",
        }, "invalid trusted release receipt")
        require(type(receipt["release_id"]) is int and
                receipt["release_id"] > 0 and
                type(receipt["contract_verified"]) is bool and
                isinstance(receipt["manifest_sha256"], str) and
                re.fullmatch(DIGEST, receipt["manifest_sha256"]),
                "invalid trusted receipt types")
        validate_identity_record(receipt["identity"])
    receipts = unique(trusted["verified_receipts"], "release_id", "receipt")
    releases = []
    seen = set()
    consumed_receipts = set()
    for number, page in enumerate(pages, 1):
        require(type(page) is dict and set(page) == {
            "repository_id", "page", "http_status", "error",
            "next_page", "releases",
        }, "invalid recorded API page")
        require(page["http_status"] == 200 and page["error"] is None,
                "release state read failed; not an empty release history")
        require(type(page["page"]) is int and page["page"] == number and
                type(page["repository_id"]) is int and
                page["repository_id"] == repository,
                "wrong repository or incomplete/reordered pagination")
        expected_next = number + 1 if number < len(pages) else None
        require(page["next_page"] == expected_next,
                "incomplete pagination: next page not consumed")
        require(type(page["releases"]) is list and
                len(page["releases"]) <= 100,
                "release page body is not an array")
        for item in page["releases"]:
            require(type(item) is dict and set(item) == {
                "id", "draft", "prerelease", "tag_name", "published_at",
                "tag_source_sha", "manifest_sha256",
            }, "invalid normalized release observation")
            require(type(item["id"]) is int and item["id"] > 0 and
                    item["id"] not in seen, "duplicate/invalid release ID")
            seen.add(item["id"])
            require(type(item["draft"]) is bool and
                    type(item["prerelease"]) is bool and
                    isinstance(item["tag_name"], str), "invalid release flags")
            if not item["tag_name"].startswith("dev-cph-dev-"):
                continue
            require(item["prerelease"],
                    "controlled development tag was promoted to stable")
            require(item["id"] in receipts,
                    "project release lacks independent manifest/tag receipt")
            receipt = receipts[item["id"]]
            bound = receipt["identity"]
            require(item["manifest_sha256"] == receipt["manifest_sha256"] and
                    item["tag_name"] == bound["tag"] and
                    item["tag_source_sha"] == bound["source_sha"],
                    "remote tag/manifest differs from independent receipt")
            consumed_receipts.add(item["id"])
            if not item["draft"]:
                require(receipt["contract_verified"] is True,
                        "published release lacks verified contract")
                published = item["published_at"]
                require(isinstance(published, str),
                        "published release lacks publication timestamp")
                timestamp = datetime.datetime.fromisoformat(
                    published.replace("Z", "+00:00"))
                require(timestamp.tzinfo is not None,
                        "publication timestamp lacks timezone")
            releases.append({**bound, "release_id": item["id"],
                             "draft": item["draft"],
                             "published_at": item["published_at"]})
    require(consumed_receipts == set(receipts),
            "known candidate receipt is missing/renamed remotely; reconcile "
            "without forgetting its reserved versionCode")
    unique(releases, "candidate_id", "remote logical candidate")
    unique(releases, "android_version_code", "reserved Android versionCode")
    require(not any(
        item["android_version_code"] == requested["android_version_code"] and
        item["candidate_id"] != requested["candidate_id"]
        for item in releases),
        "requested Android versionCode belongs to another candidate")
    published = [item for item in releases if not item["draft"]]
    latest = max((item for item in published
                  if item["candidate_id"] not in excluded),
                 key=lambda item: item["android_version_code"], default=None)
    maximum_published_code = max(
        (item["android_version_code"] for item in published), default=0)
    same = [item for item in releases
            if item["candidate_id"] == requested["candidate_id"]]
    require(len(same) <= 1, "duplicate remote logical candidate")
    if requested["candidate_id"] in excluded:
        action = "BLOCKED"
    elif same and not same[0]["draft"]:
        require(same[0]["android_version_code"] ==
                requested["android_version_code"],
                "published candidate allocation changed")
        action = "ALREADY_PUBLISHED"
    elif requested["android_version_code"] <= maximum_published_code:
        action = "BLOCKED_OLD_CANDIDATE"
    else:
        if same:
            require(same[0]["android_version_code"] ==
                    requested["android_version_code"],
                    "retry changed reserved Android versionCode")
        action = "RETRY_SAME_CANDIDATE" if same else "NEW_CANDIDATE"
    return {
        "status": "PASS", "action": action, "latest_development": latest,
        "pages_consumed": len(pages), "public_release_ready": False,
        "observation": "RECORDED_READ_ONLY_INPUT",
        "scope": "Local state classification, not a fresh remote query, "
                 "transaction reservation, or permission to publish.",
    }


def validate_identity_record(record):
    require(type(record) is dict and set(record) == {
        "source_sha", "inputs_digest", "candidate_id", "tag",
        "android_version_code",
    }, "incomplete candidate identity record")
    stable = identity(record["source_sha"], record["inputs_digest"])
    require(all(record[key] == value for key, value in stable.items()),
            "unstable candidate/tag identity")
    require(type(record["android_version_code"]) is int and
            0 < record["android_version_code"] <= 2100000000,
            "invalid Android versionCode")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    identify = sub.add_parser("identify")
    identify.add_argument("--source-sha", required=True)
    identify.add_argument("--inputs", required=True, type=Path)
    check = sub.add_parser("verify")
    check.add_argument("--manifest", required=True, type=Path)
    check.add_argument("--expected", required=True, type=Path)
    check.add_argument("--expected-sha256", required=True)
    check.add_argument("--artifacts-root", required=True, type=Path)
    check.add_argument("--evidence-root", required=True, type=Path)
    state = sub.add_parser("state")
    state.add_argument("--pages", required=True, type=Path)
    state.add_argument("--trusted-state", required=True, type=Path)
    state.add_argument("--trusted-state-sha256", required=True)
    sub.add_parser("prerequisites")
    args = parser.parse_args(argv)
    try:
        if args.command == "identify":
            inputs_digest = digest(load(args.inputs))
            result = {"inputs_digest": inputs_digest,
                      **identity(args.source_sha, inputs_digest),
                      "public_release_ready": False}
        elif args.command == "verify":
            result = verify(
                load(args.manifest),
                load_pinned(args.expected, args.expected_sha256),
                args.artifacts_root, args.evidence_root)
        elif args.command == "state":
            result = release_state(load(args.pages), load_pinned(
                args.trusted_state, args.trusted_state_sha256))
        else:
            result = load(ROOT / "project/release-prerequisites.json")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("status") == "BLOCKED" else 0
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error),
                          "public_release_ready": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
