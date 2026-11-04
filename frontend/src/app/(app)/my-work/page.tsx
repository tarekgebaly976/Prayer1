"use client";

import { Card, Group, SegmentedControl, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconAlertOctagon, IconCalendar, IconCircleCheck, IconMapPin, IconShieldLock } from "@tabler/icons-react";
import Link from "next/link";
import { useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Loading, PageHeader, StatusBadge } from "@/components/ui";
import { fmtDate, useAssetCodes, useQ } from "@/lib/hooks";
import type { Page, WorkOrder } from "@/lib/types";

const PRIO: Record<string, string> = { P1: "red", P2: "orange", P3: "blue", P4: "gray" };

export default function MyWork() {
  const { t } = useTranslation();
  const [scope, setScope] = useState("open");
  const q = useQ<Page<WorkOrder>>("/work-orders", { assigned_to_me: true, open_only: scope === "open", limit: 100, sort: "due_date" });
  const amap = useAssetCodes((q.data?.items ?? []).map((w) => w.asset_id));
  const today = new Date().toISOString().slice(0, 10);
  return (
    <>
      <PageHeader title={t("nav.myWork")}>
        <SegmentedControl value={scope} onChange={setScope} data={[{ value: "open", label: t("wo.openOnly") }, { value: "all", label: t("common.all") }]} />
      </PageHeader>
      {!q.data ? <Loading /> : (
        <Stack gap="sm">
          {q.data.items.length === 0 && (
            <Stack align="center" gap={6} py="xl" c="dimmed">
              <ThemeIcon variant="light" color="teal" size={52} radius="xl"><IconCircleCheck size={30} /></ThemeIcon>
              <Text>{t("dash.allClear")}</Text>
            </Stack>
          )}
          {q.data.items.map((w) => {
            const late = !!w.due_date && w.due_date < today && !["completed", "closed", "cancelled"].includes(w.status);
            return (
              <Card key={w.id} withBorder component={Link} href={`/work-orders/${w.id}`} padding="md" className="tap-target pp-stat" data-alert
                data-testid="my-wo-card" style={{ "--pp-stat-color": `var(--mantine-color-${PRIO[w.priority] ?? "gray"}-6)` } as CSSProperties}>
                <Group justify="space-between" wrap="nowrap" mb={4}>
                  <Text fw={600} size="sm" c="dimmed" className="mono">{w.number}</Text>
                  <Group gap={4} wrap="nowrap"><StatusBadge value={w.priority} variant="filled" /><StatusBadge value={w.status} /></Group>
                </Group>
                <Group gap={6} wrap="nowrap" align="flex-start">
                  {w.type === "emergency" && <IconAlertOctagon size={18} color="var(--mantine-color-red-6)" style={{ flexShrink: 0, marginTop: 2 }} />}
                  <Text fw={700}>{w.title}</Text>
                </Group>
                <Group gap="md" mt={6}>
                  <Group gap={4}><IconMapPin size={15} color="var(--mantine-color-dimmed)" /><Text size="sm" c="dimmed">{amap.get(w.asset_id) ?? "…"}</Text></Group>
                  <Group gap={4}><IconCalendar size={15} color={late ? "var(--mantine-color-red-6)" : "var(--mantine-color-dimmed)"} />
                    <Text size="sm" c={late ? "red.7" : "dimmed"} fw={late ? 700 : 400}>{fmtDate(w.due_date)}</Text></Group>
                  <Text size="sm" c="dimmed">{t(`woType.${w.type}`)}</Text>
                  {(w.requires_loto || w.requires_permit) && <Group gap={4}><IconShieldLock size={15} color="var(--mantine-color-red-6)" /><Text size="sm" c="red" fw={600}>{t("wo.safety")}</Text></Group>}
                </Group>
              </Card>
            );
          })}
        </Stack>
      )}
    </>
  );
}
