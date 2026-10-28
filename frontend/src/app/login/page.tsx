"use client";

import { Alert, Button, Center, Group, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
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
    <Center mih="100vh" p="md" bg="var(--mantine-color-gray-0)">
      <Paper withBorder shadow="sm" p="xl" radius="md" w="100%" maw={420}>
        <form onSubmit={submit}>
          <Stack>
            <div>
              <Title order={2}>{t("app.name")}</Title>
              <Text c="dimmed" size="sm">{t("app.tagline")}</Text>
            </div>
            {error && <Alert color="red" data-testid="login-error">{error}</Alert>}
            <TextInput label={t("auth.email")} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.currentTarget.value)} name="email" />
            <PasswordInput label={t("auth.password")} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.currentTarget.value)} name="password" />
            <Button type="submit" loading={busy} fullWidth className="tap-target">{t("auth.submit")}</Button>
            <Text size="xs" c="dimmed">{t("auth.sessionNote")}</Text>
            <Group justify="center" gap="xs">
              {LANGS.map((l) => <Button key={l.code} variant="subtle" size="xs" onClick={() => switchLang(l.code)}>{l.label}</Button>)}
            </Group>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
