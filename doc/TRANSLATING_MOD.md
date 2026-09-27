<!-- CPH-DOC: mod-localization -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `mod-localization`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# Translating a mod for CPH / 翻译 CPH Mod

This page describes a mod author's editable PO and compiled MO files. It is distinct from CPH's temporary core MO bootstrap. Read [translation inputs](../docs/project/translation-inputs.md), [translation credits](../TRANSLATION_CREDITS.md), and the actual loader in `src/translation_manager_impl.cpp` before claiming runtime support for a particular package.

## Sources and attribution

For a JSON mod, keep its source JSON, license, authors and `modinfo.json` together; a Lua Platform mod instead has `mod.lua`/`main.lua` and its own extraction needs. Preserve translator comments and credits in PO headers. Translation markup, `%` placeholders, contexts and plural entries must agree with the source; [translator notes](../lang/notes/README_all_translators.md) give format examples. A translation platform can be used by a mod author, but this repository does not name or operate an official CPH Transifex project.

## Generate, edit and compile

`lang/extract_json_strings.py` accepts one or more `-i/--include_dir` paths and a required existing `-r/--reference` POT path. The old example's `-o` option is invalid. Use an isolated copy of the mod and a valid POT reference, then inspect extracted strings before merging them into a PO catalog. The script needs Python dependencies including `polib`; `lang/update_pot.sh` shows the repository's own extraction sequence. Do not run a sample command against a real mod until its paths and dependencies are verified.

For an existing reviewed PO catalog, GNU gettext can validate and compile it into an isolated package path:

```sh
msgfmt -c --statistics -o /dev/null mods/demo/lang/po/ru.po
mkdir -p mods/demo/lang/mo/ru/LC_MESSAGES
msgfmt -o mods/demo/lang/mo/ru/LC_MESSAGES/demo.mo mods/demo/lang/po/ru.po
```

Replace `mods/demo` and `ru` with the actual mod path and locale. The loader scans user mod roots for `LC_MESSAGES/*.mo`; `demo.mo` must be packaged under the actual mod root and locale. The core `cataclysm-dda.mo` domain is inherited and should not be renamed as part of a prose cleanup. PO/POT files remain editable authoring sources even if a binary package contains only MO output.

## Verify in game

Load the mod in an isolated CPH test world, select the target language, inspect representative singular/plural and context-sensitive strings, and check logs for missing catalogs. Record the exact CPH commit, mod revision and command/result. A successful `msgfmt` run verifies catalog syntax, not extraction or gameplay. For a bundled mod, also follow `data/mods/AGENTS.md` and run the affected JSON/mod checks. Keep third-party translations and credits intact.
