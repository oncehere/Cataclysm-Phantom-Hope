# Translation credits / 翻译署名

CPH retains the translation history, licenses and translator attribution inherited through CDDA and CCB. CPH maintains its Chinese PO locally; the historical CCB provenance below does not imply that CPH operates a separate Transifex project.

## Maintained Chinese catalog / 本地维护的中文目录

`lang/cph/zh_CN.po` combines exact CDDA/CCB translation reuse, protected CPH edits,
and reviewed model proposals. The two upstream PO headers, including their
translator lists and original Last-Translator fields, are retained as comments
in this catalog. The existing Chinese in-game credits are preserved.

[The fixed maintenance snapshot](https://github.com/oncehere/Cataclysm-Phantom-Hope/tree/e1eb7141e200c2cb9369e51ad1cf5d7ce7b4b46a/cph-translation)
contains the original input PO files, licenses and credits, per-entry provenance,
protected baselines, and review records. [The import record](lang/cph/zh_CN.sources.json)
identifies exact upstream commits, artifacts and hashes. These translations are
distributed under CC BY-SA 3.0 and applicable inherited notices; the separate
maintenance tool's MIT license does not relicense game text or translations.

中文目录保留 CDDA、CCB 原始 PO 的译者名单和 CPH 人工修订。完整来源、保护基线、
补译及修正记录固定在上述提交中；工具本身的 MIT 许可不改变译文的 CC BY-SA 3.0
许可。玩家可以直接修改 PO 提交 PR，无须自行编辑工具状态文件。

## Historical bootstrap / 历史冷启动输入

CPH 于 2026-09-26 核验的冷启动基线使用来自 CCB 发布 `2026-09-23-0407` 的**真实编译 MO 资源**，来源、字节校验和所保留的许可/署名文件见 [translation-inputs.md](docs/project/translation-inputs.md)。这些 MO 是临时构建输入，不是可维护的 PO 源码，也不证明当下所有字符串的翻译覆盖率。既有 `.po` 文件中的 `# Translators:`、`Last-Translator` 等署名应保留；修复翻译流程不得删改原作者归属。

The CPH bootstrap verified on 2026-09-26 used real compiled MO resources from CCB release `2026-09-23-0407`. Their pinned source, checksums and retained license/credit files are documented in [translation-inputs.md](docs/project/translation-inputs.md). This is temporary build input, not a maintainable PO source pipeline or a coverage claim. Preserve translator headers and credits in inherited PO files.

## Inherited source record / 继承的来源记录

The inherited CCB note recorded these exact historical Transifex identifiers and date:

- Upstream CDDA translation project: `cataclysm-dda-translators/cataclysm-dda`.
- CCB-owned translation project: `Cataclysm-Cleanwater-Bomb/cataclysm-cleanwater-bomb`.
- Recorded translation download date: `2026-06-26`.

Those are **CCB historical provenance**, not CPH account or workflow instructions. The original `.po` headers carry translator names, and the inherited note identified the translation redistribution as CC BY-SA 3.0. Check current `.tx/config` and authoritative project decisions before making a new contribution route; never publish a Transifex token.

The game inherits CC BY-SA 3.0 and applicable third-party notices. Preserve each source asset's actual license and attribution. License text: <https://creativecommons.org/licenses/by-sa/3.0/>.
