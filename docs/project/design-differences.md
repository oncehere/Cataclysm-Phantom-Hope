# Source ancestry and intentional differences

`project/upstreams.lock.json` records the original B/U source identities.
`project/design-differences.json` separately records intentional project changes.
A source SHA being an ancestor is evidence of integration history, not evidence
that every source behavior remains active.

The initial ledger records the actual commits for inherited-workflow quarantine,
opt-in Linux test identity/data isolation, and two Clang 21 test callback fixes.
Those are already implemented local changes authorized by the execution task.
The ledger does not approve permanent application IDs, new gameplay choices,
translation maintenance policy, or deployment. Tooling/documentation additions
that do not adapt upstream behavior remain visible in ordinary Git history.

For an intentional upstream adaptation, record its upstream SHA, actual project
commit, reason, and decision (`retain`, `pending`, or `restore`). The recorded
commits must be ancestors of the pinned project/upstream heads. Do not replace
source SHAs with adaptation commit SHAs or reset the upstream baseline after a
revert.

For an upstream merge rollback, first use a separately reviewed normal revert
commit; retain both upstream parents in history. Record `kind: revert` and the
revert's project SHA. The current local sync tool blocks every explicit revert
and every pending/restoration decision. It also detects unrecorded default
`git revert` messages on project first-parent history. A retry of the same
upstream therefore cannot silently report restored behavior. A deliberate
restore requires a new reviewed change and a corresponding ledger/policy update;
there is no automatic revert-of-revert or conflict-resolution command.

This tripwire does not identify arbitrary hand-written semantic reversals or
prove a ledger complete. Custom reversals must be recorded explicitly. Merge
success alone never authorizes acceptance: known design constraints and actual
regression checks remain necessary. No new design choice is made by the tool.

Protected ledger/policy changes require their own explicit review. A candidate
cannot edit the ledger to approve itself. Remote enforcement of that boundary
is still E4 work, not a property established by this local JSON file.
