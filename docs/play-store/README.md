# PlantPulse – Google Play listing kit

Everything Play Console asks for, ready to paste. Images are in this folder; all screenshots use the
DEMO sample organisation (no company data).

| Item | File | Size |
|---|---|---|
| App icon | `icon-512.png` | 512×512 |
| Feature graphic | `feature-graphic-1024x500.png` | 1024×500 |
| Phone screenshots (upload 2–8) | `1-login.png` … `7-scan.png` | 1080×1920 |

---

## 1. Main store listing

**App name** (≤30): `PlantPulse – Maintenance`
**Category**: Business (alternative: Productivity) · **Tags**: Business, Productivity
**Contact e-mail**: a support address you are happy to show publicly (not a personal one if you can avoid it)
**Website** (optional): `https://84-8-106-22.sslip.io`
**Privacy policy URL**: `https://84-8-106-22.sslip.io/privacy`

### English (en-US) – default

**Short description** (≤80):
```
Work orders, PM, lubrication and condition monitoring for maintenance teams
```

**Full description** (≤4000):
```
PlantPulse is a maintenance management system (CMMS) for industrial plants. It brings work orders, preventive maintenance, lubrication, condition monitoring and spare parts into one app that works on the shop floor as well as in the office.

PlantPulse is for organisations that run it: sign in with the account your maintenance administrator gives you.

WORK ORDERS
• Raise a work request in seconds, with standard symptoms and a photo
• Plan, assign, start and complete jobs; record labour, parts and the failure cause
• "My work" shows each technician exactly what is due today

PREVENTIVE MAINTENANCE & LUBRICATION
• Time- and meter-based PM plans that generate work orders automatically
• Lubrication routes with points, lubricants and intervals
• Overdue and upcoming work at a glance

CONDITION MONITORING (PdM)
• Vibration, temperature, oil and other readings against warning and alarm limits
• Critical points first, trends per point, alerts when a limit is crossed
• Import historical readings from Excel

ASSETS & RELIABILITY
• Asset tree with search, QR code labels and a built-in scanner
• Failure-mode catalogue, Pareto by failure mode, MTBF / MTTR KPIs
• Department-based access: every team sees its own area

BUILT FOR REAL PLANTS
• English, Arabic and Bengali interfaces
• Roles for managers, planners, supervisors, engineers and technicians
• Excel import and export for assets, plans, users and readings
• Shift rosters and notifications by department

Your organisation's data stays on its own server and is sent only over encrypted connections.
```

### Arabic (ar)

**App name**: `PlantPulse – الصيانة`

**Short description**:
```
أوامر العمل والصيانة الوقائية والتزييت ومراقبة الحالة لفرق صيانة المصانع
```

**Full description**:
```
PlantPulse نظام لإدارة الصيانة (CMMS) للمنشآت الصناعية. يجمع أوامر العمل والصيانة الوقائية والتزييت ومراقبة الحالة وقطع الغيار في تطبيق واحد يعمل في الموقع وفي المكتب.

التطبيق مخصص للمنشآت التي تستخدمه: سجّل الدخول بالحساب الذي يعطيك إياه مسؤول الصيانة.

أوامر العمل
• طلب عمل خلال ثوانٍ مع أعراض قياسية وصورة
• تخطيط وتعيين وبدء وإنهاء الأعمال مع تسجيل العمالة وقطع الغيار وسبب العطل
• شاشة "عملي" تعرض لكل فني ما هو مطلوب اليوم

الصيانة الوقائية والتزييت
• خطط صيانة حسب الوقت أو العدّاد تُنشئ أوامر العمل تلقائياً
• مسارات تزييت بالنقاط والزيوت والفترات
• الأعمال المتأخرة والقادمة في لمحة

مراقبة الحالة (PdM)
• قراءات الاهتزاز والحرارة والزيت وغيرها مع حدود التحذير والإنذار
• النقاط الحرجة أولاً، واتجاه كل نقطة، وتنبيه عند تجاوز الحد
• استيراد القراءات السابقة من Excel

المعدات والاعتمادية
• شجرة معدات مع بحث وملصقات QR وماسح مدمج
• كتالوج أنماط الأعطال وتحليل باريتو ومؤشرات MTBF / MTTR
• صلاحيات حسب القسم: كل فريق يرى منطقته

مصمم للمصانع الحقيقية
• واجهة بالإنجليزية والعربية والبنغالية
• أدوار للمدير والمخطط والمشرف والمهندس والفني
• استيراد وتصدير Excel للمعدات والخطط والمستخدمين والقراءات
• جداول الورديات والإشعارات حسب القسم

بيانات منشأتك تبقى على خادمها الخاص ولا تُنقل إلا عبر اتصال مشفّر.
```

