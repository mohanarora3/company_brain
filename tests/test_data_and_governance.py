"""The generated company, the federation contract and the governance guard."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from lastday.config import ROOT, SETTINGS
from lastday.data.generator import write
from lastday.federation import FederationError, LocalFederation
from lastday.federation.governance import GovernanceError, check_sql
from lastday.federation.manifest import BLOCKED_COLUMNS, TABLES
from lastday.federation.registration import ORDER, statements

from .helpers import AS_OF, seed_dir


class GeneratorTest(unittest.TestCase):
    def test_same_seed_same_company(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ra, rb = write(7, a, as_of=AS_OF), write(7, b, as_of=AS_OF)
            for f in sorted(ra.rglob("*.json")):
                if f.name == "meta.json":
                    continue
                self.assertEqual(f.read_bytes(), (rb / f.relative_to(ra)).read_bytes(), f"{f.name} differs between runs")

    def test_different_seeds_differ(self):
        a = json.loads((seed_dir(42) / "slack" / "messages.json").read_text())["messages"]
        b = json.loads((seed_dir(7) / "slack" / "messages.json").read_text())["messages"]
        self.assertNotEqual(len(a), len(b))

    def test_identities_are_messy_like_real_companies(self):
        root = seed_dir(42)
        slack = json.loads((root / "slack" / "users.json").read_text())["members"]
        jira = json.loads((root / "jira" / "users.json").read_text())["values"]
        self.assertTrue(any(u["email"] is None for u in slack), "some Slack users hide their email")
        self.assertTrue(sum(u["email"] is None for u in jira) > len(jira) / 2, "most Jira accounts hide their email")

    def test_ground_truth_is_separate_from_the_sources(self):
        t = json.loads((seed_dir(42) / "_ground_truth.json").read_text())
        self.assertTrue(t["departures"])
        self.assertTrue(any(a["decoy"] for d in t["departures"].values() for a in d["areas"]))
        for f in (ROOT / "lastday" / "agents").glob("*.py"):
            self.assertNotIn("_ground_truth", f.read_text(), f"{f.name} must not read the ground truth")


class GovernanceTest(unittest.TestCase):
    def test_read_only(self):
        for bad in ("DELETE FROM slack.messages", "DROP TABLE jira.issues", "UPDATE hr_pg.departures SET last_day = NULL",
                    "SELECT 1; DROP TABLE x", "CREATE DATASOURCE x OPTIONS ()"):
            with self.assertRaises(GovernanceError, msg=bad):
                check_sql(bad)

    def test_sensitive_hr_data_is_blocked(self):
        for col in BLOCKED_COLUMNS:
            with self.assertRaises(GovernanceError):
                check_sql(f"SELECT {col} FROM hr_pg.employees_directory")
        with self.assertRaises(GovernanceError):
            check_sql("SELECT * FROM hr_pg.employees")

    def test_words_inside_literals_are_fine(self):
        check_sql("SELECT text FROM slack.messages WHERE text LIKE '%salary_band%'")
        check_sql("SELECT summary FROM jira.issues WHERE summary LIKE '%drop the table%'")

    def test_federation_applies_the_guard(self):
        fed = LocalFederation(seed_dir(42))
        with self.assertRaises(GovernanceError):
            fed.query("SELECT salary_band FROM hr_pg.employees_directory")


class FederationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fed = LocalFederation(seed_dir(42))

    def test_qualified_names_match_zetaris(self):
        names = {t.qualified for t in self.fed.catalog()}
        for t in TABLES:
            if not t.optional:
                self.assertIn(t.qualified, names)
        self.assertNotIn("pagerduty.incidents", names, "PagerDuty is registered later, to show discovery")

    def test_cross_source_join(self):
        r = self.fed.query(
            "SELECT e.full_name AS full_name, COUNT(*) AS n FROM slack.messages m "
            "JOIN slack.users u ON u.user_id = m.user_id "
            "JOIN hr_pg.employees_directory e ON lower(e.work_email) = lower(u.email) "
            "GROUP BY e.full_name ORDER BY n DESC", numeric=("n",))
        self.assertGreater(len(r.rows), 5)
        self.assertGreater(r.rows[0]["n"], 50)

    def test_injected_outage(self):
        fed = LocalFederation(seed_dir(42))
        fed.inject_failure("jira")
        with self.assertRaises(FederationError):
            fed.query("SELECT COUNT(*) AS n FROM jira.issues")
        fed.query("SELECT COUNT(*) AS n FROM slack.messages")

    def test_register_optional_source(self):
        fed = LocalFederation(seed_dir(42))
        fed.register("pagerduty")
        self.assertGreater(fed.query("SELECT COUNT(*) AS n FROM pagerduty.incidents", numeric=("n",)).first("n"), 0)


class RegistrationSqlTest(unittest.TestCase):
    def test_raw_hr_table_is_never_registered(self):
        sql = " ".join(statements("hr_pg", SETTINGS, placeholders=True))
        self.assertIn('REGISTER DATASOURCE TABLES ("departures", "access_grants") FROM hr_pg', sql)
        view = next(s for s in statements("hr_pg", SETTINGS, True) if "DATASOURCE VIEW" in s)
        for col in BLOCKED_COLUMNS:
            self.assertNotIn(col, view)

    def test_one_view_per_rest_table(self):
        for src in ORDER[1:]:
            sql = statements(src, SETTINGS, placeholders=True)
            for t in [t for t in TABLES if t.source == src]:
                self.assertTrue(any(f"CREATE LIGHTNING REST TABLE {t.name}_raw FROM {src}_api" in s for s in sql))
                self.assertTrue(any(f"CREATE OR REPLACE SCHEMASTORE VIEW {t.name} WITH CONTAINER {src}" in s for s in sql))

    def test_committed_templates_match_the_manifest(self):
        """zetaris/sql/*.sql are generated from the manifest; this fails if someone edits one without the other."""
        for i, src in enumerate(ORDER):
            path = ROOT / "zetaris" / "sql" / f"{i:02d}_{src}.sql"
            text = path.read_text()
            for stmt in statements(src, SETTINGS, placeholders=True):
                self.assertIn(stmt, text, f"{path.name} is out of date: run `python -m lastday zetaris sql --template`")

    def test_no_secrets_in_templates(self):
        for p in (ROOT / "zetaris" / "sql").glob("*.sql"):
            text = p.read_text()
            self.assertNotRegex(text, r"Bearer (?!\$\{)", p.name)
            self.assertIsNone(re.search(r'password "(?!\$\{)', text), p.name)


if __name__ == "__main__":
    unittest.main()
