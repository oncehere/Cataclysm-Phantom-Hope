<!-- CPH-DOC: mod-compatibility -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `mod-compatibility`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

> Compatibility scope: this page describes the inherited JSON/EOC path. New
> executable Mod behavior follows the [Lua Platform contract](../data/lua/README.md). A documented legacy operation does not establish a public Lua API.

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
*Contents*

- [Mod Compatibility](#mod-compatibility)
  - [Summary](#summary)
  - [Guide](#guide)
  - [Limitations](#limitations)
  - [Technical Summary](#technical-summary)
    - [Developers](#developers)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Mod Compatibility

## Summary

Mods are capable of dynamically loading directories based on if other mods are loaded in the world.  This will prevent file contents within the mod_interactions folder from being read unless they are part of a folder named after a loaded mod's id.

## Guide

In order to dynamically load mod content, files must be placed within subdirectories named after other mod ids within the mod_interactions folder.

Example:
Mod 1: Mind Over Matter (id:mindovermatter)
Mod 2: Xedra Evolved (id:xedra_evolved)

If Xedra wishes to load a file only when Mind Over Matter is active: mom_compat_data.json, it must be located as such:
Xedra_Evolved/mod_interactions/mindovermatter/mom_compat_data.json

Files located within the mod_interactions folders are always loaded after other mod content for every mod is loaded.

## Limitations

Multi-mod interaction folders are not supported (ie. "mindovermatter/xedra_evolved").

## Technical Summary

When mods are loaded, they are loaded while ignoring every file that is within the "mod_interactions" folder.  After all mods are finished loading then the mod_interaction folder content is loaded is the same order as the initial mods.  Within the mod interaction folders, only folders with names matching loaded mod ids (case sensitive) will be loaded.

### Developers

When a definition from the mod interaction folder is loaded, the src is saved as a combination of the base mod id, a hashtag, and the interaction mod id.  For example a combined id may be "xedra_evolved#mindovermatter".
