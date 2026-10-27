"use client";

import { Alert, Anchor, Button, Group, NumberInput, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import Link from "next/link";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { del, download, post } from "@/lib/api";
import { fmtDate, fmtMoney, fmtNum, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, Page, Part, PartUsed } from "@/lib/types";

/** Searchable spare-part picker that queries the server, so it works with thousands of items. */
export function PartSearch({ value, onChange, label }: { value: string | null; onChange: (id: string | null, part?: Part) => void; label: string }) {
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 300);
  const res = useQ<Page<Part>>("/inventory/parts", { q: q || undefined, limit: 30 });
  const items = res.data?.items ?? [];
  return (
    <Select label={label} searchable clearable w={340} value={value} searchValue={search} onSearchChange={setSearch} filter={({ options }) => options}
      onChange={(v) => onChange(v, items.find((p) => p.id === v))} data={items.map((p) => ({ value: p.id, label: `${p.code} — ${p.description}` }))} />
  );
}

/** Server-side searchable asset picker (works with thousands of assets). */
export function AssetSearch({ value, onChange, label }: { value: string | null; onChange: (id: string | null) => void; label: string }) {
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 300);
  const res = useQ<Page<Asset>>("/assets", { q: q || undefined, limit: 30 });
  return (
    <Select label={label} searchable clearable w={340} value={value} searchValue={search} onSearchChange={setSearch} filter={({ options }) => options}
      onChange={onChange} data={(res.data?.items ?? []).map((a) => ({ value: a.id, label: `${a.code} — ${a.name}` }))} />
  );
}

interface UsageReport { total: number; total_cost: number; items: PartUsed[]; by_part: { part_code: string | null; description: string; uom: string; quantity: number; cost: number }[] }

/** Parts used per work order and machine, with Excel export. */
export function PartsUsedReport() {
  const { t } = useTranslation();
  const { plant, can } = useSession();
  const [f, setF] = useState({ asset_id: null as string | null, part_id: null as string | null, start: "", end: "" });
  const [offset, setOffset] = useState(0);
  const query = { asset_id: f.asset_id ?? undefined, part_id: f.part_id ?? undefined, start: f.start || undefined, end: f.end || undefined };
  const rep = useQ<UsageReport>("/reports/parts-used", { ...query, limit: 100, offset });
  const cur = plant?.currency ?? "SAR";
  return (
    <Stack>
      <Group align="end" wrap="wrap">
        <AssetSearch label={t("used.machine")} value={f.asset_id} onChange={(v) => { setF({ ...f, asset_id: v }); setOffset(0); }} />
        <PartSearch label={t("used.part")} value={f.part_id} onChange={(v) => { setF({ ...f, part_id: v }); setOffset(0); }} />
        <TextInput type="date" label={t("used.from")} value={f.start} onChange={(e) => setF({ ...f, start: e.currentTarget.value })} />
        <TextInput type="date" label={t("used.to")} value={f.end} onChange={(e) => setF({ ...f, end: e.currentTarget.value })} />
        {can("report.export") && <Button variant="light" onClick={() => void download("/exports/parts-used.xlsx", query, "parts_used.xlsx")}>{t("common.export")} (Excel)</Button>}
      </Group>
      <Alert color="blue">{rep.data?.total ?? 0} · {t("used.total")}: {fmtMoney(rep.data?.total_cost ?? 0, cur)}</Alert>
      <Table striped>
        <Table.Thead><Table.Tr>
          <Table.Th>{t("common.date")}</Table.Th><Table.Th>{t("wo.number")}</Table.Th><Table.Th>{t("common.asset")}</Table.Th><Table.Th>{t("common.code")}</Table.Th>
          <Table.Th>{t("common.description")}</Table.Th><Table.Th>{t("common.quantity")}</Table.Th><Table.Th>{t("common.cost")}</Table.Th>
        </Table.Tr></Table.Thead>
        <Table.Tbody>
          {(rep.data?.items ?? []).map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>{fmtDate(r.used_on, plant?.timezone)}</Table.Td>
              <Table.Td><Anchor component={Link} href={`/work-orders/${r.work_order_id}`} className="mono">{r.work_order}</Anchor></Table.Td>
              <Table.Td>{r.asset_code} — {r.asset_name}</Table.Td><Table.Td className="mono">{r.part_code ?? "—"}</Table.Td><Table.Td>{r.description}</Table.Td>
              <Table.Td>{fmtNum(r.quantity)} {r.uom}</Table.Td><Table.Td>{fmtMoney(r.total_cost, cur)}</Table.Td>
            </Table.Tr>))}
        </Table.Tbody>
      </Table>
      {(rep.data?.total ?? 0) > 100 && (
        <Group><Button size="xs" variant="default" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>{t("common.prev")}</Button>
          <Button size="xs" variant="default" disabled={offset + 100 >= (rep.data?.total ?? 0)} onClick={() => setOffset(offset + 100)}>{t("common.next")}</Button></Group>
      )}
      {(rep.data?.by_part.length ?? 0) > 0 && (
        <>
          <Text fw={600}>{t("used.byPart")}</Text>
          <Table><Table.Tbody>{rep.data!.by_part.slice(0, 10).map((b) => (
            <Table.Tr key={`${b.part_code}-${b.description}`}><Table.Td className="mono">{b.part_code ?? "—"}</Table.Td><Table.Td>{b.description}</Table.Td>
              <Table.Td>{fmtNum(b.quantity)} {b.uom}</Table.Td><Table.Td>{fmtMoney(b.cost, cur)}</Table.Td></Table.Tr>))}</Table.Tbody></Table>
        </>
      )}
    </Stack>
  );
}

