"""The fictional company behind the demo: Acme Pay.

Everything here is invented. The generator turns this latent "who knows what"
model into raw records in five separate systems (HR, Slack, Jira, GitHub, Docs)
plus an optional sixth (PagerDuty). The agents never see this file: they only
see what the systems expose through the federation layer.

ROLES are positions in the company. Seed 42 uses the canonical cast below; other
seeds shuffle names inside each team, jitter activity and pick different people
to leave, so the agents have to find the risk instead of memorising it.
"""
from __future__ import annotations

TEAMS = {
    "payments": {"name": "Payments", "slack": "payments", "jira": "PAY"},
    "risk": {"name": "Risk & Fraud", "slack": "risk-eng", "jira": "RISK"},
    "platform": {"name": "Platform", "slack": "platform", "jira": "PLAT"},
    "data": {"name": "Data", "slack": "data", "jira": "DATA"},
    "cs": {"name": "Customer Success", "slack": "cs-escalations", "jira": "CS"},
}

# kind: system | process | customer. tier: 1 (business critical) .. 3.
SYSTEMS = [
    # id, name, kind, team, tier, aliases, description
    ("payments-gateway", "Payments Gateway", "system", "payments", 1, ["gateway", "checkout"],
     "Accepts card and UPI payments from merchants and routes them to acquirers."),
    ("ledger-recon", "Ledger Reconciliation", "system", "payments", 1, ["recon", "reconciliation", "ledger"],
     "Matches the internal ledger against bank and acquirer settlement files every night."),
    ("settlement-batch", "Settlement Batch", "system", "payments", 1, ["settlement", "payouts"],
     "Nightly job that pays merchants out on T+1."),
    ("refunds-service", "Refunds Service", "system", "payments", 2, ["refunds", "refund"],
     "Handles full and partial refunds."),
    ("notification-svc", "Notification Service", "system", "payments", 3, ["notifications", "webhooks"],
     "Merchant webhooks, emails and SMS."),
    ("merchant-dashboard", "Merchant Dashboard", "system", "payments", 2, ["dashboard"],
     "Web dashboard merchants use to see payments and payouts."),
    ("bank-sftp", "Unity Bank SFTP", "system", "payments", 1, ["sftp", "unity bank"],
     "Exchanges settlement files with Unity Bank over SFTP."),
    ("fraud-engine", "Fraud Engine", "system", "risk", 1, ["fraud", "risk rules"],
     "Scores every payment for fraud risk."),
    ("chargeback-ops", "Chargeback Operations", "process", "risk", 2, ["chargebacks", "disputes"],
     "Dispute handling, including the ledger entries for chargebacks."),
    ("kyc-service", "KYC Service", "system", "risk", 2, ["kyc"],
     "Merchant onboarding verification."),
    ("auth-service", "Auth Service", "system", "platform", 1, ["auth", "sso", "vault"],
     "Authentication for merchants and staff."),
    ("kubernetes", "Kubernetes Platform", "system", "platform", 1, ["k8s", "cluster", "aws"],
     "Production clusters everything runs on."),
    ("ci-cd", "CI/CD Pipeline", "system", "platform", 3, ["ci", "deploys"],
     "Build and deploy pipeline."),
    ("observability", "Observability", "system", "platform", 2, ["monitoring", "alerts", "grafana"],
     "Metrics, logs and alerting."),
    ("data-warehouse", "Data Warehouse", "system", "data", 2, ["warehouse", "dwh"],
     "Analytics warehouse fed from all services."),
    ("finance-reporting", "Finance Reporting", "system", "data", 2, ["finance reports"],
     "Reports Finance uses for revenue and month-end."),
    ("month-end-close", "Month-end Close", "process", "payments", 1, ["month end", "close"],
     "The monthly books-closing process with Finance."),
    ("pci-audit", "PCI DSS Audit", "process", "platform", 2, ["pci", "compliance"],
     "Yearly PCI compliance audit."),
    ("zenith-retail", "Zenith Retail account", "customer", "cs", 1, ["zenith"],
     "Largest merchant: 31% of processed volume."),
    ("bluebird-airlines", "Bluebird Airlines account", "customer", "cs", 2, ["bluebird"],
     "Airline merchant with heavy refunds."),
]

