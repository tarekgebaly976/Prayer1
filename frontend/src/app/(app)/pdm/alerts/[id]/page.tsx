"use client";

import { Anchor, Button, Group, Paper, Stack, Textarea } from "@mantine/core";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { KV, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { CAlert } from "../../page";

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const router = useRouter();
  const { can } = useSession();
  const q = useQ<CAlert>(`/pdm/alerts/${id}`);
  const [defect, setDefect] = useState("");
  const [resolution, setResolution] = useState("");
  const ack = useMut(() => post(`/pdm/alerts/${id}/acknowledge`, { defect_description: defect || null }));
  const wo = useMut(() => post<{ work_order_id: string }>(`/pdm/alerts/${id}/work-order`), { onDone: (r) => router.push(`/work-orders/${r.work_order_id}`) });
  const resolve = useMut(() => post(`/pdm/alerts/${id}/resolve`, { resolution }));
  if (!q.data) return <Loading />;
  const a = q.data;
  return (
    <>
      <PageHeader title={a.message}><Group><StatusBadge value={a.severity} /><StatusBadge value={a.status} /></Group></PageHeader>
      <Paper withBorder p="md" maw={760}>
        <Stack>
          <KV label={t("common.createdAt")}>{fmtDate(a.created_at, undefined, true)}</KV>
          <KV label={t("common.asset")}><Anchor component={Link} href={`/assets/${a.asset_id}`}>→</Anchor></KV>
          <KV label="Recommended action">{a.recommended_action}</KV>
          <KV label={t("pdm.defect")}>{a.defect_description}</KV>
          {a.work_order_id && <Anchor component={Link} href={`/work-orders/${a.work_order_id}`}>→ {t("nav.workOrders")}</Anchor>}
          {a.resolution && <KV label={t("pdm.resolution")}>{a.resolution}</KV>}
          {a.status !== "resolved" && (
            <>
              {can("pdm.alert_manage") && <Textarea label={t("pdm.defect")} value={defect} onChange={(e) => setDefect(e.currentTarget.value)} />}
              <Group>
                {can("pdm.alert_manage") && <Button variant="light" onClick={() => ack.mutate(undefined)}>{t("pdm.acknowledge")}</Button>}
                {can("wo.create") && !a.work_order_id && <Button onClick={() => wo.mutate(undefined)} loading={wo.isPending}>{t("pdm.createWo")}</Button>}
              </Group>
              {can("pdm.alert_manage") && (
                <Group align="end">
                  <Textarea label={t("pdm.resolution")} value={resolution} onChange={(e) => setResolution(e.currentTarget.value)} style={{ flex: 1 }} />
                  <Button color="teal" disabled={resolution.length < 5} onClick={() => resolve.mutate(undefined)}>{t("pdm.resolve")}</Button>
                </Group>
              )}
            </>
          )}
        </Stack>
      </Paper>
    </>
  );
}
