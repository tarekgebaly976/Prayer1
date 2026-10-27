"use client";

import { Badge, Button, Center, Group, Loader, Pagination, Paper, ScrollArea, Select, Stack, Table, Text, Title, type BadgeProps } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useQ } from "@/lib/hooks";
import type { Asset, Member, Page } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  triage: "gray", awaiting_approval: "yellow", approved: "blue", planned: "cyan", scheduled: "indigo", in_progress: "orange",
  on_hold: "grape", awaiting_review: "violet", completed: "teal", closed: "green", cancelled: "dark", submitted: "yellow",
  accepted: "green", rejected: "red", generated: "blue", deferral_requested: "yellow", deferred: "grape", cancellation_requested: "yellow",
  pending: "yellow", done: "green", skipped: "gray", missed: "red", normal: "green", warning: "orange", critical: "red", unknown: "gray",
  open: "red", acknowledged: "orange", wo_created: "blue", resolved: "green", draft: "gray", confirmed: "green", delayed: "red",
  ready: "green", not_ready: "red", partial: "yellow", not_required: "gray", in_service: "green", under_maintenance: "orange",
  out_of_service: "red", standby: "blue", P1: "red", P2: "orange", P3: "blue", P4: "gray", A: "red", B: "orange", C: "gray",
  requested: "yellow", ordered: "blue", received: "green", active: "blue", fulfilled: "green", not_started: "gray", emergency: "red",
};

export function StatusBadge({ value, ...rest }: { value: string | null | undefined } & BadgeProps) {
  const { t, i18n } = useTranslation();
  if (!value) return <>—</>;
  const key = `status.${value}`;
  const label = i18n.exists(key) ? t(key) : i18n.exists(`woType.${value}`) ? t(`woType.${value}`) : value;
  return <Badge color={STATUS_COLORS[value] ?? "gray"} variant="light" {...rest}>{label}</Badge>;
}

export function PageHeader({ title, actions, children }: { title: string; actions?: ReactNode; children?: ReactNode }) {
  return (
    <Stack gap={4} mb="md">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Title order={2} size="h3">{title}</Title>
        <Group gap="xs" wrap="wrap">{actions}</Group>
      </Group>
      {children}
    </Stack>
  );
}

export function Loading() {
  const { t } = useTranslation();
  return <Center p="xl"><Loader size="sm" /><Text ms="sm" c="dimmed">{t("app.loading")}</Text></Center>;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <Text c="red" size="sm">{(error as Error).message}</Text>;
}

export interface Column<T> { key: string; label: string; render: (row: T) => ReactNode; hideOnMobile?: boolean }

