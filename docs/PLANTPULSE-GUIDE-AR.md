# دليل تشغيل PlantPulse (المنتج) – كل الأوامر في مكان واحد

English version: [PLANTPULSE-GUIDE.md](PLANTPULSE-GUIDE.md) · عميل يطلب تجربة: [TRIAL-PLAYBOOK.md](TRIAL-PLAYBOOK.md)

كل الأوامر تُكتب في **Cloud Shell** (أو PowerShell على الكمبيوتر)، كل سطر لوحده، ثم Enter.
الأوامر مكتوبة **بدون علامات تنصيص** حتى لا يغيّرها كيبورد الموبايل.

> ⚠️ لا ترسل كلمات السر أو المفاتيح (`re_...`) في أي شات أو صورة.

---

## 1. ماذا يوجد على الخادم

الخادم: Oracle `84.8.106.22` (A1.Flex، 2 معالج، 12 GB ذاكرة، 45 GB تخزين، Swap 4 GB).

| النظام | العنوان | ملاحظات |
|---|---|---|
| Obeikan (الحقيقي) | https://84-8-106-22.sslip.io | لا يُلمس إلا بأمر التحديث الخاص به |
| Obeikan نسخة تجربة | https://test.84-8-106-22.sslip.io | `scripts/test-copy.sh` |
| موقع المنتج | https://plantpulse-cmms.com | `scripts/site.sh` |
| النسخة التجريبية | https://demo.plantpulse-cmms.com | `scripts/demo.sh` – بيانات تجريبية، تعود كل ليلة 3:00 |
| العملاء | https://اسم-العميل.plantpulse-cmms.com | `scripts/customer.sh` – لكل عميل نظام مستقل |

كل الأنظمة منفصلة: قاعدة بيانات ومرفقات خاصة لكل واحد. لا يرى أي عميل بيانات غيره.

---

## الإيميلات التي تصلك من الموقع

كل التنبيهات تصل إلى `plantpulse.cmms@gmail.com`، والعنوان يوضح من أي نموذج:

| العنوان | من | ماذا وصل للزائر | ماذا تفعل |
|---|---|---|---|
| **🟢 جرّب الـ Demo – Demo access**: الشركة (الاسم) | زر "جرّب الـ Demo" | رابط وكلمة سر **الـ Demo المشترك** تلقائياً | لا شيء مطلوب. تابعه بعد يوم أو يومين |
| **📞 طلب تواصل – Contact request**: الشركة (الاسم) | نموذج "تواصل معنا" | تأكيد + رابط الـ Demo المشترك | **رد أو اتصل خلال يوم عمل** (Reply يصل للزائر مباشرة) |

**الموقع لا ينشئ نظاماً خاصاً لأي عميل وحده.** نظام التجربة الخاص (القسم التالي) تنشئه أنت فقط، بعد الكلام مع العميل.

---

## 2. عميل جديد ✅ (الأهم)

**قبل التشغيل:** اسم قصير بالإنجليزي، حروف صغيرة وأرقام و `-` فقط (مثل `alsafi` أو `nada-food`).
الأسماء المحجوزة: `www demo test api app admin mail` …

```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh new alsafi it@alsafi.com Al Safi Paper Co
```

- `alsafi` ← اسم العنوان: https://alsafi.plantpulse-cmms.com
- `it@alsafi.com` ← إيميل أول مسؤول (Admin) عند العميل
- `Al Safi Paper Co` ← اسم الشركة (كلمات عادية بدون علامات تنصيص)

**إضافات اختيارية في آخر السطر:**

| الإضافة | المعنى |
|---|---|
| `--departments paper` | أقسام مصنع ورق (PM, SP, FH…). الافتراضي `general` (إنتاج، صيانة، مرافق، مباني) |
| `--departments none` | بدون أقسام، العميل يضيفها بنفسه |
| `--plant Mill No 2` | اسم المصنع (الافتراضي Main plant) |
| `--trial 30` | فترة تجربة 30 يوماً (بدونها = عميل مدفوع) |
| `--lang en` | إيميل الترحيب بالإنجليزي (الافتراضي عربي) |
| `--currency USD` / `--timezone Asia/Dubai` | الافتراضي SAR و Asia/Riyadh |

**ماذا يحدث:** خلال 2-3 دقائق يُنشأ النظام وتظهر بياناته على شاشتك (العنوان، الإيميل، كلمة السر الأولى).
**لا يُرسل أي شيء للعميل** حتى توافق أنت. أول فتح للعنوان قد يأخذ ~20 ثانية (إصدار شهادة HTTPS).

