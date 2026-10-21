# AI companion source and distribution

The AI companion is maintained in this repository under [`companion/`](../../companion/README.md). The original monorepo import retained independent package distribution. The Windows delivery now stages that package's canonical Mod and matching Python/SDK runtime with the game; players configure and explicitly start it from the recruited NPC menu. Python remains a child process with file-backed memory. Native ActorControl controls the original recruited NPC; multiplayer retains its own sessions, synchronization and scheduling. Merely loading the Mod does not start model calls.

## Source and license boundaries

The import retains the complete original history of `oncehere/cph-ai-companion` through `1240c94b4a65e7ca5a561ea08d02937b1294eb1d`. The native integration retains `e01386a1eba1752b169aa55d3941abef506b6461` and CPH main `df8fe8ead66bbdfe9efb307ea4367bc121138db1`, including the ImGui dialogue interface. See the fixed [import record](ai-companion-import.json).

`companion/LICENSE`, `NOTICE` and `THIRD_PARTY.md` preserve Apache-2.0 and the original attribution. Game source and assets retain their existing licenses. Historical evidence under `companion/docs/evidence/` and the old repository's Releases describe those exact older artifacts; they are not acceptance of a new combined revision. The old repository, tags and releases are retained, not deleted or rewritten by this migration.

## One protocol source

The authoritative protocol and fixtures are in `companion/src/cph_ai_companion/resources/protocol/`. Python packages include these resources; `tools/actor_control/generate_protocol.py` embeds the same contract and fixtures into `src/actor_control_protocol_generated.h`. The generator supports `--check`, records content digests and does not depend on a changing Git HEAD. The old `data/reference/actor_control/` copies and cross-repository exporter are retired.

From the repository root:

```sh
python3 tools/actor_control/generate_protocol.py
python3 tools/actor_control/generate_protocol.py --check
python3 -m unittest discover -s tools/actor_control -p 'test_*.py'
```

## Independent package validation

Use Python 3.12 and the fixed uv version in `companion/pyproject.toml`:

```sh
cd companion
uv sync --locked --group build
uv run --locked python -m unittest discover -s tests
uv build --python .venv/bin/python --no-build-isolation --out-dir dist
uv run --locked python tools/build_release.py --dist dist --candidate-only
```

Use focused source tests while iterating locally. The root `.github/workflows/project-companion.yml` builds the package and runs the full suite once against the installed wheel outside the source checkout, followed by isolated `init` and offline `doctor` checks. It uploads candidate wheel, sdist, Mod and accompanying materials, and does not publish a Release. Native CI also checks protocol generation; its Linux native selection includes ordinary ActorControl cases. These declarations require an actual workflow run before they count as hosted results.

Native joint validation is a separate test requiring a source-matching native binary and the exact installed wheel:

```sh
CPH_COMPANION_JOINT_DRIVER="$PWD/companion/tools/joint_driver.py" \
CPH_COMPANION_PYTHON=/absolute/path/to/installed-venv/bin/python \
  /absolute/path/to/cata_test-tiles '[.actor_control_joint]' --rng-seed 20261001
```

Run it from the CPH source root with isolated test state. It uses the deterministic fake model and records a native/Python combination, not real-model effectiveness. The standard package/Mod scan and offline doctor never call a model. Keep GUI, user-save, real-model, platform, local and hosted statuses separate.

## Releases and future changes

The build package remains `cph-ai-companion`. `build_release.py` accepts explicit
Windows interpreter, SDK site-packages and game-stage paths to assemble the
built-in Mod and hidden game-owned runtime. Canonical Mod files remain only in
the Python package resources; delivery copies bytes from the built wheel instead
of maintaining another source copy in `data/mods`. Package assembly records
artifact hashes; a supported combination additionally requires evidence
identifying the monorepo revision/tree, installed wheel and native binary.
Rebuilding the same package version does not prove identical bytes. Game release
and actual Windows GUI acceptance remain separate checks.

New changes to the protocol, native adapter and Python client can now be reviewed in one commit. Extract shared native operations only when two actual callers have equivalent semantics and old implementations can be removed. Multiplayer coexistence and player-avatar control remain future scope; this migration does not add either capability.

The protocol 1.2 task candidate adds native persistent work, bounded delayed
planning and a provider-consumption ledger while preserving those source and license
boundaries. See [ActorControl](actor-control.md) for the current task/UI/save
contract and [the accepted design](companion-avatar-design.md) for its broader
intent and verification scope. Historical wheel/native evidence still names
its original protocol; a new package must be checked against the new native
binary and exact schema digest.
