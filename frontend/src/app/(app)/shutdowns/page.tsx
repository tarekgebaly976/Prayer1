"use client";

import { Button, Modal, Stack, TextInput, Textarea } from "@mantine/core";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { DataTable, PageHeader, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, fromLocalInput, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";

export interface SD { id: string; code: string; name: string; scope: string | null; planned_start: string; planned_end: string; actual_start: string | null; actual_end: string | null; status: string; lessons_learned: string | null; completion_report: string | null }

function List() {
  const { t } = useTranslation();
  const router = useRouter();
  const { can, plant } = useSession();
  const q = useQ<SD[]>("/shutdowns");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ code: "", name: "", scope: "", planned_start: "", planned_end: "" });
  const m = useMut(() => post<SD>("/shutdowns", { ...f, scope: f.scope || null, planned_start: fromLocalInput(f.planned_start), planned_end: fromLocalInput(f.planned_end) }),
    { onDone: (s) => router.push(`/shutdowns/${s.id}`) });
  return (
    <>
      <PageHeader title={t("sd.list")} actions={can("shutdown.manage") ? <Button onClick={() => setOpen(true)}>{t("sd.new")}</Button> : null} />
      <DataTable rows={q.data} onRow={(s) => router.push(`/shutdowns/${s.id}`)} columns={[
        { key: "c", label: t("common.code"), render: (s) => s.code }, { key: "n", label: t("common.name"), render: (s) => s.name },
        { key: "s", label: t("common.start"), render: (s) => fmtDate(s.planned_start, plant?.timezone, true) }, { key: "e", label: t("common.end"), render: (s) => fmtDate(s.planned_end, plant?.timezone, true) },
        { key: "st", label: t("common.status"), render: (s) => <StatusBadge value={s.status} /> }]} />
      <Modal opened={open} onClose={() => setOpen(false)} title={t("sd.new")}>
        <Stack>
          <TextInput label={t("common.code")} value={f.code} onChange={(e) => setF({ ...f, code: e.currentTarget.value })} />
          <TextInput label={t("common.name")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
          <Textarea label="Scope" value={f.scope} onChange={(e) => setF({ ...f, scope: e.currentTarget.value })} />
          <TextInput type="datetime-local" label={t("common.start")} value={f.planned_start} onChange={(e) => setF({ ...f, planned_start: e.currentTarget.value })} />
          <TextInput type="datetime-local" label={t("common.end")} value={f.planned_end} onChange={(e) => setF({ ...f, planned_end: e.currentTarget.value })} />
          <Button disabled={!f.code || !f.name || !f.planned_start || !f.planned_end} onClick={() => m.mutate(undefined)}>{t("common.create")}</Button>
        </Stack>
      </Modal>
    </>
  );
}

export default function ShutdownsPage() {
  return <Guard perm="shutdown.view"><List /></Guard>;
}
