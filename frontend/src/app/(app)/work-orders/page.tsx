"use client";

import { Alert, Button, Checkbox, Group, Modal, MultiSelect, SegmentedControl, Stack, Switch, Text, TextInput, Textarea } from "@mantine/core";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { PlanImport } from "@/components/PlanImport";
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
  const [finish, setFinish] = useState(false);
  const [imp, setImp] = useState(false);
  const [action, setAction] = useState("close");
  const [comment, setComment] = useState("");
  const [result, setResult] = useState<{ done: string[]; skipped: { number: string | null; reason: string }[] } | null>(null);
  const bulkFinish = useMut(() => post<{ done: string[]; skipped: { number: string | null; reason: string }[] }>("/work-orders/bulk-finish",
    { work_order_ids: sel, action, comment }), { success: false, onDone: (r) => { setResult(r); setSel([]); setComment(""); } });
  const canSelect = can("wo.assign") || can("wo.bulk_close");
  const bulkAssign = useMut(() => post("/work-orders/bulk-assign", { work_order_ids: sel, user_ids: [tech], force: false }), { onDone: () => { setBulk(false); setSel([]); } });
  return (
    <>
      <PageHeader title={t("nav.workOrders")} actions={<>
        {can("wo.create") && <Button component={Link} href="/work-orders/new">{t("wo.new")}</Button>}
        {can("wo.create") && <Button variant="light" onClick={() => setImp(true)}>{t("planning.importWo")}</Button>}
        {can("wo.assign") && sel.length > 0 && <Button variant="light" onClick={() => setBulk(true)}>{t("wo.bulkAssign")} ({sel.length})</Button>}
        {can("wo.bulk_close") && sel.length > 0 && <Button variant="light" color="orange" onClick={() => { setResult(null); setFinish(true); }}>{t("planning.bulkFinish")} ({sel.length})</Button>}
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
        ...(canSelect ? [{ key: "sel", label: <Checkbox aria-label="select all" checked={!!data.data?.items.length && data.data.items.every((w) => sel.includes(w.id))}
          onChange={(e) => { const ids = (data.data?.items ?? []).map((w) => w.id); setSel(e.currentTarget.checked ? [...new Set([...sel, ...ids])] : sel.filter((x) => !ids.includes(x))); }} />,
          render: (w: WorkOrder) => (
          <Checkbox aria-label="select" checked={sel.includes(w.id)} onClick={(e) => e.stopPropagation()}
            onChange={(e) => setSel(e.currentTarget.checked ? [...sel, w.id] : sel.filter((x) => x !== w.id))} />) }] : []),
        { key: "n", label: t("wo.number"), render: (w) => <span className="mono">{w.number}</span> },
        { key: "t", label: t("wo.title"), render: (w) => w.title },
        { key: "a", label: t("common.asset"), render: (w) => amap.get(w.asset_id) ?? "…" },
        { key: "ty", label: t("common.type"), render: (w) => t(`woType.${w.type}`) },
        { key: "p", label: t("common.priority"), render: (w) => <StatusBadge value={w.priority} /> },
        { key: "s", label: t("common.status"), render: (w) => <StatusBadge value={w.status} /> },
        { key: "d", label: t("common.dueDate"), render: (w) => fmtDate(w.due_date) },
        { key: "c", label: t("wo.actualCost"), hideOnMobile: true, render: (w) => fmtMoney(w.actual_cost, plant?.currency ?? "SAR") },
      ]} />
      <Pager page={data.data} setPage={(p) => setOffset((p - 1) * 50)} />
      <PlanImport kind="work_orders" title={t("planning.importWoTitle")} opened={imp} onClose={() => setImp(false)} help={t("planning.importWoHelp")} countLabel={t("planning.importWoCount")} />
      <Modal opened={finish} onClose={() => setFinish(false)} title={t("planning.bulkTitle")}>
        {result ? <Stack>
          <Alert color={result.skipped.length ? "orange" : "teal"}>{t("planning.result", { d: result.done.length, s: result.skipped.length })}</Alert>
          {result.skipped.slice(0, 50).map((x, i) => <Text key={i} size="sm">{x.number ?? "—"}: {x.reason}</Text>)}
          <Button onClick={() => setFinish(false)}>{t("common.close")}</Button>
        </Stack> : <Stack>
          <Text size="sm" c="dimmed">{t("planning.bulkHint")}</Text>
          <SegmentedControl value={action} onChange={setAction} data={[{ value: "close", label: t("planning.close") }, { value: "cancel", label: t("planning.cancel") }]} />
          <Textarea label={t("planning.comment")} required value={comment} onChange={(e) => setComment(e.currentTarget.value)} autosize />
          <Button color={action === "cancel" ? "red" : "teal"} disabled={comment.trim().length < 3} loading={bulkFinish.isPending}
            onClick={() => bulkFinish.mutate(undefined)}>{t("planning.apply", { n: sel.length })}</Button>
        </Stack>}
      </Modal>
      <Modal opened={bulk} onClose={() => setBulk(false)} title={t("wo.bulkAssign")}>
        <UserPicker label={t("wo.assignees")} value={tech} onChange={setTech} tradeFilter />
        <Button mt="md" disabled={!tech} loading={bulkAssign.isPending} onClick={() => bulkAssign.mutate(undefined)}>{t("wo.assign")}</Button>
      </Modal>
    </>
  );
}

export default function Page_() {
  return <Guard perm="wo.view"><Suspense><List /></Suspense></Guard>;
}