**ثم 3 خطوات:**

1. **راجع النظام بنفسك:** افتح العنوان وادخل بالبيانات التي ظهرت، تأكد من اسم الشركة والمصنع والأقسام.
2. **شاهد إيميل الترحيب بدون إرسال:**
   ```
   ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi --preview
   ```
3. **عند الموافقة، أرسله:**
   ```
   ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi
   ```
   (لتغيير اللغة: أضف `--lang en` أو `--lang ar` في آخر السطر.)

الإيميل يخرج من `noreply@plantpulse-cmms.com` وفيه العنوان وكلمة السر الأولى وخطوات البداية، والرد يصل إلى
`plantpulse.cmms@gmail.com`. أمر `show` يوضح هل أُرسل ومتى.

**بعدها:** تأكد أن العميل دخل وغيّر كلمة السر. إذا لم يصله الإيميل (شركات كثيرة تحجز الإيميلات من دومين جديد)،
اطلب منه النظر في Junk / Quarantine أو أرسل له البيانات بنفسك.

---

## 3. أوامر العملاء اليومية

| المطلوب | الأمر |
|---|---|
| قائمة العملاء وحالتهم والذاكرة المتاحة | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh list` |
| بيانات عميل (العنوان، الإيميل، كلمة السر الأولى، هل أُرسل الترحيب) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh show alsafi` |
| معاينة إيميل الترحيب (بدون إرسال) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi --preview` |
| إرسال إيميل الترحيب (أو إعادته) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi` |
| مستخدم نسي كلمة السر | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh reset-password alsafi user@alsafi.com` |
| نسخة احتياطية الآن | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh backup alsafi` |
| إيقاف مؤقت (يرى العميل صفحة "متوقف مؤقتاً"، البيانات محفوظة) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop alsafi` |
| تشغيل بعد الإيقاف | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh start alsafi` |
| سجل الأخطاء | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh logs alsafi` |
| حذف عميل نهائياً (بعد نسخة احتياطية أخيرة) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remove alsafi --yes` |

### فترة التجربة

- عميل بتجربة: أضف `--trial 30` عند الإنشاء. `list` و `show` يوضحان تاريخ الانتهاء وكم يوماً بقي.
- **يصلك إيميل تذكير** على `plantpulse.cmms@gmail.com` قبل الانتهاء بـ 7 أيام، وقبلها بيوم، ويوم الانتهاء،
  ثم كل أسبوع بعد الانتهاء – وفيه الأوامر الجاهزة للنسخ.
- **لا يتوقف أي شيء تلقائياً.** القرار لك:

