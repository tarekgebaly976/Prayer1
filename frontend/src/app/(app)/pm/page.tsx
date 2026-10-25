"use client";

import { ActionIcon, Alert, Button, Checkbox, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Table, Tabs, TextInput, Textarea } from "@mantine/core";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { AssetPicker, DataTable, PageHeader, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, Page } from "@/lib/types";

interface Plan { id: string; code: string; name: string; asset_id: string; job_plan_id: string; trigger: string; frequency_unit: string | null; frequency_interval: number | null;
  schedule_basis: string; meter_interval: number | null; next_due_date: string | null; last_completed_date: string | null; is_active: boolean; lead_days: number; horizon_days: number }
interface JobPlan { id: string; code: string; name: string; estimated_hours: number; trade: string | null; requires_loto: boolean; requires_permit: boolean; requires_testing: boolean }
interface Occ { id: string; pm_plan_id: string; due_date: string; original_due_date: string; status: string; work_order_id: string | null; request_reason: string | null; requested_new_date: string | null }

function NewJobPlan({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ code: "", name: "", description: "", trade: "mechanical", estimated_hours: 1 as number | string, safety_precautions: "", tools: "",
    requires_loto: false, requires_permit: false, requires_testing: false });
  const [tasks, setTasks] = useState<{ description: string; kind: string; unit: string; max_value: string }[]>([{ description: "", kind: "check", unit: "", max_value: "" }]);
  const m = useMut(() => post("/pm/job-plans", { ...f, estimated_hours: Number(f.estimated_hours), description: f.description || null, tools: f.tools || null,
    safety_precautions: f.safety_precautions || null,
    tasks: tasks.filter((x) => x.description).map((x, i) => ({ seq: (i + 1) * 10, description: x.description, kind: x.kind, unit: x.unit || null, max_value: x.max_value ? Number(x.max_value) : null })) }),
    { onDone: onClose });
  return (
    <Modal opened={opened} onClose={onClose} title={t("pm.newJobPlan")} size="xl">
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput label={t("common.code")} value={f.code} onChange={(e) => setF({ ...f, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
          <Select label={t("pm.trade")} value={f.trade} onChange={(v) => setF({ ...f, trade: v ?? "mechanical" })} data={["mechanical", "electrical", "instrumentation", "general"]} />
          <NumberInput label={t("wo.estHours")} min={0.25} value={f.estimated_hours} onChange={(v) => setF({ ...f, estimated_hours: v })} />
        </SimpleGrid>
        <Textarea label={t("pm.safetyNotes")} value={f.safety_precautions} onChange={(e) => setF({ ...f, safety_precautions: e.currentTarget.value })} />
        <TextInput label={t("pm.tools")} value={f.tools} onChange={(e) => setF({ ...f, tools: e.currentTarget.value })} />
        <Group>
          <Checkbox label={t("wo.loto")} checked={f.requires_loto} onChange={(e) => setF({ ...f, requires_loto: e.currentTarget.checked })} />
          <Checkbox label={t("wo.permit")} checked={f.requires_permit} onChange={(e) => setF({ ...f, requires_permit: e.currentTarget.checked })} />
          <Checkbox label={t("wo.testing")} checked={f.requires_testing} onChange={(e) => setF({ ...f, requires_testing: e.currentTarget.checked })} />
        </Group>
        <Table><Table.Tbody>{tasks.map((x, i) => (
          <Table.Tr key={i}>
            <Table.Td><TextInput size="xs" placeholder={t("pm.tasks")} value={x.description} onChange={(e) => setTasks(tasks.map((y, j) => (j === i ? { ...y, description: e.currentTarget.value } : y)))} /></Table.Td>
            <Table.Td><Select size="xs" w={110} data={["check", "reading"]} value={x.kind} onChange={(v) => setTasks(tasks.map((y, j) => (j === i ? { ...y, kind: v ?? "check" } : y)))} /></Table.Td>
            <Table.Td><TextInput size="xs" w={70} placeholder="°C" value={x.unit} onChange={(e) => setTasks(tasks.map((y, j) => (j === i ? { ...y, unit: e.currentTarget.value } : y)))} /></Table.Td>
            <Table.Td><TextInput size="xs" w={80} placeholder="max" value={x.max_value} onChange={(e) => setTasks(tasks.map((y, j) => (j === i ? { ...y, max_value: e.currentTarget.value } : y)))} /></Table.Td>
            <Table.Td><ActionIcon variant="subtle" color="red" onClick={() => setTasks(tasks.filter((_, j) => j !== i))}>×</ActionIcon></Table.Td>
          </Table.Tr>))}</Table.Tbody></Table>
        <Group><Button variant="subtle" size="xs" onClick={() => setTasks([...tasks, { description: "", kind: "check", unit: "", max_value: "" }])}>+ {t("pm.tasks")}</Button></Group>
        <Button onClick={() => m.mutate(undefined)} loading={m.isPending} disabled={!f.code || !f.name}>{t("common.create")}</Button>
      </Stack>
    </Modal>
  );
}

function NewPlan({ opened, onClose, jobPlans }: { opened: boolean; onClose: () => void; jobPlans: JobPlan[] }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ code: "", name: "", asset_id: null as string | null, job_plan_id: null as string | null, trigger: "calendar", frequency_unit: "week",
    frequency_interval: 1 as number | string, schedule_basis: "fixed", start_date: new Date().toISOString().slice(0, 10), meter_id: null as string | null,
    meter_interval: 1000 as number | string, last_meter_value: 0 as number | string, horizon_days: 30 as number | string, lead_days: 7 as number | string,
    tolerance_days: 0 as number | string, priority: "P3", wo_type: "preventive" });
  const meters = useQ<{ id: string; name: string; current_value: number }[]>(f.asset_id && f.trigger === "meter" ? `/assets/${f.asset_id}/meters` : null);
  const m = useMut(() => post("/pm/plans", f.trigger === "calendar" ? {
    code: f.code, name: f.name, asset_id: f.asset_id, job_plan_id: f.job_plan_id, trigger: "calendar", frequency_unit: f.frequency_unit, frequency_interval: Number(f.frequency_interval),
    schedule_basis: f.schedule_basis, start_date: f.start_date, horizon_days: Number(f.horizon_days), lead_days: Number(f.lead_days), tolerance_days: Number(f.tolerance_days),
    priority: f.priority, wo_type: f.wo_type,
  } : { code: f.code, name: f.name, asset_id: f.asset_id, job_plan_id: f.job_plan_id, trigger: "meter", meter_id: f.meter_id, meter_interval: Number(f.meter_interval),
    last_meter_value: Number(f.last_meter_value), priority: f.priority, wo_type: f.wo_type }), { onDone: onClose });
  return (
    <Modal opened={opened} onClose={onClose} title={t("pm.newPlan")} size="lg">
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t("common.code")} value={f.code} onChange={(e) => setF({ ...f, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
          <AssetPicker value={f.asset_id} onChange={(v) => setF({ ...f, asset_id: v })} required />
          <Select label={t("pm.jobPlans")} value={f.job_plan_id} onChange={(v) => setF({ ...f, job_plan_id: v })} data={jobPlans.map((j) => ({ value: j.id, label: `${j.code} — ${j.name}` }))} />
          <Select label={t("pm.trigger")} value={f.trigger} onChange={(v) => setF({ ...f, trigger: v ?? "calendar" })} data={["calendar", "meter"]} allowDeselect={false} />
          <Select label={t("common.type")} value={f.wo_type} onChange={(v) => setF({ ...f, wo_type: v ?? "preventive" })} data={["preventive", "inspection", "predictive"].map((x) => ({ value: x, label: t(`woType.${x}`) }))} />
        </SimpleGrid>
        {f.trigger === "calendar" ? (
          <SimpleGrid cols={{ base: 2, sm: 3 }}>
            <NumberInput label={t("pm.every")} min={1} value={f.frequency_interval} onChange={(v) => setF({ ...f, frequency_interval: v })} />
            <Select label={t("pm.frequency")} value={f.frequency_unit} onChange={(v) => setF({ ...f, frequency_unit: v ?? "week" })} data={["day", "week", "month", "year"]} allowDeselect={false} />
            <Select label={t("pm.basis")} value={f.schedule_basis} onChange={(v) => setF({ ...f, schedule_basis: v ?? "fixed" })} data={[{ value: "fixed", label: t("pm.fixed") }, { value: "floating", label: t("pm.floating") }]} allowDeselect={false} />
            <TextInput type="date" label={t("pm.startDate")} value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.currentTarget.value })} />
            <NumberInput label={t("pm.horizon")} min={1} max={730} value={f.horizon_days} onChange={(v) => setF({ ...f, horizon_days: v })} />
            <NumberInput label={t("pm.lead")} min={0} value={f.lead_days} onChange={(v) => setF({ ...f, lead_days: v })} />
            <NumberInput label={t("pm.tolerance")} min={0} value={f.tolerance_days} onChange={(v) => setF({ ...f, tolerance_days: v })} />
          </SimpleGrid>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <Select label={t("pm.meter")} value={f.meter_id} onChange={(v) => setF({ ...f, meter_id: v })} data={(meters.data ?? []).map((x) => ({ value: x.id, label: `${x.name} (${x.current_value})` }))} />
            <NumberInput label={t("pm.meterInterval")} min={1} value={f.meter_interval} onChange={(v) => setF({ ...f, meter_interval: v })} />
            <NumberInput label="Last service at" min={0} value={f.last_meter_value} onChange={(v) => setF({ ...f, last_meter_value: v })} />
          </SimpleGrid>
        )}
        <Button onClick={() => m.mutate(undefined)} loading={m.isPending} disabled={!f.code || !f.asset_id || !f.job_plan_id}>{t("common.create")}</Button>
      </Stack>
    </Modal>
  );
}

