# Dependencies and design references

The original project's Python, Lua, protocol, tests and documentation retain
Apache-2.0 under CPH's `companion/` subtree. The Python package and MOD are
distributed separately from the game; native CPH source and assets retain their
existing licenses. The migration preserves the independent source history and
does not relicense either project.

Current source development belongs to the
[CPH repository](https://github.com/oncehere/Cataclysm-Phantom-Hope).
The [original repository](https://github.com/oncehere/cph-ai-companion) and its
[0.1.1 release](https://github.com/oncehere/cph-ai-companion/releases/tag/v0.1.1)
remain available as historical provenance; this source migration does not delete
them or replace published assets.

| Source | Fixed version or commit | Use and licensing boundary |
| --- | --- | --- |
| [OpenAI Python](https://github.com/openai/openai-python/releases/tag/v3.22.1) | 3.22.1 | Runtime dependency, Apache-2.0; installed from the hashed dependency lock, not vendored |
| [Hatchling](https://pypi.org/project/hatchling/1.27.0/) | 1.27.0 | Build dependency, MIT; not part of runtime installation |
| [Mindcraft](https://github.com/mindcraft-bots/mindcraft/tree/5f3acc87b479864124173de444f31fa5538f94a6) | 5f3acc87b479864124173de444f31fa5538f94a6 | MIT; design reference for action ownership and local modes; no imported code/assets |
| [Generative Agents](https://github.com/joonspk-research/generative_agents/tree/fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4) | fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4 | Apache-2.0; design reference for typed cognition and retrieval; no imported code/assets |
| [Mantella](https://github.com/art-from-the-machine/Mantella/tree/c0c1ae6db01f3c2a14dbab8ec5c3e6419e4f6bac) | c0c1ae6db01f3c2a14dbab8ec5c3e6419e4f6bac | AGPL-3.0; design reference only; no code, dialogue, character data or assets imported |
| [CPH](https://github.com/oncehere/Cataclysm-Phantom-Hope) | Compatible native revision recorded with acceptance evidence | Same source repository, separately built and distributed game; native changes retain CPH's CC BY-SA 3.0 and applicable third-party licenses |

`uv.lock` records exact direct and transitive distributions and SHA-256 hashes.
`requirements.lock` exports runtime installation requirements;
`build-requirements.lock` exports build dependencies. Installed dependency
distributions carry their own license files. This project does not redistribute
a Python runtime or a dependency wheelhouse.

References informed independently written implementations. Any future copied
code or bundled asset requires a new attribution and license record before it
is included. The original background template contains no imported character.
