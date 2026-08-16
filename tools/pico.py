#!/usr/bin/env python3
"""Talk to a MicroPython board over USB CDC. Standard library only.

Written rather than depending on `mpremote` for the same reason the firmware
has no framework: this is forty lines of protocol, it has to work on a machine
where nothing has been installed, and the raw-paste flow control is the one
part that actually needs care.

The raw REPL alone is not enough. Sending a 3 kB module through it drops data
silently, because the board has no way to say "stop, my buffer is full" — the
first attempt to push the recon script this way returned nothing at all. Raw
*paste* mode (Ctrl-A then `\\x05A\\x01`) adds a window-based flow control, which
is what `mpremote` uses and what this implements.

    pico.py run  '<python code>'
    pico.py runf <local.py>          exec a local file on the board
    pico.py get  <remote> [local]
    pico.py put  <local> <remote>
    pico.py ls   [dir]
    pico.py rm   <remote>
    pico.py reset                    soft reset, so main.py runs again

The board is found by globbing /dev/cu.usbmodem*, or named with $PICO_DEV.
"""

from __future__ import annotations

import base64
import glob
import os
import select
import sys
import termios
import time

READ_TIMEOUT = 10.0
CHUNK = 192  # bytes per put() call, kept well under the board's line limits


def _digest(data: bytes) -> int:
    """The same rolling hash the board computes, for verifying a push."""
    value = 0
    for byte in data:
        value = (value * 31 + byte) & 0xFFFFFFFF
    return value


def find_device() -> str:
    override = os.environ.get("PICO_DEV")
    if override:
        return override
    candidates = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not candidates:
        raise SystemExit(
            "no /dev/cu.usbmodem* found — is the board plugged in and running "
            "MicroPython? Set $PICO_DEV to override."
        )
    return candidates[0]


