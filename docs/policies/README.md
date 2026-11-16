# Synthetic Policy Corpus

Stores the synthetic compensation policy that the agent retrieves from in checkpoint 3.1. Section 6 of the playbook maps each loss driver to the lever that addresses it, and `tests/test_intervention_fit.py` checks that the table matches `src/tools/intervention_fit.py`.

`src/retrieval/policy_search.py` cuts the playbook into one chunk per rule and tags each chunk with the levers it governs and the population it covers. The tags live in `SECTION_TAGS`. A new section needs an entry there, or its chunks come out tagged `untagged` and `tests/test_policy_retrieval.py` fails. If a limit changes here and not in the code, `check_limits` reports a policy conflict, and the brief stops costing a rule the policy no longer states.

`playbook_manifest.json` stores the normalized SHA-256 digest of `compensation_governance_playbook.md`. `src/guardrails/integrity.py` verifies this digest before every `GuardedAdvisor` run and holds execution on any mismatch until a reviewed change updates the manifest via `python3 -m src.guardrails.integrity --update`.
