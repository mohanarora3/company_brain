# Submission kit (HackOS)

Deadline: **27 October 2026, 23:45 UTC** (28 October, 05:15 IST). Draft answers for the form are below.
Edit anything that is not true for your team before you paste it.

## Basics

- **Project name:** Last Day
- **Tagline:** Know what your company forgets before someone leaves.
- **Track:** Solving Fragmented Intelligence (Track 1). Alternative fit: The Agent That Can Explain Why (Track 2).
- **Repository:** `https://github.com/<you>/last-day` (public, with README, `.env.example`, no secrets)
- **Demo video:** (1 to 4 minutes, see `docs/DEMO_SCRIPT.md`)

## Short description (about 50 words)

When someone gives notice, Last Day's agents investigate what only they know across Slack, Jira, GitHub, the
wiki, PagerDuty and HR, queried in place through Zetaris. A Critic challenges every label until the evidence
holds. The output is a cited handover plan and exit interview, and answers saved in Meterless memory lower the
risk on the next run.

## Problem and target users

Engineering and operations managers get two to four weeks between a resignation and a last day. In that time
they have to find what only the leaving person knows: the reasons behind odd settings, recurring chores nobody
else runs, keys nobody else holds, customers who only call them. That knowledge is fragmented across five or
more tools that disagree about who everyone is, and HR data cannot be copied into another tool. Most companies
find out what they lost after the person has gone.

## Solution

A team of ten agents on a shared blackboard. The Cartographer discovers sources from the Zetaris catalog, the
Resolver links each person's accounts with federated joins, Investigators query each source, the Analyst
scores each knowledge area, and the Critic refuses labels built on thin or one-sided evidence and sends work
back through the Planner. The Risk officer prioritises by tier and deadline and escalates, the Successor scout
recommends who takes over and why, the Archivist keeps everything in Meterless H-MEM and the World Model, and
the Writer produces the handover plan and the exit interview, with every claim cited.

## Agent workflow (why it is not a pipeline)

- The Critic posts requests (corroborate, identity, retry a source, extract tacit knowledge); the Planner
  delegates them to Investigators or the Resolver in the next round; rounds repeat until the Critic raises
  nothing new (at most 6).
- Labels change between rounds with written reasons (a commit-heavy "critical" becomes "at risk" once Slack
  shows a real backup).
- The Risk officer can overrule the Critic when a covered area hides access nobody else holds.
- Failed sources are retried once, then worked around with lower confidence, and the gap is stated.
- The Writer's output goes back to the Critic, which checks every citation against the blackboard.
- Memory written in one run (exit-interview answers, accepted handovers) changes the next run's labels and
  priorities.

## Technical stack

Python 3.10+ (standard library plus Starlette and Uvicorn), Zetaris Lightning SQL over the REST API, a Node 22
bridge serving the Meterless H-MEM and World Model reference engines, NVIDIA NIM (chat and nv-embedqa
embeddings), and a vanilla JS UI with server-sent events. Custom agent framework: a blackboard and orchestrator
in about 250 lines, because the feedback loops are the product.

## Sponsor technology explanation

**Zetaris.** The data harness for all six systems. SaaS APIs are Lightning REST tables flattened by
SchemaStore views; HR is a JDBC datasource where only a governed view without compensation or personal data is
registered. Agents explore the catalog to plan, resolve identities with cross-source joins (HR × Slack × Jira ×
GitHub) inside Zetaris, and send only read-only, governance-checked Lightning SQL. Registering a new source
(PagerDuty) is picked up on the next run with no code change.

**Meterless.** The memory that outlives the person. The unmodified H-MEM and World Model reference engines run
in a local bridge. H-MEM holds tacit knowledge and exit-interview answers with provenance and trust-ledger
history, and its conflict detection catches stale runbooks that contradict the expert. The World Model holds
people, accounts and systems with bitemporal ownership: accepting a handover closes the old `owned_by` edge
rather than deleting it. Saved answers and accepted handovers change the next run's risk labels.

