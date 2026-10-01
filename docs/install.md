# Install, configure and safely stop

The first candidate targets Linux x86_64 with Python 3.12. Obtain the exact
adapted CPH build listed with acceptance evidence in the compatibility manifest.
An ordinary CPH build without ActorControl cannot provide the required service.

## Install the final artifacts

Create an isolated environment outside the source checkout. From the downloaded
release directory, install exact hashed dependencies, then the project wheel:

```sh
python3.12 -m venv /absolute/companion-venv
/absolute/companion-venv/bin/python -m pip install --require-hashes -r requirements.lock
/absolute/companion-venv/bin/python -m pip install --no-deps cph_ai_companion-0.1.0-py3-none-any.whl
```

Verify the published checksums before installation. `requirements.lock` is the
runtime export of `uv.lock`; build dependencies have a separate lock. Resources
are loaded through Python package resources and work from any current directory.
Python and third-party dependencies are not bundled with this project.

## Profile, MOD and connection

```sh
cph-ai-companion init --profile /absolute/profile --actor-id 7 \
  --install-mod --game-userdir /absolute/game-userdir
cph-ai-companion doctor --offline --profile /absolute/profile
```

Use the actual game's user directory, including any `--userdir` override. The
installer writes only its MOD in user `mods/`, records owned files and rejects
unowned destinations or modified content. Ownership metadata is JSON inside
`.cph-ai-companion-install-manifest`; its filename has no `.json` suffix, so CPH
does not scan it as gameplay data. Choose the MOD when creating/loading
the intended world. Bind the already recruited NPC by stable actor identity.

Open that recruited NPC's normal chat menu, select **AI companion control**,
and bind the profile ID from `config.json`. The menu also provides chat, status,
pause/cancel and safe stop. Binding another NPC after a character's death does
not replace that profile's existing entity. The optional `actor_id` in the
profile must match the bound NPC; leave it null if selecting the entity in game.

Edit `config.json`: set `llm.base_url`, `llm.model` and `llm.api_key_env`. Keep the
credential in that environment variable. Modify the background, personality
permissions and memory continuity settings directly in their local files.
Offline doctor reports unconfigured endpoint/credential separately; it performs
no model call, socket connection, save repair or automatic takeover.

```sh
cph-ai-companion list-sessions
cph-ai-companion run --profile /absolute/profile --session SESSION_ID
```

Select the explicit instance ID printed by discovery. The runtime requires the
descriptor version/digest to match the package and uses the descriptor's actual
game directories. By default `$XDG_RUNTIME_DIR/cph-ai-companion/` holds private
descriptors; a private user cache runtime directory is the fallback. The model
credential does not belong in those descriptors.

## File editing, saves and removal

Edit record JSON files under the configured memory directory to correct
cognition. To delete a record, remove its current record body. The next refresh
invalidates dependent summaries and managed history. Invalid partial JSON pauses
memory processing until the edit is valid; it is not silently replaced.

Unexpected connection loss permits already accepted valid work to continue.
To deliberately hand control back, use:

```sh
cph-ai-companion stop --session SESSION_ID
cph-ai-companion remove-mod --session SESSION_ID --game-userdir /absolute/game-userdir
```

Wait for native safe-detach confirmation when an activity cannot immediately
stop. Removal requires CPH to confirm released world/MOD dependencies and removes
only manifest-owned unchanged files. Profiles, memories and saves remain. Python
package uninstallation alone does not detach an in-game actor. Downgrading to an
unpatched CPH version is not covered by the safe-removal guarantee.

Supported same-schema upgrades preserve manual edits and checkpoints. Back up
the profile and use an explicitly validated native/package pair. Unsupported
future schema versions fail closed without rewriting their files.

After an interrupted game save, retain the native operation journal and all
game files. A local memory checkpoint marked `prepared` does not confirm a
successful game save, and deleting memory is not a way to retry physical work.
Use the recovery status reported by the adapted CPH build; uncertain operations
must pause instead of automatically replaying. Multi-file crash recovery for
the release candidate is still `NOT_RUN` pending its native acceptance evidence.
