# Last Day: The Whole Project Explained Simply

This is a plain-language guide to **what Last Day is, how it works, what every folder does, and what all the
technical words mean**. You don't need any prior knowledge to read it.

---

## Table of contents

1. [The idea in one minute](#1-the-idea-in-one-minute)
2. [The hackathon and why we built it this way](#2-the-hackathon-and-why-we-built-it-this-way)
3. [The fake company: Acme Pay](#3-the-fake-company-acme-pay)
4. [The big picture: all the pieces](#4-the-big-picture-all-the-pieces)
5. [Concepts explained simply](#5-concepts-explained-simply)
6. [The 10 agents: who does what](#6-the-10-agents-who-does-what)
7. [What happens when you press "Investigate"](#7-what-happens-when-you-press-investigate)
8. [Every folder and file explained](#8-every-folder-and-file-explained)
9. [What we set up on your Mac (and why)](#9-what-we-set-up-on-your-mac-and-why)
10. [Ports: who lives where](#10-ports-who-lives-where)
11. [How to start everything each day](#11-how-to-start-everything-each-day)
12. [All the commands you'll use](#12-all-the-commands-youll-use)
13. [Reading the results](#13-reading-the-results)
14. [Common problems and fixes](#14-common-problems-and-fixes)
15. [What's left before submission](#15-whats-left-before-submission)
16. [Glossary (A to Z)](#16-glossary-a-to-z)

---

## 1. The idea in one minute

**The problem:** When someone quits a job, their manager has only 2 to 4 weeks before the person's last day.
In that time the manager must work out *what only that person knows*:

- why a weird setting exists
- a weekly chore nobody else does
- a password or key nobody else has
- a customer who only ever talks to them

That knowledge is scattered across **Slack** (chat), **Jira** (tickets), **GitHub** (code), the **wiki** (docs),
**PagerDuty** (incidents) and **HR** (employee records). Nobody has time to read all of it. Usually the company
only finds out what it lost *after* the person is gone.

**Our solution, Last Day:** a team of AI **agents** does that investigation automatically. They:

1. read all those systems (through **Zetaris**),
2. argue with each other until the evidence is solid,
3. produce a **handover plan** (who takes over what) and an **exit interview** (questions to ask before the
   person leaves),
4. save the answers in **memory** (through **Meterless**), so next time the company already knows.

**Tagline:** *Know what your company forgets before someone leaves.*

---

## 2. The hackathon and why we built it this way

- **Event:** GenAI.Works **Open Agent Hackathon 2026** (online, 22 to 27 October 2026).
- **Track:** Track 1, *Solving Fragmented Intelligence*: information scattered across many tools.
- **Deadline:** **27 Oct 2026, 23:45 UTC = 28 Oct, 5:15 AM IST.**
- **Sponsors whose tech we use:**
  - **Zetaris**: reads data from many systems with one SQL query (the agents' *eyes*).
  - **Meterless**: memory for AI agents (the agents' *memory*).
  - **NVIDIA NIM**: the AI model that writes nice sentences (the agents' *voice*).
  - **Cursor**: the code editor the rules were written for.

**Rule we follow:** all code was written during the build window (from 22 Oct). The *story* (Acme Pay, Priya,
Rahul) comes from your earlier Graph Hacks project "Last Day", but **no code** from that project is reused. That
project used FalkorDB; this one is a fresh rebuild. The README declares this openly.

---

## 3. The fake company: Acme Pay

We can't use a real company's Slack or salaries in a public demo, so the project **generates a fictional
company** called **Acme Pay**, a payments startup.

- **18 employees**, e.g. Priya Raman, Rahul Verma, Nisha Kapoor, Fatima Zahra, Kenji Watanabe.
- **6 systems**: Slack, Jira, GitHub, Wiki, PagerDuty, HR.
- Thousands of realistic records: ~3,300 Slack messages, ~1,800 commits, ~1,100 Jira tickets, ~600 pull
  requests, 22 wiki pages, ~400 incidents.
- **3 people leaving**: Priya Raman (9 days left), Kenji Watanabe, and Vikram Nair (already left).

**The main story:** Priya Raman, a Staff Engineer in Payments, leaves on 3 Nov 2026. Hidden in the data:

- She holds the **only SFTP key** for Unity Bank (a secret file-transfer connection).
- The **wiki says** "silence the recon alert for 24 hours", but **Priya told the team** "6 hours, never longer".
- Two different people both show up as **"Rahul V"** (Rahul Verma and Rahul Varma), a puzzle to solve.
- Some areas *look* like only Priya knows them (she wrote the code), but actually someone else answers the
  questions in Slack. These are **decoys** that test whether the agents are fooled.

**Seeds:** a *seed* is a number that controls the random generator. Seed 42 always produces the same Acme Pay.
Seeds 7, 13, 21, 5, 77, 99 produce *different* companies with different people leaving. That's how we test the
agents on many companies.

**Ground truth:** the generator also writes down the *correct answers* (`_ground_truth.json`): what's really at
risk for each leaver. The agents **never read it**. Only the grader (`eval`) reads it afterwards, to score them.

---

## 4. The big picture: all the pieces

```
                  YOU
          ┌────────┴────────┐
     Browser               Terminal
  (localhost:8000)      (python -m lastday ...)
          │                    │
          └──────► Last Day app ◄──────┘          (Python, folder: lastday/)
                       │
                The Orchestrator  ──── runs rounds ────┐
                       │                              │
      ┌────────────────┼─────────────────┐            │
   10 AGENTS ◄── read & write ──► BLACKBOARD          │
      │                                   (shared notebook)
      │ SQL questions                     │ memories
      ▼                                   ▼
   ZETARIS (Docker, port 8888)       METERLESS bridge (Node, port 7077)
      │                                   │
      │ reads data in place               ├─ H-MEM  (memories)
      ▼                                   └─ World Model (who owns what)
  ┌───────────────────────────────┐
  │ Fake Acme Pay systems          │
  │  • Slack/Jira/GitHub/Wiki/PD   │ ← mock APIs (make saas, port 8787)
  │  • HR database (Postgres)      │ ← Docker (make hr, port 5433)
  └───────────────────────────────┘
                       ▲
          data/generator.py made all of this data

   NVIDIA NIM (internet) ← Writer uses it to write nicer sentences (optional)
```

**In words:** you click *Investigate* → the Orchestrator wakes the agents → the agents ask Zetaris questions in
SQL → Zetaris fetches answers from the fake Slack/Jira/GitHub/HR → the agents argue on the blackboard → the
Archivist saves knowledge in Meterless → the Writer produces the handover plan and interview → you see it all
live in the browser.

---

## 5. Concepts explained simply

### 5.1 AI agent
A program that **does a job on its own**: it looks at information, decides what to do next, and takes action.
In Last Day, each agent has **one specific job** (detective, sceptic, writer, etc.), like people on a team.

> Important: most of Last Day's agents are **rule-based**: they use logic, maths and SQL, not a chatbot. The AI
> language model (NVIDIA) is only used for *wording*. That's why the results are reliable and repeatable, and
> why it still works with no AI key at all.

### 5.2 Multi-agent system and the blackboard
**Multi-agent** = several agents working together.
**Blackboard** = a shared notebook in the middle of the room. Agents **never talk to each other directly**.
Instead they:
- **post findings** ("Priya made 140 commits to Ledger Reconciliation"), and
- **post requests** ("Critic: I need Slack evidence before I believe this").

Other agents read the notebook and act. This makes every step **traceable**: the whole notebook is saved and
shown in the UI.

### 5.3 Rounds
The investigation runs in **rounds**, like a meeting that keeps going until nobody has new questions:
- Round 1: find where the person shows up.
- Round 2: check who else works there.
- The Critic objects → Round 3: get more evidence.
- Round 4: fix identity puzzles, extract tacit knowledge.
- It stops when the Critic has nothing left to ask (max 6 rounds).

This is why it's **not a simple pipeline**: work flows *backwards* when the Critic isn't satisfied.

### 5.4 Tacit knowledge
Knowledge that's **in someone's head, not written down**: "always run recon before 4 AM because the bank sends
files late". Finding this is the whole point. Slack answers that *only* Priya ever gave are a strong sign of it.

### 5.5 Labels: Critical / At risk / Covered
For each **knowledge area** (a system like "Ledger Reconciliation"), the Analyst measures:
- **Their share**: how much of the activity/knowledge is the leaver's (e.g. 76%).
- **Best backup**: the next most knowledgeable person (e.g. 10%).

Then:
- 🔴 **Critical**: they hold most of it and nobody else is close → urgent handover.
- 🟡 **At risk**: they hold a lot, but someone else knows a fair amount.
- 🟢 **Covered**: others already know it well.

### 5.6 Corroboration
"Proof from more than one place." Commits alone can be misleading (the person who *types* the code isn't always
the one who *understands* it). So the Critic demands that a label also be supported by **conversation (Slack),
incidents (PagerDuty) or docs (wiki)**.

### 5.7 Identity resolution
The same person has **different usernames in every tool**:
- GitHub: `praman-acme`
- Slack: `U0M80O2RAK`
- Jira: `6a2aaa54…`
- HR: `E1014`

The **Resolver** links them by matching emails, names and "who works on the same things". When two accounts are
ambiguous ("Rahul V"), it holds back until it has evidence.

### 5.8 Database, table, row, column
- **Database**: an organised store of data.
- **Table**: like one Excel sheet (e.g. `jira.issues`).
- **Row**: one record (one ticket).
- **Column**: one field (status, assignee, created date).

### 5.9 SQL
**SQL** is the language for asking databases questions:
```sql
SELECT component, COUNT(*) FROM jira.issues WHERE assignee_id = 'Priya' GROUP BY component
```
= "for each component, how many tickets is Priya assigned?"

### 5.10 Join and federated join
A **join** combines two tables on a shared column: e.g. HR employees + Slack users, matched on email.
A **federated join** joins tables that live in **different systems** (HR in Postgres × Slack via an API). Normally
impossible without copying data. **Zetaris makes it possible**, and it's a key thing to show the judges.

### 5.11 Data federation and "in place"
**Federation** = querying many separate systems as if they were one, **without copying the data** into a central
warehouse. "**In place**" / "**in situ**" = the data stays where it lives; the query goes to it.
Why it matters: no stale copies, and sensitive data (HR!) never leaves its system.

### 5.12 Zetaris
A **data harness / federation engine**. You register each source once; then you send one SQL query and Zetaris
splits it up, runs each part at the right source, and combines the results.
In Last Day:
- **HR** is registered as a **JDBC datasource** (a direct database connection to Postgres).
- **Slack, Jira, GitHub, Wiki, PagerDuty** are registered as **Lightning REST tables**: Zetaris calls their web API
  and turns the JSON response into a table.
- **SchemaStore views** "flatten" the nested JSON into clean columns (`slack.messages`, `jira.issues`, …).

### 5.13 Governance
Rules about **who can see what**. In Last Day:
- Agents can **only read** (no DELETE, UPDATE, DROP); `governance.py` blocks anything else.
- From HR, Zetaris only exposes `departures`, `access_grants`, and a view called `employees_directory` that
  **excludes salary, personal email, home city and performance rating**. The raw table is never registered.

### 5.14 API, REST, JSON
- **API**: a way for programs to talk to each other ("give me the Slack messages").
- **REST API**: an API over normal web addresses (URLs), e.g. `http://localhost:8787/slack/api/users.list`.
- **JSON**: the text format the answers come back in: `{"name": "Priya", "team": "Payments"}`.
- **Bearer token**: a secret password sent with each request to prove you're allowed (`SAAS_TOKEN`,
  `ZETARIS_API_KEY`).

### 5.15 Mock API
A **fake version** of a real service that behaves the same way. `make saas` runs fake Slack, Jira, GitHub, Wiki
and PagerDuty APIs that return exactly the JSON shape the real products return. Zetaris can't tell the difference.

### 5.16 Meterless
An open-source **memory system for AI agents**. Two engines (we use the official ones, unmodified):
- **H-MEM (Hierarchical Memory):** stores memories in short-term, working and long-term layers. Every memory keeps
  its **provenance** (where it came from), a **trust history**, and **conflict detection** (catches when two
  sources disagree).
- **World Model:** stores *facts about the world*: people, accounts, systems, and **who owns what**. It's
  **bitemporal**: it remembers *when* something was true. Accepting a handover **closes** Priya's ownership
  instead of deleting it, so history is never lost.

Meterless is written in TypeScript (Node.js), so we run a small **bridge** server that the Python app calls.

### 5.17 Provenance and source priority
- **Provenance** = "where did this fact come from?" (Slack message X, wiki page Y, exit interview).
- **Source priority** = which source wins when two disagree. The expert's own words beat a stale wiki page. That's
  how the **24h vs 6h** conflict is resolved: keep "6 hours".

### 5.18 Why memory changes the next run
When you type Priya's exit-interview answer and save it, it goes into H-MEM. On the next run, the agents see that
the knowledge is now **written down**, so that area's risk **drops**. This "before vs after" is a strong demo moment.

### 5.19 LLM and NVIDIA NIM
- **LLM (Large Language Model)**: an AI that writes text (like ChatGPT/Claude).
- **NVIDIA NIM**: NVIDIA's hosted AI models at build.nvidia.com. We use **Llama 3.3 70B** for writing summaries
  and answers.
- **Fallback:** with no key, the Writer uses **templates** (fill-in-the-blank sentences). Everything still works,
  just less natural wording.

### 5.20 Embeddings
Turning text into a list of numbers so a computer can measure **how similar two texts are**. Used to work out
which system a Slack message is about, and to rank evidence for the Ask tab. NVIDIA model:
`llama-3.2-nv-embedqa-1b-v2`. Fallback: simple local "hashed vectors".

### 5.21 Citations
Every claim in the handover plan links to **the exact query and rows that found it**. The Critic checks every
citation before the plan is shown. This is "explainable AI": no claim without proof.

### 5.22 Evaluation
`make eval` runs the agents on 7 different fake companies and compares their labels with the ground truth:

| Metric | Result | Meaning |
|---|---|---|
| Label accuracy | **96.5%** | How often critical/at risk/covered matched the truth |
| Handover precision | 97.1% | Of the areas it said need handover, how many really did |
| Handover recall | **100%** | Of the areas that really needed handover, how many it found |
| Decoys caught | **5 / 5** | Wasn't fooled by "lots of commits but others know it" |

### 5.23 Docker, image, container
- **Docker**: runs software inside sealed boxes so you don't have to install it on your Mac directly.
- **Image**: the packed box you download once (like an installer).
- **Container**: a running copy of an image (like an open app).
- **Docker Compose**: a recipe file (`docker-compose.yml`) that starts several containers together.
- **Registry**: a store where images live. Zetaris's are in a private Azure registry, so we had to `docker login`.

### 5.24 Rosetta and amd64 vs arm64
Your Mac has an **Apple chip (arm64)**. Zetaris images are built for **Intel/AMD chips (amd64)**. They speak
different machine languages, so the code must be **translated (emulation)**. **Rosetta** is Apple's fast
translator. That's why Zetaris is a bit slow on your Mac (queries take 0.2 to 7 seconds).

### 5.25 localhost, ports, host.docker.internal
- **localhost / 127.0.0.1** = "this computer".
- **Port** = a door number. Many programs run on one computer, each on its own door (8000, 8888, 3000…).
- **host.docker.internal** = the address a program *inside* Docker uses to reach *your Mac*. Zetaris (inside
  Docker) uses it to reach the mock APIs and HR database (on your Mac).

### 5.26 .env and secrets
`.env` is a settings file with **your real keys and passwords**. It is in `.gitignore`, so it's **never uploaded to
GitHub**. `.env.example` is the safe template with blanks, which *is* uploaded.

### 5.27 Virtual environment (.venv)
A private folder of Python packages just for this project, so it doesn't mess with other projects. That's why
commands start with `.venv/bin/python`.

### 5.28 Node.js
A program that runs JavaScript/TypeScript outside the browser. Needed for the Meterless bridge (version 22.7+).

### 5.29 Server-sent events (SSE)
How the browser shows the agents' steps **live**: the server keeps the connection open and pushes each new event
as it happens.

---

## 6. The 10 agents: who does what

Think of it as a detective agency.

| # | Agent | Role on the team | What it actually does | What it pushes back on |
|---|---|---|---|---|
| 1 | **Cartographer** | Map-maker | Reads Zetaris's catalog: what tables exist, which columns hold people, dates, systems. Nothing is hard-coded, so if you add PagerDuty mid-demo, it discovers it. | — |
| 2 | **Resolver** | ID checker | Links each person's GitHub/Slack/Jira accounts to their HR record using federated joins on email, names, and co-activity. | Leaves ambiguous accounts ("Rahul V") unassigned until evidence exists |
| 3 | **Planner** | Team lead | Plans round 1, then turns every request on the blackboard into a task for an agent. | Drops requests no source can answer, with a reason |
| 4 | **Investigators** | Detectives | Write the SQL: commits, code reviews, tickets, Slack answers, docs, access, recurring chores, any newly discovered table. | — |
| 5 | **Analyst** | Accountant | Calculates the leaver's share vs the best backup per area and assigns a label. | — |
| 6 | **Critic** | Sceptic / judge | Applies 6 written rules. Rejects labels built on commits alone, unresolved identities, failed sources, or no captured knowledge. Downgrades/upgrades labels with reasons. Checks every citation. | Thin or one-sided evidence |
| 7 | **Risk officer** | Manager | Ranks by business impact: system tier, days left, chores that stop, keys nobody else holds. Escalates urgent items. | Can **overrule the Critic**: e.g. Unity Bank SFTP is "only 23%" but she holds the *only key*, and a key can't be shared like knowledge |
| 8 | **Successor scout** | Recruiter | Recommends who should take each area, with numbered reasons a manager can disagree with. | — |
| 9 | **Archivist** | Librarian | Stores knowledge in Meterless H-MEM and the World Model, and catches contradictions (wiki 24h vs Priya 6h). | Stale wiki pages that contradict the expert |
| 10 | **Writer** | Reporter | Writes the handover plan and the exit interview (16 questions), each citing evidence. Uses NVIDIA if available. Its output goes back to the Critic. | — |

Plus two helpers that aren't "agents":
- **Orchestrator**: the referee that runs the rounds.
- **Ask**: answers a successor's questions later.

---

## 7. What happens when you press "Investigate"

Using your real run on Priya as the example (48 queries, 4 rounds, ~75 seconds on Zetaris):

**Setup (round 0)**
1. *Orchestrator:* "Last Day run … on zetaris."
2. *Cartographer:* reads the catalog → "14 tables across 5 sources". Profiles each table (row counts, date ranges).
3. *Resolver:* loads HR directory, finds who's leaving, loads GitHub/Jira/Slack accounts, runs federated joins
   (HR × Jira, HR × Slack, HR × GitHub) → "Linked 52 accounts to 18 employees; 1 ambiguous."
4. *Archivist:* connects to Meterless, writes people/accounts/systems into the World Model.
5. *Planner:* writes a 5-step plan.

**Round 1: where does Priya show up?**
6. *Investigators:* her special access (HR), who else has that access, her commits by system, her Jira work,
   her Slack answers, recurring chores. → 8 candidate systems.

**Round 2: who else works on them?**
7. *Investigators:* PR reviewers, Jira work per person, commit authorship for everyone.
8. *Analyst:* first scores → **5 critical**, 0 at risk, 3 covered.
9. *Critic:* "Critical on commits and tickets alone. Not good enough." Requests corroboration for 7 areas.

**Round 3: the Critic's requests**
10. *Investigators:* Slack thread answers in the relevant channels, the questions they answered, wiki pages.
11. *Analyst:* → 4 critical, 1 at risk.
12. *Critic:* **Month-end Close downgraded** (Nisha Kapoor knows 26%). Asks the Resolver to identify unknown
    accounts on Settlement Batch, and asks for Priya's tacit knowledge on 4 areas.

**Round 4**
13. *Resolver:* compares the two "Rahul" accounts' activity → "Rahul V" = **Rahul Verma**.
14. *Investigators:* find answers only Priya ever gave (e.g. 8 on Ledger Reconciliation).
15. *Critic:* **Settlement Batch downgraded** (Rahul Verma knows 32%).
16. *Risk officer:* escalates Ledger Reconciliation, Unity Bank SFTP, Zenith Retail; notes an SFTP chore that has
    had no owner for months.
17. *Successor scout:* Rahul Verma, Fatima Zahra, Nisha Kapoor, with reasons.
18. *Archivist:* stores 12 tacit answers + 8 wiki sentences; flags the **24h vs 6h** contradiction, keeps 6h.
19. *Critic:* verifies all citations.
20. *Writer:* drafts 16 exit-interview questions.
21. *Orchestrator:* **Done. 3 critical, 2 at risk, 3 covered.**

---

## 8. Every folder and file explained

```
last_day/
├── README.md, Makefile, .env, ...   ← setup & instructions
├── lastday/          ← THE APP (Python)
│   ├── agents/       ← the 10 agents + blackboard + orchestrator
│   ├── federation/   ← how agents get data (Zetaris or local copy)
│   ├── data/         ← the fake-company generator
│   ├── saas/         ← fake Slack/Jira/GitHub/... APIs
│   ├── meterless/    ← memory client
│   └── llm/          ← NVIDIA AI + embeddings
├── meterless-bridge/ ← memory engines (Node.js)
├── web/              ← the website you see
├── zetaris/sql/      ← SQL templates to register sources in Zetaris
├── data/             ← generated companies (seed-42, seed-7, ...)
├── tests/            ← automatic checks
├── samples/          ← saved example runs
├── docs/             ← guides, demo script, submission answers
├── scripts/          ← helper scripts
├── .lastday/         ← your local run history & memory (not uploaded)
└── .venv/            ← Python packages (not uploaded)
```

### 8.1 Root files

| File | Simple explanation |
|---|---|
| `README.md` | The project's **front page** on GitHub: what it is, how to run it, the agents, sponsors, results. Judges read this first. |
| `Makefile` | A list of **shortcut commands**. `make serve` = start the website, `make saas` = start fake APIs, etc. |
| `.env` | **Your secret settings** (Zetaris key, NVIDIA key, passwords). **Never uploaded.** |
| `.env.example` | The **safe template** of `.env` with blanks. Uploaded so others know what to fill in. |
| `.gitignore` | The list of things git must **never upload**: `.env`, `.venv`, `data/seed-*`, `.lastday/`. |
| `docker-compose.yml` | Recipe to start the **HR Postgres database** in Docker (`make hr`). Loads `data/seed-42/hr/hr.sql`. |
| `requirements.txt` | Python packages the app needs: **Starlette** (web framework) and **Uvicorn** (web server). |
| `requirements-dev.txt` | Extra packages for development only. |
| `AGENTS.md` | **Rules for AI coding assistants** editing this code: use the blackboard, read-only SQL, cite every claim. |
| `.cursor/rules/` | The same rules in **Cursor's** format: `lastday-agents.mdc`, `ui.mdc`, `zetaris-sql.mdc`. |
| `LICENSE` | MIT open-source license. |

### 8.2 `lastday/`: the app itself

| File | Simple explanation |
|---|---|
| `__main__.py` | The **terminal commands**: `run`, `ask`, `serve`, `saas`, `generate`, `zetaris`, `eval`, `memory`, `doctor`. Runs when you type `python -m lastday ...`. |
| `server.py` | The **web server**: serves the website and the API (`/api/people`, `/api/runs`, `/api/ask`, `/api/sources`…) and streams live agent steps to the browser. |
| `config.py` | **Reads `.env`** and decides: use Zetaris or the local copy? Use NVIDIA or templates? |
| `eval.py` | The **grader**: runs agents on many companies and scores them against ground truth. |

#### `lastday/agents/`: the brains

| File | Simple explanation |
|---|---|
| `blackboard.py` | The **shared notebook**: findings, requests, labels, evidence, and the event log. |
| `orchestrator.py` | The **referee**: wakes each agent in order, runs rounds until the Critic is satisfied. |
| `cartographer.py` | Explores the Zetaris catalog. |
| `resolver.py` | Links accounts to people. |
| `planner.py` | Turns requests into tasks. |
| `investigators.py` | All the **detective SQL queries** (the biggest agent file, ~440 lines). |
| `analyst.py` | Calculates shares and labels. |
| `critic.py` | The 6 rules, downgrades/upgrades, citation checks. |
| `risk.py` | Urgency and escalation. |
| `successor.py` | Picks who takes over. |
| `archivist.py` | Talks to Meterless: saves memories, catches contradictions, tracks ownership. |
| `writer.py` | Writes the handover plan and exit interview. |
| `ask.py` | Answers questions in the **Ask** tab using memory + live data. |

#### `lastday/federation/`: getting the data

| File | Simple explanation |
|---|---|
| `base.py` | The **contract**: "every data engine accepts SQL and returns rows." Agents only know this, so they don't care whether it's Zetaris or the local copy. |
| `zetaris.py` | The **Zetaris client**: sends SQL to `localhost:8888` with your API key and org ID, handles errors, caches results for 5 minutes. |
| `local.py` | The **fallback**: a SQLite copy with the **same table names**, so the demo works with zero setup. |
| `governance.py` | The **safety guard**: blocks writes and forbidden HR columns *before* any query is sent. |
| `manifest.py` | The **master list** of all systems, tables and columns. Everything else is generated from it. |
| `registration.py` | **Generates the Zetaris SQL** that registers every source (`zetaris register` / `zetaris sql`). |

#### `lastday/data/`: the fake company

| File | Simple explanation |
|---|---|
| `storylines.py` | The **script**: Acme Pay's people, systems and hidden stories (the SFTP key, the 24h/6h wiki, the two Rahuls). |
| `generator.py` | **Builds all the data** from the script: Slack, Jira, GitHub, wiki, PagerDuty, HR SQL, and the ground-truth answers. |

#### `lastday/saas/`

| File | Simple explanation |
|---|---|
| `mock_api.py` | The **fake Slack/Jira/GitHub/Wiki/PagerDuty web APIs** on port 8787 (`make saas`). Includes a "fail" switch so you can simulate an outage. |

#### `lastday/meterless/` and `lastday/llm/`

| File | Simple explanation |
|---|---|
| `meterless/client.py` | Python's way of talking to the Meterless bridge: save memory, search, record ownership, audit. |
| `llm/client.py` | Calls **NVIDIA NIM** (or any OpenAI-compatible AI). Falls back to templates. |
| `llm/embeddings.py` | Text → numbers for similarity. NVIDIA model, or a local fallback. |

### 8.3 `meterless-bridge/`: the memory engines

| File | Simple explanation |
|---|---|
| `server.ts` | A small **Node.js server on port 7077** that hosts the Meterless engines. The Python app starts it automatically. |
| `scripts/setup.mjs` | **Downloads** the official Meterless engines (run by `make setup`). |
| `vendor/hmem/` | The official **H-MEM** engine (memories), unmodified, Apache-2.0. |
| `vendor/world-model/` | The official **World Model** engine (people, systems, ownership over time), unmodified. |
| `package.json` | Node.js settings. |

### 8.4 `web/`: the website

| File | Simple explanation |
|---|---|
| `index.html` | The **page layout**: departures board, person page, tabs, sources panel. |
| `app.js` | **All the behaviour** (~780 lines): load people, start runs, live trace, tabs, accept handover, save answers, Ask, register sources, simulate outages. |
| `styles.css` | The **look**: an airport departures-board style (yellow, monospaced). |
| `favicon.svg` | Browser-tab icon. |

### 8.5 `zetaris/sql/`

| File | What it registers |
|---|---|
| `00_hr_pg.sql` | HR Postgres: only `departures`, `access_grants`, and the safe `employees_directory` view |
| `01_slack.sql` | Slack users, channels, messages |
| `02_jira.sql` | Jira users, issues |
| `03_github.sql` | GitHub users, commits, commit files, pull requests, service catalog |
| `04_docs.sql` | Wiki pages |
| `05_pagerduty.sql` | PagerDuty users, incidents (left out on purpose: you add it live in the demo) |

These are **templates with placeholders**. `registration.py` fills in your real addresses and tokens.

### 8.6 `data/`: generated companies (not uploaded)

```
data/seed-42/
├── slack/  jira/  github/  docs/  pagerduty/   ← JSON the mock APIs serve
├── hr/hr.sql                                   ← loaded into Postgres by `make hr`
├── meta.json                                   ← summary of this company
└── _ground_truth.json                          ← the right answers (only eval reads it)
```
Rebuilt any time with `make data`.

### 8.7 `tests/`: automatic checks (43 tests)

| File | What it checks |
|---|---|
| `test_agents.py` | The full investigation on generated companies, scored against ground truth |
| `test_data_and_governance.py` | The generator, the federation contract, and that the safety guard blocks bad queries |
| `test_memory.py` | That memory really changes the next run |
| `test_server.py` | The web API, served for real and called over HTTP |
| `test_zetaris_client.py` | The Zetaris client against a fake Zetaris server |
| `helpers.py`, `__init__.py` | Shared test setup (isolated memory, no AI calls) |

Run them with `make test`.

### 8.8 `samples/`: example outputs

Five complete saved runs (handover, interview, blackboard, trace) plus `eval.json`:
`seed-42-priya-raman`, `seed-42-kenji-watanabe`, `seed-42-priya-jira-outage` (Jira down),
`seed-7-nisha-kapoor`, `seed-13-grace-mensah`. Judges can look at results without running anything.

### 8.9 `docs/`: guides

| File | What it's for |
|---|---|
| `ARCHITECTURE.md` | The deep technical design: rules, thresholds, formulas |
| `ZETARIS_SETUP.md` | How to connect Zetaris (what we followed) |
| `SPONSOR_TECH.md` | How each sponsor's tech is used and what's unique |
| `DEMO_SCRIPT.md` | **What to show in your demo video** |
| `SUBMISSION.md` | **Ready-made answers for the submission form** |
| `img/` | Screenshots used in the README |

### 8.10 Other folders

| Folder | Simple explanation |
|---|---|
| `scripts/screenshots.py` | Takes README screenshots automatically (needs Playwright) |
| `.lastday/` | Your **local history**: past runs (`runs/<id>/handover.md`, `interview.md`…) and Meterless memory. Not uploaded. `make clean-state` wipes it. |
| `.venv/` | Python packages for this project. Not uploaded. |
| `.git/` | Git's history of the project. |

---

## 9. What we set up on your Mac (and why)

| # | What we did | Why |
|---|---|---|
| 1 | Found the project in `~/last_day` and ran the tests | Check it was built and working |
| 2 | Created `.env` with random SaaS token & HR password | The app and Zetaris need these to talk securely |
| 3 | `make setup` | Installed Python packages + Meterless, generated fake companies |
| 4 | `docker login` to Zetaris's private registry | Zetaris images are private to hackathon users |
| 5 | Turned off Docker's internal proxy | Docker couldn't reach Azure through it (login kept timing out) |
| 6 | Raised Docker memory to ~7 GB | Zetaris needs at least 6 GB |
| 7 | Turned on Rosetta | Run Intel-built Zetaris faster on your Apple chip |
| 8 | `docker system prune -a` + freed disk | Zetaris images need ~10 GB |
| 9 | `./preflight.sh` | Zetaris's own "is your Mac ready?" check: passed |
| 10 | `docker compose pull` + start | Downloaded (~45 min) and started Zetaris |
| 11 | Logged in at `localhost:3000` as `admin@zetaris.com` | The local Zetaris has its own admin user |
| 12 | Org ID **1** + API token → `.env` | So the app can call Zetaris's API |
| 13 | `doctor` → **Zetaris connected** | Confirmed |
| 14 | `make hr` + `make saas` | Started the fake company's systems |
| 15 | `zetaris register --yes` | Told Zetaris about all 5 sources (14 tables) |
| 16 | `zetaris check` → every count matches | Proved Zetaris sees exactly the right data |
| 17 | `run Priya --sql` | **Full investigation through Zetaris: 48 federated queries** ✅ |
| 18 | NVIDIA key → `.env` | Nicer AI-written text |

---

## 10. Ports: who lives where

| Port | What runs there | Started by |
|---|---|---|
| **8000** | **Last Day website** (open in browser) | `make serve` |
| **8787** | Fake Slack/Jira/GitHub/Wiki/PagerDuty APIs | `make saas` |
| **7077** | Meterless memory bridge | Started automatically by the app |
| **5433** | HR Postgres database | `make hr` (Docker) |
| **3000** | Zetaris website (for humans) | Zetaris Docker |
| **8888** | Zetaris API (for the app) | Zetaris Docker |

"**Address already in use**" = something is already sitting on that port (usually an old copy). Kill it:
`lsof -ti :8000 | xargs kill -9`.

---

## 11. How to start everything each day

Open Docker Desktop first and wait for **"Engine running"**. Then:

**Tab 1: Zetaris + HR database**
```bash
cd ~/Downloads/zetaris-platform && docker compose up -d
cd ~/last_day && make hr
```
Wait a few minutes for Zetaris to be ready (open `localhost:3000` to check).

**Tab 2: fake APIs (leave running)**
```bash
cd ~/last_day && make saas
```

**Tab 3: the app (leave running)**
```bash
cd ~/last_day && make serve
```

Open **http://127.0.0.1:8000**. Check the bottom-left says **Zetaris connected**.

**To stop:** press **Ctrl+C** in tabs 2 and 3. **Never Ctrl+Z**: that only *pauses* the program and keeps the
port blocked.

---

## 12. All the commands you'll use

Run from `~/last_day`. `py` below means `.venv/bin/python`.

| Command | What it does |
|---|---|
| `make setup` | One-time install |
| `make serve` | Start the website on :8000 |
| `make saas` | Start the fake APIs on :8787 |
| `make hr` | Start the HR database on :5433 |
| `make test` | Run all tests |
| `make eval` | Score the agents on 7 companies |
| `make clean-state` | Forget all runs and memory (fresh start for a demo) |
| `py -m lastday doctor` | Check what's configured |
| `py -m lastday run Priya` | Investigate Priya in the terminal |
| `py -m lastday run Priya --sql` | …and print every SQL query |
| `py -m lastday run Priya --fail jira` | …pretend Jira is down |
| `py -m lastday run Priya --no-memory` | …without Meterless |
| `py -m lastday ask "Why does recon run at 03:40?"` | Ask a question |
| `py -m lastday people` | List employees and leavers |
| `py -m lastday zetaris register` | Show registration SQL (dry run) |
| `py -m lastday zetaris register --yes` | Actually register sources |
| `py -m lastday zetaris register --source pagerduty --yes` | Add PagerDuty (demo moment) |
| `py -m lastday zetaris check` | Compare Zetaris row counts with the local copy |
| `py -m lastday memory stats` | How much is in Meterless memory |

---

## 13. Reading the results

### The website

- **Left: Departures board**: people leaving and days left. *Everyone else* lets you investigate anyone.
- **Bottom-left: status**: Zetaris / Meterless / LLM / Embeddings.
- **Top-right: Sources and outages**: see each source, **register PagerDuty live**, **switch off a source** to
  simulate an outage.
- **Person page → Investigate** (toggle *Use memory* on/off).

**The 5 tabs:**
1. **Investigation**: the live trace (every agent step, every query with row count and time) and the scoreboard of
   areas with share bars.
2. **Handover plan**: each area, label, successor with reasons, actions this week. **Accept handover** moves
   ownership in the World Model.
3. **Exit interview**: 16 questions. Type answers and save → stored in memory → lowers risk next run.
4. **Evidence**: every finding; click to see the exact SQL and rows.
5. **Ask**: a successor asks questions; answers cite sources; 👍/👎 feedback goes into memory.

### Priya's result

| Area | Label | Theirs | Best backup | Successor |
|---|---|---|---|---|
| Zenith Retail account | 🔴 Critical | 80% | 14% | Fatima Zahra |
| Ledger Reconciliation | 🔴 Critical | 76% | 10% | Rahul Verma |
| Unity Bank SFTP | 🔴 Critical | 23% | 10% | Rahul Verma (she holds the only key) |
| Settlement Batch | 🟡 At risk (downgraded) | 64% | 32% | Rahul Verma |
| Month-end Close | 🟡 At risk (downgraded) | 59% | 26% | Nisha Kapoor |
| Chargeback Operations | 🟢 Covered | 29% | 50% | — |
| Payments Gateway | 🟢 Covered | 7% | 46% | — |
| Refunds Service | 🟢 Covered | 7% | 41% | — |

**One line:** *3 things will break if Priya leaves without a handover. Here's who takes each, and here are 16
questions to ask her first.*

---

## 14. Common problems and fixes

| Problem | Cause | Fix |
|---|---|---|
| Page stuck on "Loading the HR system…" | An old paused app is holding port 8000 | `lsof -ti :8000 \| xargs kill -9` then `make serve` |
| `address already in use` | Same as above | Same as above (also `:7077` for Meterless) |
| `Meterless bridge did not start` | Old bridge on 7077 | `lsof -ti :7077 \| xargs kill -9` |
| `docker login … context deadline exceeded` | Docker's proxy | Docker → Settings → Resources → Proxies → off |
| Zetaris `HTTP 401` | Wrong/expired API key | New token in Zetaris → `.env` |
| Zetaris `HTTP 400` | Org ID wrong | Must be the number (`1`) |
| `zetaris check` counts differ | HR loaded from another seed | `docker compose down -v && make hr` |
| REST table 0 rows / fails | `make saas` not running | Start it in its own tab |
| PagerDuty `HTTP 400` in check | Not registered yet (on purpose) | Fine. Register it during the demo |
| `LLM unavailable … CERTIFICATE_VERIFY_FAILED` | Python can't verify HTTPS | `.venv/bin/pip install certifi` then add `SSL_CERT_FILE=<certifi path>` to `.env` |
| Zetaris very slow | Emulation on Apple chip | Make sure Rosetta is on; give Docker 8 GB |

---

## 15. What's left before submission

| # | Task | Notes |
|---|---|---|
| 1 | Fix the NVIDIA certificate error | See section 14 |
| 2 | **Replace the NVIDIA key** | The old one was pasted in chat |
| 3 | Push to GitHub | New public repo `last-day`; check `.env` is not in `git status` |
| 4 | Fix the repo link in `docs/SUBMISSION.md` | Replace `<you>/last-day` |
| 5 | Record the demo video (1 to 4 min) | Follow `docs/DEMO_SCRIPT.md` |
| 6 | Submit | Answers in `docs/SUBMISSION.md`; before **28 Oct, 5:15 AM IST** |

**Demo moments to show:**
1. Priya's investigation running live **on Zetaris** (show "Zetaris connected" and the SQL).
2. The **Critic downgrading** Month-end Close and Settlement Batch.
3. The **Risk officer overruling**: Unity Bank SFTP critical at only 23% because of the key.
4. The **24h vs 6h** contradiction caught by memory.
5. **Register PagerDuty live**: the next run discovers it on its own.
6. **Switch off Jira**: agents retry, work around it, lower confidence.
7. **Answer an exit-interview question → run again → risk drops** (memory working).

---

## 16. Glossary (A to Z)

| Term | Simple meaning |
|---|---|
| **Agent** | A program with one job that decides and acts on its own |
| **amd64 / arm64** | Intel/AMD chips vs Apple chips: different machine languages |
| **API** | A way for programs to talk to each other |
| **API key / token** | A secret password a program uses to prove it's allowed |
| **At risk** | The leaver holds a lot, but someone else knows a fair amount |
| **Bitemporal** | Remembers *when* something was true, not just *what* |
| **Blackboard** | The shared notebook agents use instead of talking directly |
| **Catalog** | Zetaris's list of all registered tables |
| **Citation** | A link from a claim to the exact evidence |
| **Container** | A running Docker box |
| **Corroboration** | Proof from a second, different source |
| **Covered** | Others already know this area well |
| **Critical** | The leaver holds most of it; nobody close behind |
| **Decoy** | An area that *looks* critical from commits but others actually know it |
| **Docker** | Runs software in sealed boxes |
| **Docker Compose** | A recipe to start several containers together |
| **Embedding** | Text turned into numbers to measure similarity |
| **.env** | Secret settings file, never uploaded |
| **Escalate** | Mark as urgent for this week |
| **Evaluation (eval)** | Scoring the agents against the right answers |
| **Federation** | Querying many systems as one without copying data |
| **Federated join** | Combining tables from different systems in one query |
| **Governance** | Rules about who can see and do what |
| **Ground truth** | The planted right answers (agents never see them) |
| **H-MEM** | Meterless's layered memory engine |
| **host.docker.internal** | The address Docker uses to reach your Mac |
| **In place / in situ** | Data stays where it lives; the query goes to it |
| **JDBC** | A standard way for programs to connect to databases |
| **JSON** | The text format APIs answer in |
| **Lightning REST table** | Zetaris feature: turns a web API into a table |
| **LLM** | AI that writes text |
| **localhost / 127.0.0.1** | "This computer" |
| **Meterless** | Open-source memory for AI agents |
| **Mock API** | A fake service that behaves like the real one |
| **NIM** | NVIDIA's hosted AI models |
| **Node.js** | Runs JavaScript/TypeScript outside the browser |
| **Orchestrator** | The referee that runs the agents in rounds |
| **Port** | A numbered door on a computer for one program |
| **Postgres** | A popular database (HR lives in one) |
| **Preflight** | Zetaris's "is your Mac ready?" check |
| **Provenance** | Where a fact came from |
| **Registry** | A store of Docker images |
| **REST** | APIs over normal web addresses |
| **Rosetta** | Apple's translator for Intel-built software |
| **Round** | One pass of investigation; repeats until the Critic is satisfied |
| **SchemaStore view** | Zetaris feature that flattens nested JSON into columns |
| **Seed** | A number that controls which fake company is generated |
| **Server-sent events** | How the browser gets live updates |
| **Source priority** | Which source wins when two disagree |
| **SQL** | The language for asking databases questions |
| **SQLite** | A tiny file-based database (the local fallback) |
| **Tacit knowledge** | Knowledge in someone's head, not written down |
| **Template fallback** | Fill-in-the-blank text used when no AI key is set |
| **venv** | A private folder of Python packages for one project |
| **World Model** | Meterless engine for people, systems and who owns what over time |
| **Zetaris** | Data harness: one SQL query across many systems, nothing copied |
