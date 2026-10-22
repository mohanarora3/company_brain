-- GitHub REST API - acmepay org
-- Run one statement at a time (SQL Editor) or: python -m lastday zetaris register --source github
-- Template: placeholders like ${SAAS_PUBLIC_URL} are filled by `python -m lastday zetaris sql`.

CREATE LIGHTNING DATABASE github_api DESCRIBE BY "GitHub REST API - acmepay org";

CREATE SCHEMASTORE CONTAINER github;

CREATE LIGHTNING REST TABLE users_raw FROM github_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/github/users",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW users WITH CONTAINER github AS
SELECT
    r.`login` AS login,
    r.`name` AS name,
    r.`type` AS account_type
FROM github_api.users_raw
LATERAL VIEW explode(items) AS r;

CREATE LIGHTNING REST TABLE commits_raw FROM github_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/github/commits",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW commits WITH CONTAINER github AS
SELECT
    r.`sha` AS sha,
    r.`author_login` AS author_login,
    r.`author_name` AS author_name,
    r.`author_email` AS author_email,
    r.`committed_at` AS committed_at,
    r.`message` AS message,
    CAST(r.`pr_number` AS INT) AS pr_number
FROM github_api.commits_raw
LATERAL VIEW explode(items) AS r;

CREATE LIGHTNING REST TABLE commit_files_raw FROM github_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/github/commit-files",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW commit_files WITH CONTAINER github AS
SELECT
    r.`sha` AS sha,
    r.`path` AS path,
    CAST(r.`additions` AS INT) AS additions,
    CAST(r.`deletions` AS INT) AS deletions
FROM github_api.commit_files_raw
LATERAL VIEW explode(items) AS r;

CREATE LIGHTNING REST TABLE pull_requests_raw FROM github_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/github/pulls",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW pull_requests WITH CONTAINER github AS
SELECT
    r.`title` AS title,
    r.`author_login` AS author_login,
    r.`created_at` AS created_at,
    r.`merged_at` AS merged_at,
    r.`state` AS state,
    r.`reviewers` AS reviewers,
    r.`base_path` AS base_path,
    CAST(r.`number` AS INT) AS number
FROM github_api.pull_requests_raw
LATERAL VIEW explode(items) AS r;

CREATE LIGHTNING REST TABLE service_catalog_raw FROM github_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/github/catalog",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW service_catalog WITH CONTAINER github AS
SELECT
    r.`system_id` AS system_id,
    r.`name` AS name,
    r.`kind` AS kind,
    r.`owner_team` AS owner_team,
    r.`repo_path` AS repo_path,
    r.`slack_channel` AS slack_channel,
    r.`jira_component` AS jira_component,
    r.`pagerduty_service` AS pagerduty_service,
    r.`aliases` AS aliases,
    r.`description` AS description,
    CAST(r.`tier` AS INT) AS tier
FROM github_api.service_catalog_raw
LATERAL VIEW explode(items) AS r;

-- Verify (compare with `python -m lastday zetaris check`):
-- SELECT COUNT(*) AS n FROM github.users;
-- SELECT COUNT(*) AS n FROM github.commits;
-- SELECT COUNT(*) AS n FROM github.commit_files;
-- SELECT COUNT(*) AS n FROM github.pull_requests;
-- SELECT COUNT(*) AS n FROM github.service_catalog;
