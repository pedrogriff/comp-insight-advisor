# Synthetic Data Directory

Stores synthetic data generation scripts and generated SQLite/CSV datasets for the 2,000-employee org roster, multi-year vesting cashflows, and reactive offer/counter-offer logs.

`generate_interview_notes.py` reads the database and writes `interview_notes.jsonl`, 261 synthetic exit and stay interview notes, and `interview_retrieval_cases.json`, 10 retrieval cases labeled from note metadata. It has its own seed and never changes the database, and a rerun writes the same two files byte for byte.

`policy_retrieval_cases.json` holds 28 questions about the governance playbook, written by hand in the words a comp partner might use. Each one lists the rule chunks that answer it. The 18 tagged `dev` set the search's settings. The other 10, tagged `heldout`, came after that tuning and only ever get scored. 4 of the 28 have no answer in the playbook, so the right result is nothing, and some questions also list a `wrong_population` clause, such as the new-hire offer rule for a question about a raise.

`cross_lever_cases.json` holds 12 comparative questions that span two policy levers or two populations, such as "Compare the equity caps for new hires versus current staff", the question the Checkpoint 3.1 graders asked about. Each one lists, per side, the rule chunks that answer that side, written as `population/lever`, and an empty list where the playbook has no rule for that side, so the right result there is nothing. The 5 tagged `dev` shaped the router in `src/retrieval/cross_lever.py`. The 7 tagged `heldout` were written at the same time, before the router ran, and were scored once after its design froze.
