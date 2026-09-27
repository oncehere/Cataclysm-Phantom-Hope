# Locked initial history

This page records the initial B/U history and the local source remotes. Its
original no-target conclusion has been superseded: the explicitly authorized
`oncehere/Cataclysm-Phantom-Hope` native CDDA fork and retained-history upload
are documented in [fork-deployment.md](fork-deployment.md). Current remote
checks and outstanding gates are dated in [status.md](status.md).

The primary specification is [execution-spec.md](execution-spec.md).

- CDDA source: `CleverRaven/Cataclysm-DDA`
- CDDA base B: `221c786e7d61b3c9254f7cb1625bc69494b8181c`
- B tree: `c7ad91e89ca75043106a74eb9c893130f378bd16`
- CCB source: `CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb`, `refs/heads/master`
- CCB baseline U: `bcb85682f3d28ab0f0123b05e45651bb9888b61b`
- U tree: `204b14a135ae307ad2180a348a6d6553374a07af`

The isolated branch `codex/e0-e1-bootstrap` was created at B, advanced to U
with an expected-old-value ref update, and checked out before any local changes.
`git merge-base --is-ancestor B U` returned 0. The initial clean HEAD/tree were
exactly U/the U tree above. No upstream commit was rewritten or squashed.
`refs/cph/cdda-base` and `refs/cph/ccb-baseline` retain local checkpoints.

`ccb` and `upstream` use the fixed public GitHub URLs and have disabled push URLs.
`source-cache` records the existing local object source and also has push disabled.
It is not an authorized CPH remote and is not independent upstream provenance.
The clone uses independent object files, not hardlinks or alternates. It has
non-shallow commit history but may need missing promisor blobs fetched locally.

At the initial local-history checkpoint no target OWNER/REPO was configured.
The target was later authorized and created as a real CDDA fork; `origin` now
points to it with push URL `DISABLED`, while actual authorized uploads used an
explicit URL and fixed ref. The initial absence of a fork is historical, not
a current blocker. The existing upstream refs remain preserved; the dated main
protection rule and per-PR acceptance results are in [status.md](status.md).

CCB master is followed through history-preserving integration; CDDA changes are
selected individually. Active adaptations and reverts must be recorded separately
from ancestry. Retrying the same already-merged ancestor does not undo a revert.
