# CPH AI Companion

`cph-ai-companion` is an explicitly started Python 3.12 program and a Lua MOD
for an adapted Cataclysm: Phantom Hope build. It controls one already recruited
NPC through CPH's authenticated actor-control service. The player keeps control
of the avatar. Original project code is Apache-2.0; CPH remains separately
licensed and distributed.

The Python project and MOD source are maintained under `companion/` in the
[CPH repository](https://github.com/oncehere/Cataclysm-Phantom-Hope).
The package and game keep separate builds, releases, installation and control
lifecycles. The original [independent repository](https://github.com/oncehere/cph-ai-companion)
and its [published 0.1.1 release](https://github.com/oncehere/cph-ai-companion/releases/tag/v0.1.1)
remain historical sources; this migration does not delete that repository or
replace its release assets.

The model proposes bounded plans at meaningful decision points. Native CPH
executes actions, consumes resources and time, produces receipts, and runs local
NPC behavior between plans. Readable local files hold background and cognition;
human edits and deletions take precedence over automatic updates.

This checkout is a **0.1.2.dev0 local monorepo candidate**, using wire protocol 1.1.
It has not been published. Protocol 1.0 builds cannot control this candidate;
version and exact digest must match. Recorded verification is described in
[docs/compatibility.md](docs/compatibility.md) and [docs/acceptance.md](docs/acceptance.md).
Imported test results do not certify the changed monorepo candidate.
The published 0.1.1 package and its assets remain unchanged.
Graphical interaction, real-model quality and the user's actual game environment
have separate acceptance entries.

The first gathering action picks up actual ground items; it does not implement
general plant harvesting, logging or mining. Queued attacks use native melee.
Ordinary NPC behavior may use its existing ranged-combat logic between plans.
Only an adapted CPH build exposes this project's control interface; this release
does not bundle that game binary. The adapted source requires SDL3 for tiles;
see [installation and source build instructions](docs/install.md).

## Installation and explicit startup

Use Linux x86_64 and Python 3.12 with the CPH revision named in the compatibility
record. Install final wheel dependencies from the hashed runtime lock inside an
isolated environment. Follow [docs/install.md](docs/install.md) for exact steps,
MOD installation, session selection, safe stop and removal.

```sh
cph-ai-companion init --profile /absolute/profile --actor-id 7
cph-ai-companion doctor --offline --profile /absolute/profile
cph-ai-companion list-sessions
cph-ai-companion run --profile /absolute/profile --session SESSION_ID
cph-ai-companion stop --session SESSION_ID
```

Edit `config.json` and the configured background file before starting. Specify
an OpenAI-compatible endpoint and model; provide the API key through the named
environment variable. Importing the package, scanning the MOD and running
offline diagnostics do not start a model or call a provider.

## Development and artifacts

Use uv 0.12.17 and Python 3.12. Run package commands from `companion/` in the
selected CPH source checkout:

```sh
cd companion
uv sync --locked --group build
uv run --locked python -m unittest discover -s tests
uv build --python .venv/bin/python --no-build-isolation --out-dir dist
uv run --locked python tools/build_release.py --dist dist --candidate-only
```

The final command extracts MOD resources from the built wheel and emits the MOD
ZIP, compatibility manifest, dependency locks and checksums. It rejects missing
resources. Default assembly and `--candidate-only` emit an unvalidated candidate
with empty `validated_combinations` and `NOT_RUN` acceptance entries; they do not
read old PASS results from `docs/compatibility.json`.
No command in this workflow creates a remote repository or publishes a release.

After separately testing the exact wheel/native pair, explicitly supply its
evidence file with `--compatibility /absolute/tested-compatibility.json` instead.
Every validated combination in that file must name this built wheel's SHA-256;
missing or different wheel identities are rejected before assembly. A file with
no validated combinations produces an unvalidated candidate. Matching evidence
is preserved without claiming that assembly performed those tests.

The protocol and shared fixtures in `src/cph_ai_companion/resources/protocol/`
are the single authority for both Python and native code. From `companion/`,
check the native generated header with
`python3 ../tools/actor_control/generate_protocol.py --check`.
The former cross-repository `export_cph_protocol.py` step is retired.
Package CI runs from the CPH repository's root `.github/workflows/`; the Python
sdist and wheel remain self-contained package artifacts.

See [architecture](docs/architecture.md) for module and save boundaries and
[THIRD_PARTY.md](THIRD_PARTY.md) for provenance.
