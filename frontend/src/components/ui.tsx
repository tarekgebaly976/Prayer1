"use client";

import { ActionIcon, Autocomplete, Badge, Button, Center, Checkbox, CloseButton, Group, Loader, Modal, MultiSelect, Pagination, Paper, ScrollArea, Select, Skeleton, Stack, Table, Text, ThemeIcon, Title, Tooltip, UnstyledButton, type BadgeProps } from "@mantine/core";
import { useDebouncedValue, useMediaQuery } from "@mantine/hooks";
import { IconChevronDown, IconChevronRight, IconInbox, IconSitemap } from "@tabler/icons-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useQ } from "@/lib/hooks";
import type { AssetNode, Department, Member, Page } from "@/lib/types";

/** Status colours carry one meaning each: grey = not started / paused / not needed, yellow = waiting for someone,
 *  blue = approved / planned, orange = being worked on / warning, red = problem / emergency, green = done / OK. */
const STATUS_GROUPS: Record<string, string[]> = {
  gray: ["triage", "draft", "not_started", "skipped", "not_required", "unknown", "cancelled", "on_hold", "deferred", "standby"],
  yellow: ["awaiting_approval", "awaiting_review", "submitted", "pending", "deferral_requested", "cancellation_requested", "requested", "partial"],
  blue: ["approved", "planned", "scheduled", "generated", "ordered", "active", "wo_created", "confirmed"],
  orange: ["in_progress", "under_maintenance", "acknowledged", "warning"],
  red: ["rejected", "missed", "critical", "open", "delayed", "not_ready", "out_of_service", "emergency"],
  green: ["completed", "closed", "accepted", "done", "normal", "resolved", "ready", "in_service", "received", "fulfilled"],
};
const STATUS_COLORS: Record<string, string> = {
  ...Object.fromEntries(Object.entries(STATUS_GROUPS).flatMap(([c, v]) => v.map((k) => [k, c]))),
  P1: "red", P2: "orange", P3: "blue", P4: "gray", A: "red", B: "orange", C: "gray",
};

export function StatusBadge({ value, ...rest }: { value: string | null | undefined } & BadgeProps) {
  const { t, i18n } = useTranslation();
  if (!value) return <>—</>;
  const key = `status.${value}`;
  const label = i18n.exists(key) ? t(key) : i18n.exists(`woType.${value}`) ? t(`woType.${value}`) : value;
  return <Badge color={STATUS_COLORS[value] ?? "gray"} variant="light" tt="none" fw={600} styles={{ label: { overflow: "visible" } }} {...rest}>{label}</Badge>;
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
  // Placeholder lines instead of a spinner: the page keeps its shape while data arrives.
  return (
    <Stack gap={10} p="xs" role="status" aria-label={t("app.loading")} data-testid="loading">
      <Skeleton h={14} w="40%" radius="sm" /><Skeleton h={12} radius="sm" /><Skeleton h={12} w="85%" radius="sm" />
    </Stack>
  );
}

/** Friendly "nothing here" block (icon + sentence) for empty lists. */
export function EmptyState({ text, icon: Icon = IconInbox }: { text: string; icon?: typeof IconInbox }) {
  return (
    <Stack align="center" gap={6} py="xl" px="md" className="pp-empty" data-testid="empty-state">
      <ThemeIcon variant="light" color="gray" size={44} radius="xl"><Icon size={24} stroke={1.6} /></ThemeIcon>
      <Text c="dimmed" size="sm" ta="center">{text}</Text>
    </Stack>
  );
}

