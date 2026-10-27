"use client";

import { Alert, Button, FileInput, Group, Modal, Stack, Table, Text } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, download, downloadPost } from "@/lib/api";
import { useMut } from "@/lib/hooks";

type Kind = "pm_plans" | "lube_plans" | "pdm_plans" | "wo_history" | "parts_history";
interface Result { total: number; valid: number; invalid: number; plans?: number; new_lubricants?: number; errors: { row: number; code: string | null; errors: string[] }[] }

/** Excel/CSV import of a maintenance plan (PM, lubrication or condition monitoring): template → preview → import. */
export function PlanImport({ kind, title, opened, onClose, countLabel, help }: {
  kind: Kind; title: string; opened: boolean; onClose: () => void; countLabel?: string; help?: string;
}) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const close = () => { setFile(null); setRes(null); onClose(); };
  const preview = useMut(() => api<Result>("POST", `/imports/${kind}/preview`, fd()), { success: false, onDone: setRes });
  const commit = useMut(() => api<{ created: number }>("POST", `/imports/${kind}/commit`, fd()), { success: t("common.saved"), onDone: close });
  return (
    <Modal opened={opened} onClose={close} title={title} size="lg">
      <Stack>
        <Text size="sm" c="dimmed">{help ?? t("planImport.help")}</Text>
        <Button variant="subtle" onClick={() => void download(`/imports/templates/${kind}.xlsx`)}>{t("asset.template")}</Button>
        <FileInput label={t("common.file")} accept=".csv,.xlsx" clearable value={file} onChange={(f) => { setFile(f); setRes(null); }} />
        <Group>
          <Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
          <Button color="teal" disabled={!res || res.invalid > 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button>
        </Group>
        {res && (
          <>
            <Alert color={res.invalid ? "red" : "teal"}>
              {res.total} · {res.valid} {t("asset.valid")} · {res.invalid} {t("asset.invalid")}
              {res.plans !== undefined && <> · {res.plans} {countLabel ?? t("planImport.plans")}</>}
              {res.new_lubricants ? <> · {res.new_lubricants} {t("planImport.newLubricants")}</> : null}
            </Alert>
            {res.invalid > 0 && (
              <>
                <Button variant="light" size="xs" onClick={() => void downloadPost(`/imports/${kind}/errors.csv`, fd(), `${kind}_import_errors.csv`)}>{t("asset.errorsReport")}</Button>
                <Table><Table.Tbody>{res.errors.slice(0, 100).map((e) => (
                  <Table.Tr key={e.row}><Table.Td>{e.row}</Table.Td><Table.Td>{e.code}</Table.Td><Table.Td>{e.errors.join("; ")}</Table.Td></Table.Tr>))}</Table.Tbody></Table>
              </>
            )}
          </>
        )}
      </Stack>
    </Modal>
  );
}
