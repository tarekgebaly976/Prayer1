"use client";

import { Anchor, SimpleGrid, Stack, Tabs } from "@mantine/core";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "react-i18next";
import { Attachments } from "@/components/Attachments";
import { DataTable, KV, Loading, PageHeader, Section, StatusBadge } from "@/components/ui";
import { fmtDate, fmtMoney, fmtNum, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Page, Part, Warehouse } from "@/lib/types";

interface PartDetail extends Part { stock: { warehouse_id: string; warehouse: string; bin: string | null; on_hand: number; reserved: number; available: number }[];
  on_order: number; substitutes: { id: string; code: string; description: string }[]; used_on: { asset_id: string; code: string; name: string; quantity: number }[];
  active_reservations: { id: string; work_order_id: string; quantity: number; qty_issued: number }[] }
interface Txn { id: string; type: string; quantity: number; unit_cost: number; total_cost: number; balance_after: number; warehouse_id: string; work_order_id: string | null; reference: string | null; reason: string | null; created_at: string }

export default function PartDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { plant } = useSession();
  const q = useQ<PartDetail>(`/inventory/parts/${id}`);
  const tx = useQ<Page<Txn>>("/inventory/transactions", { part_id: id, limit: 200 });
  const whs = useQ<Warehouse[]>("/inventory/warehouses");
  const wmap = new Map((whs.data ?? []).map((w) => [w.id, w.code]));
  if (!q.data) return <Loading />;
  const p = q.data;
  return (
    <>
      <PageHeader title={`${p.code} · ${p.description}`}><StatusBadge value={p.criticality} /></PageHeader>
      <Tabs defaultValue="stock">
        <Tabs.List><Tabs.Tab value="stock">{t("inv.onHand")}</Tabs.Tab><Tabs.Tab value="ledger">{t("wo.transactions")}</Tabs.Tab><Tabs.Tab value="files">{t("common.attachments")}</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="stock" pt="md">
          <Stack>
            <SimpleGrid cols={{ base: 2, sm: 4 }}>
              <KV label="OEM P/N">{p.oem_part_number}</KV><KV label="Manufacturer">{p.manufacturer}</KV><KV label={t("inv.avgCost")}>{fmtMoney(p.average_cost, p.currency)}</KV>
              <KV label={t("inv.minMax")}>{fmtNum(p.min_qty)} / {fmtNum(p.max_qty)}</KV><KV label={t("inv.reorder")}>{fmtNum(p.reorder_point)}</KV>
              <KV label={t("inv.onOrder")}>{fmtNum(p.on_order)}</KV><KV label="Lead time">{p.lead_time_days ?? "—"} d</KV><KV label={t("inv.critical")}>{p.is_critical_spare ? "★" : "—"}</KV>
            </SimpleGrid>
            <DataTable rows={p.stock} rowKey={(s) => s.warehouse_id} columns={[{ key: "w", label: t("wo.warehouse"), render: (s) => s.warehouse }, { key: "b", label: "Bin", render: (s) => s.bin },
              { key: "o", label: t("inv.onHand"), render: (s) => fmtNum(s.on_hand) }, { key: "r", label: t("inv.reserved"), render: (s) => fmtNum(s.reserved) }, { key: "a", label: t("inv.available"), render: (s) => fmtNum(s.available) }]} />
            <Section title="Used on">{p.used_on.map((u) => <div key={u.asset_id}><Anchor component={Link} href={`/assets/${u.asset_id}`}>{u.code}</Anchor> {u.name} × {fmtNum(u.quantity)}</div>)}</Section>
            <Section title="Approved substitutes">{p.substitutes.map((s) => <div key={s.id}><Anchor component={Link} href={`/inventory/parts/${s.id}`}>{s.code}</Anchor> {s.description}</div>)}</Section>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="ledger" pt="md">
          <DataTable rows={tx.data?.items} columns={[
            { key: "d", label: t("common.date"), render: (x) => fmtDate(x.created_at, plant?.timezone, true) }, { key: "t", label: t("common.type"), render: (x) => x.type },
            { key: "w", label: t("wo.warehouse"), render: (x) => wmap.get(x.warehouse_id) }, { key: "q", label: t("common.quantity"), render: (x) => fmtNum(x.quantity) },
            { key: "c", label: t("inv.unitCost"), render: (x) => fmtNum(x.unit_cost) }, { key: "tc", label: t("common.total"), render: (x) => fmtMoney(x.total_cost, p.currency) },
            { key: "b", label: "Balance", render: (x) => fmtNum(x.balance_after) },
            { key: "r", label: "Ref", render: (x) => (x.work_order_id ? <Anchor component={Link} href={`/work-orders/${x.work_order_id}`}>WO</Anchor> : (x.reference ?? x.reason)) }]} />
        </Tabs.Panel>
        <Tabs.Panel value="files" pt="md"><Attachments entityType="part" entityId={p.id} /></Tabs.Panel>
      </Tabs>
    </>
  );
}
