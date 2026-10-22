-- Confluence-style wiki API - Acme Pay
-- Run one statement at a time (SQL Editor) or: python -m lastday zetaris register --source docs
-- Template: placeholders like ${SAAS_PUBLIC_URL} are filled by `python -m lastday zetaris sql`.

CREATE LIGHTNING DATABASE docs_api DESCRIBE BY "Confluence-style wiki API - Acme Pay";

CREATE SCHEMASTORE CONTAINER docs;

CREATE LIGHTNING REST TABLE pages_raw FROM docs_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/docs/wiki/api/v2/pages",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW pages WITH CONTAINER docs AS
SELECT
    r.`id` AS page_id,
    r.`space` AS space,
    r.`title` AS title,
    r.`labels` AS labels,
    r.`author_id` AS author_id,
    r.`last_editor_id` AS last_editor_id,
    r.`created_at` AS created_at,
    r.`updated_at` AS updated_at,
    r.`body` AS body
FROM docs_api.pages_raw
LATERAL VIEW explode(results) AS r;

-- Verify (compare with `python -m lastday zetaris check`):
-- SELECT COUNT(*) AS n FROM docs.pages;
