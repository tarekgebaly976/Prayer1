"use client";

import { Alert, Button, FileInput, Group, Modal, Paper, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, TextInput, UnstyledButton } from "@mantine/core";
import { IconChevronDown, IconChevronRight } from "@tabler/icons-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { LabelPrint } from "@/components/LabelPrint";
import { DataTable, DeptSelect, PageHeader, Pager, StatusBadge } from "@/components/ui";
import { api, download, downloadPost, post } from "@/lib/api";
import { useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, AssetNode, Department, Page } from "@/lib/types";

const LEVELS = ["production_line", "unit", "assembly", "sub_assembly", "component"];

function Children({ query, depth }: { query: Record<string, string>; depth: number }) {
  const { t } = useTranslation();
  const [limit, setLimit] = useState(200);
  const q = useQ<Page<AssetNode>>("/assets/tree", { ...query, limit });
  return (
    <>
      {(q.data?.items ?? []).map((k) => <TreeNode key={k.id} node={k} depth={depth} />)}
      {q.data && q.data.total > q.data.items.length && (
        <Button variant="subtle" size="compact-xs" ms={depth * 18} onClick={() => setLimit(Math.min(limit + 200, 1000))} disabled={limit >= 1000}>
          {t("common.next")} ({q.data.items.length} / {q.data.total}){limit >= 1000 ? " — use search" : ""}
        </Button>
      )}
    </>
  );
}

function TreeNode({ node, depth }: { node: AssetNode; depth: number }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Group gap={4} ps={depth * 18} py={2} wrap="nowrap">
        {node.child_count > 0 ? (
          <UnstyledButton onClick={() => setOpen(!open)} aria-label="toggle">{open ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}</UnstyledButton>
        ) : <span style={{ width: 16 }} />}
        <Text component={Link} href={`/assets/${node.id}`} size="sm" className="mono">{node.code}</Text>
        <Text size="sm" truncate>{node.name}</Text>
        <StatusBadge value={node.criticality} size="xs" />
        {node.status !== "in_service" && <StatusBadge value={node.status} size="xs" />}
      </Group>
      {open && <Children query={{ parent_id: node.id }} depth={depth + 1} />}
    </>
  );
}

function DeptTree({ dept }: { dept: Department }) {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <UnstyledButton onClick={() => setOpen(!open)} py={4}>
        <Group gap={4}>{open ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}<Text fw={600}>{dept.code} — {i18n.language === "ar" && dept.name_ar ? dept.name_ar : dept.name}</Text></Group>
      </UnstyledButton>
      {open && <Children query={{ department_id: dept.id }} depth={1} />}
    </div>
  );
}

