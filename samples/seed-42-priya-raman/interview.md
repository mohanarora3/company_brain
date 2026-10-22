# Exit interview: Priya Raman

## Zenith Retail account (critical)

1. You answered 12 questions about Zenith Retail account in #cs-escalations this year; everyone else combined answered 4. What are the three things people keep asking, and where should the answers live?
   <sub>Evidence: slack:slack_answer:cs-escalations/1763279714.000000, slack:slack_answer:cs-escalations/1763466435.000000, slack:slack_answer:cs-escalations/1763804412.000000, slack:slack_answer:cs-escalations/1765368112.000000</sub>
1. You run 'Weekly recon extract for Zenith treasury' every week (CS-232). Walk us through the steps, including anything you do outside the ticket.
   <sub>Evidence: jira:chore:CS-232</sub>
1. You are the only one holding zenith-retail-escalation-line (owner). Is anything tied to your personal accounts or devices, and who should hold it next?
   <sub>Evidence: hr_pg:access:zenith-retail-escalation-line</sub>
1. Who are the people at Zenith Retail you call when something goes wrong, and what do they expect from us that isn't in the CRM?
   <sub>Evidence: slack:slack_answer:cs-escalations/1763466435.000000, slack:slack_answer:cs-escalations/1763279714.000000</sub>

## Ledger Reconciliation (critical)

1. You answered 55 questions about Ledger Reconciliation in #payments this year; everyone else combined answered 25. What are the three things people keep asking, and where should the answers live?
   <sub>Evidence: slack:slack_answer:payments/1761313145.000000, slack:slack_answer:risk-eng/1761558482.000000, slack:slack_answer:payments/1762159871.000000, slack:slack_answer:payments/1763017519.000000</sub>
1. On 24 Mar 2026 you told Tom Becker: "03:40 because the acquirer's late-presentment file lands at 03:15. Moving it earlier silently drops about 0.4% of transactions into the next day and Finance sees phantom..." Is that still true, and what breaks if someone gets it wrong?
   <sub>Evidence: slack:slack_answer:payments/1774338120.000000</sub>
1. The wiki page 'Recon alert handling' says "When recon_break_count fires on the 1st of the month, silence it for 24 hours." but you told the team "It's noisy on the 1st of every month because of month-end accruals. Silence it for 6 hours on day 1, never longer." Which is right today?
   <sub>Evidence: docs:4001, slack:#payments/1763301928.000000</sub>
1. You are the only one holding recon-db-prod (admin). Is anything tied to your personal accounts or devices, and who should hold it next?
   <sub>Evidence: hr_pg:access:recon-db-prod</sub>

## Unity Bank SFTP (critical)

1. You are the only one holding unity-bank-sftp-keys (key-holder). Is anything tied to your personal accounts or devices, and who should hold it next?
   <sub>Evidence: hr_pg:access:unity-bank-sftp-keys</sub>
1. There is no current runbook for Unity Bank SFTP. If it broke at 3am after you left, what should the on-call check first, second and third?

## Month-end Close (at risk)

1. You answered 11 questions about Month-end Close in #payments this year; everyone else combined answered 20. What are the three things people keep asking, and where should the answers live?
   <sub>Evidence: slack:slack_answer:payments/1761717837.000000, slack:slack_answer:payments/1765880784.000000, slack:slack_answer:payments/1768801831.000000, slack:slack_answer:payments/1779171208.000000</sub>
1. You run 'Month-end: unmatched > 72h report for Finance' every month-end (PAY-508). Walk us through the steps, including anything you do outside the ticket.
   <sub>Evidence: jira:chore:PAY-508</sub>
1. There is no current runbook for Month-end Close. If it broke at 3am after you left, what should the on-call check first, second and third?

## Settlement Batch (at risk)

1. You answered 23 questions about Settlement Batch in #payments this year; everyone else combined answered 13. What are the three things people keep asking, and where should the answers live?
   <sub>Evidence: slack:slack_answer:payments/1761383149.000000, slack:slack_answer:payments/1762088791.000000, slack:slack_answer:payments/1762434317.000000, slack:slack_answer:payments/1764940374.000000</sub>
1. On 04 May 2026 you told Chloe Martin: "Not without a recon checkpoint id. --force needs --checkpoint since INC-231, otherwise you can double settle like we did to Zenith on the Diwali sale." Is that still true, and what breaks if someone gets it wrong?
   <sub>Evidence: slack:slack_answer:payments/1777904957.000000</sub>
1. There is no current runbook for Settlement Batch. If it broke at 3am after you left, what should the on-call check first, second and third?
