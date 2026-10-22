-- Slack Web API - Acme Pay workspace
-- Run one statement at a time (SQL Editor) or: python -m lastday zetaris register --source slack
-- Template: placeholders like ${SAAS_PUBLIC_URL} are filled by `python -m lastday zetaris sql`.

CREATE LIGHTNING DATABASE slack_api DESCRIBE BY "Slack Web API - Acme Pay workspace";

CREATE SCHEMASTORE CONTAINER slack;

CREATE LIGHTNING REST TABLE users_raw FROM slack_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/slack/api/users.list",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW users WITH CONTAINER slack AS
SELECT
    r.`id` AS user_id,
    r.`name` AS name,
    r.`real_name` AS real_name,
    r.`display_name` AS display_name,
    r.`email` AS email,
    r.`title` AS title,
    CAST(r.`deleted` AS INT) AS deleted
FROM slack_api.users_raw
LATERAL VIEW explode(members) AS r;

CREATE LIGHTNING REST TABLE channels_raw FROM slack_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/slack/api/conversations.list",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW channels WITH CONTAINER slack AS
SELECT
    r.`id` AS channel_id,
    r.`name` AS name,
    CAST(r.`is_archived` AS INT) AS is_archived
FROM slack_api.channels_raw
LATERAL VIEW explode(channels) AS r;

CREATE LIGHTNING REST TABLE messages_raw FROM slack_api REQUEST (
  endpoint "${SAAS_PUBLIC_URL}/slack/api/conversations.history",
  method "get",
  response_type "json",
  http_encoding "URLENCODED",
  insecure_ssl "false"
) HEADER (
  Authorization "Bearer ${SAAS_TOKEN}"
) BODY ();

CREATE OR REPLACE SCHEMASTORE VIEW messages WITH CONTAINER slack AS
SELECT
    r.`ts` AS ts,
    r.`thread_ts` AS thread_ts,
    r.`channel` AS channel,
    r.`channel_name` AS channel_name,
    r.`text` AS text,
    r.`created_at` AS created_at,
    r.`parent_user` AS parent_user,
    CAST(r.`is_reply` AS INT) AS is_reply,
    CAST(r.`reply_count` AS INT) AS reply_count,
    r.`user` AS user_id
FROM slack_api.messages_raw
LATERAL VIEW explode(messages) AS r;

-- Verify (compare with `python -m lastday zetaris check`):
-- SELECT COUNT(*) AS n FROM slack.users;
-- SELECT COUNT(*) AS n FROM slack.channels;
-- SELECT COUNT(*) AS n FROM slack.messages;
