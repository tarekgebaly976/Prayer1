"use client";

import { Alert, Button, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Tabs, TextInput, Textarea } from "@mantine/core";
import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { AssetPicker, DataTable, DeptSelect, PageHeader, StatusBadge, UserPicker } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, fmtNum, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, Page } from "@/lib/types";

interface Lub { id: string; code: string; manufacturer: string; product: string; kind: string; viscosity_grade: string | null; specification: string | null }
interface Route { id: string; code: string; name: string; department_id: string; lead_days: number }
interface Point { id: string; code: string; asset_id: string; component: string | null; lubricant_id: string; quantity: number; unit: string; method: string | null;
  frequency_days: number | null; hours_interval: number | null; route_id: string | null; last_done_date: string | null; next_due_date: string | null; qr_token: string }
interface Task { id: string; point_code: string; due_date: string; status: string; work_order_id: string | null; done_date: string | null; quantity_actual: number | null }

function Lube() {
  const { t } = useTranslation();
  const { can } = useSession();
  const lubs = useQ<Lub[]>("/lubrication/lubricants");
  const routes = useQ<Route[]>("/lubrication/routes");
  const points = useQ<Point[]>("/lubrication/points");
  const tasks = useQ<Task[]>("/lubrication/tasks");
  const cons = useQ<{ lubricant: string; product: string; unit: string; quantity: number; tasks: number }[]>("/lubrication/consumption");
  const assets = useQ<Page<Asset>>("/assets", { limit: 500 });
  const amap = new Map((assets.data?.items ?? []).map((a) => [a.id, a.code]));
  const lmap = new Map((lubs.data ?? []).map((l) => [l.id, `${l.code} ${l.product}`]));
  const rmap = new Map((routes.data ?? []).map((r) => [r.id, r.code]));
  const gen = useMut((id: string) => post<{ number: string | null; message: string | null }>(`/lubrication/routes/${id}/generate`, {}), { success: false,
    onDone: (r) => setMsg(r.number ? `→ ${r.number}` : (r.message ?? "")) });
  const [msg, setMsg] = useState<string | null>(null);
  const [modal, setModal] = useState<"lub" | "route" | "point" | "alt" | null>(null);
  const [lf, setLf] = useState({ code: "", manufacturer: "", product: "", kind: "grease", viscosity_grade: "", specification: "" });
  const [rf, setRf] = useState({ code: "", name: "", department_id: null as string | null, lead_days: 2 as number | string });
  const [pf, setPf] = useState({ code: "", asset_id: null as string | null, component: "", lubricant_id: null as string | null, quantity: 10 as number | string, unit: "g",
    method: "", frequency_days: 30 as number | string, route_id: null as string | null, responsible_user_id: null as string | null });
  const [af, setAf] = useState({ lub: null as string | null, alt: null as string | null, note: "" });
  const addLub = useMut(() => post("/lubrication/lubricants", { ...lf, viscosity_grade: lf.viscosity_grade || null, specification: lf.specification || null }), { onDone: () => setModal(null) });
  const addRoute = useMut(() => post("/lubrication/routes", { ...rf, lead_days: Number(rf.lead_days) }), { onDone: () => setModal(null) });
  const addPoint = useMut(() => post("/lubrication/points", { ...pf, quantity: Number(pf.quantity), frequency_days: Number(pf.frequency_days), component: pf.component || null, method: pf.method || null }), { onDone: () => setModal(null) });
  const addAlt = useMut(() => post(`/lubrication/lubricants/${af.lub}/alternatives`, { alternative_id: af.alt, compatibility_note: af.note }), { onDone: () => setModal(null) });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <>
      <PageHeader title={t("nav.lubrication")} actions={can("lube.manage") ? <>
        <Button onClick={() => setModal("point")}>{t("common.add")}: {t("lube.points")}</Button>
        <Button variant="light" onClick={() => setModal("route")}>{t("common.add")}: {t("lube.routes")}</Button>
        <Button variant="light" onClick={() => setModal("lub")}>{t("common.add")}: {t("lube.lubricants")}</Button>
        {can("lube.approve_alternative") && <Button variant="default" onClick={() => setModal("alt")}>{t("lube.approveAlt")}</Button>}
      </> : null} />
      <Alert color="yellow" mb="md">{t("lube.mixWarning")}</Alert>
      {msg && <Alert color="teal" mb="md" withCloseButton onClose={() => setMsg(null)}>{msg}</Alert>}
      <Tabs defaultValue="points">
        <Tabs.List>
          <Tabs.Tab value="points">{t("lube.points")}</Tabs.Tab><Tabs.Tab value="routes">{t("lube.routes")}</Tabs.Tab>
          <Tabs.Tab value="tasks">{t("lube.tasks")}</Tabs.Tab><Tabs.Tab value="lubricants">{t("lube.lubricants")}</Tabs.Tab><Tabs.Tab value="consumption">{t("lube.consumption")}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="points" pt="md">
          <DataTable rows={points.data} columns={[
            { key: "c", label: t("common.code"), render: (p) => p.code }, { key: "a", label: t("common.asset"), render: (p) => <Link href={`/assets/${p.asset_id}`}>{amap.get(p.asset_id)}</Link> },
            { key: "m", label: "Component", render: (p) => p.component }, { key: "l", label: t("lube.lubricant"), render: (p) => lmap.get(p.lubricant_id) },
            { key: "q", label: t("common.quantity"), render: (p) => `${fmtNum(p.quantity)} ${p.unit}` },
            { key: "f", label: t("lube.freqDays"), render: (p) => p.frequency_days ?? `${p.hours_interval} h` }, { key: "r", label: t("lube.routes"), render: (p) => (p.route_id ? rmap.get(p.route_id) : "") },
            { key: "d", label: t("pm.nextDue"), render: (p) => <span style={{ color: p.next_due_date && p.next_due_date < today ? "var(--mantine-color-red-7)" : undefined }}>{fmtDate(p.next_due_date)}</span> }]} />
        </Tabs.Panel>
        <Tabs.Panel value="routes" pt="md">
          <DataTable rows={routes.data} columns={[
            { key: "c", label: t("common.code"), render: (r) => r.code }, { key: "n", label: t("common.name"), render: (r) => r.name },
            { key: "p", label: t("lube.points"), render: (r) => (points.data ?? []).filter((p) => p.route_id === r.id).length },
            { key: "g", label: t("common.actions"), render: (r) => can("lube.manage") && <Button size="xs" loading={gen.isPending} onClick={() => gen.mutate(r.id)}>{t("lube.generate")}</Button> }]} />
        </Tabs.Panel>
        <Tabs.Panel value="tasks" pt="md">
          <DataTable rows={tasks.data} columns={[
            { key: "p", label: t("lube.points"), render: (x) => x.point_code }, { key: "d", label: t("common.dueDate"), render: (x) => x.due_date },
            { key: "s", label: t("common.status"), render: (x) => <StatusBadge value={x.status} /> }, { key: "dd", label: t("common.date"), render: (x) => fmtDate(x.done_date) },
            { key: "q", label: t("lube.actualQty"), render: (x) => fmtNum(x.quantity_actual) },
            { key: "w", label: "WO", render: (x) => (x.work_order_id ? <Link href={`/work-orders/${x.work_order_id}`}>→</Link> : "") }]} />
        </Tabs.Panel>
        <Tabs.Panel value="lubricants" pt="md">
          <DataTable rows={lubs.data} columns={[
            { key: "c", label: t("common.code"), render: (l) => l.code }, { key: "p", label: t("lube.lubricant"), render: (l) => `${l.manufacturer} ${l.product}` },
            { key: "k", label: t("common.type"), render: (l) => l.kind }, { key: "v", label: t("lube.viscosity"), render: (l) => l.viscosity_grade ?? l.specification }]} />
        </Tabs.Panel>
        <Tabs.Panel value="consumption" pt="md">
          <DataTable rows={cons.data} rowKey={(r) => r.lubricant + r.unit} columns={[
            { key: "l", label: t("lube.lubricant"), render: (r) => `${r.lubricant} ${r.product}` }, { key: "q", label: t("common.quantity"), render: (r) => `${fmtNum(r.quantity)} ${r.unit}` },
            { key: "t", label: t("lube.tasks"), render: (r) => r.tasks }]} />
        </Tabs.Panel>
      </Tabs>
      <Modal opened={modal === "lub"} onClose={() => setModal(null)} title={t("lube.lubricants")}>
        <Stack>
          <TextInput label={t("common.code")} value={lf.code} onChange={(e) => setLf({ ...lf, code: e.currentTarget.value })} />
          <TextInput label="Manufacturer" value={lf.manufacturer} onChange={(e) => setLf({ ...lf, manufacturer: e.currentTarget.value })} />
          <TextInput label="Product" value={lf.product} onChange={(e) => setLf({ ...lf, product: e.currentTarget.value })} />
          <Select label={t("common.type")} data={["grease", "oil"]} value={lf.kind} onChange={(v) => setLf({ ...lf, kind: v ?? "grease" })} />
          <TextInput label={t("lube.viscosity")} value={lf.viscosity_grade} onChange={(e) => setLf({ ...lf, viscosity_grade: e.currentTarget.value })} />
          <Button onClick={() => addLub.mutate(undefined)} disabled={!lf.code || !lf.product}>{t("common.create")}</Button>
        </Stack>
      </Modal>
      <Modal opened={modal === "route"} onClose={() => setModal(null)} title={t("lube.routes")}>
        <Stack>
          <TextInput label={t("common.code")} value={rf.code} onChange={(e) => setRf({ ...rf, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={rf.name} onChange={(e) => setRf({ ...rf, name: e.currentTarget.value })} />
          <DeptSelect value={rf.department_id} onChange={(v) => setRf({ ...rf, department_id: v })} />
          <NumberInput label={t("pm.lead")} value={rf.lead_days} onChange={(v) => setRf({ ...rf, lead_days: v })} min={0} />
          <Button onClick={() => addRoute.mutate(undefined)} disabled={!rf.code || !rf.department_id}>{t("common.create")}</Button>
        </Stack>
      </Modal>
      <Modal opened={modal === "point"} onClose={() => setModal(null)} title={t("lube.points")} size="lg">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t("common.code")} value={pf.code} onChange={(e) => setPf({ ...pf, code: e.currentTarget.value })} />
          <AssetPicker value={pf.asset_id} onChange={(v) => setPf({ ...pf, asset_id: v })} />
          <TextInput label="Component" value={pf.component} onChange={(e) => setPf({ ...pf, component: e.currentTarget.value })} />
          <Select label={t("lube.lubricant")} value={pf.lubricant_id} onChange={(v) => setPf({ ...pf, lubricant_id: v })} data={(lubs.data ?? []).map((l) => ({ value: l.id, label: `${l.code} ${l.product}` }))} />
          <NumberInput label={t("common.quantity")} value={pf.quantity} onChange={(v) => setPf({ ...pf, quantity: v })} min={0.001} />
          <Select label={t("common.unit")} data={["g", "kg", "ml", "L", "strokes"]} value={pf.unit} onChange={(v) => setPf({ ...pf, unit: v ?? "g" })} />
          <TextInput label={t("lube.method")} value={pf.method} onChange={(e) => setPf({ ...pf, method: e.currentTarget.value })} />
          <NumberInput label={t("lube.freqDays")} value={pf.frequency_days} onChange={(v) => setPf({ ...pf, frequency_days: v })} min={1} />
          <Select label={t("lube.routes")} clearable value={pf.route_id} onChange={(v) => setPf({ ...pf, route_id: v })} data={(routes.data ?? []).map((r) => ({ value: r.id, label: r.code }))} />
          <UserPicker label="Responsible" value={pf.responsible_user_id} onChange={(v) => setPf({ ...pf, responsible_user_id: v })} />
        </SimpleGrid>
        <Group mt="md"><Button onClick={() => addPoint.mutate(undefined)} disabled={!pf.code || !pf.asset_id || !pf.lubricant_id}>{t("common.create")}</Button></Group>
      </Modal>
      <Modal opened={modal === "alt"} onClose={() => setModal(null)} title={t("lube.approveAlt")}>
        <Stack>
          <Alert color="yellow">{t("lube.mixWarning")}</Alert>
          <Select label={t("lube.lubricant")} value={af.lub} onChange={(v) => setAf({ ...af, lub: v })} data={(lubs.data ?? []).map((l) => ({ value: l.id, label: `${l.code} ${l.product}` }))} />
          <Select label={t("lube.alternative")} value={af.alt} onChange={(v) => setAf({ ...af, alt: v })} data={(lubs.data ?? []).filter((l) => l.id !== af.lub).map((l) => ({ value: l.id, label: `${l.code} ${l.product}` }))} />
          <Textarea label={t("lube.compat")} value={af.note} onChange={(e) => setAf({ ...af, note: e.currentTarget.value })} required />
          <Button onClick={() => addAlt.mutate(undefined)} disabled={!af.lub || !af.alt || af.note.length < 10}>{t("common.approve")}</Button>
        </Stack>
      </Modal>
    </>
  );
}

export default function LubePage() {
  return <Guard perm="lube.view"><Lube /></Guard>;
}