SYSTEM_IDS = [s[0] for s in SYSTEMS]

# Role -> canonical person. activity = events per month per system (latent).
# source_bias tweaks how that knowledge shows up in each system, which is how
# decoys are planted (someone who dominates commits but not the conversation).
ROLES = [
    {"role": "payments-staff", "team": "payments", "title": "Staff Engineer", "senior": True,
     "activity": {"ledger-recon": 7.0, "settlement-batch": 2.6, "chargeback-ops": 1.4, "payments-gateway": 0.6,
                  "zenith-retail": 1.3, "month-end-close": 1.4, "refunds-service": 0.4}},
    {"role": "payments-senior", "team": "payments", "title": "Senior Engineer", "senior": True,
     "activity": {"payments-gateway": 6.0, "refunds-service": 1.6, "notification-svc": 0.9, "merchant-dashboard": 0.4,
                  "bluebird-airlines": 0.5}},
    {"role": "payments-eng-1", "team": "payments", "title": "Engineer",
     "activity": {"payments-gateway": 4.2, "refunds-service": 3.0, "notification-svc": 0.7}},
    {"role": "payments-eng-2", "team": "payments", "title": "Engineer",
     "activity": {"refunds-service": 3.4, "settlement-batch": 1.1, "ledger-recon": 0.35, "payments-gateway": 0.3}},
    {"role": "payments-em", "team": "payments", "title": "Engineering Manager",
     "activity": {"payments-gateway": 0.3, "month-end-close": 0.9, "pci-audit": 1.0, "settlement-batch": 0.2}},
    {"role": "payments-frontend", "team": "payments", "title": "Frontend Engineer", "senior": True,
     "activity": {"merchant-dashboard": 4.6, "notification-svc": 1.4},
     "source_bias": {"merchant-dashboard": {"slack": 0.25, "jira": 0.35, "pagerduty": 0.2}}},
    {"role": "risk-lead", "team": "risk", "title": "Risk Lead", "senior": True,
     "activity": {"fraud-engine": 5.0, "chargeback-ops": 2.6, "kyc-service": 0.9}},
    {"role": "risk-ml", "team": "risk", "title": "ML Engineer",
     "activity": {"fraud-engine": 4.4, "chargeback-ops": 1.2, "data-warehouse": 0.6}},
    {"role": "risk-eng", "team": "risk", "title": "Engineer",
     "activity": {"kyc-service": 4.2, "auth-service": 1.0, "fraud-engine": 0.8}},
    {"role": "platform-principal", "team": "platform", "title": "Principal SRE", "senior": True,
     "activity": {"kubernetes": 5.2, "observability": 3.2, "ci-cd": 1.6, "payments-gateway": 0.3},
     "source_bias": {"kubernetes": {"pagerduty": 0.5, "jira": 0.6}}},
    {"role": "platform-eng", "team": "platform", "title": "Platform Engineer",
     "activity": {"ci-cd": 4.0, "kubernetes": 2.2, "auth-service": 0.8, "observability": 0.9},
     "source_bias": {"kubernetes": {"pagerduty": 2.4, "jira": 1.8, "slack": 1.3}}},
    {"role": "platform-security", "team": "platform", "title": "Security Engineer", "senior": True,
     "activity": {"auth-service": 4.2, "pci-audit": 2.6, "kubernetes": 0.5}},
    {"role": "data-eng", "team": "data", "title": "Data Engineer", "senior": True,
     "activity": {"data-warehouse": 5.0, "finance-reporting": 3.0, "month-end-close": 0.5}},
    {"role": "data-analytics", "team": "data", "title": "Analytics Engineer",
     "activity": {"finance-reporting": 3.4, "data-warehouse": 2.0, "merchant-dashboard": 0.6}},
    {"role": "data-contractor", "team": "data", "title": "Data Engineer (Contractor)", "contractor": True,
     "activity": {"data-warehouse": 1.6, "finance-reporting": 0.8}},
    {"role": "cs-am", "team": "cs", "title": "Account Manager", "senior": True,
     "activity": {"bluebird-airlines": 3.0, "zenith-retail": 0.35, "merchant-dashboard": 0.5}},
    {"role": "cs-support", "team": "cs", "title": "Support Lead",
     "activity": {"merchant-dashboard": 2.4, "refunds-service": 0.5, "zenith-retail": 0.2},
     "source_bias": {"merchant-dashboard": {"slack": 3.2, "jira": 3.0, "github": 0.05}}},
    {"role": "payments-alumnus", "team": "payments", "title": "Senior Engineer", "left": True,
     "activity": {"bank-sftp": 4.2, "settlement-batch": 1.8, "ledger-recon": 0.5}},
]