| القرار | الأمر |
|---|---|
| دفع ← عميل دائم | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh activate alsafi` |
| تمديد التجربة 14 يوماً | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh extend alsafi 14` |
| إيقاف مؤقت | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop alsafi` |
| معاينة تذكير للعميل (بدون إرسال) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remind alsafi --preview` |
| إرسال التذكير للعميل بعد موافقتك | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remind alsafi` |

`activate` و `extend` يعيدان تشغيل العميل تلقائياً إذا كان متوقفاً.

**النسخ الاحتياطي:** تلقائي كل ليلة 2:45 لكل العملاء: نسخة على الخادم (14 يوماً في `/opt/plantpulse-backups/اسم-العميل`)
**ونسخة خارج الخادم** في Oracle Object Storage (نفس مكان نسخ Obeikan، داخل `customers/اسم-العميل/`).
السجل: `ssh ubuntu@84.8.106.22 sudo tail -20 /var/log/plantpulse-customers.log`

**استرجاع نسخة احتياطية** (يستبدل كل بيانات العميل الحالية؛ يأخذ نسخة أمان أولاً):
```
ssh ubuntu@84.8.106.22 sudo ls /opt/plantpulse-backups/alsafi
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh restore alsafi /opt/plantpulse-backups/alsafi/اسم-الملف.dump --yes
```
(انسخ اسم الملف `….dump` من نتيجة الأمر الأول؛ التاريخ والوقت فيه بتوقيت الخادم UTC.)

---

## نسيت كلمة السر (للمستخدمين)

في صفحة الدخول رابط **"نسيت كلمة السر؟"**: المستخدم يكتب إيميله ← يصله رابط يعمل **مرة واحدة ولمدة 30 دقيقة** ←
يختار كلمة سر جديدة. بعدها يُسجَّل خروجه من كل الأجهزة، ويُفك أي قفل على الحساب، ويصله إيميل "تم تغيير كلمة السر".

- الرد دائماً واحد سواء كان الإيميل مسجلاً أم لا (لا أحد يعرف من عنده حساب)، وأقصى 3 روابط لكل حساب في الساعة.
- يعمل فقط إذا كان الإيميل مفعّلاً في النظام. إذا ظهرت للمستخدم رسالة **"اطلب من مسؤول النظام"** فالإيميل مقفول:
  الـ admin يغيّر كلمة السر من **Admin ← Users ← Edit ← Reset password**، أو أنت من Cloud Shell:
  - عميل: `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh reset-password alsafi user@alsafi.com`
  - Obeikan: `ssh -t ubuntu@84.8.106.22 "cd /opt/cmms && sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api python -m app.cli reset-password --email user@company.com"`
- مقفول دائماً في الـ Demo (الحسابات مشتركة بين كل الزوار).
- **تشغيل الإيميل على Obeikan** (نفس مُرسِل الموقع عبر Resend):
  ```
  ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/main-mail.sh reset-only
  ```
  `reset-only` = روابط كلمة السر فقط (التنبيهات والملخص اليومي تبقى داخل البرنامج) · `all` = كل الإيميلات
  (طوارئ، تنبيهات حرجة، ملخص يومي) · `off` = إيقاف · `status` = الحالة الآن.
- لم يصل الإيميل؟ Junk / Quarantine عند المستخدم، أو حالته في https://resend.com/emails .

---

## 4. التحديثات (نسخة جديدة من البرنامج)

الترتيب الآمن دائماً: **جرّب أولاً ← ثم العملاء ← ثم Obeikan**.

| الخطوة | الأمر |
|---|---|
| 1. تنزيل الكود الجديد | `ssh ubuntu@84.8.106.22 sudo git -C /opt/cmms pull` |
| 2. تجربة على نسخة Obeikan التجريبية | `ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/test-copy.sh update` |
| 3. تحديث النسخة التجريبية (Demo) + بيانات جديدة | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/demo.sh launch-update` |
| 4. تحديث كل العملاء | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh launch-update-all` |
| 5. Obeikan الحقيقي (آخر شيء) | `ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/deploy/install-server.sh` |

أوامر `launch-…` تعمل على الخادم وحدها (5-15 دقيقة) حتى لو أُغلق Cloud Shell. لمعرفة التقدم:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/demo.sh progress
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh progress
```
`STILL RUNNING` = لم ينتهِ بعد، `FINISHED` = انتهى (اقرأ آخر سطر).

---

## 5. الموقع والإيميلات

| المطلوب | الأمر |
|---|---|
| من طلب عرضاً أو جرّب الـ Demo | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh requests` |
| إيميل تجربة | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh test-mail` |
| سجل الموقع | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh logs` |
| بعد تعديل نص الصفحة | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh update` |
| حسابات وكلمة سر الـ Demo | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/demo.sh accounts` |

**الإيميلات** تخرج من `noreply@plantpulse-cmms.com` عبر **Resend** (مجاني: 3,000 شهرياً، 100 يومياً لكل الأنظمة معاً).
الردود تذهب إلى `plantpulse.cmms@gmail.com`. حالة كل إيميل: https://resend.com/emails
(Delivered = وصل لسيرفر المستلم؛ إن لم يجده فهو في Junk/Quarantine عندهم).

**تغيير مفتاح Resend** (إذا انكشف): أنشئ مفتاحاً جديداً في Resend ← API Keys، احذف القديم، ثم:
```
ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/site.sh resend noreply@plantpulse-cmms.com
```
(الصق المفتاح عندما يُطلب). ثم أعطِ كل العملاء نفس الإعداد:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh mail-sync
```

---

## 6. السعة: كم عميلاً يتحمل الخادم؟

- كل عميل صغير ≈ **0.5 GB ذاكرة** و **1-3 GB تخزين**.
- الخادم الحالي: ~**10 عملاء** (يتوقف `customer.sh new` إذا قلّت الذاكرة المتاحة عن 1.2 GB).
- للتوسع **مجاناً**: Oracle ← Compute ← Instance ← Edit ← Shape: حتى **4 معالجات و 24 GB**، والتخزين حتى 200 GB
  (يحتاج إعادة تشغيل الخادم دقيقتين – في وقت هادئ) ⇒ ~30-40 عميلاً.
