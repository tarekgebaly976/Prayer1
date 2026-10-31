import json, os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "modfn.py")).read())
SRC = os.path.join(HERE, "..", "deck2", "project")
ED = sys.argv[1]; PAPER = ED == "paper"
v = lambda p, g: p if PAPER else g
OUT = os.path.join(HERE, ED, "project"); shutil.rmtree(os.path.join(HERE, ED), ignore_errors=True); shutil.copytree(SRC, OUT)
SL = os.path.join(OUT, "slides")
FOOT = "PlantPulse · Modules and benefits" + v(" · Paper mill", "")
def rd(n): return open(os.path.join(SL, n + ".html")).read()
def wr(n, s): open(os.path.join(SL, n + ".html"), "w").write(s.replace("Paper Mill CMMS · Modules and benefits", FOOT))
def sub(n, a, b):
    s = rd(n); assert s.count(a) == 1, (n, a[:50]); wr(n, s.replace(a, b))

for f in os.listdir(SL):
    n = f[:-5]; s = rd(n).replace("Paper Mill CMMS · Modules and benefits", FOOT); wr(n, s)

# cover
sub("cover", "PM1 · Maintenance department", v("PM1 · Maintenance department · Paper mill edition", "Maintenance management for industrial plants"))
sub("cover", ">Paper Mill CMMS</h1>", ">PlantPulse</h1>")
sub("cover", "How each part of the system works, and what it gives our maintenance team, our machines and our management",
    v("How each part of the system works, and what it gives our maintenance team, our machines and our management",
      "How each part of the system works, and what it gives a maintenance team, its machines and its management – in any industry"))
sub("cover", "updated 28 October 2026", "updated 31 October 2026")

# admin + new approvals slide
s = rd("admin"); num = re.search(r">Module (\d+) · ", s).group(1)
wr("admin", module("admin", "Administration", "Controlled access by role and by area", [
   "Named users with a role and <b>one or more departments</b> (" + v("e.g. PM + SP", "e.g. PROD + UTIL") + "), set from the Users list",
   "A user sees only those areas: work orders, requests, PM, lubrication, condition monitoring, assets, KPIs, notifications",
   "<b>Import users (Excel)</b>: add or change many people at once; temporary passwords shown once to hand out",
   "Audit log of every change; nightly backup plus an off-server copy; a <b>test copy</b> for safe trials"],
   ["Each person sees and does only their part", "Supervisors covering two areas with one login", "All technicians get a login in one step", "Every action traceable to a named person"],
   "Roles: system administrator, maintenance manager, planner, mechanical and electrical supervisor, reliability engineer, engineer, technician, storekeeper, production user, management viewer. The test copy (test address, red TEST label, no e-mails) holds a copy of the real data for training and trying imports."))
chain = [("Request", "Technician · Production · Engineer", "#E8F5E9"), ("Triage", "Supervisor · Planner", "#FFF8E1"),
         ("Approve", "Supervisor · Manager", "#FFF8E1"), ("Plan &amp; assign", "Planner · Supervisor", "#F4F6F3"),
         ("Safety sign-off", "Supervisor (LOTO / permit)", "#FFF8E1"), ("Do the work", "Technician · Engineer", "#F4F6F3"),
         ("Review", "Supervisor · Engineer · Reliability", "#FFF8E1"), ("Close", "Supervisor · Manager", "#E3F2FD")]
boxes = "\n".join(f'<div style="flex:1;background:{c};border:3px solid #102A33;border-radius:16px;padding:18px 14px;display:flex;flex-direction:column;gap:8px;min-height:200px"><p style="font-family:Rubik, Arial, sans-serif;font-size:28px;font-weight:600;color:#102A33">{i}. {a}</p><p style="font-size:22px;line-height:1.35;color:#23616D">{b}</p></div>' + ('<p style="font-size:34px;color:#102A33;align-self:center">→</p>' if i < len(chain) else "") for i, (a, b, c) in enumerate(chain, 1))
wr("approvals", f'''<section id="approvals" data-transition="fade" style="background:#F4F6F3;color:#102A33;font-family:'Public Sans', Arial, sans-serif;padding:112px 128px 160px;display:flex;flex-direction:column;gap:36px">
<p style="font-size:24px;letter-spacing:3px;text-transform:uppercase;color:#23616D;font-weight:700">Module 00 · Approvals</p>
<h2 style="font-family:Rubik, Arial, sans-serif;font-size:64px;font-weight:600;line-height:1.1;color:#102A33">Who approves each step of a job</h2>
<div style="display:flex;gap:10px;align-items:stretch">
{boxes}
</div>
<div style="display:flex;gap:48px">
<div style="flex:1;background:#FDECEA;border-left:8px solid #C62828;border-radius:12px;padding:24px 28px"><p style="font-size:26px;line-height:1.4"><b>Emergency breakdown:</b> skips approval, the technician starts at once; supervisors and manager of the area alerted by app and e-mail; closing needs the root cause.</p></div>
<div style="flex:1;background:#FFF8E1;border-left:8px solid #E3A72F;border-radius:12px;padding:24px 28px"><p style="font-size:26px;line-height:1.4"><b>Cannot be skipped:</b> LOTO locks removed, permit signed, test passed, checklist done, failure codes and root cause before a job is closed.</p></div>
</div>
<p style="position:absolute;left:128px;bottom:64px;width:1200px;font-size:24px;color:#5E6E73">{FOOT}</p>
<p style="position:absolute;right:128px;bottom:64px;width:200px;text-align:right;font-size:24px;color:#5E6E73">0</p>
<aside>PM and lubrication work orders are created already approved. PM deferrals are approved by supervisors or the manager; lubricant alternatives by the reliability engineer or manager. Administrators can change who may do each step (Administration › Workflow); the safety and completion checks always apply. Users limited to departments act only on their own areas. The full roles document with the complete permission matrix is available.</aside>
</section>
''')

