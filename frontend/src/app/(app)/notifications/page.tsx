"use client";

import { Badge, Button, Card, Group, Stack, Text } from "@mantine/core";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loading, PageHeader, Pager } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import type { Notification, Page } from "@/lib/types";

export default function Notifications() {
  const { t } = useTranslation();
  const router = useRouter();
  const [offset, setOffset] = useState(0);
  const q = useQ<Page<Notification> & { unread: number }>("/notifications", { limit: 30, offset });
  const readAll = useMut(() => post("/notifications/read-all"), { success: false });
  const read = useMut((id: string) => post(`/notifications/${id}/read`), { success: false });
  if (!q.data) return <Loading />;
  return (
    <>
      <PageHeader title={`${t("nav.notifications")} (${q.data.unread} ${t("notif.unread")})`}
        actions={<Button variant="light" onClick={() => readAll.mutate(undefined)}>{t("notif.markAll")}</Button>} />
      <Stack gap="xs">
        {q.data.items.length === 0 && <Text c="dimmed">{t("common.noData")}</Text>}
        {q.data.items.map((n) => (
          <Card key={n.id} withBorder padding="sm" style={{ cursor: n.link ? "pointer" : undefined, opacity: n.read_at ? 0.65 : 1 }}
            onClick={() => { if (!n.read_at) read.mutate(n.id); if (n.link) router.push(n.link); }}>
            <Group justify="space-between" wrap="nowrap">
              <Group gap="xs" wrap="nowrap">
                <Badge color={n.severity === "critical" ? "red" : n.severity === "warning" ? "orange" : "blue"} variant="light">{n.kind}</Badge>
                <Text fw={n.read_at ? 400 : 700} size="sm">{n.title}</Text>
              </Group>
              <Text size="xs" c="dimmed">{fmtDate(n.created_at, undefined, true)}</Text>
            </Group>
            {n.body && <Text size="sm" c="dimmed" mt={4}>{n.body}</Text>}
          </Card>
        ))}
      </Stack>
      <Pager page={q.data} setPage={(p) => setOffset((p - 1) * 30)} />
    </>
  );
}
