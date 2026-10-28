"use client";

import { LineChart } from "@mantine/charts";
import { Alert, Button, Checkbox, Group, Modal, NumberInput, Paper, Select, SimpleGrid, Stack, Tabs, Text, TextInput } from "@mantine/core";
import { useDebouncedValue, useMediaQuery } from "@mantine/hooks";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { NewAsset } from "@/components/NewAsset";
import { PlanImport } from "@/components/PlanImport";
import { AssetPicker, DataTable, PageHeader, Pager, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, fmtNum, useAssetCodes, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, Page } from "@/lib/types";

export interface MPoint { id: string; code: string; name: string; asset_id: string; technique: string; unit: string; baseline: number | null; warning_low: number | null;
  warning_high: number | null; alarm_low: number | null; alarm_high: number | null; last_status: string; last_value: number | null; last_reading_at: string | null; auto_create_wo: boolean }
export interface CAlert { id: string; point_id: string; asset_id: string; severity: string; status: string; message: string; defect_description: string | null;
  recommended_action: string | null; resolution: string | null; work_order_id: string | null; created_at: string }

const TECH = ["vibration", "temperature", "motor_current", "power", "oil_analysis", "thermography", "ultrasound", "alignment", "balancing", "pressure", "flow", "other"];

function Trend({ point }: { point: MPoint }) {
  const { t } = useTranslation();
  const { can } = useSession();
  const q = useQ<{ readings: { value: number; measured_at: string; status: string }[] }>(`/pdm/points/${point.id}/readings`, { limit: 500 });
  const [v, setV] = useState<number | string>("");
  const [res, setRes] = useState<string | null>(null);
  const add = useMut(() => post<{ status: string; message?: string }>(`/pdm/points/${point.id}/readings`, { value: Number(v) }), { success: false,
    onDone: (r) => { setRes(`${t(`status.${r.status}`)}${r.message ? ` — ${r.message}` : ""}`); setV(""); } });
  const data = (q.data?.readings ?? []).map((r) => ({ at: new Date(r.measured_at).toLocaleDateString(), value: Number(r.value) }));
  const refs = [
    point.warning_high !== null && { y: Number(point.warning_high), label: t("pdm.warnHigh"), color: "orange.6" },
    point.alarm_high !== null && { y: Number(point.alarm_high), label: t("pdm.alarmHigh"), color: "red.7" },
    point.warning_low !== null && { y: Number(point.warning_low), label: t("pdm.warnLow"), color: "orange.6" },
    point.alarm_low !== null && { y: Number(point.alarm_low), label: t("pdm.alarmLow"), color: "red.7" },
  ].filter(Boolean) as { y: number; label: string; color: string }[];
  return (
    <Stack>
      {can("pdm.record") && (
        <Group align="end">
          <NumberInput label={`${t("pdm.record")} (${point.unit})`} value={v} onChange={setV} w={180} data-testid="reading-input" />
          <Button disabled={v === ""} loading={add.isPending} onClick={() => add.mutate(undefined)}>{t("common.save")}</Button>
        </Group>
      )}
      {res && <Alert color={res.startsWith(t("status.normal")) ? "teal" : "orange"} data-testid="reading-result">{res}</Alert>}
      {data.length > 0 ? <LineChart h={260} data={data} dataKey="at" series={[{ name: "value", color: "indigo.6", label: point.unit }]} referenceLines={refs} curveType="linear" withDots />
        : <Text c="dimmed" size="sm">{t("common.noData")}</Text>}
    </Stack>
  );
}

