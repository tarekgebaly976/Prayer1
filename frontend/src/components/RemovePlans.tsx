"use client";

import { Alert, Button, Group, Modal, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { post } from "@/lib/api";
import { useMut } from "@/lib/hooks";

interface RemoveResult { deleted: number; deactivated: number; not_found: number; open_work_orders: number }

/** "Remove selected" for PM plans, PdM points and lubrication points: never-used ones are deleted, the rest deactivated. */
export function RemovePlans({ path, ids, onDone }: { path: "/pm/plans/remove" | "/pdm/points/remove" | "/lubrication/points/remove"; ids: string[]; onDone: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rm = useMut(() => post<RemoveResult>(path, { ids }), {
    success: false,
    onDone: (r) => {
      notifications.show({ color: "teal", autoClose: 10000, message: t("removal.done", { d: r.deleted, x: r.deactivated }) + (r.open_work_orders ? ` ${t("removal.openWos", { n: r.open_work_orders })}` : "") });
      setOpen(false);
      onDone();
    },
  });
  return (
    <>
      <Button color="red" variant="light" disabled={ids.length === 0} onClick={() => setOpen(true)}>{t("removal.button", { n: ids.length })}</Button>
      <Modal opened={open} onClose={() => setOpen(false)} title={t("removal.title", { n: ids.length })}>
        <Stack>
          <Alert color="orange">{t("removal.rule")}</Alert>
          <Text size="sm" c="dimmed">{t("removal.wosStay")}</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
            <Button color="red" loading={rm.isPending} onClick={() => rm.mutate(undefined)}>{t("removal.confirm")}</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