function OccActions({ o }: { o: Occ }) {
  const { t } = useTranslation();
  const { can } = useSession();
  const [mode, setMode] = useState<"defer" | "cancel" | null>(null);
  const [reason, setReason] = useState("");
  const [date, setDate] = useState("");
  const req = useMut(() => post(`/pm/occurrences/${o.id}/request`, { kind: mode, reason, new_date: mode === "defer" ? date : null }), { onDone: () => setMode(null) });
  const decide = useMut((approve: boolean) => post(`/pm/occurrences/${o.id}/decide`, { approve }));
  const pending = o.status === "deferral_requested" || o.status === "cancellation_requested";
  return (
    <Group gap={4} wrap="nowrap">
      {pending && can("pm.approve_deferral") && <><Button size="xs" onClick={() => decide.mutate(true)}>{t("common.approve")}</Button><Button size="xs" color="red" variant="light" onClick={() => decide.mutate(false)}>{t("common.reject")}</Button></>}
      {["scheduled", "generated", "deferred"].includes(o.status) && (can("wo.plan") || can("wo.execute")) && <>
        <Button size="xs" variant="subtle" onClick={() => setMode("defer")}>{t("pm.requestDefer")}</Button>
        <Button size="xs" variant="subtle" color="red" onClick={() => setMode("cancel")}>{t("pm.requestCancel")}</Button></>}
      <Modal opened={!!mode} onClose={() => setMode(null)} title={mode === "defer" ? t("pm.requestDefer") : t("pm.requestCancel")}>
        <Stack>
          <Textarea label={t("common.reason")} value={reason} onChange={(e) => setReason(e.currentTarget.value)} required />
          {mode === "defer" && <TextInput type="date" label={t("pm.newDate")} value={date} onChange={(e) => setDate(e.currentTarget.value)} />}
          <Button disabled={reason.length < 5 || (mode === "defer" && !date)} onClick={() => req.mutate(undefined)}>{t("common.submit")}</Button>
        </Stack>
      </Modal>
    </Group>
  );
}

