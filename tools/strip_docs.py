#!/usr/bin/env python3
"""Remove docstrings from firmware modules before they are written to flash.

MicroPython compiles a module when it is imported and keeps the result in RAM.
There is no `.pyc` step and no `mpy-cross` here, so every docstring becomes a
string object living on a 264 kB heap for as long as the module is loaded. The
eleven firmware modules cost about 35 kB of heap to import with their
documentation attached, on a board where the largest contiguous allocation
after boot is already only a few kilobytes.

That is a real constraint and this is the resolution: the documentation lives
in the repository, where it is read, and not in the flash of a device that has
no reader. `tools/deploy.py --keep-docs` skips this when a traceback needs to
line up with the source you are looking at.

The transform runs on the host through `ast`, so the result is guaranteed to
parse — it is generated from the parse tree rather than by deleting lines that
look like docstrings.
"""

from __future__ import annotations

import ast

DOCSTRING_HOLDERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def strip(source: str) -> str:
    """Return `source` with every docstring removed."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, DOCSTRING_HOLDERS):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            # A function whose entire body is its docstring still needs one
            # statement, or the result will not parse.
            node.body = body[1:] if len(body) > 1 else [ast.Pass()]
    stripped = ast.unparse(tree)
    compile(stripped, "<stripped>", "exec")  # never ship something that will not parse
    return stripped


def strip_bytes(data: bytes) -> bytes:
    return strip(data.decode("utf-8")).encode("utf-8")


if __name__ == "__main__":
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    library = os.path.join(root, "firmware", "lib")
    before = after = 0
    for name in sorted(os.listdir(library)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(library, name)) as handle:
            source = handle.read()
        stripped = strip(source)
        before += len(source)
        after += len(stripped)
        print(
            "%-12s %6d -> %6d bytes (%.0f %% smaller)"
            % (name, len(source), len(stripped), 100 * (1 - len(stripped) / len(source)))
        )
    print("%-12s %6d -> %6d bytes" % ("total", before, after))
    sys.exit(0)
