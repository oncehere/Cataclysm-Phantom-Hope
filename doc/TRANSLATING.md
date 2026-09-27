<!-- CPH-DOC: translation-guide -->
> **CPH repository documentation / 本仓维护。** Stable document ID: `translation-guide`.
> This page is maintained with the CPH source. The inherited
> [CCB migration record](migration/history-assessment.md) is historical.
> [Documentation index / 文档导航](../docs/README.md).

# Translating CPH / 翻译 CPH

CPH inherits CDDA and CCB translator work and attribution. The bootstrap verified on 2026-09-26 used compiled MO catalogs from a specific CCB release; it is not a maintained CPH PO pipeline or a CPH Transifex project. Read [translation inputs](../docs/project/translation-inputs.md) and [translation credits](../TRANSLATION_CREDITS.md) before changing catalog sources. The former CCB Transifex link and screenshots in older versions of this page were CCB instructions and are not a CPH contribution route.

## Translators

For a CPH translation correction, identify the current source string and context in the CPH tree, the language and affected PO entry if present, then propose the change through [CPH contribution guidance](../CONTRIBUTING.md). Preserve the inherited `# Translators:` and `Last-Translator` metadata; do not replace an original translator's credit with a generic project name. [CPH Discussions](https://github.com/oncehere/Cataclysm-Phantom-Hope/discussions) is available for public coordination. Do not publish translation service credentials.

A PO catalog is editable source; an MO catalog is compiled output. CPH's temporary, pinned MO input is for baseline builds and does not establish the completeness or accuracy of current translation strings. A sustainable PO import/update path remains to be validated. Test changed placeholders, contexts, plural forms and markup against the current source and runtime before claiming coverage.

See [the inherited translator notes](../lang/notes/README_all_translators.md) for gettext format examples. Historical header examples credit CDDA contributors and should remain attributed to them; they do not define the current CPH reporting URL or project account.

### Glossary

This inherited glossary explains terms found in the game data; verify each
entry against the current CPH source before using it as a new design rule.

