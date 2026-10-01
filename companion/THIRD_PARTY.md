# Dependencies and design references

The independent project's original code is Apache-2.0. CPH is distributed
separately; its source changes and assets retain their existing licenses.

| Source | Fixed version or commit | Use and licensing boundary |
| --- | --- | --- |
| [OpenAI Python](https://github.com/openai/openai-python/releases/tag/v3.22.1) | 3.22.1 | Runtime dependency, Apache-2.0; installed from the hashed dependency lock, not vendored |
| [Hatchling](https://pypi.org/project/hatchling/1.27.0/) | 1.27.0 | Build dependency, MIT; not part of runtime installation |
| [Mindcraft](https://github.com/mindcraft-bots/mindcraft/tree/5f3acc87b479864124173de444f31fa5538f94a6) | 5f3acc87b479864124173de444f31fa5538f94a6 | MIT; design reference for action ownership and local modes; no imported code/assets |
| [Generative Agents](https://github.com/joonspk-research/generative_agents/tree/fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4) | fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4 | Apache-2.0; design reference for typed cognition and retrieval; no imported code/assets |
| [Mantella](https://github.com/art-from-the-machine/Mantella/tree/c0c1ae6db01f3c2a14dbab8ec5c3e6419e4f6bac) | c0c1ae6db01f3c2a14dbab8ec5c3e6419e4f6bac | AGPL-3.0; design reference only; no code, dialogue, character data or assets imported |
| [CPH](https://github.com/oncehere/Cataclysm-Phantom-Hope) | Compatible native revision recorded with acceptance evidence | Separate dependency; native changes retain CPH's CC BY-SA 3.0 and applicable third-party licenses |

`uv.lock` records exact direct and transitive distributions and SHA-256 hashes.
`requirements.lock` exports runtime installation requirements;
`build-requirements.lock` exports build dependencies. Installed dependency
distributions carry their own license files. This project does not redistribute
a Python runtime or a dependency wheelhouse.

References informed independently written implementations. Any future copied
code or bundled asset requires a new attribution and license record before it
is included. The original background template contains no imported character.
