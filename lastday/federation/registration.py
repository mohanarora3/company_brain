"""Generate the Lightning SQL that registers every Acme Pay system in Zetaris.

    python -m lastday zetaris sql            # writes zetaris/sql/generated/*.sql with your endpoints
    python -m lastday zetaris register --yes # runs them one statement at a time

Conventions (the Cartographer agent relies on them to discover new sources):
  * HR is a JDBC datasource `hr_pg`. Only `departures`, `access_grants` and the
    governed `employees_directory` view are registered. The raw `employees`
    table, which holds compensation and personal data, is never registered.
  * Each REST source gets a Lightning database `<source>_api` holding one REST
    table per endpoint (`<table>_raw`), and a SchemaStore container `<source>`
    with one flattening view per table (`<source>.<table>`).
"""
from __future__ import annotations

from pathlib import Path

from ..config import Settings
from .manifest import TABLES, Table

ORDER = ["hr_pg", "slack", "jira", "github", "docs", "pagerduty"]
TITLES = {
    "hr_pg": "Acme Pay HR - Postgres", "slack": "Slack Web API - Acme Pay workspace",
    "jira": "Jira Cloud REST API - Acme Pay", "github": "GitHub REST API - acmepay org",
    "docs": "Confluence-style wiki API - Acme Pay", "pagerduty": "PagerDuty REST API - Acme Pay",
}


def _q(v: str) -> str:
    return '"' + v.replace('"', "") + '"'


def hr_statements(s: Settings, placeholders: bool) -> list[str]:
    url = "${HR_JDBC_URL}" if placeholders else s.hr_jdbc_url
    user = "${HR_PG_USER}" if placeholders else s.hr_pg_user
    pw = "${HR_PG_PASSWORD}" if placeholders else s.hr_pg_password
    directory = next(t for t in TABLES if t.qualified == "hr_pg.employees_directory")
    cols = ", ".join(c.name for c in directory.columns)
    return [
        f'CREATE DATASOURCE hr_pg DESCRIBE BY {_q(TITLES["hr_pg"])} OPTIONS (\n'
        f'  jdbcdriver "org.postgresql.Driver",\n  jdbcurl {_q(url)},\n  username {_q(user)},\n'
        f'  password {_q(pw)},\n  fetchsize "1000"\n)',
        'REGISTER DATASOURCE TABLES ("departures", "access_grants") FROM hr_pg',
        f"CREATE DATASOURCE VIEW employees_directory FROM hr_pg AS SELECT {cols} FROM employees",
    ]


def view_sql(t: Table) -> str:
    fields = []
    for c in t.columns:
        expr = "r." + ".".join(f"`{p}`" for p in c.json_path.split("."))
        if c.type == "int":
            expr = f"CAST({expr} AS INT)"
        elif c.type == "float":
            expr = f"CAST({expr} AS DOUBLE)"
        fields.append(f"    {expr} AS {c.name}")
    return (f"CREATE OR REPLACE SCHEMASTORE VIEW {t.name} WITH CONTAINER {t.source} AS\nSELECT\n" + ",\n".join(fields) +
            f"\nFROM {t.source}_api.{t.name}_raw\nLATERAL VIEW explode({t.root}) AS r")


def rest_statements(source: str, s: Settings, placeholders: bool) -> list[str]:
    base = "${SAAS_PUBLIC_URL}" if placeholders else s.saas_public_url.rstrip("/")
    token = "${SAAS_TOKEN}" if placeholders else s.saas_token
    out = [f"CREATE LIGHTNING DATABASE {source}_api DESCRIBE BY {_q(TITLES[source])}",
           f"CREATE SCHEMASTORE CONTAINER {source}"]
    for t in [t for t in TABLES if t.source == source]:
        out.append(
            f"CREATE LIGHTNING REST TABLE {t.name}_raw FROM {source}_api REQUEST (\n"
            f'  endpoint "{base}{t.endpoint}",\n  method "get",\n  response_type "json",\n'
            f'  http_encoding "URLENCODED",\n  insecure_ssl "false"\n'
            f') HEADER (\n  Authorization "Bearer {token}"\n) BODY ()')
        out.append(view_sql(t))
    return out


def verify_statements(source: str) -> list[str]:
    return [f"SELECT COUNT(*) AS n FROM {t.qualified}" for t in TABLES if t.source == source]


def statements(source: str, s: Settings, placeholders: bool = False) -> list[str]:
    return hr_statements(s, placeholders) if source == "hr_pg" else rest_statements(source, s, placeholders)


def write_files(s: Settings, out_dir: Path, placeholders: bool) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, source in enumerate(ORDER):
        optional = all(t.optional for t in TABLES if t.source == source)
        head = [f"-- {TITLES[source]}",
                "-- Run one statement at a time (SQL Editor) or: python -m lastday zetaris register --source " + source]
        if optional:
            head.append("-- Optional: register this during the demo to show the Cartographer discovering a new source.")
        if placeholders:
            head.append("-- Template: placeholders like ${SAAS_PUBLIC_URL} are filled by `python -m lastday zetaris sql`.")
        body = ";\n\n".join(statements(source, s, placeholders)) + ";\n"
        verify = "\n".join(f"-- {v};" for v in verify_statements(source))
        p = out_dir / f"{i:02d}_{source}.sql"
        p.write_text("\n".join(head) + "\n\n" + body + "\n-- Verify (compare with `python -m lastday zetaris check`):\n" + verify + "\n",
                     encoding="utf-8")
        paths.append(p)
    return paths
