"use client";

import { Alert, Button, Checkbox, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Tabs, Text, TextInput } from "@mantine/core";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { DataTable, PageHeader, Pager, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtMoney, fmtNum, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Page, Part, Warehouse } from "@/lib/types";

interface PO { id: string; number: string; status: string; external_reference: string | null; expected_date: string | null; lines: { id: string; part_code: string; part_id: string; quantity: number; qty_received: number; unit_price: number }[] }
interface Aging { slow_moving: AgingRow[]; obsolete_candidates: AgingRow[]; excess: (AgingRow & { excess_qty: number })[]; no_movement_recorded: AgingRow[] }
interface AgingRow { id: string; code: string; description: string; on_hand: number; value: number; is_critical_spare: boolean }

function Inventory() {
  const { t } = useTranslation();
  const router = useRouter();
  const { can, plant } = useSession();
  const cur = plant?.currency ?? "SAR";
  const [q, setQ] = useState("");
  const [crit, setCrit] = useState(false);
  const [below, setBelow] = useState(false);
  const [offset, setOffset] = useState(0);
  const parts = useQ<Page<Part>>("/inventory/parts", { q, critical_only: crit, below_reorder: below, limit: 50, offset });
  const allParts = useQ<Page<Part>>("/inventory/parts", { limit: 500 });
  const whs = useQ<Warehouse[]>("/inventory/warehouses");
  const pos = useQ<PO[]>("/inventory/purchase-orders");
  const val = useQ<{ total_value: number; items: { code: string; description: string; on_hand: number; average_cost: number; value: number }[] }>("/inventory/valuation");
  const aging = useQ<Aging>("/inventory/aging");
  const [modal, setModal] = useState<"part" | "receipt" | "adjust" | "po" | "wh" | null>(null);
  const [pf, setPf] = useState({ code: "", description: "", oem_part_number: "", manufacturer: "", uom: "EA", criticality: "C", is_critical_spare: false,
    min_qty: 0 as number | string, max_qty: 0 as number | string, reorder_point: 0 as number | string, unit_price: 0 as number | string, lead_time_days: "" as number | string });
  const [tx, setTx] = useState({ part_id: null as string | null, warehouse_id: null as string | null, quantity: 1 as number | string, unit_cost: 0 as number | string, delta: 0 as number | string, reason: "", reference: "", po_line_id: null as string | null });
  const [po, setPo] = useState({ part_id: null as string | null, quantity: 1 as number | string, unit_price: 0 as number | string, external_reference: "" });
  const [wh, setWh] = useState({ code: "", name: "" });
  const close = () => setModal(null);
  const createPart = useMut(() => post("/inventory/parts", { ...pf, min_qty: Number(pf.min_qty), max_qty: Number(pf.max_qty), reorder_point: Number(pf.reorder_point),
    unit_price: Number(pf.unit_price), lead_time_days: pf.lead_time_days === "" ? null : Number(pf.lead_time_days), oem_part_number: pf.oem_part_number || null, manufacturer: pf.manufacturer || null }), { onDone: close });
  const receive = useMut(() => post("/inventory/receipts", { part_id: tx.part_id, warehouse_id: tx.warehouse_id, quantity: Number(tx.quantity), unit_cost: Number(tx.unit_cost), reference: tx.reference || null, po_line_id: tx.po_line_id }), { onDone: close });
  const adjust = useMut(() => post("/inventory/adjustments", { part_id: tx.part_id, warehouse_id: tx.warehouse_id, delta: Number(tx.delta), reason: tx.reason }), { onDone: close });
  const createPo = useMut(() => post("/inventory/purchase-orders", { external_reference: po.external_reference || null, lines: [{ part_id: po.part_id, quantity: Number(po.quantity), unit_price: Number(po.unit_price) }] }), { onDone: close });
  const poStatus = useMut((a: { id: string; status: string }) => post(`/inventory/purchase-orders/${a.id}/status`, { status: a.status }));
  const createWh = useMut(() => post("/inventory/warehouses", wh), { onDone: close });
  const partOpts = (allParts.data?.items ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.description}` }));
  const whOpts = (whs.data ?? []).map((w) => ({ value: w.id, label: w.code }));
  const openLines = (pos.data ?? []).filter((p) => ["ordered", "partial"].includes(p.status)).flatMap((p) => p.lines.filter((l) => l.part_id === tx.part_id && l.qty_received < l.quantity).map((l) => ({ value: l.id, label: `${p.number} (${l.qty_received}/${l.quantity})` })));
  const agingCols = [{ key: "c", label: t("common.code"), render: (r: AgingRow) => <>{r.code}{r.is_critical_spare ? " ★" : ""}</> }, { key: "d", label: t("common.description"), render: (r: AgingRow) => r.description },
    { key: "q", label: t("inv.onHand"), render: (r: AgingRow) => fmtNum(r.on_hand) }, { key: "v", label: t("inv.valuation"), render: (r: AgingRow) => fmtMoney(r.value, cur) }];
  return (
    <>
      <PageHeader title={t("nav.inventory")} actions={<>
        {can("inventory.manage") && <Button onClick={() => setModal("part")}>{t("inv.newPart")}</Button>}
        {can("inventory.transact") && <Button variant="light" onClick={() => setModal("receipt")}>{t("inv.receive")}</Button>}
        {can("inventory.adjust") && <Button variant="light" onClick={() => setModal("adjust")}>{t("inv.adjust")}</Button>}
        {can("purchase.manage") && <Button variant="default" onClick={() => setModal("po")}>{t("inv.newPO")}</Button>}
        {can("inventory.manage") && <Button variant="default" onClick={() => setModal("wh")}>+ {t("wo.warehouse")}</Button>}
      </>} />
      <Tabs defaultValue="parts">
        <Tabs.List><Tabs.Tab value="parts">{t("inv.parts")}</Tabs.Tab><Tabs.Tab value="pos">{t("inv.pos")}</Tabs.Tab>
          <Tabs.Tab value="valuation">{t("inv.valuation")}</Tabs.Tab><Tabs.Tab value="aging">{t("inv.aging")}</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="parts" pt="md">
          <Group mb="sm">
            <TextInput placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.currentTarget.value); setOffset(0); }} />
            <Checkbox label={t("inv.critical")} checked={crit} onChange={(e) => setCrit(e.currentTarget.checked)} />
            <Checkbox label={t("inv.belowReorder")} checked={below} onChange={(e) => setBelow(e.currentTarget.checked)} />
          </Group>
          <DataTable rows={parts.data?.items} onRow={(p) => router.push(`/inventory/parts/${p.id}`)} columns={[
            { key: "c", label: t("common.code"), render: (p) => <span className="mono">{p.code}{p.is_critical_spare ? " ★" : ""}</span> },
            { key: "d", label: t("common.description"), render: (p) => p.description }, { key: "k", label: t("common.criticality"), render: (p) => <StatusBadge value={p.criticality} /> },
            { key: "oh", label: t("inv.onHand"), render: (p) => `${fmtNum(p.qty_on_hand)} ${p.uom}` }, { key: "r", label: t("inv.reserved"), render: (p) => fmtNum(p.qty_reserved) },
            { key: "a", label: t("inv.available"), render: (p) => <Text c={Number(p.qty_available) <= Number(p.reorder_point) ? "red" : undefined} size="sm">{fmtNum(p.qty_available)}</Text> },
            { key: "o", label: t("inv.onOrder"), render: (p) => fmtNum(p.qty_on_order) }, { key: "rp", label: t("inv.reorder"), render: (p) => fmtNum(p.reorder_point) },
            { key: "ac", label: t("inv.avgCost"), render: (p) => fmtMoney(p.average_cost, p.currency) }]} />
          <Pager page={parts.data} setPage={(p) => setOffset((p - 1) * 50)} />
        </Tabs.Panel>
        <Tabs.Panel value="pos" pt="md">
          <Alert color="blue" mb="sm">{t("inv.erpNote")}</Alert>
          <DataTable rows={pos.data} columns={[
            { key: "n", label: "#", render: (p) => p.number }, { key: "s", label: t("common.status"), render: (p) => <StatusBadge value={p.status} /> },
            { key: "e", label: t("inv.externalRef"), render: (p) => p.external_reference }, { key: "l", label: t("wo.part"), render: (p) => p.lines.map((l) => `${l.part_code} ${l.qty_received}/${l.quantity}`).join(", ") },
            { key: "a", label: t("common.actions"), render: (p) => can("purchase.manage") && <Group gap={4}>
              {p.status === "requested" && <Button size="xs" onClick={() => poStatus.mutate({ id: p.id, status: "ordered" })}>{t("status.ordered")}</Button>}
              {["requested", "ordered", "draft"].includes(p.status) && <Button size="xs" color="red" variant="subtle" onClick={() => poStatus.mutate({ id: p.id, status: "cancelled" })}>{t("common.cancel")}</Button>}</Group> }]} />
        </Tabs.Panel>
        <Tabs.Panel value="valuation" pt="md">
          <Text fw={700} mb="sm">{t("common.total")}: {fmtMoney(val.data?.total_value ?? 0, cur)}</Text>
          <DataTable rows={val.data?.items} rowKey={(r) => r.code} columns={[{ key: "c", label: t("common.code"), render: (r) => r.code }, { key: "d", label: t("common.description"), render: (r) => r.description },
            { key: "q", label: t("inv.onHand"), render: (r) => fmtNum(r.on_hand) }, { key: "a", label: t("inv.avgCost"), render: (r) => fmtMoney(r.average_cost, cur) }, { key: "v", label: t("common.total"), render: (r) => fmtMoney(r.value, cur) }]} />
        </Tabs.Panel>
        <Tabs.Panel value="aging" pt="md">
          <Stack>
            <Text fw={600}>Excess (above max)</Text><DataTable rows={aging.data?.excess} columns={agingCols} />
            <Text fw={600}>Slow-moving (&gt;180 days)</Text><DataTable rows={aging.data?.slow_moving} columns={agingCols} />
            <Text fw={600}>Obsolete candidates (&gt;730 days)</Text><DataTable rows={aging.data?.obsolete_candidates} columns={agingCols} />
          </Stack>
        </Tabs.Panel>
      </Tabs>
      <Modal opened={modal === "part"} onClose={close} title={t("inv.newPart")} size="lg">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t("common.code")} value={pf.code} onChange={(e) => setPf({ ...pf, code: e.currentTarget.value })} />
          <TextInput label={t("common.description")} value={pf.description} onChange={(e) => setPf({ ...pf, description: e.currentTarget.value })} />
          <TextInput label="OEM P/N" value={pf.oem_part_number} onChange={(e) => setPf({ ...pf, oem_part_number: e.currentTarget.value })} />
          <TextInput label="Manufacturer" value={pf.manufacturer} onChange={(e) => setPf({ ...pf, manufacturer: e.currentTarget.value })} />
          <TextInput label={t("common.unit")} value={pf.uom} onChange={(e) => setPf({ ...pf, uom: e.currentTarget.value })} />
          <Select label={t("common.criticality")} data={["A", "B", "C"]} value={pf.criticality} onChange={(v) => setPf({ ...pf, criticality: v ?? "C" })} />
          <NumberInput label="Min" min={0} value={pf.min_qty} onChange={(v) => setPf({ ...pf, min_qty: v })} />
          <NumberInput label="Max" min={0} value={pf.max_qty} onChange={(v) => setPf({ ...pf, max_qty: v })} />
          <NumberInput label={t("inv.reorder")} min={0} value={pf.reorder_point} onChange={(v) => setPf({ ...pf, reorder_point: v })} />
          <NumberInput label={t("inv.unitCost")} min={0} value={pf.unit_price} onChange={(v) => setPf({ ...pf, unit_price: v })} />
          <NumberInput label="Lead time (days)" min={0} value={pf.lead_time_days} onChange={(v) => setPf({ ...pf, lead_time_days: v })} />
          <Checkbox mt="lg" label={t("inv.critical")} checked={pf.is_critical_spare} onChange={(e) => setPf({ ...pf, is_critical_spare: e.currentTarget.checked })} />
        </SimpleGrid>
        <Button mt="md" disabled={!pf.code || !pf.description} onClick={() => createPart.mutate(undefined)}>{t("common.create")}</Button>
      </Modal>
      <Modal opened={modal === "receipt" || modal === "adjust"} onClose={close} title={modal === "receipt" ? t("inv.receive") : t("inv.adjust")}>
        <Stack>
          <Select label={t("wo.part")} searchable data={partOpts} value={tx.part_id} onChange={(v) => setTx({ ...tx, part_id: v, po_line_id: null })} />
          <Select label={t("wo.warehouse")} data={whOpts} value={tx.warehouse_id} onChange={(v) => setTx({ ...tx, warehouse_id: v })} />
          {modal === "receipt" ? <>
            <NumberInput label={t("common.quantity")} min={0.001} value={tx.quantity} onChange={(v) => setTx({ ...tx, quantity: v })} />
            <NumberInput label={t("inv.unitCost")} min={0} value={tx.unit_cost} onChange={(v) => setTx({ ...tx, unit_cost: v })} />
            <Select label="PO line" clearable data={openLines} value={tx.po_line_id} onChange={(v) => setTx({ ...tx, po_line_id: v })} />
            <TextInput label="Reference (GRN / delivery note)" value={tx.reference} onChange={(e) => setTx({ ...tx, reference: e.currentTarget.value })} />
            <Button disabled={!tx.part_id || !tx.warehouse_id} onClick={() => receive.mutate(undefined)}>{t("common.save")}</Button>
          </> : <>
            <NumberInput label={t("inv.delta")} value={tx.delta} onChange={(v) => setTx({ ...tx, delta: v })} />
            <TextInput label={t("common.reason")} required value={tx.reason} onChange={(e) => setTx({ ...tx, reason: e.currentTarget.value })} />
            <Button disabled={!tx.part_id || !tx.warehouse_id || !Number(tx.delta) || tx.reason.length < 5} onClick={() => adjust.mutate(undefined)}>{t("common.save")}</Button>
          </>}
        </Stack>
      </Modal>
      <Modal opened={modal === "po"} onClose={close} title={t("inv.newPO")}>
        <Stack>
          <Alert color="blue">{t("inv.erpNote")}</Alert>
          <Select label={t("wo.part")} searchable data={partOpts} value={po.part_id} onChange={(v) => setPo({ ...po, part_id: v })} />
          <NumberInput label={t("common.quantity")} min={0.001} value={po.quantity} onChange={(v) => setPo({ ...po, quantity: v })} />
          <NumberInput label={t("inv.unitCost")} min={0} value={po.unit_price} onChange={(v) => setPo({ ...po, unit_price: v })} />
          <TextInput label={t("inv.externalRef")} value={po.external_reference} onChange={(e) => setPo({ ...po, external_reference: e.currentTarget.value })} />
          <Button disabled={!po.part_id} onClick={() => createPo.mutate(undefined)}>{t("common.create")}</Button>
        </Stack>
      </Modal>
      <Modal opened={modal === "wh"} onClose={close} title={t("wo.warehouse")}>
        <Stack>
          <TextInput label={t("common.code")} value={wh.code} onChange={(e) => setWh({ ...wh, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={wh.name} onChange={(e) => setWh({ ...wh, name: e.currentTarget.value })} />
          <Button disabled={!wh.code || !wh.name} onClick={() => createWh.mutate(undefined)}>{t("common.create")}</Button>
        </Stack>
      </Modal>
    </>
  );
}

export default function InventoryPage() {
  return <Guard perm="inventory.view"><Inventory /></Guard>;
}

