"use client";

import { Alert, Anchor, Button, Checkbox, Group, Modal, MultiSelect, NumberInput, Progress, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Attachments } from "@/components/Attachments";
import { Gantt } from "@/components/Gantt";
import { KV, Loading, PageHeader, Section, StatusBadge } from "@/components/ui";
import { patch, post } from "@/lib/api";
import { fmtNum, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { SD } from "../page";

interface Pkg { id: string; code: string; name: string; duration_hours: number; planned_start: string | null; planned_finish: string | null; progress_pct: number; status: string;
  is_critical: boolean; total_float_hours: number; material_status: string; permit_status: string; loto_status: string; planned_manpower: number; contractor_manpower: number;
  delay_reason: string | null; predecessors: string[]; work_orders: { id: string; number: string; status: string }[] }
interface Detail { shutdown: SD; cpm: { duration_hours: number; critical_path: string[]; planned_window_hours: number; fits_window: boolean };
  readiness: Record<string, number | null | { code: string; reason: string | null }[]>; packages: Pkg[];
  checks: { id: string; category: string; description: string; is_done: boolean; result: string | null }[] }

const READY = ["not_ready", "partial", "ready", "not_required"];

export default function ShutdownDetail() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useSession();
  const q = useQ<Detail>(`/shutdowns/${id}`);
  const [pkg, setPkg] = useState<{ code: string; name: string; duration_hours: number | string; planned_manpower: number | string; contractor_manpower: number | string; predecessor_ids: string[] } | null>(null);
  const [prog, setProg] = useState<{ id: string; progress_pct: number | string; delay_reason: string; note: string } | null>(null);
  const [check, setCheck] = useState({ category: "pre_startup", description: "" });
  const [result, setResult] = useState<Record<string, string>>({});
  const [lessons, setLessons] = useState<string | null>(null);
  const m = can("shutdown.manage");
  const addPkg = useMut(() => post(`/shutdowns/${id}/packages`, { ...pkg, duration_hours: Number(pkg?.duration_hours), planned_manpower: Number(pkg?.planned_manpower), contractor_manpower: Number(pkg?.contractor_manpower) }), { onDone: () => setPkg(null) });
  const upd = useMut((a: { pid: string; body: object }) => patch(`/shutdowns/${id}/packages/${a.pid}`, a.body), { success: false });
  const logProg = useMut(() => post(`/shutdowns/${id}/packages/${prog?.id}/progress`, { progress_pct: Number(prog?.progress_pct), delay_reason: prog?.delay_reason || null, note: prog?.note || null }), { onDone: () => setProg(null) });
  const addCheck = useMut(() => post(`/shutdowns/${id}/checks`, check), { onDone: () => setCheck({ ...check, description: "" }) });
  const doneCheck = useMut((cid: string) => post(`/shutdowns/${id}/checks/${cid}/complete`, { result: result[cid] ?? "" }));
  const setStatus = useMut((status: string) => patch(`/shutdowns/${id}`, { status, lessons_learned: lessons ?? undefined }));
  if (!q.data) return <Loading />;
  const d = q.data;
  const r = d.readiness;
  const pct = (k: string) => (typeof r[k] === "number" ? (r[k] as number) : 0);
  return (
    <>
      <PageHeader title={`${d.shutdown.code} · ${d.shutdown.name}`} actions={m ? <>
        {d.shutdown.status === "planning" && <Button onClick={() => setStatus.mutate("ready")}>{t("status.ready")}</Button>}
        {["planning", "ready"].includes(d.shutdown.status) && <Button color="orange" onClick={() => setStatus.mutate("in_progress")}>{t("status.in_progress")}</Button>}
        {d.shutdown.status === "in_progress" && <Button color="teal" onClick={() => setStatus.mutate("completed")}>{t("status.completed")}</Button>}
        <Button variant="light" onClick={() => setPkg({ code: "", name: "", duration_hours: 4, planned_manpower: 2, contractor_manpower: 0, predecessor_ids: [] })}>+ {t("sd.packages")}</Button>
      </> : null}><StatusBadge value={d.shutdown.status} /></PageHeader>
      <SimpleGrid cols={{ base: 2, sm: 4, lg: 6 }} mb="md">
        <KV label={t("sd.duration")}>{fmtNum(d.cpm.duration_hours)} / {fmtNum(d.cpm.planned_window_hours)} h</KV>
        <KV label={t("sd.fits")}>{d.cpm.fits_window ? "✓" : <Text c="red" fw={700}>✗</Text>}</KV>
        <KV label={t("sd.progress")}><Progress value={pct("weighted_progress_pct")} /> {fmtNum(r.weighted_progress_pct as number)}%</KV>
        <KV label={t("sd.materials")}>{fmtNum(r.materials_ready_pct as number)}%</KV>
        <KV label={t("sd.permits")}>{fmtNum(r.permits_ready_pct as number)}%</KV>
        <KV label={t("sd.loto")}>{fmtNum(r.loto_ready_pct as number)}%</KV>
      </SimpleGrid>
      <Tabs defaultValue="gantt">
        <Tabs.List><Tabs.Tab value="gantt">{t("sd.gantt")}</Tabs.Tab><Tabs.Tab value="packages">{t("sd.packages")}</Tabs.Tab>
          <Tabs.Tab value="checks">{t("sd.checks")}</Tabs.Tab><Tabs.Tab value="report">{t("sd.report")}</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="gantt" pt="md">
          <Text size="sm" mb="xs">{t("sd.criticalPath")}: <b>{d.cpm.critical_path.join(" → ")}</b></Text>
          <Gantt from={d.shutdown.planned_start} to={d.shutdown.planned_end} items={d.packages.map((p) => ({ id: p.id, label: `${p.code} ${p.name}`, start: p.planned_start, end: p.planned_finish, critical: p.is_critical, progress: Number(p.progress_pct) }))} />
        </Tabs.Panel>
        <Tabs.Panel value="packages" pt="md">
          <Table.ScrollContainer minWidth={1000}><Table striped fz="sm">
            <Table.Thead><Table.Tr><Table.Th>{t("common.code")}</Table.Th><Table.Th>{t("common.name")}</Table.Th><Table.Th>{t("sd.duration")}</Table.Th><Table.Th>{t("sd.float")}</Table.Th>
              <Table.Th>{t("sd.materials")}</Table.Th><Table.Th>{t("sd.permits")}</Table.Th><Table.Th>{t("sd.loto")}</Table.Th><Table.Th>{t("sd.progress")}</Table.Th><Table.Th>WO</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{d.packages.map((p) => (
              <Table.Tr key={p.id} style={p.is_critical ? { borderInlineStart: "3px solid var(--mantine-color-red-7)" } : undefined}>
                <Table.Td>{p.code}</Table.Td><Table.Td>{p.name}{p.delay_reason && <Text size="xs" c="red">{p.delay_reason}</Text>}</Table.Td><Table.Td>{fmtNum(p.duration_hours)}</Table.Td><Table.Td>{fmtNum(p.total_float_hours)}</Table.Td>
                {(["material_status", "permit_status", "loto_status"] as const).map((k) => (
                  <Table.Td key={k}>{m ? <Select size="xs" w={120} data={READY.map((x) => ({ value: x, label: t(`status.${x}`) }))} value={p[k]} onChange={(v) => v && upd.mutate({ pid: p.id, body: { [k]: v } })} /> : <StatusBadge value={p[k]} />}</Table.Td>))}
                <Table.Td><Group gap={4} wrap="nowrap"><StatusBadge value={p.status} /><Text size="xs">{fmtNum(p.progress_pct)}%</Text>
                  {m && <Button size="compact-xs" variant="subtle" onClick={() => setProg({ id: p.id, progress_pct: Number(p.progress_pct), delay_reason: "", note: "" })}>±</Button>}</Group></Table.Td>
                <Table.Td>{p.work_orders.map((w) => <Anchor key={w.id} component={Link} href={`/work-orders/${w.id}`} size="xs" me={4}>{w.number}</Anchor>)}</Table.Td>
              </Table.Tr>))}</Table.Tbody>
          </Table></Table.ScrollContainer>
        </Tabs.Panel>
        <Tabs.Panel value="checks" pt="md">
          <Stack>
            {m && <Group align="end"><Select label={t("common.category")} data={["pre_startup", "commissioning"]} value={check.category} onChange={(v) => setCheck({ ...check, category: v ?? "pre_startup" })} />
              <TextInput label={t("common.description")} value={check.description} onChange={(e) => setCheck({ ...check, description: e.currentTarget.value })} style={{ flex: 1 }} />
              <Button disabled={!check.description} onClick={() => addCheck.mutate(undefined)}>{t("sd.addCheck")}</Button></Group>}
            {d.checks.map((c) => (
              <Group key={c.id} justify="space-between" wrap="nowrap">
                <Checkbox readOnly checked={c.is_done} label={`[${c.category}] ${c.description}${c.result ? ` — ${c.result}` : ""}`} />
                {!c.is_done && m && <Group gap={4} wrap="nowrap"><TextInput size="xs" placeholder="Result" value={result[c.id] ?? ""} onChange={(e) => setResult({ ...result, [c.id]: e.currentTarget.value })} />
                  <Button size="xs" disabled={(result[c.id] ?? "").length < 2} onClick={() => doneCheck.mutate(c.id)}>{t("common.confirm")}</Button></Group>}
              </Group>))}
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="report" pt="md">
          <Stack>
            <Section title={t("sd.lessons")}>
              <Textarea value={lessons ?? d.shutdown.lessons_learned ?? ""} onChange={(e) => setLessons(e.currentTarget.value)} autosize minRows={3} disabled={!m} />
              {m && <Button mt="xs" size="xs" onClick={() => void patch(`/shutdowns/${id}`, { lessons_learned: lessons }).then(() => q.refetch())}>{t("common.save")}</Button>}
            </Section>
            <Attachments entityType="shutdown" entityId={d.shutdown.id} defaultCategory="report" />
          </Stack>
        </Tabs.Panel>
      </Tabs>
      <Modal opened={!!pkg} onClose={() => setPkg(null)} title={t("sd.packages")}>
        {pkg && <Stack>
          <TextInput label={t("common.code")} value={pkg.code} onChange={(e) => setPkg({ ...pkg, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={pkg.name} onChange={(e) => setPkg({ ...pkg, name: e.currentTarget.value })} />
          <NumberInput label={t("sd.duration")} min={0.5} value={pkg.duration_hours} onChange={(v) => setPkg({ ...pkg, duration_hours: v })} />
          <SimpleGrid cols={2}><NumberInput label={t("sd.manpower")} min={0} value={pkg.planned_manpower} onChange={(v) => setPkg({ ...pkg, planned_manpower: v })} />
            <NumberInput label="Contractor" min={0} value={pkg.contractor_manpower} onChange={(v) => setPkg({ ...pkg, contractor_manpower: v })} /></SimpleGrid>
          <MultiSelect label={t("sd.predecessors")} data={d.packages.map((p) => ({ value: p.id, label: p.code }))} value={pkg.predecessor_ids} onChange={(v) => setPkg({ ...pkg, predecessor_ids: v })} />
          <Button disabled={!pkg.code || !pkg.name} onClick={() => addPkg.mutate(undefined)}>{t("common.create")}</Button>
        </Stack>}
      </Modal>
      <Modal opened={!!prog} onClose={() => setProg(null)} title={t("sd.progress")}>
        {prog && <Stack>
          <NumberInput label="%" min={0} max={100} value={prog.progress_pct} onChange={(v) => setProg({ ...prog, progress_pct: v })} />
          <TextInput label={t("sd.delayReason")} value={prog.delay_reason} onChange={(e) => setProg({ ...prog, delay_reason: e.currentTarget.value })} />
          <TextInput label={t("common.notes")} value={prog.note} onChange={(e) => setProg({ ...prog, note: e.currentTarget.value })} />
          <Button onClick={() => logProg.mutate(undefined)}>{t("common.save")}</Button>
        </Stack>}
      </Modal>
      {setStatus.error && <Alert color="red" mt="md">{setStatus.error.message}</Alert>}
    </>
  );
}
