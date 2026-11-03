# دليل تشغيل PlantPulse (المنتج) – كل الأوامر في مكان واحد

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
| `--lang en` | إيميل الترحيب بالإنجليزي (الافتراضي عربي) |
| `--no-welcome` | لا ترسل إيميل ترحيب (ستسلّم البيانات بنفسك) |
| `--currency USD` / `--timezone Asia/Dubai` | الافتراضي SAR و Asia/Riyadh |

**ماذا يحدث:** خلال 2-3 دقائق يُنشأ النظام، ويصل للمسؤول **إيميل ترحيب** من `noreply@plantpulse-cmms.com`
فيه العنوان وكلمة السر الأولى وخطوات البداية، وتظهر نفس البيانات على شاشتك.
أول فتح للعنوان قد يأخذ ~20 ثانية (إصدار شهادة HTTPS).

**بعدها:** تأكد أن العميل دخل وغيّر كلمة السر. إذا لم يصله الإيميل (شركات كثيرة تحجز الإيميلات من دومين جديد)،
اطلب منه النظر في Junk / Quarantine أو أرسل له البيانات بنفسك.

---

## 3. أوامر العملاء اليومية

| المطلوب | الأمر |
|---|---|
| قائمة العملاء وحالتهم والذاكرة المتاحة | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh list` |
| بيانات عميل (العنوان، الإيميل، كلمة السر الأولى) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh show alsafi` |
| إعادة إرسال إيميل الترحيب | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome alsafi` |
| مستخدم نسي كلمة السر | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh reset-password alsafi user@alsafi.com` |
| نسخة احتياطية الآن | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh backup alsafi` |
| إيقاف مؤقت (مثلاً لم يدفع) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop alsafi` |
| تشغيل بعد الإيقاف | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh start alsafi` |
| سجل الأخطاء | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh logs alsafi` |
| حذف عميل نهائياً (بعد نسخة احتياطية أخيرة) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remove alsafi --yes` |

**النسخ الاحتياطي:** تلقائي كل ليلة 2:45 لكل العملاء، يُحفظ 14 يوماً في `/opt/plantpulse-backups/اسم-العميل`.
⚠️ النسخ حالياً **على نفس الخادم** – الخطوة التالية: نسخة خارج الخادم.

**استرجاع نسخة احتياطية** (يستبدل كل بيانات العميل الحالية؛ يأخذ نسخة أمان أولاً):
```
ssh ubuntu@84.8.106.22 sudo ls /opt/plantpulse-backups/alsafi
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh restore alsafi /opt/plantpulse-backups/alsafi/اسم-الملف.dump --yes
```
(انسخ اسم الملف `….dump` من نتيجة الأمر الأول؛ التاريخ والوقت فيه بتوقيت الخادم UTC.)

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

## 9. قائمة تحقق: عميل جديد يدفع

1. ☐ اتفاق مكتوب (السعر، مدة الاشتراك، الدعم، من يُدخل البيانات).
2. ☐ اسم قصير للعنوان + إيميل مسؤول عند العميل.
3. ☐ `customer.sh new …` ← تأكد من وصول إيميل الترحيب.
4. ☐ العميل دخل وغيّر كلمة السر.
5. ☐ استيراد الأصول وخطط الصيانة من قوالب Excel (مساعدة منك في الأيام الأولى).
6. ☐ تدريب قصير: المخطط، المشرفين، الفنيين (الموبايل).
7. ☐ تأكد أن النسخ الاحتياطي يعمل: `customer.sh backup الاسم`.
