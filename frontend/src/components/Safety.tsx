"use client";

import { Alert, Badge, Button, Checkbox, Group, MultiSelect, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { post } from "@/lib/api";
import { fmtDate, fromLocalInput, toLocalInput, useMut } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { LotoPoint, WODetail } from "@/lib/types";

export const PERMIT_TYPES = ["cold_work", "hot_work", "electrical", "confined_space", "work_at_height", "excavation", "lifting", "chemical"];
const ENERGY_TYPES = ["electrical", "mechanical", "hydraulic", "pneumatic", "steam", "thermal", "chemical", "gravity", "other"];

/** Permit details + supervisor sign-off. */
export function PermitSignoff({ wo }: { wo: WODetail["work_order"] }) {
  const { t } = useTranslation();
  const { can } = useSession();
  const [f, setF] = useState({ ref: wo.permit_reference ?? "", types: wo.permit_types ? wo.permit_types.split(",") : [], until: toLocalInput(wo.permit_valid_until) });
  const finished = ["closed", "cancelled"].includes(wo.status);
  const disabled = !can("wo.safety_signoff") || finished;
  const sign = useMut(() => post(`/work-orders/${wo.id}/safety-signoff`, {
    permit_reference: f.ref || null, permit_types: f.types, permit_valid_until: fromLocalInput(f.until),
  }));
  return (
    <Stack gap="xs">
      <Group align="end" wrap="wrap">
        <TextInput label={t("wo.permitRef")} value={f.ref} onChange={(e) => setF({ ...f, ref: e.currentTarget.value })} disabled={disabled} />
        <MultiSelect label={t("safety.permitTypes")} w={300} value={f.types} onChange={(v) => setF({ ...f, types: v })} disabled={disabled}
          data={PERMIT_TYPES.map((p) => ({ value: p, label: t(`safety.types.${p}`) }))} />
        <TextInput type="datetime-local" label={t("safety.validUntil")} value={f.until} onChange={(e) => setF({ ...f, until: e.currentTarget.value })} disabled={disabled} />
      </Group>
      <Button w="fit-content" disabled={disabled} loading={sign.isPending} onClick={() => sign.mutate(undefined)}>{t("wo.safetySign")}</Button>
    </Stack>
  );
}

/** LOTO isolation register: each point is locked when recorded, verified, and released before completion. */
export function LotoRegister({ woId, rows, status }: { woId: string; rows: LotoPoint[]; status: string }) {
  const { t } = useTranslation();
  const { can, plant } = useSession();
  const empty = { point: "", energy_type: "electrical", lock_number: "", zero_energy_verified: false };
  const [f, setF] = useState(empty);
  const allowed = (can("wo.execute") || can("wo.safety_signoff")) && !["closed", "cancelled"].includes(status);
  const canAdd = allowed && status !== "completed";
  const apply = useMut(() => post(`/work-orders/${woId}/loto`, { ...f, lock_number: f.lock_number || null }), { onDone: () => setF(empty) });
  const verify = useMut((id: string) => post(`/work-orders/${woId}/loto/${id}/verify`));
  const remove = useMut((id: string) => post(`/work-orders/${woId}/loto/${id}/remove`));
  const on = rows.filter((r) => !r.removed_at).length;
  return (
    <Stack gap="xs">
      <Text size="sm" c="dimmed">{t("safety.lotoHint")}</Text>
      {canAdd && (
        <Group align="end" wrap="wrap">
          <TextInput label={t("safety.point")} w={260} value={f.point} onChange={(e) => setF({ ...f, point: e.currentTarget.value })} />
          <Select label={t("safety.energy")} w={150} value={f.energy_type} onChange={(v) => setF({ ...f, energy_type: v ?? "electrical" })} allowDeselect={false}
            data={ENERGY_TYPES.map((e) => ({ value: e, label: t(`safety.energies.${e}`) }))} />
          <TextInput label={t("safety.lock")} w={120} value={f.lock_number} onChange={(e) => setF({ ...f, lock_number: e.currentTarget.value })} />
          <Checkbox label={t("safety.verified")} checked={f.zero_energy_verified} onChange={(e) => setF({ ...f, zero_energy_verified: e.currentTarget.checked })} />
          <Button disabled={f.point.trim().length < 2} loading={apply.isPending} onClick={() => apply.mutate(undefined)}>{t("safety.applyLock")}</Button>
        </Group>
      )}
      {on > 0 && <Alert color="orange">{t("safety.locksOn", { n: on })}</Alert>}
      {rows.length === 0 ? <Text size="sm" c="dimmed">{t("safety.noLocks")}</Text> : (
        <Table striped>
          <Table.Thead><Table.Tr><Table.Th>{t("safety.point")}</Table.Th><Table.Th>{t("safety.energy")}</Table.Th><Table.Th>{t("safety.lock")}</Table.Th>
            <Table.Th>{t("safety.appliedBy")}</Table.Th><Table.Th>{t("safety.removedBy")}</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {rows.map((r) => (
              <Table.Tr key={r.id}>
                <Table.Td>{r.point} {r.zero_energy_verified ? <Badge color="teal" size="xs">✓ 0 E</Badge> : <Badge color="red" size="xs">!</Badge>}</Table.Td>
                <Table.Td>{t(`safety.energies.${r.energy_type}`)}</Table.Td><Table.Td className="mono">{r.lock_number ?? "—"}</Table.Td>
                <Table.Td>{r.applied_by} · {fmtDate(r.applied_at, plant?.timezone, true)}</Table.Td>
                <Table.Td>{r.removed_at ? `${r.removed_by} · ${fmtDate(r.removed_at, plant?.timezone, true)}` : "—"}</Table.Td>
                <Table.Td>{allowed && !r.removed_at && (<Group gap={4} wrap="nowrap">
                  {!r.zero_energy_verified && <Button size="xs" variant="light" onClick={() => verify.mutate(r.id)}>{t("safety.verify")}</Button>}
                  <Button size="xs" variant="subtle" color="orange" onClick={() => remove.mutate(r.id)}>{t("safety.remove")}</Button></Group>)}</Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
