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
import type { FailureCode, Page } from "@/lib/types";

export interface WReq { id: string; number: string; asset_id: string; title: string; description: string | null; symptoms: string | null;
  suggested_priority: string; is_breakdown: boolean; status: string; triage_note: string | null; work_order_id: string | null; created_at: string }

export function NewRequest({ opened, onClose, assetId }: { opened: boolean; onClose: () => void; assetId?: string }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ asset_id: assetId ?? null as string | null, title: "", description: "", suggested_priority: "P3", is_breakdown: false,
    symptom_code_id: null as string | null, problem_code_id: null as string | null });
  const [ownTitle, setOwnTitle] = useState(false);
  // Standard lists: the symptom (what is seen or heard) and, if known, the failure mode of this equipment's type.
  const codes = useQ<FailureCode[]>(opened ? "/failure-codes" : null, { asset_id: f.asset_id });
  const symptoms = (codes.data ?? []).filter((c) => c.kind === "symptom");
  const modes = (codes.data ?? []).filter((c) => c.kind === "problem");
  const byId = new Map((codes.data ?? []).map((c) => [c.id, c]));
  const autoTitle = [f.symptom_code_id && byId.get(f.symptom_code_id)?.description, f.problem_code_id && byId.get(f.problem_code_id)?.description].filter(Boolean).join(" – ");
  const title = ownTitle ? f.title : autoTitle;
  const needSymptom = symptoms.length > 0;
  const modeOpts = (() => {
    const opt = (c: FailureCode) => ({ value: c.id, label: `${c.description}${c.equipment_type ? ` · ${c.equipment_type}` : ""}` });
    const mine = modes.filter((c) => c.suggested);
    if (!mine.length) return modes.map(opt);
    return [{ group: t("fm.forType", { type: mine[0]?.equipment_type ?? "" }), items: mine.map(opt) }, { group: t("fm.other"), items: modes.filter((c) => !c.suggested).map(opt) }];
  })();
  const m = useMut(() => post("/work-requests", { ...f, title, symptoms: f.symptom_code_id ? byId.get(f.symptom_code_id)?.description ?? null : null }), {
    onDone: () => { onClose(); setOwnTitle(false); setF({ ...f, title: "", description: "", symptom_code_id: null, problem_code_id: null }); } });
  return (
    <Modal opened={opened} onClose={onClose} title={t("req.new")} size="lg">
      <Stack>
        <AssetPicker value={f.asset_id} onChange={(v) => setF({ ...f, asset_id: v })} required />
        {needSymptom && <Select label={t("wo.symptoms")} required searchable placeholder={t("fm.pickSymptom")} value={f.symptom_code_id}
          onChange={(v) => setF({ ...f, symptom_code_id: v })} data={symptoms.map((c) => ({ value: c.id, label: c.description }))} />}
        {modes.length > 0 && <Select label={t("fm.suspected")} description={t("fm.suspectedHint")} searchable clearable value={f.problem_code_id}
          onChange={(v) => setF({ ...f, problem_code_id: v })} data={modeOpts} />}
        <TextInput label={t("wo.title")} required value={title} name="req-title" description={!ownTitle && autoTitle ? t("fm.autoTitle") : undefined}
          onChange={(e) => { setOwnTitle(true); setF({ ...f, title: e.currentTarget.value }); }} />
        <Textarea label={t("common.description")} value={f.description} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} autosize />
        <Select label={t("req.suggested")} data={["P1", "P2", "P3", "P4"]} value={f.suggested_priority} onChange={(v) => setF({ ...f, suggested_priority: v ?? "P3" })} allowDeselect={false} />
        <Checkbox color="red" label={t("req.breakdown")} checked={f.is_breakdown} onChange={(e) => setF({ ...f, is_breakdown: e.currentTarget.checked })} />
        <Button onClick={() => m.mutate(undefined)} loading={m.isPending} disabled={!f.asset_id || title.length < 3 || (needSymptom && !f.symptom_code_id)} className="tap-target">{t("common.submit")}</Button>
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