# Canonical cast for seed 42 (role -> person). Each person has deliberately
# inconsistent identities across tools, the way real companies do.
CAST = {
    "payments-staff": {"name": "Priya Raman", "slack": "priya.r", "slack_display": "Priya", "jira": "Priya R.",
                        "github": "praman-acme", "alt_email": "priya@ramanhome.example"},
    "payments-senior": {"name": "Arjun Mehta", "slack": "arjun", "slack_display": "Arjun M", "jira": "Arjun Mehta",
                         "github": "arjunm"},
    "payments-eng-1": {"name": "Meera Iyer", "slack": "meera.iyer", "slack_display": "Meera", "jira": "Meera Iyer",
                        "github": "meera-i"},
    "payments-eng-2": {"name": "Rahul Verma", "slack": "rahul", "slack_display": "Rahul V", "jira": "Rahul V",
                        "github": "rverma", "hide_slack_email": True},
    "payments-em": {"name": "Nisha Kapoor", "slack": "nisha.k", "slack_display": "Nisha", "jira": "Nisha Kapoor",
                     "github": "nishak"},
    "payments-frontend": {"name": "Chloe Martin", "slack": "chloe", "slack_display": "Chloe M", "jira": "Chloe Martin",
                           "github": "chloe-codes"},
    "risk-lead": {"name": "Daniel Okafor", "slack": "dokafor", "slack_display": "Daniel O.", "jira": "Daniel Okafor",
                   "github": "dokafor"},
    "risk-ml": {"name": "Sofia Lindqvist", "slack": "sofia", "slack_display": "Sofia L", "jira": "Sofia Lindqvist",
                 "github": "sofialq"},
    "risk-eng": {"name": "Hassan Ali", "slack": "hassan", "slack_display": "Hassan", "jira": "Hassan Ali",
                  "github": "hassan-ali"},
    "platform-principal": {"name": "Kenji Watanabe", "slack": "kenji", "slack_display": "Kenji W", "jira": "Kenji Watanabe",
                            "github": "kwatanabe"},
    "platform-eng": {"name": "Lucas Moreau", "slack": "lucas", "slack_display": "Lucas", "jira": "Lucas Moreau",
                      "github": "lmoreau"},
    "platform-security": {"name": "Aisha Bello", "slack": "aisha.b", "slack_display": "Aisha", "jira": "Aisha Bello",
                           "github": "aishab"},
    "data-eng": {"name": "Ananya Gupta", "slack": "ananya", "slack_display": "Ananya G", "jira": "Ananya Gupta",
                  "github": "ananya-g"},
    "data-analytics": {"name": "Marco Rossi", "slack": "marco", "slack_display": "Marco", "jira": "Marco Rossi",
                        "github": "mrossi"},
    "data-contractor": {"name": "Rahul Varma", "slack": "rahul.varma", "slack_display": "Rahul V.", "jira": "Rahul Varma",
                         "github": "rahulvarma-dev"},
    "cs-am": {"name": "Fatima Zahra", "slack": "fatima", "slack_display": "Fatima Z", "jira": "Fatima Zahra",
               "github": None},
    "cs-support": {"name": "Tom Becker", "slack": "tom", "slack_display": "Tom B", "jira": "Tom Becker",
                    "github": "tbecker"},
    "payments-alumnus": {"name": "Vikram Nair", "slack": "vikram", "slack_display": "Vikram N", "jira": "Vikram Nair",
                          "github": "vnair"},
}

