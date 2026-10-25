"use client";

import { Button, Card, Group, SimpleGrid, Text } from "@mantine/core";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { Loading, PageHeader } from "@/components/ui";
import { useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";

interface Summary {
  today: string; my_open_work?: number; open_work_orders?: number; open_emergencies?: number; overdue_work_orders?: number;
  awaiting_approval?: number; awaiting_review?: number; new_requests?: number; pm_pending_approvals?: number; lube_overdue?: number;
  open_alerts?: { critical: number; warning: number }; timezone?: string;
}

function Stat({ label, value, href, color }: { label: string; value: number | undefined; href: string; color?: string }) {
  if (value === undefined) return null;
  return (
    <Card withBorder component={Link} href={href} padding="md" data-testid={`stat-${href}`}>
      <Text size="sm" c="dimmed">{label}</Text>
      <Text fz={30} fw={700} c={value > 0 ? color : undefined}>{value}</Text>
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
      <PageHeader title={`${t("nav.dashboard")} — ${plant?.plant_name ?? ""}`}>
        <Text size="sm" c="dimmed">{me?.full_name} · {s.today} ({s.timezone})</Text>
      </PageHeader>
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }} mb="lg">
        <Stat label={t("dash.myOpen")} value={s.my_open_work} href="/my-work" />
        <Stat label={t("dash.emergencies")} value={s.open_emergencies} href="/work-orders?type=emergency&open=1" color="red" />
        <Stat label={t("dash.overdue")} value={s.overdue_work_orders} href="/work-orders?overdue=1" color="orange" />
        <Stat label={t("dash.open")} value={s.open_work_orders} href="/work-orders?open=1" />
        <Stat label={t("dash.newRequests")} value={s.new_requests} href="/requests" color="yellow" />
        <Stat label={t("dash.awaitingApproval")} value={s.awaiting_approval} href="/work-orders?status=awaiting_approval" color="yellow" />
        <Stat label={t("dash.awaitingReview")} value={s.awaiting_review} href="/work-orders?status=awaiting_review" color="violet" />
        <Stat label={t("dash.pmApprovals")} value={s.pm_pending_approvals} href="/pm?tab=approvals" color="yellow" />
        <Stat label={t("dash.lubeOverdue")} value={s.lube_overdue} href="/lubrication" color="orange" />
        <Stat label={t("dash.critical")} value={s.open_alerts?.critical} href="/pdm?tab=alerts" color="red" />
      </SimpleGrid>
      <Text fw={600} mb="xs">{t("dash.quick")}</Text>
      <Group>
        {can("request.create") && <Button component={Link} href="/requests?new=1" color="red" className="tap-target">{t("req.new")}</Button>}
        {can("wo.create") && <Button component={Link} href="/work-orders/new" className="tap-target">{t("wo.new")}</Button>}
        <Button component={Link} href="/scan" variant="light" className="tap-target">{t("nav.scan")}</Button>
        {can("kpi.view") && <Button component={Link} href="/kpis" variant="light" className="tap-target">{t("nav.kpis")}</Button>}
      </Group>
    </>
  );
}
