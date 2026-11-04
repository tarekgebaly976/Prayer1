# PlantPulse operator guide (the product) – every command in one place

Arabic version: [PLANTPULSE-GUIDE-AR.md](PLANTPULSE-GUIDE-AR.md) · Someone asks for a trial: [TRIAL-PLAYBOOK.md](TRIAL-PLAYBOOK.md)

Type every command in **Cloud Shell** (or PowerShell on a computer), one line at a time, then Enter.
Commands are written **without quotes** so a phone keyboard cannot change them.

> ⚠️ Never send passwords or keys (`re_...`) in a chat or a screenshot.

---

## 1. What runs on the server

Server: Oracle `84.8.106.22` (A1.Flex, 2 OCPU, 12 GB RAM, 45 GB disk, 4 GB swap).

| System | Address | Notes |
|---|---|---|
| Obeikan (real) | https://84-8-106-22.sslip.io | Only touched by its own update command |
| Obeikan test copy | https://test.84-8-106-22.sslip.io | `scripts/test-copy.sh` |
| Product website | https://plantpulse-cmms.com | `scripts/site.sh` |
| Public demo | https://demo.plantpulse-cmms.com | `scripts/demo.sh` – sample general factory, back to the sample data every night at 03:00 |
| Customers | https://customer-name.plantpulse-cmms.com | `scripts/customer.sh` – one separate system per customer |

Every system is separate: its own database and attachments. No customer ever sees another's data.

---

## 2. E-mails you receive from the website

All notifications go to `plantpulse.cmms@gmail.com`. The subject tells you which form was used:

| Subject | From | What the visitor already got | What you do |
|---|---|---|---|
| **🟢 جرّب الـ Demo – Demo access**: Company (Name) | "Try the demo" button | Address and password of the **shared demo**, automatically | Nothing required. Follow up in 1–2 days: "Did you try it?" |
| **📞 طلب تواصل – Contact request**: Company (Name) | "Contact us" form | A confirmation + the shared demo access | **Reply or call within one working day** (Reply goes straight to the visitor) |

**The website never creates a customer system by itself.** A private trial system (step 3) is created only by
you, after you have talked to the visitor and agreed on a trial.

| | Shared demo | Private trial / customer system |
|---|---|---|
| Address | `demo.plantpulse-cmms.com`, one for everybody | `name.plantpulse-cmms.com`, one per company |
| Data | Sample factory, reset every night | Empty; the customer's real data, **kept** |
| Created by | The website, automatically | **You**, with `customer.sh new` |

List of everyone who used the forms:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh requests
```

---

## 3. New customer ✅ (the most important)

**Before you start:** a short English name, lowercase letters, digits and `-` only (e.g. `alsafi` or `nada-food`).
Reserved names: `www demo test api app admin mail` …

```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh new alsafi it@alsafi.com Al Safi Paper Co
```

- `alsafi` → the address: https://alsafi.plantpulse-cmms.com
- `it@alsafi.com` → e-mail of the customer's first administrator (Admin)
- `Al Safi Paper Co` → company name (plain words, no quotes)

**Optional additions at the end of the line:**

| Addition | Meaning |
|---|---|
| `--trial 30` | 30-day trial (without it = paying customer) |
| `--departments paper` | Paper-mill departments (PM, SP, FH…). Default `general` (Production, Maintenance, Utilities, Facilities) |
| `--departments none` | No departments; the customer adds their own |
| `--plant Mill No 2` | Plant name (default Main plant) |
| `--lang en` | Welcome e-mail in English (default Arabic) |
| `--currency USD` / `--timezone Asia/Dubai` | Defaults are SAR and Asia/Riyadh |

**What happens:** within 2–3 minutes the system is created and its details appear on your screen (address,
e-mail, first password). **Nothing is sent to the customer** until you approve. The first visit to the address
can take ~20 seconds (HTTPS certificate).

**Then 3 steps:**

1. **Check the system yourself:** open the address and sign in with the details shown; check the company, plant
   and departments.
2. **See the welcome e-mail without sending it:**
   ```
   ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi --preview
   ```
3. **When you approve, send it:**
   ```
   ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi
   ```
   (To change the language add `--lang en` or `--lang ar` at the end.)

The e-mail comes from `noreply@plantpulse-cmms.com` with the address, the first password and first steps; replies
reach `plantpulse.cmms@gmail.com`. The `show` command tells whether and when it was sent.

**Afterwards:** make sure the customer signed in and changed the password. If the e-mail did not arrive (many
companies hold mail from a new domain), ask them to check Junk / Quarantine, or send the details yourself.

---

## 4. Everyday customer commands

| What | Command |
|---|---|
| List customers, their state and free memory | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh list` |
| One customer's details (address, e-mail, first password, welcome sent?) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh show alsafi` |
| Preview the welcome e-mail (nothing sent) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi --preview` |
| Send (or resend) the welcome e-mail | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi` |
| A user forgot the password | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh reset-password alsafi user@alsafi.com` |
| Backup now | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh backup alsafi` |
| Pause (the customer sees a "paused" page; data kept) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop alsafi` |
| Start again after a pause | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh start alsafi` |
| Error log | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh logs alsafi` |
| Delete a customer for good (after a final backup) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remove alsafi --yes` |

