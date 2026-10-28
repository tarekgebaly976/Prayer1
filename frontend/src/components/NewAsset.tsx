"use client";

import { Button, Modal, Select, SimpleGrid, Stack, TextInput } from "@mantine/core";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { post } from "@/lib/api";
import { useMut, useQ } from "@/lib/hooks";
import type { Asset, Page } from "@/lib/types";
import { DeptSelect } from "./ui";

export const LEVELS = ["production_line", "unit", "assembly", "sub_assembly", "component"];

/** Create one asset. `parent` pre-fills the department and the parent (e.g. the equipment a new measurement point is on). */
export function NewAsset({ opened, onClose, onCreated, parent }: { opened: boolean; onClose: () => void; onCreated?: (a: Asset) => void; parent?: Asset | null }) {
  const { t } = useTranslation();
  const router = useRouter();
  const childLevel = parent ? LEVELS[Math.min(LEVELS.indexOf(parent.level) + 1, LEVELS.length - 1)] ?? "component" : "production_line";
  const [f, setF] = useState({ code: "", name: "", name_ar: "", department_id: parent?.department_id ?? null as string | null, parent_id: parent?.id ?? null as string | null, level: childLevel,
    criticality: "C", oem: "", model: "", serial_number: "", install_date: "", location: "", description: "" });
  const parents = useQ<Page<Asset>>(f.department_id ? "/assets" : null, { department_id: f.department_id, limit: 500 });
  const m = useMut(() => post<Asset>("/assets", { ...f, name_ar: f.name_ar || null, install_date: f.install_date || null, oem: f.oem || null, model: f.model || null,
    serial_number: f.serial_number || null, location: f.location || null, description: f.description || null }), { onDone: (a) => { onClose(); if (onCreated) onCreated(a); else router.push(`/assets/${a.id}`); } });
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