# what's new
items = [("PlantPulse", "New name and icon; works for any plant"), ("Several departments", "One user can cover e.g. " + v("PM + SP", "PROD + UTIL")),
         ("User import", "Many users from Excel, temporary passwords once"), ("Approval chart", "Roles document and who approves each step"),
         ("Test copy", "Safe copy of real data for training and trials"), ("Google Play", "Store listing, privacy page and app icon ready"),
         v(("New areas", "Workshop, 171 AC units, forklifts and loader"), ("Failure modes", "Catalogue by equipment type, Top-10 Pareto")),
         ("Condition monitoring", "Critical first, priorities and history from Excel")]
cards = "\n".join(f'<div style="background:#1C3D48;border-radius:18px;padding:26px 30px;display:flex;flex-direction:column;gap:8px"><h3 style="font-family:Rubik, Arial, sans-serif;font-size:32px;font-weight:600;color:#E3A72F">{a}</h3><p style="font-size:24px;line-height:1.35;color:#DCE6E8">{b}</p></div>' for a, b in items)
s = rd("whatsnew")
s = re.sub(r'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:24px">.*?</div>\n<p style="position', '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:24px">\n' + cards + '\n</div>\n<p style="position', s, flags=re.S)
s = s.replace(">What changed since the first presentation<", ">What is new in PlantPulse<")
s = re.sub(r"<aside>.*?</aside>", "<aside>All of these are live on the server except the Play Store app, which is in preparation. Details are on each module slide.</aside>", s, flags=re.S)
wr("whatsnew", s)

# next steps
sub("next", "<b>Excel user import</b> so every technician gets a login in one step", "<b>PlantPulse on Google Play,</b> after closed testing with 12 testers")
sub("next", "<b>PM plans for the new areas:</b> AC filters, forklift services, workshop machines",
    v("<b>PM plans for the new areas:</b> AC filters, forklift services, workshop machines", "<b>Ready-made PM templates</b> for pumps, motors, compressors, ACs and forklifts"))
sub("next", "Send ideas from your area to the CMMS administrator", "Send ideas from your area to the PlantPulse administrator")

if not PAPER:
    sub("assets", "About 8,500 assets in a tree", "Thousands of assets in a tree")
    sub("assets", "<aside>New areas added: Central Workshop (WS), Air Conditioning (HVAC, 171 units) and Mobile Equipment (MOB, forklifts and wheel loader).",
        "<aside>Any area can be added: production lines, utilities, workshops, air conditioning, mobile equipment, buildings.")
    sub("assets", "(pump, motor, gearbox, roll…)", "(pump, motor, gearbox, fan, compressor…)")
    sub("company", "MTBF and MTTR for PM and FH are linked", "MTBF and MTTR per department are linked")
    sub("company", "<aside>Seven KPIs today: Major Breakdown (OPI), Maintenance Adherence, Maintenance Cost, MTBF and MTTR for PM and FH.",
        "<aside>Typical KPIs: major breakdowns, maintenance adherence, maintenance cost, MTBF and MTTR per department.")
    sub("failure", "12 general types, 12 paper-machine types, ACs, forklifts, machine tools", "pumps, motors, gearboxes, fans, compressors, conveyors, ACs, forklifts, machine tools")
    sub("pdm", "(e.g. PM-DRYER-04-CM24). Example: all 73 dryer cylinders' bearing points marked Critical and 290 historical bearing temperatures imported.",
        "(e.g. L1-PUMP-04-CM24). Example: every bearing point of the critical pumps and fans marked Critical in one Excel upload, and years of past readings imported.")
    sub("parts", "<aside>2026 history already holds 611 spare-part lines worth SAR 1.02 million. ", "<aside>Past spare-part usage can be imported from Excel. ")
    sub("shutdowns", "next planned paper machine shutdown", "next planned line shutdown")
    for f in os.listdir(SL):
        t = rd(f[:-5])
        for w in ("aper machine", "Paper Mill", "dryer", "PM1", "8,500", "SAR 1.02", "PM and FH", "WWTP"):
            assert w not in t, (f, w)

# order + numbering
d = json.load(open(os.path.join(OUT, "deck.json")))
d["title"] = "PlantPulse – Modules and Benefits" + v(" (Paper Mill)", " (General Industry)")
o = d["order"]; o.insert(o.index("admin") + 1, "approvals"); d["order"] = o
d["sections"]["s6"]["description"] = "Platform: notifications, administration and approvals, imports, mobile and languages"
json.dump(d, open(os.path.join(OUT, "deck.json"), "w"), ensure_ascii=False)
m = 0
for i, sid in enumerate(o, 1):
    s = rd(sid)
    if re.search(r">Module \d+ · ", s):
        m += 1; s = re.sub(r">Module \d+ · ", f">Module {m:02d} · ", s, 1)
    s = re.sub(r'(text-align:right;font-size:24px;color:#[0-9A-Fa-f]{6}">)\d+(</p>)', lambda x: f"{x.group(1)}{i}{x.group(2)}", s, 1)
    wr(sid, s)
c = rd("cover"); c = re.sub(r"\d+ modules · as running", f"{m} modules · as running", c); wr("cover", c)
print(ED, len(o), "slides,", m, "modules")
