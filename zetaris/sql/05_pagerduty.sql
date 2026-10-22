-- PagerDuty REST API - Acme Pay
-- Run one statement at a time (SQL Editor) or: python -m lastday zetaris register --source pagerduty
-- Optional: register this during the demo to show the Cartographer discovering a new source.
-- Template: placeholders like ${SAAS_PUBLIC_URL} are filled by `python -m lastday zetaris sql`.

CREATE LIGHTNING DATABASE pagerduty_api DESCRIBE BY "PagerDuty REST API - Acme Pay";

CREATE SCHEMASTORE CONTAINER pagerduty;

CREATE LIGHTNING REST TABLE users_raw FROM pagerduty_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/pagerduty/users",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW users WITH CONTAINER pagerduty AS
SELECT
    r.`id` AS user_id,
    r.`name` AS name,
    r.`email` AS email,
    r.`role` AS role
FROM pagerduty_api.users_raw
LATERAL VIEW explode(users) AS r;

CREATE LIGHTNING REST TABLE incidents_raw FROM pagerduty_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/pagerduty/incidents",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW incidents WITH CONTAINER pagerduty AS
SELECT
    r.`id` AS incident_id,
    r.`service` AS service,
    r.`title` AS title,
    r.`urgency` AS urgency,
    r.`status` AS status,
    r.`created_at` AS created_at,
    r.`resolved_at` AS resolved_at,
    r.`resolved_by` AS resolved_by,
    CAST(r.`escalated` AS INT) AS escalated
FROM pagerduty_api.incidents_raw
LATERAL VIEW explode(incidents) AS r;

-- Verify (compare with `python -m lastday zetaris check`):
-- SELECT COUNT(*) AS n FROM pagerduty.users;
-- SELECT COUNT(*) AS n FROM pagerduty.incidents;
