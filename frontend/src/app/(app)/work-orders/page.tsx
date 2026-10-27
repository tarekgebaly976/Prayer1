"use client";

import { Button, Checkbox, Group, Modal, MultiSelect, Switch, TextInput } from "@mantine/core";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { DataTable, PageHeader, Pager, StatusBadge, UserPicker } from "@/components/ui";
import { download, post } from "@/lib/api";
import { fmtDate, fmtMoney, useAssetCodes, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, Page, WorkOrder } from "@/lib/types";

const STATUSES = ["triage", "awaiting_approval", "approved", "planned", "scheduled", "in_progress", "on_hold", "awaiting_review", "completed", "closed", "cancelled"];
const TYPES = ["preventive", "predictive", "corrective", "emergency", "inspection", "improvement", "shutdown", "lubrication"];

function List() {
  const { t } = useTranslation();
  const router = useRouter();
  const sp = useSearchParams();
  const { can, plant } = useSession();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string[]>(sp.get("status") ? [sp.get("status") as string] : []);
  const [type, setType] = useState<string[]>(sp.get("type") ? [sp.get("type") as string] : []);
  const [openOnly, setOpenOnly] = useState(sp.get("open") === "1");
  const [overdue, setOverdue] = useState(sp.get("overdue") === "1");
  const [offset, setOffset] = useState(0);
  const [sel, setSel] = useState<string[]>([]);
  const [bulk, setBulk] = useState(false);
  const [tech, setTech] = useState<string | null>(null);
  const data = useQ<Page<WorkOrder>>("/work-orders", { q, status, type, open_only: openOnly, overdue, limit: 50, offset });
  const amap = useAssetCodes((data.data?.items ?? []).map((w) => w.asset_id));
  const bulkAssign = useMut(() => post("/work-orders/bulk-assign", { work_order_ids: sel, user_ids: [tech], force: false }), { onDone: () => { setBulk(false); setSel([]); } });
  return (
    <>
      <PageHeader title={t("nav.workOrders")} actions={<>
        {can("wo.create") && <Button component={Link} href="/work-orders/new">{t("wo.new")}</Button>}
        {can("wo.assign") && sel.length > 0 && <Button variant="light" onClick={() => setBulk(true)}>{t("wo.bulkAssign")} ({sel.length})</Button>}
        {can("report.export") && <Button variant="default" onClick={() => void download("/exports/work-orders.xlsx")}>{t("common.export")} XLSX</Button>}
      </>}>
        <Group gap="xs" wrap="wrap">
          <TextInput placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.currentTarget.value); setOffset(0); }} w={200} />
          <MultiSelect placeholder={t("common.status")} data={STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))} value={status} onChange={setStatus} w={240} clearable />
          <MultiSelect placeholder={t("common.type")} data={TYPES.map((s) => ({ value: s, label: t(`woType.${s}`) }))} value={type} onChange={setType} w={220} clearable />
          <Switch label={t("wo.openOnly")} checked={openOnly} onChange={(e) => setOpenOnly(e.currentTarget.checked)} />
          <Switch label={t("wo.overdueOnly")} checked={overdue} onChange={(e) => setOverdue(e.currentTarget.checked)} />
        </Group>
      </PageHeader>
      <DataTable rows={data.data?.items} onRow={(w) => router.push(`/work-orders/${w.id}`)} columns={[
        ...(can("wo.assign") ? [{ key: "sel", label: "", render: (w: WorkOrder) => (
          <Checkbox aria-label="select" checked={sel.includes(w.id)} onClick={(e) => e.stopPropagation()}
            onChange={(e) => setSel(e.currentTarget.checked ? [...sel, w.id] : sel.filter((x) => x !== w.id))} />) }] : []),
        { key: "n", label: t("wo.number"), render: (w) => <span className="mono">{w.number}</span> },
        { key: "t", label: t("wo.title"), render: (w) => w.title },
        { key: "a", label: t("common.asset"), render: (w) => amap.get(w.asset_id) ?? "…" },
        { key: "ty", label: t("common.type"), render: (w) => t(`woType.${w.type}`) },
        { key: "p", label: t("common.priority"), render: (w) => <StatusBadge value={w.priority} /> },
        { key: "s", label: t("common.status"), render: (w) => <StatusBadge value={w.status} /> },
        { key: "d", label: t("common.dueDate"), render: (w) => fmtDate(w.due_date) },
        { key: "c", label: t("wo.actualCost"), render: (w) => fmtMoney(w.actual_cost, plant?.currency ?? "SAR") },
      ]} />
      <Pager page={data.data} setPage={(p) => setOffset((p - 1) * 50)} />
      <Modal opened={bulk} onClose={() => setBulk(false)} title={t("wo.bulkAssign")}>
        <UserPicker label={t("wo.assignees")} value={tech} onChange={setTech} />
        <Button mt="md" disabled={!tech} loading={bulkAssign.isPending} onClick={() => bulkAssign.mutate(undefined)}>{t("wo.assign")}</Button>
      </Modal>
    </>
  );
}

export default function Page_() {
  return <Guard perm="wo.view"><Suspense><List /></Suspense></Guard>;
}

