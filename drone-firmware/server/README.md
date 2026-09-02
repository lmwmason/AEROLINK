# AEROLINK central server

This primary implementation folder is reserved for the offline fleet registry,
deterministic allocator/planner, advisory-AI adapter, operator API/dashboard,
and audit/replay tooling. Those components begin after the UART protocol gate.

The MVP server is the only coordinator; automatic server election and any
internet service are out of scope. AI output will be schema-constrained,
advisory, deterministically validated, operator-audited, and unable to arm or
issue setpoint, motor, or payload commands.