- لتوفير ذاكرة: أوقف نسخة Obeikan التجريبية عند عدم الحاجة:
  `ssh -t ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/test-copy.sh stop`

---

## 7. Oracle والتكاليف

- الحساب **Pay As You Go**، والخادم **Always Free** ⇒ لا تكلفة طالما لم يُنشأ شيء جديد.
- **تنبيه ميزانية €1** يرسل إيميل إذا بدأ أي صرف.
- ⚠️ لا تنشئ Instance / Volume / Load Balancer / Database جديدة دون مراجعة.

---

## 8. طوارئ

| المشكلة | ماذا تفعل |
|---|---|
| موقع لا يفتح (أي عنوان) | `ssh ubuntu@84.8.106.22 sudo docker ps` – كل الأنظمة يجب أن تكون `Up` |
| عنوان عميل لا يفتح | `customer.sh list` (RUNNING يجب 4/4) ثم `customer.sh start الاسم` |
| الخادم بطيء أو امتلأ | `ssh ubuntu@84.8.106.22 free -h` و `ssh ubuntu@84.8.106.22 df -h /` |
| تنظيف مساحة التخزين | `ssh ubuntu@84.8.106.22 sudo docker image prune -f` |
| إعادة تشغيل الخادم بالكامل | من Oracle ← Instance ← Reboot. كل الأنظمة تعود وحدها (restart: unless-stopped) |

---

## إعادة نظام Obeikan الأساسي إلى أمثلة فقط

يمسح كل البيانات التشغيلية (الأصول، PM، PdM، التزييت، أوامر العمل، الطلبات، المرفقات …)، ويُبقي المستخدمين
وكلمات السر والأقسام، ويضيف أمثلة وهمية (أكواد `EX-…`)، ويحدّث نسخة التجربة. يأخذ نسخة احتياطية كاملة أولاً،
وتجربة جافة (Dry run) قبل أي مسح.
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh status
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh WIPE-ALL-DATA
```
النسخة الاحتياطية التي تُؤخذ قبل المسح تُنسخ إلى `/opt/cmms-backups/keep/` – هذا المجلد لا يُحذف منه شيء أبداً
(الحذف التلقائي بعد 14 يوماً لا يلمسه)، لذلك يمكن إرجاع البيانات القديمة **في أي وقت**، حتى بعد سنوات.

**سجل – مسح بيانات Obeikan يوم 2026-11-03.** البيانات القديمة (الأصول، PM، PdM، أوامر العمل، المرفقات …) محفوظة في:
- الخادم: `/opt/cmms-backups/keep/cmms_<الوقت>.dump` (+ `storage_<الوقت>.tar.gz` للمرفقات)
- خارج الخادم: Oracle Object Storage، مجلد `20261103/` (لا يُحذف تلقائياً)

عرض المحفوظ، ثم إرجاع البيانات القديمة (يستبدل الأمثلة وأي شيء أُدخل بعد المسح):
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh kept
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/reset-to-examples.sh undo /opt/cmms-backups/keep/cmms_FILE-NAME.dump
```
لحفظ أي نسخة أخرى للأبد: `… reset-to-examples.sh keep /opt/cmms-backups/cmms_FILE-NAME.dump`.
لو ضاع الخادم نفسه: نزّل الملفات الأربعة من مجلد `20261103/` في Object Storage إلى `/opt/cmms-backups/keep/`
على الخادم الجديد ثم نفّذ نفس سطر `undo`.

## 9. قائمة تحقق: عميل جديد يدفع

1. ☐ اتفاق مكتوب (السعر، مدة الاشتراك، الدعم، من يُدخل البيانات).
2. ☐ اسم قصير للعنوان + إيميل مسؤول عند العميل (+ `--trial 30` إذا كانت تجربة).
3. ☐ `customer.sh new …` ← ادخل وراجع النظام بنفسك.
4. ☐ `customer.sh welcome الاسم --preview` ثم `customer.sh welcome الاسم` ← تأكد من وصول الإيميل.
5. ☐ العميل دخل وغيّر كلمة السر.
6. ☐ استيراد الأصول وخطط الصيانة من قوالب Excel (مساعدة منك في الأيام الأولى).
7. ☐ تدريب قصير: المخطط، المشرفين، الفنيين (الموبايل).
8. ☐ تأكد أن النسخ الاحتياطي يعمل: `customer.sh backup الاسم`.
