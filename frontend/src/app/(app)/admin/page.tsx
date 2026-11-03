"use client";

import { Alert, Autocomplete, Badge, Button, Checkbox, Code, FileInput, Group, Modal, MultiSelect, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Switch, Tabs, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { FailureCodeImport } from "@/components/FailureModes";
import { PartsImport } from "@/components/PartsImport";
import { PlanImport } from "@/components/PlanImport";
import { DataTable, DeptMultiSelect, DeptSelect, PageHeader, Pager, StatusBadge, TradeInput } from "@/components/ui";
import { api, del, download, patch, post, put } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Department, FailureCode, Member, Page } from "@/lib/types";

interface Transition { id: string; from_status: string; to_status: string; permission: string; is_active: boolean }
interface PlantCfg { id: string; code: string; name: string; timezone: string; currency: string; allow_negative_stock: boolean; working_hours_per_day: number; working_days: number[]; settings: Record<string, unknown> }
interface Audit { id: number; at: string; user_id: string | null; action: string; entity_type: string | null; entity_id: string | null; data: Record<string, unknown>; ip: string | null }
interface Job { id: string; job: string; status: string; started_at: string; finished_at: string | null; error: string | null; details: Record<string, unknown> }

const deptIds = (m: Member) => m.department_ids ?? (m.department_id ? [m.department_id] : []);

function EditUser({ m, roleOpts, onClose }: { m: Member; roleOpts: { value: string; label: string }[]; onClose: () => void }) {
  const { t } = useTranslation();
  const u = m.user;
  const [f, setF] = useState({ email: u.email, full_name: u.full_name, employee_no: u.employee_no ?? "", trade: u.trade ?? "",
    hourly_rate: (u.hourly_rate ?? "") as number | string, role: m.role_code, department_ids: deptIds(m) });
  const [pw, setPw] = useState("");
  const save = useMut(() => patch(`/users/${u.id}`, { ...f, employee_no: f.employee_no || null, trade: f.trade || null,
    hourly_rate: f.hourly_rate === "" ? null : Number(f.hourly_rate) }), { onDone: onClose });
  const reset = useMut(() => post(`/users/${u.id}/reset-password`, { password: pw }), { success: t("admin.passwordReset"), onDone: () => setPw("") });
  const remove = useMut(() => del(`/users/${u.id}`), { success: t("admin.removed"), onDone: onClose });
  return (
    <Modal opened onClose={onClose} title={`${t("admin.editUser")}: ${u.full_name}`}>
      <Stack>
        <TextInput label={t("common.email")} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.currentTarget.value })} />
        <TextInput label={t("common.name")} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.currentTarget.value })} />
        <Select label={t("common.role")} data={roleOpts} value={f.role} onChange={(v) => setF({ ...f, role: v ?? f.role })} allowDeselect={false} />
        <DeptMultiSelect value={f.department_ids} onChange={(v) => setF({ ...f, department_ids: v })} label={t("admin.departments")} placeholder={t("admin.allDepts")} />
        <SimpleGrid cols={3}><TradeInput value={f.trade} onChange={(v) => setF({ ...f, trade: v })} />
          <TextInput label="Employee #" value={f.employee_no} onChange={(e) => setF({ ...f, employee_no: e.currentTarget.value })} />
          <NumberInput label="Rate/h" min={0} value={f.hourly_rate} onChange={(v) => setF({ ...f, hourly_rate: v })} /></SimpleGrid>
        <Button disabled={!f.email || f.full_name.length < 2} loading={save.isPending} onClick={() => save.mutate(undefined)}>{t("common.save")}</Button>
        <Group align="end">
          <TextInput label={t("admin.newPassword")} type="password" description="≥ 12 characters, 3 of: lower, upper, digit, symbol" value={pw}
            onChange={(e) => setPw(e.currentTarget.value)} style={{ flex: 1 }} />
          <Button variant="light" disabled={pw.length < 12} loading={reset.isPending} onClick={() => reset.mutate(undefined)}>{t("admin.resetPassword")}</Button>
        </Group>
        <Button color="red" variant="subtle" loading={remove.isPending}
          onClick={() => { if (window.confirm(t("admin.removeConfirm", { name: u.full_name }))) remove.mutate(undefined); }}>{t("admin.remove")}</Button>
      </Stack>
    </Modal>
  );
}

interface UserImportResult { new: number; updated: number; unchanged: number; passwords: number; invalid: number;
  errors: { row: number; code: string | null; errors: string[] }[]; credentials?: { name: string; email: string; temporary_password: string }[] }

