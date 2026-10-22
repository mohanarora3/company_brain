-- Acme Pay HR - Postgres
-- Run one statement at a time (SQL Editor) or: python -m lastday zetaris register --source hr_pg
-- Template: placeholders like ${SAAS_PUBLIC_URL} are filled by `python -m lastday zetaris sql`.

CREATE DATASOURCE hr_pg DESCRIBE BY "Acme Pay HR - Postgres" OPTIONS (
  jdbcdriver "org.postgresql.Driver",
  jdbcurl "${HR_JDBC_URL}",
  username "${HR_PG_USER}",
  password "${HR_PG_PASSWORD}",
  fetchsize "1000"
);

REGISTER DATASOURCE TABLES ("departures", "access_grants") FROM hr_pg;

CREATE DATASOURCE VIEW employees_directory FROM hr_pg AS SELECT employee_id, full_name, preferred_name, work_email, title, team, team_id, manager_id, employment_type, status, start_date, last_day, location FROM employees;

-- Verify (compare with `python -m lastday zetaris check`):
-- SELECT COUNT(*) AS n FROM hr_pg.employees_directory;
-- SELECT COUNT(*) AS n FROM hr_pg.departures;
-- SELECT COUNT(*) AS n FROM hr_pg.access_grants;
