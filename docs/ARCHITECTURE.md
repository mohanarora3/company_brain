# Architecture

Last Day answers one question: *if this person leaves, what does the company stop knowing, and what do we
do about it before their last day?* This page explains how the agents get there, with the thresholds and
formulas they use, so you can argue with them.

## The shape of a run

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant C as Cartographer
    participant R as Resolver
    participant P as Planner
    participant I as Investigators
    participant A as Analyst
    participant K as Critic
    participant X as Risk officer
    participant S as Successor scout
    participant M as Archivist (Meterless)
    participant W as Writer
    O->>C: read the Zetaris catalog, profile tables, build the source map
    O->>R: link accounts to HR employees (federated joins)
    O->>M: connect; read earlier exit-interview answers and handovers
    P->>I: round 1: footprint of the leaver in every source
    P->>I: round 2: ownership from systems of record (code, reviews, Jira)
    I->>A: evidence
    A->>K: provisional labels
    K-->>P: requests: corroborate, identity, retry_source, tacit
    loop until the Critic raises nothing new (max 6 rounds)
        P->>I: conversation, incidents, docs probes for the areas in question
        P->>R: disambiguate accounts by co-activity
        P->>I: retry a failed source, or drop it and lower confidence
        P->>I: extract the tacit answers
        I->>A: more evidence
        A->>K: corroborated labels
        K-->>P: new requests, or none
    end
    O->>X: priority, deadlines, escalation (keeps exclusive access critical)
    O->>S: successor per area, with reasons
    O->>M: memory + World Model writes, conflict detection
    O->>W: handover plan + exit interview
    W->>K: every citation checked against the blackboard
