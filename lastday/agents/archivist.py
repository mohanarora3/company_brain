"""Archivist: keeps the company's memory in the Meterless engines.

World Model (event-sourced graph, bitemporal edges, source-priority facts):
  * people, their accounts in each system (identity_of edges, with the match method),
    and catalog systems;
  * knows edges with the evidence-weighted share, and owned_by edges for each
    at-risk area; accepting a handover re-points owned_by to the successor,
    which closes the old edge (validTo) instead of deleting it;
  * facts that conflict (a wiki page vs. what the expert said) are asserted
    with their source; the engine's source-priority policy decides which wins.

H-MEM (tiered memory with a trust ledger):
  * the tacit answers the Critic asked for, with Slack provenance;
  * wiki sentences for the same systems, so contradictions surface through
    H-MEM's conflict detection;
  * every exit-interview answer, which later runs read back as written
    knowledge (it lowers risk) and the successor Q&A retrieves with citations.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..config import SETTINGS
from ..meterless.client import Meterless, MeterlessUnavailable, now_iso, prov
from .blackboard import Blackboard

NUMERIC = re.compile(r"\b(\d+(?:\.\d+)?)\s*(hours?|h|days?|minutes?|mins?|weeks?|months?|%|rps)\b", re.I)


FREQ = {"daily": "every 1 days", "weekly": "every 7 days", "fortnightly": "every 14 days", "monthly": "every 30 days",
        "quarterly": "every 90 days", "yearly": "every 365 days", "annually": "every 365 days"}


def claims(text: str) -> list[str]:
    """Short numeric clauses ("silence it for 24 hours") so H-MEM can compare like with like.

    Frequency words become numbers ("monthly" -> "every 30 days"), so "rotate the key monthly" and
    "we rotate it quarterly" read as conflicting numeric values to H-MEM's conflict detector.
    """
    out = []
    for sent in re.split(r"(?<=[.!?;])\s+|[,;()]\s*", text or ""):
        low = sent.lower()
        for k, v in FREQ.items():
            low = re.sub(rf"\b{k}\b", v, low)
        words = re.findall(r"[a-z0-9_%:-]+", low)
        for i, w in enumerate(words):
            if re.fullmatch(r"\d+(\.\d+)?", w) and i + 1 < len(words) and NUMERIC.match(f"{w} {words[i + 1]}"):
                out.append(" ".join(words[max(0, i - 4):i + 2]))
    return out


def _sentences(text: str) -> list[str]:
    body = re.sub(r"^#.*$", "", text or "", flags=re.M)
    body = re.sub(r"^System:.*$", "", body, flags=re.M)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s.strip()) > 25]


class Archivist:
    name = "Archivist"

    def __init__(self, namespace: str):
        self.m = Meterless(namespace)
        self.ns = namespace
        self.ok = False
        self.index_file = Path(SETTINGS.state_dir) / f"hmem-index-{namespace}.json"
        self.index: dict[str, str] = {}

    def connect(self, bb: Blackboard) -> bool:
        try:
            h = self.m.health()
            stats = self.m.hmem_stats()
            self.ok = True
            if self.index_file.exists() and stats.get("memories", 0) > 0:
                self.index = json.loads(self.index_file.read_text())
            bb.emit(self.name, "connect", f"Meterless engines online (H-MEM: {h['engines']['hmem']}, World Model: "
                    f"{h['engines']['worldModel']}); {stats.get('memories', 0)} memories in '{self.ns}'",
                    health=h, hmem=stats)
        except MeterlessUnavailable as e:
            self.ok = False
            bb.emit(self.name, "error", f"Meterless bridge unavailable, continuing without memory: {e}")
        return self.ok

    def _save_index(self) -> None:
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        self.index_file.write_text(json.dumps(self.index))

    def _remember(self, bb: Blackboard, content: str, source: str, **kw) -> str | None:
        key = hashlib.sha1(f"{source}|{content}".encode()).hexdigest()[:16]
        if key in self.index:
            return self.index[key]
        try:
            rec = self.m.remember(content, source, **kw)
        except MeterlessUnavailable as e:
            bb.emit(self.name, "error", f"H-MEM write failed: {e}")
            return None
        self.index[key] = rec["id"]
        bb.memory_log.append({"id": rec["id"], "content": content[:160], "source": source, "tags": kw.get("tags", [])})
        return rec["id"]

    # ------------------------------------------------------------ reads
    def prior(self, bb: Blackboard) -> dict[str, list]:
        """Interview answers captured in earlier sessions, grouped by system."""
        if not self.ok:
            return {}
        eid = bb.target["employee_id"]
        try:
            mems = self.m.memories(tag=f"person:{eid}")
        except MeterlessUnavailable:
            return {}
        out: dict[str, list] = {}
        for m in mems:
            if "kind:interview" in m["tags"] and not (m.get("provenance") or {}).get("label", "").startswith("Claim from"):
                sys_tag = next((t[7:] for t in m["tags"] if t.startswith("system:")), "")
                out.setdefault(sys_tag, []).append({"id": m["id"], "content": m["content"], "confidence": m["confidence"]})
        if out:
            n = sum(len(v) for v in out.values())
            bb.emit(self.name, "recall", f"H-MEM holds {n} exit-interview answer{'s' if n != 1 else ''} from earlier sessions "
                    f"across {len(out)} area{'s' if len(out) != 1 else ''}; {'they count' if n != 1 else 'it counts'} as written knowledge",
                    systems={k: len(v) for k, v in out.items()})
        return out

    # ----------------------------------------------------------- writes
    def seed_world(self, bb: Blackboard) -> None:
        if not self.ok:
            return
        at = now_iso()
        ops = []
        for eid, d in bb.directory.items():
            ops.append({"op": "entity", "type": "person", "externalKey": {"system": "hr", "id": eid}, "name": d["full_name"],
                        "attrs": {"title": d.get("title"), "team": d.get("team"), "status": d.get("status")},
                        "source": prov("hr", "Resolver", at)})
        for sid, s in bb.systems.items():
            ops.append({"op": "entity", "type": "system", "externalKey": {"system": "catalog", "id": sid}, "name": s["name"],
                        "attrs": {"tier": s.get("tier"), "team": s.get("owner_team"), "kind": s.get("kind")},
                        "source": prov("github", "Cartographer", at)})
        for (src, acct), v in bb.account_owner.items():
            if not v.get("person"):
                continue
            ops.append({"op": "entity", "type": "account", "externalKey": {"system": src, "id": acct}, "name": f"{src}:{acct}",
                        "source": prov(src, "Resolver", at)})
            ops.append({"op": "relate", "from": f"account:{src}:{acct}", "type": "identity_of", "to": f"person:hr:{v['person']}",
                        "attrs": {"method": v["method"], "confidence": v["confidence"]},
                        "validFrom": bb.as_of.isoformat(), "source": prov("agent", "Resolver", at, run_id=bb.run_id)})
        try:
            res = self.m.world(ops)
            errs = [r for r in res if isinstance(r, dict) and r.get("error")]
            bb.emit(self.name, "world", f"World Model: {len(ops) - len(errs)} identity and catalog writes "
                    "(people, accounts, identity_of edges, systems)", writes=len(ops), errors=errs[:3])
        except MeterlessUnavailable as e:
            bb.emit(self.name, "error", f"World Model write failed: {e}")

    def record(self, bb: Blackboard) -> None:
        if not self.ok:
            return
        at = now_iso()
        eid = bb.target["employee_id"]
        tname = bb.person_name(eid)
        ops = []
        for a in bb.areas.values():
            sys_ent = f"system:catalog:{a.system}"
            ops.append({"op": "relate", "from": f"person:hr:{eid}", "type": "knows", "to": sys_ent,
                        "attrs": {"share": a.share, "sources": a.sources_used, "run": bb.run_id},
                        "validFrom": bb.as_of.isoformat(), "source": prov("agent", "Analyst", at, run_id=bb.run_id)})
            for b in a.backups[:2]:
                ops.append({"op": "relate", "from": f"person:hr:{b['person']}", "type": "knows", "to": sys_ent,
                            "attrs": {"share": b["share"], "sources": b["sources"]}, "validFrom": bb.as_of.isoformat(),
                            "source": prov("agent", "Analyst", at, run_id=bb.run_id)})
            if a.label != "covered":
                ops.append({"op": "relate", "from": sys_ent, "type": "owned_by", "to": f"person:hr:{eid}",
                            "validFrom": bb.as_of.isoformat(), "attrs": {"basis": "evidence share", "share": a.share},
                            "source": prov("agent", "Analyst", at, run_id=bb.run_id)})
            ops.append({"op": "fact", "about": sys_ent, "predicate": f"departure_risk:{eid}", "value": a.label,
                        "confidence": a.confidence, "source": prov("agent", "Critic", at, run_id=bb.run_id)})
        try:
            self.m.world(ops)
        except MeterlessUnavailable as e:
            bb.emit(self.name, "error", f"World Model write failed: {e}")

        # H-MEM: tacit knowledge and wiki sentences for the areas that matter.
        n_tacit = n_doc = 0
        for a in bb.areas.values():
            if a.label == "covered":
                continue
            for t in a.tacit:
                mid = self._remember(bb, f"{a.name}: {t['question']} -> {t['text']}", f"slack:#{t['channel']}/{t['ts']}",
                                     tags=[f"system:{a.system}", f"person:{eid}", "kind:tacit"], confidence=0.8,
                                     origin="chat_message", label=f"Slack answer by {tname} in #{t['channel']}",
                                     mission=bb.run_id)
                t["memory_id"] = mid
                n_tacit += mid is not None
                for c in claims(t["text"]):
                    self._remember(bb, f"{a.name} claim: {c}", f"slack:#{t['channel']}/{t['ts']}",
                                   tags=[f"system:{a.system}", f"person:{eid}", "kind:tacit"], confidence=0.8,
                                   origin="chat_message", label=f"Claim from {tname}'s Slack answer", mission=bb.run_id)
            for d in a.docs:
                stale = d["age_days"] > 365
                for sent in _sentences(d.get("body", ""))[:6]:
                    mid = self._remember(bb, f"{a.name}: {d['title']} -> {sent}", f"docs:{d['page_id']}",
                                         tags=[f"system:{a.system}", "kind:doc"], confidence=0.55 if stale else 0.7,
                                         origin="document", label=f"Wiki page '{d['title']}' ({d['age_days']} days old)",
                                         mission=bb.run_id)
                    n_doc += mid is not None
                    for c in claims(sent):
                        self._remember(bb, f"{a.name} claim: {c}", f"docs:{d['page_id']}", tags=[f"system:{a.system}", "kind:doc"],
                                       confidence=0.55 if stale else 0.7, origin="document",
                                       label=f"Claim from wiki page '{d['title']}'", mission=bb.run_id)
            best = a.backups[0]["name"] if a.backups else "nobody"
            summary = (f"Verified finding: if {tname} leaves, {a.name} is {a.label.replace('_', ' ')}. "
                       f"Strongest remaining backup: {best}. Critic status: {a.status}.")
            self._remember(bb, summary, f"lastday:run:{bb.run_id}", tags=[f"system:{a.system}", f"person:{eid}", "kind:verdict"],
                           confidence=a.confidence, origin="plan_completion", label="Critic-verified Last Day finding",
                           mission=bb.run_id)
        self._save_index()
        bb.emit(self.name, "memory", f"H-MEM: {n_tacit} tacit answers and {n_doc} wiki sentences stored with provenance",
                tacit=n_tacit, docs=n_doc)
        self.detect_conflicts(bb)

    def detect_conflicts(self, bb: Blackboard) -> list[dict]:
        """H-MEM conflict detection between wiki sentences and what experts said; World Model decides the winner."""
        if not self.ok:
            return []
        try:
            res = self.m.conflicts()
        except MeterlessUnavailable:
            return []
        found = []
        at = now_iso()
        ops = []
        for c in res.get("conflicts", []):
            a, b = c.get("a") or {}, c.get("b") or {}
            kinds = {t for t in a.get("tags", []) + b.get("tags", []) if t.startswith("kind:")}
            if "kind:doc" not in kinds or not kinds & {"kind:tacit", "kind:interview"}:
                continue
            doc, expert = (a, b) if "kind:doc" in a.get("tags", []) else (b, a)
            sysid = next((t[7:] for t in doc.get("tags", []) if t.startswith("system:")), "")
            area = bb.areas.get(sysid)
            if not area:
                continue
            page = next((d for d in area.docs if f"docs:{d['page_id']}" == doc["source"]), {})
            claim_doc = doc["content"].split("claim:", 1)[-1].strip()
            claim_exp = expert["content"].split("claim:", 1)[-1].strip()
            doc_text = next((x for x in _sentences(page.get("body", "")) if claim_doc.split()[-1] in x.lower()),
                            doc["content"].split("->")[-1].strip())
            tacit = next((t for t in area.tacit if expert["source"].endswith(f"/{t['ts']}")), None)
            item = {"system": sysid, "doc": doc_text, "doc_title": page.get("title", doc["source"]), "doc_source": doc["source"],
                    "doc_age_days": page.get("age_days"), "doc_claim": claim_doc, "expert_claim": claim_exp,
                    "expert": tacit["text"] if tacit else expert["content"].split("->")[-1].strip(),
                    "expert_source": expert["source"], "expert_kind": "interview" if "kind:interview" in expert.get("tags", []) else "slack",
                    "reason": c["reason"], "confidence": round(c["confidence"], 2), "memories": [doc["id"], expert["id"]]}
            if any(x["doc_source"] == item["doc_source"] and x["expert_source"] == item["expert_source"] for x in area.conflicts):
                continue
            area.conflicts.append(item)
            found.append(item)
            predicate = "guidance:" + hashlib.sha1(doc["content"].encode()).hexdigest()[:8]
            kind = "interview" if "kind:interview" in expert.get("tags", []) else "slack"
            ops.append({"op": "fact", "about": f"system:catalog:{sysid}", "predicate": predicate,
                        "value": _numbers(doc["content"]) or doc["content"][-80:], "confidence": doc.get("confidence", 0.5),
                        "source": prov("docs", "Archivist", page.get("updated_at") or at, url=doc["source"])})
            ops.append({"op": "fact", "about": f"system:catalog:{sysid}", "predicate": predicate,
                        "value": _numbers(expert["content"]) or expert["content"][-80:], "confidence": expert.get("confidence", 0.8),
                        "source": prov(kind, "Archivist", at, url=expert["source"])})
        if ops:
            try:
                results = self.m.world(ops)
                for item, r in zip(found, results[1::2]):
                    item["world_model_winner"] = next((x["value"] for x in (r.get("rivals") or []) if not x.get("supersededBy")), None)
            except MeterlessUnavailable:
                pass
        for item in found:
            bb.emit(self.name, "conflict", f"Wiki page '{item['doc_title']}' contradicts the expert on "
                    f"{bb.areas[item['system']].name}: '{item['doc_claim']}' vs '{item['expert_claim']}'"
                    + (f"; World Model keeps '{item['world_model_winner']}' (source priority)" if item.get("world_model_winner") else ""),
                    **item)
        return found

    # ------------------------------------------------- interview + handover
    def save_answer(self, bb_or_none, run: dict, system: str, question: str, answer: str) -> dict:
        eid = run["target"]["employee_id"]
        tname = run["target"]["full_name"]
        content = f"{run_area_name(run, system) if system else 'General'}: {question} -> {answer}"
        rec = self.m.remember(content, f"interview:{eid}:{now_iso()}", tags=[f"system:{system}", f"person:{eid}", "kind:interview"],
                              confidence=0.9, origin="chat_message", label=f"Exit interview answer by {tname}",
                              mission=run["run_id"])
        self.m.world([{"op": "fact", "about": f"system:catalog:{system}", "predicate": f"interview:{rec['id']}",
                       "value": answer[:500], "confidence": 0.9, "source": prov("interview", tname)}])
        ids = {rec["id"]}
        for c in claims(answer):
            r2 = self.m.remember(f"{run_area_name(run, system)} claim: {c}", f"interview:{eid}:{now_iso()}",
                                 tags=[f"system:{system}", f"person:{eid}", "kind:interview"], confidence=0.9,
                                 origin="chat_message", label=f"Claim from {tname}'s exit interview", mission=run["run_id"])
            ids.add(r2["id"])
        conflicts = self.m.conflicts()
        mine = [c for c in conflicts.get("conflicts", []) if ids & {c.get("memoryA"), c.get("memoryB")}]
        return {"memory": rec, "conflicts": mine}

    def accept_handover(self, run: dict, system: str, successor_id: str, by: str = "manager") -> dict:
        at = now_iso()
        res = self.m.world([{"op": "relate", "from": f"system:catalog:{system}", "type": "owned_by",
                             "to": f"person:hr:{successor_id}", "validFrom": at[:10] + "T12:00:00Z",
                             "attrs": {"basis": "handover accepted", "run": run["run_id"]}, "source": prov("manual", by, at)}])
        history = self.m.relationships("owned_by", f"system:catalog:{system}")
        return {"result": res, "history": history}


def _numbers(text: str) -> str:
    m = NUMERIC.findall(text or "")
    return ", ".join(f"{a} {b}" for a, b in m)


def run_area_name(run: dict, system: str) -> str:
    for a in run.get("areas", []):
        if a["system"] == system:
            return a["name"]
    return system
