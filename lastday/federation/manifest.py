"""The federated schema: which systems exist and how each one is exposed.

One manifest drives three things, so they can never drift apart:
  1. the Zetaris registration SQL (Lightning REST tables + SchemaStore views,
     and the governed Postgres datasource for HR),
  2. the local SQLite snapshot used when no Zetaris instance is configured,
  3. a column fallback for Zetaris responses that carry rows without headers.

Agents query the same qualified names on both engines, e.g. `slack.messages`,
`hr_pg.employees_directory`. They never see raw HR tables: the directory view
leaves out salary, personal email, home city and performance rating.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Column:
    name: str
    path: str = ""            # path inside one JSON record; defaults to name
    type: str = "string"      # string | int | float

    @property
    def json_path(self) -> str:
        return self.path or self.name


@dataclass(frozen=True)
class Table:
    source: str               # namespace agents use: slack, jira, github, docs, pagerduty, hr_pg
    name: str
    kind: str                 # rest | jdbc
    endpoint: str = ""        # REST path on the SaaS gateway
    file: str = ""            # snapshot file under data/seed-N/
    root: str = ""            # array field in the JSON response
    columns: tuple = field(default_factory=tuple)
    description: str = ""
    optional: bool = False    # not registered by default (PagerDuty is "discovered" later)

    @property
    def qualified(self) -> str:
        return f"{self.source}.{self.name}"


def C(*names: str, **typed: str) -> tuple:
    cols = [Column(n) for n in names]
    cols += [Column(n, type=t) for n, t in typed.items()]
    return tuple(cols)


TABLES: list[Table] = [
    # --- HR (Postgres, registered in Zetaris as JDBC datasource hr_pg) -------------
    Table("hr_pg", "employees_directory", "jdbc", file="hr/employees.json", root="employees",
          columns=C("employee_id", "full_name", "preferred_name", "work_email", "title", "team", "team_id",
                    "manager_id", "employment_type", "status", "start_date", "last_day", "location"),
          description="Governed employee directory (no compensation or personal data)."),
    Table("hr_pg", "departures", "jdbc", file="hr/departures.json", root="departures",
          columns=C("employee_id", "notice_date", "last_day", "reason_category", "backfill_status"),
          description="Notice periods and last days."),
    Table("hr_pg", "access_grants", "jdbc", file="hr/access_grants.json", root="access_grants",
          columns=C("employee_id", "resource", "level", "granted_at"),
          description="Privileged access by employee (admin consoles, keys, escalation lines)."),
    # --- Slack ---------------------------------------------------------------------
    Table("slack", "users", "rest", "/slack/api/users.list", "slack/users.json", "members",
          (Column("user_id", "id"),) + C("name", "real_name", "display_name", "email", "title", deleted="int"),
          "Slack workspace members."),
    Table("slack", "channels", "rest", "/slack/api/conversations.list", "slack/channels.json", "channels",
          (Column("channel_id", "id"),) + C("name", is_archived="int"), "Slack channels."),
    Table("slack", "messages", "rest", "/slack/api/conversations.history", "slack/messages.json", "messages",
          C("ts", "thread_ts", "channel", "channel_name", "text", "created_at", "parent_user",
            is_reply="int", reply_count="int") + (Column("user_id", "user"),),
          "Messages and thread replies across public channels."),
    # --- Jira ----------------------------------------------------------------------
    Table("jira", "users", "rest", "/jira/rest/api/3/users", "jira/users.json", "values",
          C("account_id", "display_name", "email", "time_zone", active="int"), "Atlassian accounts."),
    Table("jira", "issues", "rest", "/jira/rest/api/3/search", "jira/issues.json", "issues",
          (Column("issue_key", "key"),) + C("project", "component", "issue_type", "summary", "description",
                                            "status", "labels", "assignee_id", "reporter_id", "created",
                                            "updated", "resolved"),
          "Jira issues across all projects."),
    # --- GitHub --------------------------------------------------------------------
    Table("github", "users", "rest", "/github/users", "github/users.json", "items",
          C("login", "name") + (Column("account_type", "type"),), "GitHub org members and bots."),
    Table("github", "commits", "rest", "/github/commits", "github/commits.json", "items",
          C("sha", "author_login", "author_name", "author_email", "committed_at", "message", pr_number="int"),
          "Commits on the main branch of the platform monorepo."),
    Table("github", "commit_files", "rest", "/github/commit-files", "github/commit_files.json", "items",
          C("sha", "path", additions="int", deletions="int"), "Files touched by each commit."),
    Table("github", "pull_requests", "rest", "/github/pulls", "github/pulls.json", "items",
          C("title", "author_login", "created_at", "merged_at", "state", "reviewers", "base_path", number="int"),
          "Merged pull requests with reviewers."),
    Table("github", "service_catalog", "rest", "/github/catalog", "github/catalog.json", "items",
          C("system_id", "name", "kind", "owner_team", "repo_path", "slack_channel", "jira_component",
            "pagerduty_service", "aliases", "description", tier="int"),
          "Backstage-style service catalog (catalog-info.yaml) linking each system to its repo path, channel and component."),
    # --- Docs (Confluence-style) ---------------------------------------------------------
    Table("docs", "pages", "rest", "/docs/wiki/api/v2/pages", "docs/pages.json", "results",
          (Column("page_id", "id"),) + C("space", "title", "labels", "author_id", "last_editor_id", "created_at",
                                         "updated_at", "body"),
          "Wiki pages: runbooks, ADRs, how-tos. Authors are Atlassian account ids."),
    # --- PagerDuty (optional: registered later to show discovery) --------------------
    Table("pagerduty", "users", "rest", "/pagerduty/users", "pagerduty/users.json", "users",
          (Column("user_id", "id"),) + C("name", "email", "role"), "PagerDuty users.", optional=True),
    Table("pagerduty", "incidents", "rest", "/pagerduty/incidents", "pagerduty/incidents.json", "incidents",
          (Column("incident_id", "id"),) + C("service", "title", "urgency", "status", "created_at", "resolved_at",
                                             "resolved_by", escalated="int"),
          "Incidents and who resolved them.", optional=True),
]

BY_NAME = {t.qualified: t for t in TABLES}
SOURCES = sorted({t.source for t in TABLES})

SOURCE_LABELS = {
    "hr_pg": "HR (Postgres)", "slack": "Slack", "jira": "Jira", "github": "GitHub", "docs": "Docs (wiki)",
    "pagerduty": "PagerDuty",
}

# Columns that exist in the HR system but must never be queried by an agent.
BLOCKED_COLUMNS = {"salary_band", "personal_email", "home_city", "performance_rating"}
BLOCKED_TABLES = {"hr_pg.employees"}


def tables(include_optional: bool = True) -> list[Table]:
    return [t for t in TABLES if include_optional or not t.optional]