```

Agents never call each other. They read and write a shared **blackboard** (`lastday/agents/blackboard.py`):
evidence, areas, requests, findings, escalations, the query log and the event trace. The orchestrator
(`orchestrator.py`) decides who acts next from the open requests. That makes every interaction visible: a
request has an id, an author, a reason and a status, and the UI's Evidence tab lists them all.

## Federation: one contract, two engines

`lastday/federation/base.py` defines what an engine must do: `status`, `catalog`, and a governed,
read-only `query`. Two engines implement it.

- **Zetaris** (`zetaris.py`): Lightning SQL over the HTTP API, on either the direct REST route
  (`{ZETARIS_REST_URL}/sql-editor/sqls/run`) or the UI proxy (`/api/proxy/sql-editor/sqls/run-query`). Every call
  sends the GUI-created API key as a bearer token, the numeric `X-Org-ID` and a fresh UUID `X-Request-ID`.
  Zetaris returns values as strings and sometimes rows without headers, so numeric columns are coerced and
  columns are named from the query's own `AS` aliases when needed. Transient 502/503/504 responses are retried.
- **Local snapshot** (`local.py`): SQLite in memory, one attached database per source, so
  `slack.messages` and `hr_pg.departures` are valid names and cross-source joins behave the same way. It
  loads the same JSON the mock SaaS APIs serve to Zetaris.

One manifest (`manifest.py`) describes every table: its source, REST endpoint, JSON root and typed columns.
It drives the Zetaris registration SQL, the local loader and the column fallback, so they cannot drift (a
test regenerates the committed templates and compares).

### How the sources look in Zetaris

| Source | Registered as | Agents query |
|---|---|---|
| HR (Postgres) | `CREATE DATASOURCE hr_pg` (JDBC); `REGISTER DATASOURCE TABLES ("departures", "access_grants")`; `CREATE DATASOURCE VIEW employees_directory` without the sensitive columns | `hr_pg.employees_directory`, `hr_pg.departures`, `hr_pg.access_grants` |
| Slack, Jira, GitHub, wiki, PagerDuty | `CREATE LIGHTNING DATABASE <src>_api`; one `CREATE LIGHTNING REST TABLE <t>_raw` per API endpoint; `CREATE SCHEMASTORE CONTAINER <src>`; one `CREATE OR REPLACE SCHEMASTORE VIEW <t>` that explodes the JSON array into columns | `slack.messages`, `jira.issues`, `github.commits`, `docs.pages`, `pagerduty.incidents`, ... |

The raw `employees` table, which holds salary band, personal email, home city and performance rating, is
never registered.

### Governance

Before any engine sees a statement, `governance.py` checks it:

- only `SELECT`, `WITH`, `SHOW` and `DESCRIBE`; no write keywords outside string literals;
- no `hr_pg.employees`, and none of the four sensitive columns, anywhere in the statement.

A blocked query is logged as `blocked` in the trace. With Zetaris this is the second layer; the first is that
the raw table is not registered at all.

## The agents

### Cartographer

Reads the catalog (`SHOW LIGHTNING DATABASES`, `SHOW LIGHTNING TABLES`, `SHOW DATASOURCES`,
`DESCRIBE DATASOURCE TABLE` on Zetaris), profiles each table (rows, time span) and classifies every column by
role: person reference, timestamp, link to a service, free text, name, email. From the roles it decides which
probes are possible. Any table with a person column, a time column and a column whose values are service
catalog ids becomes a generic **activity** source. That is how PagerDuty is discovered when you register it
mid-demo, with no code change.

### Resolver

Links accounts to HR employees in three passes:

1. **Federated joins on email**, one cross-source query each: HR × Slack, HR × Jira, HR × PagerDuty, HR ×
   GitHub commit author emails. Confidence 0.97 to 0.99.
2. **Names and handles** for the rest, with Jaro-Winkler similarity and a confidence score.
3. **Ambiguous accounts** (two candidates, e.g. Rahul Verma and Rahul Varma both appear as "Rahul V") stay
   unassigned. When the Critic asks, the Resolver compares the systems the account works on with each
   candidate's team and their other accounts' systems, and decides only if one candidate clearly wins.

### Investigators

Small sets of read-only queries; every Evidence row keeps the id of the query that produced it.

| Probe | Reads | Evidence weight |
|---|---|---|
| footprint | the leaver's activity in every source | (planning only) |
| code | commits joined to files and the service catalog's repo paths | 1.0 per commit |
| reviews | pull-request reviewers per base path | 0.6 |
| work | Jira issues per component and assignee | 1.2 done, 0.5 open |
| conversation | Slack thread replies, attributed to systems from the thread text (keywords, then NIM embeddings) | 2.0 per answer |
| activity | any discovered table (PagerDuty incidents) | 1.5 |
| docs | wiki pages per system: age, author still here? | doc coverage |
| access | privileged access only the leaver holds | exclusive flag |
| chores | recurring Jira tickets and whether they stop when the owner leaves | 1.5 |

Weights decay with a 240-day half-life, so a person who stopped touching a system a year ago is not its expert.

### Analyst

For each candidate area: the leaver's **share** of evidence-weighted knowledge, the **best backup** (the
strongest remaining active person) and which sources the numbers rest on. People who already left count
toward nothing; unattributed accounts count toward the total, which is why unresolved identities matter.

| Label | Rule |
|---|---|
| critical | share ≥ 0.55 and best backup < 0.25, or exclusive access with share ≥ 0.30, or exclusive access to a system they barely touch |
| at risk | share ≥ 0.35, or no backup ≥ 0.25 and share ≥ 0.25 |
| covered | otherwise |

### Critic

Six written rules (`critic.py`):

1. **Systems-of-record bias.** A critical or at-risk label built on commits and tickets alone, or an area
   where 35% or more of the leaver's footprint is conversation, needs corroboration before anyone acts on it.
2. **Unresolved identities.** If more than 5% of an area's activity comes from unattributed accounts, ask the
   Resolver to disambiguate.
3. **Missing sources.** If a source failed, ask for one retry; if it fails again, accept with lower confidence
   and say which evidence is missing.
4. **Critical areas need the knowledge, not just the number.** Ask for the tacit answers before the handover is
   written.
5. **Explain changes.** When a label moves between passes, record why (which source showed the backups).
6. **Every claim cites evidence that exists.** Checked on the Writer's output; sections without citations fall
   back to the template text.

### Risk officer

Priority = label weight × tier weight × urgency, plus bonuses for chores that stop and keys nobody else holds,
minus a little for good documentation. Urgency is 1.0 with 14 days or fewer left, 0.85 within 30 days, 0.7
otherwise. It escalates critical tier-1 or exclusive-access areas with 21 days or fewer left, with concrete
actions for this week. It also flags gaps that existed before this departure (chores nobody has owned for
months). One rule lets it overrule the Critic: if a knowledge-based "covered" label hides access only the
leaver holds, the area goes back to critical, because a key cannot be shared the way knowledge can.

### Successor scout

Score = 0.55 × direct knowledge of the area + 0.20 × owning team or neighbouring systems + 0.12 × how often
the leaver answered their questions about it + 0.13 × headroom (fewer open tickets). Every recommendation
lists its reasons with numbers.

### Archivist (Meterless)

See [Sponsor technology](SPONSOR_TECH.md#meterless) for the engines. Per run it:

- writes people, their accounts (`identity_of` edges with the match method), systems, `knows` edges with
  shares and `owned_by` edges for at-risk areas to the **World Model**;
- stores the tacit answers (with Slack provenance) and the wiki sentences for the same systems in **H-MEM**,
  then runs H-MEM's conflict detection. Numeric claims are normalised ("monthly" becomes "every 30 days") so
  "silence it for 24 hours" and "silence it for 6 hours" compare as conflicting values. The conflicting fact is
  asserted to the World Model with its source, and its source-priority policy (interview > Slack > Jira >
  PagerDuty > GitHub > docs) decides which value stands;
- at the start of the next run, reads earlier exit-interview answers back. Each answer counts as written
  knowledge: the leaver's share falls (`written = min(0.6, 0.15 × answers)`) and a "written down" backup
  appears, so the label can drop from critical to at risk to covered;
- reads accepted handovers from the World Model (`owned_by` now pointing at the successor; the old edge is
  closed with `validTo`, not deleted) and lowers those areas' priority.

### Writer

Builds the handover plan and the exit interview from the blackboard, area by area, with citations. With an
LLM configured it rewrites the summaries for readability; the Critic then checks the citations survived and
falls back to the template text if not. Interview questions are built from evidence: "You answered 12 questions
about Zenith Retail in #cs-escalations this year; everyone else combined answered 4...", a quoted Slack answer
with a number in it, a wiki page that contradicts them, a chore that stops, a key only they hold.

## Ask (for the successor)

`agents/ask.py`: H-MEM retrieval (hybrid ranking with a trace) plus a live federated search of Slack answers
and wiki pages about the system the question names, ranked with NIM embeddings. The answer cites both. Without
an LLM it quotes the best-ranked evidence, preferring an exit-interview answer about the same system.

## Failure handling

- **A source fails** (try *Simulate outage* in the Sources dialog, or `python -m lastday run Priya --fail jira`):
  the query is retried once; then the source is marked failed, the Critic asks for one more retry in the next
  round, and if it still fails the run continues on the other sources with confidence lowered and the gap stated.
  Only the source named in the error is blamed, not every source in a join.
- **Meterless bridge down:** the run continues without memory and says so in the trace.
- **LLM down or no key:** template wording. After three failed calls the LLM is switched off for the process.
- **A request nobody can serve** (no source behind the probe) is dropped with a reason, so the loop always ends.

## Reproducibility

`python -m lastday generate --seed N` builds a company deterministically (same seed, same files, byte for
byte, apart from the timestamp in `meta.json`). Every run saves `run.json` (the whole blackboard),
`events.jsonl` (the trace), `handover.md` and `interview.md` under `.lastday/runs/<id>/`, and the UI can reopen
and replay any of them.