function NewAsset({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const router = useRouter();
  const [f, setF] = useState({ code: "", name: "", name_ar: "", department_id: null as string | null, parent_id: null as string | null, level: "production_line",
    criticality: "C", oem: "", model: "", serial_number: "", install_date: "", location: "", description: "" });
  const parents = useQ<Page<Asset>>(f.department_id ? "/assets" : null, { department_id: f.department_id, limit: 500 });
  const m = useMut(() => post<Asset>("/assets", { ...f, name_ar: f.name_ar || null, install_date: f.install_date || null, oem: f.oem || null, model: f.model || null,
    serial_number: f.serial_number || null, location: f.location || null, description: f.description || null }), { onDone: (a) => { onClose(); router.push(`/assets/${a.id}`); } });
  return (
    <Modal opened={opened} onClose={onClose} title={t("asset.new")} size="lg">
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t("common.code")} required value={f.code} onChange={(e) => setF({ ...f, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} required value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
          <TextInput label={`${t("common.name")} (AR)`} dir="rtl" value={f.name_ar} onChange={(e) => setF({ ...f, name_ar: e.currentTarget.value })} />
          <DeptSelect value={f.department_id} onChange={(v) => setF({ ...f, department_id: v, parent_id: null })} />
          <Select label={t("asset.level")} value={f.level} onChange={(v) => setF({ ...f, level: v ?? "production_line" })} allowDeselect={false} data={LEVELS.map((l) => ({ value: l, label: t(`level.${l}`) }))} />
          <Select label={t("asset.parent")} searchable clearable value={f.parent_id} onChange={(v) => setF({ ...f, parent_id: v })} disabled={f.level === "production_line"}
            data={(parents.data?.items ?? []).filter((a) => LEVELS.indexOf(a.level) < LEVELS.indexOf(f.level)).map((a) => ({ value: a.id, label: `${a.code} — ${a.name}` }))} />
          <Select label={t("common.criticality")} value={f.criticality} onChange={(v) => setF({ ...f, criticality: v ?? "C" })} data={["A", "B", "C"]} allowDeselect={false} />
          <TextInput label={t("asset.oem")} value={f.oem} onChange={(e) => setF({ ...f, oem: e.currentTarget.value })} />
          <TextInput label={t("asset.model")} value={f.model} onChange={(e) => setF({ ...f, model: e.currentTarget.value })} />
          <TextInput label={t("asset.serial")} value={f.serial_number} onChange={(e) => setF({ ...f, serial_number: e.currentTarget.value })} />
          <TextInput type="date" label={t("asset.installDate")} value={f.install_date} onChange={(e) => setF({ ...f, install_date: e.currentTarget.value })} />
          <TextInput label={t("common.location")} value={f.location} onChange={(e) => setF({ ...f, location: e.currentTarget.value })} />
        </SimpleGrid>
        <Button onClick={() => m.mutate(undefined)} loading={m.isPending} disabled={!f.code || !f.name || !f.department_id}>{t("common.create")}</Button>
      </Stack>
    </Modal>
  );
}

interface ImportResult { total: number; valid: number; invalid: number; errors: { row: number; code: string | null; errors: string[] }[] }

function ImportAssets({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<ImportResult | null>(null);
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const preview = useMut(() => api<ImportResult>("POST", "/imports/assets/preview", fd()), { success: false, onDone: setRes });
  // Start from an empty form every time, so a finished import never leaves its file selected for the next one.
  const close = () => { setFile(null); setRes(null); onClose(); };
  const commit = useMut(() => api<{ created: number }>("POST", "/imports/assets/commit", fd()), { onDone: close });
  const errorsCsv = () => downloadPost("/imports/assets/errors.csv", fd(), "asset_import_errors.csv");
  return (
    <Modal opened={opened} onClose={close} title={t("asset.importTitle")} size="lg">
      <Stack>
        <Button variant="subtle" onClick={() => void download("/imports/templates/assets.xlsx")}>{t("asset.template")}</Button>
        <FileInput label={t("common.file")} accept=".csv,.xlsx" clearable value={file} onChange={(f) => { setFile(f); setRes(null); }} />
        <Group>
          <Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
          <Button color="teal" disabled={!res || res.invalid > 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button>
        </Group>
        {res && (
          <>
            <Alert color={res.invalid ? "red" : "teal"}>{res.total} · {res.valid} {t("asset.valid")} · {res.invalid} {t("asset.invalid")}</Alert>
            {res.invalid > 0 && (
              <>
                <Button variant="light" size="xs" onClick={() => void errorsCsv()}>{t("asset.errorsReport")}</Button>
                <Table><Table.Tbody>{res.errors.slice(0, 100).map((e) => (
                  <Table.Tr key={e.row}><Table.Td>{e.row}</Table.Td><Table.Td>{e.code}</Table.Td><Table.Td>{e.errors.join("; ")}</Table.Td></Table.Tr>))}</Table.Tbody></Table>
              </>
            )}
          </>
        )}
      </Stack>
    </Modal>
  );
}

function Assets() {
  const { t } = useTranslation();
  const router = useRouter();
  const { can } = useSession();
  const [view, setView] = useState("tree");
  const [q, setQ] = useState("");
  const [crit, setCrit] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [newOpen, setNewOpen] = useState(false);
  const [impOpen, setImpOpen] = useState(false);
  const [labels, setLabels] = useState(false);
  const depts = useQ<Department[]>("/departments");
  const list = useQ<Page<Asset>>(view === "list" ? "/assets" : null, { q, criticality: crit, limit: 50, offset });
  return (
    <>
      <PageHeader title={t("nav.assets")} actions={<>
        {can("asset.edit") && <Button onClick={() => setNewOpen(true)}>{t("asset.new")}</Button>}
        {can("asset.import") && <Button variant="light" onClick={() => setImpOpen(true)}>{t("common.import")}</Button>}
        <Button variant="default" onClick={() => setLabels(true)}>{t("labels.button")}</Button>
        {can("report.export") && <Button variant="default" onClick={() => void download("/exports/assets.csv")}>{t("common.export")} CSV</Button>}
      </>}>
        <SegmentedControl value={view} onChange={setView} data={[{ value: "tree", label: t("asset.tree") }, { value: "list", label: t("asset.list") }]} w={240} />
      </PageHeader>
      <LabelPrint kind="assets" opened={labels} onClose={() => setLabels(false)} />
      {view === "tree" ? (
        <Paper withBorder p="md">{(depts.data ?? []).map((d) => <DeptTree key={d.id} dept={d} />)}</Paper>
      ) : (
        <>
          <Group mb="sm">
            <TextInput placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.currentTarget.value); setOffset(0); }} />
            <Select placeholder={t("common.criticality")} clearable data={["A", "B", "C"]} value={crit} onChange={setCrit} w={140} />
          </Group>
          <DataTable rows={list.data?.items} onRow={(a) => router.push(`/assets/${a.id}`)} columns={[
            { key: "c", label: t("common.code"), render: (a) => <span className="mono">{a.code}</span> },
            { key: "n", label: t("common.name"), render: (a) => a.name },
            { key: "l", label: t("asset.level"), render: (a) => t(`level.${a.level}`) },
            { key: "k", label: t("common.criticality"), render: (a) => <StatusBadge value={a.criticality} /> },
            { key: "s", label: t("common.status"), render: (a) => <StatusBadge value={a.status} /> },
            { key: "o", label: t("asset.oem"), render: (a) => `${a.oem ?? ""} ${a.model ?? ""}` },
          ]} />
          <Pager page={list.data} setPage={(p) => setOffset((p - 1) * 50)} />
        </>
      )}
      <NewAsset opened={newOpen} onClose={() => setNewOpen(false)} />
      <ImportAssets opened={impOpen} onClose={() => setImpOpen(false)} />
    </>
  );
}

export default function AssetsPage() {
  return <Guard perm="asset.view"><Assets /></Guard>;
}
