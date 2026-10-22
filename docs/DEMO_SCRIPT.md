# Demo video script (3 min 30 s)

The submission video must be 1 to 4 minutes and show the main workflow, how the agents solve the challenge,
the key features, and how Zetaris and Meterless are integrated. This script hits each of those once.

**Before recording**

```bash
make clean-state                 # fresh Meterless memory and no old runs
python -m lastday doctor         # Zetaris connected, Meterless online, NIM key set
make saas & make serve           # SaaS APIs for Zetaris, then the app
```

Open http://localhost:8000 at 1440×900, browser zoom 100%. Have the Zetaris SQL Editor open in a second tab.
Register PagerDuty *after* the first run (step 7), not before.

| Time | Show | Say |
|---|---|---|
| 0:00 | The departures board. | "Priya Raman leaves Acme Pay in 12 days. Her manager has to work out what only Priya knows. It's spread across Slack, Jira, GitHub, a stale wiki and HR, and nobody has time to read it all. Last Day does that investigation with a team of agents." |
| 0:15 | Zetaris SQL Editor: run `SELECT * FROM hr_pg.employees_directory LIMIT 5`, then point at the registered sources. | "Every system stays where it is. Zetaris federates them: the SaaS APIs are Lightning REST tables, HR is Postgres, and the agents only ever see this governed view, with no salaries or personal data." |
| 0:30 | Back to Last Day. Click Priya, then **Investigate**. The trace starts streaming. | "Ten agents, one blackboard. The Cartographer reads the Zetaris catalog. The Resolver links Priya's Slack, Jira and GitHub accounts with federated joins." |
| 0:50 | Pause on round 2: five areas show **Critical** on the right. | "From commits and tickets alone, five areas look critical." |
| 1:00 | Scroll to the Critic's requests. | "The Critic doesn't accept that. Commits over-credit whoever types the code. It asks for corroboration from conversation and incidents, asks the Resolver to sort out an ambiguous 'Rahul V' account, and asks for what Priya actually knows." |
| 1:15 | Settlement Batch flips to **At risk** on the scoreboard. | "With Slack evidence in, Rahul Verma turns out to answer Settlement Batch questions too. The Critic downgrades it, and records why." |
| 1:25 | The Archivist's conflict line. | "Meterless H-MEM catches a stale runbook: the wiki says silence the recon alert for 24 hours, Priya told the team 6. The World Model's source priority keeps hers." |
| 1:35 | **Handover plan** tab: escalation box, then Ledger Reconciliation. | "The plan a manager can act on this week: three escalations, what Priya knows that isn't written down, and who should take over, with reasons." |
| 1:55 | Click a citation chip. The drawer shows the evidence and its SQL. | "Every claim links to the federated query that found it." |
| 2:05 | Click **Accept handover to Rahul**. Toast. | "Accepting writes the new owner to the Meterless World Model. The old ownership is closed, not deleted." |
| 2:15 | **Exit interview** tab. Type an answer under a Zenith question and click **Save answer to memory**. | "Sixteen questions built from evidence, like 'you answered 12 Zenith questions this year, everyone else 4'. Her answer goes into H-MEM." |
| 2:30 | **Investigate again**. On the scoreboard, Zenith Retail's share drops. | "Next run, that answer counts as written knowledge, and the risk drops." |
| 2:45 | **Sources and outages**: turn on the Jira outage. Run again; show the retry and lower-confidence lines. | "If Jira goes down mid-investigation, the agents retry, then carry on with the other sources at lower confidence, and say so." |
| 3:00 | In a terminal, `python -m lastday zetaris register --source pagerduty --yes`, then run again: the discovery line. | "Register a new source in Zetaris and the Cartographer finds it on the next run. No code change." |
| 3:10 | **Ask** tab: "Why does recon run at 03:40?" | "And for Rahul, after Priya's gone: answers from memory and live data, with citations." |
| 3:20 | README evaluation table. | "On seven generated companies with planted decoys: 96.5% label accuracy, every area that needed a handover found, every decoy caught. Last Day. Know what your company forgets, before someone leaves." |

**Tips**
- Turn the Jira outage off again before the Ask step.
- If the live trace runs too fast to narrate, press **Replay at reading speed** after the run; it replays the
  recorded events at a readable pace.
- Hide queries (checkbox above the trace) for the overview, show them when talking about Zetaris.
