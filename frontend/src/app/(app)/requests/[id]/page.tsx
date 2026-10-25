"use client";

import { Anchor, Button, Group, Paper, Select, SimpleGrid, Stack, Text, Textarea } from "@mantine/core";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KV, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset } from "@/lib/types";
import type { WReq } from "../page";

export default function RequestDetail() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can } = useSession();
  const rq = useQ<WReq>(`/work-requests/${id}`);
  const r = rq.data;
  const asset = useQ<Asset>(r ? `/assets/${r.asset_id}` : null);
  const [note, setNote] = useState("");
  const [type, setType] = useState("corrective");
  const [prio, setPrio] = useState<string | null>(null);
  const triage = useMut((accept: boolean) => post(`/work-requests/${id}/triage`, { accept, note: note || null, type, priority: prio }));
  if (rq.isLoading) return <Loading />;
  if (!r) return <Text c="dimmed">{t("common.noData")}</Text>;
  return (
    <>
      <PageHeader title={`${r.number} · ${r.title}`}><Group><StatusBadge value={r.status} />{r.is_breakdown && <StatusBadge value="emergency" />}</Group></PageHeader>
      <Paper withBorder p="md" maw={800}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <KV label={t("common.asset")}>{asset.data ? <Anchor component={Link} href={`/assets/${asset.data.id}`}>{asset.data.code} — {asset.data.name}</Anchor> : "…"}</KV>
            <KV label={t("req.suggested")}><StatusBadge value={r.suggested_priority} /></KV>
            <KV label={t("common.createdAt")}>{fmtDate(r.created_at, undefined, true)}</KV>
          </SimpleGrid>
          <KV label={t("wo.symptoms")}>{r.symptoms}</KV>
          <KV label={t("common.description")}>{r.description}</KV>
          {r.triage_note && <KV label={t("req.triage")}>{r.triage_note}</KV>}
          {r.work_order_id && <Anchor component={Link} href={`/work-orders/${r.work_order_id}`}>→ {t("nav.workOrders")}</Anchor>}
          {r.status === "submitted" && can("request.triage") && (
            <Stack>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select label={t("common.type")} value={type} onChange={(v) => setType(v ?? "corrective")} allowDeselect={false}
                  data={["corrective", "emergency", "inspection", "improvement"].map((x) => ({ value: x, label: t(`woType.${x}`) }))} />
                <Select label={t("common.priority")} value={prio} onChange={setPrio} clearable data={["P1", "P2", "P3", "P4"]} />
              </SimpleGrid>
              <Textarea label={t("common.notes")} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
              <Group>
                <Button onClick={() => triage.mutate(true)} loading={triage.isPending}>{t("req.accept")}</Button>
                <Button color="red" variant="light" disabled={!note} onClick={() => triage.mutate(false)}>{t("req.reject")}</Button>
              </Group>
            </Stack>
          )}
        </Stack>
      </Paper>
    </>
  );
}
