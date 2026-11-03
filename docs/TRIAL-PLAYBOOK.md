# عميل يطلب تجربة – خطوة بخطوة / Trial request playbook

English below. الأوامر تُكتب في **Cloud Shell**، كل سطر لوحده، ثم Enter. لا ترسل كلمة السر في أي شات أو صورة.
الدليل الكامل: [PLANTPULSE-GUIDE-AR.md](PLANTPULSE-GUIDE-AR.md) · [PLANTPULSE-GUIDE.md](PLANTPULSE-GUIDE.md)

---

## قبل أي شيء: الـ Demo المشترك ≠ نظام تجربة خاص

| | الـ Demo المشترك | نظام تجربة خاص |
|---|---|---|
| الرابط | `demo.plantpulse-cmms.com` للكل | `NAME.plantpulse-cmms.com` لكل شركة |
| البيانات | مصنع تجريبي، يعود لأصله كل ليلة | فارغ، بيانات العميل الحقيقية، **محفوظة** |
| من ينشئه | الموقع **تلقائياً** (الإيميل 🟢 أو 📞) | **أنت فقط**، بالأوامر أدناه |

الإيميلات 🟢 / 📞 تعني أن الزائر استلم رابط الـ Demo المشترك فقط. **أنشئ نظام تجربة خاص فقط بعد الكلام مع العميل
والاتفاق على تجربة جادة.**

## ما تحتاجه من العميل

| | مثال | ملاحظة |
|---|---|---|
| **NAME** – اسم قصير للعنوان | `opi` | إنجليزي، حروف صغيرة وأرقام و `-` فقط |
| **EMAIL** – إيميل أول مسؤول (Admin) | `it@company.com` | سيصله إيميل الترحيب |
| **COMPANY** – اسم الشركة | `OPI` | كلمات عادية بدون علامات تنصيص |
| القطاع | ورق / عام | ورق ⇒ `--departments paper`، غير ذلك اتركه |
| اللغة | عربي / إنجليزي | إنجليزي ⇒ `--lang en` |
| المدة | 30 يوماً | `--trial 30` |

## 1. أنشئ نظام التجربة (دقيقتان تقريباً)

```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh new NAME EMAIL COMPANY --trial 30
```
مثال لمصنع ورق، إيميل بالإنجليزي:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh new opi it@company.com OPI --trial 30 --departments paper --lang en
```
في النهاية يظهر: العنوان `https://NAME.plantpulse-cmms.com`، الإيميل، **كلمة السر الأولى**، وتاريخ انتهاء التجربة.
**لم يُرسل أي شيء للعميل بعد.**

## 2. راجع النظام بنفسك

افتح `https://NAME.plantpulse-cmms.com` وادخل بالإيميل وكلمة السر التي ظهرت (أول فتح قد يأخذ ~20 ثانية).
المفروض: نظام فارغ، اسم الشركة صحيح، الأقسام صحيحة.

## 3. شاهد إيميل الترحيب ثم أرسله

