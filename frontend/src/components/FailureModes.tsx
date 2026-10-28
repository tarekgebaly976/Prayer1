"use client";

import { BarChart } from "@mantine/charts";
import { Alert, Button, Card, FileInput, Group, Modal, SegmentedControl, Stack, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, download } from "@/lib/api";
import { fmtDate, fmtNum, useMut, useQ } from "@/lib/hooks";
import { AssetPicker, DataTable } from "./ui";

interface CodePreview { new: number; updated: number; invalid: number; types: string[]; errors: { row: number; code: string | null; errors: string[] }[] }

/** Failure-code catalogue from Excel (kind, code, description, equipment_type, category): new codes are added, existing ones updated. */
export function FailureCodeImport({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<CodePreview | null>(null);
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const close = () => { setFile(null); setRes(null); onClose(); };
  const preview = useMut(() => api<CodePreview>("POST", "/failure-codes/import?apply=false", fd()), { success: false, onDone: setRes });
  const commit = useMut(() => api("POST", "/failure-codes/import?apply=true", fd()), { onDone: close });
  return (
    <Modal opened={opened} onClose={close} title={t("fm.importTitle")} size="lg">
      <Stack>
        <Text size="sm" c="dimmed">{t("fm.importHint")}</Text>
        <Button variant="light" w="fit-content" onClick={() => void download("/failure-codes/export.xlsx")}>{t("fm.download")}</Button>
        <FileInput label={t("common.file")} accept=".xlsx,.csv" clearable value={file} onChange={(v) => { setFile(v); setRes(null); }} />
        <Group><Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
          <Button color="teal" disabled={!res || res.invalid > 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button></Group>
        {res && <Alert color={res.invalid ? "orange" : "teal"} data-testid="fc-preview">
          {t("fm.newCodes", { n: res.new })} · {t("fm.updatedCodes", { n: res.updated })} · {res.invalid} {t("asset.invalid")}
          {res.types.length > 0 && <Text size="xs" mt={4}>{t("fm.types")}: {res.types.join(", ")}</Text>}
          {res.errors.slice(0, 30).map((e, i) => <div key={i}>Row {e.row} {e.code ?? ""}: {e.errors.join("; ")}</div>)}
        </Alert>}
      </Stack>
    </Modal>
  );
}

interface Classified { set: number; by_type: Record<string, number>; samples: Record<string, string[]>; unmatched: number }

/** Suggests an equipment type from each asset name (motor, pump, gearbox …) for assets without one. */
export function ClassifyAssets({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [res, setRes] = useState<Classified | null>(null);
  const close = () => { setRes(null); onClose(); };
  const preview = useMut(() => api<Classified>("POST", "/assets/equipment-types/classify?apply=false"), { success: false, onDone: setRes });
  const apply = useMut(() => api("POST", "/assets/equipment-types/classify?apply=true"), { onDone: close });
  return (
    <Modal opened={opened} onClose={close} title={t("fm.classifyTitle")} size="lg">
      <Stack>
        <Text size="sm" c="dimmed">{t("fm.classifyHint")}</Text>
        <Group><Button loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
          <Button color="teal" disabled={!res || res.set === 0} loading={apply.isPending} onClick={() => apply.mutate(undefined)}>{t("fm.applyTypes", { n: res?.set ?? 0 })}</Button></Group>
        {res && <Alert color="teal" data-testid="classify-preview">
          {Object.entries(res.by_type).map(([k, v]) => (
            <div key={k}><b>{k}: {v}</b> <Text span size="xs" c="dimmed">{(res.samples[k] ?? []).slice(0, 3).join(" · ")}</Text></div>))}
          <Text size="sm" mt={4}>{t("fm.unmatched", { n: res.unmatched })}</Text>
        </Alert>}
      </Stack>
    </Modal>
  );
}

interface ParetoRow { code: string | null; failure_mode: string; equipment_types: string[]; work_orders: number; downtime_hours: number; share_pct: number; cumulative_pct: number; last: string | null }

/** Top failure modes (Pareto) for KPI reviews and RCA: work orders per failure mode, with downtime. */
export function FailurePareto({ start, end }: { start: string; end: string }) {
  const { t } = useTranslation();
  const [by, setBy] = useState("mode");
  const [under, setUnder] = useState<string | null>(null);
  const q = useQ<{ rows: ParetoRow[]; total: number; closed_breakdowns_without_code: number }>("/kpis/failure-modes", { start, end, by, under });
  const rows = q.data?.rows ?? [];
  return (
    <Stack>
      <Group align="end" wrap="wrap">
        <SegmentedControl value={by} onChange={setBy} data={[{ value: "mode", label: t("fm.byMode") }, { value: "code", label: t("fm.byCode") }, { value: "symptom", label: t("fm.bySymptom") }]} />
        <div style={{ width: 340 }}><AssetPicker label={t("labels.under")} value={under} onChange={setUnder} clearable /></div>
      </Group>
      {q.data && q.data.closed_breakdowns_without_code > 0 && <Alert color="orange">{t("fm.missingCodes", { n: q.data.closed_breakdowns_without_code })}</Alert>}
      {rows.length > 0 && <Card withBorder><Text fw={600} mb="xs">{t("fm.top10")}</Text>
        <BarChart h={260} data={rows.slice(0, 10).map((r) => ({ mode: r.code ?? r.failure_mode, wos: r.work_orders }))} dataKey="mode"
          series={[{ name: "wos", label: t("nav.workOrders"), color: "red.6" }]} tickLine="none" xAxisProps={{ interval: 0, angle: -20, textAnchor: "end", height: 70 }} /></Card>}
      <DataTable rows={rows} columns={[
        ...(by !== "mode" ? [{ key: "c", label: t("common.code"), render: (r: ParetoRow) => <b>{r.code}</b> }] : []),
        { key: "m", label: t("fm.mode"), render: (r: ParetoRow) => r.failure_mode },
        { key: "e", label: t("fm.types"), render: (r: ParetoRow) => r.equipment_types.join(", ") },
        { key: "n", label: t("nav.workOrders"), render: (r: ParetoRow) => r.work_orders },
        { key: "d", label: t("wo.downtime"), render: (r: ParetoRow) => fmtNum(r.downtime_hours) },
        { key: "s", label: "%", render: (r: ParetoRow) => `${r.share_pct} (Σ ${r.cumulative_pct})` },
        { key: "l", label: t("fm.last"), render: (r: ParetoRow) => fmtDate(r.last) },
      ]} />
      <Text size="xs" c="dimmed">{t("fm.paretoNote")}</Text>
    </Stack>
  );
}

/** Equipment type field with the standard list plus types already used; free text is allowed. */
export function EquipmentTypeInput({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) {
  const { t } = useTranslation();
  const types = useQ<string[]>("/assets/equipment-types");
  return <TextInput label={t("fm.equipmentType")} list="equipment-types" value={value ?? ""} onChange={(e) => onChange(e.currentTarget.value || null)}
    rightSection={<datalist id="equipment-types">{(types.data ?? []).map((x) => <option key={x} value={x} />)}</datalist>} />;
}
