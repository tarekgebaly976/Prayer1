# Project status — 2026-11-03

PlantPulse is now two things on one server (Oracle Cloud, Riyadh, `84.8.106.22`):

1. **The plant's own CMMS** (the first customer, a paper mill) at https://84-8-106-22.sslip.io, with a test copy at
   https://test.84-8-106-22.sslip.io. Unchanged by the product work below.
2. **PlantPulse as a product** for other plants: website, public demo, and one separate PlantPulse per customer.

Operator guide (every command): [English](PLANTPULSE-GUIDE.md) · [Arabic](PLANTPULSE-GUIDE-AR.md) · Plan ahead: [ROADMAP.md](ROADMAP.md)

## Live on the server

| What | Address | Managed by | State |
|---|---|---|---|
| Plant CMMS (real) | https://84-8-106-22.sslip.io | `deploy/install-server.sh` | live since 2026-10-26; nightly backup, copied to Oracle Object Storage |
| Plant CMMS test copy | https://test.84-8-106-22.sslip.io | `scripts/test-copy.sh` | try new versions here first |
| Product website | https://plantpulse-cmms.com (www redirects) | `scripts/site.sh` | live; EN/AR; "Try the demo" and "Contact us" forms |
| Public demo | https://demo.plantpulse-cmms.com | `scripts/demo.sh` | live; sample plant reloaded every night 03:00 Riyadh |
| Customer instances | https://&lt;name&gt;.plantpulse-cmms.com | `scripts/customer.sh` | ready; tested end to end with a trial customer (created, signed in, removed) |

Domain `plantpulse-cmms.com` on Cloudflare (DNS only): A records `@`, `www`, `demo`, `*` → the server; Resend e-mail
records (`send`, `rsend`, `resend._domainkey`) and `_dmarc`. HTTPS by Caddy (automatic certificates).

**2026-11-03 – real plant data wiped, replaced by examples** (`scripts/reset-to-examples.sh WIPE-ALL-DATA`; users and
departments kept). The data from before the wipe is **kept permanently** in `/opt/cmms-backups/keep/` (excluded from the
14-day cleanup) and in Object Storage `20261103/`; it can be put back at any time with
`reset-to-examples.sh undo /opt/cmms-backups/keep/cmms_<time>.dump` (see PLANTPULSE-GUIDE.md §10).

## Completed

### Product: website (2026-11-02/03)
* Landing page in English and Arabic (RTL): features, screenshots, "your own system", getting started.
* **Try the demo**: visitor leaves name/company/e-mail → receives the demo address and accounts at once, in the
  language they used; the owner is notified. **Contact us**: owner notified, visitor gets a confirmation with the
  demo access. Every submission is also saved on the server (`site.sh requests`). Honeypot, rate limits,
  3 e-mails per address per day.
* E-mail from `PlantPulse <noreply@plantpulse-cmms.com>` via Resend (domain verified: SPF, DKIM, DMARC); replies go
  to `plantpulse.cmms@gmail.com`.

* 2026-11-04: the 11 phone screenshots show the new app look (`site/public/img/v4/`), made with
  `scripts/site-screenshots.js` from a local copy with the demo's sample plant (rerun it after the next design change).

### Product: public demo
* Own database and images, blue **DEMO** label, no e-mail from the app, reset every night.
* A living sample plant – a **general manufacturing plant** (production line with mixer, hydraulic press, drying oven
  and packaging; crusher and grinding mill; palletizer; utilities), not tied to one industry – regenerated each night
  relative to "today": 6 months of history (breakdowns with failure
  codes, PM history, contractor work, production, budget), 13 open work orders in every status, requests, alarms,
  overdue lubrication. Six-month KPIs: PM compliance 83 %, MTBF 225 h, MTTR 3.1 h, OEE 88 %, availability 98.6 %.
* Shared password guarded every 10 minutes (restored if a visitor changes it; lock-outs lifted).

### Product: one PlantPulse per customer (`scripts/customer.sh`)
* `new <name> <admin-email> <Company> [--trial 30] [--departments general|paper|none] [--lang ar|en]`:
  own database, attachments and settings, first administrator with a random password, address with HTTPS.
* **Nothing is e-mailed to the customer until the owner approves**: `welcome <name> --preview`, then `welcome <name>`.
* **Trials**: owner reminded 7 days / 1 day before, on the day and weekly after; nothing stops automatically;
  `extend`, `activate` (paid), `remind --preview` / `remind` (customer reminder after approval).
* **Pause**: `stop` shows a bilingual "paused" page (data kept); `start` brings it back.
* Nightly backups (02:45 Riyadh), verified, kept 14 days on the server and copied to Oracle Object Storage
  (`customers/<name>/`); `restore` with a safety backup first; `remove` with a final backup.
* Updates: `launch-update-all` (builds the new version and moves every running customer, in the background).
* Memory limits per customer; creation refused when the server is short of memory.