class Pico:
    def __init__(self, device: str | None = None):
        self.device = device or find_device()
        self.fd = os.open(self.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(self.fd)
        cflag = (cflag | termios.CLOCAL | termios.CREAD) & ~termios.CRTSCTS
        cc[termios.VMIN] = 0
        cc[termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, [0, 0, cflag, 0, ispeed, ospeed, cc])
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    # -- plumbing ---------------------------------------------------------

    def close(self) -> None:
        os.close(self.fd)

    def _write(self, data: bytes, timeout: float = READ_TIMEOUT) -> None:
        """Write every byte.

        `os.write` on a non-blocking tty returns after however many bytes fit
        in the driver's buffer, which is not necessarily all of them. Ignoring
        that return value works fine for one-line commands and then loses data
        in the middle of a multi-kilobyte push, where the board waits forever
        for a terminator that was silently dropped.
        """
        view = memoryview(data)
        deadline = time.time() + timeout
        while view:
            try:
                written = os.write(self.fd, view)
            except BlockingIOError:
                written = 0
            if written:
                view = view[written:]
                deadline = time.time() + timeout
            else:
                _, ready, _ = select.select([], [self.fd], [], 0.05)
                if not ready and time.time() > deadline:
                    raise TimeoutError("serial write stalled with %d bytes left" % len(view))

    def _read_until(self, token: bytes, timeout: float = READ_TIMEOUT) -> bytes:
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if token in buf:
                return buf
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if ready:
                chunk = os.read(self.fd, 4096)
                if chunk:
                    buf += chunk
                    deadline = time.time() + timeout
        raise TimeoutError("timed out waiting for %r; got %r" % (token, buf[-400:]))

    def _read_exact(self, count: int, timeout: float = READ_TIMEOUT) -> bytes:
        buf = b""
        deadline = time.time() + timeout
        while len(buf) < count and time.time() < deadline:
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if ready:
                chunk = os.read(self.fd, count - len(buf))
                if chunk:
                    buf += chunk
                    deadline = time.time() + timeout
        if len(buf) < count:
            raise TimeoutError("short read: wanted %d, got %r" % (count, buf))
        return buf

    # -- REPL -------------------------------------------------------------

    def enter_raw(self) -> None:
        self._write(b"\r\x03\x03")  # interrupt whatever is running
        time.sleep(0.2)
        termios.tcflush(self.fd, termios.TCIFLUSH)
        self._write(b"\r\x01")
        self._read_until(b"raw REPL; CTRL-B to exit\r\n>")

    def exit_raw(self) -> None:
        self._write(b"\r\x02")
        time.sleep(0.2)

    def exec(self, code: str, timeout: float = 30.0) -> tuple[str, str]:
        """Run code on the board, returning (stdout, stderr)."""
        data = code.encode()
        self._write(b"\x05A\x01")
        response = self._read_exact(2, 3.0)
        if response == b"R\x01":
            window = int.from_bytes(self._read_exact(2, 3.0), "little")
            available = window
            sent = 0
            while sent < len(data):
                while available == 0:
                    signal = self._read_exact(1, timeout)
                    if signal == b"\x01":
                        available += window
                    elif signal == b"\x04":
                        self._write(b"\x04")
                        raise RuntimeError("board aborted raw-paste")
                count = min(available, len(data) - sent, window)
                self._write(data[sent : sent + count])
                sent += count
                available -= count
            self._write(b"\x04")
            self._read_until(b"\x04", timeout)
        else:  # older firmware without raw-paste; small scripts only
            self._write(data + b"\x04")
            self._read_until(b"OK", 5.0)
        body = self._read_until(b"\x04>", timeout).rsplit(b"\x04>", 1)[0]
        out, _, err = body.partition(b"\x04")
        return out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    def check(self, code: str, timeout: float = 30.0) -> str:
        """`exec`, but a traceback on the board becomes an exception here."""
        out, err = self.exec(code, timeout)
        if err.strip():
            raise RuntimeError(err.strip())
        return out

    # -- files ------------------------------------------------------------

    def get(self, remote: str) -> bytes:
        out = self.check(
            "import ubinascii,sys\n"
            "f=open(%r,'rb')\n"
            "while True:\n"
            "    b=f.read(192)\n"
            "    if not b: break\n"
            "    sys.stdout.write(ubinascii.b2a_base64(b))\n"
            "f.close()\n" % remote,
            timeout=90,
        )
        return b"".join(base64.b64decode(line) for line in out.split() if line)

    def resync(self) -> None:
        """Get back to a known state after a lost byte."""
        self.exit_raw()
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.enter_raw()

    def _put_once(self, data: bytes, remote: str) -> None:
        parent = remote.rsplit("/", 1)[0]
        if parent and parent != remote:
            self.check("import os\ntry:\n os.mkdir(%r)\nexcept Exception: pass" % parent)
        # Delete before writing rather than truncating with 'wb'. Overwriting an
        # existing file makes littlefs erase its old blocks, and an RP2040 stalls
        # with interrupts off for the duration of a flash erase — long enough to
        # drop the USB byte that acknowledges the write. Creating a fresh file
        # erases nothing, and this failure went from every time to never.
        self.check("import os\ntry:\n os.remove(%r)\nexcept Exception: pass" % remote)
        self.check("f=open(%r,'wb')\nimport ubinascii" % remote)
        for offset in range(0, len(data), CHUNK):
            encoded = base64.b64encode(data[offset : offset + CHUNK]).decode()
            self.check("f.write(ubinascii.a2b_base64(%r))" % encoded)
        self.check("f.close()")

    def checksum(self, remote: str) -> tuple[int, int]:
        """(size, hash) of a file on the board, for verifying a push."""
        out = self.check(
            "h=0\ns=0\n"
            "f=open(%r,'rb')\n"
            "while True:\n"
            "    b=f.read(256)\n"
            "    if not b: break\n"
            "    s+=len(b)\n"
            "    for c in b: h=(h*31+c) & 0xFFFFFFFF\n"
            "f.close()\n"
            "print(s,h)\n" % remote,
            timeout=60,
        )
        size, digest = out.split()
        return int(size), int(digest)

    def put(self, data: bytes, remote: str, retries: int = 3) -> None:
        """Write a file to the board and prove it arrived intact.

        Serial to this board is not perfectly reliable — a flash erase can eat
        a byte — so a push that reports success without checking is a push that
        can leave truncated code on a device that then runs it. Every attempt
        is verified against a hash of the local bytes, and a failure restarts
        the whole file rather than trying to patch up a partial one.
        """
        expected = (len(data), _digest(data))
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                self._put_once(data, remote)
                if self.checksum(remote) == expected:
                    return
                last_error = RuntimeError("checksum mismatch after write")
            except (TimeoutError, RuntimeError) as error:
                last_error = error
            if attempt < retries - 1:
                self.resync()
        raise RuntimeError("could not write %s: %s" % (remote, last_error))

    def reset(self) -> None:
        self.exit_raw()
        self._write(b"\r\x04")
        time.sleep(0.5)

    def hard_reset(self, settle: float = 4.0) -> None:
        """`machine.reset()`, then wait for USB to come back and reopen.

        A hard reset re-enumerates the CDC device, so the file descriptor this
        object holds becomes invalid — writing to it raises ENXIO. The port can
        also come back under a different name, so it is looked up again.
        """
        try:
            # Leave raw mode first. In the raw REPL nothing runs until Ctrl-D,
            # so writing the reset as plain text there just fills a buffer that
            # is then discarded — the board keeps running and every later
            # measurement is taken next to a live firmware.
            self._write(b"\r\x02")
            time.sleep(0.2)
            self._write(b"\r\x03")  # interrupt whatever main.py is doing
            time.sleep(0.2)
            self._write(b"import machine; machine.reset()\r\n")
        except OSError:
            pass  # the reset can land before the write is acknowledged
        try:
            os.close(self.fd)
        except OSError:
            pass
        deadline = time.time() + 20
        time.sleep(settle)
        while time.time() < deadline:
            try:
                self.device = find_device()
                self.__init__(self.device)
                return
            except (OSError, SystemExit):
                time.sleep(0.5)
        raise TimeoutError("board did not come back after a hard reset")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    command = sys.argv[1]
    board = Pico()
    try:
        if command == "reset":
            board.reset()
            print("reset; main.py is running")
            return 0
        board.enter_raw()
        if command == "run":
            out, err = board.exec(sys.argv[2], float(os.environ.get("PICO_TIMEOUT", 30)))
            sys.stdout.write(out)
            if err.strip():
                sys.stderr.write(err)
                return 1
        elif command == "runf":
            out, err = board.exec(
                open(sys.argv[2]).read(), float(os.environ.get("PICO_TIMEOUT", 90))
            )
            sys.stdout.write(out)
            if err.strip():
                sys.stderr.write(err)
                return 1
        elif command == "get":
            data = board.get(sys.argv[2])
            if len(sys.argv) > 3:
                with open(sys.argv[3], "wb") as handle:
                    handle.write(data)
                print("%d bytes -> %s" % (len(data), sys.argv[3]))
            else:
                sys.stdout.write(data.decode("utf-8", "replace"))
        elif command == "put":
            with open(sys.argv[2], "rb") as handle:
                data = handle.read()
            board.put(data, sys.argv[3])
            print("%d bytes -> %s" % (len(data), sys.argv[3]))
        elif command == "ls":
            directory = sys.argv[2] if len(sys.argv) > 2 else "/"
            sys.stdout.write(
                board.check(
                    "import os\n"
                    "for n in sorted(os.listdir(%r)):\n"
                    "    st=os.stat(%r.rstrip('/')+'/'+n)\n"
                    "    print(('d' if st[0] & 0x4000 else '-'), '%%7d' %% st[6], n)\n"
                    % (directory, directory)
                )
            )
        elif command == "rm":
            board.check("import os\nos.remove(%r)" % sys.argv[2])
            print("removed %s" % sys.argv[2])
        else:
            print(__doc__)
            return 1
    finally:
        board.exit_raw()
        board.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
