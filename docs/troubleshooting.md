# Troubleshooting

## `ModuleNotFoundError: No module named 'aerolink_server'` / `aerolink_pi`

Both packages install from `src/` layouts and are not on `sys.path` by
default. Every command in this repository's docs/scripts sets
`PYTHONPATH` explicitly, e.g.:

```sh
PYTHONPATH=server/src:raspberry-pi/src python3 -m unittest discover -s server/tests -v
```

If you're running a script directly rather than through
`scripts/test-*.sh` or `server/tools/*.py` (which already set this),
you'll need the same `PYTHONPATH`.

## `make TARGET=SITL ...` fails with `bind port 57xx for UARTn failed!!`

Another process (often a leftover SITL instance from a previous
interrupted run) is still holding that port. Check for and clean up
orphans:

```sh
pgrep -af betaflight_2026 || echo "none"
pkill -f betaflight_2026   # only if you're sure nothing else is using it
```

`server/src/aerolink_server/real_sitl.py`'s `Supervisor.close()`
terminates every SITL process it started (`SIGTERM`, then `SIGKILL` on a
3 s timeout) even on failure, so this should be rare when using
`server/tools/run_real_sitl.py`; it's more likely after a manually
launched SITL binary was killed with `kill -9` from another terminal.

## The 15-node real-SITL gate (`run_real_sitl.py --nodes 15`) times out with
`TCP UART <port> did not complete readiness probe`

This is a known, pre-existing, host-load-dependent flaky readiness probe
— see [`docs/scale-test-report.md`](scale-test-report.md)'s "known flaky
gate" section. It has passed on retry every time observed. If it fails,
just retry:

```sh
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 15 --artifacts /tmp/aerolink-retry
```

If it fails repeatedly (not just occasionally) on your machine, check
host load (`uptime`) — 15 concurrent SITL processes is CPU-intensive —
and check `<artifacts>/node-XX/sitl.log` for the failing node: it should
show `[AEROLINK] ready vehicle=N ...`; if that line never appears, the
SITL binary itself failed to start (a real bug, not the known flaky
probe) and the fix belongs in `flight-controller/`, not this doc.

## `AEROLINK_SITL=1` build succeeds but the runtime endpoint never goes ready

Two independent gates must both be satisfied — a compile-time one
(`AEROLINK_SITL=1` when building) and a runtime one
(`--aerolink-vehicle <id>` when launching the binary). Confirm both:

```sh
cd flight-controller && make TARGET=SITL AEROLINK_SITL=1 AUTOHYDRATE_SUBMODULES= BETAFLIGHT_CONFIG=src/config
./obj/betaflight_2026.6.1_SITL --instance 0 --aerolink-vehicle 1
```

Without `AEROLINK_SITL=1` at compile time, `io/aerolink.c`/`aerolink_sitl.c`
aren't even built into the binary (see `flight-controller/src/platform/SIMULATOR/target/SITL/target.mk`)
— see [`docs/limitations.md`](limitations.md) for why this is
intentional and should not be relaxed.

## A test that spawns a background thread/process hangs or leaves an orphan

`SimulationHttpServer.stop()` calls `shutdown()`, `server_close()`, then
joins its thread — don't call it twice on the same instance (the second
`server_close()` can raise on an already-closed socket); see
`server/tests/test_reliability.py::test_graceful_shutdown_frees_the_port_for_a_new_server`
for the pattern of stopping one instance before starting a replacement on
the same port. For a real-SITL run, `Supervisor.close()` (called in
`run_real_sitl.py`'s `finally` block) is the corresponding cleanup —
always let it run rather than `Ctrl-C`-ing mid-test if you can help it.

## `make` reports a `fnm_multishells` / Node.js symlink error before the real build error

This is a shell-integration side effect of an unrelated Node version
manager (`fnm`) in some sandboxed environments, not a Betaflight or
AEROLINK build problem — it appears as a warning line before the actual
`make` output and does not affect the build. Look at the `Error N`
line(s) after it, if any, for the real failure.

## `security_scan.py` fails with "potential secret"

It matched an `api_key`/`password`/`private_key`/`secret` literal
assignment whose value doesn't contain `test`/`redacted`/`configured`.
If it's a genuine test fixture, name the value so it's obviously one
(e.g. include `test` in it, as `server/tests/test_http_api.py`'s
`"wrong-key-00000000000000000000000"` fixture does implicitly by context
— prefer an explicit `test`/`fixture` substring for new fixtures). If
it's a real secret, it does not belong in the repository at all — see
`docs/security-review.md`.
