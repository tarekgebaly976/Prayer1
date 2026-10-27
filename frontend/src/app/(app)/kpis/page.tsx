"use client";

import { BarChart } from "@mantine/charts";
import { Alert, Button, Card, FileInput, Group, Modal, NumberInput, ScrollArea, SimpleGrid, Stack, Table, Tabs, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { DeptSelect, Loading, PageHeader } from "@/components/ui";
import { api, download, put } from "@/lib/api";
import { fmtNum, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { KPI } from "@/lib/types";

interface Def { code: string; name: string; unit: string; formula: string; source_data: string; inclusion_rules: string; period: string; missing_data: string }

function Drill({ code, start, end, dept, onClose }: { code: string; start: string; end: string; dept: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useQ<KPI & { definition: Def; records: Record<string, unknown>[]; records_truncated: boolean }>(`/kpis/${code}`, { start, end, department_id: dept });
  const trend = useQ<{ period: string; value: number | null; available: boolean; manual: number | null; target: number | null }[]>(`/kpis/trend/${code}`, { months: 12, department_id: dept });
  const hasManual = (trend.data ?? []).some((x) => x.manual !== null && x.manual !== undefined);
  const rows = q.data?.records ?? [];
  const cols = rows[0] ? Object.keys(rows[0]).filter((k) => !k.endsWith("_id") && k !== "id") : [];
  return (
    <Modal opened onClose={onClose} size="xl" title={q.data?.definition.name ?? code}>
      {!q.data ? <Loading /> : (
        <Stack>
          <Text size="sm"><b>{t("kpi.formula")}:</b> {q.data.definition.formula}</Text>
          <Text size="xs" c="dimmed"><b>{t("kpi.rules")}:</b> {q.data.definition.inclusion_rules}</Text>
          <Text size="xs" c="dimmed"><b>{t("kpi.source")}:</b> {q.data.definition.source_data} · <b>{t("kpi.missing")}:</b> {q.data.definition.missing_data}</Text>
          <Group><Text fw={700}>{q.data.available ? `${fmtNum(q.data.value)} ${q.data.unit}` : `${t("common.unavailable")}: ${q.data.reason}`}</Text>
            {q.data.denominator !== null && <Text size="sm" c="dimmed">{t("kpi.numerator")} {fmtNum(q.data.numerator)} · {t("kpi.denominator")} {fmtNum(q.data.denominator)}</Text>}</Group>
          {Object.keys(q.data.details ?? {}).length > 0 && <Text size="xs" className="mono">{JSON.stringify(q.data.details)}</Text>}
          {trend.data && <BarChart h={180} withLegend={hasManual} dataKey="period"
            data={trend.data.map((x) => ({ period: x.period, [t("kpi.calculated")]: x.value ?? 0, [t("kpi.manualSeries")]: x.manual ?? 0, [t("kpi.target")]: x.target ?? 0 }))}
            series={[{ name: t("kpi.calculated"), color: "indigo.6" }, ...(hasManual ? [{ name: t("kpi.manualSeries"), color: "orange.5" }, { name: t("kpi.target"), color: "gray.5" }] : [])]} />}
          <Text fw={600}>{t("kpi.drill")} ({rows.length}{q.data.records_truncated ? "+" : ""})</Text>
          <ScrollArea h={300}>
            <Table fz="xs" striped>
              <Table.Thead><Table.Tr>{cols.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr></Table.Thead>
              <Table.Tbody>{rows.map((r, i) => (
                <Table.Tr key={i}>{cols.map((c) => {
                  const v = r[c];
                  const link = c === "number" && typeof r.id === "string" ? `/work-orders/${r.id}` : null;
                  return <Table.Td key={c}>{link ? <a href={link}>{String(v)}</a> : typeof v === "object" ? JSON.stringify(v) : String(v ?? "")}</Table.Td>;
                })}</Table.Tr>))}</Table.Tbody>
            </Table>
          </ScrollArea>
        </Stack>
      )}
    </Modal>
  );
}

interface Card { id: string; name: string; unit: string | null; department: string | null; kpi_code: string | null; higher_is_better: boolean;
  months: { target: number | null; actual: number | null }[] }
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const met = (c: Card, a: number | null, tg: number | null) => (a === null || tg === null ? null : c.higher_is_better ? a >= tg : a <= tg);
const avg = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x !== null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

/** Company KPI scorecard (e.g. the management KPI sheet): target and actual per month, entered by the team via Excel. */
function CompanyKPIs() {
  const { t } = useTranslation();
  const { can } = useSession();
  const [year, setYear] = useState<number | string>(new Date().getFullYear());
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<{ kpis: number; values: number; cleared: number; invalid: number; errors: { row: number; code: string | null; errors: string[] }[] } | null>(null);
  const cards = useQ<Card[]>("/kpis/scorecard", { year: Number(year) });
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const preview = useMut(() => api<NonNullable<typeof res>>("POST", "/kpis/scorecard/preview", fd()), { success: false, onDone: setRes });
  const commit = useMut(() => api("POST", "/kpis/scorecard/commit", fd()), { onDone: () => { setFile(null); setRes(null); } });
  const remove = useMut((id: string) => api("DELETE", `/kpis/scorecard/${id}`));
  return (
    <Stack>
      <Text size="sm" c="dimmed">{t("kpi.manualHint")}</Text>
      <Group align="end" wrap="wrap">
        <NumberInput label={t("kpi.year")} w={110} min={2000} max={2100} value={year} onChange={setYear} />
        <Button variant="light" onClick={() => void download("/kpis/scorecard/template.xlsx", { year: Number(year) }, `kpi_scorecard_${year}.xlsx`)}>{t("kpi.downloadTemplate")}</Button>
      </Group>
      {can("kpi.manage") && (
        <Group align="end" wrap="wrap">
          <FileInput label={t("kpi.upload")} w={300} accept=".xlsx" clearable value={file} onChange={(f) => { setFile(f); setRes(null); }} />
          <Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
          <Button color="teal" disabled={!res || res.invalid > 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button>
        </Group>
      )}
      {res && (
        <Alert color={res.invalid ? "red" : "teal"}>
          {res.kpis} KPI · {res.values} {t("kpi.values")} · {res.cleared} {t("kpi.cleared")} · {res.invalid} {t("asset.invalid")}
          {res.errors.slice(0, 50).map((e, i) => <div key={i}>Row {e.row}: {e.errors.join("; ")}</div>)}
        </Alert>
      )}
      {(cards.data ?? []).length === 0 ? <Text size="sm" c="dimmed">{t("common.noData")}</Text> : (
        <ScrollArea>
          <Table striped fz="sm" withColumnBorders>
            <Table.Thead><Table.Tr><Table.Th>KPI</Table.Th><Table.Th /><Table.Th>{t("kpi.ytd")}</Table.Th>{MONTHS.map((m) => <Table.Th key={m}>{m}</Table.Th>)}{can("kpi.manage") && <Table.Th />}</Table.Tr></Table.Thead>
            <Table.Tbody>{(cards.data ?? []).map((c) => {
              const ya = avg(c.months.map((m) => m.actual)), yt = avg(c.months.map((m) => m.target)), ok = met(c, ya, yt);
              return (
                <Table.Tr key={c.id}>
                  <Table.Td><b>{c.name}</b><Text size="xs" c="dimmed">{[c.department, c.unit, c.higher_is_better ? "↑" : "↓"].filter(Boolean).join(" · ")}</Text></Table.Td>
                  <Table.Td><Text size="xs">{t("kpi.actual")}</Text><Text size="xs" c="dimmed">{t("kpi.target")}</Text></Table.Td>
                  <Table.Td><Text size="sm" fw={700} c={ok === null ? undefined : ok ? "teal" : "red"}>{ya === null ? "—" : fmtNum(ya)}</Text><Text size="xs" c="dimmed">{yt === null ? "—" : fmtNum(yt)}</Text></Table.Td>
                  {c.months.map((m, i) => { const g = met(c, m.actual, m.target); return (
                    <Table.Td key={i}><Text size="sm" fw={600} c={g === null ? undefined : g ? "teal" : "red"}>{m.actual === null ? "—" : fmtNum(m.actual)}</Text>
                      <Text size="xs" c="dimmed">{m.target === null ? "" : fmtNum(m.target)}</Text></Table.Td>); })}
                  {can("kpi.manage") && <Table.Td><Button size="compact-xs" variant="subtle" color="red" onClick={() => { if (window.confirm(t("kpi.deleteConfirm", { name: c.name }))) remove.mutate(c.id); }}>{t("common.delete")}</Button></Table.Td>}
                </Table.Tr>);
            })}</Table.Tbody>
          </Table>
        </ScrollArea>
      )}
    </Stack>
  );
}

function KPIs() {
  const { t } = useTranslation();
  const { can } = useSession();
  const today = new Date().toISOString().slice(0, 10);
  const [start, setStart] = useState(`${today.slice(0, 7)}-01`);
  const [end, setEnd] = useState(today);
  const [dept, setDept] = useState<string | null>(null);
  const [drill, setDrill] = useState<string | null>(null);
  const q = useQ<{ kpis: KPI[]; currency: string }>("/kpis", { start, end, department_id: dept });
  const defs = useQ<Def[]>("/kpis/definitions");
  const names = new Map((defs.data ?? []).map((d) => [d.code, d.name]));
  const [prod, setProd] = useState({ department_id: null as string | null, record_date: today, tons_produced: 0 as number | string, good_tons: "" as number | string, planned_production_hours: 24 as number | string, run_hours: "" as number | string, ideal_rate_tph: "" as number | string });
  const [bud, setBud] = useState({ department_id: null as string | null, year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)), amount: 0 as number | string });
  const n = (v: number | string) => (v === "" ? null : Number(v));
  const saveProd = useMut(() => put("/kpis/production", { ...prod, tons_produced: Number(prod.tons_produced), good_tons: n(prod.good_tons), planned_production_hours: n(prod.planned_production_hours), run_hours: n(prod.run_hours), ideal_rate_tph: n(prod.ideal_rate_tph) }));
  const saveBud = useMut(() => put("/kpis/budgets", { ...bud, amount: Number(bud.amount) }));
  const costDept = q.data?.kpis.find((k) => k.code === "cost_by_department")?.details.by_department as Record<string, number> | undefined;
  return (
    <>
      <PageHeader title={t("kpi.title")} actions={can("report.export") ? <>
        <Button variant="default" onClick={() => void download("/exports/kpis.xlsx", { start, end, department_id: dept })}>{t("kpi.exportXlsx")}</Button>
        <Button variant="default" onClick={() => void download("/reports/kpis.pdf", { start, end })}>{t("kpi.exportPdf")}</Button></> : null}>
        <Group align="end" wrap="wrap">
          <TextInput type="date" label={t("common.from")} value={start} onChange={(e) => setStart(e.currentTarget.value)} />
          <TextInput type="date" label={t("common.to")} value={end} onChange={(e) => setEnd(e.currentTarget.value)} />
          <DeptSelect value={dept} onChange={setDept} clearable />
        </Group>
      </PageHeader>
      <Alert color="blue" mb="md">{t("kpi.notice")}</Alert>
      <Tabs defaultValue="dash">
        <Tabs.List><Tabs.Tab value="dash">{t("nav.kpis")}</Tabs.Tab><Tabs.Tab value="manual">{t("kpi.manual")}</Tabs.Tab>
          {can("kpi.manage") && <Tabs.Tab value="data">{t("kpi.production")} / {t("kpi.budget")}</Tabs.Tab>}</Tabs.List>
        <Tabs.Panel value="manual" pt="md"><CompanyKPIs /></Tabs.Panel>
        <Tabs.Panel value="dash" pt="md">
          {!q.data ? <Loading /> : (
            <>
              <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
                {q.data.kpis.map((k) => (
                  <Card key={k.code} withBorder padding="sm" style={{ cursor: "pointer" }} onClick={() => setDrill(k.code)} data-testid={`kpi-${k.code}`}>
                    <Text size="xs" c="dimmed" lineClamp={1}>{names.get(k.code) ?? k.code}</Text>
                    {k.available ? <Text fz={22} fw={700}>{fmtNum(k.value)} <Text span size="sm" c="dimmed">{k.unit}</Text></Text>
                      : <Text size="xs" c="orange" lineClamp={3} title={k.reason ?? ""}>{t("common.unavailable")}: {k.reason}</Text>}
                    {typeof k.details.note === "string" && <Text size="xs" c="dimmed" lineClamp={2} title={k.details.note}>ⓘ {k.details.note}</Text>}
                    {k.code === "backlog" && k.details.weeks !== undefined && k.details.weeks !== null && <Text size="xs" c="dimmed">≈ {String(k.details.weeks)} weeks</Text>}
                  </Card>))}
              </SimpleGrid>
              {costDept && Object.keys(costDept).length > 0 && (
                <Card withBorder mt="md"><Text fw={600} mb="xs">{names.get("cost_by_department")} ({q.data.currency})</Text>
                  <BarChart h={220} data={Object.entries(costDept).map(([d, v]) => ({ dept: d, cost: v }))} dataKey="dept" series={[{ name: "cost", color: "teal.6" }]} /></Card>
              )}
            </>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="data" pt="md">
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Card withBorder><Text fw={600} mb="sm">{t("kpi.production")}</Text><Stack>
              <DeptSelect value={prod.department_id} onChange={(v) => setProd({ ...prod, department_id: v })} />
              <TextInput type="date" label={t("common.date")} value={prod.record_date} onChange={(e) => setProd({ ...prod, record_date: e.currentTarget.value })} />
              <SimpleGrid cols={2}>
                <NumberInput label={t("kpi.tons")} min={0} value={prod.tons_produced} onChange={(v) => setProd({ ...prod, tons_produced: v })} />
                <NumberInput label={t("kpi.goodTons")} min={0} value={prod.good_tons} onChange={(v) => setProd({ ...prod, good_tons: v })} />
                <NumberInput label={t("kpi.plannedH")} min={0} max={24} value={prod.planned_production_hours} onChange={(v) => setProd({ ...prod, planned_production_hours: v })} />
                <NumberInput label={t("kpi.runH")} min={0} max={24} value={prod.run_hours} onChange={(v) => setProd({ ...prod, run_hours: v })} />
                <NumberInput label={t("kpi.ideal")} min={0} value={prod.ideal_rate_tph} onChange={(v) => setProd({ ...prod, ideal_rate_tph: v })} />
              </SimpleGrid>
              <Button disabled={!prod.department_id} onClick={() => saveProd.mutate(undefined)}>{t("common.save")}</Button></Stack></Card>
            <Card withBorder><Text fw={600} mb="sm">{t("kpi.budget")}</Text><Stack>
              <DeptSelect value={bud.department_id} onChange={(v) => setBud({ ...bud, department_id: v })} clearable label={`${t("common.department")} (${t("common.optional")})`} />
              <SimpleGrid cols={2}><NumberInput label="Year" value={bud.year} onChange={(v) => setBud({ ...bud, year: Number(v) })} />
                <NumberInput label="Month" min={1} max={12} value={bud.month} onChange={(v) => setBud({ ...bud, month: Number(v) })} /></SimpleGrid>
              <NumberInput label={t("common.cost")} min={0} value={bud.amount} onChange={(v) => setBud({ ...bud, amount: v })} />
              <Button onClick={() => saveBud.mutate(undefined)}>{t("common.save")}</Button></Stack></Card>
          </SimpleGrid>
        </Tabs.Panel>
      </Tabs>
      {drill && <Drill code={drill} start={start} end={end} dept={dept} onClose={() => setDrill(null)} />}
    </>
  );
}

export default function KPIPage() {
  return <Guard perm="kpi.view"><KPIs /></Guard>;
}
