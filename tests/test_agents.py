"""The agents end to end on generated companies, scored against planted ground truth."""
from __future__ import annotations

import unittest

from lastday.agents.orchestrator import run_analysis
from lastday.eval import evaluate
from lastday.federation import LocalFederation

from .helpers import AS_OF, seed_dir, truth


class InvestigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fed = LocalFederation(seed_dir(42))
        cls.t = truth(42)
        cls.eid = next(e for e, d in cls.t["departures"].items() if d["name"] == "Priya Raman")
        cls.events = []
        cls.bb = run_analysis(cls.fed, cls.eid, as_of=AS_OF, use_memory=False, on_event=cls.events.append)

    def test_labels_match_ground_truth(self):
        got = {a.system: a.label for a in self.bb.areas.values()}
        for area in self.t["departures"][self.eid]["areas"]:
            self.assertEqual(got.get(area["system"], "covered"), area["label"], area["system"])

    def test_agents_interact_over_several_rounds(self):
        self.assertGreaterEqual(self.bb.round, 3)
        kinds = {(e["agent"], e["kind"]) for e in self.events}
        for expected in [("Critic", "request"), ("Planner", "delegate"), ("Critic", "verdict"), ("Risk officer", "escalation"),
                         ("Resolver", "disambiguation"), ("Successor scout", "successor")]:
            self.assertIn(expected, kinds)
        self.assertTrue(all(r.status in ("done", "dropped") for r in self.bb.requests), "every request is handled")

    def test_critic_changes_labels_with_reasons(self):
        moved = [a for a in self.bb.areas.values() if a.status in ("downgraded", "upgraded")]
        self.assertTrue(moved, "corroboration changes at least one provisional label")
        for a in moved:
            self.assertTrue(any(h["stage"].startswith("critic") and h["notes"] for h in a.history))

    def test_risk_officer_keeps_exclusive_access_critical(self):
        sftp = self.bb.areas.get("bank-sftp")
        self.assertIsNotNone(sftp)
        self.assertEqual(sftp.label, "critical")
        self.assertTrue(any(x.get("exclusive") for x in sftp.exclusive_access))

    def test_every_handover_claim_is_cited(self):
        h = self.bb.outputs["handover"]
        self.assertEqual(self.bb.outputs["citation_problems"], [])
        for s in h["areas"]:
            self.assertTrue(s["citations"], s["system"])
            for c in s["citations"]:
                self.assertIn(c, self.bb.evidence)
                q = self.bb.evidence[c].query_id
                self.assertTrue(any(x.id == q for x in self.bb.queries), f"{c} points to a query that ran")

    def test_interview_questions_cite_evidence(self):
        qs = self.bb.outputs["interview"]["questions"]
        self.assertGreaterEqual(len(qs), 5)
        self.assertGreaterEqual(sum(1 for q in qs if q["cites"]) / len(qs), 0.7)

    def test_sensitive_columns_never_queried(self):
        for q in self.bb.queries:
            self.assertNotIn("salary_band", q.sql)
            self.assertNotIn("hr_pg.employees ", q.sql + " ")


class OutageTest(unittest.TestCase):
    def test_agents_retry_then_degrade(self):
        fed = LocalFederation(seed_dir(42))
        fed.inject_failure("jira")
        events = []
        eid = next(iter(truth(42)["departures"]))
        bb = run_analysis(fed, eid, as_of=AS_OF, use_memory=False, on_event=events.append)
        self.assertIn("jira", bb.failed_sources)
        self.assertTrue(any(r.kind == "retry_source" for r in bb.requests))
        self.assertTrue(any(e["kind"] in ("retry", "degraded") for e in events))
        self.assertTrue(bb.outputs["handover"]["headline"], "still produces a handover")


class DiscoveryTest(unittest.TestCase):
    def test_new_source_is_discovered(self):
        fed = LocalFederation(seed_dir(42))
        eid = next(iter(truth(42)["departures"]))
        before = run_analysis(fed, eid, as_of=AS_OF, use_memory=False)
        fed.register("pagerduty")
        events = []
        after = run_analysis(fed, eid, as_of=AS_OF, use_memory=False, on_event=events.append)
        self.assertNotIn("pagerduty.incidents", before.source_map)
        self.assertIn("pagerduty.incidents", after.source_map)
        self.assertTrue(any(e["kind"] == "discovery" for e in events))


class EvaluationTest(unittest.TestCase):
    def test_accuracy_across_companies(self):
        s = evaluate([42, 7, 13], as_of=AS_OF, verbose=False)
        self.assertGreaterEqual(s["label_accuracy"], 0.9)
        self.assertEqual(s["handover_recall"], 1.0, "never miss an area that needs a handover")
        caught, total = (int(x) for x in s["decoys_caught"].split("/"))
        self.assertEqual(caught, total, "every planted decoy is caught by corroboration")


if __name__ == "__main__":
    unittest.main()