/** Many users at once from Excel; temporary passwords of new people are shown once, to hand out. */
function UserImport({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<UserImportResult | null>(null);
  const [done, setDone] = useState<UserImportResult | null>(null);
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const close = () => { setFile(null); setRes(null); setDone(null); onClose(); };
  const preview = useMut(() => api<UserImportResult>("POST", "/users/import?apply=false", fd()), { success: false, onDone: setRes });
  const commit = useMut(() => api<UserImportResult>("POST", "/users/import?apply=true", fd()), { onDone: setDone });
  const saveCsv = () => {
    const lines = [["name", "email", "temporary_password"], ...(done?.credentials ?? []).map((c) => [c.name, c.email, c.temporary_password])];
    const csv = "\ufeff" + lines.map((l) => l.map((v) => `"${v.replace(/"/g, '""')}"`).join(",")).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = "new_passwords.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <Modal opened={opened} onClose={close} title={t("admin.importUsers")} size="lg">
      {done ? (
        <Stack>
          <Alert color="teal">{t("admin.importDone", { n: done.new, u: done.updated })}</Alert>
          {(done.credentials ?? []).length > 0 && <>
            <Alert color="orange">{t("admin.passwordsOnce")}</Alert>
            <DataTable rows={done.credentials} rowKey={(c) => c.email} columns={[
              { key: "n", label: t("common.name"), render: (c) => c.name }, { key: "e", label: t("common.email"), render: (c) => c.email },
              { key: "p", label: t("common.password"), render: (c) => <Code>{c.temporary_password}</Code> }]} />
            <Button variant="light" w="fit-content" onClick={saveCsv}>{t("admin.savePasswords")}</Button>
          </>}
          <Button onClick={close}>{t("common.close")}</Button>
        </Stack>
      ) : (
        <Stack>
          <Text size="sm" c="dimmed">{t("admin.importUsersHint")}</Text>
          <Button variant="light" w="fit-content" onClick={() => void download("/users/import/template.xlsx")}>{t("admin.usersTemplate")}</Button>
          <FileInput label={t("common.file")} accept=".xlsx,.csv" clearable value={file} onChange={(v) => { setFile(v); setRes(null); }} />
          <Group><Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
            <Button color="teal" disabled={!res || res.invalid > 0 || res.new + res.updated === 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button></Group>
          {res && <Alert color={res.invalid ? "orange" : "teal"} data-testid="users-preview">
            {t("admin.importPreview", { n: res.new, u: res.updated, s: res.unchanged, p: res.passwords })} · {res.invalid} {t("asset.invalid")}
            {res.errors.slice(0, 30).map((e, i) => <div key={i}>Row {e.row} {e.code ?? ""}: {e.errors.join("; ")}</div>)}
          </Alert>}
        </Stack>
      )}
    </Modal>
  );
}

/** Trade straight in the users table: pick from the list (Machinist, Welder …) or type one; saved when you leave the box. */
function TradeCell({ m }: { m: Member }) {
  const { t } = useTranslation();
  const trades = useQ<string[]>("/trades");
  const [v, setV] = useState(m.user.trade ?? "");
  const save = useMut((trade: string) => patch(`/users/${m.user.id}`, { trade: trade.trim() || null }), { success: false });
  const commit = (x: string) => { if (x.trim() !== (m.user.trade ?? "")) save.mutate(x); };
  return <Autocomplete size="xs" w={140} placeholder={t("trade.placeholder")} data={trades.data ?? []} value={v} limit={30}
    onChange={setV} onOptionSubmit={(x) => { setV(x); commit(x); }} onBlur={() => commit(v)} aria-label="trade" />;
}

function Users() {
  const { t } = useTranslation();
  const users = useQ<Member[]>("/users");
  const roles = useQ<{ code: string; name: string }[]>("/roles");
  const [imp, setImp] = useState(false);
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<Member | null>(null);
  const [f, setF] = useState({ email: "", full_name: "", password: "", role: "technician", department_ids: [] as string[], trade: "", employee_no: "", hourly_rate: "" as number | string });
  const create = useMut(() => post("/users", { ...f, trade: f.trade || null, employee_no: f.employee_no || null, hourly_rate: f.hourly_rate === "" ? null : Number(f.hourly_rate) }), { onDone: () => setOpen(false) });
  const toggle = useMut((m: Member) => patch(`/users/${m.user.id}`, { is_active: !m.is_active }));
  const setRole = useMut((a: { id: string; role: string }) => patch(`/users/${a.id}`, { role: a.role }));
  const setDept = useMut((a: { id: string; depts: string[] }) => patch(`/users/${a.id}`, { department_ids: a.depts }));
  const setSummary = useMut((m: Member) => patch(`/users/${m.user.id}`, { daily_summary: !m.daily_summary }), { success: false });
  const roleOpts = (roles.data ?? []).map((r) => ({ value: r.code, label: r.name }));
  return (
    <>
      <UserImport opened={imp} onClose={() => setImp(false)} />
      <Group mb="sm" align="start"><Button onClick={() => setOpen(true)} style={{ flexShrink: 0 }}>{t("admin.newUser")}</Button>
        <Button variant="light" onClick={() => setImp(true)} style={{ flexShrink: 0 }}>{t("admin.importUsers")}</Button><Text size="xs" c="dimmed" maw={760}>{t("admin.deptHint")}</Text></Group>
      <DataTable rows={users.data} rowKey={(m) => m.user.id} columns={[
        { key: "n", label: t("common.name"), render: (m) => <div style={{ minWidth: 170 }}>
          <Text size="sm" fw={500}>{m.user.full_name}</Text><Text size="xs" c="dimmed">{m.user.email}</Text>
          <Button size="compact-xs" variant="light" mt={4} onClick={() => setEdit(m)}>{t("common.edit")}</Button></div> },
        { key: "r", label: t("common.role"), render: (m) => <Select size="xs" w={190} data={roleOpts} value={m.role_code} onChange={(v) => v && setRole.mutate({ id: m.user.id, role: v })} /> },
        { key: "d", label: t("admin.departments"), render: (m) => <div style={{ width: 190 }}><DeptMultiSelect label="" compact value={deptIds(m)}
          onChange={(v) => setDept.mutate({ id: m.user.id, depts: v })} placeholder={t("admin.allDepts")} /></div> },
        { key: "t", label: t("trade.label"), render: (m) => <TradeCell key={`${m.user.id}:${m.user.trade ?? ""}`} m={m} /> },
        { key: "a", label: t("common.active"), render: (m) => <Switch checked={m.is_active} onChange={() => toggle.mutate(m)} aria-label="active" /> },
        { key: "s", label: t("admin.dsColumn"), render: (m) => <Switch checked={!!m.daily_summary} onChange={() => setSummary.mutate(m)} aria-label="daily summary" /> }]} />
      {edit && <EditUser key={edit.user.id} m={edit} roleOpts={roleOpts} onClose={() => setEdit(null)} />}
      <Modal opened={open} onClose={() => setOpen(false)} title={t("admin.newUser")}>
        <Stack>
          <TextInput label={t("common.email")} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.currentTarget.value })} />
          <TextInput label={t("common.password")} type="password" description="≥ 12 characters, 3 of: lower, upper, digit, symbol" value={f.password} onChange={(e) => setF({ ...f, password: e.currentTarget.value })} />
          <Select label={t("common.role")} data={roleOpts} value={f.role} onChange={(v) => setF({ ...f, role: v ?? "technician" })} />
          <DeptMultiSelect value={f.department_ids} onChange={(v) => setF({ ...f, department_ids: v })} label={t("admin.departments")} placeholder={t("admin.allDepts")} />
          <SimpleGrid cols={3}><TradeInput value={f.trade} onChange={(v) => setF({ ...f, trade: v })} />
            <TextInput label="Employee #" value={f.employee_no} onChange={(e) => setF({ ...f, employee_no: e.currentTarget.value })} />
            <NumberInput label="Rate/h" min={0} value={f.hourly_rate} onChange={(v) => setF({ ...f, hourly_rate: v })} /></SimpleGrid>
          <Button disabled={!f.email || !f.full_name || f.password.length < 12} loading={create.isPending} onClick={() => create.mutate(undefined)}>{t("common.create")}</Button>
        </Stack>
      </Modal>
    </>
  );
}

