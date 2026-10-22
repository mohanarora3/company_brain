"""Evaluation harness: run the agents on generated companies and score them against ground truth.

    python -m lastday eval --seeds 42 7 13 21

For each seed the generator plants who knows what (including decoys where a
commit-only view would be wrong and keys only one person holds). The agents
never read _ground_truth.json; this harness does, after the run, and reports:

  * label accuracy on every area the truth considers (critical / at_risk / covered),
  * recall and precision of "needs a handover" (critical or at_risk),
  * how many decoys the Critic's corroboration step caught,
  * whether the planted wiki contradiction was found.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .agents.orchestrator import run_analysis
from .config import SETTINGS
from .data.generator import write
from .federation import LocalFederation


def evaluate(seeds: list[int], as_of: date | None = None, use_memory: bool = False, verbose: bool = True) -> dict:
    as_of = as_of or date(2026, 10, 22)
    rows, totals = [], {"areas": 0, "exact": 0, "tp": 0, "fp": 0, "fn": 0, "decoys": 0, "decoys_caught": 0,
                        "conflicts_planted": 0, "conflicts_found": 0, "queries": 0}
    for seed in seeds:
        root = SETTINGS.data_dir / f"seed-{seed}"
        if not (root / "meta.json").exists() or json.loads((root / "meta.json").read_text())["as_of"] != as_of.isoformat():
            write(seed, SETTINGS.data_dir, as_of=as_of)
        truth = json.loads((root / "_ground_truth.json").read_text())
        fed = LocalFederation(root)
        for eid, dep in truth["departures"].items():
            bb = run_analysis(fed, eid, as_of=as_of, use_memory=use_memory)
            totals["queries"] += len(bb.queries)
            got = {a.system: a for a in bb.areas.values()}
            for t in dep["areas"]:
                a = got.get(t["system"])
                pred = a.label if a else "covered"
                totals["areas"] += 1
                totals["exact"] += pred == t["label"]
                need_t, need_p = t["label"] != "covered", pred != "covered"
                totals["tp"] += need_t and need_p
                totals["fp"] += need_p and not need_t
                totals["fn"] += need_t and not need_p
                caught = None
                if t["decoy"]:
                    totals["decoys"] += 1
                    caught = pred != "critical"
                    totals["decoys_caught"] += caught
                rows.append({"seed": seed, "person": dep["name"], "system": t["system"], "truth": t["label"], "pred": pred,
                             "share_truth": t["share"], "share_pred": a.share if a else 0.0, "decoy": t["decoy"],
                             "caught": caught, "status": a.status if a else "not a candidate"})
            if any(c["system"] in got for c in truth["planted_conflicts"]) and eid == _staff_eid(truth, dep):
                totals["conflicts_planted"] += 1
                totals["conflicts_found"] += any(got[c["system"]].conflicts for c in truth["planted_conflicts"] if c["system"] in got)
    p = totals["tp"] / max(1, totals["tp"] + totals["fp"])
    r = totals["tp"] / max(1, totals["tp"] + totals["fn"])
    summary = {"seeds": seeds, "areas": totals["areas"], "label_accuracy": round(totals["exact"] / max(1, totals["areas"]), 3),
               "handover_precision": round(p, 3), "handover_recall": round(r, 3),
               "decoys_caught": f"{totals['decoys_caught']}/{totals['decoys']}",
               "queries": totals["queries"], "rows": rows}
    if use_memory:
        summary["conflicts_found"] = f"{totals['conflicts_found']}/{totals['conflicts_planted']}"
    if verbose:
        for row in rows:
            mark = "ok " if row["truth"] == row["pred"] else "MISS"
            print(f"{mark} seed {row['seed']:>3} {row['person']:<16} {row['system']:<20} truth={row['truth']:<8} "
                  f"pred={row['pred']:<8} share {row['share_truth']:.2f}/{row['share_pred']:.2f}"
                  + (" decoy " + ("caught" if row["caught"] else "MISSED") if row["decoy"] else ""))
        print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    return summary


def _staff_eid(truth: dict, dep: dict) -> str:
    """The planted wiki contradiction is about ledger-recon, whose expert is whoever holds that role."""
    for eid, d in truth["departures"].items():
        if any(a["system"] == "ledger-recon" and a["label"] == "critical" for a in d["areas"]):
            return eid
    return ""


def save(summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2))
