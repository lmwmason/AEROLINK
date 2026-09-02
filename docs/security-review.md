# Security review

Software-only review of `server/src/aerolink_server/security.py` and its
integration in `http_api.py`, `real_sitl.py`, and
`raspberry-pi/src/aerolink_pi/vehicle_process.py`. Threat coverage and
residual limitations are tracked in [`docs/threat-model.md`](threat-model.md);
this document is the reviewer's verdict on what is and is not covered by
tests, not a restatement of the threat table.

## Scope

In scope: application-layer authentication/authorization between a Pi
node and the central server over the private LAN, the operator HTTP API,
audit-log integrity, secret handling, and dependency/SBOM evidence. Out
of scope (see [`docs/limitations.md`](limitations.md)): physical LAN
security, Pi/OS hardening, a production identity provider, and anything
below the application layer (this is a MAC over the request, not
transport encryption — deploy it behind TLS/a genuinely isolated LAN, not
as a substitute for one).

## What was reviewed and is test-covered

- **Mutual node/server authentication.** Every node request carries an
  HMAC-SHA256 signature over `method\npath\ntimestamp\nnonce\nsha256(body)`
  (`sign_message`/`node_headers`); the server verifies it against the
  node's current or immediately-previous key (`SecurityContext.verify_node`)
  and signs its own response back to the node
  (`response_headers`/`verify_server_response`), so a node also
  authenticates the server. Covered by
  `test_security.py::test_mutual_signature_replay_identity_and_rotation`
  and exercised end-to-end by the real 1/3/15-node SITL harness.
- **Replay protection.** A per-node nonce cache with expiry rejects a
  replayed request even with a valid signature (same test); a
  `X-AEROLINK-Time` more than 30 s from the server's wall clock is
  rejected regardless of signature validity.
- **Key rotation.** `rotate_node_key` keeps exactly one previous key
  valid during rollover so an in-flight request signed with the old key
  is not spuriously rejected; covered by the same test.
- **Rate limiting and request-size limits.** A token-bucket per node
  (`rate`/`burst`) and a 16 KiB (`MAX_HTTP_BODY`) request-size cap are
  both covered by
  `test_security.py::test_roles_expiry_rate_size_secret_and_redaction`.
- **Operator roles and session expiration.** `viewer`/`operator`/`admin`
  is a strict allow-list (`ROLE_PERMISSIONS`); a session past its TTL is
  rejected even for a permission it previously held. Covered by the same
  test and, at the HTTP layer, by
  `test_http_api.py::test_mission_authorize_abort_workflow_and_node_detail`
  and `test_maintenance_requires_admin_role_and_blocks_allocation` (a
  `viewer` session is rejected with 403 for `authorize`/`maintenance`).
- **Secure secret loading.** `load_secret` refuses a key file with group/
  world permission bits set and a key under 32 bytes; only an environment
  variable or such a file is accepted — no default, no hardcoded
  fallback. Covered by
  `test_security.py::test_roles_expiry_rate_size_secret_and_redaction`.
  `scripts/security_scan.py` (part of the fast profile) additionally
  scans every tracked and untracked-but-not-ignored file for an
  `api_key`/`password`/`private_key`/`secret` literal assignment and
  fails the build if one is found outside an obvious test/placeholder
  value.
- **Log redaction.** `redact()` replaces any dict value whose key matches
  `authorization`/`credential`/`key`/`secret`/`signature`/`token`
  (case-insensitively, recursively) before it reaches an audit entry or
  the diagnostics bundle. Covered by
  `test_security.py`'s redaction assertion and
  `test_ai.py::test_context_and_output_are_redacted_in_audit`.
- **Audit-log integrity chaining.** Every `AuditLog.append` links to the
  SHA-256 hash of the previous entry; `verify()` walks the full chain and
  detects a single mutated character. Covered by
  `test_security.py::test_audit_chain_detects_tampering` and, at scale,
  by `test_reliability.py::test_repeated_restart_reconciliation_cycles`
  and `test_storage.py::test_restart_reconciliation_cannot_resume_old_mission_or_epoch`
  (chain survives reload from SQLite across restarts).
- **Dependency/SBOM evidence.** `scripts/security_scan.py` also emits a
  reproducible `evidence/sbom.spdx.json` (SPDX 2.3) and
  `evidence/dependency-scan.json`. There are zero third-party Python
  runtime dependencies (`server/pyproject.toml`, `raspberry-pi/pyproject.toml`);
  the dependency-scan evidence records this and is explicit that no
  offline vulnerability database is vendored, so an empty
  `known_vulnerabilities` list is not proof of absence.
- **Concurrency correctness.** `test_reliability.py::test_concurrent_delivery_requests_never_double_assign_a_vehicle`
  is a security-adjacent correctness property: a race in
  `FleetServer.create_mission` could otherwise let two authenticated,
  authorized requests double-assign the same vehicle (fixed in the same
  pass — see [`docs/scale-test-report.md`](scale-test-report.md)).

## What is not proven by this review

- No penetration test or independent code audit has been performed;
  this is the author's own review plus the automated tests listed above.
- The forbidden-token/redaction lists are reviewable allow/deny lists,
  not a formal proof of completeness — see the equivalent caveat in
  [`docs/ai-safety-boundary.md`](ai-safety-boundary.md).
- `scripts/security_scan.py`'s secret pattern is a regex heuristic; it
  will not find a secret that does not match `key/secret/password/
  private_key <op> "..."` (e.g. one split across variables or encoded).
- There is no rate limiting or authentication on `/api/stream` beyond the
  same operator-session check as every other read endpoint — an
  authorized-but-malicious client can still hold many concurrent SSE
  connections; `test_reliability.py`'s slow-client test only shows one
  such connection does not block others, not that the server is immune
  to a deliberate connection-exhaustion attempt.
- Provisioning (how a real node first receives its key) remains `TBD`,
  as recorded in `docs/threat-model.md`.
