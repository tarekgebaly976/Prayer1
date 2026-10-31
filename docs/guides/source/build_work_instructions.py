"""PlantPulse – step-by-step work instructions (English PDF). argv: out.pdf paper|general"""

import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    CondPageBreak,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = sys.argv[1]
ED = sys.argv[2]
PAPER = ED == "paper"


def v(paper, general):
    return paper if PAPER else general


NAVY, TEAL, AMBER, SOFT, LINE = colors.HexColor("#102A33"), colors.HexColor("#23616D"), colors.HexColor("#B9781A"), colors.HexColor("#44535A"), colors.HexColor("#D5DDDF")
TIP_BG, WARN_BG = colors.HexColor("#E6F0F1"), colors.HexColor("#FBF0DC")

S = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=30, leading=36, textColor=NAVY),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=15, leading=21, textColor=SOFT),
    "part": ParagraphStyle("part", fontName="Helvetica-Bold", fontSize=20, leading=26, textColor=NAVY, spaceBefore=4, spaceAfter=4),
    "partintro": ParagraphStyle("partintro", fontName="Helvetica", fontSize=10.5, leading=15, textColor=SOFT, spaceAfter=8),
    "proc": ParagraphStyle("proc", fontName="Helvetica-Bold", fontSize=13.5, leading=18, textColor=TEAL, spaceBefore=10, spaceAfter=3),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=9.5, leading=13, textColor=SOFT, spaceAfter=5),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=15, textColor=NAVY, alignment=TA_LEFT),
    "step": ParagraphStyle("step", fontName="Helvetica", fontSize=10.5, leading=15, textColor=NAVY),
    "box": ParagraphStyle("box", fontName="Helvetica", fontSize=9.8, leading=14, textColor=NAVY),
    "toc": ParagraphStyle("toc", fontName="Helvetica", fontSize=10.5, leading=16, textColor=NAVY),
    "tocpart": ParagraphStyle("tocpart", fontName="Helvetica-Bold", fontSize=11, leading=18, textColor=TEAL, spaceBefore=6),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.6, leading=11.5, textColor=NAVY),
}


