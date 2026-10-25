"use client";

import { Card, Group, SegmentedControl, Stack, Text } from "@mantine/core";
import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loading, PageHeader, StatusBadge } from "@/components/ui";
import { fmtDate, useQ } from "@/lib/hooks";
import type { Page, WorkOrder } from "@/lib/types";

export default function MyWork() {
  const { t } = useTranslation();
  const [scope, setScope] = useState("open");
  const q = useQ<Page<WorkOrder>>("/work-orders", { assigned_to_me: true, open_only: scope === "open", limit: 100, sort: "due_date" });
  return (
    <>
      <PageHeader title={t("nav.myWork")}>
        <SegmentedControl value={scope} onChange={setScope} data={[{ value: "open", label: t("wo.openOnly") }, { value: "all", label: t("common.all") }]} />
      </PageHeader>
      {!q.data ? <Loading /> : (
        <Stack gap="sm">
          {q.data.items.length === 0 && <Text c="dimmed">{t("common.noData")}</Text>}
          {q.data.items.map((w) => (
            <Card key={w.id} withBorder component={Link} href={`/work-orders/${w.id}`} padding="md" className="tap-target" data-testid="my-wo-card">
              <Group justify="space-between" wrap="nowrap" mb={4}>
                <Text fw={700} className="mono">{w.number}</Text>
                <Group gap={4}><StatusBadge value={w.priority} /><StatusBadge value={w.status} /></Group>
              </Group>
              <Text>{w.title}</Text>
              <Group gap="md" mt={4}>
                <Text size="sm" c="dimmed">{t(`woType.${w.type}`)}</Text>
                <Text size="sm" c="dimmed">{t("common.dueDate")}: {fmtDate(w.due_date)}</Text>
                {(w.requires_loto || w.requires_permit) && <Text size="sm" c="red" fw={600}>⚠ {t("wo.safety")}</Text>}
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </>
  );
}
