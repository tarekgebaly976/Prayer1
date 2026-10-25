"use client";

import { Alert, Anchor, Button, Group, Paper, SimpleGrid, Stack, Text, Textarea } from "@mantine/core";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KV, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";

interface WO { id: string; number: string; title: string; status: string }
interface H { id: string; shift_date: string; status: string; summary: string; outgoing_user_id: string; outstanding_breakdowns: string | null; pending_work: string | null;
  safety_concerns: string | null; equipment_abnormalities: string | null; pending_permits: string | null; critical_risks: string | null; supervisor_comment: string | null;
  open_breakdowns_now: WO[]; open_breakdowns_at_submit: WO[] }

export default function HandoverDetail() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const { can, me } = useSession();
  const q = useQ<H>(`/shifts/handovers/${id}`);
  const [comment, setComment] = useState("");
  const submit = useMut(() => post(`/shifts/handovers/${id}/submit`));
  const confirm = useMut(() => post(`/shifts/handovers/${id}/confirm`, { comment: comment || null }));
  if (!q.data) return <Loading />;
  const h = q.data;
  const wos = (l: WO[]) => l.length ? l.map((w) => <div key={w.id}><Anchor component={Link} href={`/work-orders/${w.id}`} size="sm">{w.number}</Anchor> {w.title} <StatusBadge value={w.status} size="xs" /></div>) : "—";
  return (
    <>
      <PageHeader title={`${t("shift.handovers")} · ${h.shift_date}`}><StatusBadge value={h.status} /></PageHeader>
      <Paper withBorder p="md" maw={900}>
        <Stack>
          <KV label={t("shift.summary")}><Text style={{ whiteSpace: "pre-wrap" }}>{h.summary}</Text></KV>
          {h.safety_concerns && <Alert color="red" title={t("shift.safetyConcerns")}>{h.safety_concerns}</Alert>}
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <KV label={t("shift.outstanding")}>{h.outstanding_breakdowns}</KV><KV label={t("shift.pendingWork")}>{h.pending_work}</KV>
            <KV label={t("shift.abnormalities")}>{h.equipment_abnormalities}</KV><KV label={t("shift.pendingPermits")}>{h.pending_permits}</KV>
            <KV label={t("shift.risks")}>{h.critical_risks}</KV><KV label={t("shift.openNow")}>{wos(h.open_breakdowns_now)}</KV>
          </SimpleGrid>
          {h.status !== "draft" && <KV label="At submission">{wos(h.open_breakdowns_at_submit)}</KV>}
          {h.supervisor_comment && <KV label={t("common.comment")}>{h.supervisor_comment}</KV>}
          {h.status === "draft" && h.outgoing_user_id === me?.id && <Group><Button onClick={() => submit.mutate(undefined)}>{t("common.submit")}</Button></Group>}
          {h.status === "submitted" && can("handover.confirm") && h.outgoing_user_id !== me?.id && (
            <Group align="end"><Textarea label={t("common.comment")} value={comment} onChange={(e) => setComment(e.currentTarget.value)} style={{ flex: 1 }} />
              <Button color="teal" onClick={() => confirm.mutate(undefined)}>{t("common.confirm")}</Button></Group>
          )}
        </Stack>
      </Paper>
    </>
  );
}
