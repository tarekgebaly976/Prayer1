# User manual

The interface is available in **English** and **Arabic** (right-to-left): use the language button (文A icon) in the
top bar. Your choice is saved to your account. The coloured badge at the top shows whether you are **online**; the
system needs a connection to save records — nothing is stored silently on the device.

Screenshots: `docs/screenshots/`.

## 1. Signing in
Use your company e-mail and password. After 5 wrong attempts the account is locked for 15 minutes. If you belong to
several plants, choose the plant in the top bar; you only see data of the selected plant (and only your department
if your account is department-restricted).

## 2. Install on a phone or tablet
Open the site in Chrome/Edge (Android) or Safari (iOS) → *Add to Home screen*. The app opens on **My work**.

## 3. Reporting a problem (everyone with "Work requests")
*Work requests → New work request* (or the red button on an asset page / after scanning its QR code). Choose the asset,
describe the symptom, tick **Breakdown** if the machine is stopped — supervisors are alerted immediately.

## 4. Technicians: doing the work
1. **My work** lists work orders assigned to you, sorted by due date. ⚠ marks jobs needing LOTO/permit.
2. Open a job. If LOTO/permit is required, the supervisor must sign off first — the *In progress* button is refused
   until then.
3. Press **Move to: In progress**.
4. **Checklist** tab: tap OK / Not OK, enter readings (out-of-range readings are flagged), record lubrication tasks
   (only the specified lubricant or an approved alternative is accepted).
5. Record findings, root cause, failure codes, downtime; add **photos** in *Attachments* (camera opens on phones).
6. **Labor** tab: book your hours (you can only book your own time).
7. **Move to: Awaiting review / test** when done.

Scan an equipment QR label with **Scan QR** to open its page: history, spare parts (BOM), manuals, meters.

## 5. Supervisors
* *Work requests*: accept (creates a work order) or reject with a reason.
* Approve work orders, assign technicians (*Details* tab — conflicts with leave or overlapping jobs are flagged),
  sign off LOTO/permits, record test results, complete and close work. Emergency breakdowns may go straight to
  *In progress*; closing them needs the emergency-closure permission.
* Completion is blocked until required checklist items, test results, failure codes (corrective/emergency) and root
  cause (emergency) are present — the message lists what is missing.
* *Shifts & handover*: confirm handovers written by the outgoing shift (you cannot confirm your own).
* *PM → Approvals*: approve or reject deferral/cancellation requests (you cannot approve your own request).

## 6. Planners
* *Preventive maintenance*: create job plans (task list, readings with limits, safety precautions, LOTO/permit/test
  flags) and PM plans (calendar: every N days/weeks/months/years, fixed or floating from last completion; or meter:
  every N running hours). Work orders are generated automatically *lead days* before the due date — never twice.
* Plan work orders: planned start/end, estimated hours, supervisor; schedule; reserve spare parts.
* *Lubrication*: lubrication points, routes, *Generate route WO*.
* *Shutdowns*: work packages with durations and predecessors; the critical path is calculated and shown in red on the
  Gantt chart; track material/permit/LOTO readiness, daily progress and delay reasons; pre-startup checks must be
  completed before the shutdown can be closed.

## 7. Storekeepers
*Spare parts*: goods receipts (optionally against a purchase requisition line), issues and returns against work
orders (cost goes to the work order at moving-average cost), adjustments (reason required), transfers, critical
spares, below-reorder filter, valuation, aging/excess. Stock can never go negative. Purchase requisitions are local
references — there is no ERP connection.

## 8. Reliability engineers
*Condition monitoring*: measurement points with warning/alarm limits; enter readings (or receive them from the plant
gateway); status Normal / Warning / Critical / Unknown is a transparent limit comparison (no prediction is claimed).
Alerts can be acknowledged, turned into a predictive work order and resolved. Trend charts show limits.

## 9. Managers: KPIs and reports
*KPIs & reports*: 20 KPIs for a period and department. Click a KPI for its formula, inclusion rules, numerator /
denominator, 12-month trend and the underlying records. If data is missing the KPI says **Not available** and why —
values are never estimated. Export XLSX/PDF. Work order PDF reports are on each work order.
Enter daily production (tonnes, hours) and monthly budgets in the *Production data / Budget* tab — needed for cost
per ton, OEE and budget vs actual.
