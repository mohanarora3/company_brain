# Handover plan: Nisha Kapoor

Nisha Kapoor leaves in 33 days (24 Nov 2026). 3 critical and 2 at-risk areas need a handover; 3 areas are already covered by others.

## Zenith Retail account: critical

Nisha holds 66% of the evidence-weighted knowledge of Zenith Retail account (tier 1); the strongest remaining person holds 18%. Backups: Tom Becker 18%, Felix Wagner 16%. Sources: jira, slack.

**What they know that is not written down**

- Zenith reconciles on their own calendar (Sat-Fri). Send them the weekly recon extract, not the daily one, and call their treasury lead before emailing. _( asked by Arjun Mehta in #cs-escalations on 11 Jan 2026 )_
- Their treasury lead takes the escalation line, not the account manager. The number is on the escalation line we own, it isn't in the CRM. _( asked by Arjun Mehta in #cs-escalations on 10 Jan 2026 )_

**Recommended successor:** Tom Becker: 18% of the Zenith Retail account activity; Nisha answered their Zenith Retail account questions 2 times; on the owning team (Customer Success); 1 open ticket

**Checklist**

- [ ] Pair Tom Becker with Nisha on Zenith Retail account for the next 10 working days
- [ ] Transfer zenith-retail-escalation-line (owner) to Tom Becker; nobody else holds it
- [ ] Reassign recurring chore 'Weekly recon extract for Zenith treasury' (CS-222)
- [ ] Introduce Tom Becker to the Zenith Retail contacts before the last day
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: hr_pg:access:zenith-retail-escalation-line, jira:chore:CS-222, jira:issue_done:c5f3c6e025903b38ed233c69@zenith-retail:Done, slack:slack_answer:cs-escalations/1761474921.000000, slack:slack_answer:cs-escalations/1761744325.000000, slack:slack_answer:cs-escalations/1765009594.000000, slack:slack_answer:cs-escalations/1765618867.000000, slack:slack_answer:cs-escalations/1768032566.000000 ... · confidence 75% · Critic: verified</sub>

## Ledger Reconciliation: critical

Nisha holds 75% of the evidence-weighted knowledge of Ledger Reconciliation (tier 1); the strongest remaining person holds 12%. Backups: Rahul Verma 12%, Hassan Ali 4%. Sources: github, jira, slack.

**What they know that is not written down**

- 03:40 because the acquirer's late-presentment file lands at 03:15. Moving it earlier silently drops about 0.4% of transactions into the next day and Finance sees phantom breaks. _( asked by Priya Raman in #payments on 26 Nov 2025 )_
- New acquirer = new parser in recon/parsers + a row in recon_overrides + 2 weeks in shadow mode. Never skip shadow mode, the one time we did cost us 3 days of manual matching. _( asked by Felix Wagner in #payments on 17 Mar 2026 )_
- If recon shows a mismatch of exactly the FX fee, it's the T+1 rate snapshot. Rerun recon with --fx-snapshot=settlement-date. Don't adjust the ledger by hand. _( asked by Priya Raman in #payments on 06 Mar 2026 )_
- It's noisy on the 1st of every month because of month-end accruals. Silence it for 6 hours on day 1, never longer. _( asked by Meera Iyer in #payments on 29 Nov 2025 )_
- Risk's dispute webhook must carry the original ledger txn id, else recon can't link it. v3 of the webhook has it. _( asked by Hassan Ali in #risk-eng on 11 Dec 2025 )_
- Tolerance rules live in recon/rules.yaml, but the acquirer-specific overrides are in the DB table recon_overrides, not in the repo. That's on purpose so ops can hotfix. _( asked by Rahul Verma in #payments on 17 Dec 2025 )_
- Warehouse lags recon by one run because the export reads the previous checkpoint. A difference of exactly one day's volume is expected. _( asked by Rahul Varma in #payments on 26 Oct 2025 )_
- recon replay --date YYYY-MM-DD --dry-run first. The replay writes to the checkpoint table, so never run two replays at once. _( asked by Kenji Watanabe in #payments on 17 Jan 2026 )_

**Recommended successor:** Rahul Verma: 12% of the Ledger Reconciliation activity; Nisha answered their Ledger Reconciliation questions 4 times; on the owning team (Payments); works on neighbouring systems; 0 open tickets

**Checklist**

- [ ] Pair Rahul Verma with Nisha on Ledger Reconciliation for the next 10 working days
- [ ] Transfer recon-db-prod (admin) to Rahul Verma; nobody else holds it
- [ ] Write the Ledger Reconciliation runbook from the tacit answers below, reviewed by Nisha
- [ ] Fix wiki page 'ADR-014: Idempotency keys scoped to merchant + amount + 24h': last updated 12 months ago; author Nisha Kapoor has notice
- [ ] Fix wiki page 'Recon alert handling': last updated 19 months ago
- [ ] Fix wiki page 'Recon alert handling': says "silence it for 24 hours" but Nisha told the team "silence it for 6 hours"
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: docs:doc:4000, github:commit:nishak@ledger-recon, github:review:pr1184:nishak, github:review:pr1185:nishak, github:review:pr1598:nishak, hr_pg:access:recon-db-prod, jira:issue_done:c5f3c6e025903b38ed233c69@ledger-recon:Done, jira:issue_open:c5f3c6e025903b38ed233c69@ledger-recon:To Do ... · confidence 90% · Critic: verified</sub>

## Unity Bank SFTP: critical

Nisha holds 22% of the evidence-weighted knowledge of Unity Bank SFTP (tier 1); the strongest remaining person holds 21%. Backups: Meera Iyer 21%, Priya Raman 20% (stale), Chloe Martin 19% (stale). Sources: github. Only holder of unity-bank-sftp-keys.

**Recommended successor:** Chloe Martin: on the owning team (Payments); works on neighbouring systems; 0 open tickets

**Checklist**

- [ ] Pair Chloe Martin with Nisha on Unity Bank SFTP for the next 10 working days
- [ ] Transfer unity-bank-sftp-keys (key-holder) to Chloe Martin; nobody else holds it
- [ ] Find an owner for 'Rotate Unity Bank SFTP key': unowned since unattributed left
- [ ] Write the Unity Bank SFTP runbook from the tacit answers below, reviewed by Nisha
- [ ] Fix wiki page 'Unity Bank SFTP runbook': last updated 20 months ago; author Vikram Nair has left
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: github:review:pr1590:nishak, hr_pg:access:unity-bank-sftp-keys, jira:chore:PAY-509 · confidence 50% · Critic: verified</sub>

## Month-end Close: at risk

Nisha holds 63% of the evidence-weighted knowledge of Month-end Close (tier 1); the strongest remaining person holds 25%. Backups: Arjun Mehta 25%, Marco Rossi 12%. Sources: github, jira, slack.

**Recommended successor:** Arjun Mehta: 25% of the Month-end Close activity; Nisha answered their Month-end Close questions 2 times; on the owning team (Payments); 0 open tickets

**Checklist**

- [ ] Pair Arjun Mehta with Nisha on Month-end Close for the next 10 working days
- [ ] Reassign recurring chore 'Month-end: unmatched > 72h report for Finance' (PAY-491)
- [ ] Write the Month-end Close runbook from the tacit answers below, reviewed by Nisha
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: github:commit:nishak@month-end-close, jira:chore:PAY-491, jira:issue_done:c5f3c6e025903b38ed233c69@month-end-close:Done, jira:issue_open:c5f3c6e025903b38ed233c69@month-end-close:To Do, slack:slack_answer:payments/1764825010.000000, slack:slack_answer:payments/1765696753.000000, slack:slack_answer:payments/1769427989.000000, slack:slack_answer:payments/1775658336.000000 ... · confidence 90% · Critic: downgraded</sub>

## Settlement Batch: at risk

Nisha holds 65% of the evidence-weighted knowledge of Settlement Batch (tier 1); the strongest remaining person holds 29%. Backups: Rahul Verma 29%, Arjun Mehta 3%. Sources: github, jira, slack.

**Recommended successor:** Rahul Verma: 28% of the Settlement Batch activity; Nisha answered their Settlement Batch questions 1 time; on the owning team (Payments); works on neighbouring systems; 0 open tickets

**Checklist**

- [ ] Pair Rahul Verma with Nisha on Settlement Batch for the next 10 working days
- [ ] Write the Settlement Batch runbook from the tacit answers below, reviewed by Nisha
- [ ] Fix wiki page 'INC-231 postmortem: double settlement to Zenith': last updated 9 months ago; author Nisha Kapoor has notice
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: docs:doc:4002, github:commit:nishak@settlement-batch, github:review:pr1178:nishak, github:review:pr1179:nishak, github:review:pr1180:nishak, github:review:pr1181:nishak, github:review:pr1182:nishak, github:review:pr1596:nishak ... · confidence 90% · Critic: downgraded</sub>

## Already covered

- Chargeback Operations: backups Hassan Ali, Arjun Mehta
- Refunds Service: backups Chloe Martin, Rahul Verma
- Payments Gateway: backups Priya Raman, Chloe Martin
