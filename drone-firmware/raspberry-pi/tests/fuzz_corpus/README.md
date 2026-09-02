# UART v1 seed corpus

Each non-comment line in `seeds.hex` is one parser input encoded as hexadecimal.
The corpus is intentionally small and reviewed; deterministic property tests
expand and mutate it without network access. It contains no actuator command.
