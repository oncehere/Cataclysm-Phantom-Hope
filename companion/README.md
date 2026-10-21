# CPH AI Companion

**玩家从这里开始：[Windows 中文快速上手](docs/quickstart.zh-CN.md)** —
在游戏中完成绑定、配置、启动、对话和安全停用，无需 Python 命令。

`cph-ai-companion` supplies the runtime and Lua MOD for CPH's built-in Windows
AI companion. The staged game includes matching Python 3.12 and SDK dependencies;
players do not install Python or run shell commands. It controls one already recruited
NPC through CPH's authenticated actor-control service. The player keeps control
of the avatar. Original project code is Apache-2.0; CPH remains separately
licensed.

The Python project and MOD source are maintained under `companion/` in the
[CPH repository](https://github.com/oncehere/Cataclysm-Phantom-Hope).
The wheel remains an independently testable build input. Windows game delivery
stages its canonical Mod and matching runtime together. The original [independent repository](https://github.com/oncehere/cph-ai-companion)
and its [published 0.1.1 release](https://github.com/oncehere/cph-ai-companion/releases/tag/v0.1.1)
remain historical sources; this migration does not delete that repository or
replace its release assets.

The model proposes bounded plans and persistent tasks at meaningful decision points. Native CPH
executes actions, consumes resources and time, produces receipts, and runs local
NPC behavior between plans. Readable local files hold background and cognition;
human edits and deletions take precedence over automatic updates.

This checkout is a **0.1.2.dev0 local monorepo candidate**, using wire protocol 1.2.
It has not been published. Protocol 1.0/1.1 builds cannot control this candidate;
version and exact digest must match. Recorded verification is described in
[docs/compatibility.md](docs/compatibility.md) and [docs/acceptance.md](docs/acceptance.md).
Imported test results do not certify the changed monorepo candidate.
The published 0.1.1 package and its assets remain unchanged.
Graphical interaction, real-model quality and the user's actual game environment
have separate acceptance entries.

The first gathering action picks up actual ground items; it does not implement
general plant harvesting, logging or mining. Queued attacks use native melee.
Ordinary NPC behavior may use its existing ranged-combat logic between plans.
Only an adapted CPH build exposes this project's control interface. The source requires SDL3 for tiles;
see [installation and source build instructions](docs/install.md).

## Installation and explicit startup

Use a matching Windows game bundle and enable **CPH AI companion** in the world's
Mod list. Open the game's chat menu (default **Shift+C**) and press **Shift+I**
to choose **AI companion**.
Bind a visible recruited companion, choose **Configure AI companion**, then save its endpoint, model, background and
daily duties. Enter the API key in the masked session-only field and explicitly
choose **Start AI companion**. **Stop AI and safely return control** uses the
native safe handoff. The game owns the hidden runtime process and closes its
child job when the game exits.

The key is not written to configuration, saves, command arguments or logs. It is
passed only in the child's environment; enter it again after restarting the game.
Profiles retain the existing schema under `userdir/ai-companion/profiles/`.
Importing the package, scanning the MOD and running offline diagnostics do not
start a model. See [docs/install.md](docs/install.md) for developer packaging and
the historical standalone CLI workflow. Implementation does not itself prove
Windows GUI or provider acceptance; see the dated acceptance record.

The protocol 1.2 task contract supports following, guarding, travel, ground-item
gathering and crafting. Native CPH maintains accepted tasks and their progress
between model replies, while local NPC danger reactions and basic behavior
remain available. The world does not pause for a model response. New requests
append by default; explicitly prioritized work waits for a safe handoff, and
ordinary conversation does not cancel existing work. Beyond basic follow/guard,
autonomous task proposals require configured `duties.allowed_tasks` (empty by default)
and the corresponding item, recipe and distance scope.

The companion menu shows a short status summary. Press **h** for quick start,
or **s / Status and conversation** for system connection/response status, dialogue
and previously observed progress. The summary updates when you return to the menu.
These views do not reveal the real private queue or
hidden motives; unseen work remains unknown. Full state belongs to the optional
debug view. World memories and task progress follow the confirmed game save;
background/personality preferences and provider-spending counters have separate
lifecycles.

Defaults bound a decision to three calls/four local queries, 30 seconds per
request and 90 seconds per episode. The 100-call/100,000-token consumption
budget persists across process restarts and game reloads. Optional
`llm.thinking_mode` (`enabled`/`disabled`) forwards a provider-specific thinking
setting; omission preserves the provider default. See [architecture](docs/architecture.md)
for exact limits, renewal scope and safety of delayed results. These are current
candidate contracts; the [acceptance record](docs/acceptance.md) distinguishes
tested behavior from GUI, real-provider and publication claims.

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

The source archive contains build/test sources and manuals. Historical raw
acceptance attachments remain in the [fixed repository archive](https://github.com/oncehere/Cataclysm-Phantom-Hope/tree/71db54271124f072c330ef3da101c1480ef6aae8/companion/docs/evidence)
and are excluded from new source archives; their historical results do not
validate a rebuilt package.
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

For independent Lua/JSON content and story checks, use the
[isolated scenario workflow](../tools/scenarios/README.md). It prepares fresh
test directories and supports launch/rerun without importing this package or
requesting a model; gameplay outcomes still require observation.

The optional developer tool `python tools/online_acceptance.py` defaults to an
offline check of three synthetic planning cases. Its explicit `--online` mode
uses a dated, persistent call budget and failure stop, with a key inherited from
the environment or entered without echo. It requires separate authorization for
real calls and reads no player saves or profiles. Validating a returned candidate
does not certify native adoption or GUI gameplay; those checks remain separate.

See [architecture](docs/architecture.md) for module and save boundaries and
[THIRD_PARTY.md](THIRD_PARTY.md) for provenance.
