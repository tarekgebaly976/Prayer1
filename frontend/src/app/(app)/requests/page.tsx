"use client";

import { Button, Checkbox, Modal, Select, Stack, TextInput, Textarea } from "@mantine/core";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { AssetPicker, DataTable, PageHeader, Pager, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Page } from "@/lib/types";

export interface WReq { id: string; number: string; asset_id: string; title: string; description: string | null; symptoms: string | null;
  suggested_priority: string; is_breakdown: boolean; status: string; triage_note: string | null; work_order_id: string | null; created_at: string }

export function NewRequest({ opened, onClose, assetId }: { opened: boolean; onClose: () => void; assetId?: string }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ asset_id: assetId ?? null as string | null, title: "", symptoms: "", description: "", suggested_priority: "P3", is_breakdown: false });
  const m = useMut(() => post("/work-requests", f), { onDone: () => { onClose(); setF({ ...f, title: "", symptoms: "", description: "" }); } });
  return (
    <Modal opened={opened} onClose={onClose} title={t("req.new")} size="lg">
      <Stack>
        <AssetPicker value={f.asset_id} onChange={(v) => setF({ ...f, asset_id: v })} required />
        <TextInput label={t("wo.title")} required value={f.title} onChange={(e) => setF({ ...f, title: e.currentTarget.value })} name="req-title" />
        <Textarea label={t("wo.symptoms")} value={f.symptoms} onChange={(e) => setF({ ...f, symptoms: e.currentTarget.value })} autosize />
        <Textarea label={t("common.description")} value={f.description} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} autosize />
        <Select label={t("req.suggested")} data={["P1", "P2", "P3", "P4"]} value={f.suggested_priority} onChange={(v) => setF({ ...f, suggested_priority: v ?? "P3" })} allowDeselect={false} />
        <Checkbox color="red" label={t("req.breakdown")} checked={f.is_breakdown} onChange={(e) => setF({ ...f, is_breakdown: e.currentTarget.checked })} />
        <Button onClick={() => m.mutate(undefined)} loading={m.isPending} disabled={!f.asset_id || f.title.length < 3} className="tap-target">{t("common.submit")}</Button>
      </Stack>
    </Modal>
  );
}

function List() {
  const { t } = useTranslation();
  const sp = useSearchParams();
  const router = useRouter();
  const { can } = useSession();
  const [open, setOpen] = useState(sp.get("new") === "1");
  const [status, setStatus] = useState<string | null>(can("request.triage") ? "submitted" : null);
  const [offset, setOffset] = useState(0);
  const q = useQ<Page<WReq>>("/work-requests", { status, limit: 50, offset, mine: !can("wo.view") });
  return (
    <>
      <PageHeader title={t("nav.requests")} actions={<Button color="red" onClick={() => setOpen(true)}>{t("req.new")}</Button>}>
        <Select w={200} clearable value={status} onChange={setStatus} placeholder={t("common.status")}
          data={["submitted", "accepted", "rejected"].map((s) => ({ value: s, label: t(`status.${s}`) }))} />
      </PageHeader>
      <DataTable rows={q.data?.items} onRow={(r) => router.push(`/requests/${r.id}`)} columns={[
        { key: "n", label: "#", render: (r) => <span className="mono">{r.number}</span> },
        { key: "t", label: t("wo.title"), render: (r) => <>{r.is_breakdown && "🛑 "}{r.title}</> },
        { key: "p", label: t("req.suggested"), render: (r) => <StatusBadge value={r.suggested_priority} /> },
        { key: "s", label: t("common.status"), render: (r) => <StatusBadge value={r.status} /> },
        { key: "d", label: t("common.createdAt"), render: (r) => fmtDate(r.created_at, undefined, true) },
      ]} />
      <Pager page={q.data} setPage={(p) => setOffset((p - 1) * 50)} />
      <NewRequest opened={open} onClose={() => setOpen(false)} />
    </>
  );
}

export default function Requests() {
  return <Guard perm="request.create"><Suspense><List /></Suspense></Guard>;
}
