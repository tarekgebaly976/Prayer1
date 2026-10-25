"use client";

import { Anchor, Button, FileButton, Group, Select, Stack, Text } from "@mantine/core";
import { IconUpload } from "@tabler/icons-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, download } from "@/lib/api";
import { fmtDate, useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";

interface Att { id: string; filename: string; category: string; size_bytes: number; created_at: string }

export function Attachments({ entityType, entityId, defaultCategory = "document" }: { entityType: string; entityId: string; defaultCategory?: string }) {
  const { t } = useTranslation();
  const { can } = useSession();
  const [category, setCategory] = useState<string>(defaultCategory);
  const q = useQ<Att[]>("/attachments", { entity_type: entityType, entity_id: entityId });
  const up = useMut((f: File) => {
    const fd = new FormData();
    fd.append("entity_type", entityType);
    fd.append("entity_id", entityId);
    fd.append("category", category);
    fd.append("file", f);
    return api("POST", "/attachments", fd);
  });
  return (
    <Stack gap="xs">
      {can("attachment.upload") && (
        <Group gap="xs">
          <Select size="xs" w={140} value={category} onChange={(v) => v && setCategory(v)} allowDeselect={false}
            data={["photo", "manual", "drawing", "report", "certificate", "document"]} aria-label={t("common.category")} />
          <FileButton onChange={(f) => f && up.mutate(f)} accept="image/png,image/jpeg,image/webp,application/pdf,.xlsx,.docx,.dwg,.dxf,.csv,.txt" capture={category === "photo" ? "environment" : undefined}>
            {(props) => <Button size="xs" leftSection={<IconUpload size={14} />} loading={up.isPending} {...props}>{t("common.upload")}</Button>}
          </FileButton>
        </Group>
      )}
      {(q.data ?? []).length === 0 ? <Text size="sm" c="dimmed">{t("common.noData")}</Text> : (q.data ?? []).map((a) => (
        <Group key={a.id} justify="space-between" gap="xs">
          <Anchor size="sm" onClick={() => void download(`/attachments/${a.id}/download`, undefined, a.filename)}>{a.filename}</Anchor>
          <Text size="xs" c="dimmed">{a.category} · {(a.size_bytes / 1024).toFixed(0)} KB · {fmtDate(a.created_at)}</Text>
        </Group>
      ))}
    </Stack>
  );
}
