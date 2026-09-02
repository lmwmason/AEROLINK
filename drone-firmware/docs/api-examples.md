# API examples

Simulation-only. Every example below talks to a loopback
`SimulationHttpServer` backed by a `FleetServer` that has no connection
to real hardware. Full endpoint reference:
[`docs/openapi.yaml`](openapi.yaml).

## Start a local server

```python
# scripts/dev_server.py-style snippet — run with:
#   PYTHONPATH=server/src:raspberry-pi/src python3 -c "..."
import secrets
from aerolink_server.core import FleetServer
from aerolink_server.http_api import SimulationHttpServer
from aerolink_server.security import SecurityContext

node_keys = {1: secrets.token_bytes(32)}          # or load from dev-credentials/nodes.json
security = SecurityContext(node_keys)
admin_token = security.create_operator_session("admin", ttl_seconds=3600)
fleet = FleetServer()
server = SimulationHttpServer(fleet, security, admin_token)
server.start()
print(f"listening on 127.0.0.1:{server.port}, admin token: {admin_token}")
```

Or use the same setup `server/tools/run_real_sitl.py` builds, against a
real Betaflight SITL binary (built with
`make TARGET=SITL AEROLINK_SITL=1 AUTOHYDRATE_SUBMODULES= BETAFLIGHT_CONFIG=src/config`
in `flight-controller/`):

```sh
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 1 --artifacts /tmp/aerolink-demo
```

## Operator: read the dashboard

```sh
curl -s "http://127.0.0.1:$PORT/api/fleet" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool
```

## Operator: create, authorize, and complete a mission

```sh
curl -s -X POST "http://127.0.0.1:$PORT/api/missions" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"count": 3}'
# -> {"mission_id": "mission-1", "state": "PLANNED", "vehicles": [1, 2, 3]}

curl -s -X POST "http://127.0.0.1:$PORT/api/missions/mission-1/authorize" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"operator": "alice"}'
# -> {"mission_id": "mission-1", "state": "AUTHORIZED"}

curl -s -X POST "http://127.0.0.1:$PORT/api/missions/mission-1/complete" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# -> {"mission_id": "mission-1", "state": "COMPLETED"}
```

Aborting instead of completing is a two-step, explicit workflow —
`.../abort-request` then `.../abort-confirm` — so a mission is never
silently finalized:

```sh
curl -s -X POST "http://127.0.0.1:$PORT/api/missions/mission-1/abort-request" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"operator": "alice"}'
curl -s -X POST "http://127.0.0.1:$PORT/api/missions/mission-1/abort-confirm" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"operator": "alice"}'
```

## Operator: maintenance (admin role only)

```sh
curl -s -X POST "http://127.0.0.1:$PORT/api/vehicles/5/maintenance" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"operator": "alice", "note": "battery swap"}'
# a viewer-role token here gets 403, not silent no-op
curl -s -X POST "http://127.0.0.1:$PORT/api/vehicles/5/maintenance" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -d '{"operator": "alice", "action": "clear"}'
```

## Advisory AI (read-only; never allocates or creates a mission)

```sh
curl -s -X POST "http://127.0.0.1:$PORT/api/ai/fleet-size" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"estimated_kg": 2.5}'
# -> {"valid": true, "model": "deterministic-fake", "version": "1", "confidence": 1.0, "output": {"count": 3}}
```

The recommended `count` still has to be passed through
`POST /api/missions`, which independently re-validates it — see
[`docs/ai-safety-boundary.md`](ai-safety-boundary.md).

## Observability

```sh
curl -s "http://127.0.0.1:$PORT/api/metrics" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s "http://127.0.0.1:$PORT/api/audit/export" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -sN "http://127.0.0.1:$PORT/api/stream?token=$ADMIN_TOKEN"   # Server-Sent Events
```

## Node registration/telemetry (HMAC-signed, not a bearer token)

A node request is signed, not bearer-authenticated — see
`aerolink_server.security.node_headers` and
`raspberry-pi/src/aerolink_pi/vehicle_process.py` for a real client. A
minimal Python example:

```python
import json
from aerolink_server.security import node_headers
import urllib.request

body = json.dumps({"vehicle_id": 1, "session": 1, "health": "online"}, separators=(",", ":"), sort_keys=True).encode()
headers = {"Content-Type": "application/json", **node_headers(1, node_key, "POST", "/api/telemetry", body)}
urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/api/telemetry", data=body, headers=headers))
```