def box(kind: str, text: str):
    label = {"tip": "Tip", "note": "Note", "warn": "Important"}[kind]
    p = Paragraph(f"<b>{label}:</b> {text}", S["box"])
    t = Table([[p]], colWidths=[170 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WARN_BG if kind == "warn" else TIP_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 3, AMBER if kind == "warn" else TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [Spacer(1, 4), t]


def steps(items: list[str]):
    return ListFlowable(
        [ListItem(Paragraph(i, S["step"]), leftIndent=16, value=n + 1) for n, i in enumerate(items)],
        bulletType="1",
        bulletFontName="Helvetica-Bold",
        bulletFontSize=10.5,
        bulletColor=TEAL,
        leftIndent=16,
        spaceBefore=2,
    )


def code(text: str):
    t = Table([[Paragraph(text, S["code"])]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF1F2")), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return [Spacer(1, 4), t]


# ---- Content: parts → procedures (title, who, where, steps, extras) -------------------------------------------------
P = []


def part(title, intro):
    P.append(("part", title, intro, []))


def proc(title, who, where, items, *extras):
    P[-1][3].append((title, who, where, items, extras))


part("Getting started", "Signing in, installing the app on a phone and finding your way around. For everyone.")
proc("Sign in and change your password", "Everyone", "Any browser",
     ["Open <b>https://84-8-106-22.sslip.io</b> in Chrome (computer or phone).",
      "Enter the e-mail and the temporary password the administrator gave you, then press <b>Sign in</b>.",
      "Change the password at once: tap the <b>person icon</b> (top right) › <b>Change password</b>.",
      "Type the current password, the new password twice, and press <b>Save</b>."],
     ("note", "A password needs at least 12 characters with three of: lowercase, uppercase, digit, symbol. Never share it: every action is recorded under your name."))
proc("Install the app on a phone", "Everyone with a phone", "Chrome on Android, Safari on iPhone",
     ["<b>Android</b>: open the link in <b>Chrome</b>, sign in, then Chrome menu (three dots) › <b>Install app</b> or <b>Add to Home screen</b>.",
      "<b>iPhone</b>: open the link in <b>Safari</b> (or Chrome), tap the <b>Share</b> button › <b>Add to Home Screen</b> › <b>Add</b>.",
      "Open PlantPulse from its <b>PlantPulse</b> icon (gear with an orange pulse) on the home screen from now on, and sign in once inside it."],
     ("warn", "Install from Chrome, not Samsung Internet. Samsung Internet packages the page as an app and Google Play Protect may show a warning. A Google Play version of PlantPulse is in preparation."),
     ("tip", "If a new button described in this guide is missing after an update, close the app completely (recent apps list) and open it again."))
proc("Find your way around", "Everyone", "Top bar and menu",
     ["<b>Menu</b> (left, or the three lines on a phone): Dashboard, My work, Scan QR, Work requests, Work orders, Assets, Preventive maintenance, Lubrication, Condition monitoring, Shifts and handover, Spare parts, Shutdowns, KPIs and reports, Administration.",
      "<b>ONLINE</b> badge: green means connected. Reconnect before saving if it shows offline.",
      "<b>Bell</b>: your notifications (breakdowns, jobs assigned to you, approvals waiting). Tap one to open the record.",
      "<b>Language button</b> (next to the bell): English, Arabic (right to left) or Bengali; your choice is remembered on every device."],
     ("note", "You only see the menus and buttons your role allows, and if your account has one or more departments (e.g. " + v("PM + SP", "PROD + UTIL") + ") you only see those areas’ equipment, jobs and alerts. If something is missing, ask the administrator; do not use someone else’s account."),
     ("tip", "Any field where you choose an asset has a small <b>tree</b> button: open the levels with the arrows and click a code, or simply type part of the code or name."))

part("Reporting and doing work", "From a reported problem to a closed work order: requests, QR, work orders, safety and spare parts.")
proc("Report a problem (work request)", "Everyone, including production", "Work requests › New work request",
     ["Open <b>Work requests</b> › <b>New work request</b> (or scan the machine’s QR label and press <b>New work request</b> on its page).",
      "Choose the <b>asset</b>: type part of its code or name, or use the tree button.",
      "Choose the <b>Symptom</b> from the list: what you see or hear (abnormal noise, high vibration, oil leak, tripped…).",
      "If you know it, choose the <b>Suspected failure mode</b>. The modes of that equipment type are shown first (“For this equipment”). Leave it empty if unsure: the technician confirms it later.",
      "The <b>Title</b> fills in by itself from your choices; change it only if needed. Write details in <b>Description</b>.",
      "Tick <b>Breakdown (machine stopped)</b> if the machine is stopped; that area’s supervisors are notified at once.",
      "Press <b>Submit</b>. You can follow the request’s status in the Work requests list."],
     ("tip", "Use a work request instead of a phone call or WhatsApp message, so every breakdown is counted in MTBF and MTTR."))
proc("Scan a QR label", "Everyone", "Scan QR",
     ["Open <b>Scan QR</b> from the menu and press <b>Start camera</b>.",
      "Point the camera at the label on the machine or lubrication point.",
      "The asset’s page opens: details, history, spare parts, lubrication, condition monitoring, attachments.",
      "To report a fault on it, press <b>New work request</b> on that page."],
     ("warn", "Scan from inside the app. The phone’s normal camera app does not open these labels."),
     ("tip", "Camera not working? Type the code printed under the QR (cmms:asset:...) in the box on the Scan QR page."))
proc("Accept or reject a work request", "Supervisor", "Work requests",
     ["Open <b>Work requests</b> and open a new request.",
      "Check the asset and description; adjust the suggested priority if needed.",
      "Press <b>Accept &amp; create WO</b> to create the work order, or <b>Reject</b> and write the reason."],
     ("note", "Breakdowns appear at the top of the Dashboard as open emergencies until they are handled."))
proc("Assign a work order", "Supervisor", "Work orders › open the work order › Details",
     ["Open <b>Work orders</b> (filter by status, type, overdue) and open the job.",
      "In the <b>Details</b> tab choose the technician(s) under <b>Assignees</b> and press <b>Assign</b>.",
      "The system warns if a technician is on leave or already booked at that time.",
      "Several jobs for one technician: tick them in the list and use <b>Bulk assign</b>."],
     ("note", "Preventive, lubrication and condition-monitoring work orders are created by the system already approved; they only need assigning."))
proc("Carry out a work order", "Technician", "My work › open the job",
     ["Open <b>My work</b>. Jobs are sorted by due date; a warning mark means LOTO or a permit is needed.",
      "If LOTO is needed, record every isolation point (see the next procedure) and wait for the supervisor’s sign-off.",
      "Press <b>Move to: In progress</b>.",
      "In the <b>Checklist</b> tab mark each task OK or Not OK and enter readings; out-of-range readings are flagged.",
      "Record findings and downtime, and choose <b>Symptom</b>, <b>Problem</b> (the failure mode; this equipment’s modes are listed first), <b>Cause</b> and <b>Remedy</b>. Add photos in <b>Attachments</b> (the camera opens on a phone).",
      "<b>Labor</b> tab: <b>Book labor</b> for your own hours.",
      "<b>Materials</b> tab: record every spare part you fitted (see “Record spare parts used”).",
      "Remove your locks, then press <b>Move to: Awaiting review</b>."],
     ("warn", "Book your hours on every job. Without labour hours, Planned Maintenance %, Emergency % and labour cost stay “Not available”."))
proc("Record LOTO and sign off the permit", "Technician (isolation), supervisor (sign-off)", "Work order › Checklist › LOTO isolation register",
     ["Technician: for each isolation point enter the point (e.g. MCC-3 breaker Q12), the energy type and the lock / tag number, then press <b>Apply lock</b>.",
      "After testing, tick <b>Zero energy verified</b> (<b>Verify</b>) on each point.",
      "Supervisor: check all points, enter the permit number, permit types (cold work, hot work, electrical, confined space, work at height...) and <b>Permit valid until</b>.",
      "Supervisor: press <b>Sign off LOTO / permit</b>. Only now can the job move to In progress.",
      "When the work is finished, the technician presses <b>Remove lock</b> on each point."],
     ("warn", "The system refuses: starting work before sign-off, signing off an expired permit, and completing the job while a lock is still applied. It supports the physical lock-and-tag procedure; it does not replace it."))
proc("Record spare parts used", "Technician or supervisor", "Work order › Materials › Spare parts used",
     ["Open the work order’s <b>Materials</b> tab.",
      "In <b>Spare part</b>, type the part code or part of the description and pick it.",
      "Not in the list? Type a description in <b>Item not in the list</b> instead.",
      "Enter the <b>Quantity</b> (unit cost is optional; blank uses the book cost) and press <b>Add part used</b>."],
     ("note", "This records which part went on which job and machine, and adds its cost to the work order. Store stock is not changed, because the store system is not connected."),
     ("tip", "Spare parts › <b>Parts used</b> shows all parts by machine (including everything below it), by part and by period, with Excel export."))
proc("Review and close a work order", "Supervisor", "Work orders › status Awaiting review",
     ["Open the Dashboard counter <b>Awaiting review</b>, or filter Work orders by that status.",
      "Check the checklist, readings, hours, parts, photos and findings.",
      "Record a test result if the job needs one (<b>Record result</b>).",
      "Use <b>Move to</b> to complete and close the job, or send it back if something is missing."],
     ("note", "Closing is refused until required checklist items, test results and failure codes are complete (root cause too for emergencies). The message lists what is missing. Each work order can be printed as a PDF report."))

part("Planned work", "Preventive maintenance, lubrication and condition monitoring create their work orders automatically.")
proc("Follow the PM schedule", "Planner, supervisor", "Preventive maintenance",
     ["<b>PM plans</b> tab: all plans with last done and next due; use the search box for a code or name; use the page numbers at the bottom for more.",
      "<b>Schedule</b> tab: coming due dates with plan, machine and a link to the work order once it is created.",
      "Work orders are created up to 7 days before the due date by the scheduler, which runs every 15 minutes. <b>Run scheduler now</b> forces a run.",
      "<b>Job plans</b> tab: the task list, hours and safety needs behind each plan."],
     ("tip", "A monthly mechanical round on one machine is one work order with all its tasks in the checklist."))
proc("Move or cancel a PM", "Anyone with PM access (request), supervisor (approval)", "Preventive maintenance › Schedule",
     ["Find the due date in the <b>Schedule</b> tab.",
      "Press <b>Request deferral</b> (choose the new due date) or <b>Request cancellation</b>, and write the reason.",
      "A supervisor opens the <b>Approvals</b> tab and approves or rejects it. You cannot approve your own request."],
     ("warn", "Never just leave a PM open. An unexplained overdue PM lowers PM compliance."))
proc("Import a plan from Excel (PM, lubrication or condition monitoring)", "Planner (PM, lubrication), reliability engineer (condition monitoring)", "Import plan button on the Preventive maintenance, Lubrication or Condition monitoring page",
     ["Press <b>Import plan</b> and download the template.",
      "Fill one row per task (PM), per lubrication point, or per measurement point. Leave <b>start_date</b> blank to spread the first due dates over the first cycle.",
      "Choose the file and press <b>Preview</b>. It shows how many rows are valid and lists every error.",
      "Fix any errors (download the error report if needed), choose the file again and <b>Preview</b> again.",
      "When there are 0 errors, press <b>Import</b>."],
     ("note", "Import is all or nothing: if one row has an error, nothing is saved. A plan or point code that already exists is reported as an error, so importing the same file twice never doubles the data."))
proc("Do a lubrication route", "Lubricator / technician", "My work › lubrication work order",
     ["Each route gives one work order with the points due in the next 2 days. Open it from <b>My work</b>.",
      "In the <b>Checklist</b> tab, for each point: enter the actual quantity, the lubricant used and a condition note, then press <b>Record</b> (or <b>Skip</b> with a reason).",
      "Complete the work order when all points are recorded."],
     ("warn", "Use only the lubricant shown on the point, or an alternative approved in <b>Lubrication › Approve alternative</b>. Any other lubricant is refused."),
     ("tip", "Replace the general names “General oil / grease (specify product)” with the real products in the <b>Lubricants</b> tab."))
proc("Enter a condition reading and handle an alert", "Technician (reading), reliability engineer (alert)", "Condition monitoring",
     ["Open <b>Condition monitoring</b> › <b>Measurement points</b>. Critical and High points are at the top (red / orange badge); tick <b>Critical &amp; high only</b> to see just those.",
      "Find a point with <b>Search</b> (point, equipment code or name) or <b>Asset and everything below it</b>, then click it. On a phone it opens full screen.",
      "Enter the value in <b>Record reading</b> and press <b>Save</b>. The status becomes normal, warning or critical against the limits. Close the panel with the <b>X</b> at its top right.",
      "A reading outside a limit opens an alert in the <b>Alerts</b> tab, sent to that area’s engineers.",
      "The engineer presses <b>Acknowledge</b>, then <b>Create work order</b> if action is needed, and finally <b>Resolve</b> with the resolution."],
     ("note", "Status comes from clear limit rules; the system does not predict failures. A point not read for too long becomes “unknown”. The screen list shows the first 2,000 points; use search for the others."))
proc("Set the priority of measurement points", "Planner, engineer, reliability engineer, manager, administrator", "Condition monitoring",
     ["One point: click it and choose <b>Critical</b>, <b>High</b> or <b>Normal</b> next to <b>Priority</b>.",
      "Many points: press <b>Priorities (Excel)</b> › <b>Download points with priorities</b>.",
      "In the yellow <b>priority</b> column choose Critical, High or Normal (filter and sort freely; only that column is read).",
      "Upload the file, press <b>Preview</b> (shows how many change), then <b>Apply priorities</b>."],
     ("tip", v("Example: all bearing points of the 73 dryer cylinders were set to Critical in one upload.", "Example: set every bearing point of the critical pumps, fans and compressors to Critical in one upload.")))
proc("Add a measurement point (and missing equipment)", "Reliability engineer", "Condition monitoring › New measurement point",
     ["Choose the <b>Asset</b> (type or use the tree).",
      "Equipment not in the list? Press <b>+ Equipment not in the list? Add it</b> (or <b>+ Add equipment under the selected asset</b>), fill code and name, <b>Create</b>.",
      "Choose the <b>Technique</b> and <b>Unit</b>; enter warning and alarm limits.",
      "Leave <b>Code</b> and <b>Name</b> empty: they are made from the asset (e.g. " + v("PM-DRYER-04-CM27", "L1-PUMP-04-CM27") + "). Press <b>Create</b>."])
proc("Import past readings (history)", "Reliability engineer", "Condition monitoring › Import readings history",
     ["Press <b>Import readings history</b> › <b>Download template</b>. Its <b>points</b> sheet lists every point code.",
      "Fill one row per reading: <b>point_code</b>, <b>date</b>, <b>time</b> (optional, blank = 08:00), <b>value</b>, <b>note</b>.",
      "Choose the file, press <b>Preview</b> (readings, points, period, how many critical / warning), then <b>Import</b>."],
     ("note", "Old readings appear in the trend and get a status from today’s limits, but raise no alerts. A point’s last value changes only if the imported reading is newer. Importing the same file twice adds nothing."))

part("Assets and labels", "Finding machines, their history, equipment types and printing QR labels.")
proc("Find an asset and its history", "Everyone", "Assets",
     ["Open <b>Assets</b>. <b>Hierarchy</b> shows the tree (area › line › unit › equipment); <b>List</b> lets you search by code or name.",
      "Open the asset. Tabs: <b>Details</b>, <b>History</b> (every job" + v(", including migrated 2026 jobs marked MIG", ", including imported history") + "), <b>BOM / spare parts</b>, <b>Meters / Condition monitoring</b>, <b>Lubrication</b>, <b>Attachments</b>.",
      "The <b>Reliability</b> card shows MTBF, MTTR, availability and breakdown downtime for 12 months."])
proc("Set equipment types (which failure modes apply)", "Planner, engineer", "Assets › Equipment types; asset page › Edit",
     ["Press <b>Equipment types</b> › <b>Preview</b>: the system suggests a type from each name (" + v("pump, motor, gearbox, roll, dryer cylinder, crane…", "pump, motor, gearbox, fan, compressor, conveyor, crane…") + ") for assets without one.",
      "Check the samples, then press <b>Apply to … assets</b>.",
      "For an asset it could not recognise: open it › <b>Edit</b> › <b>Equipment type</b>. Parts below an asset use its type."],
     ("note", "The type decides which failure modes are offered first on requests and work orders for that machine."))
proc("Print QR labels (A4, 24 labels per sheet)", "Planner, supervisor", "Assets › Print QR labels (also on each asset page and on Lubrication)",
     ["Open <b>Assets</b> and press <b>Print QR labels</b>.",
      "In <b>Asset and everything below it</b> choose an area to start with, e.g. " + v("Press", "Line 1") + ".",
      "Leave <b>Level</b> empty for all levels, or choose Production line and Unit for the main machines only.",
      "If the first sheet is partly used, enter how many labels are already used in <b>Labels already used on the first sheet</b>.",
      "Press <b>Download PDF</b>.",
      "First time: print one page on plain paper at <b>Actual size / 100%</b> (not “Fit to page”), lay it on the label sheet against the light and check the positions.",
      "If it matches, print on the label sheets. If not, send the size written on the label box to the administrator.",
      "Stick a label on the machine and test it with <b>Scan QR</b>."],
     ("note", "Sheet: 3 × 8 labels of 70 × 37 mm, no margin. Each label shows the QR, the code, the name and the location. At most 2,400 labels (100 sheets) per PDF; narrow the selection if asked."),
     ("tip", "On the Lubrication page, labels can be printed per route; each shows the lubricant, quantity and frequency."))

part("Shifts and roster", "Shift types and the monthly roster from Excel.")
proc("Set up shift types", "Manager, planner", "Shifts and handover › Shift types",
     ["Press <b>New shift type</b> and add each code the roster uses, e.g. <b>D</b> Day 06:00–18:00 12 h, <b>N</b> Night 18:00–06:00 12 h, <b>G</b> General 07:00–17:00 10 h.",
      "Use your real times and hours; the hours count as available manpower."])
proc("Import the roster from Excel", "Manager, planner", "Shifts and handover › Import roster (Excel)",
     ["Set <b>From</b> and <b>To</b> (up to 62 days, e.g. a whole month) and press <b>Download roster template</b>.",
      "Press <b>Enable Editing</b> in Excel. Each day cell has a drop-down: D, N, G (your shift types), OFF, L (leave), A (absence). Fridays and Saturdays are shaded but can still be duty days. Blank = no change.",
      "Save, choose the file, press <b>Preview</b> (people, entries, dates, unknown names), then <b>Import</b>."],
     ("note", "If the drop-down shows only OFF, L and A, the shift types are not set up yet: add them, then download the template again. Your own grid also works: a row starting with “Name”, then the days (day numbers or dates), several blocks allowed."),
     ("tip", "Names not in the system can be created as technicians by the administrator (tick “Create them as technicians”); they get a login after the administrator sets their e-mail and resets the password."))

part("KPIs and company KPIs", "Calculated KPIs, failure modes and the plant’s own monthly KPI sheet.")
proc("View KPIs for a period and department", "Manager, engineer, supervisor", "KPIs and reports › KPIs and reports",
     ["Set <b>From</b> and <b>To</b>. The page opens on the current month; set 1 January for the whole year.",
      "Choose a <b>Department</b> or leave it empty for the whole plant.",
      "Tap a KPI to see its formula, inclusion rules, 12-month trend and the work orders behind it.",
      "Use <b>Export XLSX</b> or <b>Export PDF</b> for reports."],
     ("note", "“Not available” means the data is missing, and the reason is shown. Values are never estimated. Maintenance cost today is spare parts only."))
proc("See the top failure modes (Pareto)", "Manager, reliability engineer, supervisor", "KPIs and reports › Failure modes",
     ["Set the period at the top of the KPIs page and open the <b>Failure modes</b> tab.",
      "Choose <b>By failure mode</b> (adds up the same mode on all equipment types), <b>By code</b> or <b>By symptom</b>.",
      "Optionally choose an asset to see only it and everything below it.",
      "The chart shows the top 10; the table gives work orders, downtime hours, share and cumulative %."],
     ("note", "Only work orders with a failure code are counted. The orange note shows how many closed breakdowns have no code: remind technicians to choose the Problem before completing."))
proc("Enter production data and budget", "Manager or planner", "KPIs and reports › Production data / Budget",
     ["Production: choose the date and department, enter " + v("<b>Tons produced</b>, <b>Good tons</b>", "the quantity produced and good quantity (tons, pieces or any unit)") + ", <b>Planned hours</b>, <b>Run hours</b> and <b>Ideal rate</b>, and save.",
      "Budget: choose department, year and month, enter the amount, and save."],
     ("tip", "These unlock OEE, maintenance cost per " + v("ton", "unit produced") + " and budget versus actual."))
proc("Enter a month of company KPIs (in the app)", "Manager", "KPIs and reports › Company KPIs",
     ["Open the <b>Company KPIs</b> tab and choose the <b>Year</b>.",
      "Press <b>Enter month</b> and choose the month (e.g. Oct 2026).",
      "Type the <b>Actual</b> for each KPI. The <b>Target</b> is filled in from the previous month; change it only if the target changed.",
      "Press <b>Save</b>. The month shows green when the target is met and red when missed."],
     ("tip", "Open the same month again to correct a value. Clearing a box deletes that value."))
proc("Update company KPIs from Excel", "Manager", "KPIs and reports › Company KPIs",
     ["Choose the <b>Year</b> and press <b>Download template</b>; it comes back filled with the saved values.",
      "Fill or change the <b>Actual</b> and <b>Target</b> rows under the month columns (YYYY-MM).",
      "Choose the file under <b>Upload filled template</b>, press <b>Preview</b>, then <b>Import</b>."],
     ("note", "A blank cell keeps the saved value; type x to delete a value. A new KPI name in the file adds a new KPI. Columns: department code (blank = whole plant), unit, higher_is_better (yes / no), cmms_kpi (optional link to a calculated KPI such as mtbf)."))

part("Roles and approvals", "What each role can do and who approves each step. The chart and table follow the procedures of this part.")
proc("Find who approves a work order", "Everyone", "Work order › Move to",
     ["Open the work order: the <b>Move to</b> buttons show only the steps your role may do.",
      "Breakdown requests: a supervisor or planner of that area accepts them; the work order is created at once.",
      "Corrective work: <b>Send for approval</b>, then a supervisor or the manager <b>approves</b> (or returns it with a question).",
      "The planner plans and schedules, the technician does the work and submits it for review, the supervisor or engineer reviews, the supervisor or manager closes."],
     ("note", "Emergency breakdowns skip approval: the technician starts at once and the area's supervisors and manager are alerted by app and e-mail. PM and lubrication work orders are created already approved."),
     ("tip", "Administrators can change which role may do each step in Administration › Workflow. The safety and completion checks always apply."))

part("Administration", "For the PlantPulse administrator only.")
proc("Add, edit, reset or remove a user", "Administrator", "Administration › Users",
     ["<b>New user</b>: name, e-mail, role, optional departments, trade and hourly rate (used for labour cost), temporary password. Save.",
      "<b>Departments</b> column in the Users list: pick one or more (" + v("PM, SP, FH, UTIL, WWTP, EAI, WS, HVAC, MOB", "PROD, MAINT, UTIL, FAC…") + "), e.g. <b>" + v("PM + SP", "PROD + UTIL") + "</b> for someone who covers two areas; the first is the main one. The person then sees only those areas (lists, alerts, KPIs, notifications). The <b>X</b> at the right of the field clears it = All departments. Leave managers, planners and reliability engineers on All.",
      "<b>Edit user</b>: change name, role, departments, trade or rate.",
      "<b>Reset password</b>: give the new temporary password to the user; they change it after signing in.",
      "<b>Disable</b> stops the user at once; <b>Remove from plant</b> removes them (their name stays on past records; the e-mail can be added again later)."])
proc("Import many users from Excel", "Administrator", "Administration › Users › Import users (Excel)",
     ["Press <b>Import users (Excel)</b> › <b>Download current users</b>: the file lists everyone already in the plant.",
      "Change any row (role, department, trade, e-mail) or add new people below. Several departments: write them like <b>" + v("PM,SP", "PROD,UTIL") + "</b>. Leave <b>old_email</b> blank on new rows; write <b>yes</b> in <b>reset_password</b> to give someone a new temporary password.",
      "Choose the file and press <b>Preview</b>: new, changed, unchanged and every error by row.",
      "Press <b>Import</b>. The temporary passwords of new people are shown once: press <b>Save passwords (CSV)</b> and give each person their own, privately."],
     ("warn", "Store the passwords file safely and delete it once handed out. Nobody is removed by an import."))
proc("Try changes on the test copy first", "Administrator", "Server terminal (PowerShell or Cloud Shell)",
     ["Connect to the server and go to <b>/opt/cmms</b>.",
      "<b>sudo bash scripts/test-copy.sh start</b> creates a copy of today's real data at <b>https://test.84-8-106-22.sslip.io</b> (red TEST label, no e-mails sent).",
      "Try imports, new settings or training there.",
      "<b>refresh</b> copies the real data again; <b>stop</b> pauses it; <b>remove</b> deletes it."],
     ("note", "Nothing done on the test copy reaches the real system."))
proc("Departments and failure codes", "Administrator", "Administration › Departments / Failure codes",
     ["<b>Departments</b>: enter code, name and type, press <b>Add</b> (e.g. " + v("WS Central Workshop, HVAC Air Conditioning, MOB Mobile Equipment, type UTIL", "PROD Production, MAINT Maintenance, UTIL Utilities, FAC Buildings &amp; Facilities") + ").",
      "<b>Failure codes</b>: press <b>Import failure codes (Excel)</b>; download the current list, add or change rows (kind: symptom / problem / cause / remedy, code, description, equipment_type, category), upload, <b>Preview</b>, <b>Import</b>.",
      "Use <b>Search</b> to find a code (e.g. " + v("PMP, ROL, ACU, MOB, bearing", "PMP, MTR, CMP, bearing") + ")."],
     ("note", v("Existing codes are updated, codes not in the file stay. Loaded so far: failure modes for 12 general and 12 paper-machine equipment types, air conditioners, forklifts and machine tools, plus standard symptoms, causes and remedies.", "Existing codes are updated, codes not in the file stay. Start from the standard catalogue (pumps, motors, gearboxes, fans, compressors, conveyors, valves, air conditioners, forklifts, machine tools) and add your own.")))
proc("Update the server to a new version", "Administrator", "PowerShell on a laptop, or Oracle Cloud Shell",
     ["Open <b>PowerShell</b> on your laptop, or sign in to <b>cloud.oracle.com</b> and open <b>Cloud Shell</b> (the >_ icon at the top).",
      "Paste the update command below and press Enter.",
      "Wait until <b>==&gt; Done</b> appears (a few minutes). Do not switch apps or lock the phone meanwhile.",
      "If the screen stops or shows “Connection closed” before Done, run the same command again; it is safe.",
      "Ask users to refresh the page or reopen the app."],
     ("code", 'ssh -t ubuntu@84.8.106.22 "cd /opt/cmms &amp;&amp; sudo git pull &amp;&amp; sudo bash deploy/install-server.sh"'),
     ("note", "The old version keeps running until the new one is ready, so users can keep working during the update."))
proc("Check the backups", "Administrator", "Oracle console › Storage › Buckets",
     ["Every night at 02:15 the server backs up the database and attachments and uploads a copy to the bucket.",
      "Open <b>Storage › Buckets</b> › the CMMS bucket › <b>Objects</b>; each night adds a dated folder with 4 files.",
      "Once a month, open the latest folder and <b>Download</b> the cmms_....dump file to a company drive."],
     ("warn", "Never share the bucket upload link (pre-authenticated request). Anyone holding it can write to the bucket."),
     ("note", "Free storage is 10 GB. Check the bucket’s usage every few months and delete old folders if it approaches 8 GB."))

part("Troubleshooting", "Quick answers to the most common problems.")
TROUBLE = [
    ("A button from this guide is missing", "Refresh the page; on a phone close the app from the recent apps list and open it again. If still missing, your role may not include it."),
    ("Play Protect warning when installing", "Install from Chrome (menu › Add to Home screen), not from Samsung Internet."),
    ("The phone camera does not open a QR label", "Use Scan QR inside the app, or type the code printed under the QR."),
    ("A KPI shows “Not available”", "Read the reason on the card: usually missing labour hours, production data, budget or rosters."),
    ("An import is refused", "Preview lists every error by row; fix them, choose the file again and preview again. Nothing is saved until all rows are valid."),
    ("I cannot start a job", "LOTO and permit must be signed off first; the message names what is missing."),
    ("I cannot close a job", "The message lists what is missing: checklist items, test result, failure code, root cause or a lock still applied."),
    ("Cloud Shell stopped updating during a server update", "Wait 3 minutes, reload the page, open Cloud Shell and run the update command again."),
    ("Forgot password", "Ask the administrator to use Reset password in Administration › Users."),
    ("I only see my own area", "Your account has departments. Ask the administrator to add the other areas you cover, or to clear the field (All departments) if you cover the whole plant."),
    ("Roster drop-down shows only OFF, L, A", "Add the shift types (D, N, G…) in Shifts and handover › Shift types, then download the template again."),
    ("A point or asset is not in the list", "Lists show the first 2,000 items: use Search or the asset tree. Excel downloads always include everything."),
    ("iPhone: no Install button", "Use the Share button › Add to Home Screen (in Safari, or Chrome’s share button)."),
]


# ---- Build ---------------------------------------------------------------------------------------------------------
def on_page(c, doc):
    c.saveState()
    if doc.page > 1:
        c.setFont("Helvetica", 8.5)
        c.setFillColor(SOFT)
        c.drawString(20 * mm, 12 * mm, "PlantPulse · Work instructions" + v(" · Paper mill edition", ""))
        c.drawRightString(190 * mm, 12 * mm, f"Page {doc.page}")
        c.setStrokeColor(LINE)
        c.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)
    c.restoreState()


story = []
# Cover
story += [Spacer(1, 50 * mm), Paragraph("PlantPulse", S["title"]), Spacer(1, 4),
          Paragraph("Maintenance management – work instructions: how to do each task, step by step" + v("<br/>Paper mill edition", "<br/>General industry edition"), S["subtitle"]), Spacer(1, 10 * mm)]
cover = Table([[Paragraph(v("Plant: PM1 · Maintenance department<br/>", "For any industrial plant: production lines, utilities, workshops, buildings<br/>") + "System: https://84-8-106-22.sslip.io<br/>Version: 31 October 2026 (PlantPulse name, users in several departments, user import from Excel, roles and approval chart)", S["body"])]], colWidths=[170 * mm])
cover.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 4, AMBER), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
story += [cover, Spacer(1, 12 * mm),
          Paragraph("Each procedure says <b>who</b> does it and <b>where</b> in the app, then gives numbered steps. "
                    "<b>Tip</b> boxes save time; <b>Important</b> boxes protect people, machines and data.", S["body"]),
          PageBreak()]
# Contents
story.append(Paragraph("Contents", S["part"]))
n = 0
for i, (_, title, _, procs) in enumerate(P, 1):
    story.append(Paragraph(f"{i}. {title}", S["tocpart"]))
    for j, pr in enumerate(procs, 1):
        story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{i}.{j}&nbsp;&nbsp;{pr[0]}", S["toc"]))
story.append(PageBreak())
# Parts
for i, (_, title, intro, procs) in enumerate(P, 1):
    if i > 1:
        story.append(CondPageBreak(90 * mm))
    story += [Paragraph(f"{i}. {title}", S["part"]), Paragraph(intro, S["partintro"])]
    for j, (ptitle, who, where, items, extras) in enumerate(procs, 1):
        head = [Paragraph(f"{i}.{j}&nbsp;&nbsp;{ptitle}", S["proc"]),
                Paragraph(f"<b>Who:</b> {who}&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;<b>Where:</b> {where}", S["meta"])]
        block = head + [steps(items)]
        for kind, text in extras:
            block += code(text) if kind == "code" else box(kind, text)
        story.append(KeepTogether(block) if len(items) <= 6 else CondPageBreak(60 * mm))
        if len(items) > 6:
            story += block
        story.append(Spacer(1, 4))
    if title == "Roles and approvals":
        roles = [("Role", "Can do / approve"),
                 ("System Administrator", "Everything; the only role that manages users, departments, plant settings and workflow"),
                 ("Maintenance Manager", "Every maintenance step: approve, plan, close, emergency closure, PM deferrals, KPIs and budgets"),
                 ("Maintenance Planner", "Triage requests, create / plan / schedule / assign work orders, PM and lubrication plans, imports. Does not approve, execute or close"),
                 ("Mechanical / Electrical Supervisor", "Triage, approve, plan, assign, execute, review, LOTO / permit sign-off, close (incl. emergencies), cancel, PM deferrals, handovers"),
                 ("Reliability Engineer", "Create work orders, review completed work, condition monitoring points and alerts, PM and lubrication plans, lubricant alternatives"),
                 ("Engineer", "Create work orders, do and review work, readings, point priority, edit assets"),
                 ("Technician", "Work requests, do the work, lubrication tasks, readings, handovers (no approvals, no KPIs)"),
                 ("Storekeeper", "Spare parts master and stock, reservations, purchase references"),
                 ("Production User", "Work requests only; sees assets, work orders, condition monitoring, KPIs"),
                 ("Management Viewer", "Sees everything read-only, exports reports")]
        t = Table([[Paragraph(f"<b>{a}</b>" if i == 0 else a, S["box"]), Paragraph(f"<b>{b}</b>" if i == 0 else b, S["box"])] for i, (a, b) in enumerate(roles)],
                  colWidths=[52 * mm, 118 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TIP_BG), ("GRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story += [Spacer(1, 4), t, PageBreak(), Image("/tmp/flow/wo.png", width=170 * mm, height=170 * mm * 1836 / 2340), Spacer(1, 6),
                  Image("/tmp/flow/other.png", width=170 * mm, height=170 * mm * 1023 / 2340)]
    if title == "Troubleshooting":
        rows = [[Paragraph("<b>Problem</b>", S["box"]), Paragraph("<b>What to do</b>", S["box"])]] + [
            [Paragraph(a, S["box"]), Paragraph(b, S["box"])] for a, b in TROUBLE]
        t = Table(rows, colWidths=[62 * mm, 108 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TIP_BG), ("GRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(t)

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=24 * mm,
                        title="PlantPulse – Work instructions" + v(" (paper mill)", " (general industry)"), author="PlantPulse")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("ok")