* **Exodii**: The Exodii are a bunch of humans from another dimension.  When
  the Blob invaded their world, they managed to acquire enough technology to
  open portals of their own, and now they portal to worlds that have been
  attacked by the Blob and try to rescue survivors.  Exodii is a horrible
  mangling of "Exodus" - the word literally means leaving or going out and has
  connotations of forced emigration and refugees.  The Exodii are the people of
  an Exodus.  While Exodus is a Latin word and "ii" to indicate a plural is a
  Latin thing, but this isn't actually the [correct Latin
  plural](https://www.latin-is-simple.com/en/vocabulary/noun/9294/) for this
  word.

### Grammatical gender

For NPC dialogue (and potentially other strings) some languages may wish to
have alternate translations depending on the gender of the conversation
participants.  This two pieces of initial configuration.

1. The dialogue must have the relevant genders listed in the json file defining
   it.  See [the NPC docs](./JSON/NPCs.md).
2. Each language must specify the genders it wishes to use via the translation
   of `grammatical gender list`.  This should be a space-separated list of
   genders used in this language for such translations.  Don't add genders here
   until you're sure you will need them, because it will make more work for
   you.  If you need different genders than are currently supported you must
   add them to the `all_genders` lists in `lang/extract_json_strings.py` and
   `src/translations.cpp`.

Having done this, the relevant dialogue lines will appear multiple times for
translation, with different genders specified in the message context.  For
example, a context of `npc:m` would indicate that the NPC participant in the
conversation is male.

Because of technical limitations, all supported genders will appear as
contexts, but you only need to provide translations for the genders listed in
`grammatical gender list` for your language.

Other parts of the game have various ad hoc solutions to grammatical gender, so
don't be surprised to see other contexts appearing for other strings.

### Tips

There are format rules in the inherited catalogs that CPH translators should observe.
These include the use of terms like `%s` and `%3$d` (leave them as they are),
and the use of tags like `<name>`, which shouldn't be translated.

Information about these and any other issues specific to individual languages,
can be found in the inherited [language notes folder][4].

General notes for all translators are in `README_all_translators.txt`,
and notes specific to a language may be stored as `<lang_id>.txt`,
for example `de.txt` for German.

The number of translatable strings and translation coverage depend on the current
CPH tree and catalog input; use a measured count rather than an inherited total.

## Developers

The inherited CPH source uses [GNU gettext][5] and the translation interfaces in `src/translations.h` and `src/translations.cpp`.

Using `gettext` requires two actions:

* Marking strings that should be translated in the source code.
* Calling translation functions at run time.

Marking translatable string allows for their automatic extraction.
This process generates a file that maps the original string (usually in English)
as it appears in the source code to the translated string.
These mappings are used at run time by the translation functions.

Note that only extracted strings can get translated, since the original string
is acting as the identifier used to request the translation.
If a translation function can't find the translation, it returns the original
string.

### Translation Functions

In order to mark a string for translation and to obtain its translation at
runtime, you should use one of the following functions and classes.

String *literals* that are used in any of these functions are automatically
extracted. Non-literal strings are still translated at run time, but they won't
get extracted.

#### `_()`

This function is appropriate for use on simple strings, for example:

```cpp
const char *translated = _( "text marked for translation" )
```

It also works directly:

```cpp
add_msg( _( "You drop the %s." ), the_item_name );
```

Strings from the JSON files are extracted by the `lang/extract_json_strings.py`
script, and can be translated at run time using `_()`. If translation context
is desired for a JSON string, `class translation` can be used instead, which is
documented below.

#### `pgettext()`

This function is useful when the original string's meaning is ambiguous in
isolation. For example, the word "blue", which can mean either a color or an
emotion.

In addition to the translatable string, `pgettext` receives a context which is
provided to the translators, but is not part of the translated string itself.
This function's first parameter is the context, the second is the string to be
translated:

```cpp
const char *translated = pgettext("The color", "blue")
```

#### `n_gettext()`

Some languages have complex rules for plural forms. `n_gettext` can be used to
translate these plurals correctly. Its first parameter is the untranslated
string in singular form, the second parameter is the untranslated string in
plural form and the third one is used to determine which one of the first two
should be used at run time:

```cpp
const char *translated = n_gettext("one zombie", "many zombies", num_of_zombies)
```

### `translation`

There are times when you want to store a string for translation, maybe with
translation context; Sometimes you may also want to store a string that needs no
translation or has plural forms. `class translation` in `translations.h|cpp`
offers these functionalities in a single wrapper:

```cpp
const translation text = to_translation( "Context", "Text" );
```

```cpp
const translation text = to_translation( "Text without context" );
```

```cpp
const translation text = pl_translation( "Singular", "Plural" );
```

```cpp
const translation text = pl_translation( "Context", "Singular", "Plural" );
```

```cpp
const translation text = no_translation( "This string will not be translated" );
```

The string can then be translated/retrieved with the following code

```cpp
const std::string translated = text.translated();
```

```cpp
// this translates the plural form of the text corresponding to the number 2
const std::string translated = text.translated( 2 );
```

`class translation` can also be read from JSON. The method `translation::deserialize()`
handles deserialization from a `JsonIn` object, so translations can be read from
JSON using the appropriate JSON functions. The JSON syntax is as follows:

```jsonc
"name": "bar"
```

```jsonc
"name": { "ctxt": "foo", "str": "bar", "str_pl": "baz" }
```

or

```jsonc
"name": { "ctxt": "foo", "str_sp": "foo" }
```

In the above code, `"ctxt"` and `"str_pl"` are both optional, whereas `"str_sp"`
is equivalent to specifying `"str"` and `"str_pl"` with the same string. Additionally,
`"str_pl"` and `"str_sp"` will only be read if the translation object is constructed using
`plural_tag` or `pl_translation()`, or converted using `make_plural()`. Here's
an example:

```cpp
translation name{ translation::plural_tag() };
jsobj.read( "name", name );
```

If neither `"str_pl"` nor `"str_sp"` is specified, the plural form defaults to
the singular form + "s". However, `"str_pl"` may still be needed if the unit
test cannot determine whether the correct plural form can be formed by simply
appending "s".

### Translation Context Comments

#### JSON

JSON objects can add comments for translators by writing it like below (the order
of the entries does not matter):

```jsonc
"name": {
    "//~": "as in 'foobar'",
    "str": "bar"
}
```

Do note that the JSON syntax is only supported if a JSON value is read using
`translation`. If you want new json values to use this format, refer to
`translations.h|cpp` and read the strings with `translation`. Afterwards
you also need to update `extract_json_strings.py` and run `lang/update_pot.sh`
to ensure that the strings are correctly extracted for translation, and run the
unit test to fix text styling issues reported by the `translation` class.

If a string doesn't need to be translated, you can write `"NO_I18N"` in the
`"//~"` comment, and this string will not be available to translators.
Alternatively, you can specify `"//I18N": false` at the top level.
(see [JSON_INFO.md](JSON/JSON_INFO.md#translatable-strings))

#### C++

C++ code can add comments for translators by including a ~ in a comment on the
previous line of the file containing the string to be translated.

```C++
//~ foo
some.function( _( "translators get 'foo' for context translating this string" ) );
```

### Static string variables

Translation functions should not be called when initializing a static variable.
For global static variables, calling these functions does nothing because the
translation system is not yet initialized. For local static variables, the
translation will only happen once and switching language in-game will not work
properly. Consider using translation objects (`to_translation()` or `pl_translation()`)
to mark the string for extraction and call `translation::translated()` on the
fly to ensure the string is properly translated each time.

Note if a string becomes translated in-game after you add a translation function
call to the initialization of a global static variable, it usually means a
translation call is already made when the string is used, and your newly added
translation call happens to mark the string for extraction. In this case, using
a translation object is also recommended to avoid calling the translation
function twice.

### Recommendations

In the inherited source, some classes, like `itype` and `mtype`, provide a wrapper
for the translation functions, called `nname`.

When an empty string is marked for translation, it is always translated into
debug information, rather than an empty string.
On most cases, strings can be considered to be never empty, and thus always
safe to mark for translation, however, when handling a string that can be empty
and *needs* to remain empty after translation, the string should be checked for
emptiness and only passed to a translation function when is non-empty.

Error and debug messages must not be marked for translation.
When they appear, the player is expected to report them *exactly* as they are
printed by the game.

See the [gettext manual][6] for more information.

## Maintainers

The inherited page formerly described a weekly `pull-translations` workflow and a CCB Transifex account. Neither is an active CPH translation service by virtue of this document. The 2026-09-26 CPH baseline used pinned MO assets, documented in [translation inputs](../docs/project/translation-inputs.md). Before importing or regenerating PO catalogs, define and verify the actual source service, credentials boundary, license/attribution retention, merge strategy and repeatable checks. Do not overwrite inherited PO headers or substitute an empty MO catalog for a real translation.

The repository contains `lang/update_pot.sh`, `lang/merge_po.sh` and `lang/compile_mo.sh`; use them only after checking dependencies and input provenance. A targeted syntax check can use `msgfmt -c --statistics -o /dev/null lang/po/LOCALE.po` on a real file. Compiling an MO is not evidence that source extraction, linguistic quality or game loading passed. Report the exact command and result; see [CONTRIBUTING.md](../CONTRIBUTING.md).

[4]: ../lang/notes
[5]: https://www.gnu.org/software/gettext/
[6]: https://www.gnu.org/software/gettext/manual/index.html