**Cursor.** The development environment. `AGENTS.md` and `.cursor/rules/` hold the project rules (blackboard
only, governed SQL, cited claims, no ground-truth access), and the 10-second test suite and evaluation command
let Cursor's agent check its own changes. *Before submitting, add one or two sentences on what you built with
Cursor during the week.*

**NVIDIA.** NIM retrieval embeddings attribute Slack threads to systems and rank evidence for successor
questions; a NIM chat model writes the manager-facing summaries and answers, re-checked by the Critic.

**What is unique.** The agents do not get a database, they get a catalog to explore. Identity resolution runs
as federated joins in Zetaris rather than copying user tables. And memory changes decisions, not just wording:
one saved exit-interview answer measurably lowers the risk on the next run, with an audit trail.

## Evidence it works

- 7 generated companies, 57 scored areas: 96.5% label accuracy, 97.1% handover precision, 100% recall, 5 of 5
  planted decoys caught (`make eval`, `samples/eval.json`).
- 43 automated tests, including outages, discovery, governance, memory and the HTTP API (`make test`).
- `samples/`: handover plans, exit interviews, full blackboards and event traces for five runs across three
  companies, one with Jira down.

## Pre-existing components (declare in the form)

All code in this repository was written during the build window. Reused from before:
1. The fictional company's story (Acme Pay, its characters and about a dozen scenario sentences in
   `lastday/data/storylines.py`) from our Graph Hacks project Last Day (github.com/mohanarora3/Last_Day). No code
   from that project is reused; it used FalkorDB.
2. Meterless H-MEM and World Model reference engines, vendored unmodified (Apache-2.0).
3. Zetaris API routes and Lightning SQL forms from zetaris/getting-started.

## Future enhancements

- Real connectors (Slack export, Jira Cloud, GitHub GraphQL) registered as Zetaris REST tables against a live workspace.
- Feed NVIDIA embeddings into H-MEM retrieval (the reference engine uses a hash embedder).
- Meterless Relay missions for the leaver's recurring desktop chores, so they can be replayed after they go.
- A backtest on real repositories: predict, then measure what slowed down after a maintainer left.

## Slide deck outline (10 slides)

1. **Last Day.** Tagline, team, track. Image: `docs/img/board.png`.
2. **The problem.** 12 days, 5 tools, 1 person who knows. A quote from the handover ("silence it for 6 hours, never longer").
3. **Who it's for.** Engineering and ops managers, at the moment of resignation.
4. **What it produces.** Handover plan and exit interview, every claim cited. Image: `docs/img/handover-area.png`.
5. **How the agents work.** The blackboard diagram from the README; the Critic's loop highlighted.
6. **Watching them argue.** Image: `docs/img/investigation.png`. Settlement Batch, critical to at risk, and why.
7. **Zetaris.** Registration (REST tables, SchemaStore views, governed HR view), federated identity joins, catalog discovery.
8. **Meterless.** H-MEM (tacit answers, conflict detection, trust ledger) and World Model (bitemporal ownership). Before and after a saved answer.
9. **Results.** The evaluation table; outage and discovery; 43 tests. NVIDIA and Cursor in one line each.
10. **What's next.** The future enhancements above. Link to the repo.

## Final checklist (from the hackathon brief)

- [ ] One primary track selected (Track 1)
- [ ] Zetaris and Meterless integrated; developed in Cursor; NVIDIA where it contributes
- [ ] Runs from a clean setup: `make setup && make serve`
- [ ] Credentials only from environment variables; `.env.example` has placeholders only; no keys in git history
- [ ] Logs and traces: the Evidence tab, `events.jsonl`, `samples/`
- [ ] Works on more than one case: three companies, five runs in `samples/`, seven in the evaluation
- [ ] Demo video 1 to 4 minutes uploaded
- [ ] Slide deck complete
- [ ] README covers setup, usage and dependencies
- [ ] Pre-existing components declared
- [ ] Submitted before 27 October, 23:45 UTC