export function DataTable<T extends object>({ rows, columns, onRow, empty, rowKey }: {
  rows: T[] | undefined; columns: Column<T>[]; onRow?: (r: T) => void; empty?: string; rowKey?: (r: T, i: number) => string;
}) {
  const { t } = useTranslation();
  if (!rows) return <Loading />;
  if (rows.length === 0) return <Text c="dimmed" p="md">{empty ?? t("common.noData")}</Text>;
  return (
    <ScrollArea type="auto">
      <Table striped highlightOnHover={!!onRow} verticalSpacing="xs" miw={600}>
        <Table.Thead><Table.Tr>{columns.map((c) => <Table.Th key={c.key}>{c.label}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>
          {rows.map((r, i) => (
            <Table.Tr key={rowKey ? rowKey(r, i) : ("id" in r && typeof r.id === "string" ? r.id : String(i))} onClick={onRow ? () => onRow(r) : undefined} style={onRow ? { cursor: "pointer" } : undefined}>
              {columns.map((c) => <Table.Td key={c.key}>{c.render(r)}</Table.Td>)}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

export function Pager({ page, setPage }: { page: Page<unknown> | undefined; setPage: (n: number) => void }) {
  if (!page || page.total <= page.limit) return null;
  const pages = Math.ceil(page.total / page.limit);
  return (
    <Group justify="space-between" mt="sm">
      <Text size="sm" c="dimmed">{page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} / {page.total}</Text>
      <Pagination total={pages} value={Math.floor(page.offset / page.limit) + 1} onChange={(p) => setPage(p)} size="sm" />
    </Group>
  );
}

export function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="sm"><Text fw={600}>{title}</Text><Group gap="xs">{actions}</Group></Group>
      {children}
    </Paper>
  );
}

const LEVEL_INDENT: Record<string, number> = { production_line: 0, unit: 1, assembly: 2, sub_assembly: 3, component: 4 };

/**
 * Asset picker that searches the server, so it works with thousands of assets. With nothing typed it lists the top
 * of the hierarchy (production lines and units of every department); typing searches code and name across all levels.
 */
export function AssetPicker({ value, onChange, label, required, clearable }: {
  value: string | null; onChange: (v: string | null) => void; label?: string; required?: boolean; clearable?: boolean;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search.trim(), 300);
  const [picked, setPicked] = useState<Asset | null>(null);
  const res = useQ<Page<Asset>>("/assets", q ? { q, limit: 50 } : { levels: "production_line,unit", limit: 200 });
  const items = res.data?.items ?? [];
  // Keep the chosen asset displayable even when it is not in the current result list (e.g. an existing value).
  const known = picked?.id === value ? picked : items.find((a) => a.id === value) ?? null;
  const current = useQ<Asset>(value && !known ? `/assets/${value}` : null);
  const selected = known ?? current.data ?? null;
  const list = selected && !items.some((a) => a.id === selected.id) ? [selected, ...items] : items;
  const byId = new Map(list.map((a) => [a.id, a]));
  const labelOf = (a: Asset) => `${a.code} — ${a.name}`;
  return (
    <Select label={label ?? t("common.asset")} searchable clearable={clearable} required={required} value={value}
      placeholder={t("common.search")} nothingFoundMessage={res.isFetching ? "…" : t("common.noData")}
      searchValue={search} onSearchChange={setSearch} filter={({ options }) => options}
      onChange={(v) => { setPicked(v ? byId.get(v) ?? null : null); onChange(v); }}
      data={list.map((a) => ({ value: a.id, label: labelOf(a) }))}
      renderOption={({ option }) => {
        const a = byId.get(option.value);
        return <Text size="sm" pl={(LEVEL_INDENT[a?.level ?? "component"] ?? 0) * 12} fw={a && LEVEL_INDENT[a.level] === 0 ? 700 : 400}>{option.label}</Text>;
      }} maxDropdownHeight={360} />
  );
}

export function UserPicker({ value, onChange, label, roles, multiple }: { value: string | null; onChange: (v: string | null) => void; label: string; roles?: string[]; multiple?: false }) {
  const q = useQ<Member[]>("/users");
  const data = (q.data ?? []).filter((m) => m.is_active && (!roles || roles.includes(m.role_code))).map((m) => ({ value: m.user.id, label: `${m.user.full_name}${m.user.trade ? ` (${m.user.trade})` : ""}` }));
  void multiple;
  return <Select label={label} searchable clearable value={value} onChange={onChange} data={data} />;
}

export function DeptSelect({ value, onChange, label, clearable }: { value: string | null; onChange: (v: string | null) => void; label?: string; clearable?: boolean }) {
  const { t, i18n } = useTranslation();
  const q = useQ<{ id: string; code: string; name: string; name_ar: string | null }[]>("/departments");
  return <Select label={label ?? t("common.department")} clearable={clearable} value={value} onChange={onChange}
    data={(q.data ?? []).map((d) => ({ value: d.id, label: `${d.code} — ${i18n.language === "ar" && d.name_ar ? d.name_ar : d.name}` }))} />;
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed">{label}</Text>
      <div>{children ?? "—"}</div>
    </div>
  );
}

export function ConfirmButton({ children, onConfirm, color, loading, disabled }: { children: ReactNode; onConfirm: () => void; color?: string; loading?: boolean; disabled?: boolean }) {
  return <Button color={color} loading={loading} disabled={disabled} onClick={() => { if (window.confirm(String(children))) onConfirm(); }}>{children}</Button>;
}
