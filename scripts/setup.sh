#!/bin/sh
# One-command local dev setup. No third-party Python packages are
# required (see server/pyproject.toml, raspberry-pi/pyproject.toml); this
# only checks the toolchain, makes scripts executable, and generates
# test-only local credentials.
set -eu
cd "$(dirname "$0")/.."

python3 - <<'EOF'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11+ required, found {sys.version}")
print(f"python3 {sys.version.split()[0]} OK")
EOF

chmod +x scripts/*.sh scripts/*.py flight-controller/src/test/run_aerolink_native.sh 2>/dev/null || true

if command -v cc >/dev/null 2>&1; then
  echo "cc ($(cc --version | head -1)) OK — needed for the FC native tests and TARGET=SITL builds"
else
  echo "WARNING: no 'cc' found; flight-controller native tests and SITL builds will fail" >&2
fi

python3 scripts/generate_dev_credentials.py >/dev/null 2>&1 || true

cat <<'MSG'

Setup complete. Next steps:
  scripts/test-fast.sh                 # unit/protocol/state/security tests, ~seconds
  scripts/test-all.sh                  # + feature-off/on SITL builds and real 1/3-node runs
  scripts/test-15-node.sh              # + the 15-node real-SITL gate and reliability soak
  cp config/dev.env.example config/dev.env   # then edit; config/dev.env is git-ignored

See docs/api-examples.md for example requests against the simulation
server, and README.md / AGENT.md / PRD.md before touching the control
path.
MSG
