"use client";

import { Anchor, Container, Divider, List, Stack, Text, Title } from "@mantine/core";

/** Public privacy policy (linked from the Google Play listing). Describes what the system actually stores. */
export default function PrivacyPage() {
  return (
    <Container size="sm" py="xl">
      <Stack gap="sm">
        <Title order={2}>Privacy policy – Paper Mill CMMS</Title>
        <Text size="sm" c="dimmed">Last updated: 31 October 2026</Text>
        <Text>Paper Mill CMMS is a maintenance management system used by the maintenance teams of a paper mill. It is for the plant’s own staff: accounts are created by the plant’s administrator; there is no public sign-up.</Text>
        <Title order={4}>What the app stores</Title>
        <List spacing={4}>
          <List.Item>Your account: name, work e-mail, role, department, trade, and optionally employee number and hourly rate (for labour cost).</List.Item>
          <List.Item>The work you record: work orders, requests, checklists, readings, hours, spare parts, comments, shift roster and handovers.</List.Item>
          <List.Item>Photos and files you choose to attach to a job or asset.</List.Item>
          <List.Item>Security records: sign-in times, the device’s IP address and an audit log of changes, kept to protect the system and for safety and quality audits.</List.Item>
        </List>
        <Title order={4}>Camera and device</Title>
        <Text>The camera is used only when you press Scan QR or add a photo, and only inside the app. The app does not read contacts, messages, location or other files on the phone, and shows no advertising.</Text>
        <Title order={4}>Who can see it, and where it is kept</Title>
        <Text>Data is visible only to signed-in staff of the plant, according to their role and department. It is kept on the plant’s own server and its backups in cloud storage, sent over encrypted HTTPS. It is not sold or shared with third parties for marketing or analytics.</Text>
        <Title order={4}>How long, and your choices</Title>
        <Text>Maintenance records are kept as long as the plant needs them for maintenance history and audits. When someone leaves, the administrator disables or removes the account; their name stays on the past records they signed. To see, correct or delete your account data, ask the plant’s CMMS administrator.</Text>
        <Title order={4}>Contact</Title>
        <Text>The CMMS administrator of your plant, or the developer at the e-mail address shown on the app’s Google Play page.</Text>
        <Divider my="md" />
        <div dir="rtl" lang="ar">
          <Stack gap="sm">
            <Title order={3}>سياسة الخصوصية – نظام صيانة مصنع الورق</Title>
            <Text>هذا النظام لإدارة الصيانة يستخدمه موظفو المصنع فقط، والحسابات ينشئها مسؤول النظام؛ لا يوجد تسجيل عام.</Text>
            <Text><b>ما يُحفظ:</b> بيانات الحساب (الاسم، البريد الوظيفي، الدور، القسم، التخصص)، والأعمال المسجلة (أوامر العمل، الطلبات، القراءات، الساعات، قطع الغيار، الورديات)، والصور والملفات التي ترفقها، وسجلات الأمان (أوقات الدخول وعنوان IP وسجل التعديلات).</Text>
            <Text><b>الكاميرا:</b> تُستخدم فقط عند مسح رمز QR أو إضافة صورة داخل التطبيق. لا يقرأ التطبيق جهات الاتصال أو الرسائل أو الموقع، ولا يعرض إعلانات.</Text>
            <Text><b>الاطلاع والتخزين:</b> البيانات متاحة فقط لموظفي المصنع المسجلين حسب الدور والقسم، ومحفوظة على خادم المصنع ونسخه الاحتياطية، وتُنقل عبر اتصال مشفر. لا تُباع ولا تُشارك مع أي طرف ثالث.</Text>
            <Text><b>طلباتك:</b> للاطلاع على بياناتك أو تصحيحها أو حذف حسابك، تواصل مع مسؤول النظام في المصنع.</Text>
          </Stack>
        </div>
        <Anchor href="/login" size="sm" mt="md">Sign in</Anchor>
      </Stack>
    </Container>
  );
}