// General types for any industry, then the paper-mill areas already in use.
const DEPT_TYPES = [
  { group: "General", items: ["PRODUCTION", "MAINTENANCE", "UTILITIES", "FACILITIES", "QUALITY", "WAREHOUSE", "OTHER"].map((v) => ({ value: v, label: v.charAt(0) + v.slice(1).toLowerCase() })) },
  { group: "Paper mill", items: ["PM", "SP", "FH", "WWTP", "EAI", "UTIL"] },
];

function EditDept({ d, onClose }: { d: Department; onClose: () => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ code: d.code, name: d.name, name_ar: d.name_ar ?? "", type: d.type, is_active: d.is_active });
  const save = useMut(() => patch(`/departments/${d.id}`, { ...f, name_ar: f.name_ar || null }), { onDone: onClose });
  return (
    <Modal opened onClose={onClose} title={`${t("reorg.editTitle")}: ${d.code}`}>
      <Stack>
        <TextInput label={t("common.code")} value={f.code} onChange={(e) => setF({ ...f, code: e.currentTarget.value })} />
        <TextInput label={t("common.name")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
        <TextInput label="Arabic name" dir="rtl" value={f.name_ar} onChange={(e) => setF({ ...f, name_ar: e.currentTarget.value })} />
        <Select label={t("common.type")} data={DEPT_TYPES} value={f.type} onChange={(v) => setF({ ...f, type: v ?? f.type })} allowDeselect={false} />
        <Switch label={t("reorg.active")} checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.currentTarget.checked })} />
        <Button disabled={!f.code || !f.name} loading={save.isPending} onClick={() => save.mutate(undefined)}>{t("common.save")}</Button>
      </Stack>
    </Modal>
  );
}

interface MoveRes { lines: string[]; moves: { code: string; name: string; becomes: string }[]; to: string; assets: number; work_orders: number; pm_plans: number; applied: boolean }
interface TopAsset { id: string; code: string; name: string; department_id: string; parent_id: string | null; level: string }