# Extra names used when a seed reshuffles the cast.
SPARE_NAMES = [
    ("Kavya Menon", "kavya"), ("Omar Haddad", "omar.h"), ("Ines Duarte", "ines"), ("Wei Zhang", "weiz"),
    ("Grace Mensah", "grace.m"), ("Mateo Alvarez", "mateo"), ("Yuki Sato", "yuki"), ("Leah Cohen", "leahc"),
    ("Arnav Shah", "arnav"), ("Noor Rahman", "noor"), ("Felix Wagner", "felix.w"), ("Sara Novak", "sara.n"),
]

# Admin access that only certain roles hold. "exclusive" grants are the
# classic last-day trap: keys and consoles nobody else can open.
ACCESS = [
    # role, system resource, level
    ("payments-staff", "recon-db-prod", "admin"),
    ("payments-staff", "unity-bank-sftp-keys", "key-holder"),
    ("payments-staff", "zenith-retail-escalation-line", "owner"),
    ("payments-em", "recon-db-prod", "read"),
    ("platform-principal", "aws-prod-admin", "admin"),
    ("platform-eng", "aws-prod-admin", "admin"),
    ("platform-principal", "grafana-admin", "admin"),
    ("platform-security", "vault-admin", "admin"),
    ("platform-principal", "vault-admin", "admin"),
    ("platform-security", "pci-evidence-locker", "owner"),
    ("data-eng", "warehouse-admin", "admin"),
    ("data-analytics", "warehouse-admin", "admin"),
    ("risk-lead", "fraud-rules-console", "admin"),
    ("risk-ml", "fraud-rules-console", "admin"),
    ("payments-senior", "acquirer-portal", "admin"),
    ("payments-eng-1", "acquirer-portal", "admin"),
    ("cs-am", "bluebird-airlines-escalation-line", "owner"),
    ("cs-support", "bluebird-airlines-escalation-line", "backup"),
]

# Which system each access resource protects.
ACCESS_SYSTEM = {
    "recon-db-prod": "ledger-recon",
    "unity-bank-sftp-keys": "bank-sftp",
    "zenith-retail-escalation-line": "zenith-retail",
    "aws-prod-admin": "kubernetes",
    "grafana-admin": "observability",
    "vault-admin": "auth-service",
    "pci-evidence-locker": "pci-audit",
    "warehouse-admin": "data-warehouse",
    "fraud-rules-console": "fraud-engine",
    "acquirer-portal": "payments-gateway",
    "bluebird-airlines-escalation-line": "bluebird-airlines",
}