### Server and account
* 4 GB swap added (safety net during builds). Oracle account upgraded to **Pay As You Go** (server stays within
  Always Free; protects it from idle reclamation); budget alert at €1/month.
* Every Caddy change is validated in a throw-away Caddy before the running one is touched.

### App look (2026-11-03/04) – live
* Same brand as the website: navy `#17324D` + amber `#F5A623`, self-hosted fonts (Inter, IBM Plex Sans Arabic), logo in
  the header, light-grey page with white cards, branded sign-in page.
* Sidebar in navy, grouped (Daily work / Maintenance / Assets & resources / Analysis & admin) with live counts
  (new requests, emergencies, overdue lubrication, PM approvals, critical alerts) and the user card at the bottom.
* Dashboard cards with icons and a coloured edge when something needs attention; tables as white cards, dates and
  WO numbers no longer split over two lines, status badges in normal case.
* Dashboard (phase 2): "Needs attention" list (open work orders by priority, Mine / All, overdue dates in red),
  work orders opened vs completed per week (new `GET /dashboard/activity`), 6-month KPIs (PM compliance, MTBF, MTTR,
  availability). Technicians see their own work first; on phones the cards are compact.
* Phones (phase 3): bottom bar (Dashboard, My work, big red "new request" button, Scan QR, Notifications with
  counts); every table becomes one card per row (no sideways scrolling); work order actions stay pinned above the
  bottom bar; My work cards show priority colour, asset, due date (red when overdue) and safety flag.
* Phase 4: dark mode in the brand's navy (moon / sun button in the header, remembered per device); status colours
  with one meaning each (grey not started / paused, yellow waiting, blue planned, orange in work, red problem, green
  done); loading placeholders instead of spinners; empty lists show an icon and a sentence.
* **Live everywhere since 2026-11-04** (version `8c8bb6a`): public demo, plant test copy and the real plant CMMS
  (`install-server.sh`); no customers yet, new ones are created from this version. No database change in this update.

### Forgot password (2026-11-04)
* "Forgot password?" on the sign-in page: e-mailed link, single use, 30 minutes, at most 3 per account and hour, same
  answer for any address, new link cancels the old one; afterwards signed out everywhere, lock-out lifted, confirmation
  e-mail. Token stored only as a SHA-256 digest (migration 0016, table `password_resets`); link address from
  `CMMS_PUBLIC_URL`, never from the request. Off without e-mail, and always on the public demo ("ask your administrator").
* Fixed with it: public pages (`/privacy`, reset pages) no longer bounce to the sign-in page when opened directly.
* `CMMS_EMAIL_NOTIFICATIONS=false` keeps alerts and daily summaries in the app while reset e-mails still go out;
  `scripts/main-mail.sh reset-only | all | off | status` sets the Obeikan system's mail from the website's Resend sender.
  Obeikan: e-mail off until `main-mail.sh reset-only` is run (users use personal e-mail addresses).

### Spare parts import (2026-11-03)
* Import button on the Inventory page (template, preview, errors.csv); optional warehouse / qty_on_hand / bin columns
  are booked as opening stock.

### CMMS application (earlier, see TEST_REPORT.md)
* Milestones 1–4 complete, milestone 5 mostly (see earlier sections of README / PRODUCTION_READINESS.md).
* Recent app changes for the product: blue DEMO instance label (TEST stays red); the KPI page opens on the last six
  months on a demo instance; `seed-demo` loads the living sample plant (`--profile general` for the public demo;
  the default paper-mill profile is what the automated tests use).

## Capacity (measured 2026-11-03)
2 OCPU, 12 GB RAM (8.7 GB available), 45 GB disk (23 GB free), 4 GB swap. A small customer uses ≈ 0.5 GB RAM and
1–3 GB disk ⇒ about **10 customers** on the current VM; free upgrade to 4 OCPU / 24 GB / 200 GB ⇒ about 30–40.

## Tested
* Backend 60+ tests pass after the demo-data change; frontend type check and lint clean.
* On the server: website forms and e-mails (Resend, delivered), demo build and nightly data, customer create → sign in
  → remove, Caddy reload without downtime, swap, backups off-server for the plant CMMS.

## Not yet tested / open points
* A paused customer page and trial reminders on the server (tested with stand-ins only).
* E-mail deliverability to corporate mail systems: messages are delivered but some (e.g. Proofpoint) hold mail from
  the new domain; reputation builds over weeks. Ask customers' IT to allow `plantpulse-cmms.com`.
* e2e: all 27 pass (2026-11-04). The run needs raised per-IP rate limits because every test comes from one IP (set
  in CI and docs/TESTING.md).
* Customer restore on the server (scripted; drill pending). Real phones and QR scanning by customers.
* The €93 card authorisation from the Oracle upgrade (2026-11-03) should be released by the bank; check it.

## Next actions
See [ROADMAP.md](ROADMAP.md). Immediate: LinkedIn launch post, follow up demo sign-ups (`site.sh requests`),
first paying customer with the checklist in the operator guide.
