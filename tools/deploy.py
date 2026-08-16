#!/usr/bin/env python3
"""Install the firmware onto the board.

    tools/deploy.py                push changed files, then restart
    tools/deploy.py --all          push everything regardless of checksum
    tools/deploy.py --no-restart   push and leave the board at the REPL
    tools/deploy.py --wipe-wifi    also delete the saved credentials, so the
                                   board comes back up in setup mode
    tools/deploy.py --keep-docs    ship the docstrings too, so a traceback's
                                   line numbers match the files you are reading

Docstrings are removed on the way (see `strip_docs.py`): MicroPython keeps them
in RAM for as long as the module is imported, and this firmware's documentation
costs more heap than the board can spare. The files in the repository are
untouched — only what is written to flash is stripped.

Only files whose contents differ are written, because writing flash is the slow
and failure-prone part of this loop: a re-deploy after editing one module takes
about a second instead of fifteen.

`wifi.json` and `cache.json` live only on the board and are never touched. The
credentials are not in this repository and a deploy must not be able to destroy
them by accident — that would turn every firmware tweak into a walk to wherever
the beacon is plugged in, with a phone.
"""

from __future__ import annotations

import json
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import pico  # noqa: E402
import strip_docs  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import portal  # noqa: E402

FIRMWARE = os.path.join(ROOT, "firmware")

# Files the board owns. A deploy never writes or removes these.
BOARD_OWNED = ("wifi.json", "cache.json", "setup.json")


def files_to_push():
    """(local path, remote path) for everything the firmware needs."""
    yield os.path.join(FIRMWARE, "main.py"), "/main.py"
    yield os.path.join(FIRMWARE, "config.json"), "/config.json"
    library = os.path.join(FIRMWARE, "lib")
    for name in sorted(os.listdir(library)):
        if name.endswith(".py"):
            yield os.path.join(library, name), "/lib/" + name


def payload(local: str, keep_docs: bool) -> bytes:
    """The exact bytes to write for a local file."""
    with open(local, "rb") as handle:
        data = handle.read()
    if keep_docs or not local.endswith(".py"):
        return data
    return strip_docs.strip_bytes(data)


def main() -> int:
    push_all = "--all" in sys.argv
    restart = "--no-restart" not in sys.argv
    wipe_wifi = "--wipe-wifi" in sys.argv
    keep_docs = "--keep-docs" in sys.argv

    board = pico.Pico()
    print("board: %s" % board.device)
    board.enter_raw()
    try:
        pushed, skipped, saved = 0, 0, 0
        for local, remote in files_to_push():
            data = payload(local, keep_docs)
            saved += os.path.getsize(local) - len(data)
            if not push_all:
                try:
                    if board.checksum(remote) == (len(data), pico._digest(data)):
                        skipped += 1
                        continue
                except Exception:
                    pass  # not there yet, or unreadable: push it
            board.put(data, remote)
            print("  wrote %-22s %5d bytes" % (remote, len(data)))
            pushed += 1

        print(
            "%d pushed, %d already current%s"
            % (
                pushed,
                skipped,
                "" if keep_docs else " (%d bytes of docstrings left on the host)" % saved,
            )
        )

        if wipe_wifi:
            board.check(
                "import os\ntry:\n os.remove('wifi.json')\nexcept Exception: pass"
            )
            print("removed wifi.json — the board will come up in setup mode")
        else:
            existing = board.check(
                "import os\nprint('wifi.json' in os.listdir('/'))"
            ).strip()
            if existing != "True":
                # The setup passphrase is random and lives only on the board.
                # If it has not been generated yet, generate it here so the
                # deploy can print it — otherwise the owner would have to read
                # it off the serial console before they could join.
                try:
                    passphrase = json.loads(board.get("setup.json"))["passphrase"]
                except Exception:
                    passphrase = portal.generate_passphrase(source=secrets.token_bytes)
                    board.put(
                        json.dumps({"passphrase": passphrase}).encode(), "setup.json"
                    )
                print(
                    "\nno wifi.json on the board — it starts its setup access point "
                    "on the next boot:"
                )
                print("  network:    launch-window-setup")
                print("  passphrase: %s" % passphrase)
                print("  then open:  http://192.168.4.1/")
    finally:
        board.exit_raw()

    if restart:
        board.reset()
        print("restarted")
    board.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