# Tacit knowledge: what an expert says in Slack threads. {asker} is filled in.
# These are the facts the handover and the exit interview must preserve.
TIPS = {
    "ledger-recon": [
        ("Recon mismatch equal to the FX fee?",
         "If recon shows a mismatch of exactly the FX fee, it's the T+1 rate snapshot. Rerun recon with "
         "--fx-snapshot=settlement-date. Don't adjust the ledger by hand."),
        ("Why does recon run at 03:40 and not 02:00?",
         "03:40 because the acquirer's late-presentment file lands at 03:15. Moving it earlier silently drops "
         "about 0.4% of transactions into the next day and Finance sees phantom breaks."),
        ("Unity Bank file arrived twice, is recon double counting?",
         "Unity Bank sometimes re-sends the settlement file with a new name after 02:00. Recon dedupes on the "
         "file's trailer hash, not the filename. Check the trailer, not the name."),
        ("Where do the recon tolerance rules live?",
         "Tolerance rules live in recon/rules.yaml, but the acquirer-specific overrides are in the DB table "
         "recon_overrides, not in the repo. That's on purpose so ops can hotfix."),
        ("Recon break after a partial refund, what now?",
         "Partial refunds create two ledger lines and recon pairs them by refund_group_id. Older clients send an "
         "empty refund_group_id. Backfill the id and rerun."),
        ("The recon_break_count alert is screaming on the 1st again",
         "It's noisy on the 1st of every month because of month-end accruals. Silence it for 6 hours on day 1, "
         "never longer."),
        ("How do I replay a recon day?",
         "recon replay --date YYYY-MM-DD --dry-run first. The replay writes to the checkpoint table, so never run "
         "two replays at once."),
        ("Adding a new acquirer to recon?",
         "New acquirer = new parser in recon/parsers + a row in recon_overrides + 2 weeks in shadow mode. Never "
         "skip shadow mode, the one time we did cost us 3 days of manual matching."),
        ("Warehouse numbers don't match recon",
         "Warehouse lags recon by one run because the export reads the previous checkpoint. A difference of exactly "
         "one day's volume is expected."),
    ],
    "settlement-batch": [
        ("Settlement batch timed out, can I rerun with --force?",
         "Not without a recon checkpoint id. --force needs --checkpoint since INC-231, otherwise you can double "
         "settle like we did to Zenith on the Diwali sale."),
        ("Merchant on settlement hold, should recon pause?",
         "No. Recon still matches their transactions; the hold is applied in settlement-batch."),
        ("When does T+1 payout actually leave?",
         "Payout files go to Unity Bank at 06:10 after recon signs off the checkpoint."),
    ],
    "month-end-close": [
        ("What does Finance need from us at month-end?",
         "Finance needs the 'unmatched > 72h' report by day 2. Generate it with recon_report.py --aging=72; "
         "anything under 72h is timing noise."),
        ("Month-end won't balance, chargebacks again?",
         "Chargebacks must post to the suspense account first (acct 2190), never against merchant balance. Risk "
         "marks the outcome, then recon moves it."),
    ],
    "zenith-retail": [
        ("Zenith says settlement is short again",
         "Zenith reconciles on their own calendar (Sat-Fri). Send them the weekly recon extract, not the daily one, "
         "and call their treasury lead before emailing."),
        ("Who do we call at Zenith for an outage?",
         "Their treasury lead takes the escalation line, not the account manager. The number is on the escalation "
         "line we own, it isn't in the CRM."),
    ],
    "payments-gateway": [
        ("Gateway 502s from acquirer B",
         "Acquirer B rate-limits at 300 rps per merchant. The gateway backs off automatically; if it persists, flip "
         "the routing weight in gateway/routing.yaml."),
        ("Idempotency keys on the gateway?",
         "Gateway uses the request id but the ledger keys on merchant + amount + 24h window, see ADR-014."),
        ("UPI callbacks arriving late",
         "UPI callbacks can lag up to 20 minutes. Don't mark them failed before the 30 minute sweep."),
    ],
    "refunds-service": [
        ("Partial refund stuck in pending",
         "Pending refunds over 48h need the acquirer refund reference; requeue with refunds requeue --ref."),
        ("Bluebird bulk refunds",
         "Bluebird sends refunds in bulk after cancellations. Throttle to 50/s or the acquirer rejects them."),
    ],
    "merchant-dashboard": [
        ("Merchant can't see payouts on the dashboard",
         "Payout widget reads finance-reporting, which lags a day. Tell them T+1 and check the export job."),
        ("Dashboard login loop for a merchant",
         "Clear their SSO session in auth-service admin; it's almost never the dashboard."),
        ("CSV export times out for big merchants",
         "Use the async export toggle in the merchant settings; the sync path caps at 50k rows."),
    ],
    "kubernetes": [
        ("Node pool upgrade order?",
         "Upgrade the system pool first, then payments, then batch. Batch last because settlement can't move."),
        ("Pods evicted on the batch pool",
         "Batch pool is memory-tight on the 1st. Scale it to 6 nodes before month-end."),
        ("How do we get into prod in an emergency?",
         "Break-glass role via aws-prod-admin; it pages the platform on-call automatically."),
    ],
    "observability": [
        ("Which alerts page at night?",
         "Only tier 1 SLO burn alerts page. Everything else goes to the morning digest."),
        ("Grafana dashboards missing after migration",
         "They're provisioned from the observability repo, re-run the provisioning job."),
    ],
    "fraud-engine": [
        ("Fraud score spiking for one merchant",
         "Check if they launched a sale; the velocity rule doesn't know about campaigns. Add a temporary allowlist."),
        ("How are fraud rules deployed?",
         "Rules go through the fraud-rules console with two-person approval. Never edit rules.json in prod."),
    ],
    "chargeback-ops": [
        ("Dispute webhook missing the txn id",
         "Risk's dispute webhook must carry the original ledger txn id, else recon can't link it. v3 of the webhook "
         "has it."),
    ],
    "kyc-service": [
        ("KYC vendor timeouts",
         "KYC vendor has a 10s SLA; retries are safe because requests carry our onboarding id."),
    ],
    "auth-service": [
        ("Rotating the SSO signing key",
         "Rotate the SSO signing key every 90 days via vault; the old key must stay valid for 24h."),
    ],
    "ci-cd": [
        ("Deploy stuck on approval",
         "Tier 1 services need a second approver from the owning team; ping them in the deploy thread."),
    ],
    "data-warehouse": [
        ("Warehouse load late",
         "The nightly load waits for the recon checkpoint. If recon is late, so is the warehouse."),
        ("Which warehouse tables are PII?",
         "Anything in the raw_ schema. Only the curated_ schema is cleared for analysts."),
    ],
    "finance-reporting": [
        ("Revenue report off by a day",
         "Finance reporting is in UTC; Finance reads it in IST. Use the _ist views."),
    ],
    "bank-sftp": [
        ("Unity Bank SFTP key expiring?",
         "The SFTP key is rotated through the bank's partner portal; they need 5 working days notice."),
        ("SFTP connection refused from the new NAT",
         "Unity Bank allowlists our egress IPs; new NAT IPs need a change request on their portal."),
    ],
    "bluebird-airlines": [
        ("Bluebird asking for refund status",
         "Bluebird wants a daily refund status file, not emails. It's generated by refunds-service at 07:00."),
    ],
    "notification-svc": [
        ("Webhook retries for a merchant",
         "Webhooks retry with backoff for 24h, then land in the dead-letter queue."),
    ],
    "pci-audit": [
        ("Where is last year's PCI evidence?",
         "In the PCI evidence locker; the auditor gets read access for the audit window only."),
    ],
}

