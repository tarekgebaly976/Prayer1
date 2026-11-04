"use client";

import { Alert, Anchor, Button, PasswordInput, Stack, Text } from "@mantine/core";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AuthCard } from "@/components/AuthCard";
import { ApiError, post } from "@/lib/api";
import { applyDirection, toLang } from "@/lib/i18n";

function ResetForm() {
  const { t, i18n } = useTranslation();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  // The e-mailed link carries the account's language; nobody is signed in yet to tell us.
  const lang = params.get("lang");
  useEffect(() => {
    if (!lang) return;
    const l = toLang(lang);
    void i18n.changeLanguage(l);
    applyDirection(l);
  }, [lang, i18n]);
  const [pw, setPw] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<"form" | "done" | "bad">(token.length >= 20 ? "form" : "bad");
  const [error, setError] = useState<string | null>(null);
  const mismatch = repeat.length > 0 && repeat !== pw;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/auth/reset-password", { token, new_password: pw });
      setState("done");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) setState("bad");
      else setError((err as Error).message); // e.g. the password rule: the link stays usable
    } finally {
      setBusy(false);
    }
  }

  if (state === "done") {
    return (
      <Stack>
        <Alert color="teal" data-testid="reset-done">{t("auth.done")}</Alert>
        <Button component={Link} href="/login" fullWidth className="tap-target">{t("auth.submit")}</Button>
      </Stack>
    );
  }
  if (state === "bad") {
    return (
      <Stack>
        <Alert color="red" data-testid="reset-bad-link">{token ? t("auth.badLink") : t("auth.noToken")}</Alert>
        <Button component={Link} href="/forgot-password" variant="light" fullWidth className="tap-target">{t("auth.requestNew")}</Button>
      </Stack>
    );
  }
  return (
    <form onSubmit={submit}>
      <Stack>
        {error && <Alert color="red">{error}</Alert>}
        <PasswordInput label={t("auth.newPassword")} description={t("auth.passwordRule")} autoComplete="new-password" required value={pw}
          onChange={(e) => setPw(e.currentTarget.value)} />
        <PasswordInput label={t("auth.repeatPassword")} autoComplete="new-password" required value={repeat} error={mismatch ? t("auth.passwordMismatch") : undefined}
          onChange={(e) => setRepeat(e.currentTarget.value)} />
        <Button type="submit" loading={busy} disabled={pw.length < 12 || pw !== repeat} fullWidth className="tap-target">{t("auth.saveNew")}</Button>
      </Stack>
    </form>
  );
}

/** Opened from the "forgot password" e-mail: /reset-password?token=… */
export default function ResetPasswordPage() {
  const { t } = useTranslation();
  return (
    <AuthCard subtitle={t("auth.newTitle")}>
      <Suspense><ResetForm /></Suspense>
      <Text ta="center" mt="md" size="sm"><Anchor component={Link} href="/login">{t("auth.backToLogin")}</Anchor></Text>
    </AuthCard>
  );
}
