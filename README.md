# CPH AI Companion

`cph-ai-companion` is an explicitly started Python 3.12 program and a Lua MOD
for an adapted Cataclysm: Phantom Hope build. It controls one already recruited
NPC through CPH's authenticated actor-control service. The player keeps control
of the avatar. Original project code is Apache-2.0; CPH remains separately
licensed and distributed.

The model proposes bounded plans at meaningful decision points. Native CPH
executes actions, consumes resources and time, produces receipts, and runs local
NPC behavior between plans. Readable local files hold background and cognition;
human edits and deletions take precedence over automatic updates.

This checkout is a **0.1.1 experimental prerelease candidate**. Compatibility and actual
acceptance are recorded in [docs/compatibility.md](docs/compatibility.md) and
[docs/acceptance.md](docs/acceptance.md). The tested integration uses a real
native NPC and installed Python package with a synthetic local model endpoint.
Graphical interaction, real-model quality and the user's actual game environment
have separate, unrun acceptance entries.

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

Use uv 0.12.17 and Python 3.12:

```sh
uv sync --locked --group build
uv run --locked python -m unittest discover -s tests
uv build --python .venv/bin/python --no-build-isolation --out-dir dist
uv run --locked python tools/build_release.py --dist dist
```

The final command extracts MOD resources from the built wheel and emits the MOD
ZIP, compatibility manifest, dependency locks and checksums. It rejects missing
resources and leaves validation claims at their recorded evidence level.
No command in this workflow creates a remote repository or publishes a release.

See [architecture](docs/architecture.md) for module and save boundaries and
[THIRD_PARTY.md](THIRD_PARTY.md) for provenance.