GENERIC_QUESTIONS = [
    "Anyone know why {system} is slow today?",
    "Who can review my {system} PR?",
    "Is {system} deploying today?",
    "Quick one about {system}: is there a runbook?",
    "Seeing errors in {system} logs, known issue?",
    "How do I test {system} locally?",
]

GENERIC_ANSWERS = [
    "Looking now, give me 10 minutes.",
    "Known issue, fix is in review.",
    "Yes, there's a flag for that in the config. I'll send you the PR.",
    "Ping me after standup and I'll walk you through it.",
    "That's expected after the last deploy, it settles in an hour.",
    "I'll take it, assigning to myself.",
]

CHATTER = [
    "Lunch at 1?", "Deploy done.", "Standup moved to 10:30 today.", "Thanks!", "Nice work on the release.",
    "Who broke the build? :)", "Reminder: retro on Friday.", "Coffee anyone?",
]

COMMIT_VERBS = ["fix", "refactor", "add", "update", "handle", "remove", "tune", "log"]
COMMIT_OBJECTS = ["edge case", "retry logic", "config", "metrics", "tests", "parser", "timeouts", "error handling",
                  "batch size", "feature flag"]
FILES = {
    "ledger-recon": ["recon/engine.py", "recon/rules.yaml", "recon/parsers/unity.py", "recon/parsers/acquirer_b.py",
                     "recon/checkpoint.py", "recon/report.py"],
    "settlement-batch": ["settlement/batch.py", "settlement/payout_file.py", "settlement/holds.py"],
    "payments-gateway": ["gateway/router.py", "gateway/routing.yaml", "gateway/acquirers.py", "gateway/upi.py"],
    "refunds-service": ["refunds/api.py", "refunds/queue.py", "refunds/partial.py"],
    "notification-svc": ["notify/webhooks.py", "notify/email.py"],
    "merchant-dashboard": ["dashboard/src/Payouts.tsx", "dashboard/src/Export.tsx", "dashboard/src/api.ts"],
    "bank-sftp": ["sftp/client.py", "sftp/keys.md", "sftp/schedule.py"],
    "fraud-engine": ["fraud/rules.py", "fraud/model.py", "fraud/velocity.py"],
    "chargeback-ops": ["chargebacks/webhook.py", "chargebacks/suspense.py"],
    "kyc-service": ["kyc/vendor.py", "kyc/onboarding.py"],
    "auth-service": ["auth/sso.py", "auth/sessions.py", "auth/keys.py"],
    "kubernetes": ["infra/k8s/pools.tf", "infra/k8s/batch-pool.yaml", "infra/k8s/upgrade.md"],
    "ci-cd": ["ci/pipeline.yml", "ci/deploy.sh"],
    "observability": ["observability/alerts.yaml", "observability/dashboards.json"],
    "data-warehouse": ["warehouse/load.sql", "warehouse/models/curated.sql"],
    "finance-reporting": ["reporting/revenue.sql", "reporting/ist_views.sql"],
    "month-end-close": ["ops/month_end/checklist.md", "ops/month_end/recon_report.py"],
    "pci-audit": ["compliance/pci/controls.md"],
}