---

## 2. App content (Policy → App content)

### Privacy policy
`https://84-8-106-22.sslip.io/privacy`

### Ads
**No, my app does not contain ads.**

### App access
**All or some functionality is restricted** → add instructions:
- Name: `Demo account`
- Username: `manager@demo.example.com`
- Password: *(the demo password you chose on the server – type it only into Play Console)*
- Other information:
  `Sign in with the account above. It belongs to a separate DEMO organisation with sample data only. No other steps are needed.`

Create the demo organisation once on the server (it is separate from the real one; you type the password, it is never shown):
```
cd /opt/cmms && sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api python -m app.cli seed-demo
```

### Content rating (IARC questionnaire)
- Category: **All other app types** (Utility / Productivity / Communication / Other)
- Violence, sexual content, profanity, drugs, gambling, horror: **No** to all
- Do users interact or exchange content? **Yes** – users inside the same organisation see each other's work orders and comments. (No public chat, no strangers.)
- Shares user location? **No** · Allows purchases of digital goods? **No** · Unrestricted internet browser? **No**
- Expected result: **Everyone / PEGI 3**

### Target audience and content
- Target age: **18 and over** only
- Appeals to children? **No**

### News app: **No** · COVID-19 tracing: **No** · Government app: **No** · Financial features: **None**
### Health apps: **None**

### Data safety
Overview:
- Collects or shares required user data? **Yes**
- All data encrypted in transit? **Yes** (HTTPS only)
- Way for users to request deletion? **Yes** – "Users ask their organisation's administrator, who can deactivate the account and delete personal data. Contact: <support e-mail>."
- Data shared with third parties? **No** · Sold? **No**

Data types collected (for every one: Collected = Yes, Shared = No, Processed ephemerally = No, **Required**, purposes = **App functionality** + **Account management**; for "Other actions / diagnostics" also **Fraud prevention, security and compliance**):

| Section | Type | Why |
|---|---|---|
| Personal info | Name | user's name on work orders |
| Personal info | Email address | sign-in |
| Personal info | User IDs | account and employee number |
| Photos and videos | Photos | photos attached to requests and work orders (optional for the user) |
| App activity | Other user-generated content | work orders, comments, readings |
| App activity | Other actions | audit log of changes |
| Device or other IDs | – | **not collected** |
| Location | – | **not collected** |

(IP address and sign-in times are kept in the security log: declare under **App activity → Other actions**, purpose **Security**.)

---

## 3. Closed testing (required for new personal accounts)

1. **Testing → Closed testing → Create track** (or use "Alpha").
2. **Testers**: create a Google Group (e.g. plantpulse-testers@googlegroups.com) or an e-mail list, and add
   at least **12 people** with Google accounts who have an Android phone.
3. **Create release** → upload the `.aab` from PWABuilder → release name `1.0.0 (1)` → notes "First test release".
4. Fill **Countries**: Saudi Arabia (and any others) → **Review and roll out**.
5. Send testers the **opt-in link** shown on the track. Each one opens it, taps *Become a tester*, then installs from Play.
6. Testers must **keep the app installed for 14 days in a row** and open it now and then. Collect feedback.
7. After 14 days with ≥12 testers: **Dashboard → Apply for production** and answer the short questionnaire
   (who tested, what feedback, what changed).
8. After approval: **Production → Create release** (same or newer `.aab`) → roll out.

Before step 3 the server must serve `/.well-known/assetlinks.json` (from PWABuilder's package),
otherwise the app shows a browser address bar.
