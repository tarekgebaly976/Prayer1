"use client";

import { Alert, Button, FileInput, Group, Modal, Paper, SegmentedControl, Select, Stack, Table, TextInput } from "@mantine/core";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Guard } from "@/components/AppFrame";
import { LabelPrint } from "@/components/LabelPrint";
import { NewAsset } from "@/components/NewAsset";
import { AssetTree, DataTable, PageHeader, Pager, StatusBadge } from "@/components/ui";
import { api, download, downloadPost } from "@/lib/api";
import { useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Asset, Page } from "@/lib/types";

interface ImportResult { total: number; valid: number; invalid: number; errors: { row: number; code: string | null; errors: string[] }[] }

function ImportAssets({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<ImportResult | null>(null);
  const fd = () => { const d = new FormData(); if (file) d.append("file", file); return d; };
  const preview = useMut(() => api<ImportResult>("POST", "/imports/assets/preview", fd()), { success: false, onDone: setRes });
  // Start from an empty form every time, so a finished import never leaves its file selected for the next one.
  const close = () => { setFile(null); setRes(null); onClose(); };
  const commit = useMut(() => api<{ created: number }>("POST", "/imports/assets/commit", fd()), { onDone: close });
  const errorsCsv = () => downloadPost("/imports/assets/errors.csv", fd(), "asset_import_errors.csv");
  return (
    <Modal opened={opened} onClose={close} title={t("asset.importTitle")} size="lg">
      <Stack>
        <Button variant="subtle" onClick={() => void download("/imports/templates/assets.xlsx")}>{t("asset.template")}</Button>
        <FileInput label={t("common.file")} accept=".csv,.xlsx" clearable value={file} onChange={(f) => { setFile(f); setRes(null); }} />
        <Group>
          <Button disabled={!file} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t("asset.preview")}</Button>
          <Button color="teal" disabled={!res || res.invalid > 0} loading={commit.isPending} onClick={() => commit.mutate(undefined)}>{t("asset.commit")}</Button>
        </Group>
        {res && (
          <>
            <Alert color={res.invalid ? "red" : "teal"}>{res.total} · {res.valid} {t("asset.valid")} · {res.invalid} {t("asset.invalid")}</Alert>
            {res.invalid > 0 && (
              <>
                <Button variant="light" size="xs" onClick={() => void errorsCsv()}>{t("asset.errorsReport")}</Button>
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

function Assets() {
  const { t } = useTranslation();
  const router = useRouter();
  const { can } = useSession();
  const [view, setView] = useState("tree");
  const [q, setQ] = useState("");
  const [crit, setCrit] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [newOpen, setNewOpen] = useState(false);
  const [impOpen, setImpOpen] = useState(false);
  const [labels, setLabels] = useState(false);
  const list = useQ<Page<Asset>>(view === "list" ? "/assets" : null, { q, criticality: crit, limit: 50, offset });
  return (
    <>
      <PageHeader title={t("nav.assets")} actions={<>
        {can("asset.edit") && <Button onClick={() => setNewOpen(true)}>{t("asset.new")}</Button>}
        {can("asset.import") && <Button variant="light" onClick={() => setImpOpen(true)}>{t("common.import")}</Button>}
        <Button variant="default" onClick={() => setLabels(true)}>{t("labels.button")}</Button>
        {can("report.export") && <Button variant="default" onClick={() => void download("/exports/assets.csv")}>{t("common.export")} CSV</Button>}
      </>}>
        <SegmentedControl value={view} onChange={setView} data={[{ value: "tree", label: t("asset.tree") }, { value: "list", label: t("asset.list") }]} w={240} />
      </PageHeader>
      <LabelPrint kind="assets" opened={labels} onClose={() => setLabels(false)} />
      {view === "tree" ? (
        <Paper withBorder p="md"><AssetTree /></Paper>
      ) : (
        <>
          <Group mb="sm">
            <TextInput placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.currentTarget.value); setOffset(0); }} />
            <Select placeholder={t("common.criticality")} clearable data={["A", "B", "C"]} value={crit} onChange={setCrit} w={140} />
          </Group>
          <DataTable rows={list.data?.items} onRow={(a) => router.push(`/assets/${a.id}`)} columns={[
            { key: "c", label: t("common.code"), render: (a) => <span className="mono">{a.code}</span> },
            { key: "n", label: t("common.name"), render: (a) => a.name },
            { key: "l", label: t("asset.level"), render: (a) => t(`level.${a.level}`) },
            { key: "k", label: t("common.criticality"), render: (a) => <StatusBadge value={a.criticality} /> },
            { key: "s", label: t("common.status"), render: (a) => <StatusBadge value={a.status} /> },
            { key: "o", label: t("asset.oem"), render: (a) => `${a.oem ?? ""} ${a.model ?? ""}` },
          ]} />
          <Pager page={list.data} setPage={(p) => setOffset((p - 1) * 50)} />
        </>
      )}
      <NewAsset opened={newOpen} onClose={() => setNewOpen(false)} />
      <ImportAssets opened={impOpen} onClose={() => setImpOpen(false)} />
    </>
  );
}

export default function AssetsPage() {
  return <Guard perm="asset.view"><Assets /></Guard>;
}
