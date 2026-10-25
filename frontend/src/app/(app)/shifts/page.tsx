"use client";

import { Badge, Button, Checkbox, Group, Modal, NumberInput, ScrollArea, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { DataTable, DeptSelect, PageHeader, StatusBadge, UserPicker } from "@/components/ui";
import { post, put } from "@/lib/api";
import { useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";

interface ShiftDef { id: string; code: string; name: string; kind: string; start_time: string; end_time: string }
interface Entry { id: string; user_id: string; name: string; trade: string | null; work_date: string; shift: string | null; kind: string; hours: number; overtime_hours: number; callout_hours: number }
interface Team { id: string; code: string; name: string; pattern_id: string | null; members: { id: string; name: string }[] }
interface Handover { id: string; department_id: string; shift_date: string; shift_id: string; status: string; summary: string; outgoing_user_id: string }
interface Manpower { date: string; people: number; total_supply: number; total_demand: number; flags: string[] }

const addDays = (d: string, n: number) => { const x = new Date(`${d}T00:00:00`); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };
const KIND_COLOR: Record<string, string> = { work: "blue", overtime: "orange", callout: "red", leave: "gray", absence: "dark" };

function Shifts() {
  const { t } = useTranslation();
  const router = useRouter();
  const { can, me } = useSession();
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10));
  const end = addDays(start, 13);
  const shifts = useQ<ShiftDef[]>("/shifts/definitions");
  const roster = useQ<Entry[]>("/shifts/roster", { start, end });
  const teams = useQ<Team[]>("/shifts/teams");
  const handovers = useQ<Handover[]>("/shifts/handovers");
  const mp = useQ<Manpower[]>("/shifts/manpower", { start, end });
  const days = Array.from({ length: 14 }, (_, i) => addDays(start, i));
  const people = useMemo(() => {
    const m = new Map<string, { name: string; trade: string | null; cells: Map<string, Entry> }>();
    (roster.data ?? []).forEach((e) => {
      if (!m.has(e.user_id)) m.set(e.user_id, { name: e.name, trade: e.trade, cells: new Map() });
      m.get(e.user_id)?.cells.set(e.work_date, e);
    });
    return [...m.entries()];
  }, [roster.data]);
  const [entry, setEntry] = useState<{ user_id: string | null; work_date: string; shift_id: string | null; kind: string; hours: number | string; overtime_hours: number | string; callout_hours: number | string; replace: boolean } | null>(null);
  const [gen, setGen] = useState<string | null>(null);
  const [ho, setHo] = useState<Record<string, string | null> | null>(null);
  const saveEntry = useMut(() => put("/shifts/roster", { ...entry, hours: Number(entry?.hours), overtime_hours: Number(entry?.overtime_hours), callout_hours: Number(entry?.callout_hours),
    shift_id: entry?.kind === "leave" || entry?.kind === "absence" ? null : entry?.shift_id }), { onDone: () => setEntry(null) });
  const genRoster = useMut(() => post(`/shifts/teams/${gen}/generate-roster`, { start, end }), { onDone: () => setGen(null) });
  const createHo = useMut(() => post<{ id: string }>("/shifts/handovers", ho), { onDone: (r) => router.push(`/shifts/handovers/${r.id}`) });
  return (
    <>
      <PageHeader title={t("nav.shifts")} actions={<>
        {can("handover.create") && <Button onClick={() => setHo({ department_id: null, shift_date: new Date().toISOString().slice(0, 10), shift_id: null, summary: "", incoming_user_id: null,
          outstanding_breakdowns: "", pending_work: "", safety_concerns: "", equipment_abnormalities: "", pending_permits: "", critical_risks: "" })}>{t("shift.newHandover")}</Button>}
        {can("shift.manage") && <Button variant="light" onClick={() => setEntry({ user_id: null, work_date: start, shift_id: null, kind: "work", hours: 8, overtime_hours: 0, callout_hours: 0, replace: false })}>{t("shift.setEntry")}</Button>}
      </>}>
        <Group><TextInput type="date" value={start} onChange={(e) => setStart(e.currentTarget.value)} aria-label={t("common.start")} /><Text size="sm" c="dimmed">→ {end}</Text></Group>
      </PageHeader>
      <Tabs defaultValue="roster">
        <Tabs.List><Tabs.Tab value="roster">{t("shift.roster")}</Tabs.Tab><Tabs.Tab value="manpower">{t("shift.manpower")}</Tabs.Tab>
          <Tabs.Tab value="handovers">{t("shift.handovers")}</Tabs.Tab><Tabs.Tab value="teams">{t("shift.teams")}</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="roster" pt="md">
          <ScrollArea type="auto">
            <Table withTableBorder withColumnBorders miw={900} fz="xs">
              <Table.Thead><Table.Tr><Table.Th>{t("common.user")}</Table.Th>{days.map((d) => <Table.Th key={d}>{d.slice(5)}</Table.Th>)}</Table.Tr></Table.Thead>
              <Table.Tbody>{people.map(([uid, p]) => (
                <Table.Tr key={uid}><Table.Td>{p.name}<Text size="xs" c="dimmed">{p.trade}</Text></Table.Td>
                  {days.map((d) => { const e = p.cells.get(d); return (
                    <Table.Td key={d} style={{ cursor: can("shift.manage") ? "pointer" : undefined }}
                      onClick={() => can("shift.manage") && setEntry({ user_id: uid, work_date: d, shift_id: shifts.data?.find((s) => s.code === e?.shift)?.id ?? null, kind: e?.kind ?? "work",
                        hours: e?.hours ?? 8, overtime_hours: e?.overtime_hours ?? 0, callout_hours: e?.callout_hours ?? 0, replace: !!e })}>
                      {e ? <Badge size="xs" color={KIND_COLOR[e.kind]} variant="light">{e.shift ?? e.kind}{Number(e.overtime_hours) > 0 ? "+OT" : ""}</Badge> : ""}
                    </Table.Td>); })}
                </Table.Tr>))}</Table.Tbody>
            </Table>
          </ScrollArea>
        </Tabs.Panel>
        <Tabs.Panel value="manpower" pt="md">
          <DataTable rows={mp.data} rowKey={(r) => r.date} columns={[
            { key: "d", label: t("common.date"), render: (r) => r.date }, { key: "p", label: t("common.user"), render: (r) => r.people },
            { key: "s", label: t("shift.supply"), render: (r) => r.total_supply }, { key: "dm", label: t("shift.demand"), render: (r) => r.total_demand },
            { key: "f", label: t("shift.flags"), render: (r) => r.flags.map((f) => <Text key={f} size="xs" c="red">⚠ {f}</Text>) }]} />
        </Tabs.Panel>
        <Tabs.Panel value="handovers" pt="md">
          <DataTable rows={handovers.data} onRow={(h) => router.push(`/shifts/handovers/${h.id}`)} columns={[
            { key: "d", label: t("common.date"), render: (h) => h.shift_date }, { key: "sh", label: t("shift.shift"), render: (h) => shifts.data?.find((s) => s.id === h.shift_id)?.code },
            { key: "s", label: t("common.status"), render: (h) => <StatusBadge value={h.status} /> }, { key: "m", label: t("shift.summary"), render: (h) => h.summary.slice(0, 80) },
            { key: "o", label: t("shift.outgoing"), render: (h) => (h.outgoing_user_id === me?.id ? "✓ me" : "") }]} />
        </Tabs.Panel>
        <Tabs.Panel value="teams" pt="md">
          <DataTable rows={teams.data} columns={[
            { key: "c", label: t("common.code"), render: (x) => x.code }, { key: "n", label: t("common.name"), render: (x) => x.name },
            { key: "m", label: t("common.user"), render: (x) => x.members.map((m) => m.name).join(", ") },
            { key: "g", label: t("common.actions"), render: (x) => can("shift.manage") && x.pattern_id && <Button size="xs" onClick={() => setGen(x.id)}>{t("shift.generateRoster")}</Button> }]} />
        </Tabs.Panel>
      </Tabs>
      <Modal opened={!!entry} onClose={() => setEntry(null)} title={t("shift.setEntry")}>
        {entry && <Stack>
          <UserPicker label={t("common.user")} value={entry.user_id} onChange={(v) => setEntry({ ...entry, user_id: v })} />
          <TextInput type="date" label={t("common.date")} value={entry.work_date} onChange={(e) => setEntry({ ...entry, work_date: e.currentTarget.value })} />
          <Select label={t("shift.kind")} value={entry.kind} onChange={(v) => setEntry({ ...entry, kind: v ?? "work" })} data={["work", "overtime", "callout", "leave", "absence"]} />
          {!["leave", "absence"].includes(entry.kind) && <Select label={t("shift.shift")} value={entry.shift_id} onChange={(v) => setEntry({ ...entry, shift_id: v })} data={(shifts.data ?? []).map((s) => ({ value: s.id, label: `${s.code} ${s.start_time.slice(0, 5)}–${s.end_time.slice(0, 5)}` }))} />}
          <SimpleGrid cols={3}>
            <NumberInput label={t("common.hours")} value={entry.hours} onChange={(v) => setEntry({ ...entry, hours: v })} min={0} max={24} />
            <NumberInput label={t("shift.overtimeH")} value={entry.overtime_hours} onChange={(v) => setEntry({ ...entry, overtime_hours: v })} min={0} />
            <NumberInput label={t("shift.calloutH")} value={entry.callout_hours} onChange={(v) => setEntry({ ...entry, callout_hours: v })} min={0} />
          </SimpleGrid>
          <Checkbox label={t("shift.replace")} checked={entry.replace} onChange={(e) => setEntry({ ...entry, replace: e.currentTarget.checked })} />
          <Button disabled={!entry.user_id} onClick={() => saveEntry.mutate(undefined)}>{t("common.save")}</Button>
        </Stack>}
      </Modal>
      <Modal opened={!!gen} onClose={() => setGen(null)} title={t("shift.generateRoster")}>
        <Text size="sm">{start} → {end}</Text>
        <Button mt="md" onClick={() => genRoster.mutate(undefined)}>{t("common.generate")}</Button>
      </Modal>
      <Modal opened={!!ho} onClose={() => setHo(null)} title={t("shift.newHandover")} size="lg">
        {ho && <Stack>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <DeptSelect value={ho.department_id ?? null} onChange={(v) => setHo({ ...ho, department_id: v })} />
            <TextInput type="date" label={t("common.date")} value={ho.shift_date ?? ""} onChange={(e) => setHo({ ...ho, shift_date: e.currentTarget.value })} />
            <Select label={t("shift.shift")} value={ho.shift_id ?? null} onChange={(v) => setHo({ ...ho, shift_id: v })} data={(shifts.data ?? []).map((s) => ({ value: s.id, label: s.code }))} />
          </SimpleGrid>
          <UserPicker label={t("shift.incoming")} value={ho.incoming_user_id ?? null} onChange={(v) => setHo({ ...ho, incoming_user_id: v })} />
          {(["summary", "outstanding_breakdowns", "pending_work", "safety_concerns", "equipment_abnormalities", "pending_permits", "critical_risks"] as const).map((k) => (
            <Textarea key={k} label={t({ summary: "shift.summary", outstanding_breakdowns: "shift.outstanding", pending_work: "shift.pendingWork", safety_concerns: "shift.safetyConcerns",
              equipment_abnormalities: "shift.abnormalities", pending_permits: "shift.pendingPermits", critical_risks: "shift.risks" }[k])} autosize
              value={ho[k] ?? ""} onChange={(e) => setHo({ ...ho, [k]: e.currentTarget.value || null })} required={k === "summary"} />
          ))}
          <Button disabled={!ho.department_id || !ho.shift_id || (ho.summary ?? "").length < 5} onClick={() => createHo.mutate(undefined)}>{t("common.create")}</Button>
        </Stack>}
      </Modal>
    </>
  );
}

export default function ShiftsPage() {
  return <Guard perm="shift.view"><Shifts /></Guard>;
}
