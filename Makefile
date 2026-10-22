PY ?= .venv/bin/python
# Newest Python 3.10+ on the machine (macOS's own python3 can be 3.9).
PYTHON ?= $(shell for p in python3.13 python3.12 python3.11 python3.10 python3; do command -v $$p >/dev/null 2>&1 && echo $$p && break; done)

.PHONY: setup data serve demo test eval samples saas hr zetaris-sql zetaris-register zetaris-check doctor clean-state

setup:                      ## venv + Python deps + Meterless engines (Node 22.7+)
	@$(PYTHON) -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ needed, found ' + sys.version.split()[0]"
	@node -e "const [a,b]=process.versions.node.split('.').map(Number); if (a<22||(a===22&&b<7)) console.log('warning: Node '+process.version+' is too old for the Meterless bridge (needs 22.7+); runs will continue without memory')" 2>/dev/null || echo "warning: Node.js not found; runs will continue without Meterless memory"
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -q -r requirements.txt
	test -f meterless-bridge/vendor/hmem/src/index.ts || (cd meterless-bridge && npm run setup)
	$(PY) -m lastday generate --seeds 42 7 13 21

data:                       ## regenerate the demo companies
	$(PY) -m lastday generate --seeds 42 7 13 21

serve:                      ## web app on http://localhost:8000
	$(PY) -m lastday serve

demo:                       ## one investigation in the terminal
	$(PY) -m lastday run Priya

test:                       ## unit + end-to-end tests (standard library only)
	$(PY) -W ignore -m unittest discover -s tests -t . -v

eval:                       ## score the agents on several generated companies
	$(PY) -m lastday eval --seeds 42 7 13 21 5 77 99 --out samples/eval.json

samples:                    ## regenerate samples/ from a clean memory state
	rm -rf .lastday
	$(PY) -m lastday run Priya --quiet --out samples/seed-42-priya-raman
	$(PY) -m lastday run Kenji --quiet --out samples/seed-42-kenji-watanabe
	$(PY) -m lastday run Priya --quiet --no-memory --fail jira --out samples/seed-42-priya-jira-outage
	$(PY) -m lastday --seed 7 run E1015 --quiet --out samples/seed-7-nisha-kapoor
	$(PY) -m lastday --seed 13 run E1014 --quiet --out samples/seed-13-grace-mensah
	$(PY) -m lastday eval --seeds 42 7 13 21 5 77 99 --quiet --out samples/eval.json

saas:                       ## mock Slack/Jira/GitHub/Docs/PagerDuty APIs for Zetaris
	$(PY) -m lastday saas

hr:                         ## HR Postgres on :5433 for Zetaris
	docker compose up -d hr-postgres

zetaris-sql:                ## write registration SQL with your endpoints
	$(PY) -m lastday zetaris sql

zetaris-register:           ## register every source in Zetaris (asks no questions: review `make zetaris-sql` first)
	$(PY) -m lastday zetaris register --yes

zetaris-check:              ## compare Zetaris row counts with the snapshot
	$(PY) -m lastday zetaris check

doctor:
	$(PY) -m lastday doctor

clean-state:                ## forget runs and Meterless memory
	rm -rf .lastday
