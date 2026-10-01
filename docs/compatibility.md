# Compatibility record

The first candidate is package `0.1.0`, Python `>=3.12,<3.13`, Linux x86_64,
OpenAI SDK `3.22.1`, wire protocol `1.0`, and schema version `1` for profile,
memory, checkpoint and native extension state.

`compatibility.json` is the machine-readable release record. Its
`validated_combinations` list contains only package/native combinations backed
by joint acceptance evidence. A candidate based on an adapted tree is recorded
separately under `candidate`; base HEAD alone is not a validated native revision.
No validated combination is claimed until that evidence is recorded.

Handshake checks protocol version and exact protocol digest. CPH consumes a fixed
snapshot exported from this project's resources. A matching version string is
insufficient when the digest differs. Future native changes need joint tests
before addition to the validated list.

The Python platform tag describes packaging, not tested operating-system support.
Windows, macOS, Android, real-provider quality and remote CI remain unclaimed
unless separately recorded. Import/diagnostic success does not establish game
action, save recovery or removal acceptance.
