"use client";

import { Button, Group, Modal, MultiSelect, NumberInput, Select, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { download } from "@/lib/api";
import { useQ } from "@/lib/hooks";
import { AssetPicker, DeptSelect } from "./ui";

const LEVELS = ["production_line", "unit", "assembly", "sub_assembly", "component"] as const;

/** QR label sheets: A4, 24 labels (3 × 8, 70 × 37 mm). Assets by area/level/department, or lubrication points by route. */
export function LabelPrint({ kind, opened, onClose, under: preset }: {
  kind: "assets" | "lube"; opened: boolean; onClose: () => void; under?: string;
}) {
  const { t } = useTranslation();
  const [under, setUnder] = useState<string | null>(preset ?? null);
  const [levels, setLevels] = useState<string[]>([]);
  const [dept, setDept] = useState<string | null>(null);
  const [route, setRoute] = useState<string | null>(null);
  const [skip, setSkip] = useState<number | string>(0);
  const [busy, setBusy] = useState(false);
  const routes = useQ<{ id: string; code: string; name: string }[]>(kind === "lube" && opened ? "/lubrication/routes" : null);
  const go = async () => {
    setBusy(true);
    try {
      if (kind === "assets") {
        await download("/assets/labels.pdf", { under: preset ?? under, levels: levels.join(",") || undefined, department_id: dept, skip: Number(skip) || 0 });
      } else {
        await download("/lubrication/points/labels.pdf", { route_id: route, under: preset ?? under, skip: Number(skip) || 0 });
      }
      onClose();
    } catch (e) {
      notifications.show({ color: "red", title: t("common.error"), message: (e as Error).message, autoClose: 8000 });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal opened={opened} onClose={onClose} title={t("labels.title")}>
      <Stack>
        <Text size="sm" c="dimmed">{t("labels.hint")}</Text>
        {!preset && <AssetPicker label={t("labels.under")} value={under} onChange={setUnder} clearable />}
        {kind === "assets" && <>
          <MultiSelect label={t("asset.level")} placeholder={t("labels.allLevels")} clearable value={levels} onChange={setLevels}
            data={LEVELS.map((l) => ({ value: l, label: t(`level.${l}`) }))} />
          {!preset && <DeptSelect value={dept} onChange={setDept} clearable />}
        </>}
        {kind === "lube" && <Select label={t("lube.routes")} clearable value={route} onChange={setRoute}
          data={(routes.data ?? []).map((r) => ({ value: r.id, label: `${r.code} — ${r.name}` }))} />}
        <NumberInput label={t("labels.skip")} description={t("labels.skipHint")} min={0} max={23} value={skip} onChange={setSkip} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t("common.cancel")}</Button>
          <Button loading={busy} onClick={() => void go()}>{t("labels.download")}</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
