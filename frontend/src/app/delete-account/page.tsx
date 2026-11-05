"use client";

import { Anchor, Container, Divider, List, Stack, Text, Title } from "@mantine/core";

/** Public account and data deletion page (linked from the Google Play Data safety form). */
export default function DeleteAccountPage() {
  return (
    <Container size="sm" py="xl">
      <Stack gap="sm">
        <Title order={2}>Delete your account and data – PlantPulse</Title>
        <Text>
          PlantPulse (PlantPulse CMMS – Maintenance on Google Play) is used by the maintenance staff of an industrial
          plant. Accounts are created and managed by the plant’s CMMS administrator, so deletion requests go to them.
        </Text>

        <Title order={4}>How to request deletion</Title>
        <List type="ordered" spacing={4}>
          <List.Item>Contact your plant’s CMMS administrator (or your maintenance manager) by e-mail or in person.</List.Item>
          <List.Item>Say that you want your PlantPulse account and personal data deleted, and give the e-mail address you sign in with.</List.Item>
          <List.Item>The administrator deactivates the account at once and deletes your personal data within 30 days, then confirms to you.</List.Item>
          <List.Item>
            If you cannot reach your administrator, e-mail the developer at the address shown on the app’s Google Play
            page with the same details; we will pass the request to your plant and follow it up.
          </List.Item>
        </List>

        <Title order={4}>What is deleted</Title>
        <List spacing={4}>
          <List.Item>Your sign-in account and password.</List.Item>
          <List.Item>Your contact and profile details: e-mail address, employee number, hourly rate, department and trade.</List.Item>
          <List.Item>Your notification settings and shift-roster entries.</List.Item>
        </List>

        <Title order={4}>What is kept, and for how long</Title>
        <List spacing={4}>
          <List.Item>
            Work orders, readings, comments and photos you recorded stay with the plant’s maintenance history, because
            the plant needs them for equipment history, safety and quality audits. Your name stays on the records you
            signed.
          </List.Item>
          <List.Item>Sign-in records (time and IP address) are deleted automatically after 90 days.</List.Item>
          <List.Item>The audit log of changes is kept with the maintenance records it describes, for the same audits.</List.Item>
          <List.Item>Backups that may still contain your data are deleted automatically after 14 days.</List.Item>
        </List>

        <Divider my="md" />
        <div dir="rtl" lang="ar">
          <Stack gap="sm">
            <Title order={3}>حذف حسابك وبياناتك – PlantPulse</Title>
            <Text>حسابات PlantPulse ينشئها ويديرها مسؤول نظام الصيانة في المصنع، لذلك يُقدَّم طلب الحذف إليه.</Text>
            <Title order={4}>خطوات طلب الحذف</Title>
            <List type="ordered" spacing={4}>
              <List.Item>تواصل مع مسؤول النظام في المصنع (أو مدير الصيانة) بالبريد أو شخصيًا.</List.Item>
              <List.Item>اطلب حذف حسابك وبياناتك الشخصية، واذكر البريد الذي تسجّل به الدخول.</List.Item>
              <List.Item>يعطّل المسؤول الحساب فورًا ويحذف بياناتك الشخصية خلال 30 يومًا، ثم يؤكد لك.</List.Item>
              <List.Item>إذا لم تستطع الوصول للمسؤول، راسل المطوّر على البريد الظاهر في صفحة التطبيق على Google Play.</List.Item>
            </List>
            <Text><b>ما يُحذف:</b> حساب الدخول وكلمة المرور، والبريد والرقم الوظيفي وأجر الساعة والقسم والتخصص، وإعدادات الإشعارات والورديات.</Text>
            <Text><b>ما يُحتفظ به:</b> أوامر العمل والقراءات والتعليقات والصور التي سجّلتها تبقى في سجل صيانة المصنع لأغراض تاريخ المعدات والسلامة والتدقيق، ويبقى اسمك على السجلات التي وقّعتها. سجلات الدخول (الوقت وعنوان IP) تُحذف تلقائيًا بعد 90 يومًا، وسجل التعديلات يبقى مع سجلات الصيانة، والنسخ الاحتياطية تُحذف تلقائيًا بعد 14 يومًا.</Text>
          </Stack>
        </div>
        <Anchor href="/privacy" size="sm" mt="md">Privacy policy</Anchor>
      </Stack>
    </Container>
  );
}
