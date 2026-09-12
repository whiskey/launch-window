#!/usr/bin/env python3
"""Check the string catalogue against the source, both ways.

    app/tools/check-strings.py

Every user-facing string is written as `String(localized: "key", defaultValue:)`
with an explicit key, so the catalogue has a contract that can be verified
rather than eyeballed. This checks four things:

  * every key used in Swift exists in `Localizable.xcstrings`;
  * every entry in the catalogue is still used by some Swift file — apart from
    the AppIntents metadata, whose keys are its English text and which therefore
    cannot be found this way;
  * every entry has both English and German;
  * English and German agree on how many `%n$@` placeholders they take, and on
    which ones, because a translation that drops one is a crash waiting for the
    first reader in that language.

Exits non-zero and prints what is wrong. Nothing here writes anything.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOG = ROOT / "Shared" / "Localizable.xcstrings"
LANGUAGES = ("en", "de")

# `String(localized: "key", defaultValue: "...")`, possibly wrapped over lines.
CALL = re.compile(r'String\(localized:\s*"([^"]+)"\s*,\s*defaultValue:', re.S)
PLACEHOLDER = re.compile(r"%(\d+)\$@")
# Entries whose key is their English text, written as literals so the AppIntents
# metadata extractor can see them.
INTENT_COMMENT = "AppIntents metadata; the English text is the key."


def keys_in_source() -> set[str]:
    found: set[str] = set()
    for path in sorted(ROOT.rglob("*.swift")):
        found.update(CALL.findall(path.read_text()))
    return found


def main() -> int:
    if not CATALOG.exists():
        print("missing %s" % CATALOG, file=sys.stderr)
        return 2

    catalog = json.loads(CATALOG.read_text())
    entries = catalog.get("strings", {})
    used = keys_in_source()
    problems: list[str] = []

    for key in sorted(used - set(entries)):
        problems.append("not in the catalogue: %s" % key)

    for key, entry in sorted(entries.items()):
        if entry.get("comment") == INTENT_COMMENT:
            continue
        if key not in used:
            problems.append("in the catalogue but unused: %s" % key)

    for key, entry in sorted(entries.items()):
        localizations = entry.get("localizations", {})
        values = {}
        for language in LANGUAGES:
            unit = localizations.get(language, {}).get("stringUnit", {})
            value = unit.get("value")
            if value is None:
                problems.append("%s has no %s" % (key, language))
            else:
                values[language] = value
        if len(values) == len(LANGUAGES):
            shapes = {lang: sorted(PLACEHOLDER.findall(text)) for lang, text in values.items()}
            if len(set(map(tuple, shapes.values()))) > 1:
                problems.append(
                    "%s: placeholders differ %s"
                    % (key, ", ".join("%s=%s" % (l, s or "none") for l, s in shapes.items()))
                )

    if problems:
        for problem in problems:
            print(problem)
        print("\n%d problem(s)" % len(problems))
        return 1

    print("%d keys, %s, all present and agreeing" % (len(entries), " and ".join(LANGUAGES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
