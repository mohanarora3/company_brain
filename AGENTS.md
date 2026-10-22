# Working on Last Day (for Cursor and other coding agents)

Last Day is a multi-agent system: when someone gives notice, it finds what only they know across
Slack, Jira, GitHub, the wiki, PagerDuty and HR, argues about it until the evidence holds, and writes
a handover plan and an exit interview. Read `docs/ARCHITECTURE.md` before changing agent behaviour.

## Run things

```bash
make setup          # venv, deps, Meterless engines, demo data
make test           # 40+ tests, standard library only, ~10 s
make serve          # http://localhost:8000
python -m lastday run Priya --sql      # one investigation in the terminal, every query printed
python -m lastday eval --seeds 42 7 13 # accuracy against planted ground truth
python -m lastday doctor               # what is configured
```

Run `make test` after every change to `lastday/agents/` and `python -m lastday eval` after any change
to scoring, the Critic or the Planner. Accuracy must not drop below 0.9 and handover recall must stay 1.0.

## Rules that keep the system honest

- **Agents only talk to the blackboard.** No agent calls another. They post findings and requests on
  `Blackboard`; the orchestrator decides who acts next. Keep it that way.
- **Every query goes through `bb.sql(...)`.** That is where governance, retries, logging and the trace
  happen. Never call `fed.query` from an agent.
- **SQL uses qualified names only** (`slack.messages`, `hr_pg.employees_directory`), the same on Zetaris
  and the local snapshot. Escape values with `lit()` / `in_list()`; never format raw strings into SQL.
- **HR is governed.** Never query `hr_pg.employees`, `salary_band`, `personal_email`, `home_city` or
  `performance_rating`. `federation/governance.py` blocks it; do not weaken it.
- **Every claim cites evidence.** New handover or interview text must carry evidence ids that exist on
  the blackboard; the Critic's `check_citations` enforces it.
- **The agents never read `_ground_truth.json`.** Only `lastday/eval.py` does. A test fails otherwise.
- **The LLM is for wording, not reasoning.** Labels, scores, critique and escalation must work with no
  LLM key. LLM output is checked by the Critic and falls back to templates.
- **Secrets live in `.env`** (gitignored). `.env.example` holds placeholders only.

## Zetaris

Agents work identically on Zetaris and on the local SQLite snapshot. Registration SQL is generated from
`lastday/federation/manifest.py`; if you add a table there, regenerate the templates with
`python -m lastday zetaris sql --template` (a test checks they match). Zetaris Lightning SQL: one
statement per call, no trailing semicolon. See `docs/ZETARIS_SETUP.md`.

## Meterless

`meterless-bridge/` serves the unmodified Meterless H-MEM and World Model reference engines
(Apache-2.0, vendored at a pinned commit) to Python over a local JSON API. Do not edit `vendor/`;
change `server.ts` or `lastday/meterless/client.py` instead.