### Trial period

- Trial customer: add `--trial 30` when creating. `list` and `show` give the end date and the days left.
- **You get a reminder e-mail** at `plantpulse.cmms@gmail.com` 7 days before the end, 1 day before, on the day,
  then every week after the end – with the commands ready to copy.
- **Nothing stops by itself.** You decide:

| Decision | Command |
|---|---|
| Paid → permanent customer | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh activate alsafi` |
| Extend the trial by 14 days | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh extend alsafi 14` |
| Pause | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop alsafi` |
| Preview a reminder to the customer (nothing sent) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remind alsafi --preview` |
| Send the reminder after your approval | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remind alsafi` |

`activate` and `extend` start a paused customer again automatically.

**Backups:** automatic every night at 02:45 for all customers: a copy on the server (14 days in
`/opt/plantpulse-backups/customer-name`) **and a copy off the server** in Oracle Object Storage (same place as
Obeikan's backups, under `customers/customer-name/`).
Log: `ssh ubuntu@84.8.106.22 sudo tail -20 /var/log/plantpulse-customers.log`

**Restore a backup** (replaces all of the customer's current data; takes a safety backup first):
```
ssh ubuntu@84.8.106.22 sudo ls /opt/plantpulse-backups/alsafi
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh restore alsafi /opt/plantpulse-backups/alsafi/FILE-NAME.dump --yes
```
(Copy the `….dump` file name from the first command; its date and time are in server time, UTC.)

---

## Forgot password (for users)

The sign-in page has a **"Forgot password?"** link: the user types their e-mail → gets a link that works **once, for
30 minutes** → chooses a new password. They are then signed out on every device, any lock-out is lifted, and a
"password was changed" e-mail is sent.

- The answer is always the same whether or not the address has an account (nobody can find out who has one); at most
  3 links per account per hour.
- Works only where the system can send e-mail. If the user sees **"ask your administrator"**, e-mail is off there:
  the administrator sets a password in **Admin → Users → Edit → Reset password**, or you from Cloud Shell:
  - customer: `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh reset-password alsafi user@alsafi.com`
  - Obeikan: `ssh -t ubuntu@84.8.106.22 "cd /opt/cmms && sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api python -m app.cli reset-password --email user@company.com"`
- Always off on the public demo (its accounts are shared by every visitor).
- **E-mail on the Obeikan system** (same sender as the website, via Resend):
  ```
  ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/main-mail.sh reset-only
  ```
  `reset-only` = password links only (alerts and daily summaries stay in the app) · `all` = every e-mail (emergencies,
  critical alerts, daily summary) · `off` = no e-mail · `status` = what it does now.
- E-mail not arriving? The user's Junk / Quarantine, or its status at https://resend.com/emails .

---

## 5. Updates (a new version of the software)

Always in this safe order: **test first → then customers → then Obeikan**.

| Step | Command |
|---|---|
| 1. Download the new code | `ssh ubuntu@84.8.106.22 sudo git -C /opt/cmms pull` |
| 2. Try it on the Obeikan test copy | `ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/test-copy.sh update` |
| 3. Update the public demo + fresh sample data | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/demo.sh launch-update` |
| 4. Update all customers | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh launch-update-all` |
| 5. Real Obeikan (last) | `ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/deploy/install-server.sh` |

`launch-…` commands run on the server by themselves (5–15 minutes) even if Cloud Shell is closed. To see progress:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/demo.sh progress
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh progress
```
`STILL RUNNING` = not finished yet, `FINISHED` = done (read the last line).

