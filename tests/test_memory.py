"""Meterless H-MEM + World Model through the bridge: memory changes the next run.

Skipped when Node 22.7+ or the vendored engines are missing.
"""
from __future__ import annotations

import unittest

from lastday.agents.archivist import Archivist
from lastday.agents.ask import ask
from lastday.agents.orchestrator import namespace_for, run_analysis
from lastday.federation import LocalFederation
from lastday.meterless.client import Meterless, stop_bridge

from .helpers import AS_OF, engines_vendored, node_ok, seed_dir, truth


@unittest.skipUnless(node_ok() and engines_vendored(), "needs Node 22.7+ and meterless-bridge/vendor (npm run setup)")
class MemoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fed = LocalFederation(seed_dir(42))
        cls.ns = namespace_for(cls.fed)
        cls.m = Meterless(cls.ns)
        cls.m.health()
        cls.m.reset()
        cls.eid = next(e for e, d in truth(42)["departures"].items() if d["name"] == "Priya Raman")
        cls.first = run_analysis(cls.fed, cls.eid, as_of=AS_OF, use_memory=True)

    @classmethod
    def tearDownClass(cls):
        stop_bridge()

    def test_memory_written_with_provenance(self):
        self.assertTrue(self.first.memory_log)
        mems = self.m.memories(tag=f"person:{self.eid}")
        self.assertTrue(all(x["provenance"].get("label") for x in mems))
        self.assertGreater(self.m.wm_stats()["entities"], 30)

    def test_planted_wiki_contradiction_found(self):
        recon = self.first.areas["ledger-recon"]
        self.assertTrue(recon.conflicts, "the stale wiki page contradicts what the expert said in Slack")
        self.assertEqual(recon.conflicts[0].get("world_model_winner"), "6 hours", "source priority keeps the expert's value")

    def test_interview_answer_lowers_risk_next_run(self):
        snap = self.first.snapshot()
        before = self.first.areas["zenith-retail"].share
        arch = Archivist(self.ns)
        arch.connect(self.first)
        arch.save_answer(None, snap, "zenith-retail", "Who do we call at Zenith?",
                         "Call Meena in Zenith treasury first, then email the weekly recon extract from the recon-exports bucket.")
        again = run_analysis(self.fed, self.eid, as_of=AS_OF, use_memory=True)
        self.assertLess(again.areas["zenith-retail"].share, before)
        self.assertTrue(any(h["stage"] == "memory" for h in again.areas["zenith-retail"].history))

    def test_accepted_handover_repoints_ownership(self):
        snap = self.first.snapshot()
        sec = next(s for s in snap["outputs"]["handover"]["areas"] if s["system"] == "settlement-batch")
        arch = Archivist(self.ns)
        arch.connect(self.first)
        out = arch.accept_handover(snap, "settlement-batch", sec["successor"]["person"])
        owners = [r for r in out["history"] if not r.get("validTo")]
        self.assertTrue(any(r["to"].endswith(sec["successor"]["person"]) for r in owners))
        again = run_analysis(self.fed, self.eid, as_of=AS_OF, use_memory=True)
        self.assertEqual(again.areas["settlement-batch"].status, "handed_over")

    def test_successor_question_uses_memory(self):
        out = ask(self.fed, self.ns, "Why does recon run at 03:40?", as_of=AS_OF)
        self.assertTrue(out["memory"]["available"])
        self.assertIn("03:15", out["answer"])
        self.assertTrue(any(c["kind"] == "memory" for c in out["context"]))


if __name__ == "__main__":
    unittest.main()
