"use client";

import { Alert, Anchor, Button, Stack, Text, TextInput } from "@mantine/core";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AuthCard } from "@/components/AuthCard";
import { Loading } from "@/components/ui";
import { post } from "@/lib/api";

/** "Forgot password": always the same answer, whether or not the address has an account. */
export default function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/v1/meta").then((r) => r.json()).then((m: { password_reset?: boolean }) => setEnabled(!!m.password_reset)).catch(() => setEnabled(false));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard subtitle={t("auth.forgotTitle")}>
      {enabled === null ? <Loading /> : !enabled ? (
        <Stack><Alert color="blue" data-testid="reset-unavailable">{t("auth.askAdmin")}</Alert></Stack>
      ) : sent ? (
        <Alert color="teal" data-testid="reset-sent">{t("auth.sent")}</Alert>
      ) : (
        <form onSubmit={submit}>
          <Stack>
            <Text size="sm">{t("auth.forgotHint")}</Text>
            {error && <Alert color="red">{error}</Alert>}
            <TextInput label={t("auth.email")} type="email" autoComplete="username" required value={email} name="email"
              onChange={(e) => setEmail(e.currentTarget.value)} />
            <Button type="submit" loading={busy} fullWidth className="tap-target">{t("auth.sendLink")}</Button>
          </Stack>
        </form>
      )}
      <Text ta="center" mt="md" size="sm"><Anchor component={Link} href="/login">{t("auth.backToLogin")}</Anchor></Text>
    </AuthCard>
  );
}
