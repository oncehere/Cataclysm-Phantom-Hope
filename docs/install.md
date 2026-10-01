# Install, configure and safely stop

The experimental prerelease targets Linux x86_64 with Python 3.12. An ordinary
CPH build without ActorControl cannot provide the required service. The release
contains the Python program and MOD, not an adapted CPH binary.

## Obtain and build the adapted CPH source

Use [oncehere/Cataclysm-Phantom-Hope](https://github.com/oncehere/Cataclysm-Phantom-Hope)
and its `codex/actor-control-20260930` branch. Check out the exact commit in the
downloaded release's `compatibility.json`; the moving branch alone is not a
compatibility guarantee. Run these commands from that release directory:

```sh
CPH_NATIVE_COMMIT="$(python3.12 -c 'import json; print(json.load(open("compatibility.json"))["validated_combinations"][0]["native_commit"])')"
git clone --branch codex/actor-control-20260930 \
  https://github.com/oncehere/Cataclysm-Phantom-Hope.git cph-source
git -C cph-source checkout --detach "$CPH_NATIVE_COMMIT"
git -C cph-source rev-parse HEAD
```

The native candidate is
[`a04e657dc009cc5dceacec20eb1acdc23068f248`](https://github.com/oncehere/Cataclysm-Phantom-Hope/commit/a04e657dc009cc5dceacec20eb1acdc23068f248).
Use the manifest's tested combination when choosing the package to install.
The adapted changes are available for review in
[CPH draft PR #25](https://github.com/oncehere/Cataclysm-Phantom-Hope/pull/25).
They have not been merged into ordinary CPH `main` or deployed to the user's
installed game by this package.

Install a C++17 compiler, CMake, Ninja and the native dependencies described in
CPH's [CMake build guide](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/a04e657dc009cc5dceacec20eb1acdc23068f248/doc/c++/COMPILING-CMAKE.md).
Tiles require SDL3. The repository's
[flake.nix](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/a04e657dc009cc5dceacec20eb1acdc23068f248/flake.nix)
also declares its development dependencies. The Linux candidate was tested with
**Clang 21.1.8**. Select that C++ compiler explicitly in the following
configuration; sound, translations and backtraces are disabled
in this particular tested build:

```sh
cmake -S cph-source -B cph-build -G Ninja \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_BUILD_TYPE=Release '-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG' \
  -DCATA_ENABLE_LUA_PLATFORM=ON -DTILES=ON -DCURSES=OFF -DHEADLESS=OFF \
  -DSOUND=OFF -DLOCALIZE=OFF -DBACKTRACE=OFF -DLIBBACKTRACE=OFF \
  -DBUILD_TESTING=ON
cmake --build cph-build --target cataclysm-tiles --parallel 2
```

Keep the build outside the source tree. Run it with explicit absolute source
and user directories, using that same user directory when installing the MOD:

```sh
/absolute/cph-build/src/cataclysm-tiles \
  --basepath /absolute/cph-source/ --datadir /absolute/cph-source/data/ \
  --userdir /absolute/game-userdir/
```

This source-build path does not replace the system's installed CPH. Build
success and the automated native integration scenario do not establish a GUI
session or the user's real saves; those remain separate acceptance entries.

## Install the final artifacts

Create an isolated environment outside the source checkout. From the downloaded
release directory, install exact hashed dependencies, then the project wheel:

```sh
python3.12 -m venv /absolute/companion-venv
/absolute/companion-venv/bin/python -m pip install --require-hashes -r requirements.lock
/absolute/companion-venv/bin/python -m pip install --no-deps cph_ai_companion-0.1.1-py3-none-any.whl
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
invalidates dependent summaries and managed history. Invalid partial JSON causes
the running program to close its provider and connection and exit; it is not
silently replaced. Correct the file and explicitly run the program again.
Changes to the endpoint, paths or memory-continuity policy require a restart;
personality permissions, limits and debug settings can update while running.

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

For an upgrade from `0.1.0` to `0.1.1`, install the new wheel in a separate
environment. The installer protects existing MOD files, so a changed version
cannot overwrite the old MOD. Use the old program's `stop` and `remove-mod`
commands above and wait for successful safe removal. With the new program,
run `init --install-mod` using a new, empty bootstrap profile directory solely
to install the MOD. Keep your original character profile, background and memory
files, then bind its original profile ID in game and run the new program with
that original profile. `init` cannot overwrite an existing profile. If native
dependency release is incomplete, preserve the installation until CPH reports
safe removal.

After an interrupted game save, retain the native operation journal and all
game files. A local memory checkpoint marked `prepared` does not confirm a
successful game save, and deleting memory is not a way to retry physical work.
Use the recovery status reported by the adapted CPH build; uncertain operations
must pause instead of automatically replaying. Focused native fault scenarios
passed for the operation journal, beforeimages, native writers and gameplay
snapshot boundaries. A complete physical crash campaign and graphical save/load
journeys remain `NOT_RUN`; see [the acceptance record](acceptance.md).