# Documents per system: (title, kind, author_role, months_since_update, body).
# Missing runbooks and stale docs are part of the story. Two docs contradict
# what experts say in Slack: the conflict detector should catch them.
DOCS = [
    ("ledger-recon", "ADR-014: Idempotency keys scoped to merchant + amount + 24h", "adr", "payments-staff", 13,
     "We key ledger writes on (merchant_id, amount_minor, currency, 24h bucket) instead of the gateway request id, "
     "because two acquirers retry with different request ids. Using request ids caused double postings."),
    ("ledger-recon", "Recon alert handling", "howto", "payments-em", 19,
     "When recon_break_count fires on the 1st of the month, silence it for 24 hours. Month-end accruals cause "
     "temporary breaks."),
    ("settlement-batch", "INC-231 postmortem: double settlement to Zenith", "postmortem", "payments-staff", 9,
     "Root cause: settlement batch rerun with --force bypassed the recon idempotency guard. Fix: --force requires "
     "a recon checkpoint id."),
    ("payments-gateway", "Payments Gateway runbook", "runbook", "payments-senior", 3,
     "Routing weights live in gateway/routing.yaml. Acquirer B rate limits at 300 rps per merchant. On-call checks "
     "the acquirer status page first."),
    ("payments-gateway", "Gateway architecture overview", "overview", "payments-senior", 7,
     "The gateway routes payments to acquirers by weight and handles UPI callbacks asynchronously."),
    ("refunds-service", "Refunds runbook", "runbook", "payments-eng-1", 5,
     "Requeue stuck refunds with refunds requeue --ref. Bluebird bulk refunds must be throttled to 50 per second."),
    ("merchant-dashboard", "Merchant Dashboard support guide", "runbook", "cs-support", 2,
     "Payout widget lags a day (finance-reporting). Login loops are auth-service sessions. Big CSV exports use the "
     "async toggle."),
    ("bank-sftp", "Unity Bank SFTP runbook", "runbook", "payments-alumnus", 20,
     "Rotate the SFTP key monthly through the partner portal. Unity Bank allowlists our egress IPs."),
    ("fraud-engine", "Fraud rules: how to deploy", "runbook", "risk-lead", 4,
     "Rules are deployed through the fraud-rules console with two-person approval."),
    ("fraud-engine", "Fraud model retraining", "howto", "risk-ml", 6,
     "Retrain monthly from the curated warehouse features; shadow for a week before promoting."),
    ("chargeback-ops", "Chargeback process", "overview", "risk-lead", 8,
     "Disputes post to suspense account 2190 before recon moves them."),
    ("kyc-service", "KYC vendor integration", "runbook", "risk-eng", 5,
     "Vendor SLA is 10s; requests are idempotent on onboarding id."),
    ("auth-service", "SSO key rotation runbook", "runbook", "platform-security", 3,
     "Rotate every 90 days via vault; keep the old key valid for 24h."),
    ("kubernetes", "Cluster upgrade runbook", "runbook", "platform-eng", 2,
     "Upgrade order: system pool, payments, batch. Scale batch pool to 6 nodes before month-end."),
    ("kubernetes", "Break-glass access", "runbook", "platform-eng", 4,
     "Use the aws-prod-admin break-glass role; it pages platform on-call."),
    ("ci-cd", "Deploy approvals", "howto", "platform-eng", 6,
     "Tier 1 services need a second approver from the owning team."),
    ("observability", "Alerting policy", "overview", "platform-principal", 10,
     "Only tier 1 SLO burn alerts page at night."),
    ("data-warehouse", "Warehouse data map", "overview", "data-eng", 4,
     "raw_ schema has PII; curated_ is cleared for analysts. Nightly load waits on the recon checkpoint."),
    ("finance-reporting", "Finance reporting timezones", "howto", "data-analytics", 5,
     "Reports are UTC; use the _ist views for Finance."),
    ("pci-audit", "PCI audit playbook", "runbook", "platform-security", 11,
     "Evidence lives in the PCI evidence locker; auditors get time-boxed read access."),
    ("bluebird-airlines", "Bluebird account notes", "overview", "cs-am", 3,
     "Bluebird wants a daily refund status file at 07:00."),
    ("notification-svc", "Webhook delivery", "overview", "payments-senior", 9,
     "Webhooks retry for 24h then go to the dead-letter queue."),
]