```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome NAME --preview
```
إذا كان صحيحاً:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome NAME
```
يصله من `noreply@plantpulse-cmms.com`: الرابط، كلمة السر، وخطوات البداية (تغيير كلمة السر، إضافة المستخدمين،
استيراد الأصول من Excel). إذا لم يصله: Junk / Quarantine عندهم، أو أرسل له البيانات بنفسك.

## 4. خلال التجربة

- يصلك تذكير على `plantpulse.cmms@gmail.com` قبل الانتهاء بـ 7 أيام، وبيوم، ويوم الانتهاء – وفيه الأوامر جاهزة.
- **لا يتوقف شيء تلقائياً.** القرار لك:

| القرار | الأمر |
|---|---|
| دفع ← عميل دائم | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh activate NAME` |
| يحتاج وقتاً أكثر | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh extend NAME 14` |
| لم يكمل (صفحة "متوقف مؤقتاً"، البيانات محفوظة) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop NAME` |
| تذكير للعميل: معاينة ثم إرسال | `… customer.sh remind NAME --preview` ثم `… customer.sh remind NAME` |
| حالة كل العملاء | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh list` |
| بياناته (العنوان، كلمة السر الأولى، الترحيب أُرسل؟) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh show NAME` |
| مجرد تجربة داخلية – حذف نهائي (بعد نسخة احتياطية) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remove NAME --yes` |

---

## سجل العميل (انسخه لكل عميل تجربة واحفظه عندك – بدون كلمات سر)

```
الشركة:                    
الاسم في العنوان (NAME):     https://______.plantpulse-cmms.com
المسؤول عند العميل:         الاسم ______  الإيميل ______  الجوال ______
القطاع / الأقسام:            general / paper
بداية التجربة:   ____/__/__     نهاية التجربة: ____/__/__
إيميل الترحيب أُرسل:         نعم / لا   تاريخ ______
العميل دخل وغيّر كلمة السر:  نعم / لا
استيراد الأصول من Excel:     نعم / لا
تدريب:                       المخطط ☐  المشرفين ☐  الفنيين ☐
متابعة (مكالمة/زيارة):       ______
القرار النهائي:              activate / extend ___ يوماً / stop / remove
ملاحظات:
```

---
---

# Trial request playbook (English)

Type the commands in **Cloud Shell**, one line at a time. Never send passwords in a chat or a screenshot.

## First: shared demo ≠ private trial system

| | Shared demo | Private trial system |
|---|---|---|
| Address | `demo.plantpulse-cmms.com` for everybody | `NAME.plantpulse-cmms.com`, one per company |
| Data | Sample factory, reset every night | Empty; the customer's real data, **kept** |
| Created by | The website, **automatically** (e-mail 🟢 or 📞) | **Only you**, with the commands below |

The 🟢 / 📞 e-mails mean the visitor got the shared demo only. **Create a private trial only after you have talked to
the customer and agreed on a real trial.**

## What you need from the customer

| | Example | Note |
|---|---|---|
| **NAME** – short name for the address | `opi` | lowercase letters, digits and `-` only |
| **EMAIL** – first administrator's e-mail | `it@company.com` | receives the welcome e-mail |
| **COMPANY** – company name | `OPI` | plain words, no quotes |
| Industry | paper / general | paper ⇒ `--departments paper`, otherwise leave it out |
| Language | Arabic / English | English ⇒ `--lang en` |
| Length | 30 days | `--trial 30` |

## 1. Create the trial system (about 2 minutes)
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh new NAME EMAIL COMPANY --trial 30
```
Example, paper mill, English e-mail:
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh new opi it@company.com OPI --trial 30 --departments paper --lang en
```
At the end you see the address, the e-mail, the **first password** and the trial end date. **Nothing has been sent
to the customer yet.**

## 2. Check the system yourself
Open `https://NAME.plantpulse-cmms.com` and sign in with the details shown (first visit can take ~20 s).
Expect: an empty system, the right company name and departments.

## 3. Preview the welcome e-mail, then send it
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome NAME --preview
```
```
ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh welcome NAME
```
Sent from `noreply@plantpulse-cmms.com` with the address, password and first steps. Not arrived? Their Junk /
Quarantine, or send the details yourself.

## 4. During the trial
You get reminders at `plantpulse.cmms@gmail.com` 7 days and 1 day before the end and on the day, with the commands.
**Nothing stops automatically.** Decide with:

| Decision | Command |
|---|---|
| Paid → permanent | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh activate NAME` |
| Needs more time | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh extend NAME 14` |
| Did not continue ("paused" page, data kept) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh stop NAME` |
| Reminder to the customer: preview, then send | `… customer.sh remind NAME --preview`, then `… customer.sh remind NAME` |
| State of all customers | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh list` |
| Details (address, first password, welcome sent?) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh show NAME` |
| Internal test only – delete (after a final backup) | `ssh ubuntu@84.8.106.22 sudo bash /opt/cmms/scripts/customer.sh remove NAME --yes` |

## Customer record (copy one per trial and keep it – no passwords)
```
Company:
Address name (NAME):        https://______.plantpulse-cmms.com
Customer contact:           name ______  e-mail ______  phone ______
Industry / departments:     general / paper
Trial start: ____-__-__     Trial end: ____-__-__
Welcome e-mail sent:        yes / no   date ______
Signed in, password changed: yes / no
Assets imported from Excel: yes / no
Training:                   planner ☐  supervisors ☐  technicians ☐
Follow-up (call / visit):   ______
Final decision:             activate / extend ___ days / stop / remove
Notes:
```