/** Move production lines or units (whole tree + work orders) to another department, e.g. WTP out of Utilities. */
function MoveAssets({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const top = useQ<Page<TopAsset>>("/assets", { levels: "production_line,unit", limit: 500 });
  const depts = useQ<Department[]>("/departments");
  const code = new Map((depts.data ?? []).map((d) => [d.id, d.code]));
  const items = top.data?.items ?? [];
  const byId = new Map(items.map((a) => [a.id, a]));
  const [ids, setIds] = useState<string[]>([]);
  const [to, setTo] = useState<string | null>(null);
  const [parent, setParent] = useState<string | null>(null);
  const [res, setRes] = useState<MoveRes | null>(null);
  const label = (a: TopAsset) => {
    const up = a.parent_id ? byId.get(a.parent_id) : undefined;
    return `${code.get(a.department_id) ?? "?"} · ${up ? `${up.code} › ` : ""}${a.code} — ${a.name}`;
  };
  const sorted = [...items].sort((a, b) => label(a).localeCompare(label(b)));
  const hasUnit = ids.some((i) => byId.get(i)?.level === "unit");
  const targetLines = items.filter((a) => a.level === "production_line" && a.department_id === to && !ids.includes(a.id));
  const run = useMut((apply: boolean) => post<MoveRes>("/departments/move-assets", { asset_ids: ids, to_department_id: to, parent_id: hasUnit ? parent : null, apply }),
    { success: false, onDone: (r) => setRes(r) });
  const reset = () => setRes(null);
  return (
    <Modal opened onClose={onClose} title={t("reorg.moveTitle")} size="lg">
      <Stack>
        <Text size="sm" c="dimmed">{t("reorg.moveHint")}</Text>
        <MultiSelect label={t("reorg.lines")} searchable value={ids} onChange={(v) => { setIds(v); reset(); }}
          data={sorted.map((a) => ({ value: a.id, label: label(a) }))} />
        <DeptSelect label={t("reorg.to")} value={to} onChange={(v) => { setTo(v); setParent(null); reset(); }} />
        {hasUnit && <Select label={t("reorg.parent")} description={t("reorg.parentHint")} clearable placeholder={t("reorg.ownLine")} value={parent}
          onChange={(v) => { setParent(v); reset(); }} data={targetLines.map((a) => ({ value: a.id, label: `${a.code} — ${a.name}` }))} />}
        {res && <Alert color={res.applied ? "teal" : "blue"}>
          {t("reorg.result", { a: res.assets, w: res.work_orders, p: res.pm_plans, to: res.to })}{res.applied && ` ${t("reorg.done")}`}
          {res.moves.map((m) => <div key={m.code}>{m.code}: {m.becomes === "line" ? t("reorg.becomesLine") : m.becomes}</div>)}
        </Alert>}
        <Group>
          <Button variant="light" disabled={!ids.length || !to} loading={run.isPending} onClick={() => run.mutate(false)}>{t("reorg.preview")}</Button>
          <Button color="orange" disabled={!res || res.applied} loading={run.isPending} onClick={() => run.mutate(true)}>{t("reorg.apply")}</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function Basics() {
  const { t } = useTranslation();
  const depts = useQ<Department[]>("/departments");
  const codes = useQ<FailureCode[]>("/failure-codes");
  const [d, setD] = useState({ code: "", name: "", name_ar: "", type: "PRODUCTION" });
  const [c, setC] = useState({ kind: "problem", code: "", description: "" });
  const addD = useMut(() => post("/departments", { ...d, name_ar: d.name_ar || null }));
  const addC = useMut(() => post("/failure-codes", c), { onDone: () => setC({ ...c, code: "", description: "" }) });
  const [fcImp, setFcImp] = useState(false);
  const [editD, setEditD] = useState<Department | null>(null);
  const [moving, setMoving] = useState(false);
  const [fcq, setFcq] = useState("");
  const shownCodes = (codes.data ?? []).filter((x) => !fcq || `${x.code} ${x.description} ${x.equipment_type ?? ""}`.toLowerCase().includes(fcq.toLowerCase()));
  return (
    <SimpleGrid cols={{ base: 1, md: 2 }}>
      <Stack>
        <Text fw={600}>{t("admin.departments")}</Text>
        <Group align="end" wrap="wrap"><TextInput label={t("common.code")} w={90} value={d.code} onChange={(e) => setD({ ...d, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={d.name} onChange={(e) => setD({ ...d, name: e.currentTarget.value })} />
          <Select label={t("common.type")} w={170} data={DEPT_TYPES} value={d.type} onChange={(v) => setD({ ...d, type: v ?? "OTHER" })} />
          <Button disabled={!d.code || !d.name} onClick={() => addD.mutate(undefined)}>{t("common.add")}</Button></Group>
        <Group><Button size="xs" variant="light" color="orange" onClick={() => setMoving(true)}>{t("reorg.move")}</Button></Group>
        <DataTable rows={depts.data} columns={[{ key: "c", label: t("common.code"), render: (x) => x.code }, { key: "n", label: t("common.name"), render: (x) => `${x.name}${x.name_ar ? ` / ${x.name_ar}` : ""}` },
          { key: "t", label: t("common.type"), render: (x) => x.type }, { key: "a", label: t("common.active"), render: (x) => (x.is_active ? "✓" : "—") },
          { key: "e", label: "", render: (x) => <Button size="xs" variant="light" onClick={() => setEditD(x)}>{t("reorg.edit")}</Button> }]} />
        {editD && <EditDept key={editD.id} d={editD} onClose={() => setEditD(null)} />}
        {moving && <MoveAssets onClose={() => setMoving(false)} />}
      </Stack>
      <Stack>
        <Group justify="space-between"><Text fw={600}>{t("admin.failureCodes")}</Text>
          <Button size="xs" variant="light" onClick={() => setFcImp(true)}>{t("fm.importTitle")}</Button></Group>
        <FailureCodeImport opened={fcImp} onClose={() => setFcImp(false)} />
        <Group align="end" wrap="wrap"><Select label={t("common.type")} w={120} data={["problem", "cause", "remedy"]} value={c.kind} onChange={(v) => setC({ ...c, kind: v ?? "problem" })} />
          <TextInput label={t("common.code")} w={90} value={c.code} onChange={(e) => setC({ ...c, code: e.currentTarget.value })} />
          <TextInput label={t("common.description")} value={c.description} onChange={(e) => setC({ ...c, description: e.currentTarget.value })} />
          <Button disabled={!c.code || !c.description} onClick={() => addC.mutate(undefined)}>{t("common.add")}</Button></Group>
        <TextInput placeholder={t("common.search")} value={fcq} onChange={(e) => setFcq(e.currentTarget.value)} />
        <DataTable rows={shownCodes} columns={[{ key: "k", label: t("common.type"), render: (x) => x.kind }, { key: "c", label: t("common.code"), render: (x) => x.code },
          { key: "d", label: t("common.description"), render: (x) => x.description }, { key: "e", label: t("fm.equipmentType"), render: (x) => x.equipment_type },
          { key: "g", label: t("common.category"), render: (x) => x.category }]} />
      </Stack>
    </SimpleGrid>
  );
}

function Workflow() {
  const { t } = useTranslation();
  const q = useQ<Transition[]>("/workflow/transitions");
  const perms = useQ<Perm[]>("/permissions");
  const opts = (perms.data ?? []).map((p) => ({ value: p.code, label: `${p.code} — ${p.description}` }));
  const upd = useMut((a: { id: string; body: object }) => patch(`/workflow/transitions/${a.id}`, a.body));
  return <Stack>
    <Text size="sm" c="dimmed">{t("roles.workflowHint")}</Text>
    <DataTable rows={q.data} columns={[
    { key: "f", label: t("common.from"), render: (x) => <StatusBadge value={x.from_status} /> }, { key: "t", label: t("common.to"), render: (x) => <StatusBadge value={x.to_status} /> },
    { key: "p", label: t("admin.permission"), render: (x) => <Select size="xs" w={360} searchable allowDeselect={false} data={opts.length ? opts : [{ value: x.permission, label: x.permission }]}
      value={x.permission} onChange={(v) => v && v !== x.permission && upd.mutate({ id: x.id, body: { permission: v } })} /> },
    { key: "a", label: t("common.active"), render: (x) => <Switch checked={x.is_active} onChange={() => upd.mutate({ id: x.id, body: { is_active: !x.is_active } })} /> }]} />
  </Stack>;
}

interface Perm { code: string; description: string; group: string }
interface RoleRow { code: string; name: string; builtin: boolean; customized: boolean; locked: boolean; members: number; permissions: string[] }
const GROUPS: Record<string, string> = { plant: "Administration", user: "Administration", audit: "Administration", asset: "Assets", request: "Work requests",
  wo: "Work orders", pm: "PM", lube: "Lubrication", pdm: "PdM", shift: "Shifts", handover: "Shifts", inventory: "Inventory", purchase: "Inventory",
  shutdown: "Shutdowns", kpi: "KPIs & reports", report: "KPIs & reports", attachment: "Attachments" };

/** What each role may do. Only a System Administrator changes it; the change applies to every plant at the next page load. */
function Roles() {
  const { t } = useTranslation();
  const { me } = useSession();
  const editable = !!me?.is_system_admin;
  const perms = useQ<Perm[]>("/permissions");
  const roles = useQ<RoleRow[]>("/roles/matrix");
  const [code, setCode] = useState<string | null>(null);
  const [draft, setDraft] = useState<string[] | null>(null);
  const [newRole, setNewRole] = useState<{ name: string; copy_from: string | null } | null>(null);
  const [rename, setRename] = useState<string | null>(null);
  const role = roles.data?.find((r) => r.code === code) ?? null;
  const cur = draft ?? role?.permissions ?? [];
  const pick = (c: string | null) => { setCode(c); setDraft(null); };
  const save = useMut(() => put(`/roles/${code}/permissions`, { permissions: cur }), { onDone: () => setDraft(null) });
  const reset = useMut(() => post(`/roles/${code}/reset`, {}), { onDone: () => setDraft(null) });
  const remove = useMut(() => del(`/roles/${code}`), { onDone: () => pick(null) });
  const create = useMut(() => post<{ code: string }>("/roles", newRole), { onDone: (r) => { setNewRole(null); pick(r.code); } });
  const ren = useMut(() => patch(`/roles/${code}`, { name: rename }), { onDone: () => setRename(null) });
  const groups = new Map<string, Perm[]>();
  for (const p of perms.data ?? []) { const g = GROUPS[p.group] ?? p.group; groups.set(g, [...(groups.get(g) ?? []), p]); }
  const has = new Set(cur);
  const flip = (c: string) => setDraft(has.has(c) ? cur.filter((x) => x !== c) : [...cur, c]);
  const roleOpts = (roles.data ?? []).map((r) => ({ value: r.code, label: `${r.name} (${r.members})` }));
  const dirty = draft !== null;
  return (
    <Stack>
      <Alert color="blue">{editable ? t("roles.hint") : t("roles.readOnly")}</Alert>
      <Group align="end">
        <Select label={t("common.role")} w={340} searchable data={roleOpts} value={code} onChange={pick} placeholder={t("roles.pick")} />
        {editable && <Button variant="light" onClick={() => setNewRole({ name: "", copy_from: code })}>{t("roles.new")}</Button>}
        {editable && role && !role.locked && <Button variant="default" onClick={() => setRename(role.name)}>{t("roles.rename")}</Button>}
        {editable && role?.builtin && role.customized && !role.locked && <Button variant="default" loading={reset.isPending} onClick={() => reset.mutate(undefined)}>{t("roles.reset")}</Button>}
        {editable && role && !role.builtin && <Button color="red" variant="light" disabled={role.members > 0} title={role.members > 0 ? t("roles.inUse") : undefined}
          loading={remove.isPending} onClick={() => remove.mutate(undefined)}>{t("common.delete")}</Button>}
      </Group>
      {role && <Group gap="xs">
        <Badge variant="light" color={role.builtin ? (role.customized ? "orange" : "gray") : "violet"}>{t(role.builtin ? (role.customized ? "roles.kindEdited" : "roles.kindDefault") : "roles.kindCustom")}</Badge>
        <Text size="sm" c="dimmed">{t("roles.members", { n: role.members })} · {t("roles.count", { n: cur.length, total: perms.data?.length ?? 0 })}</Text>
      </Group>}
      {role?.locked && <Alert color="gray">{t("roles.locked")}</Alert>}
      {role && <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
        {[...groups.entries()].map(([g, ps]) => (
          <Stack key={g} gap={4} p="sm" style={{ border: "1px solid var(--mantine-color-gray-3)", borderRadius: 8 }}>
            <Group justify="space-between"><Text fw={600}>{g}</Text>
              {editable && !role.locked && <Checkbox size="xs" label={t("roles.all")} checked={ps.every((p) => has.has(p.code))}
                onChange={(e) => setDraft(e.currentTarget.checked ? [...new Set([...cur, ...ps.map((p) => p.code)])] : cur.filter((c) => !ps.some((p) => p.code === c)))} />}
            </Group>
            {ps.map((p) => <Checkbox key={p.code} disabled={!editable || role.locked} checked={has.has(p.code)} onChange={() => flip(p.code)}
              label={<><Code>{p.code}</Code> {p.description}</>} />)}
          </Stack>
        ))}
      </SimpleGrid>}
      {editable && role && !role.locked && <Group><Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(undefined)}>{t("common.save")}</Button>
        {dirty && <Button variant="default" onClick={() => setDraft(null)}>{t("common.cancel")}</Button>}</Group>}
      <Modal opened={!!newRole} onClose={() => setNewRole(null)} title={t("roles.new")}>
        {newRole && <Stack>
          <TextInput label={t("common.name")} placeholder="Area Engineer" value={newRole.name} onChange={(e) => setNewRole({ ...newRole, name: e.currentTarget.value })} />
          <Select label={t("roles.copyFrom")} clearable data={roleOpts} value={newRole.copy_from} onChange={(v) => setNewRole({ ...newRole, copy_from: v })} />
          <Button disabled={newRole.name.trim().length < 2} loading={create.isPending} onClick={() => create.mutate(undefined)}>{t("common.create")}</Button>
        </Stack>}
      </Modal>
      <Modal opened={rename !== null} onClose={() => setRename(null)} title={t("roles.rename")}>
        <Stack><TextInput label={t("common.name")} value={rename ?? ""} onChange={(e) => setRename(e.currentTarget.value)} />
          <Button disabled={(rename ?? "").trim().length < 2} loading={ren.isPending} onClick={() => ren.mutate(undefined)}>{t("common.save")}</Button></Stack>
      </Modal>
    </Stack>
  );
}

/** A new, empty plant / mill in the same organization (System Administrators only). */
function NewPlant() {
  const { t } = useTranslation();
  const [f, setF] = useState({ code: "", name: "", timezone: "Asia/Riyadh", currency: "SAR", departments: "paper" });
  const [made, setMade] = useState<{ id: string; code: string; name: string } | null>(null);
  const create = useMut(() => post<{ id: string; code: string; name: string }>("/plants", f), { onDone: setMade });
  const open = (id: string) => { window.localStorage.setItem("cmms.plant", id); window.location.reload(); };
  return (
    <Stack maw={600} mt="xl" p="md" style={{ border: "1px solid var(--mantine-color-gray-3)", borderRadius: 8 }}>
      <Text fw={700}>{t("plants.new")}</Text>
      <Text size="sm" c="dimmed">{t("plants.hint")}</Text>
      <SimpleGrid cols={2}>
        <TextInput label={t("common.code")} placeholder="MILL2" value={f.code} onChange={(e) => setF({ ...f, code: e.currentTarget.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "") })} />
        <TextInput label={t("common.name")} placeholder="New Mill" value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
        <TextInput label={t("admin.timezone")} value={f.timezone} onChange={(e) => setF({ ...f, timezone: e.currentTarget.value })} />
        <TextInput label={t("admin.currency")} maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.currentTarget.value.toUpperCase() })} />
      </SimpleGrid>
      <SegmentedControl value={f.departments} onChange={(v) => setF({ ...f, departments: v })} data={[
        { value: "paper", label: t("plants.deptPaper") }, { value: "general", label: t("plants.deptGeneral") }, { value: "none", label: t("plants.deptNone") }]} />
      <Group><Button disabled={!f.code || f.name.trim().length < 2} loading={create.isPending} onClick={() => create.mutate(undefined)}>{t("plants.create")}</Button></Group>
      {made && <Alert color="teal">{t("plants.done", { code: made.code })} <Button size="xs" ml="sm" onClick={() => open(made.id)}>{t("plants.open")}</Button></Alert>}
    </Stack>
  );
}

function PlantSettings() {
  const { t } = useTranslation();
  const q = useQ<PlantCfg>("/plant");
  const [f, setF] = useState<PlantCfg | null>(null);
  if (q.data && f === null) setF(q.data);
  const save = useMut(() => patch("/plant", { name: f?.name, timezone: f?.timezone, currency: f?.currency, allow_negative_stock: f?.allow_negative_stock, working_hours_per_day: f?.working_hours_per_day, settings: f?.settings }));
  if (!f) return null;
  return (
    <Stack maw={600}>
      <TextInput label={t("common.name")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
      <SimpleGrid cols={2}><TextInput label={t("admin.timezone")} value={f.timezone} onChange={(e) => setF({ ...f, timezone: e.currentTarget.value })} />
        <TextInput label={t("admin.currency")} maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.currentTarget.value.toUpperCase() })} />
        <NumberInput label="Working h/day" value={f.working_hours_per_day} onChange={(v) => setF({ ...f, working_hours_per_day: Number(v) })} /></SimpleGrid>
      <Switch label="Allow negative stock (not recommended)" checked={f.allow_negative_stock} onChange={(e) => setF({ ...f, allow_negative_stock: e.currentTarget.checked })} />
      <TextInput label="settings (JSON)" className="mono" defaultValue={JSON.stringify(f.settings)} onBlur={(e) => { try { setF({ ...f, settings: JSON.parse(e.currentTarget.value) as Record<string, unknown> }); } catch { /* keep previous */ } }} />
      <Group><Button onClick={() => save.mutate(undefined)}>{t("common.save")}</Button></Group>
    </Stack>
  );
}

