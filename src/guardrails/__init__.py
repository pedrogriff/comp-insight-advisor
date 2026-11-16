"""Guardrails, monitoring and the human approval gate for Checkpoint 6.1.

The package wraps the Checkpoint 5.1 squad without changing how it reasons:

- input_guard screens a request before any agent or tool runs.
- output_guard adds checks on a verified brief that the figure verifier lacks.
- monitor reads a finished run's trace and flags behavior outside its limits.
- integrity confirms the playbook matches its recorded hash.
- approval scores a brief's risk, routes it and records the human decision.
- audit writes a hash-chained JSONL log of every step.
- pipeline ties them together as GuardedAdvisor.
- evaluate scores all of it on frozen cases.
"""
