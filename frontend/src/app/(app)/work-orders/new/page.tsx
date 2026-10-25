"use client";

import { Button, Checkbox, Group, NumberInput, Paper, Select, SimpleGrid, Stack, TextInput, Textarea } from "@mantine/core";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { AssetPicker, PageHeader } from "@/components/ui";
import { post } from "@/lib/api";
import { fromLocalInput, useMut } from "@/lib/hooks";
import type { WorkOrder } from "@/lib/types";

const TYPES = ["corrective", "emergency", "inspection", "improvement", "preventive", "predictive", "shutdown"];

function Form() {
  const { t } = useTranslation();
  const router = useRouter();
  const sp = useSearchParams();
  const [f, setF] = useState({ asset_id: sp.get("asset"), type: "corrective", title: "", priority: "P3", description: "", symptoms: "",
    due_date: "", planned_start: "", planned_end: "", estimated_hours: "" as number | string, requires_loto: false, requires_permit: false,
    requires_testing: false, safety_requirements: "" });
  const set = (k: keyof typeof f, v: unknown) => setF((x) => ({ ...x, [k]: v }));
  const m = useMut(() => post<WorkOrder>("/work-orders", {
    asset_id: f.asset_id, type: f.type, title: f.title, priority: f.priority, description: f.description || null, symptoms: f.symptoms || null,
    due_date: f.due_date || null, planned_start: fromLocalInput(f.planned_start), planned_end: fromLocalInput(f.planned_end),
    estimated_hours: f.estimated_hours === "" ? null : Number(f.estimated_hours), requires_loto: f.requires_loto, requires_permit: f.requires_permit,
    requires_testing: f.requires_testing, safety_requirements: f.safety_requirements || null,
  }), { onDone: (w) => router.push(`/work-orders/${w.id}`) });
  return (
    <>
      <PageHeader title={t("wo.new")} />
      <Paper withBorder p="md" maw={900}>
        <form onSubmit={(e) => { e.preventDefault(); m.mutate(undefined); }}>
          <Stack>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <AssetPicker value={f.asset_id} onChange={(v) => set("asset_id", v)} required />
              <Select label={t("common.type")} value={f.type} onChange={(v) => set("type", v)} allowDeselect={false} data={TYPES.map((x) => ({ value: x, label: t(`woType.${x}`) }))} />
              <TextInput label={t("wo.title")} required minLength={3} value={f.title} onChange={(e) => set("title", e.currentTarget.value)} name="title" />
              <Select label={t("common.priority")} value={f.priority} onChange={(v) => set("priority", v)} allowDeselect={false} data={["P1", "P2", "P3", "P4"]} disabled={f.type === "emergency"} />
              <TextInput type="date" label={t("common.dueDate")} value={f.due_date} onChange={(e) => set("due_date", e.currentTarget.value)} />
              <NumberInput label={t("wo.estHours")} min={0} value={f.estimated_hours} onChange={(v) => set("estimated_hours", v)} />
              <TextInput type="datetime-local" label={t("wo.plannedStart")} value={f.planned_start} onChange={(e) => set("planned_start", e.currentTarget.value)} />
              <TextInput type="datetime-local" label={t("wo.plannedEnd")} value={f.planned_end} onChange={(e) => set("planned_end", e.currentTarget.value)} />
            </SimpleGrid>
            <Textarea label={t("wo.symptoms")} value={f.symptoms} onChange={(e) => set("symptoms", e.currentTarget.value)} autosize minRows={2} />
            <Textarea label={t("common.description")} value={f.description} onChange={(e) => set("description", e.currentTarget.value)} autosize minRows={3} />
            <Group>
              <Checkbox label={t("wo.loto")} checked={f.requires_loto} onChange={(e) => set("requires_loto", e.currentTarget.checked)} />
              <Checkbox label={t("wo.permit")} checked={f.requires_permit} onChange={(e) => set("requires_permit", e.currentTarget.checked)} />
              <Checkbox label={t("wo.testing")} checked={f.requires_testing} onChange={(e) => set("requires_testing", e.currentTarget.checked)} />
            </Group>
            <Textarea label={t("wo.safety")} value={f.safety_requirements} onChange={(e) => set("safety_requirements", e.currentTarget.value)} autosize />
            <Group><Button type="submit" loading={m.isPending} disabled={!f.asset_id || f.title.length < 3}>{t("common.create")}</Button></Group>
          </Stack>
        </form>
      </Paper>
    </>
  );
}

export default function NewWO() {
  return <Guard perm="wo.create"><Suspense><Form /></Suspense></Guard>;
}
