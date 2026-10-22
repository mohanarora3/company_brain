# Handover plan: Kenji Watanabe

Kenji Watanabe leaves in 37 days (28 Nov 2026). 1 critical and 1 at-risk areas need a handover; 4 areas are already covered by others.

## Observability: critical

Kenji holds 74% of the evidence-weighted knowledge of Observability (tier 2); the strongest remaining person holds 26%. Backups: Lucas Moreau 26%. Sources: github, jira, slack.

**What they know that is not written down**

- Only tier 1 SLO burn alerts page. Everything else goes to the morning digest. _( asked by Rahul Verma in #platform on 02 Dec 2025 )_
- They're provisioned from the observability repo, re-run the provisioning job. _( asked by Aisha Bello in #platform on 31 Oct 2025 )_

**Recommended successor:** Lucas Moreau: 26% of the Observability activity; Kenji answered their Observability questions 3 times; on the owning team (Platform); works on neighbouring systems; 2 open tickets

**Checklist**

- [ ] Pair Lucas Moreau with Kenji on Observability for the next 10 working days
- [ ] Transfer grafana-admin (admin) to Lucas Moreau; nobody else holds it
- [ ] Write the Observability runbook from the tacit answers below, reviewed by Kenji
- [ ] Fix wiki page 'Alerting policy': last updated 10 months ago; author Kenji Watanabe has notice
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: docs:doc:4016, github:commit:kwatanabe@observability, github:review:pr1465:kwatanabe, github:review:pr1466:kwatanabe, github:review:pr1467:kwatanabe, github:review:pr1468:kwatanabe, github:review:pr1469:kwatanabe, hr_pg:access:grafana-admin ... · confidence 90% · Critic: verified</sub>

## Kubernetes Platform: at risk

Kenji holds 63% of the evidence-weighted knowledge of Kubernetes Platform (tier 1); the strongest remaining person holds 32%. Backups: Lucas Moreau 32%, Aisha Bello 5%. Sources: github, jira, slack.

**Recommended successor:** Lucas Moreau: 32% of the Kubernetes Platform activity; Kenji answered their Kubernetes Platform questions 9 times; on the owning team (Platform); works on neighbouring systems; 2 open tickets

**Checklist**

- [ ] Pair Lucas Moreau with Kenji on Kubernetes Platform for the next 10 working days
- [ ] Reassign recurring chore 'Scale batch node pool before month-end' (PLAT-368)
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: github:commit:kwatanabe@kubernetes, github:review:pr1448:kwatanabe, github:review:pr1449:kwatanabe, github:review:pr1450:kwatanabe, github:review:pr1451:kwatanabe, github:review:pr1452:kwatanabe, github:review:pr1453:kwatanabe, github:review:pr1454:kwatanabe ... · confidence 90% · Critic: verified</sub>

## Already covered

- Auth Service: backups Aisha Bello, Hassan Ali
- CI/CD Pipeline: backups Lucas Moreau
- Settlement Batch: backups Rahul Verma, Lucas Moreau
- Payments Gateway: backups Arjun Mehta, Meera Iyer
