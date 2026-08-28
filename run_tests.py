#!/usr/bin/env python3
"""Single entry point for the whole test suite.

    env_seven/bin/python run_tests.py

Why this exists: ``tests/`` grew organically and holds four different shapes of
test file, so "the suite is green" used to mean "someone ran a dozen files by
hand and read the output". This runner executes every one of them, boots and
tears down its own server for the socket tests, and returns a single exit code.

The four shapes it handles:

1. **Script + exit code** — ends with ``exit(0 if all(results) else 1)``.
   Most files. Verdict comes from the exit status.
2. **unittest** — ``unittest.main()`` under a ``__main__`` guard. Also exits
   with a real status.
3. **pytest-shaped, no ``__main__``** — defines ``test_*()`` and nothing calls
   them, so running the file as a script silently does nothing. The runner
   invokes them itself, so no dependency on pytest being installed.
4. **Print-only** — no asserts, no exit code, cannot fail. Reported as UNSCORED
   rather than counted green, because a test that can't fail isn't a pass.

A ``FAIL`` line in a file's output is treated as a failure even if the file
exits 0 — several files print per-check results, and shape 4 would otherwise
hide real breakage.

Port hygiene: the socket server is always torn down and the port confirmed free
before the runner returns, including on exception or Ctrl-C. A leftover listener
would make the next run test stale code (and ``app.py`` refuses to start into an
occupied port).
"""
import argparse
import collections
import os
import re
import runpy
import signal
import socket
import subprocess
import threading
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(REPO, "tests")

# The socket tests drive a python-socketio *client* against a real server. They
# hardcode this port; keep them in sync if it ever changes.
SOCKET_PORT = 5005

# Per-file wall-clock ceiling. Socket tests sleep on purpose (waiting out turn
# timers), so they get much longer than engine tests.
ENGINE_TIMEOUT = 180
SOCKET_TIMEOUT = 300

# Server boot: how long to wait for the port to start accepting.
BOOT_TIMEOUT = 45

PASS, FAIL, UNSCORED, ERROR, TIMEOUT, SKIP = "PASS", "FAIL", "UNSCORED", "ERROR", "TIMEOUT", "SKIP"