/** Parts fitted on a work order, recorded without moving stock (store not connected). */
export function PartsUsed({ woId, rows, currency, editable }: { woId: string; rows: PartUsed[]; currency: string; editable: boolean }) {
  const { t } = useTranslation();
  const { can, plant } = useSession();
  const empty = { part_id: null as string | null, description: "", quantity: 1 as number | string, uom: "", unit_cost: "" as number | string, note: "" };
  const [f, setF] = useState(empty);
  const allowed = editable && (can("wo.execute") || can("inventory.transact"));
  const add = useMut(() => post(`/work-orders/${woId}/parts-used`, {
    part_id: f.part_id, description: f.part_id ? null : f.description || null, quantity: Number(f.quantity), uom: f.uom || null,
    unit_cost: f.unit_cost === "" ? null : Number(f.unit_cost), note: f.note || null,
  }), { onDone: () => setF(empty) });
  const remove = useMut((id: string) => del(`/work-orders/${woId}/parts-used/${id}`));
  const total = rows.reduce((s, r) => s + Number(r.total_cost), 0);
  return (
    <Stack>
      <Text fw={600}>{t("used.title")}</Text>
      {allowed && (
        <>
          <Text size="sm" c="dimmed">{t("used.hint")}</Text>
          <Group align="end" wrap="wrap">
            <PartSearch label={t("used.part")} value={f.part_id} onChange={(id, p) => setF({ ...f, part_id: id, uom: p?.uom ?? f.uom })} />
            {!f.part_id && <TextInput label={t("used.other")} w={240} value={f.description} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} />}
            <NumberInput label={t("common.quantity")} w={100} min={0.001} value={f.quantity} onChange={(v) => setF({ ...f, quantity: v })} />
            <TextInput label={t("common.unit")} w={80} value={f.uom} onChange={(e) => setF({ ...f, uom: e.currentTarget.value })} />
            <NumberInput label={t("used.unitCost")} w={170} min={0} value={f.unit_cost} onChange={(v) => setF({ ...f, unit_cost: v })} />
            <TextInput label={t("common.notes")} w={200} value={f.note} onChange={(e) => setF({ ...f, note: e.currentTarget.value })} />
            <Button loading={add.isPending} disabled={(!f.part_id && !f.description.trim()) || !(Number(f.quantity) > 0)} onClick={() => add.mutate(undefined)}>
              {t("used.add")}
            </Button>
          </Group>
        </>
      )}
      {rows.length === 0 ? <Alert color="gray">{t("used.none")}</Alert> : (
        <Table striped>
          <Table.Thead><Table.Tr>
            <Table.Th>{t("common.date")}</Table.Th><Table.Th>{t("common.code")}</Table.Th><Table.Th>{t("common.description")}</Table.Th>
            <Table.Th>{t("common.quantity")}</Table.Th><Table.Th>{t("common.cost")}</Table.Th><Table.Th>{t("common.notes")}</Table.Th><Table.Th />
          </Table.Tr></Table.Thead>
          <Table.Tbody>
            {rows.map((r) => (
              <Table.Tr key={r.id}>
                <Table.Td>{fmtDate(r.used_on, plant?.timezone)}</Table.Td><Table.Td className="mono">{r.part_code ?? "—"}</Table.Td><Table.Td>{r.description}</Table.Td>
                <Table.Td>{fmtNum(r.quantity)} {r.uom}</Table.Td><Table.Td>{fmtMoney(r.total_cost, currency)}</Table.Td><Table.Td>{r.note}</Table.Td>
                <Table.Td>{allowed && <Button size="xs" variant="subtle" color="red" onClick={() => remove.mutate(r.id)}>{t("common.delete")}</Button>}</Table.Td>
              </Table.Tr>))}
            <Table.Tr><Table.Td colSpan={4} fw={700}>{t("used.total")}</Table.Td><Table.Td fw={700}>{fmtMoney(total, currency)}</Table.Td><Table.Td colSpan={2} /></Table.Tr>
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
