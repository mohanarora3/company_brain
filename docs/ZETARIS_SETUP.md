# Running Last Day on Zetaris

The agents talk to a federation contract. Locally that is a SQLite snapshot; with these steps it is your
Zetaris instance, querying Acme Pay's six systems in place. Table names are identical on both, so no agent
code changes.

```
  Zetaris (Docker on your laptop, or an AWS cluster)
   ├── hr_pg            JDBC datasource ──────────────► Postgres :5433  (docker compose)
   ├── slack_api ... pagerduty_api  Lightning REST tables ─► mock SaaS APIs :8787 (python -m lastday saas)
   └── slack, jira, github, docs, pagerduty   SchemaStore views that flatten the JSON
        ▲
        │ read-only Lightning SQL over the REST API (bearer key, X-Org-ID, X-Request-ID)
  Last Day agents
```

## 1. Get a Zetaris instance

Follow [zetaris/getting-started](https://github.com/zetaris/getting-started) (`START-HERE.md`):

- **On your laptop:** download the bundle from Zetaris Cloud's *Run locally* page and follow its Docker
  Compose install guide. The UI is on `http://localhost:3000`, the REST API on `http://localhost:8888/api/v1.0`.
- **Managed AWS cluster:** connect your AWS account in Zetaris Cloud and create a cluster (the Hobby tier is free;
  see their AWS Free Tier checklist). Then read the AWS note in step 3.

## 2. Create an API key and find your organisation id

In the Zetaris UI:

- **Management → API Tokens → +** creates the key. Copy it once.
- **Management → Organisation** shows the numeric organisation **ID**.

Put them in `.env` (copy `.env.example` first):

```dotenv
ZETARIS_REST_URL=http://localhost:8888/api/v1.0
ZETARIS_ORG_ID=1234
ZETARIS_API_KEY=...
SAAS_TOKEN=any-long-random-string
HR_PG_PASSWORD=any-password
```

`python -m lastday doctor` should now report Zetaris as connected.

## 3. Start Acme Pay's systems

```bash
make data           # writes data/seed-42/, including hr/hr.sql
make hr             # Postgres with the HR schema on localhost:5433
make saas           # Slack/Jira/GitHub/wiki/PagerDuty APIs on :8787 (leave it running)
```

Zetaris calls these from inside its own containers, so the defaults use `host.docker.internal`, which Docker
Desktop resolves to your laptop:

```dotenv
SAAS_PUBLIC_URL=http://host.docker.internal:8787
HR_JDBC_URL=jdbc:postgresql://host.docker.internal:5433/acme_hr
```

**AWS cluster instead?** It cannot reach your laptop. Expose the SaaS APIs with a tunnel
(`cloudflared tunnel --url http://localhost:8787` prints a public https URL; put it in `SAAS_PUBLIC_URL`), and load
`data/seed-42/hr/hr.sql` into a Postgres the cluster can reach (RDS, Neon, Supabase), then set `HR_JDBC_URL`,
`HR_PG_USER` and `HR_PG_PASSWORD` to it. Every SaaS request carries `Authorization: Bearer $SAAS_TOKEN`, so use a
long random token.

## 4. Register the sources

Look at what will run first (a dry run prints every statement, with your secrets masked):

```bash
python -m lastday zetaris register
```

Then run it:

```bash
python -m lastday zetaris register --yes
```

It sends one statement per call, in dependency order: the HR datasource with only `departures` and
`access_grants` plus the governed `employees_directory` view, then for each SaaS source a Lightning database, a
REST table per endpoint and a SchemaStore view that explodes the JSON into columns. "Already exists" errors are
skipped, so re-running is safe. PagerDuty is left out on purpose (see step 6).

You can also paste the files into the SQL Editor: `python -m lastday zetaris sql` writes them with your
endpoints to `zetaris/sql/generated/` (gitignored, because they contain your token). The templates in
`zetaris/sql/` show the same statements with placeholders.

## 5. Check and run

```bash
python -m lastday zetaris check        # row counts on Zetaris vs the snapshot, table by table, plus catalog discovery
python -m lastday run Priya --sql      # one investigation, every Lightning SQL statement printed
make serve                             # the UI; the top bar shows "Zetaris connected"
```

With the Zetaris variables set, the engine switches automatically. Force it with `LASTDAY_ENGINE=zetaris`
(fails loudly if Zetaris is unreachable) or back with `LASTDAY_ENGINE=local`.

## 6. The discovery moment for the demo

```bash
python -m lastday zetaris register --source pagerduty --yes
```

Run Priya again. The Cartographer finds `pagerduty.incidents` in the catalog, sees it has a person column, a
timestamp and a column whose values are service ids, and adds it as a new activity source. On-call incident
work now counts toward knowledge shares, without any code change.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `HTTP 401` | Create a new API key under Management → API Tokens and update `ZETARIS_API_KEY`. |
| `HTTP 400` | `ZETARIS_ORG_ID` must be the numeric organisation id. |
| `CREATE LIGHTNING REST TABLE` fails or returns 0 rows | Zetaris calls the endpoint to infer the schema. Make sure `make saas` is running and reachable from Zetaris: `docker exec <zetaris-api-container> curl -s -H "Authorization: Bearer $SAAS_TOKEN" http://host.docker.internal:8787/healthz`. |
| `CREATE DATASOURCE hr_pg` fails | Zetaris tests the JDBC connection first: check `make hr` is up and the URL, user and password in `.env`. |
| Counts differ in `zetaris check` | The SaaS APIs serve the seed in `LASTDAY_SEED`; make sure Postgres was loaded from the same seed (`docker compose down -v && make hr`). |
| Slow first queries | Zetaris fetches REST tables on demand. The client caches results for 5 minutes per statement within a process. |

## What has been tested, and what has not

The Zetaris client is tested against a stand-in HTTP server that enforces the documented headers and returns
the response shapes the client must handle (`tests/test_zetaris_client.py`). The registration statements
follow the syntax in Zetaris's command reference and the confirmed-working PokeAPI recipe in
`zetaris/getting-started`. Agent queries avoid the documented limitation of referencing the same
`explode()` view twice in one query. Run steps 4 and 5 on your instance before recording the demo, and check
the counts match.
