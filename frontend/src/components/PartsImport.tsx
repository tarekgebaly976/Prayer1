"use client";

import { Alert, Button, FileInput, Group, Stack, Text } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, download, downloadPost } from "@/lib/api";
import { useMut } from "@/lib/hooks";

interface Result { total: number; valid: number; invalid: number; errors: { row: number; errors: string[] }[]; warnings: { row: number; warnings: string[] }[] }

/** Spare parts import (Excel/CSV): template, preview, then commit. Optional opening stock per store. */
export function PartsImport({ onDone }: { onDone?: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const preview = useMut(() => api<Result>("POST", "/imports/parts/preview", fd()), { success: false, onDone: setRes });
  const commit = useMut(() => api("POST", "/imports/parts/commit", fd()), { onDone: () => { setFile(null); setRes(null); onDone?.(); } });
  return (
    <Stack maw={700}>
      <Text size="sm" c="dimmed">{t("inv.importHelp")}</Text>
      <Button variant="subtle" w="fit-content" onClick={() => void download("/imports/templates/parts.xlsx")}>{t("asset.template")} (parts)</Button>
      <FileInput label={t("common.file")} accept=".csv,.xlsx" clearable value={file} onChange={(f) => { setFile(f); setRes(null); }} />
      <Group><Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
        <Button color="teal" disabled={!res || res.invalid > 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button>
        {res && res.invalid > 0 && <Button variant="subtle" color="red" onClick={() => void downloadPost("/imports/parts/errors.csv", fd(), "parts_import_errors.csv")}>errors.csv</Button>}</Group>
      {res && <Alert color={res.invalid ? "red" : "teal"}>{res.total} · {res.valid} {t("asset.valid")} · {res.invalid} {t("asset.invalid")}
        {res.errors.map((e) => <div key={e.row}>Row {e.row}: {e.errors.join("; ")}</div>)}
        {res.warnings.map((w) => <div key={`w${w.row}`}>⚠ Row {w.row}: {w.warnings.join("; ")}</div>)}</Alert>}
    </Stack>
  );
}