interface SummaryCfg { enabled: boolean; send_time: string; days: number[]; working_days: number[]; timezone: string; email_configured: boolean;
  suppressed: string | null; recipients: { user_id: string; full_name: string; email: string; department_ids: string[] }[] }

const ALL_DAYS = [1, 2, 3, 4, 5, 6, 7];
// ISO weekday (1 = Monday) to a short local name; 2024-01-01 was a Monday.
const dayName = (d: number, lang: string) => new Date(Date.UTC(2024, 0, d)).toLocaleDateString(lang, { weekday: "short", timeZone: "UTC" });
const sameDays = (a: number[], b: number[]) => a.length === b.length && [...a].sort().every((v, i) => v === [...b].sort()[i]);

/** Summary e-mail: switch, frequency and send time for the plant; recipients are chosen in Users. Administrators only. */
function DailySummary() {
  const { t, i18n } = useTranslation();
  const q = useQ<SummaryCfg>("/daily-summary");
  const users = useQ<Member[]>("/users");
  const depts = useQ<Department[]>("/departments");
  const [f, setF] = useState<{ enabled: boolean; send_time: string; days: number[] } | null>(null);
  const [mode, setMode] = useState<string | null>(null);
  const [who, setWho] = useState<string | null>(null);
  const [pv, setPv] = useState<{ subject: string; body: string } | null>(null);
  if (q.data && f === null) {
    const d = q.data;
    setF({ enabled: d.enabled, send_time: d.send_time, days: d.days });
    setMode(sameDays(d.days, ALL_DAYS) ? "daily" : sameDays(d.days, d.working_days) ? "working" : d.days.length === 1 ? "weekly" : "custom");
  }
  const save = useMut(() => put("/daily-summary", f));
  const preview = useMut(() => api<{ subject: string; body: string }>("GET", `/daily-summary/preview${who ? `?user_id=${who}` : ""}`), { success: false, onDone: setPv });
  if (!f || !q.data) return null;
  const cfg = q.data;
  const deptCode = new Map((depts.data ?? []).map((d) => [d.id, d.code]));
  const pickMode = (m: string) => {
    setMode(m);
    if (m === "daily") setF({ ...f, days: ALL_DAYS });
    else if (m === "working") setF({ ...f, days: cfg.working_days });
    else if (m === "weekly") setF({ ...f, days: [f.days[0] ?? 7] });
  };
  return (
    <Stack maw={760}>
      {cfg.suppressed && <Alert color="red">{t("admin.dsSuppressed")}</Alert>}
      {!cfg.email_configured && !cfg.suppressed && <Alert color="orange">{t("admin.dsNoEmail")}</Alert>}
      <Text size="sm" c="dimmed">{t("admin.dsHint")}</Text>
      <Switch label={t("admin.dsEnabled")} checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.currentTarget.checked })} />
      <TextInput type="time" w={220} label={t("admin.dsTime")} description={cfg.timezone} value={f.send_time} onChange={(e) => setF({ ...f, send_time: e.currentTarget.value })} />
      <Stack gap={6}>
        <Text size="sm" fw={500}>{t("admin.dsFrequency")}</Text>
        <SegmentedControl w="fit-content" value={mode ?? "daily"} onChange={pickMode} data={[
          { value: "daily", label: t("admin.dsDaily") }, { value: "working", label: t("admin.dsWorking") },
          { value: "weekly", label: t("admin.dsWeekly") }, { value: "custom", label: t("admin.dsCustom") }]} />
        {mode === "weekly" && <Select w={220} label={t("admin.dsDay")} allowDeselect={false} value={String(f.days[0] ?? 7)}
          data={ALL_DAYS.map((d) => ({ value: String(d), label: dayName(d, i18n.language) }))} onChange={(v) => v && setF({ ...f, days: [Number(v)] })} />}
        {mode === "custom" && <Checkbox.Group value={f.days.map(String)} onChange={(v) => setF({ ...f, days: v.map(Number) })}>
          <Group>{ALL_DAYS.map((d) => <Checkbox key={d} value={String(d)} label={dayName(d, i18n.language)} />)}</Group></Checkbox.Group>}
      </Stack>
      <Group><Button disabled={!f.send_time || f.days.length === 0} loading={save.isPending} onClick={() => save.mutate(undefined)}>{t("common.save")}</Button></Group>
      <Text fw={600} mt="md">{t("admin.dsRecipients")} ({cfg.recipients.length})</Text>
      {cfg.recipients.length === 0 ? <Text size="sm" c="dimmed">{t("admin.dsNone")}</Text> :
        <DataTable rows={cfg.recipients} rowKey={(r) => r.user_id} columns={[
          { key: "n", label: t("common.name"), render: (r) => r.full_name }, { key: "e", label: t("common.email"), render: (r) => r.email },
          { key: "d", label: t("admin.departments"), render: (r) => r.department_ids.length ? r.department_ids.map((d) => deptCode.get(d) ?? "?").join(", ") : t("admin.allDepts") }]} />}
      <Group align="end" mt="md">
        <Select w={280} label={t("admin.dsPreviewFor")} clearable searchable value={who} onChange={setWho}
          data={(users.data ?? []).map((m) => ({ value: m.user.id, label: m.user.full_name }))} />
        <Button variant="light" loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("admin.dsPreview")}</Button>
      </Group>
      <Modal opened={!!pv} onClose={() => setPv(null)} title={pv?.subject} size="xl">
        <Code block style={{ whiteSpace: "pre-wrap" }}>{pv?.body}</Code>
      </Modal>
    </Stack>
  );
}

