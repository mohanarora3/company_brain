# Sponsor technology

Every sponsor technology has a job in Last Day that the product would be worse without. This page says
what each one does, where it is in the code, and what is unusual about how we use it.

## Zetaris

**Job: the data harness.** The agents need Slack, Jira, GitHub, the wiki, PagerDuty and HR at once, joined on
people, without copying HR data anywhere. That is what Zetaris does.

- **Registration** (`lastday/federation/registration.py`, `zetaris/sql/`). HR is a JDBC datasource `hr_pg` with
  only `departures`, `access_grants` and a `CREATE DATASOURCE VIEW employees_directory` that leaves out salary
  band, personal email, home city and performance rating. Each SaaS source is a Lightning database of REST
  tables (one per API endpoint) plus a SchemaStore container of views that `LATERAL VIEW explode(...)` the JSON
  into columns. The SQL is generated from one manifest, so the Zetaris schema, the local snapshot and the agents'
  expectations cannot drift.
- **Querying** (`lastday/federation/zetaris.py`). Read-only Lightning SQL over the REST API with the bearer key,
  numeric `X-Org-ID` and a UUID `X-Request-ID` per call. Header-less rows are named from the query's own aliases;
  string values are coerced; transient errors are retried; results are cached per statement for five minutes.
- **Federated joins do the identity work.** The Resolver links accounts to employees with single cross-source
  queries, for example HR × Slack on email:
  ```sql
  SELECT e.employee_id AS employee_id, u.user_id AS account
  FROM hr_pg.employees_directory e JOIN slack.users u ON lower(e.work_email) = lower(u.email)
  ```
- **Discovery from the catalog** (`agents/cartographer.py`). The Cartographer reads `SHOW LIGHTNING DATABASES`,
  `SHOW LIGHTNING TABLES`, `SHOW DATASOURCES` and `DESCRIBE DATASOURCE TABLE`, classifies columns by role and
  decides which investigations are possible. Register PagerDuty mid-demo and the next run uses it.
- **Governance in two layers.** Zetaris never exposes the raw HR table; `federation/governance.py` additionally
  refuses any agent statement that writes or mentions a sensitive column, before it reaches Zetaris.

**What is unusual:** the agents do not get "a database". They get a catalog to explore, and they plan their
investigation from what it contains. Identity resolution, the hardest part of working across SaaS tools, is
done as federated joins inside Zetaris rather than by copying user tables into the app.

## Meterless

**Job: the memory that outlives the person.** The whole point of Last Day is to keep knowledge after someone
leaves, so the memory layer is the product, not a cache.

`meterless-bridge/` runs the **unmodified** H-MEM and World Model reference engines from
[Meterless/Meterless](https://github.com/Meterless/Meterless) (Apache-2.0, vendored at a pinned commit, the
same way the official agentathon starter vendors H-MEM) and exposes them to the Python agents over a small
local JSON API. `lastday/meterless/client.py` starts it on demand, so `python -m lastday serve` stays one
command.

**H-MEM** (tiered memory with a trust ledger):
- the tacit answers the Critic asked for, each with Slack provenance (`slack:#payments/<ts>`, "Slack answer by
  Priya Raman in #payments");
- wiki sentences for the same systems, so H-MEM's **conflict detection** catches a runbook that contradicts the
  expert ("silence it for 24 hours" vs "6 hours, never longer");
- every exit-interview answer. The next run reads them back as written knowledge, so the leaver's share drops and
  the label can move from critical to covered. One saved answer took Zenith Retail from 80% to 71% in the demo;
- the successor's questions use H-MEM's hybrid retrieval, and every memory can be opened to its trust-ledger
  history. Helpful / Wrong feedback adjusts its confidence.

**World Model** (event-sourced graph with bitemporal edges and source-priority facts):
- people, their accounts in each tool (`identity_of`, with the match method and confidence) and catalog systems;
- `knows` edges with evidence-weighted shares and `owned_by` edges for at-risk areas;
- **accepting a handover** re-points `owned_by` to the successor. The old edge is closed with `validTo`, not
  deleted, so the company can always ask who owned a system on a given date. The next run sees the accepted
  handover and lowers that area's priority;
- conflicting facts are asserted with their source, and the source-priority policy (exit interview > Slack >
  Jira > PagerDuty > GitHub > wiki) decides which value stands.

**What is unusual:** memory changes the agents' decisions, not just their wording. A saved exit-interview answer
measurably lowers risk on the next run, an accepted handover changes priorities, and a stale wiki page loses to
what the expert said, with an audit trail for each.

The LLM client also works with the Meterless Runtime (any OpenAI-compatible endpoint with `LLM_EXTRA_HEADERS`).

## NVIDIA

**Job: understanding text the systems do not link.** Most Slack threads do not say which service they are about.

- **NIM retrieval embeddings** (`nvidia/llama-3.2-nv-embedqa-1b-v2`, asymmetric query/passage embeddings,
  `lastday/llm/embeddings.py`) attribute Slack threads to catalog systems when keywords fail, rank the federated
  evidence for the successor's questions, and compare candidate successors.
- **A NIM chat model** (`LLM_MODEL`, any model on build.nvidia.com) rewrites handover summaries for managers and
  writes the successor answers with numbered citations. The Critic re-checks citations after the LLM writes and
  falls back to the template text if any are lost.
- One `NVIDIA_API_KEY` enables both. Without it, a hashed-vector fallback and templates keep everything running,
  and the UI says which is in use. The evaluation numbers in the README were measured without the LLM, so
  they show the agents' reasoning, not the model's.

## Cursor

**Job: the development environment.** The repository is set up so Cursor's agent works within the rules
that keep the system honest:

- `AGENTS.md` (read by Cursor): how to run, test and evaluate; agents only talk through the blackboard; every
  query goes through the governed `bb.sql`; every claim cites evidence; the agents never read the ground truth;
  the LLM is for wording, not reasoning.
- `.cursor/rules/lastday-agents.mdc`, `zetaris-sql.mdc` and `ui.mdc`: scoped rules for agent code, SQL that
  must run on both Zetaris and the snapshot, and the UI's design system.
- The test suite runs in about 10 seconds with no dependencies, so Cursor's agent can run it after every
  change, and `python -m lastday eval` guards accuracy.

## Space XAI

Not required. Any OpenAI-compatible model works for the wording (`LLM_BASE_URL=https://api.x.ai/v1` plus
`LLM_MODEL`), though NVIDIA NIM is the default.
