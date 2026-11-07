# Roadmap — PlantPulse as a product (from 2026-11-03)

Status of what exists: [PROJECT_STATUS.md](PROJECT_STATUS.md). Operator commands: [PLANTPULSE-GUIDE.md](PLANTPULSE-GUIDE.md) (Arabic: [PLANTPULSE-GUIDE-AR.md](PLANTPULSE-GUIDE-AR.md)).
Technical CMMS roadmap (SSO, offline, …): [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md#roadmap-suggested-order).
Checklist with owner and target month (Arabic): [ACTION_PLAN_2026-11.md](ACTION_PLAN_2026-11.md).

## Now (this month) — go to market
| # | Action | Who | Notes |
|---|---|---|---|
| 1 | LinkedIn launch post (EN/AR) with image | owner | Text ready; image from ChatGPT prompt (Arabic text added in Canva if needed) |
| 2 | Follow up every demo sign-up within 1–2 days | owner | `site.sh requests`; notification e-mails to plantpulse.cmms@gmail.com |
| 3 | First paying / pilot customer | owner | Checklist in the operator guide (§9): `customer.sh new … --trial 30`, review, welcome e-mail |
| 4 | Price list and a simple agreement (subscription, support, data entry help) | owner | Needed before the first invoice |
| 5 | Ask the plant's IT (and each customer's IT) to allow mail from `plantpulse-cmms.com` | owner | Corporate filters hold mail from a new domain |
| 6 | Check the €93 Oracle card authorisation was released | owner | Bank statement; Oracle Billing support if not |

## Next (1–3 months) — website and operations
| # | Item | Why |
|---|---|---|
| 7 | **Uptime monitoring** (e.g. UptimeRobot, free): site, demo, plant CMMS, each customer | E-mail/phone alert when something is down |
| 8 | **`sales@plantpulse-cmms.com`** via Cloudflare Email Routing → Gmail; use it as reply-to and on the site | Professional address, no personal Gmail shown |
| 9 | Object-storage lifecycle rule (delete backups older than ~90 days) | Keep within the 20 GB free tier as customers grow |
| 10 | Website: privacy policy and terms pages; pricing or "plans" section; customer logos/testimonial once allowed | Trust and conversions |
| 11 | Website analytics (privacy-friendly, e.g. Cloudflare Web Analytics) | Know which pages bring demo sign-ups |
| 12 | Restore drill for a customer on the server | Prove the customer backup/restore end to end |
| 13 | Server: grow to 4 OCPU / 24 GB / 200 GB (free) when ~8 customers are live | Capacity; 2-minute restart in a quiet hour |

## App (CMMS) — product features
| # | Item | Why |
|---|---|---|
| 14 | Google Play publication (listing kit ready in `docs/play-store`) | Phone install from the store |
| 15 | Offline technician mode (queue + conflict check) | Plants with weak Wi-Fi on the shop floor |
| 16 | SSO (Azure AD / Google) + MFA for admins | Asked for by larger companies' IT |
| 17 | Arabic for server messages and PDF reports | Full Arabic experience |
| 18 | Planner calendar with drag-and-drop | Planning comfort |
| 19 | Customer self-service: own domain (`cmms.customer.com`), logo on reports | Larger customers |
| 20 | Usage dashboard for the owner (users, work orders per customer) | Know which customers are active; renewals |
| 24 | **Smart Import (AI)**: customer files in any shape → PlantPulse import templates (see below) | Data entry is the hardest part of starting; faster onboarding |

### 24 — Smart Import (AI-assisted data onboarding) — added 2026-11-07
Idea: the customer uploads a file in any shape (messy Excel, PDF, photo of a table, other column names); an AI model
maps it onto the existing PlantPulse import template (assets, PM, lubrication, PdM, rosters, spare parts, users,
history) and returns that template plus notes on what it was unsure of.

* **The AI never saves anything.** Its output goes into the existing import preview and `errors.csv` check; a person
  reviews and confirms, as today.
* **Phase 1 (now, no code):** owner prepares the first customers' files with Claude as a paid "data entry help"
  service (item 4); collect the real file types customers send.
* **Phase 2 (after 2–3 customers):** build it into the app based on those real cases.
* **Before phase 2:** customer consent and an agreement clause (files go to an external AI service); check Saudi
  PDPL for personal data (users, rosters); cost per file; API key kept on the server only.

## Later — scale
* A second server or managed database when one customer needs guaranteed availability.
* Billing integration (invoices, card payments) once there are enough customers.
* On-premise installation package for customers who require their own server (`deploy/install-server.sh` is the base).
