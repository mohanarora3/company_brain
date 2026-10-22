-- Jira Cloud REST API - Acme Pay
-- Run one statement at a time (SQL Editor) or: python -m lastday zetaris register --source jira
-- Template: placeholders like ${SAAS_PUBLIC_URL} are filled by `python -m lastday zetaris sql`.

CREATE LIGHTNING DATABASE jira_api DESCRIBE BY "Jira Cloud REST API - Acme Pay";

CREATE SCHEMASTORE CONTAINER jira;

CREATE LIGHTNING REST TABLE users_raw FROM jira_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/jira/rest/api/3/users",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW users WITH CONTAINER jira AS
SELECT
    r.`account_id` AS account_id,
    r.`display_name` AS display_name,
    r.`email` AS email,
    r.`time_zone` AS time_zone,
    CAST(r.`active` AS INT) AS active
FROM jira_api.users_raw
LATERAL VIEW explode(values) AS r;

CREATE LIGHTNING REST TABLE issues_raw FROM jira_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/jira/rest/api/3/search",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW issues WITH CONTAINER jira AS
SELECT
    r.`key` AS issue_key,
    r.`project` AS project,
    r.`component` AS component,
    r.`issue_type` AS issue_type,
    r.`summary` AS summary,
    r.`description` AS description,
    r.`status` AS status,
    r.`labels` AS labels,
    r.`assignee_id` AS assignee_id,
    r.`reporter_id` AS reporter_id,
    r.`created` AS created,
    r.`updated` AS updated,
    r.`resolved` AS resolved
FROM jira_api.issues_raw
LATERAL VIEW explode(issues) AS r;

-- Verify (compare with `python -m lastday zetaris check`):
-- SELECT COUNT(*) AS n FROM jira.users;
-- SELECT COUNT(*) AS n FROM jira.issues;