GREEN, RED, YELLOW, GREY, BOLD, RESET = (
    ("\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() else ("", "", "", "", "", "")
)
COLOR = {PASS: GREEN, FAIL: RED, ERROR: RED, TIMEOUT: RED, UNSCORED: YELLOW, SKIP: GREY}


# ── discovery ────────────────────────────────────────────────────────────

def needs_server(path: str) -> bool:
    """True if the file drives a socket.io client against a running server."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    return str(SOCKET_PORT) in src or "socketio.Client" in src


def discover(pattern=None):
    """Return (engine_files, socket_files), each sorted by name."""
    engine, sock = [], []
    for name in sorted(os.listdir(TESTS)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        if pattern and pattern not in name:
            continue
        path = os.path.join(TESTS, name)
        (sock if needs_server(path) else engine).append(path)
    return engine, sock


# ── running one file (child process: --_run-one) ─────────────────────────

def run_one_inprocess(path: str) -> int:
    """Execute one test file the way its author intended. Runs in a child.

    Exit codes: 0 pass, 1 fail, 3 unscored (ran clean but asserts nothing).
    """
    sys.path.insert(0, REPO)
    # Present the argv a plain `python tests/foo.py` would see. unittest.main()
    # parses sys.argv and dies on the runner's own --_run-one flag.
    sys.argv = [path]
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    has_main_guard = "__main__" in src

    try:
        globs = runpy.run_path(path, run_name="__main__")
    except SystemExit as exc:
        # Shapes 1 and 2 decide their own verdict.
        code = exc.code
        if code is None:
            code = 0
        return code if isinstance(code, int) else 1

    # Ran to completion without exiting. If it defines test_* functions and has
    # no __main__ guard, nothing has actually executed them yet (shape 3).
    funcs = [
        (name, obj) for name, obj in sorted(globs.items())
        if name.startswith("test_") and callable(obj)
    ]
    if funcs and not has_main_guard:
        failed = False
        for name, fn in funcs:
            try:
                fn()
            except AssertionError as exc:
                print("FAIL %s: assertion failed: %s" % (name, exc))
                failed = True
            except Exception as exc:  # noqa: BLE001 - report, don't mask
                import traceback
                traceback.print_exc()
                print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
                failed = True
            else:
                print("PASS %s" % name)
        return 1 if failed else 0

    # No verdict of any kind: asserts nothing, exits nothing.
    if "assert" not in src and not funcs:
        return 3
    return 0


def _tail(text: str, lines: int = 18) -> str:
    kept = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join("    " + ln for ln in kept[-lines:])


def run_file(path: str, timeout: int, env=None):
    """Run one test file in a subprocess. Returns (verdict, seconds, output)."""
    started = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--_run-one", path],
            cwd=REPO,
            env={**os.environ, **(env or {}), "PYTHONUNBUFFERED": "1"},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return TIMEOUT, time.time() - started, out

    elapsed = time.time() - started
    out = proc.stdout + proc.stderr

    # A printed FAIL outranks a clean exit code: several files report per-check
    # results and then exit 0 regardless.
    printed_fails = len(re.findall(r"(?m)^\s*FAIL\b", out))
    if printed_fails:
        return FAIL, elapsed, out
    if proc.returncode == 3:
        return UNSCORED, elapsed, out
    if proc.returncode == 0:
        return PASS, elapsed, out
    if proc.returncode < 0:
        return ERROR, elapsed, out
    return FAIL, elapsed, out


# ── the socket-test server ───────────────────────────────────────────────

def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


class TestServer:
    """Boots `PORT=<port> python app.py` and guarantees the port is released.

    app.py deliberately refuses to start when the port is already serving (two
    processes would split in-memory rooms), so a stale listener is fatal to the
    run rather than something to work around silently.
    """

    def __init__(self, port: int):
        self.port = port
        self.proc = None
        self.log = ""
        # The server's stdout is a pipe, and a pipe nobody reads fills up: at
        # ~64KB the OS blocks the writer, which here means the *game server*
        # freezes mid-run holding every client. It cost a full afternoon to find,
        # because the only symptom is that whichever socket test happens to run
        # last stops receiving events — so it read as a flaky test rather than a
        # wedged server. Drained continuously by a daemon thread into a bounded
        # buffer: the server can never block, and the tail is still there to
        # print if the boot fails.
        self._lines = collections.deque(maxlen=500)
        self._drain = None

    def start(self) -> bool:
        if port_open(self.port):
            print("%s%sERROR%s port %d is already in use — a previous run leaked a "
                  "server, or something else is listening." % (BOLD, RED, RESET, self.port))
            print("      find it with:  ss -ltnp | grep :%d" % self.port)
            return False

        print("%s· booting test server on port %d%s" % (GREY, self.port, RESET))
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(REPO, "app.py")],
            cwd=REPO,
            env={**os.environ, "PORT": str(self.port), "PYTHONUNBUFFERED": "1",
                 "FLASK_DEBUG": "0",
                 # Under test, a hidden-info leak must break the run loudly
                 # rather than scroll past in the log (see sockets/audience.py).
                 "LEAK_GUARD": "raise",
                 # A test run must not leave a snapshot behind, or the next real
                 # server boot would resurrect throwaway test rooms. Persistence
                 # itself is covered by tests/test_room_store.py, which uses its
                 # own snapshot path.
                 "ROOM_PERSIST": "0"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # Own process group, so stop() can signal any children eventlet spawns.
            start_new_session=True,
        )
        self._drain = threading.Thread(target=self._pump, daemon=True)
        self._drain.start()

        deadline = time.time() + BOOT_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self._drain.join(timeout=5)
                print("%s%sERROR%s test server exited during boot (code %s):"
                      % (BOLD, RED, RESET, self.proc.returncode))
                print(_tail("\n".join(self._lines)))
                return False
            if port_open(self.port):
                # Accepting TCP is not the same as serving Flask; wait for a real
                # response so the first socket test doesn't race the app.
                time.sleep(0.4)
                print("%s· server up%s" % (GREY, RESET))
                return True
            time.sleep(0.2)

        print("%s%sERROR%s test server did not open port %d within %ds"
              % (BOLD, RED, RESET, self.port, BOOT_TIMEOUT))
        self.stop()
        return False

    def _pump(self) -> None:
        """Read the server's output for as long as it runs, keeping only the tail."""
        stream = self.proc.stdout
        if stream is None:
            return
        try:
            for line in stream:
                self._lines.append(line.rstrip("\n"))
        except (ValueError, OSError):
            pass  # stream closed under us during shutdown — nothing to salvage

    def tail(self, lines: int = 18) -> str:
        """The end of the server's own log, for diagnosing a failed run."""
        return _tail("\n".join(self._lines), lines)

    def stop(self) -> None:
        """SIGTERM, then SIGKILL, then verify the port is actually free."""
        if self.proc is None:
            return  # never started (engine-only run) — nothing to release
        if self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        self.proc = None

        # The listener can linger briefly after the process dies.
        for _ in range(30):
            if not port_open(self.port):
                print("%s· server stopped, port %d released%s" % (GREY, self.port, RESET))
                return
            time.sleep(0.2)
        print("%s%sWARNING%s port %d still appears open after teardown — check "
              "for a stray process:  ss -ltnp | grep :%d"
              % (BOLD, YELLOW, RESET, self.port, self.port))


# ── reporting ────────────────────────────────────────────────────────────

def report(results) -> int:
    """Print the summary. Returns the process exit code."""
    width = max((len(os.path.basename(p)) for p, _, _, _ in results), default=30)
    print("\n" + "─" * (width + 26))
    for path, verdict, elapsed, _ in results:
        print("%s%-9s%s %-*s %5.1fs"
              % (COLOR.get(verdict, ""), verdict, RESET, width,
                 os.path.basename(path), elapsed))
    print("─" * (width + 26))

    counts = {}
    for _, verdict, _, _ in results:
        counts[verdict] = counts.get(verdict, 0) + 1
    summary = "  ".join(
        "%s%d %s%s" % (COLOR.get(v, ""), counts[v], v.lower(), RESET)
        for v in (PASS, FAIL, ERROR, TIMEOUT, UNSCORED, SKIP) if v in counts
    )
    print("%s%d files%s   %s" % (BOLD, len(results), RESET, summary))

    bad = [(p, v) for p, v, _, _ in results if v in (FAIL, ERROR, TIMEOUT)]
    for path, verdict, _, out in results:
        if verdict in (FAIL, ERROR, TIMEOUT):
            print("\n%s%s %s%s" % (RED, verdict, os.path.basename(path), RESET))
            print(_tail(out))

    unscored = [os.path.basename(p) for p, v, _, _ in results if v == UNSCORED]
    if unscored:
        # Say this out loud every run: these look like tests in the directory
        # listing but cannot fail, so they must not be mistaken for coverage.
        print("\n%sUNSCORED (no assertions — cannot fail, not coverage):%s %s"
              % (YELLOW, RESET, ", ".join(unscored)))

    if bad:
        print("\n%s%sSUITE FAILED%s — %d file(s) need attention"
              % (BOLD, RED, RESET, len(bad)))
        return 1
    print("\n%s%sSUITE GREEN%s" % (BOLD, GREEN, RESET))
    return 0


# ── main ─────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Run the Super Cards test suite.")
    ap.add_argument("-k", "--filter", metavar="SUBSTR",
                    help="only run test files whose name contains SUBSTR")
    ap.add_argument("--engine-only", action="store_true",
                    help="skip the tests that need a live server")
    ap.add_argument("--socket-only", action="store_true",
                    help="only run the tests that need a live server")
    ap.add_argument("--port", type=int, default=SOCKET_PORT,
                    help="port for the test server (default %d)" % SOCKET_PORT)
    ap.add_argument("--_run-one", metavar="PATH", help=argparse.SUPPRESS)
    args = ap.parse_args()

    # Child mode: execute a single test file and exit with its verdict.
    if args._run_one:
        return run_one_inprocess(args._run_one)

    engine, sock = discover(args.filter)
    if args.engine_only:
        sock = []
    if args.socket_only:
        engine = []
    if not engine and not sock:
        print("no test files matched")
        return 1

    results = []
    server = TestServer(args.port)
    try:
        if engine:
            print("%s%s── engine tests (%d) ──%s" % (BOLD, "", len(engine), RESET))
            for path in engine:
                verdict, elapsed, out = run_file(path, ENGINE_TIMEOUT)
                print("  %s%-9s%s %s" % (COLOR.get(verdict, ""), verdict, RESET,
                                         os.path.basename(path)))
                results.append((path, verdict, elapsed, out))

        if sock:
            print("\n%s── socket tests (%d, need a live server) ──%s"
                  % (BOLD, len(sock), RESET))
            if not server.start():
                for path in sock:
                    results.append((path, ERROR, 0.0, "test server failed to start"))
            else:
                # Serial on purpose: they share one server and one room namespace.
                for path in sock:
                    verdict, elapsed, out = run_file(path, SOCKET_TIMEOUT)
                    print("  %s%-9s%s %s" % (COLOR.get(verdict, ""), verdict, RESET,
                                             os.path.basename(path)))
                    results.append((path, verdict, elapsed, out))
    except KeyboardInterrupt:
        print("\ninterrupted — tearing down")
        server.stop()
        return 130
    finally:
        server.stop()

    return report(results)


if __name__ == "__main__":
    sys.exit(main())