If only the website changed (text, pictures, forms):
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh update
```

---

## 6. Website and e-mail

| What | Command |
|---|---|
| Who used "Try the demo" / "Contact us" | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh requests` |
| Test e-mail | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh test-mail` |
| Website log | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh logs` |
| After changing the page | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh update` |
| Demo accounts and password | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/demo.sh accounts` |

**E-mails** go out from `noreply@plantpulse-cmms.com` through **Resend** (free: 3,000 a month, 100 a day for all
systems together). Replies go to `plantpulse.cmms@gmail.com`. Status of every e-mail: https://resend.com/emails
(Delivered = accepted by the recipient's mail server; if they cannot find it, it is in their Junk/Quarantine).

**Change the Resend key** (if it was exposed): create a new key in Resend → API Keys, delete the old one, then:
```
ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh resend noreply@plantpulse-cmms.com
```
(paste the key when asked). Then give every customer the same setting:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh mail-sync
```

---

## 7. Capacity: how many customers can the server take?

- A small customer ≈ **0.5 GB RAM** and **1–3 GB disk**.
- Current server: about **10 customers** (`customer.sh new` refuses when free memory drops below 1.2 GB).
- To grow **for free**: Oracle → Compute → Instance → Edit → Shape: up to **4 OCPU and 24 GB**, disk up to 200 GB
  (needs a 2-minute server restart – do it in a quiet hour) ⇒ about 30–40 customers.
- To save memory: stop the Obeikan test copy when you don't need it:
  `ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/test-copy.sh stop`

---

## 8. Oracle and costs

- The account is **Pay As You Go** and the server is **Always Free** ⇒ no cost as long as nothing new is created.
- A **€1 budget alert** sends an e-mail if any spending starts.
- ⚠️ Do not create a new Instance / Volume / Load Balancer / Database without a review.

---

## 9. Emergencies

| Problem | What to do |
|---|---|
| A site does not open (any address) | `ssh ubuntu@84.8.106.22 sudo docker ps` – every system should be `Up` |
| A customer's address does not open | `customer.sh list` (RUNNING should be 4/4), then `customer.sh start name` |
| Server slow or full | `ssh ubuntu@84.8.106.22 free -h` and `ssh ubuntu@84.8.106.22 df -h /` |
| Free disk space | `ssh ubuntu@84.8.106.22 sudo docker image prune -f` |
| Restart the whole server | Oracle → Instance → Reboot. Every system comes back by itself (restart: unless-stopped) |

---

## 10. Reset the main (Obeikan) system to examples

Wipes all operational data (assets, PM, PdM, lubrication, work orders, requests, attachments …), keeps users,
passwords and departments, adds a few invented examples (codes `EX-…`), and refreshes the test copy. A full backup is
taken first, and a dry run checks everything before anything is wiped.
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh status
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh WIPE-ALL-DATA
```
The backup taken just before the wipe is copied to `/opt/cmms-backups/keep/` – the 14-day cleanup never touches that
folder, so the old data can be put back **at any time**, even years later. Use the `undo` line printed at the end.

**Record – Obeikan data wiped on 2026-11-03.** The old data (assets, PM, PdM, work orders, attachments …) is kept in:
- the server: `/opt/cmms-backups/keep/cmms_<time>.dump` (+ `storage_<time>.tar.gz` for the attachments)
- off the server: Oracle Object Storage, folder `20261103/` (never deleted automatically)

See what is kept, and put the old data back (this replaces the examples and anything entered since):
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh kept
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh undo /opt/cmms-backups/keep/cmms_FILE-NAME.dump
```
Keep any other backup permanently: `… reset-to-examples.sh keep /opt/cmms-backups/cmms_FILE-NAME.dump`.
If the server itself is ever lost: download the 4 files of `20261103/` from Object Storage to
`/opt/cmms-backups/keep/` on the new server and run the same `undo` line.

## 11. Checklist: a new paying customer

1. ☐ Written agreement (price, subscription period, support, who enters the data).
2. ☐ A short name for the address + the customer's admin e-mail (+ `--trial 30` for a trial).
3. ☐ `customer.sh new …` → sign in and check the system yourself.
4. ☐ `customer.sh welcome name --preview`, then `customer.sh welcome name` → check the e-mail arrived.
5. ☐ The customer signed in and changed the password.
6. ☐ Import assets and PM plans from the Excel templates (help them in the first days).
7. ☐ Short training: planner, supervisors, technicians (phone).
8. ☐ Check that backups work: `customer.sh backup name`.
