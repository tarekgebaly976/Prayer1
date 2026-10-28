"use client";

import {
  Alert, Anchor, Badge, Button, Checkbox, Grid, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput, Textarea, Timeline,
} from "@mantine/core";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Attachments } from "@/components/Attachments";
import { PartsUsed } from "@/components/PartsUsed";
import { LotoRegister, PermitSignoff } from "@/components/Safety";
import { KV, Loading, PageHeader, Section, StatusBadge, UserPicker } from "@/components/ui";
import { del, download, patch, post } from "@/lib/api";
import { fmtDate, fmtMoney, fmtNum, fromLocalInput, toLocalInput, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { ChecklistItem, FailureCode, Page, Part, WODetail, Warehouse } from "@/lib/types";

const EXEC_STATES = ["in_progress", "on_hold"];

function Transition({ wo, allowed }: { wo: WODetail["work_order"]; allowed: string[] }) {
  const { t } = useTranslation();
  const [to, setTo] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const m = useMut(() => post(`/work-orders/${wo.id}/status`, { to, comment: comment || null }), { onDone: () => { setTo(null); setComment(""); } });
  if (!allowed.length) return null;
  return (
    <>
      <Group gap="xs" wrap="wrap">
        {allowed.map((s) => (
          <Button key={s} size="sm" variant={s === "cancelled" ? "outline" : "filled"} color={s === "cancelled" ? "red" : undefined}
            onClick={() => setTo(s)} data-testid={`to-${s}`} className="tap-target">{t("wo.moveTo")}: {t(`status.${s}`)}</Button>
        ))}
      </Group>
      <Modal opened={!!to} onClose={() => setTo(null)} title={to ? `${t("wo.moveTo")}: ${t(`status.${to}`)}` : ""}>
        <Textarea label={t("wo.transitionComment")} value={comment} onChange={(e) => setComment(e.currentTarget.value)} required={to === "cancelled"} data-testid="transition-comment" />
        <Button mt="md" loading={m.isPending} onClick={() => m.mutate(undefined)} data-testid="transition-confirm">{t("common.confirm")}</Button>
      </Modal>
    </>
  );
}

function ChecklistRow({ woId, item, editable }: { woId: string; item: ChecklistItem; editable: boolean }) {
  const { t } = useTranslation();
  const [val, setVal] = useState<number | string>(item.reading_value ?? "");
  const m = useMut((body: object) => patch(`/work-orders/${woId}/checklist/${item.id}`, body), { success: false });
  return (
    <Table.Tr>
      <Table.Td>{item.seq}</Table.Td>
      <Table.Td>{item.description}{item.is_required ? " *" : ""}{item.unit ? ` [${item.min_value ?? ""}–${item.max_value ?? ""} ${item.unit}]` : ""}</Table.Td>
      <Table.Td>
        {item.kind === "reading" ? (
          <Group gap={4} wrap="nowrap">
            <NumberInput size="xs" w={100} value={val} onChange={setVal} disabled={!editable} aria-label={t("wo.reading")} />
            <Button size="xs" disabled={!editable || val === ""} onClick={() => m.mutate({ is_done: true, reading_value: Number(val) })}>{t("common.save")}</Button>
          </Group>
        ) : (
          <Group gap={4}>
            <Button size="xs" color="teal" variant={item.is_done && item.is_ok ? "filled" : "light"} disabled={!editable} onClick={() => m.mutate({ is_done: true, is_ok: true })}>{t("wo.ok")}</Button>
            <Button size="xs" color="red" variant={item.is_done && item.is_ok === false ? "filled" : "light"} disabled={!editable} onClick={() => m.mutate({ is_done: true, is_ok: false })}>{t("wo.notOk")}</Button>
          </Group>
        )}
      </Table.Td>
      <Table.Td>{item.is_done ? (item.is_ok === false ? <Badge color="red">{item.reading_value !== null ? t("wo.outOfRange") : t("wo.notOk")}</Badge> : <Badge color="teal">✓</Badge>) : "—"}</Table.Td>
      <Table.Td><Text size="xs" c="dimmed">{item.done_by ?? ""}</Text></Table.Td>
    </Table.Tr>
  );
}

function Materials({ d }: { d: WODetail }) {
  const { t } = useTranslation();
  const { can, plant } = useSession();
  const wo = d.work_order;
  const parts = useQ<Page<Part>>("/inventory/parts", { limit: 500 }, { enabled: can("inventory.view") });
  const whs = useQ<Warehouse[]>("/inventory/warehouses", undefined, { enabled: can("inventory.view") });
  const [f, setF] = useState<{ part_id: string | null; warehouse_id: string | null; quantity: number | string }>({ part_id: null, warehouse_id: null, quantity: 1 });
  const reserve = useMut(() => post(`/work-orders/${wo.id}/reservations`, { ...f, quantity: Number(f.quantity) }));
  const issueRes = useMut((r: WODetail["reservations"][number]) => post(`/work-orders/${wo.id}/issues`, { part_id: r.part_id, warehouse_id: r.warehouse_id, quantity: Number(r.quantity) - Number(r.qty_issued), reservation_id: r.id }));
  const issueDirect = useMut(() => post(`/work-orders/${wo.id}/issues`, { ...f, quantity: Number(f.quantity) }));
  const ret = useMut(() => post(`/work-orders/${wo.id}/returns`, { ...f, quantity: Number(f.quantity), reason: "returned unused" }));
  const cancelRes = useMut((id: string) => del(`/work-orders/${wo.id}/reservations/${id}`));
  const ready = f.part_id && f.warehouse_id && Number(f.quantity) > 0;
  return (
    <Stack>
      <PartsUsed woId={wo.id} rows={d.parts_used} currency={wo.currency} editable={!["closed", "cancelled"].includes(wo.status)} />
      {(can("inventory.reserve") || can("inventory.transact")) && (
        <Group align="end" wrap="wrap">
          <Select label={t("wo.part")} searchable w={280} value={f.part_id} onChange={(v) => setF({ ...f, part_id: v })}
            data={(parts.data?.items ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.description} (${fmtNum(p.qty_available)} ${p.uom})` }))} />
          <Select label={t("wo.warehouse")} w={140} value={f.warehouse_id} onChange={(v) => setF({ ...f, warehouse_id: v })} data={(whs.data ?? []).map((w) => ({ value: w.id, label: w.code }))} />
          <NumberInput label={t("common.quantity")} w={110} min={0.001} value={f.quantity} onChange={(v) => setF({ ...f, quantity: v })} />
          {can("inventory.reserve") && <Button disabled={!ready} loading={reserve.isPending} onClick={() => reserve.mutate(undefined)}>{t("wo.reserve")}</Button>}
          {can("inventory.transact") && <Button variant="light" disabled={!ready} onClick={() => issueDirect.mutate(undefined)}>{t("wo.issue")}</Button>}
          {can("inventory.transact") && <Button variant="default" disabled={!ready} onClick={() => ret.mutate(undefined)}>{t("wo.return")}</Button>}
        </Group>
      )}
      <Text fw={600} size="sm">{t("wo.reservations")}</Text>
      <Table><Table.Tbody>
        {d.reservations.map((r) => (
          <Table.Tr key={r.id}>
            <Table.Td>{r.part_code}</Table.Td><Table.Td>{r.description}</Table.Td><Table.Td>{r.warehouse}</Table.Td>
            <Table.Td>{fmtNum(r.qty_issued)} / {fmtNum(r.quantity)} {r.uom}</Table.Td><Table.Td><StatusBadge value={r.status} /></Table.Td>
            <Table.Td>{r.status === "active" && can("inventory.transact") && <Button size="xs" onClick={() => issueRes.mutate(r)}>{t("wo.issue")}</Button>}
              {r.status === "active" && can("inventory.reserve") && <Button size="xs" variant="subtle" color="red" onClick={() => cancelRes.mutate(r.id)}>{t("common.cancel")}</Button>}</Table.Td>
          </Table.Tr>))}
      </Table.Tbody></Table>
      <Text fw={600} size="sm">{t("wo.transactions")}</Text>
      <Table><Table.Tbody>
        {d.transactions.map((x) => (
          <Table.Tr key={x.id}><Table.Td>{fmtDate(x.at, plant?.timezone, true)}</Table.Td><Table.Td>{x.part_code}</Table.Td><Table.Td>{x.type}</Table.Td>
            <Table.Td>{fmtNum(x.quantity)}</Table.Td><Table.Td>{fmtMoney(-Number(x.total_cost), wo.currency)}</Table.Td></Table.Tr>))}
      </Table.Tbody></Table>
    </Stack>
  );
}

export default function WODetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can, me, plant } = useSession();
  const q = useQ<WODetail>(`/work-orders/${id}/detail`);
  const codes = useQ<FailureCode[]>(q.data ? "/failure-codes" : null, { asset_id: q.data?.work_order.asset_id });
  const [exec, setExec] = useState<Record<string, unknown>>({});
  const [plan, setPlan] = useState<Record<string, unknown>>({});
  const [assignee, setAssignee] = useState<string | null>(null);
  const [force, setForce] = useState(false);
  const [labor, setLabor] = useState<{ work_date: string; hours: number | string; is_overtime: boolean; notes: string }>({ work_date: new Date().toISOString().slice(0, 10), hours: 1, is_overtime: false, notes: "" });
  const [test, setTest] = useState({ test_result: "", test_passed: true });
  const [comment, setComment] = useState("");
  const [svc, setSvc] = useState({ description: "", cost: 0 as number | string, po_reference: "" });
  const [lube, setLube] = useState<Record<string, number | string>>({});

  const d = q.data;
  // Re-seed the edit forms whenever a new version of the work order arrives (adjust state during render).
  const [seededVersion, setSeededVersion] = useState<string | null>(null);
  const seedKey = d ? `${d.work_order.id}:${d.work_order.version}` : null;
  if (d && seedKey !== seededVersion) {
    setSeededVersion(seedKey);
    const w = d.work_order;
    setExec({ findings: w.findings ?? "", recommendations: w.recommendations ?? "", root_cause: w.root_cause ?? "", corrective_action: w.corrective_action ?? "",
      symptom_code_id: w.symptom_code_id, problem_code_id: w.problem_code_id, cause_code_id: w.cause_code_id, remedy_code_id: w.remedy_code_id, downtime_hours: w.downtime_hours ?? "",
      production_loss_tons: w.production_loss_tons ?? "" });
    setPlan({ planned_start: toLocalInput(w.planned_start), planned_end: toLocalInput(w.planned_end), due_date: w.due_date ?? "", estimated_hours: w.estimated_hours ?? "",
      priority: w.priority, requires_loto: w.requires_loto, requires_permit: w.requires_permit, requires_testing: w.requires_testing, supervisor_id: w.supervisor_id });
  }

  const saveExec = useMut(() => patch(`/work-orders/${id}`, {
    ...exec, version: d?.work_order.version,
    downtime_hours: exec.downtime_hours === "" ? null : Number(exec.downtime_hours), production_loss_tons: exec.production_loss_tons === "" ? null : Number(exec.production_loss_tons),
  }));
  const savePlan = useMut(() => patch(`/work-orders/${id}`, {
    ...plan, version: d?.work_order.version, planned_start: fromLocalInput(String(plan.planned_start ?? "")), planned_end: fromLocalInput(String(plan.planned_end ?? "")),
    due_date: plan.due_date || null, estimated_hours: plan.estimated_hours === "" ? null : Number(plan.estimated_hours),
  }));
  const assign = useMut(() => post(`/work-orders/${id}/assign`, { user_ids: [assignee], lead_id: assignee, force }));
  const unassign = useMut((uid: string) => del(`/work-orders/${id}/assign/${uid}`));
  const recordTest = useMut(() => post(`/work-orders/${id}/test-result`, test));
  const addLabor = useMut(() => post(`/work-orders/${id}/labor`, { ...labor, hours: Number(labor.hours), notes: labor.notes || null }));
  const addComment = useMut(() => post(`/work-orders/${id}/comments`, { body: comment }), { onDone: () => setComment("") });
  const addSvc = useMut(() => post(`/work-orders/${id}/services`, { ...svc, cost: Number(svc.cost), po_reference: svc.po_reference || null }));
  const recLube = useMut((task: WODetail["lube_tasks"][number]) => post(`/lubrication/tasks/${task.id}/record`, { quantity: Number(lube[task.id] ?? task.quantity) }));

  if (!d) return <Loading />;
  const w = d.work_order;
  const isAssignee = d.assignees.some((a) => a.user_id === me?.id);
  const canExec = can("wo.execute") && (isAssignee || can("wo.assign")) && EXEC_STATES.includes(w.status);
  const finished = ["closed", "cancelled"].includes(w.status);
  // The failure modes of this equipment's type come first, so the technician picks from a short list.
  const codeOpts = (k: string) => {
    const all = (codes.data ?? []).filter((c) => c.kind === k);
    const opt = (c: FailureCode) => ({ value: c.id, label: `${c.code} — ${c.description}${c.category ? ` (${c.category})` : ""}` });
    const mine = all.filter((c) => c.suggested);
    if (!mine.length) return all.map(opt);
    return [{ group: t("fm.forType", { type: mine[0]?.equipment_type ?? "" }), items: mine.map(opt) }, { group: t("fm.other"), items: all.filter((c) => !c.suggested).map(opt) }];
  };

  return (
    <>
      <PageHeader title={`${w.number} · ${w.title}`} actions={<>
        {w.source === "migrated" && <Badge color="gray" variant="outline">{t("planImport.migrated")} · {w.external_ref}</Badge>}
        <Button variant="default" onClick={() => void download(`/reports/work-orders/${w.id}.pdf`)}>{t("wo.pdf")}</Button>
      </>}>
        <Group gap="xs">
          <StatusBadge value={w.status} size="lg" data-testid="wo-status" /><StatusBadge value={w.priority} /><Badge variant="outline">{t(`woType.${w.type}`)}</Badge>
          {w.is_repeat_failure && <Badge color="red">{t("wo.repeat")}</Badge>}
          {d.asset && <Anchor component={Link} href={`/assets/${d.asset.id}`} size="sm">{d.asset.code} — {d.asset.name}</Anchor>}
        </Group>
      </PageHeader>
      {(w.requires_loto || w.requires_permit) && (
        <Alert color={w.safety_signed_at ? "teal" : "red"} mb="md" title={t("wo.safety")}>
          {w.requires_loto && <div>• {t("wo.loto")} — {d.loto.filter((x) => !x.removed_at).length} 🔒</div>}
          {w.requires_permit && <div>• {t("wo.permit")} {w.permit_reference ? `(${w.permit_reference})` : ""}
            {w.permit_types ? ` · ${w.permit_types.split(",").map((p) => t(`safety.types.${p}`)).join(", ")}` : ""}
            {w.permit_valid_until ? ` · ${t("safety.validUntil")} ${fmtDate(w.permit_valid_until, plant?.timezone, true)}` : ""}</div>}
          {w.safety_requirements && <div>{w.safety_requirements}</div>}
          {w.safety_signed_at ? <div>{t("wo.signedBy")}: {d.safety_signed_by} · {fmtDate(w.safety_signed_at, plant?.timezone, true)}</div> : null}
        </Alert>
      )}
      <Stack mb="md"><Transition wo={w} allowed={d.allowed_transitions} /></Stack>
      <Tabs defaultValue="exec" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="exec">{t("wo.checklist")}</Tabs.Tab>
          <Tabs.Tab value="details">{t("common.details")}</Tabs.Tab>
          <Tabs.Tab value="labor">{t("wo.labor")}</Tabs.Tab>
          <Tabs.Tab value="materials">{t("wo.materials")}</Tabs.Tab>
          <Tabs.Tab value="files">{t("common.attachments")}</Tabs.Tab>
          <Tabs.Tab value="history">{t("common.history")}</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="exec" pt="md">
          <Stack>
            {d.lube_tasks.length > 0 && (
              <Section title={t("wo.lubeTasks")}>
                <Alert color="yellow" mb="sm">{t("lube.mixWarning")}</Alert>
                <Table><Table.Tbody>{d.lube_tasks.map((x) => (
                  <Table.Tr key={x.id}>
                    <Table.Td>{x.point_code}</Table.Td><Table.Td>{x.component} {x.location}</Table.Td><Table.Td>{x.lubricant}</Table.Td>
                    <Table.Td>{fmtNum(x.quantity)} {x.unit} · {x.method}</Table.Td>
                    <Table.Td>{x.status === "pending" ? (
                      <Group gap={4} wrap="nowrap"><NumberInput size="xs" w={90} value={lube[x.id] ?? Number(x.quantity)} onChange={(v) => setLube({ ...lube, [x.id]: v })} disabled={!canExec} aria-label={t("lube.actualQty")} />
                        <Button size="xs" disabled={!canExec || !can("lube.execute")} onClick={() => recLube.mutate(x)}>{t("wo.recordLube")}</Button></Group>
                    ) : <StatusBadge value={x.status} />}</Table.Td>
                  </Table.Tr>))}</Table.Tbody></Table>
              </Section>
            )}
            <Section title={t("wo.checklist")}>
              {d.checklist.length === 0 ? <Text c="dimmed" size="sm">{t("common.noData")}</Text> : (
                <Table.ScrollContainer minWidth={560}><Table><Table.Tbody>
                  {d.checklist.map((c) => <ChecklistRow key={c.id} woId={w.id} item={c} editable={canExec} />)}
                </Table.Tbody></Table></Table.ScrollContainer>
              )}
            </Section>
            <Section title={t("wo.findings")} actions={<Button size="xs" disabled={finished || !(can("wo.edit") || (can("wo.execute") && isAssignee))} loading={saveExec.isPending} onClick={() => saveExec.mutate(undefined)}>{t("common.save")}</Button>}>
              <SimpleGrid cols={{ base: 1, sm: 3 }} mb="sm">
                <Select label={t("wo.symptoms")} data={codeOpts("symptom")} value={(exec.symptom_code_id as string) ?? null} onChange={(v) => setExec({ ...exec, symptom_code_id: v })} clearable searchable />
                <Select label={t("wo.problem")} data={codeOpts("problem")} value={(exec.problem_code_id as string) ?? null} onChange={(v) => setExec({ ...exec, problem_code_id: v })} clearable searchable />
                <Select label={t("wo.cause")} data={codeOpts("cause")} value={(exec.cause_code_id as string) ?? null} onChange={(v) => setExec({ ...exec, cause_code_id: v })} clearable searchable />
                <Select label={t("wo.remedy")} data={codeOpts("remedy")} value={(exec.remedy_code_id as string) ?? null} onChange={(v) => setExec({ ...exec, remedy_code_id: v })} clearable searchable />
              </SimpleGrid>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Textarea label={t("wo.findings")} autosize minRows={2} value={String(exec.findings ?? "")} onChange={(e) => setExec({ ...exec, findings: e.currentTarget.value })} />
                <Textarea label={t("wo.recommendations")} autosize minRows={2} value={String(exec.recommendations ?? "")} onChange={(e) => setExec({ ...exec, recommendations: e.currentTarget.value })} />
                <Textarea label={t("wo.rootCause")} autosize minRows={2} value={String(exec.root_cause ?? "")} onChange={(e) => setExec({ ...exec, root_cause: e.currentTarget.value })} />
                <Textarea label={t("wo.correctiveAction")} autosize minRows={2} value={String(exec.corrective_action ?? "")} onChange={(e) => setExec({ ...exec, corrective_action: e.currentTarget.value })} />
                <NumberInput label={t("wo.downtime")} min={0} value={exec.downtime_hours as number | string} onChange={(v) => setExec({ ...exec, downtime_hours: v })} />
                <NumberInput label={t("wo.productionLoss")} min={0} value={exec.production_loss_tons as number | string} onChange={(v) => setExec({ ...exec, production_loss_tons: v })} />
              </SimpleGrid>
            </Section>
            {(w.requires_loto || d.loto.length > 0) && (
              <Section title={t("safety.lotoRegister")}><LotoRegister woId={w.id} rows={d.loto} status={w.status} /></Section>
            )}
            <Grid>
              <Grid.Col span={{ base: 12, md: 6 }}>
                <Section title={t("wo.safetySign")}>
                  <PermitSignoff key={`${w.id}:${w.version}`} wo={w} />
                </Section>
              </Grid.Col>
              <Grid.Col span={{ base: 12, md: 6 }}>
                <Section title={t("wo.testResult")}>
                  {w.test_result && <Text size="sm" mb="xs">{w.test_passed ? "✓" : "✗"} {w.test_result} — {d.tested_by}</Text>}
                  <Textarea value={test.test_result} onChange={(e) => setTest({ ...test, test_result: e.currentTarget.value })} disabled={!can("wo.review")} autosize aria-label={t("wo.testResult")} />
                  <Group mt="xs">
                    <Checkbox label={t("wo.testPassed")} checked={test.test_passed} onChange={(e) => setTest({ ...test, test_passed: e.currentTarget.checked })} disabled={!can("wo.review")} />
                    <Button size="xs" disabled={!can("wo.review") || test.test_result.length < 3 || !["in_progress", "awaiting_review"].includes(w.status)} onClick={() => recordTest.mutate(undefined)}>{t("wo.recordTest")}</Button>
                  </Group>
                </Section>
              </Grid.Col>
            </Grid>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="details" pt="md">
          <Stack>
            <SimpleGrid cols={{ base: 2, sm: 4 }}>
              <KV label={t("common.dueDate")}>{fmtDate(w.due_date)}</KV>
              <KV label={t("wo.plannedStart")}>{fmtDate(w.planned_start, plant?.timezone, true)}</KV>
              <KV label="Actual start">{fmtDate(w.actual_start, plant?.timezone, true)}</KV>
              <KV label="Actual end">{fmtDate(w.actual_end, plant?.timezone, true)}</KV>
              <KV label={t("wo.estHours")}>{fmtNum(w.estimated_hours)}</KV>
              <KV label={t("wo.labor")}>{fmtNum(w.actual_labor_hours)} h · {fmtMoney(w.actual_labor_cost, w.currency)}</KV>
              <KV label={t("wo.materials")}>{fmtMoney(w.actual_material_cost, w.currency)}</KV>
              <KV label={t("wo.actualCost")}><b>{fmtMoney(w.actual_cost, w.currency)}</b></KV>
            </SimpleGrid>
            {w.symptoms && <KV label={t("wo.symptoms")}>{w.symptoms}</KV>}
            {w.description && <KV label={t("common.description")}><Text style={{ whiteSpace: "pre-wrap" }}>{w.description}</Text></KV>}
            <Section title={t("wo.assignees")}>
              <Stack gap={4} mb="sm">{d.assignees.map((a) => (
                <Group key={a.user_id} gap="xs"><Text size="sm">{a.name}{a.is_lead ? ` (${t("wo.lead")})` : ""}</Text>
                  {can("wo.assign") && !finished && <Button size="compact-xs" variant="subtle" color="red" onClick={() => unassign.mutate(a.user_id)}>×</Button>}</Group>))}</Stack>
              {can("wo.assign") && !finished && (
                <Group align="end">
                  <UserPicker label={t("wo.assign")} value={assignee} onChange={setAssignee} />
                  <Checkbox label={t("wo.force")} checked={force} onChange={(e) => setForce(e.currentTarget.checked)} />
                  <Button disabled={!assignee} loading={assign.isPending} onClick={() => assign.mutate(undefined)}>{t("wo.assign")}</Button>
                </Group>
              )}
            </Section>
            {can("wo.edit") && !finished && w.status !== "completed" && (
              <Section title={t("common.edit")} actions={<Button size="xs" loading={savePlan.isPending} onClick={() => savePlan.mutate(undefined)}>{t("common.save")}</Button>}>
                <SimpleGrid cols={{ base: 1, sm: 3 }}>
                  <TextInput type="datetime-local" label={t("wo.plannedStart")} value={String(plan.planned_start ?? "")} onChange={(e) => setPlan({ ...plan, planned_start: e.currentTarget.value })} />
                  <TextInput type="datetime-local" label={t("wo.plannedEnd")} value={String(plan.planned_end ?? "")} onChange={(e) => setPlan({ ...plan, planned_end: e.currentTarget.value })} />
                  <TextInput type="date" label={t("common.dueDate")} value={String(plan.due_date ?? "")} onChange={(e) => setPlan({ ...plan, due_date: e.currentTarget.value })} />
                  <NumberInput label={t("wo.estHours")} min={0} value={plan.estimated_hours as number | string} onChange={(v) => setPlan({ ...plan, estimated_hours: v })} />
                  <Select label={t("common.priority")} data={["P1", "P2", "P3", "P4"]} value={plan.priority as string} onChange={(v) => setPlan({ ...plan, priority: v })} allowDeselect={false} />
                  <UserPicker label={t("wo.supervisor")} value={(plan.supervisor_id as string) ?? null} onChange={(v) => setPlan({ ...plan, supervisor_id: v })} />
                </SimpleGrid>
                <Group mt="sm">
                  <Checkbox label={t("wo.loto")} checked={!!plan.requires_loto} onChange={(e) => setPlan({ ...plan, requires_loto: e.currentTarget.checked })} />
                  <Checkbox label={t("wo.permit")} checked={!!plan.requires_permit} onChange={(e) => setPlan({ ...plan, requires_permit: e.currentTarget.checked })} />
                  <Checkbox label={t("wo.testing")} checked={!!plan.requires_testing} onChange={(e) => setPlan({ ...plan, requires_testing: e.currentTarget.checked })} />
                </Group>
              </Section>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="labor" pt="md">
          <Stack>
            {(isAssignee || can("wo.assign")) && can("wo.execute") && !finished && (
              <Group align="end" wrap="wrap">
                <TextInput type="date" label={t("common.date")} value={labor.work_date} onChange={(e) => setLabor({ ...labor, work_date: e.currentTarget.value })} />
                <NumberInput label={t("common.hours")} min={0.25} max={24} step={0.25} w={100} value={labor.hours} onChange={(v) => setLabor({ ...labor, hours: v })} />
                <Checkbox label={t("wo.overtime")} checked={labor.is_overtime} onChange={(e) => setLabor({ ...labor, is_overtime: e.currentTarget.checked })} />
                <TextInput label={t("common.notes")} value={labor.notes} onChange={(e) => setLabor({ ...labor, notes: e.currentTarget.value })} />
                <Button loading={addLabor.isPending} onClick={() => addLabor.mutate(undefined)}>{t("wo.addLabor")}</Button>
              </Group>
            )}
            <Table><Table.Tbody>{d.labor.map((l) => (
              <Table.Tr key={l.id}><Table.Td>{l.work_date}</Table.Td><Table.Td>{l.name}</Table.Td><Table.Td>{fmtNum(l.hours)} h{l.is_overtime ? " OT" : ""}</Table.Td>
                <Table.Td>{fmtMoney(l.cost, w.currency)}</Table.Td><Table.Td>{l.notes}</Table.Td></Table.Tr>))}</Table.Tbody></Table>
            <Section title={t("wo.services")}>
              {can("wo.edit") && !finished && (
                <Group align="end" mb="sm" wrap="wrap">
                  <TextInput label={t("common.description")} value={svc.description} onChange={(e) => setSvc({ ...svc, description: e.currentTarget.value })} />
                  <NumberInput label={t("common.cost")} min={0} value={svc.cost} onChange={(v) => setSvc({ ...svc, cost: v })} />
                  <TextInput label="PO" value={svc.po_reference} onChange={(e) => setSvc({ ...svc, po_reference: e.currentTarget.value })} />
                  <Button disabled={!svc.description} onClick={() => addSvc.mutate(undefined)}>{t("wo.addService")}</Button>
                </Group>
              )}
              {d.services.map((s) => <Text key={s.id} size="sm">{s.description} — {fmtMoney(s.cost, w.currency)} {s.po_reference ?? ""}</Text>)}
            </Section>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="materials" pt="md"><Materials d={d} /></Tabs.Panel>
        <Tabs.Panel value="files" pt="md"><Attachments entityType="work_order" entityId={w.id} defaultCategory="photo" /></Tabs.Panel>
        <Tabs.Panel value="history" pt="md">
          <Grid>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Timeline active={d.history.length} bulletSize={14}>
                {d.history.map((h, i) => (
                  <Timeline.Item key={i} title={t(`status.${h.to}`)}>
                    <Text size="xs" c="dimmed">{h.by} · {fmtDate(h.at, plant?.timezone, true)}</Text>{h.comment && <Text size="sm">{h.comment}</Text>}
                  </Timeline.Item>))}
              </Timeline>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Stack gap="xs">
                {d.comments.map((c) => <div key={c.id}><Text size="xs" c="dimmed">{c.user} · {fmtDate(c.at, plant?.timezone, true)}</Text><Text size="sm">{c.body}</Text></div>)}
                <Textarea placeholder={t("wo.addComment")} value={comment} onChange={(e) => setComment(e.currentTarget.value)} />
                <Group><Button size="xs" disabled={!comment} onClick={() => addComment.mutate(undefined)}>{t("wo.addComment")}</Button></Group>
              </Stack>
            </Grid.Col>
          </Grid>
        </Tabs.Panel>
      </Tabs>
    </>
  );
}
