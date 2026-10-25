"use client";

import { BarChart } from "@mantine/charts";
import { Alert, Button, Card, Group, Modal, NumberInput, ScrollArea, SimpleGrid, Stack, Table, Tabs, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { DeptSelect, Loading, PageHeader } from "@/components/ui";
import { download, put } from "@/lib/api";
import { fmtNum, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { KPI } from "@/lib/types";

interface Def { code: string; name: string; unit: string; formula: string; source_data: string; inclusion_rules: string; period: string; missing_data: string }

function Drill({ code, start, end, dept, onClose }: { code: string; start: string; end: string; dept: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useQ<KPI & { definition: Def; records: Record<string, unknown>[]; records_truncated: boolean }>(`/kpis/${code}`, { start, end, department_id: dept });
  const trend = useQ<{ period: string; value: number | null; available: boolean }[]>(`/kpis/trend/${code}`, { months: 12, department_id: dept });
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
          {trend.data && <BarChart h={180} data={trend.data.map((x) => ({ period: x.period, value: x.value ?? 0 }))} dataKey="period" series={[{ name: "value", color: "indigo.6" }]} />}
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
        <Tabs.List><Tabs.Tab value="dash">{t("nav.kpis")}</Tabs.Tab>{can("kpi.manage") && <Tabs.Tab value="data">{t("kpi.production")} / {t("kpi.budget")}</Tabs.Tab>}</Tabs.List>
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
