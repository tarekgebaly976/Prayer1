"use client";

import { Anchor, Breadcrumbs, Button, Grid, Group, Image, NumberInput, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Attachments } from "@/components/Attachments";
import { DataTable, KV, Loading, PageHeader, Section, StatusBadge } from "@/components/ui";
import { EquipmentTypeInput } from "@/components/FailureModes";
import { LabelPrint } from "@/components/LabelPrint";
import { blobUrl, patch, post } from "@/lib/api";
import { fmtDate, fmtMoney, fmtNum, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, AssetNode, KPI, Page, Part } from "@/lib/types";
import { NewRequest } from "../../requests/page";

interface History { work_orders: { id: string; number: string; type: string; status: string; title: string; created_at: string; actual_cost: number }[];
  downtime: { id: string; started_at: string; ended_at: string | null; is_failure: boolean; reason: string | null }[];
  status_history: { from: string | null; to: string; at: string; note: string | null }[]; total_cost: number }
interface Meter { id: string; name: string; unit: string; current_value: number; last_read_at: string | null; is_operating_hours: boolean }
interface Bom { id: string; part_id: string; part_code: string; description: string; quantity: number; position: string | null; is_critical_spare: boolean }

function MeterRow({ m }: { m: Meter }) {
  const { t } = useTranslation();
  const { can } = useSession();
  const [v, setV] = useState<number | string>("");
  const add = useMut(() => post(`/assets/meters/${m.id}/readings`, { value: Number(v) }), { onDone: () => setV("") });
  return (
    <Table.Tr>
      <Table.Td>{m.name}</Table.Td><Table.Td>{fmtNum(m.current_value)} {m.unit}</Table.Td><Table.Td>{fmtDate(m.last_read_at, undefined, true)}</Table.Td>
      <Table.Td>{can("pdm.record") && <Group gap={4} wrap="nowrap"><NumberInput size="xs" w={110} value={v} onChange={setV} min={Number(m.current_value)} aria-label={t("asset.addReading")} />
        <Button size="xs" disabled={v === ""} onClick={() => add.mutate(undefined)}>{t("asset.addReading")}</Button></Group>}</Table.Td>
    </Table.Tr>
  );
}

