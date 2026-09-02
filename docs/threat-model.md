# Software-only threat model

The protected boundary is central server → authenticated private LAN → one Pi
identity → local UART session → non-actuating FC parser. Availability of the
isolated LAN and compromise resistance of the Pi operating system are assumed,
not proven. Physical safety and flight behavior are outside this model.

| Threat | Control | Residual limitation |
|---|---|---|
| Fake registration / vehicle-ID collision | Per-node HMAC key, signed identity and fixed 1–15 registry | Provisioning process is TBD |
| Packet injection / replay | Canonical-body MAC, nonce cache, sequence/epoch checks and expiry | Offline wall-clock disagreement beyond 30 s requires reconciliation |
| Server impersonation | Server signs each node response with that node's key | Application-layer MAC is not transport confidentiality |
| Dashboard privilege escalation | Expiring viewer/operator/admin sessions and permission checks | Production identity provider is TBD |
| Malicious AI output | Strict advisory schemas and deterministic validator; no executable method | Human-readable summaries remain untrusted text |
| Corrupt map or mission | Version/reference validation and immutable revision checks | Real building survey remains TBD |
| Denial of service | 16 KiB request cap, bounded parsers/queues, token-bucket rate limiting | A saturated LAN/host can still deny availability |
| Compromised Pi | Per-node isolation, FC independently validates identity/session/age/bounds | A stolen node key requires rotation and incident response |
| Clock disagreement | Bounded skew window plus nonce/sequence replay protection | No internet time is used; large skew fails closed |
| Audit tampering | SHA-256 hash chain with full-chain verification and export | External anchoring is not implemented |

Keys are loaded from environment variables or owner-only files. Repository
fixtures are visibly test-only and provide no deployment credential. Rotation
accepts an explicitly controlled previous-key overlap; there is no automatic
network key distribution.