function PdM() {
  const { t } = useTranslation();
  const sp = useSearchParams();
  const router = useRouter();
  const { can } = useSession();
  const [sel, setSel] = useState<string | null>(sp.get("point"));
  const [offset, setOffset] = useState(0);
  const [openOnly, setOpenOnly] = useState(true);
  const [add, setAdd] = useState(false);
  const [imp, setImp] = useState(false);
  const [f, setF] = useState({ code: "", name: "", asset_id: null as string | null, technique: "vibration", unit: "mm/s", warning_high: "" as number | string, alarm_high: "" as number | string,
    warning_low: "" as number | string, alarm_low: "" as number | string, auto_create_wo: false, external_tag: "", recommended_action: "" });
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search.trim(), 300);
  const [under, setUnder] = useState<string | null>(null);
  const [newAsset, setNewAsset] = useState(false);
  const points = useQ<MPoint[]>("/pdm/points", { q: q || undefined, under });
  const chosen = useQ<Asset>(f.asset_id ? `/assets/${f.asset_id}` : null);
  const alerts = useQ<Page<CAlert>>("/pdm/alerts", { open_only: openOnly, limit: 50, offset });
  const amap = useAssetCodes([...(points.data ?? []), ...(alerts.data?.items ?? [])].map((x) => x.asset_id));
  const pmap = new Map((points.data ?? []).map((p) => [p.id, p]));
  const n = (v: number | string) => (v === "" ? null : Number(v));
  const create = useMut(() => post("/pdm/points", { ...f, warning_high: n(f.warning_high), alarm_high: n(f.alarm_high), warning_low: n(f.warning_low), alarm_low: n(f.alarm_low),
    external_tag: f.external_tag || null, recommended_action: f.recommended_action || null }), { onDone: () => setAdd(false) });
  const point = sel ? pmap.get(sel) : undefined;
  // Side by side only on wide screens; on a phone (or a narrow window) the point opens in its own window.
  const wide = useMediaQuery("(min-width: 75em)", true);
  const detail = point ? <>
    <Text fw={600} mb={4}>{point.code} — {point.name}</Text>
    <Text size="xs" c="dimmed" mb="sm">{t("pdm.limits")}: W {fmtNum(point.warning_low)}/{fmtNum(point.warning_high)} · A {fmtNum(point.alarm_low)}/{fmtNum(point.alarm_high)} {point.unit}</Text>
    <Trend point={point} />
  </> : null;
  return (
    <>
      <PageHeader title={t("nav.pdm")} actions={can("pdm.manage") ? <>
        <Button onClick={() => setAdd(true)}>{t("pdm.newPoint")}</Button>
        <Button variant="light" onClick={() => setImp(true)}>{t("planImport.button")}</Button>
      </> : null}>
        <Text size="sm" c="dimmed">{t("pdm.ruleNote")}</Text>
      </PageHeader>
      <PlanImport kind="pdm_plans" title={t("planImport.pdm")} opened={imp} onClose={() => setImp(false)} />
      <Tabs defaultValue={sp.get("tab") ?? "points"}>
        <Tabs.List><Tabs.Tab value="points">{t("pdm.points")}</Tabs.Tab><Tabs.Tab value="alerts">{t("pdm.alerts")}</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="points" pt="md">
          <Group mb="sm" align="end">
            <TextInput label={t("common.search")} placeholder={t("pdm.searchHint")} value={search} onChange={(e) => setSearch(e.currentTarget.value)} w={260} />
            <div style={{ width: 340 }}><AssetPicker label={t("labels.under")} value={under} onChange={setUnder} clearable /></div>
          </Group>
          <SimpleGrid cols={wide && point ? 2 : 1}>
            <DataTable rows={points.data} onRow={(p) => setSel(p.id)} columns={[
              { key: "c", label: t("common.code"), render: (p) => <b>{p.code}</b> }, { key: "a", label: t("common.asset"), render: (p) => amap.get(p.asset_id) },
              { key: "t", label: t("pdm.technique"), render: (p) => p.technique }, { key: "v", label: t("pdm.lastValue"), render: (p) => `${fmtNum(p.last_value)} ${p.unit}` },
              { key: "s", label: t("common.status"), render: (p) => <StatusBadge value={p.last_status} /> }]} />
            {wide && detail ? <Paper withBorder p="md">{detail}</Paper> : null}
          </SimpleGrid>
        </Tabs.Panel>
        <Tabs.Panel value="alerts" pt="md">
          <Checkbox mb="sm" label={t("wo.openOnly")} checked={openOnly} onChange={(e) => setOpenOnly(e.currentTarget.checked)} />
          <DataTable rows={alerts.data?.items} onRow={(a) => router.push(`/pdm/alerts/${a.id}`)} columns={[
            { key: "d", label: t("common.createdAt"), render: (a) => fmtDate(a.created_at, undefined, true) },
            { key: "p", label: t("pdm.points"), render: (a) => pmap.get(a.point_id)?.code }, { key: "a", label: t("common.asset"), render: (a) => amap.get(a.asset_id) },
            { key: "sv", label: "Severity", render: (a) => <StatusBadge value={a.severity} /> }, { key: "s", label: t("common.status"), render: (a) => <StatusBadge value={a.status} /> },
            { key: "m", label: t("common.description"), render: (a) => a.message }]} />
          <Pager page={alerts.data} setPage={(p) => setOffset((p - 1) * 50)} />
        </Tabs.Panel>
      </Tabs>
      <Modal opened={!wide && !!point} onClose={() => setSel(null)} title={t("pdm.points")} fullScreen>{detail}</Modal>
      <Modal opened={add} onClose={() => setAdd(false)} title={t("pdm.newPoint")} size="lg">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Stack gap={4}>
            <AssetPicker value={f.asset_id} onChange={(v) => setF({ ...f, asset_id: v })} required />
            {can("asset.edit") && <Button variant="subtle" size="compact-xs" w="fit-content" onClick={() => setNewAsset(true)}>
              {f.asset_id ? t("pdm.addAssetUnder") : t("pdm.addAsset")}</Button>}
          </Stack>
          <Select label={t("pdm.technique")} data={TECH} value={f.technique} onChange={(v) => setF({ ...f, technique: v ?? "other" })} />
          <TextInput label={t("common.code")} value={f.code} onChange={(e) => setF({ ...f, code: e.currentTarget.value })}
            placeholder={chosen.data ? `${t("pdm.auto")}: ${chosen.data.code}-CM..` : t("pdm.auto")} description={t("pdm.codeHint")} />
          <TextInput label={t("common.name")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })}
            placeholder={chosen.data ? `${chosen.data.name} – ${f.technique.replace("_", " ")}` : t("pdm.auto")} />
          <TextInput label={t("common.unit")} value={f.unit} onChange={(e) => setF({ ...f, unit: e.currentTarget.value })} />
          <TextInput label="OPC UA / MQTT tag" value={f.external_tag} onChange={(e) => setF({ ...f, external_tag: e.currentTarget.value })} />
          <NumberInput label={t("pdm.warnHigh")} value={f.warning_high} onChange={(v) => setF({ ...f, warning_high: v })} />
          <NumberInput label={t("pdm.alarmHigh")} value={f.alarm_high} onChange={(v) => setF({ ...f, alarm_high: v })} />
          <NumberInput label={t("pdm.warnLow")} value={f.warning_low} onChange={(v) => setF({ ...f, warning_low: v })} />
          <NumberInput label={t("pdm.alarmLow")} value={f.alarm_low} onChange={(v) => setF({ ...f, alarm_low: v })} />
        </SimpleGrid>
        <TextInput mt="sm" label="Recommended action" value={f.recommended_action} onChange={(e) => setF({ ...f, recommended_action: e.currentTarget.value })} />
        <Checkbox mt="sm" label="Auto-create WO on critical" checked={f.auto_create_wo} onChange={(e) => setF({ ...f, auto_create_wo: e.currentTarget.checked })} />
        <Button mt="md" onClick={() => create.mutate(undefined)} disabled={!f.asset_id}>{t("common.create")}</Button>
      </Modal>
      {newAsset && <NewAsset opened onClose={() => setNewAsset(false)} parent={chosen.data ?? null} onCreated={(a) => setF({ ...f, asset_id: a.id })} />}
    </>
  );
}

export default function PdMPage() {
  return <Guard perm="pdm.view"><Suspense><PdM /></Suspense></Guard>;
}