# Recurring operational chores in Jira. If the owner leaves, these silently stop.
RECURRING = [
    ("month-end-close", "Month-end: unmatched > 72h report for Finance", "payments-staff"),
    ("bank-sftp", "Rotate Unity Bank SFTP key", "payments-alumnus"),
    ("auth-service", "Rotate SSO signing key (90 days)", "platform-security"),
    ("kubernetes", "Scale batch node pool before month-end", "platform-principal"),
    ("zenith-retail", "Weekly recon extract for Zenith treasury", "payments-staff"),
]

INCIDENT_TITLES = {
    "ledger-recon": ["Recon break count above threshold", "Recon job failed to start", "Recon checkpoint lag"],
    "settlement-batch": ["Settlement batch timeout", "Payout file rejected by bank"],
    "payments-gateway": ["Gateway 5xx spike", "Acquirer B latency", "UPI callback backlog"],
    "refunds-service": ["Refund queue growing"],
    "kubernetes": ["Node pool pressure", "Pods evicted on batch pool", "Cluster autoscaler stuck"],
    "observability": ["Alertmanager down"],
    "auth-service": ["SSO login errors"],
    "fraud-engine": ["Fraud scoring latency", "Fraud false positive spike"],
    "data-warehouse": ["Warehouse load late"],
    "bank-sftp": ["SFTP connection refused"],
    "merchant-dashboard": ["Dashboard errors for merchants"],
    "kyc-service": ["KYC vendor timeouts"],
}