function TableSkeleton({ cols }: { cols: number }) {
  const { t } = useTranslation();
  return (
    <Stack gap={8} className="pp-table" p="md" role="status" aria-label={t("app.loading")} data-testid="loading">
      {[0, 1, 2, 3, 4].map((i) => (
        <Group key={i} gap="md" wrap="nowrap">{Array.from({ length: Math.min(cols, 6) }, (_, j) => <Skeleton key={j} h={14} radius="sm" style={{ flex: j === 1 ? 2 : 1 }} />)}</Group>
      ))}
    </Stack>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <Text c="red" size="sm">{(error as Error).message}</Text>;
}

/** Dates and date-times are not broken over two lines in table cells ("2026-11-" / "03"). */
const DATE_RE = /^\d{4}-\d{2}-\d{2}/;
const keepTogether = (v: ReactNode) => (typeof v === "string" && DATE_RE.test(v) ? <span className="nowrap">{v}</span> : v);

export interface Column<T> { key: string; label: ReactNode; render: (row: T) => ReactNode; hideOnMobile?: boolean }

export function DataTable<T extends object>({ rows, columns, onRow, empty, rowKey, selected, onSelect }: {
  rows: T[] | undefined; columns: Column<T>[]; onRow?: (r: T) => void; empty?: string; rowKey?: (r: T, i: number) => string;
  /** Row selection (checkbox column) by row id; shown when onSelect is given. */
  selected?: string[]; onSelect?: (ids: string[]) => void;
}) {
  const { t } = useTranslation();
  // Phones: every row becomes a card (first column as its heading, the others as label / value), no sideways scrolling.
  const phone = useMediaQuery("(max-width: 48em)");
  if (!rows) return <TableSkeleton cols={columns.length} />;
  if (rows.length === 0) return <EmptyState text={empty ?? t("common.noData")} />;
  const idOf = (r: T, i: number) => (rowKey ? rowKey(r, i) : ("id" in r && typeof r.id === "string" ? r.id : String(i)));
  const sel = new Set(selected ?? []);
  const ids = rows.map(idOf);
  const all = ids.length > 0 && ids.every((x) => sel.has(x));
  const toggle = (id: string) => { const n = new Set(sel); if (n.has(id)) n.delete(id); else n.add(id); onSelect?.([...n]); };
  if (phone) {
    const [head, ...rest] = columns.filter((c) => !c.hideOnMobile);
    return (
      <Stack gap="xs" data-testid="table-cards">
        {rows.map((r, i) => {
          const id = idOf(r, i);
          return (
            <Paper key={id} withBorder p="sm" className={onRow ? "pp-card-row pp-clickable" : "pp-card-row"} onClick={onRow ? () => onRow(r) : undefined}>
              <Group justify="space-between" wrap="nowrap" gap="xs" mb={rest.length ? 6 : 0}>
                <Text fw={700} size="sm" style={{ minWidth: 0 }} component="div">{head ? keepTogether(head.render(r)) : null}</Text>
                {onSelect && <Checkbox aria-label="select" checked={sel.has(id)} onChange={() => toggle(id)} onClick={(e) => e.stopPropagation()} />}
              </Group>
              <div className="pp-card-grid">
                {rest.map((c) => (
                  <div key={c.key} className={c.label ? undefined : "pp-card-wide"}>
                    {c.label ? <Text size="xs" c="dimmed" lh={1.3}>{c.label}</Text> : null}
                    <Text size="sm" component="div" lh={1.4}>{keepTogether(c.render(r))}</Text>
                  </div>
                ))}
              </div>
            </Paper>
          );
        })}
      </Stack>
    );
  }
  return (
    <ScrollArea type="auto" className="pp-table">
      <Table striped highlightOnHover={!!onRow} verticalSpacing="sm" horizontalSpacing="md" miw={600} stripedColor="var(--pp-page-bg)">
        <Table.Thead><Table.Tr>
          {onSelect && <Table.Th w={36}><Checkbox aria-label="all" checked={all} indeterminate={!all && ids.some((x) => sel.has(x))}
            onChange={() => onSelect(all ? [...sel].filter((x) => !ids.includes(x)) : [...new Set([...sel, ...ids])])} /></Table.Th>}
          {columns.map((c) => <Table.Th key={c.key}>{c.label}</Table.Th>)}
        </Table.Tr></Table.Thead>
        <Table.Tbody>
          {rows.map((r, i) => (
            <Table.Tr key={idOf(r, i)} onClick={onRow ? () => onRow(r) : undefined} style={onRow ? { cursor: "pointer" } : undefined}>
              {onSelect && <Table.Td onClick={(e) => e.stopPropagation()}><Checkbox aria-label="select" checked={sel.has(idOf(r, i))} onChange={() => toggle(idOf(r, i))} /></Table.Td>}
              {columns.map((c) => <Table.Td key={c.key}>{keepTogether(c.render(r))}</Table.Td>)}
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
type PickedAsset = Pick<AssetNode, "id" | "code" | "name" | "level" | "department_id">;

export function AssetPicker({ value, onChange, label, required, clearable }: {
  value: string | null; onChange: (v: string | null) => void; label?: string; required?: boolean; clearable?: boolean;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search.trim(), 300);
  const [picked, setPicked] = useState<PickedAsset | null>(null);
  const [browse, setBrowse] = useState(false);
  const res = useQ<Page<PickedAsset>>("/assets", q ? { q, limit: 50 } : { levels: "production_line,unit", limit: 200 });
  const items = res.data?.items ?? [];
  // Keep the chosen asset displayable even when it is not in the current result list (e.g. an existing value).
  const known = picked?.id === value ? picked : items.find((a) => a.id === value) ?? null;
  const current = useQ<PickedAsset>(value && !known ? `/assets/${value}` : null);
  const selected = known ?? current.data ?? null;
  const list = selected && !items.some((a) => a.id === selected.id) ? [selected, ...items] : items;
  const byId = new Map(list.map((a) => [a.id, a]));
  const labelOf = (a: PickedAsset) => `${a.code} — ${a.name}`;
  return (
    <>
    <Modal opened={browse} onClose={() => setBrowse(false)} title={label ?? t("common.asset")} size="lg">
      <Text size="xs" c="dimmed" mb="xs">{t("asset.pickFromTree")}</Text>
      <AssetTree onPick={(a) => { setPicked(a); onChange(a.id); setBrowse(false); }} />
    </Modal>
    <Select label={label ?? t("common.asset")} searchable clearable={clearable} required={required} value={value}
      rightSectionPointerEvents="all" rightSectionWidth={clearable && value ? 56 : 32}
      rightSection={<Group gap={0} wrap="nowrap">
        {clearable && value && <CloseButton size="sm" aria-label="clear" onClick={() => { setPicked(null); onChange(null); }} />}
        <Tooltip label={t("asset.tree")}><ActionIcon variant="subtle" size="sm" aria-label={t("asset.tree")} onClick={() => setBrowse(true)}><IconSitemap size={16} /></ActionIcon></Tooltip>
      </Group>}
      placeholder={t("common.search")} nothingFoundMessage={res.isFetching ? "…" : t("common.noData")}
      searchValue={search} onSearchChange={setSearch} filter={({ options }) => options}
      onChange={(v) => { setPicked(v ? byId.get(v) ?? null : null); onChange(v); }}
      data={list.map((a) => ({ value: a.id, label: labelOf(a) }))}
      renderOption={({ option }) => {
        const a = byId.get(option.value);
        return <Text size="sm" pl={(LEVEL_INDENT[a?.level ?? "component"] ?? 0) * 12} fw={a && LEVEL_INDENT[a.level] === 0 ? 700 : 400}>{option.label}</Text>;
      }} maxDropdownHeight={360} />
    </>
  );
}

export function UserPicker({ value, onChange, label, roles, multiple, tradeFilter }: {
  value: string | null; onChange: (v: string | null) => void; label: string; roles?: string[]; multiple?: false; tradeFilter?: boolean;
}) {
  const { t } = useTranslation();
  const q = useQ<Member[]>("/users");
  const [trade, setTrade] = useState<string | null>(null);
  const people = (q.data ?? []).filter((m) => m.is_active && (!roles || roles.includes(m.role_code)));
  const trades = [...new Set(people.map((m) => m.user.trade).filter((x): x is string => !!x))].sort();
  const data = people.filter((m) => !trade || m.user.trade === trade)
    .map((m) => ({ value: m.user.id, label: `${m.user.full_name}${m.user.trade ? ` (${m.user.trade})` : ""}` }));
  void multiple;
  const pick = <Select label={label} searchable clearable value={value} onChange={onChange} data={data} style={{ flex: 1 }} />;
  if (!tradeFilter || trades.length === 0) return pick;
  return (
    <Group align="end" gap="xs" wrap="nowrap">
      <Select label={t("trade.filter")} w={150} clearable placeholder={t("trade.all")} value={trade} onChange={setTrade} data={trades} />
      {pick}
    </Group>
  );
}

/** Trade (craft) of a person or job plan: pick from the list or type a new one. */
export function TradeInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label?: string }) {
  const { t } = useTranslation();
  const q = useQ<string[]>("/trades");
  return <Autocomplete label={label ?? t("trade.label")} value={value} onChange={onChange} data={q.data ?? []} placeholder={t("trade.placeholder")} limit={30} />;
}

export function DeptSelect({ value, onChange, label, clearable, placeholder }: {
  value: string | null; onChange: (v: string | null) => void; label?: string; clearable?: boolean; placeholder?: string;
}) {
  const { t, i18n } = useTranslation();
  const q = useQ<{ id: string; code: string; name: string; name_ar: string | null }[]>("/departments");
  return <Select label={label ?? t("common.department")} clearable={clearable} value={value} onChange={onChange} placeholder={placeholder} size={label === "" ? "xs" : undefined}
    data={(q.data ?? []).map((d) => ({ value: d.id, label: `${d.code} — ${i18n.language === "ar" && d.name_ar ? d.name_ar : d.name}` }))} />;
}

/** Several departments (a user who covers more than one area); the first chosen is the main one. Empty = all. */
export function DeptMultiSelect({ value, onChange, label, placeholder, compact }: {
  value: string[]; onChange: (v: string[]) => void; label?: string; placeholder?: string; compact?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const q = useQ<{ id: string; code: string; name: string; name_ar: string | null }[]>("/departments");
  return <MultiSelect label={label ?? t("common.department")} aria-label={label === "" ? t("admin.departments") : undefined} value={value} onChange={onChange} clearable searchable
    placeholder={value.length ? undefined : placeholder} size={compact ? "xs" : undefined}
    data={(q.data ?? []).map((d) => ({ value: d.id, label: compact ? d.code : `${d.code} — ${i18n.language === "ar" && d.name_ar ? d.name_ar : d.name}` }))} />;
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

/** The plant hierarchy, opened level by level. With `onPick` a click selects the asset instead of opening its page. */
type OnPick = ((a: AssetNode) => void) | undefined;

function Children({ query, depth, onPick }: { query: Record<string, string>; depth: number; onPick: OnPick }) {
  const { t } = useTranslation();
  const [limit, setLimit] = useState(200);
  const q = useQ<Page<AssetNode>>("/assets/tree", { ...query, limit });
  return (
    <>
      {(q.data?.items ?? []).map((k) => <TreeNode key={k.id} node={k} depth={depth} onPick={onPick} />)}
      {q.data && q.data.total > q.data.items.length && (
        <Button variant="subtle" size="compact-xs" ms={depth * 18} onClick={() => setLimit(Math.min(limit + 200, 1000))} disabled={limit >= 1000}>
          {t("common.next")} ({q.data.items.length} / {q.data.total}){limit >= 1000 ? " — use search" : ""}
        </Button>
      )}
    </>
  );
}

function TreeNode({ node, depth, onPick }: { node: AssetNode; depth: number; onPick: OnPick }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Group gap={4} ps={depth * 18} py={2} wrap="nowrap">
        {node.child_count > 0 ? (
          <UnstyledButton onClick={() => setOpen(!open)} aria-label="toggle">{open ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}</UnstyledButton>
        ) : <span style={{ width: 16 }} />}
        {onPick ? <UnstyledButton onClick={() => onPick(node)}><Text size="sm" className="mono" c="blue">{node.code}</Text></UnstyledButton>
          : <Text component={Link} href={`/assets/${node.id}`} size="sm" className="mono">{node.code}</Text>}
        <Text size="sm" truncate>{node.name}</Text>
        <StatusBadge value={node.criticality} size="xs" />
        {node.status !== "in_service" && <StatusBadge value={node.status} size="xs" />}
      </Group>
      {open && <Children query={{ parent_id: node.id }} depth={depth + 1} onPick={onPick} />}
    </>
  );
}

export function DeptTree({ dept, onPick }: { dept: Department; onPick?: OnPick }) {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <UnstyledButton onClick={() => setOpen(!open)} py={4}>
        <Group gap={4}>{open ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}<Text fw={600}>{dept.code} — {i18n.language === "ar" && dept.name_ar ? dept.name_ar : dept.name}</Text></Group>
      </UnstyledButton>
      {open && <Children query={{ department_id: dept.id }} depth={1} onPick={onPick} />}
    </div>
  );
}

export function AssetTree({ onPick }: { onPick?: (a: AssetNode) => void }) {
  const depts = useQ<Department[]>("/departments");
  return <>{(depts.data ?? []).map((d) => <DeptTree key={d.id} dept={d} onPick={onPick} />)}</>;
}
