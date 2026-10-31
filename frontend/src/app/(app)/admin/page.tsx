"use client";

import { Alert, Button, Code, FileInput, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Switch, Tabs, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { FailureCodeImport } from "@/components/FailureModes";
import { PlanImport } from "@/components/PlanImport";
import { DataTable, DeptSelect, PageHeader, Pager, StatusBadge } from "@/components/ui";
import { api, del, download, patch, post } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import type { Department, FailureCode, Member, Page } from "@/lib/types";

interface Transition { id: string; from_status: string; to_status: string; permission: string; is_active: boolean }
interface PlantCfg { id: string; code: string; name: string; timezone: string; currency: string; allow_negative_stock: boolean; working_hours_per_day: number; working_days: number[]; settings: Record<string, unknown> }
interface Audit { id: number; at: string; user_id: string | null; action: string; entity_type: string | null; entity_id: string | null; data: Record<string, unknown>; ip: string | null }
interface Job { id: string; job: string; status: string; started_at: string; finished_at: string | null; error: string | null; details: Record<string, unknown> }

function EditUser({ m, roleOpts, onClose }: { m: Member; roleOpts: { value: string; label: string }[]; onClose: () => void }) {
  const { t } = useTranslation();
  const u = m.user;
  const [f, setF] = useState({ email: u.email, full_name: u.full_name, employee_no: u.employee_no ?? "", trade: u.trade ?? "",
    hourly_rate: (u.hourly_rate ?? "") as number | string, role: m.role_code, department_id: m.department_id });
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
        <DeptSelect clearable value={f.department_id} onChange={(v) => setF({ ...f, department_id: v })} label={`${t("common.department")} (${t("common.optional")})`} />
        <SimpleGrid cols={3}><TextInput label="Trade" value={f.trade} onChange={(e) => setF({ ...f, trade: e.currentTarget.value })} />
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

function Users() {
  const { t } = useTranslation();
  const users = useQ<Member[]>("/users");
  const roles = useQ<{ code: string; name: string }[]>("/roles");
  const [imp, setImp] = useState(false);
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<Member | null>(null);
  const [f, setF] = useState({ email: "", full_name: "", password: "", role: "technician", department_id: null as string | null, trade: "", employee_no: "", hourly_rate: "" as number | string });
  const create = useMut(() => post("/users", { ...f, trade: f.trade || null, employee_no: f.employee_no || null, hourly_rate: f.hourly_rate === "" ? null : Number(f.hourly_rate) }), { onDone: () => setOpen(false) });
  const toggle = useMut((m: Member) => patch(`/users/${m.user.id}`, { is_active: !m.is_active }));
  const setRole = useMut((a: { id: string; role: string }) => patch(`/users/${a.id}`, { role: a.role }));
  const setDept = useMut((a: { id: string; dept: string | null }) => patch(`/users/${a.id}`, { department_id: a.dept }));
  const roleOpts = (roles.data ?? []).map((r) => ({ value: r.code, label: r.name }));
  return (
    <>
      <UserImport opened={imp} onClose={() => setImp(false)} />
      <Group mb="sm" align="start" wrap="nowrap"><Button onClick={() => setOpen(true)}>{t("admin.newUser")}</Button>
        <Button variant="light" onClick={() => setImp(true)} style={{ flexShrink: 0 }}>{t("admin.importUsers")}</Button><Text size="xs" c="dimmed" maw={760}>{t("admin.deptHint")}</Text></Group>
      <DataTable rows={users.data} rowKey={(m) => m.user.id} columns={[
        { key: "n", label: t("common.name"), render: (m) => m.user.full_name }, { key: "e", label: t("common.email"), render: (m) => m.user.email },
        { key: "r", label: t("common.role"), render: (m) => <Select size="xs" w={220} data={roleOpts} value={m.role_code} onChange={(v) => v && setRole.mutate({ id: m.user.id, role: v })} /> },
        { key: "d", label: t("common.department"), render: (m) => <div style={{ width: 170 }}><DeptSelect label="" clearable value={m.department_id}
          onChange={(v) => setDept.mutate({ id: m.user.id, dept: v })} placeholder={t("admin.allDepts")} /></div> },
        { key: "t", label: "Trade", render: (m) => m.user.trade }, { key: "a", label: t("common.active"), render: (m) => <Switch checked={m.is_active} onChange={() => toggle.mutate(m)} aria-label="active" /> },
        { key: "x", label: "", render: (m) => <Button size="xs" variant="light" onClick={() => setEdit(m)}>{t("common.edit")}</Button> }]} />
      {edit && <EditUser key={edit.user.id} m={edit} roleOpts={roleOpts} onClose={() => setEdit(null)} />}
      <Modal opened={open} onClose={() => setOpen(false)} title={t("admin.newUser")}>
        <Stack>
          <TextInput label={t("common.email")} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.currentTarget.value })} />
          <TextInput label={t("common.password")} type="password" description="≥ 12 characters, 3 of: lower, upper, digit, symbol" value={f.password} onChange={(e) => setF({ ...f, password: e.currentTarget.value })} />
          <Select label={t("common.role")} data={roleOpts} value={f.role} onChange={(v) => setF({ ...f, role: v ?? "technician" })} />
          <DeptSelect clearable value={f.department_id} onChange={(v) => setF({ ...f, department_id: v })} label={`${t("common.department")} (${t("common.optional")})`} />
          <SimpleGrid cols={3}><TextInput label="Trade" value={f.trade} onChange={(e) => setF({ ...f, trade: e.currentTarget.value })} />
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

function Basics() {
  const { t } = useTranslation();
  const depts = useQ<Department[]>("/departments");
  const codes = useQ<FailureCode[]>("/failure-codes");
  const [d, setD] = useState({ code: "", name: "", name_ar: "", type: "PRODUCTION" });
  const [c, setC] = useState({ kind: "problem", code: "", description: "" });
  const addD = useMut(() => post("/departments", { ...d, name_ar: d.name_ar || null }));
  const addC = useMut(() => post("/failure-codes", c), { onDone: () => setC({ ...c, code: "", description: "" }) });
  const [fcImp, setFcImp] = useState(false);
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
        <DataTable rows={depts.data} columns={[{ key: "c", label: t("common.code"), render: (x) => x.code }, { key: "n", label: t("common.name"), render: (x) => `${x.name}${x.name_ar ? ` / ${x.name_ar}` : ""}` }, { key: "t", label: t("common.type"), render: (x) => x.type }]} />
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
  const upd = useMut((a: { id: string; body: object }) => patch(`/workflow/transitions/${a.id}`, a.body));
  return <DataTable rows={q.data} columns={[
    { key: "f", label: t("common.from"), render: (x) => <StatusBadge value={x.from_status} /> }, { key: "t", label: t("common.to"), render: (x) => <StatusBadge value={x.to_status} /> },
    { key: "p", label: t("admin.permission"), render: (x) => <TextInput size="xs" defaultValue={x.permission} onBlur={(e) => e.currentTarget.value !== x.permission && upd.mutate({ id: x.id, body: { permission: e.currentTarget.value } })} /> },
    { key: "a", label: t("common.active"), render: (x) => <Switch checked={x.is_active} onChange={() => upd.mutate({ id: x.id, body: { is_active: !x.is_active } })} /> }]} />;
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

function PartsImport() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<{ total: number; valid: number; invalid: number; errors: { row: number; errors: string[] }[]; warnings: { row: number; warnings: string[] }[] } | null>(null);
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const preview = useMut(() => api<NonNullable<typeof res>>("POST", "/imports/parts/preview", fd()), { success: false, onDone: setRes });
  const commit = useMut(() => api("POST", "/imports/parts/commit", fd()), { onDone: () => { setFile(null); setRes(null); } });
  return (
    <Stack maw={700}>
      <Button variant="subtle" w="fit-content" onClick={() => void download("/imports/templates/parts.xlsx")}>{t("asset.template")} (parts)</Button>
      <FileInput label={t("common.file")} accept=".csv,.xlsx" clearable value={file} onChange={(f) => { setFile(f); setRes(null); }} />
      <Group><Button disabled={!file} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
        <Button color="teal" disabled={!res || res.invalid > 0} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button></Group>
      {res && <Alert color={res.invalid ? "red" : "teal"}>{res.total} · {res.valid} {t("asset.valid")} · {res.invalid} {t("asset.invalid")}
        {res.errors.map((e) => <div key={e.row}>Row {e.row}: {e.errors.join("; ")}</div>)}
        {res.warnings.map((w) => <div key={`w${w.row}`}>⚠ Row {w.row}: {w.warnings.join("; ")}</div>)}</Alert>}
    </Stack>
  );
}

export default function AdminPage() {
  const { t } = useTranslation();
  return (
    <Guard perm="plant.admin">
      <PageHeader title={t("nav.admin")} />
      <Tabs defaultValue="users" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="users">{t("admin.users")}</Tabs.Tab><Tabs.Tab value="basics">{t("admin.departments")} / {t("admin.failureCodes")}</Tabs.Tab>
          <Tabs.Tab value="workflow">{t("admin.workflow")}</Tabs.Tab><Tabs.Tab value="plant">{t("admin.plant")}</Tabs.Tab><Tabs.Tab value="import">{t("common.import")}</Tabs.Tab>
          <Tabs.Tab value="tokens">{t("admin.tokens")}</Tabs.Tab><Tabs.Tab value="audit">{t("admin.audit")}</Tabs.Tab><Tabs.Tab value="jobs">{t("admin.jobs")}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="users" pt="md"><Users /></Tabs.Panel>
        <Tabs.Panel value="basics" pt="md"><Basics /></Tabs.Panel>
        <Tabs.Panel value="workflow" pt="md"><Workflow /></Tabs.Panel>
        <Tabs.Panel value="plant" pt="md"><PlantSettings /></Tabs.Panel>
        <Tabs.Panel value="import" pt="md"><Stack><HistoryImports /><PartsImport /></Stack></Tabs.Panel>
        <Tabs.Panel value="tokens" pt="md"><Tokens /></Tabs.Panel>
        <Tabs.Panel value="audit" pt="md"><AuditLog /></Tabs.Panel>
        <Tabs.Panel value="jobs" pt="md"><Jobs /></Tabs.Panel>
      </Tabs>
    </Guard>
  );
}
