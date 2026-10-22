# Handover plan: Priya Raman

Priya Raman leaves in 12 days (03 Nov 2026). 3 critical and 2 at-risk areas need a handover; 3 areas are already covered by others.

## Escalate this week

- **Ledger Reconciliation** (tier 1, 12 days left): transfer recon-db-prod this week; schedule a recorded walkthrough; no current runbook exists; book the exit-interview questions for this area first
- **Unity Bank SFTP** (tier 1, 12 days left): transfer unity-bank-sftp-keys this week; schedule a recorded walkthrough; no current runbook exists; book the exit-interview questions for this area first
- **Zenith Retail account** (tier 1, 12 days left): transfer zenith-retail-escalation-line this week; reassign 1 recurring chore(s): Weekly recon extract for Zenith treasury; schedule a recorded walkthrough; no current runbook exists; book the exit-interview questions for this area first

## Zenith Retail account: critical

Priya holds 80% of the evidence-weighted knowledge of Zenith Retail account (tier 1); the strongest remaining person holds 14%. Backups: Fatima Zahra 14%, Tom Becker 6%. Sources: jira, slack.

**What they know that is not written down**

- Zenith reconciles on their own calendar (Sat-Fri). Send them the weekly recon extract, not the daily one, and call their treasury lead before emailing. _( asked by Lucas Moreau in #cs-escalations on 18 Nov 2025 )_
- Their treasury lead takes the escalation line, not the account manager. The number is on the escalation line we own, it isn't in the CRM. _( asked by Marco Rossi in #cs-escalations on 16 Nov 2025 )_

**Recommended successor:** Fatima Zahra: 14% of the Zenith Retail account activity; on the owning team (Customer Success); 2 open tickets

**Checklist**

- [ ] Pair Fatima Zahra with Priya on Zenith Retail account for the next 10 working days
- [ ] Transfer zenith-retail-escalation-line (owner) to Fatima Zahra; nobody else holds it
- [ ] Reassign recurring chore 'Weekly recon extract for Zenith treasury' (CS-232)
- [ ] Introduce Fatima Zahra to the Zenith Retail contacts before the last day
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: hr_pg:access:zenith-retail-escalation-line, jira:chore:CS-232, jira:issue_done:6a2aaa5459547b4c0547df25@zenith-retail:Done, slack:slack_answer:cs-escalations/1763279714.000000, slack:slack_answer:cs-escalations/1763466435.000000, slack:slack_answer:cs-escalations/1763804412.000000, slack:slack_answer:cs-escalations/1765368112.000000, slack:slack_answer:cs-escalations/1770013593.000000 ... · confidence 75% · Critic: verified</sub>

## Ledger Reconciliation: critical

Priya holds 76% of the evidence-weighted knowledge of Ledger Reconciliation (tier 1); the strongest remaining person holds 10%. Backups: Rahul Verma 10%, Daniel Okafor 10%, Sofia Lindqvist 3%. Sources: github, jira, slack.

**What they know that is not written down**

- 03:40 because the acquirer's late-presentment file lands at 03:15. Moving it earlier silently drops about 0.4% of transactions into the next day and Finance sees phantom breaks. _( asked by Tom Becker in #payments on 24 Mar 2026 )_
- New acquirer = new parser in recon/parsers + a row in recon_overrides + 2 weeks in shadow mode. Never skip shadow mode, the one time we did cost us 3 days of manual matching. _( asked by Chloe Martin in #payments on 22 Jan 2026 )_
- If recon shows a mismatch of exactly the FX fee, it's the T+1 rate snapshot. Rerun recon with --fx-snapshot=settlement-date. Don't adjust the ledger by hand. _( asked by Ananya Gupta in #payments on 05 Feb 2026 )_
- It's noisy on the 1st of every month because of month-end accruals. Silence it for 6 hours on day 1, never longer. _( asked by Meera Iyer in #payments on 16 Nov 2025 )_
- Risk's dispute webhook must carry the original ledger txn id, else recon can't link it. v3 of the webhook has it. _( asked by Hassan Ali in #risk-eng on 27 Oct 2025 )_
- Tolerance rules live in recon/rules.yaml, but the acquirer-specific overrides are in the DB table recon_overrides, not in the repo. That's on purpose so ops can hotfix. _( asked by Chloe Martin in #payments on 03 Nov 2025 )_
- Warehouse lags recon by one run because the export reads the previous checkpoint. A difference of exactly one day's volume is expected. _( asked by Nisha Kapoor in #payments on 11 Feb 2026 )_
- recon replay --date YYYY-MM-DD --dry-run first. The replay writes to the checkpoint table, so never run two replays at once. _( asked by Rahul Varma in #payments on 24 Dec 2025 )_

**Recommended successor:** Rahul Verma: 10% of the Ledger Reconciliation activity; Priya answered their Ledger Reconciliation questions 4 times; on the owning team (Payments); works on neighbouring systems; 0 open tickets

**Checklist**

- [ ] Pair Rahul Verma with Priya on Ledger Reconciliation for the next 10 working days
- [ ] Transfer recon-db-prod (admin) to Rahul Verma; nobody else holds it
- [ ] Write the Ledger Reconciliation runbook from the tacit answers below, reviewed by Priya
- [ ] Fix wiki page 'ADR-014: Idempotency keys scoped to merchant + amount + 24h': last updated 13 months ago; author Priya Raman has notice
- [ ] Fix wiki page 'Recon alert handling': last updated 19 months ago
- [ ] Fix wiki page 'Recon alert handling': says "silence it for 24 hours" but Priya told the team "silence it for 6 hours"
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: docs:doc:4000, github:commit:praman-acme@ledger-recon, github:review:pr1201:praman-acme, github:review:pr1202:praman-acme, github:review:pr1624:praman-acme, hr_pg:access:recon-db-prod, jira:issue_done:6a2aaa5459547b4c0547df25@ledger-recon:Done, jira:issue_open:6a2aaa5459547b4c0547df25@ledger-recon:In Progress ... · confidence 90% · Critic: verified</sub>

## Unity Bank SFTP: critical

Priya holds 23% of the evidence-weighted knowledge of Unity Bank SFTP (tier 1); the strongest remaining person holds 10%. Backups: Meera Iyer 21% (stale), Chloe Martin 20% (stale), Arjun Mehta 19% (stale). Sources: github. Only holder of unity-bank-sftp-keys.

**Recommended successor:** Rahul Verma: on the owning team (Payments); works on neighbouring systems; 0 open tickets

**Checklist**

- [ ] Pair Rahul Verma with Priya on Unity Bank SFTP for the next 10 working days
- [ ] Transfer unity-bank-sftp-keys (key-holder) to Rahul Verma; nobody else holds it
- [ ] Find an owner for 'Rotate Unity Bank SFTP key': unowned since unattributed left
- [ ] Write the Unity Bank SFTP runbook from the tacit answers below, reviewed by Priya
- [ ] Fix wiki page 'Unity Bank SFTP runbook': last updated 20 months ago; author Vikram Nair has left
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: github:review:pr1616:praman-acme, hr_pg:access:unity-bank-sftp-keys, jira:chore:PAY-526 · confidence 50% · Critic: verified</sub>

## Month-end Close: at risk

Priya holds 59% of the evidence-weighted knowledge of Month-end Close (tier 1); the strongest remaining person holds 26%. Backups: Nisha Kapoor 26%, Ananya Gupta 15%. Sources: github, jira, slack.

**Recommended successor:** Nisha Kapoor: 26% of the Month-end Close activity; Priya answered their Month-end Close questions 1 time; on the owning team (Payments); 0 open tickets

**Checklist**

- [ ] Pair Nisha Kapoor with Priya on Month-end Close for the next 10 working days
- [ ] Reassign recurring chore 'Month-end: unmatched > 72h report for Finance' (PAY-508)
- [ ] Write the Month-end Close runbook from the tacit answers below, reviewed by Priya
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: github:review:pr1207:praman-acme, jira:chore:PAY-508, jira:issue_done:6a2aaa5459547b4c0547df25@month-end-close:Done, slack:slack_answer:payments/1761717837.000000, slack:slack_answer:payments/1765880784.000000, slack:slack_answer:payments/1768801831.000000, slack:slack_answer:payments/1779171208.000000, slack:slack_answer:payments/1779969956.000000 ... · confidence 90% · Critic: downgraded</sub>

## Settlement Batch: at risk

Priya holds 64% of the evidence-weighted knowledge of Settlement Batch (tier 1); the strongest remaining person holds 32%. Backups: Rahul Verma 32%, Nisha Kapoor 4%. Sources: github, jira, slack.

**What they know that is not written down**

- Not without a recon checkpoint id. --force needs --checkpoint since INC-231, otherwise you can double settle like we did to Zenith on the Diwali sale. _( asked by Chloe Martin in #payments on 04 May 2026 )_
- No. Recon still matches their transactions; the hold is applied in settlement-batch. _( asked by Nisha Kapoor in #payments on 06 Nov 2025 )_

**Recommended successor:** Rahul Verma: 30% of the Settlement Batch activity; Priya answered their Settlement Batch questions 4 times; on the owning team (Payments); works on neighbouring systems; 0 open tickets

**Checklist**

- [ ] Pair Rahul Verma with Priya on Settlement Batch for the next 10 working days
- [ ] Write the Settlement Batch runbook from the tacit answers below, reviewed by Priya
- [ ] Fix wiki page 'INC-231 postmortem: double settlement to Zenith': last updated 9 months ago; author Priya Raman has notice
- [ ] Answer the exit-interview questions for this area

<sub>Evidence: docs:doc:4002, github:commit:praman-acme@settlement-batch, github:review:pr1195:praman-acme, github:review:pr1196:praman-acme, github:review:pr1197:praman-acme, github:review:pr1198:praman-acme, github:review:pr1199:praman-acme, github:review:pr1200:praman-acme ... · confidence 90% · Critic: downgraded</sub>

## Already covered

- Chargeback Operations: backups Daniel Okafor, Sofia Lindqvist
- Payments Gateway: backups Arjun Mehta, Meera Iyer
- Refunds Service: backups Rahul Verma, Meera Iyer
