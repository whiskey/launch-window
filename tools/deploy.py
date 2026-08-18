#!/usr/bin/env python3
"""Install the firmware onto the board.

    tools/deploy.py                push changed files, then restart
    tools/deploy.py --all          push everything regardless of checksum
    tools/deploy.py --no-restart   push and leave the board at the REPL
    tools/deploy.py --wipe-wifi    also delete the saved credentials, so the
                                   board comes back up in setup mode, and print
                                   how to join it
    tools/deploy.py --keep-docs    ship the docstrings too, so a traceback's
                                   line numbers match the files you are reading

Docstrings are removed on the way (see `strip_docs.py`): MicroPython keeps them
in RAM for as long as the module is imported, and this firmware's documentation
costs more heap than the board can spare. The files in the repository are
untouched — only what is written to flash is stripped.

Only files whose contents differ are written, because writing flash is the slow
and failure-prone part of this loop: a re-deploy after editing one module takes
about a second instead of fifteen.

`wifi.json`, `cache.json` and `setup.json` live only on the board: nothing in
this repository is ever pushed over them. The credentials are not here and a
deploy must not be able to destroy them by accident — that would turn every
firmware tweak into a walk to wherever the beacon is plugged in, with a phone.
The two deliberate exceptions are `--wipe-wifi`, which removes `wifi.json` on
request, and `setup.json`, which is created — never overwritten — when the board
has no setup passphrase yet, so that a deploy can print it.
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


def setup_ap() -> dict:
    """The `setup_ap` block the board will boot with (see `main.py`)."""
    with open(os.path.join(FIRMWARE, "config.json"), "rb") as handle:
        return json.loads(handle.read()).get("setup_ap") or {}


def announce_setup_mode(board, reason: str) -> None:
    """Print how to join the setup access point, under the line `reason`.

    The passphrase is random and lives only on the board, so read it back when
    it is already there and generate it here when it is not — otherwise the
    owner would have to read it off the serial console before they could join.
    A passphrase configured in `config.json` wins, exactly as it does on the
    board, and no `setup.json` is written for one.
    """
    access_point = setup_ap()
    passphrase = access_point.get("password")
    if not passphrase:
        try:
            passphrase = json.loads(board.get(portal.PASSPHRASE_PATH))["passphrase"]
        except Exception:
            passphrase = portal.generate_passphrase(source=secrets.token_bytes)
            board.put(
                json.dumps({"passphrase": passphrase}).encode(),
                portal.PASSPHRASE_PATH,
            )
    print("\n%s" % reason)
    print("  network:    %s" % access_point.get("ssid", "launch-window-setup"))
    print("  passphrase: %s" % passphrase)
    print("  then open:  http://192.168.4.1/")


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

        stored_wifi = (
            board.check("import os\nprint('wifi.json' in os.listdir('/'))").strip()
            == "True"
        )
        if wipe_wifi:
            if stored_wifi:
                # Deliberately unguarded: a remove that fails silently would be
                # reported below as a board in setup mode that is not.
                board.check("import os\nos.remove('wifi.json')")
                reason = "removed wifi.json"
            else:
                reason = "there was no wifi.json to remove"
            stored_wifi = False
        else:
            reason = "no wifi.json on the board"

        if not stored_wifi:
            announce_setup_mode(
                board,
                "%s — it starts its setup access point on the next boot:" % reason,
            )
    finally:
        board.exit_raw()

    if restart:
        board.reset()
        print("restarted")
    board.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
