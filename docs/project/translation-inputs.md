# Translation inputs and maintained Chinese catalog

## Maintained Simplified Chinese

`lang/cph/zh_CN.po` contains 117,313 messages: the complete 117,224-message catalog
extracted from CPH `a43a8f2f270994dad716ab067c48aad7c2eeaee3`, plus 89 multiplayer
entries reviewed for the 2026-10-01 update. The original catalog remains an exact
byte prefix, including all 251 previously
maintained world-generation translations unchanged. Exact reuse follows
protected project edits, CDDA, CCB, then existing translations; reviewed model
proposals fill the remaining gaps. Coverage refers to that extracted template,
not every dynamically constructed string or a full linguistic review.

The multiplayer additions reuse 51 exact upstream translations, correct 17
upstream translations, and supply 21 new translations, including six co-op tips,
the copy-address binding, and activity text. Their pinned source, per-entry keys
and attribution are retained in the import record. These additions cover the
changed native and peripheral data strings; they do not establish full game UI
or language acceptance.

[The import record](../../lang/cph/zh_CN.sources.json) pins the template, original
PO, upstream commits and artifacts, and the separate maintenance project's
immutable Git commit. That commit retains per-entry sources, protected baselines,
original PO files, licenses, and review evidence. Translator headers are also
preserved in the shipped PO; see [translation credits](../../TRANSLATION_CREDITS.md).
The translations retain the game's CC BY-SA 3.0 license, independently of the
maintenance tool's MIT license.

The existing Make, shell, and CMake targets compile this source to
`lang/mo/cph/zh_CN/LC_MESSAGES/cataclysm-dda.mo`. Runtime lookup uses user Mod
catalogs first, then the CPH maintained directory, then the remaining core
catalogs. A missing maintained entry falls back to the locked base catalog;
the original base MO files stay byte-identical to `project/assets.lock.json`.
Other languages continue using their existing catalogs.

```sh
make -C lang LANGUAGES=zh_CN
# Alternative entry point used by existing workflows:
bash lang/compile_mo.sh zh_CN
```

Contributors can edit this PO directly in a normal PR. Before the next upstream
import, maintainers copy the current game PO into the maintenance project's
catalog while retaining its corresponding state and snapshots, so intervening
PO-only edits are detected and protected. Review the new candidate, retain the
updated PO/state together in that maintenance branch, and copy the accepted PO
back here with its attribution and an updated import record. Do not regenerate
from an old maintenance PO and overwrite newer game edits. This workflow needs
no model service for ordinary checks, merging, or compilation.

## Locked base catalogs

This is the locked E1 input and its 2026-09-26 validation record. The compiled
MO set remains the fallback and other-language resource source, not evidence of
maintained PO coverage for those languages or a four-platform release input.
Local `inputs/` lives outside the source
repository; see [workspace-layout.md](workspace-layout.md).

E1 temporarily uses the **actual compiled MO resources** from the CCB release
`2026-09-23-0407`. Both the release's `target_commitish` and its tag resolve to
the locked baseline `bcb85682f3d28ab0f0123b05e45651bb9888b61b`. This is not a
maintainable PO source pipeline for those base resources. The maintained Chinese
source described above is built separately; no empty replacement catalogs are
generated and the locked base files are not rewritten.

## Input and attribution

`project/assets.lock.json` pins the public release asset ID `582281303`, URL,
223,961,956-byte archive, SHA256, and each selected output's size and SHA256.
The archive SHA256 is
`60f1fbf1b47fd330ca9b999b83319749dae5f8fee7d4aaf784b515a2e2b4af1a`.
The public GitHub release/asset metadata was verified on 2026-09-26. The
checksum pins these bytes; it does not establish independent provenance of
the upstream translation source, which is not included in this asset.

The 73 selected files consist of 49 MO catalogs, the four packaged root
`LICENSE*.txt` notices, and 20 `data/credits/*.credits` attribution files.
The inherited `LICENSE.txt` identifies the game's CC BY-SA 3.0 license and
includes separate third-party notices. The tool preserves every selected
notice and credit byte-for-byte. No upstream binary, script, font, test MO,
or other game data is extracted or executed. This resource lock covers this
translation bootstrap, not all of the game's assets or dependencies.

