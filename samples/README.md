# Sample outputs

Real runs of the agents on generated companies, so you can read the outputs without running anything.
Regenerate with `make clean-state` and the commands below; generation and runs are deterministic per seed.

| Folder | Company (seed) | Departing | Notes |
|---|---|---|---|
| `seed-42-priya-raman/` | 42 | Priya Raman, Staff Engineer, Payments, 12 days left | The demo case: 3 critical, 2 at risk, a wiki contradiction caught by H-MEM |
| `seed-42-kenji-watanabe/` | 42 | Kenji Watanabe, Principal SRE, 37 days left | A different team and different sources |
| `seed-42-priya-jira-outage/` | 42 | Priya Raman, with Jira down | Retry, then carry on at lower confidence; labels still hold |
| `seed-7-nisha-kapoor/` | 7 | Nisha Kapoor | A different company from the same generator |
| `seed-13-grace-mensah/` | 13 | Grace Mensah, Account Manager | A customer-facing role: knowledge lives in conversation |
| `eval.json` | 42, 7, 13, 21, 5, 77, 99 | every departure | Labels against planted ground truth |

Each run folder has:

- `handover.md`: the handover plan, with citations;
- `interview.md`: the exit-interview questions, with the evidence behind each;
- `run.json`: the whole blackboard (areas and their verdict history, requests between agents, every federated
  query with its SQL, timing and row count, evidence, identities, memory writes);
- `events.jsonl`: the trace, one event per line, in the order the agents acted.

```bash
python -m lastday run Priya --out samples/seed-42-priya-raman
python -m lastday run Kenji --out samples/seed-42-kenji-watanabe
python -m lastday run Priya --no-memory --fail jira --out samples/seed-42-priya-jira-outage
python -m lastday --seed 7 run E1015 --out samples/seed-7-nisha-kapoor
python -m lastday --seed 13 run E1014 --out samples/seed-13-grace-mensah
python -m lastday eval --seeds 42 7 13 21 5 77 99 --out samples/eval.json
```