function Tokens() {
  const { t } = useTranslation();
  const q = useQ<{ id: string; name: string; revoked_at: string | null; last_used_at: string | null }[]>("/integration-tokens");
  const [name, setName] = useState("");
  const [tok, setTok] = useState<string | null>(null);
  const create = useMut(() => post<{ token: string }>("/integration-tokens", { name }), { onDone: (r) => setTok(r.token) });
  const revoke = useMut((id: string) => del(`/integration-tokens/${id}`));
  return (
    <Stack>
      <Text size="sm" c="dimmed">Write-only credential for the industrial data gateway (OPC UA / MQTT / SCADA historian bridge). It can only post readings; it cannot read CMMS data or send commands.</Text>
      <Group align="end"><TextInput label={t("common.name")} value={name} onChange={(e) => setName(e.currentTarget.value)} /><Button disabled={!name} onClick={() => create.mutate(undefined)}>{t("common.create")}</Button></Group>
      {tok && <Alert color="yellow" title={t("admin.tokenNote")}><Code block>{tok}</Code></Alert>}
      <DataTable rows={q.data} columns={[{ key: "n", label: t("common.name"), render: (x) => x.name }, { key: "u", label: "Last used", render: (x) => fmtDate(x.last_used_at, undefined, true) },
        { key: "r", label: t("common.status"), render: (x) => (x.revoked_at ? "revoked" : <Button size="xs" color="red" variant="light" onClick={() => revoke.mutate(x.id)}>Revoke</Button>) }]} />
    </Stack>
  );
}