function Detail() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const { t, i18n } = useTranslation();
  const { can, plant } = useSession();
  const a = useQ<Asset>(`/assets/${id}`);
  const anc = useQ<AssetNode[]>(`/assets/${id}/ancestors`);
  const kids = useQ<Page<AssetNode>>("/assets/tree", { parent_id: id, limit: 200 });
  const hist = useQ<History>(`/assets/${id}/history`);
  const meters = useQ<Meter[]>(`/assets/${id}/meters`);
  const bom = useQ<Bom[]>(`/assets/${id}/bom`);
  const rel = useQ<Record<string, KPI>>(`/assets/${id}/reliability`);
  const lube = useQ<{ id: string; code: string; component: string | null; next_due_date: string | null; quantity: number; unit: string }[]>(can("lube.view") ? "/lubrication/points" : null, { asset_id: id });
  const pdm = useQ<{ id: string; code: string; name: string; last_status: string; last_value: number | null; unit: string }[]>(can("pdm.view") ? "/pdm/points" : null, { asset_id: id });
  const parts = useQ<Page<Part>>(can("asset.edit") && can("inventory.view") ? "/inventory/parts" : null, { limit: 500 });
  const [qr, setQr] = useState<string | null>(null);
  const [req, setReq] = useState(false);
  const [labels, setLabels] = useState(false);
  const [edit, setEdit] = useState<Record<string, unknown> | null>(null);
  const [bomF, setBomF] = useState<{ part_id: string | null; quantity: number | string }>({ part_id: null, quantity: 1 });
  const [meterName, setMeterName] = useState("");
  useEffect(() => { blobUrl(`/assets/${id}/qr.png`).then(setQr).catch(() => setQr(null)); }, [id]);
  const save = useMut(() => patch(`/assets/${id}`, edit), { onDone: () => setEdit(null) });
  const addBom = useMut(() => post(`/assets/${id}/bom`, { part_id: bomF.part_id, quantity: Number(bomF.quantity) }));
  const addMeter = useMut(() => post(`/assets/${id}/meters`, { name: meterName }), { onDone: () => setMeterName("") });
  if (!a.data) return <Loading />;
  const x = a.data;
  const name = i18n.language === "ar" && x.name_ar ? x.name_ar : x.name;
  return (
    <>
      <Breadcrumbs mb="xs" separator="›">{(anc.data ?? []).map((n) => <Anchor key={n.id} component={Link} href={`/assets/${n.id}`} size="sm">{n.code}</Anchor>)}</Breadcrumbs>
      <PageHeader title={`${x.code} · ${name}`} actions={<>
        {can("request.create") && <Button color="red" onClick={() => setReq(true)}>{t("req.new")}</Button>}
        {can("wo.create") && <Button component={Link} href={`/work-orders/new?asset=${x.id}`}>{t("wo.new")}</Button>}
        {can("asset.edit") && <Button variant="light" onClick={() => setEdit({ name: x.name, name_ar: x.name_ar, criticality: x.criticality, status: x.status, oem: x.oem, model: x.model, serial_number: x.serial_number, location: x.location, description: x.description, equipment_type: x.equipment_type })}>{t("common.edit")}</Button>}
      </>}>
        <Group gap="xs"><StatusBadge value={x.status} /><StatusBadge value={x.criticality} /><Text size="sm" c="dimmed">{t(`level.${x.level}`)}</Text></Group>
      </PageHeader>
      <Tabs defaultValue={sp.get("tab") ?? "info"} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="info">{t("common.details")}</Tabs.Tab>
          <Tabs.Tab value="history">{t("common.history")}</Tabs.Tab>
          <Tabs.Tab value="bom">{t("asset.bom")}</Tabs.Tab>
          <Tabs.Tab value="cm">{t("asset.meters")} / {t("nav.pdm")}</Tabs.Tab>
          {can("lube.view") && <Tabs.Tab value="lube">{t("nav.lubrication")}</Tabs.Tab>}
          <Tabs.Tab value="files">{t("common.attachments")}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="info" pt="md">
          <Grid>
            <Grid.Col span={{ base: 12, md: 8 }}>
              {edit ? (
                <Section title={t("common.edit")} actions={<><Button size="xs" variant="default" onClick={() => setEdit(null)}>{t("common.cancel")}</Button><Button size="xs" onClick={() => save.mutate(undefined)}>{t("common.save")}</Button></>}>
                  <SimpleGrid cols={{ base: 1, sm: 2 }}>
                    {(["name", "name_ar", "oem", "model", "serial_number", "location"] as const).map((k) => (
                      <TextInput key={k} label={k} value={String(edit[k] ?? "")} onChange={(e) => setEdit({ ...edit, [k]: e.currentTarget.value || null })} />))}
                    <EquipmentTypeInput value={(edit.equipment_type as string | null) ?? null} onChange={(v) => setEdit({ ...edit, equipment_type: v })} />
                    <Select label={t("common.criticality")} data={["A", "B", "C"]} value={String(edit.criticality)} onChange={(v) => setEdit({ ...edit, criticality: v })} />
                    <Select label={t("common.status")} value={String(edit.status)} onChange={(v) => setEdit({ ...edit, status: v })}
                      data={["in_service", "standby", "under_maintenance", "out_of_service", "decommissioned"].map((s) => ({ value: s, label: t(`status.${s}`) }))} />
                  </SimpleGrid>
                  <Textarea mt="sm" label={t("common.description")} value={String(edit.description ?? "")} onChange={(e) => setEdit({ ...edit, description: e.currentTarget.value })} />
                </Section>
              ) : (
                <SimpleGrid cols={{ base: 2, sm: 3 }}>
                  <KV label={t("asset.oem")}>{x.oem}</KV><KV label={t("asset.model")}>{x.model}</KV><KV label={t("asset.serial")}>{x.serial_number}</KV>
                  <KV label={t("asset.installDate")}>{fmtDate(x.install_date)}</KV><KV label={t("common.location")}>{x.location}</KV>
                  <KV label={t("asset.opHours")}>{fmtNum(x.operating_hours)}</KV>
                  <KV label={t("fm.equipmentType")}>{x.equipment_type}</KV>
                  <KV label={t("common.description")}>{x.description}</KV>
                  <KV label={t("wo.actualCost")}>{fmtMoney(hist.data?.total_cost ?? 0, plant?.currency ?? "SAR")}</KV>
                </SimpleGrid>
              )}
              <Section title={t("asset.reliability")}>
                <SimpleGrid cols={{ base: 2, sm: 4 }}>
                  {rel.data && (["mtbf", "mttr", "availability", "breakdown_downtime"] as const).map((k) => {
                    const v = rel.data?.[k];
                    return <KV key={k} label={k.toUpperCase()}>{v?.available ? `${fmtNum(v.value)} ${v.unit}` : <Text size="xs" c="dimmed">{v?.reason}</Text>}</KV>;
                  })}
                </SimpleGrid>
              </Section>
              <Section title={t("asset.children")}>
                {kids.data && kids.data.total > kids.data.items.length && <Text size="xs" c="dimmed">{kids.data.items.length} / {kids.data.total}</Text>}
                {(kids.data?.items ?? []).map((k) => <Group key={k.id} gap="xs"><Anchor component={Link} href={`/assets/${k.id}`} className="mono" size="sm">{k.code}</Anchor><Text size="sm">{k.name}</Text><StatusBadge value={k.criticality} size="xs" /></Group>)}
              </Section>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 4 }}>
              <Section title={t("asset.qr")}>
                {qr && <Image src={qr} alt="QR" w={180} />}
                <Text size="xs" c="dimmed" className="mono">cmms:asset:{x.qr_token}</Text>
                <Group gap="xs" mt="xs">
                  <Button size="xs" variant="default" onClick={() => setLabels(true)}>{t("labels.button")}</Button>
                  <Button size="xs" variant="subtle" onClick={() => window.print()}>{t("labels.printPage")}</Button>
                </Group>
                <LabelPrint kind="assets" under={x.id} opened={labels} onClose={() => setLabels(false)} />
              </Section>
            </Grid.Col>
          </Grid>
        </Tabs.Panel>
        <Tabs.Panel value="history" pt="md">
          <Stack>
            <DataTable rows={hist.data?.work_orders} columns={[
              { key: "n", label: t("wo.number"), render: (w) => <Anchor component={Link} href={`/work-orders/${w.id}`} className="mono">{w.number}</Anchor> },
              { key: "t", label: t("wo.title"), render: (w) => w.title }, { key: "ty", label: t("common.type"), render: (w) => t(`woType.${w.type}`) },
              { key: "s", label: t("common.status"), render: (w) => <StatusBadge value={w.status} /> },
              { key: "d", label: t("common.createdAt"), render: (w) => fmtDate(w.created_at) },
              { key: "c", label: t("common.cost"), render: (w) => fmtMoney(w.actual_cost, plant?.currency ?? "SAR") }]} />
            <Section title="Downtime">
              <DataTable rows={hist.data?.downtime} columns={[
                { key: "s", label: t("common.start"), render: (d) => fmtDate(d.started_at, plant?.timezone, true) },
                { key: "e", label: t("common.end"), render: (d) => fmtDate(d.ended_at, plant?.timezone, true) },
                { key: "f", label: "Failure", render: (d) => (d.is_failure ? t("common.yes") : t("common.no")) }, { key: "r", label: t("common.reason"), render: (d) => d.reason }]} />
            </Section>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="bom" pt="md">
          {can("asset.edit") && can("inventory.view") && (
            <Group align="end" mb="sm">
              <Select label={t("wo.part")} searchable w={320} value={bomF.part_id} onChange={(v) => setBomF({ ...bomF, part_id: v })} data={(parts.data?.items ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.description}` }))} />
              <NumberInput label={t("common.quantity")} w={100} min={0.001} value={bomF.quantity} onChange={(v) => setBomF({ ...bomF, quantity: v })} />
              <Button disabled={!bomF.part_id} onClick={() => addBom.mutate(undefined)}>{t("common.add")}</Button>
            </Group>
          )}
          <DataTable rows={bom.data} columns={[
            { key: "c", label: t("common.code"), render: (b) => <Anchor component={Link} href={`/inventory/parts/${b.part_id}`}>{b.part_code}</Anchor> },
            { key: "d", label: t("common.description"), render: (b) => b.description }, { key: "q", label: t("common.quantity"), render: (b) => fmtNum(b.quantity) },
            { key: "k", label: t("inv.critical"), render: (b) => (b.is_critical_spare ? "★" : "") }]} />
        </Tabs.Panel>
        <Tabs.Panel value="cm" pt="md">
          <Stack>
            <Section title={t("asset.meters")} actions={can("asset.edit") ? <Group gap={4}><TextInput size="xs" placeholder={t("common.name")} value={meterName} onChange={(e) => setMeterName(e.currentTarget.value)} /><Button size="xs" disabled={!meterName} onClick={() => addMeter.mutate(undefined)}>{t("common.add")}</Button></Group> : undefined}>
              <Table><Table.Tbody>{(meters.data ?? []).map((m) => <MeterRow key={m.id} m={m} />)}</Table.Tbody></Table>
            </Section>
            {can("pdm.view") && <Section title={t("pdm.points")}>
              {(pdm.data ?? []).map((p) => <Group key={p.id} gap="xs"><Anchor component={Link} href={`/pdm?point=${p.id}`}>{p.code}</Anchor><Text size="sm">{p.name}</Text><StatusBadge value={p.last_status} /><Text size="sm">{fmtNum(p.last_value)} {p.unit}</Text></Group>)}
            </Section>}
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="lube" pt="md">
          <DataTable rows={lube.data} columns={[{ key: "c", label: t("common.code"), render: (p) => p.code }, { key: "m", label: "Component", render: (p) => p.component },
            { key: "q", label: t("common.quantity"), render: (p) => `${fmtNum(p.quantity)} ${p.unit}` }, { key: "n", label: t("pm.nextDue"), render: (p) => fmtDate(p.next_due_date) }]} />
        </Tabs.Panel>
        <Tabs.Panel value="files" pt="md"><Attachments entityType="asset" entityId={x.id} defaultCategory="manual" /></Tabs.Panel>
      </Tabs>
      <NewRequest opened={req} onClose={() => setReq(false)} assetId={x.id} />
    </>
  );
}

export default function AssetDetail() {
  return <Suspense><Detail /></Suspense>;
}