function PM() {
  const { t } = useTranslation();
  const sp = useSearchParams();
  const { can } = useSession();
  const [jp, setJp] = useState(false);
  const [np, setNp] = useState(false);
  const [runRes, setRunRes] = useState<string | null>(null);
  const plans = useQ<Page<Plan>>("/pm/plans", { limit: 500 });
  const jobs = useQ<JobPlan[]>("/pm/job-plans");
  const occ = useQ<Page<Occ>>("/pm/occurrences", { limit: 500, status: ["scheduled", "generated", "deferred", "deferral_requested", "cancellation_requested"] });
  const approvals = useQ<Page<Occ>>("/pm/occurrences", { limit: 200, status: ["deferral_requested", "cancellation_requested"] });
  const assets = useQ<Page<Asset>>("/assets", { limit: 500 });
  const amap = new Map((assets.data?.items ?? []).map((a) => [a.id, a.code]));
  const pmap = new Map((plans.data?.items ?? []).map((p) => [p.id, p.code]));
  const run = useMut(() => post<{ work_orders_created: number; occurrences_created: number }>("/pm/scheduler/run", {}), { success: false,
    onDone: (r) => setRunRes(`${r.occurrences_created} occurrences, ${r.work_orders_created} work orders created`) });
  const occCols = [
    { key: "p", label: t("pm.plans"), render: (o: Occ) => pmap.get(o.pm_plan_id) },
    { key: "d", label: t("common.dueDate"), render: (o: Occ) => <>{o.due_date}{o.due_date !== o.original_due_date && ` (${o.original_due_date})`}</> },
    { key: "s", label: t("common.status"), render: (o: Occ) => <StatusBadge value={o.status} /> },
    { key: "r", label: t("common.reason"), render: (o: Occ) => o.request_reason ? `${o.request_reason}${o.requested_new_date ? ` → ${o.requested_new_date}` : ""}` : "" },
    { key: "w", label: "WO", render: (o: Occ) => (o.work_order_id ? <Link href={`/work-orders/${o.work_order_id}`}>→</Link> : "") },
    { key: "a", label: t("common.actions"), render: (o: Occ) => <OccActions o={o} /> },
  ];
  return (
    <>
      <PageHeader title={t("nav.pm")} actions={<>
        {can("pm.manage") && <Button onClick={() => setNp(true)}>{t("pm.newPlan")}</Button>}
        {can("pm.manage") && <Button variant="light" onClick={() => setJp(true)}>{t("pm.newJobPlan")}</Button>}
        {can("pm.run_scheduler") && <Button variant="default" loading={run.isPending} onClick={() => run.mutate(undefined)}>{t("pm.runScheduler")}</Button>}
      </>} />
      {runRes && <Alert color="teal" mb="md" withCloseButton onClose={() => setRunRes(null)}>{runRes}</Alert>}
      <Tabs defaultValue={sp.get("tab") ?? "plans"}>
        <Tabs.List>
          <Tabs.Tab value="plans">{t("pm.plans")}</Tabs.Tab><Tabs.Tab value="schedule">{t("pm.occurrences")}</Tabs.Tab>
          <Tabs.Tab value="approvals">{t("pm.approvals")} ({approvals.data?.total ?? 0})</Tabs.Tab><Tabs.Tab value="jobs">{t("pm.jobPlans")}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="plans" pt="md">
          <DataTable rows={plans.data?.items} columns={[
            { key: "c", label: t("common.code"), render: (p) => p.code }, { key: "n", label: t("common.name"), render: (p) => p.name },
            { key: "a", label: t("common.asset"), render: (p) => amap.get(p.asset_id) },
            { key: "f", label: t("pm.frequency"), render: (p) => (p.trigger === "calendar" ? `${p.frequency_interval} ${p.frequency_unit} · ${p.schedule_basis}` : `${p.meter_interval} (meter)`) },
            { key: "l", label: t("pm.lastDone"), render: (p) => fmtDate(p.last_completed_date) },
            { key: "d", label: t("pm.nextDue"), render: (p) => fmtDate(p.next_due_date) },
            { key: "s", label: t("common.active"), render: (p) => (p.is_active ? "✓" : "—") }]} />
        </Tabs.Panel>
        <Tabs.Panel value="schedule" pt="md"><DataTable rows={occ.data?.items} columns={occCols} /></Tabs.Panel>
        <Tabs.Panel value="approvals" pt="md"><DataTable rows={approvals.data?.items} columns={occCols} /></Tabs.Panel>
        <Tabs.Panel value="jobs" pt="md">
          <DataTable rows={jobs.data} columns={[
            { key: "c", label: t("common.code"), render: (j) => j.code }, { key: "n", label: t("common.name"), render: (j) => j.name },
            { key: "t", label: t("pm.trade"), render: (j) => j.trade }, { key: "h", label: t("wo.estHours"), render: (j) => j.estimated_hours },
            { key: "s", label: t("wo.safety"), render: (j) => [j.requires_loto && "LOTO", j.requires_permit && "Permit", j.requires_testing && "Test"].filter(Boolean).join(", ") }]} />
        </Tabs.Panel>
      </Tabs>
      <NewJobPlan opened={jp} onClose={() => setJp(false)} />
      <NewPlan opened={np} onClose={() => setNp(false)} jobPlans={jobs.data ?? []} />
    </>
  );
}

export default function PMPage() {
  return <Guard perm="pm.view"><Suspense><PM /></Suspense></Guard>;
}