function AuditLog() {
  const { t } = useTranslation();
  const [offset, setOffset] = useState(0);
  const [action, setAction] = useState("");
  const q = useQ<Page<Audit>>("/audit-logs", { limit: 50, offset, action });
  const users = useQ<Member[]>("/users");
  const umap = new Map((users.data ?? []).map((m) => [m.user.id, m.user.full_name]));
  return (
    <>
      <TextInput mb="sm" w={240} placeholder={`${t("admin.action")} (e.g. wo.)`} value={action} onChange={(e) => setAction(e.currentTarget.value)} />
      <DataTable rows={q.data?.items} rowKey={(a) => String(a.id)} columns={[{ key: "t", label: t("common.date"), render: (a) => fmtDate(a.at, undefined, true) },
        { key: "u", label: t("common.user"), render: (a) => (a.user_id ? umap.get(a.user_id) ?? a.user_id.slice(0, 8) : "system") }, { key: "a", label: t("admin.action"), render: (a) => a.action },
        { key: "e", label: "Entity", render: (a) => `${a.entity_type ?? ""} ${a.entity_id?.slice(0, 8) ?? ""}` }, { key: "d", label: t("common.details"), render: (a) => <Text size="xs" className="mono" lineClamp={2}>{JSON.stringify(a.data)}</Text> }]} />
      <Pager page={q.data} setPage={(p) => setOffset((p - 1) * 50)} />
    </>
  );
}

