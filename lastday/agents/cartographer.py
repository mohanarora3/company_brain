"""Cartographer: discovers what the federation can see and how the pieces connect.

It reads the Zetaris catalog (Lightning databases, REST tables, JDBC
datasources, column descriptions), profiles each table (row count, time span)
and works out each column's role: identity key, person reference, timestamp,
system link, free text. From that it builds the source map the other agents
plan against, including which investigation probes are possible.

Nothing is hardcoded per source: a table registered later (PagerDuty, say)
with a person column, a time column and a column whose values are service
catalog ids is picked up as a new activity source on the next run.
"""
from __future__ import annotations

import re

from ..federation.base import ident
from .blackboard import Blackboard

PERSON_COL = re.compile(r"(^|_)(user_id|author_login|author_id|assignee_id|last_editor_id|resolved_by|employee_id|account_id|login)$")
TIME_COL = re.compile(r"(^|_)(created_at|created|committed_at|merged_at|updated_at|resolved_at|granted_at|ts)$")
LINK_COL = re.compile(r"(^|_)(component|service|path|base_path|channel_name|system_id|resource|repo_path)$")
TEXT_COL = re.compile(r"(^|_)(text|body|summary|title|message|description)$")
NAME_COL = re.compile(r"(^|_)(name|real_name|display_name|full_name|author_name)$")
EMAIL_COL = re.compile(r"(^|_)(email|work_email|author_email)$")

# Specialised probes and the tables they need. Anything else with the right
# column roles is handled by the generic activity probe.
PROBES = {
    "access": ["hr_pg.access_grants", "hr_pg.employees_directory"],
    "code": ["github.commits", "github.commit_files", "github.service_catalog"],
    "reviews": ["github.pull_requests", "github.service_catalog"],
    "conversation": ["slack.messages", "github.service_catalog"],
    "work": ["jira.issues"],
    "chores": ["jira.issues"],
    "docs": ["docs.pages", "github.service_catalog"],
}
SPECIALISED_TABLES = {"github.commits", "github.commit_files", "github.pull_requests", "slack.messages", "jira.issues",
                      "docs.pages", "hr_pg.access_grants"}


class Cartographer:
    name = "Cartographer"

    def run(self, bb: Blackboard) -> None:
        bb.emit(self.name, "start", "Reading the federation catalog")
        tables = bb.fed.catalog()
        bb.catalog = tables
        status = bb.fed.status()
        bb.emit(self.name, "catalog", f"{len(tables)} tables across {len({t.source for t in tables})} sources on {status.get('label', bb.fed.engine)}",
                engine=bb.fed.engine, tables=[t.qualified for t in tables],
                discovered_via=sorted({t.discovered_via for t in tables if t.discovered_via}))
        have = {t.qualified: t for t in tables}

        # Service catalog first: it is the Rosetta stone between repo paths, channels and components.
        if "github.service_catalog" in have:
            res = bb.sql(self.name, "Load the service catalog", "SELECT system_id, name, kind, owner_team, tier, repo_path, "
                         "slack_channel, jira_component, pagerduty_service, aliases, description FROM github.service_catalog",
                         numeric=("tier",))
            for r in (res.rows if res else []):
                r["alias_list"] = [a.strip().lower() for a in (r.get("aliases") or "").split(",") if a.strip()]
                bb.systems[r["system_id"]] = r
        system_ids = set(bb.systems)

        smap: dict = {}
        for t in tables:
            cols = [c["name"].lower() for c in t.columns]
            pref = ["created_at", "committed_at", "created", "merged_at", "updated_at", "resolved_at", "granted_at", "ts"]
            roles = {
                "person": [c for c in cols if PERSON_COL.search(c)],
                "time": sorted([c for c in cols if TIME_COL.search(c)],
                               key=lambda c: next((i for i, p in enumerate(pref) if c.endswith(p)), 99)),
                "link": [c for c in cols if LINK_COL.search(c)],
                "text": [c for c in cols if TEXT_COL.search(c)],
                "name": [c for c in cols if NAME_COL.search(c)],
                "email": [c for c in cols if EMAIL_COL.search(c)],
            }
            is_identity = t.name in ("users", "employees_directory") or (not roles["time"] and bool(roles["email"]))
            entry = {"table": t.qualified, "source": t.source, "kind": t.kind, "columns": cols, "roles": roles,
                     "identity": bool(is_identity), "detail": t.detail, "discovered_via": t.discovered_via}
            # Profile: size and time span (one cheap aggregate per table).
            tcol = roles["time"][0] if roles["time"] else None
            sel = "COUNT(*) AS n" + (f", MIN({ident(tcol)}) AS first_at, MAX({ident(tcol)}) AS last_at" if tcol else "")
            prof = bb.sql(self.name, f"Profile {t.qualified}", f"SELECT {sel} FROM {t.qualified}", numeric=("n",))
            if prof and prof.rows:
                entry.update({"rows": prof.first("n"), "first_at": prof.first("first_at"), "last_at": prof.first("last_at")})
            # Generic activity: person + time + a column whose values are catalog system ids.
            if not is_identity and roles["person"] and roles["time"] and t.qualified not in SPECIALISED_TABLES:
                for lc in roles["link"]:
                    vals = bb.sql(self.name, f"Check whether {t.qualified}.{lc} links to the service catalog",
                                  f"SELECT DISTINCT {ident(lc)} AS v FROM {t.qualified}")
                    distinct = [str(v) for v in (vals.col("v") if vals else []) if v]
                    hits = [v for v in distinct if v in system_ids]
                    if distinct and len(hits) / len(distinct) >= 0.5:
                        entry["activity"] = {"system_col": lc, "person_col": roles["person"][0], "time_col": roles["time"][0]}
                        break
            smap[t.qualified] = entry

        bb.source_map = smap
        bb.probes_available = {p for p, need in PROBES.items() if all(n in have for n in need)}
        generic = [q for q, e in smap.items() if e.get("activity")]
        for q in generic:
            bb.probes_available.add(f"activity:{q}")
        new = [q for q in generic if q.split(".")[0] not in ("jira", "github", "slack", "docs", "hr_pg")]
        bb.emit(self.name, "source_map", f"{len(bb.probes_available)} probes possible; identity tables: "
                + ", ".join(q for q, e in smap.items() if e["identity"]),
                probes=sorted(bb.probes_available), generic_activity=generic, new_sources=new,
                systems=len(bb.systems))
        if new:
            bb.emit(self.name, "discovery", f"New activity source discovered: {', '.join(new)}. "
                    "It links people to catalog systems, so the Planner will include it.", tables=new)
