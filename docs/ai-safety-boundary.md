# AI safety boundary

This describes `server/src/aerolink_server/ai.py` and how it is wired into
`FleetServer` (`server/src/aerolink_server/core.py`). It is software-only
evidence; see [`docs/limitations.md`](limitations.md).

## Rule

AI proposes; it never executes. Per AGENT.md and PRD SV-4, an AI proposal
may only: interpret a delivery request, recommend a fleet size, rank route
alternatives, summarize anomalies, explain a maintenance flag, or write an
operator-facing mission summary. It cannot arm, set a setpoint, control a
payload, disable a safety check, or override a deterministic rejection.

## How the boundary is enforced

1. **Strict per-task schema.** `SCHEMAS` in `ai.py` fixes the required
   fields and types for each of the six allowed tasks. Anything else —
   missing fields, wrong types, an unrecognized task name — fails
   `validate_schema` and is rejected before it reaches `FleetServer`.
2. **Forbidden-token scan.** Every string value in a proposal's output
   (recursively, including free text the model may have echoed back from
   user input such as a parcel name) is scanned as whole words against
   `FORBIDDEN_TOKENS` (`arm`, `disarm`, `motor`, `throttle`,
   `payload_activate`, `setpoint`, `override_safety`,
   `bypass_validation`). A match rejects the proposal outright, which is
   also how a hidden instruction smuggled into free-text input (prompt
   injection) is caught if it makes it into the output.
3. **Domain rules beyond the schema.** `AdvisoryValidator.validate` also
   checks task-specific bounds: `fleet_size.count` must be `1..15`,
   `maintenance_explanation.vehicle_id` must be a real fleet id (when the
   caller passes `valid_vehicle_ids`), `mission_summary.mission_id` and
   `route_ranking` waypoints must reference missions/locations the server
   actually knows about (when the caller passes `known_missions` /
   `known_locations`) — this is what rejects a fabricated vehicle/mission
   id or a stale map reference.
4. **Deterministic fallback, never silent failure.** `AdvisoryAiService`
   runs the configured provider, validates it, and on any failure (schema
   violation, forbidden token, domain-rule violation, timeout, or a raised
   exception) retries against `DeterministicFakeProvider`. If the fallback
   also fails to validate, the caller gets `valid=False` and nothing in
   `FleetServer` changes — no default action is taken on its behalf.
5. **Timeout and cancellation.** `AiProvider.propose(task, context,
   timeout_s)` takes an explicit timeout; `DeterministicFakeProvider`
   demonstrates this with a configurable `latency_s` that reports
   `timed_out=True` past the deadline, which `AdvisoryValidator` treats as
   invalid regardless of schema shape.
6. **Provenance and audit.** Every request — valid or not — writes one
   `ai_proposal` audit entry with `request_id`, `model`, `version`,
   `prompt_version`, `confidence`, `valid`, `source` (`primary` /
   `fallback` / `rejected`), and the redacted context and output
   (`aerolink_server.security.redact`, so any field named like a secret is
   replaced before it is logged). The audit log is hash-chained
   (`AuditLog.verify()`), so the AI decision trail is tamper-evident.
7. **Advisory call sites never mutate state.** `FleetServer.advise_*`
   methods and their `/api/ai/*` HTTP endpoints (see
   [`docs/openapi.yaml`](openapi.yaml)) only return a proposal; a fleet-size
   recommendation still has to pass through `allocate()`/`create_mission()`,
   which independently re-validates the count and current fleet health.

## What is not proven here

- The deterministic fake provider is the only implemented provider. A real
  model integration would need its own adversarial evaluation before this
  boundary can be trusted against it; the schema/token/domain-rule gate is
  designed to be provider-neutral, but it has only been exercised against
  a provider that cannot itself misbehave beyond the test doubles in
  `server/tests/test_ai.py`.
- The forbidden-token scan is a coarse, reviewable safety net, not a
  general prompt-injection defense; it is deliberately whole-word (so
  "alarm" or "farming" do not false-positive) and can be evaded by any
  output that never spells a forbidden token as its own word. It is one
  layer among schema/domain-rule validation, not the sole protection.
- `server/tests/fixtures/ai_evaluator_cases.json` is a reviewed evaluator
  set exercised in CI, not an exhaustive adversarial corpus.
