"use client";

import { Button, Card, Group, SimpleGrid, Text, ThemeIcon } from "@mantine/core";
import {
  IconAlertOctagon, IconAlertTriangle, IconCalendarTime, IconChartBar, IconChecklist, IconClipboardList, IconClockExclamation, IconDroplet,
  IconEye, IconHeartRateMonitor, IconPlus, IconQrcode, IconUserCheck,
} from "@tabler/icons-react";
import Link from "next/link";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Loading, PageHeader } from "@/components/ui";
import { useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";

interface Summary {
  today: string; my_open_work?: number; open_work_orders?: number; open_emergencies?: number; overdue_work_orders?: number;
  awaiting_approval?: number; awaiting_review?: number; new_requests?: number; pm_pending_approvals?: number; lube_overdue?: number;
  open_alerts?: { critical: number; warning: number }; timezone?: string;
}

function Stat({ label, value, href, color, icon: Icon, alert }: {
  label: string; value: number | undefined; href: string; color: string; icon: typeof IconUserCheck; alert?: boolean;
}) {
  if (value === undefined) return null;
  const on = value > 0;
  return (
    <Card withBorder component={Link} href={href} padding="md" data-testid={`stat-${href}`} className="pp-stat"
      data-alert={alert && on ? true : undefined} style={{ "--pp-stat-color": `var(--mantine-color-${color}-6)` } as CSSProperties}>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Text size="sm" c="dimmed" fw={500} lh={1.3}>{label}</Text>
        <ThemeIcon variant="light" color={on ? color : "gray"} size={34} radius="md"><Icon size={19} stroke={1.8} /></ThemeIcon>
      </Group>
      <Text fz={32} fw={800} lh={1.1} mt={6} c={on && alert ? `${color}.7` : on ? "brand.7" : "gray.5"}>{value}</Text>
    </Card>
  );
}

export default function Dashboard() {
  const { t } = useTranslation();
  const { plant, can, me } = useSession();
  const q = useQ<Summary>("/dashboard/summary", undefined, { refetchInterval: 60_000 });
  if (!q.data) return <Loading />;
  const s = q.data;
  return (
    <>
      <PageHeader title={t("nav.dashboard")}>
        <Text size="sm" c="dimmed">{plant?.plant_name} · {me?.full_name} · {s.today} ({s.timezone})</Text>
      </PageHeader>
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }} mb="xl" spacing="md">
        <Stat label={t("dash.myOpen")} value={s.my_open_work} href="/my-work" color="brand" icon={IconUserCheck} />
        <Stat label={t("dash.emergencies")} value={s.open_emergencies} href="/work-orders?type=emergency&open=1" color="red" icon={IconAlertOctagon} alert />
        <Stat label={t("dash.overdue")} value={s.overdue_work_orders} href="/work-orders?overdue=1" color="orange" icon={IconClockExclamation} alert />
        <Stat label={t("dash.open")} value={s.open_work_orders} href="/work-orders?open=1" color="brand" icon={IconClipboardList} />
        <Stat label={t("dash.newRequests")} value={s.new_requests} href="/requests" color="yellow" icon={IconAlertTriangle} alert />
        <Stat label={t("dash.awaitingApproval")} value={s.awaiting_approval} href="/work-orders?status=awaiting_approval" color="yellow" icon={IconChecklist} alert />
        <Stat label={t("dash.awaitingReview")} value={s.awaiting_review} href="/work-orders?status=awaiting_review" color="violet" icon={IconEye} alert />
        <Stat label={t("dash.pmApprovals")} value={s.pm_pending_approvals} href="/pm?tab=approvals" color="yellow" icon={IconCalendarTime} alert />
        <Stat label={t("dash.lubeOverdue")} value={s.lube_overdue} href="/lubrication" color="orange" icon={IconDroplet} alert />
        <Stat label={t("dash.critical")} value={s.open_alerts?.critical} href="/pdm?tab=alerts" color="red" icon={IconHeartRateMonitor} alert />
      </SimpleGrid>
      <Card withBorder padding="md">
        <Text fw={700} mb="sm">{t("dash.quick")}</Text>
        <Group gap="sm">
          {can("request.create") && <Button component={Link} href="/requests?new=1" color="red" leftSection={<IconAlertTriangle size={18} />} className="tap-target">{t("req.new")}</Button>}
          {can("wo.create") && <Button component={Link} href="/work-orders/new" leftSection={<IconPlus size={18} />} className="tap-target">{t("wo.new")}</Button>}
          <Button component={Link} href="/scan" variant="light" leftSection={<IconQrcode size={18} />} className="tap-target">{t("nav.scan")}</Button>
          {can("kpi.view") && <Button component={Link} href="/kpis" variant="light" leftSection={<IconChartBar size={18} />} className="tap-target">{t("nav.kpis")}</Button>}
        </Group>
      </Card>
    </>
  );
}
