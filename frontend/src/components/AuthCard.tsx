"use client";

import { Center, Group, Paper, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

/** The navy sign-in background with the white card and logo: sign-in, "forgot password" and "new password". */
export function AuthCard({ children, subtitle }: { children: ReactNode; subtitle?: string }) {
  const { t } = useTranslation();
  return (
    <Center p="md" className="pp-login">
      <Paper shadow="xl" p="xl" radius="lg" w="100%" maw={420}>
        <Group gap="sm" wrap="nowrap" mb="md">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icons/icon.svg" alt="" width={48} height={48} />
          <div>
            <Title order={2} c="var(--pp-strong)" lh={1.1}>{t("app.name")}</Title>
            <Text c="dimmed" size="sm">{subtitle ?? t("app.tagline")}</Text>
          </div>
        </Group>
        {children}
      </Paper>
    </Center>
  );
}