function Jobs() {
  const q = useQ<Job[]>("/system/jobs");
  const ob = useQ<Record<string, number>>("/system/email-outbox");
  return (
    <Stack>
      <Text size="sm">Email outbox: <span className="mono">{JSON.stringify(ob.data ?? {})}</span> (status &quot;disabled&quot; = no SMTP provider configured)</Text>
      <DataTable rows={q.data} columns={[{ key: "j", label: "Job", render: (x) => x.job }, { key: "s", label: "Status", render: (x) => <StatusBadge value={x.status === "success" ? "done" : x.status === "failed" ? "critical" : "pending"}>{x.status}</StatusBadge> },
        { key: "t", label: "Started", render: (x) => fmtDate(x.started_at, undefined, true) }, { key: "d", label: "Details", render: (x) => <Text size="xs" className="mono" lineClamp={2}>{x.error ?? JSON.stringify(x.details)}</Text> }]} />
    </Stack>
  );
}

function HistoryImports() {
  const { t } = useTranslation();
  const [open, setOpen] = useState<"wo_history" | "parts_history" | null>(null);
  return (
    <Stack maw={700} gap="xs">
      <Text size="sm" c="dimmed">{t("planImport.historyHelp")}</Text>
      <Group>
        <Button variant="light" onClick={() => setOpen("wo_history")}>{t("planImport.woHistory")}</Button>
        <Button variant="light" onClick={() => setOpen("parts_history")}>{t("planImport.partsHistory")}</Button>
      </Group>
      <PlanImport kind="wo_history" title={t("planImport.woHistory")} opened={open === "wo_history"} onClose={() => setOpen(null)}
        countLabel={t("planImport.breakdowns")} help={t("planImport.historyHelp")} />
      <PlanImport kind="parts_history" title={t("planImport.partsHistory")} opened={open === "parts_history"} onClose={() => setOpen(null)}
        countLabel={t("planImport.matchedParts")} help={t("planImport.historyHelp")} />
    </Stack>
  );
}

export default function AdminPage() {
  const { t } = useTranslation();
  const { me, can } = useSession();
  return (
    <Guard perm="plant.admin">
      <PageHeader title={t("nav.admin")} />
      <Tabs defaultValue="users" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="users">{t("admin.users")}</Tabs.Tab><Tabs.Tab value="basics">{t("admin.departments")} / {t("admin.failureCodes")}</Tabs.Tab>
          {can("user.manage") && <Tabs.Tab value="roles">{t("roles.tab")}</Tabs.Tab>}<Tabs.Tab value="workflow">{t("admin.workflow")}</Tabs.Tab><Tabs.Tab value="plant">{t("admin.plant")}</Tabs.Tab><Tabs.Tab value="summary">{t("admin.dsTab")}</Tabs.Tab><Tabs.Tab value="import">{t("common.import")}</Tabs.Tab>
          <Tabs.Tab value="tokens">{t("admin.tokens")}</Tabs.Tab><Tabs.Tab value="audit">{t("admin.audit")}</Tabs.Tab><Tabs.Tab value="jobs">{t("admin.jobs")}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="users" pt="md"><Users /></Tabs.Panel>
        <Tabs.Panel value="basics" pt="md"><Basics /></Tabs.Panel>
        <Tabs.Panel value="roles" pt="md"><Roles /></Tabs.Panel>
        <Tabs.Panel value="workflow" pt="md"><Workflow /></Tabs.Panel>
        <Tabs.Panel value="plant" pt="md"><PlantSettings />{me?.is_system_admin && <NewPlant />}</Tabs.Panel>
        <Tabs.Panel value="summary" pt="md"><DailySummary /></Tabs.Panel>
        <Tabs.Panel value="import" pt="md"><Stack><HistoryImports /><PartsImport /></Stack></Tabs.Panel>
        <Tabs.Panel value="tokens" pt="md"><Tokens /></Tabs.Panel>
        <Tabs.Panel value="audit" pt="md"><AuditLog /></Tabs.Panel>
        <Tabs.Panel value="jobs" pt="md"><Jobs /></Tabs.Panel>
      </Tabs>
    </Guard>
  );
}
