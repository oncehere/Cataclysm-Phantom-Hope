#!/usr/bin/env bash
# Read-only upstream audit: clones into a disposable directory; no API key used.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SHA=a28493ba832ffc5506d4e45f4ddfdc5623931aa9
AUDIT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/po-maintain-lokit.XXXXXXXX")"
trap 'chmod -R u+w -- "$AUDIT_DIR"; rm -rf -- "$AUDIT_DIR"' EXIT
command -v go >/dev/null || { echo 'BLOCKED: Go >= 1.23.6 required (e.g. nix shell nixpkgs#go).' >&2; exit 2; }
git clone -q https://github.com/minios-linux/lokit.git "$AUDIT_DIR/lokit"
git -C "$AUDIT_DIR/lokit" checkout -q --detach "$SHA"
test "$(git -C "$AUDIT_DIR/lokit" rev-parse HEAD)" = "$SHA"
cp "$ROOT/scripts/audit/lokit_probe_test.go" "$AUDIT_DIR/lokit/translate/po_maintain_audit_test.go"
export PO_MAINTAIN_AUDIT_FIXTURE="$ROOT/tests/fixtures/compatibility.json"
# Caches and downloaded build dependencies remain temporary, outside the repo.
export CGO_ENABLED=0
export GOCACHE="$AUDIT_DIR/go-cache" GOMODCACHE="$AUDIT_DIR/go-mod"
cd "$AUDIT_DIR/lokit"
printf 'Pinned lokit: %s\n' "$SHA"
go version
go test ./translate -run '^TestAudit' -count=1 -v