The gettext domain remains `cataclysm-dda`, matching `lang/compile_mo.sh` and
`PATH_INFO::lang_file()` at U. Application identity isolation is a separate
change; renaming this domain would invalidate the inherited catalogs.

## Reproduction

From a registered worktree in the current local workspace, derive its workspace
root and choose a new resource directory outside the source tree. In an
independent clone or CI job, set an explicit output root instead:

```sh
CPH_WORKSPACE="$(dirname "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")"
TRANSLATION_OUTPUT="$CPH_WORKSPACE/inputs/translations-$(date -u +%Y%m%dT%H%M%SZ)-$$"
test ! -e "$TRANSLATION_OUTPUT" || exit 1
env -u TX_TOKEN -u GH_TOKEN -u GITHUB_TOKEN \
  python3 tools/project/bootstrap_translations.py --output "$TRANSLATION_OUTPUT"
python3 tools/project/bootstrap_translations.py --check --output "$TRANSLATION_OUTPUT"
python3 -m unittest discover -s tests/project -p 'test_bootstrap_translations.py' -v
```

The first command downloads the public asset directly into a new temporary
directory, verifies it, selects the locked resources, parses all MO files, and
checks the real Simplified Chinese lookup `Settings` → `设置`. It does not use
Transifex credentials, prior Actions artifacts, an existing resource cache,
or a project's remote target. `--archive PATH` optionally reuses a raw archive
but still verifies the whole locked size/SHA256 before parsing. `--check` is
read-only and performs no download. JSON results go to stdout; failures go to
stderr with exit 1, and argument errors exit 2.

The output directory must not exist. Successful extraction writes only the
locked resources, and failures leave no resource directory. Existing output
requires `--check` or a fresh path, so user files are never silently replaced.
For the local U build, copy the verified `lang/mo/<locale>` directories into
the isolated checkout's `lang/mo`, leaving its tracked `.gitignore` intact;
these are generated build inputs, not source or a public release. Do not copy
over an existing installation, configuration, save, or translation directory.

## Safety and actual coverage

Extraction verifies archive bytes first, validates all archive member paths,
rejects duplicate names, and enforces member-count, per-file and total
decompression limits. It never uses `extractall`, carries executable modes,
or follows archive links. The upstream archive has one unrelated documentation
symlink; its exact path and target are recorded as an inert exclusion in the
lock. Any other link, device, FIFO, sparse file, or selected link fails.
An existing output check rejects symlinks, unlisted files, missing inputs,
changed hashes, malformed catalogs, missing required locales, or a failed
Chinese lookup.

All 49 actual catalogs are retained. Thirteen supplied upstream catalogs
contain only headers: `ace`, `be@tarask`, `be_BY`, `ca`, `en@pirate`, `en_NG`,
`es`, `et`, `fi`, `he`, `hi`, `ru_RU`, and `th_TH`. They report zero entries and
are **not evidence of language coverage**. `zh_CN` and `ru` are required and
must contain nonempty entries. Reported entry counts exclude catalog headers,
count plural variants individually, and do not imply a percentage of current
source strings or linguistic correctness.

The resource probe proves real GNU gettext parsing and the named lookup. Game
loading, platform execution, and four-platform release acceptance require
their own actual build/test evidence. The unit suite uses explicit small
archive/parser fixtures to test policy failures; those fixtures are never
used as game or platform acceptance evidence.

## 冷启动与维护要求

初始化不能依赖本仓库既有成功 artifact。输入须有可核验来源、对象、摘要、许可和署名；优先维护 PO，只取得 MO 时如实报告编译资源及其维护缺口，不以空翻译、禁用中文或丢弃素材证明成功。缺少输入只阻塞依赖它的检查/发布及相应必需门槛，不阻塞无关工具开发；fixture 必须标明测试用途。

历史来源（本次未重新在线核验）：[锁定 CCB 翻译 workflow](https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/blob/bcb85682f3d28ab0f0123b05e45651bb9888b61b/.github/workflows/build-translations.yml)。

## 验收场景

以下为保留的规范性场景；是否已通过须查实际证据，不由本表或模型测试推断。

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T20 | 无 TX_TOKEN、无历史 artifacts、无缓存 | 已声明输入可取得并校验；否则失败，不伪造翻译。 |
