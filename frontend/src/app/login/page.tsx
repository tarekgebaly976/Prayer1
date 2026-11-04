"use client";

import { Alert, Anchor, Button, Center, Group, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { applyDirection, LANGS, type Lang } from "@/lib/i18n";
import { useSession } from "@/lib/session";

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login, me } = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (me) router.replace("/"); }, [me, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message || t("auth.failed"));
    } finally {
      setBusy(false);
    }
  }
  const switchLang = (l: Lang) => { void i18n.changeLanguage(l); applyDirection(l); };

  return (
    <Center p="md" className="pp-login">
      <Paper shadow="xl" p="xl" radius="lg" w="100%" maw={420}>
        <form onSubmit={submit}>
          <Stack>
            <Group gap="sm" wrap="nowrap" mb={4}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/icons/icon.svg" alt="" width={48} height={48} />
              <div>
                <Title order={2} c="var(--pp-strong)" lh={1.1}>{t("app.name")}</Title>
                <Text c="dimmed" size="sm">{t("app.tagline")}</Text>
              </div>
            </Group>
            {error && <Alert color="red" data-testid="login-error">{error}</Alert>}
            <TextInput label={t("auth.email")} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.currentTarget.value)} name="email" />
            <PasswordInput label={t("auth.password")} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.currentTarget.value)} name="password" />
            <Anchor component={Link} href="/forgot-password" size="sm" mt={-8} ta="end" data-testid="forgot-link">{t("auth.forgot")}</Anchor>
            <Button type="submit" loading={busy} fullWidth className="tap-target">{t("auth.submit")}</Button>
            <Text size="xs" c="dimmed">{t("auth.sessionNote")}</Text>
            <Text size="xs" ta="center"><a href="/privacy" style={{ color: "inherit" }}>Privacy policy / سياسة الخصوصية</a></Text>
            <Group justify="center" gap="xs">
              {LANGS.map((l) => <Button key={l.code} variant="subtle" size="xs" onClick={() => switchLang(l.code)}>{l.label}</Button>)}
            </Group>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
