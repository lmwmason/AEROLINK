# Continuous integration

CI is offline at test runtime and exercises only the non-actuating software
boundary. Pull requests run fast validation and the feature-off/on builds plus
real 1/3-node SITL tests. The 15-node job is scheduled weekly to keep ordinary
reviews responsive. Every job has a hard timeout and uploads `artifacts/`,
including `test-report.json` and one combined-output log per case, even after a
failure. Betaflight build objects are cached by source hash.

Local equivalents are `scripts/test-fast.sh`, `scripts/test-all.sh`, and
`scripts/test-15-node.sh`. Pass `--artifacts PATH` to place evidence elsewhere.
The runner stops at the first failure, retains all preceding logs, and returns
nonzero. Repository validation checks Python and shell syntax, JSON parsing,
relative documentation links, and the explicit flight/actuator include ban in
the SITL endpoint. The fast profile also runs `scripts/security_scan.py`,
which fails on a likely committed secret and writes a reproducible
`evidence/sbom.spdx.json` and `evidence/dependency-scan.json` (uploaded
alongside `artifacts/`).

CI never flashes firmware, selects hardware pins, drives an actuator, or
connects AEROLINK setpoints to Betaflight control code.
