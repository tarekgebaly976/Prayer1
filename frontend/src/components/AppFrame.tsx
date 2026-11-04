"use client";

import { ActionIcon, AppShell, Avatar, Badge, Box, useComputedColorScheme, useMantineColorScheme, Burger, Button, Group, Indicator, Menu, Modal, NavLink, PasswordInput, ScrollArea, Select, Stack, Text, Tooltip } from "@mantine/core";
import { useDisclosure, useNetwork } from "@mantine/hooks";
import {
  IconAlertTriangle, IconBell, IconBox, IconCalendarTime, IconChartBar, IconClipboardList, IconDashboard, IconDroplet, IconHeartRateMonitor,
  IconKey, IconLanguage, IconLogout, IconMoon, IconPlus, IconSun, IconQrcode, IconSettings, IconSitemap, IconTool, IconToolsKitchen, IconUserCheck, IconWifi, IconWifiOff,
} from "@tabler/icons-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { post } from "@/lib/api";
import { useMut, useQ } from "@/lib/hooks";
import { LANGS } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { Loading } from "./ui";

type NavItem = { href: string; key: string; icon: typeof IconDashboard; perm?: string };
const NAV_GROUPS: { key: string | null; items: NavItem[] }[] = [
  { key: null, items: [{ href: "/", key: "nav.dashboard", icon: IconDashboard }] },
  { key: "navGroup.daily", items: [
    { href: "/my-work", key: "nav.myWork", icon: IconUserCheck, perm: "wo.view" },
    { href: "/scan", key: "nav.scan", icon: IconQrcode, perm: "asset.view" },
    { href: "/requests", key: "nav.requests", icon: IconAlertTriangle, perm: "request.create" },
    { href: "/work-orders", key: "nav.workOrders", icon: IconClipboardList, perm: "wo.view" },
  ] },
  { key: "navGroup.maintenance", items: [
    { href: "/pm", key: "nav.pm", icon: IconCalendarTime, perm: "pm.view" },
    { href: "/lubrication", key: "nav.lubrication", icon: IconDroplet, perm: "lube.view" },
    { href: "/pdm", key: "nav.pdm", icon: IconHeartRateMonitor, perm: "pdm.view" },
    { href: "/shutdowns", key: "nav.shutdowns", icon: IconTool, perm: "shutdown.view" },
  ] },
  { key: "navGroup.resources", items: [
    { href: "/assets", key: "nav.assets", icon: IconSitemap, perm: "asset.view" },
    { href: "/inventory", key: "nav.inventory", icon: IconBox, perm: "inventory.view" },
    { href: "/shifts", key: "nav.shifts", icon: IconToolsKitchen, perm: "shift.view" },
  ] },
  { key: "navGroup.insight", items: [
    { href: "/kpis", key: "nav.kpis", icon: IconChartBar, perm: "kpi.view" },
    { href: "/admin", key: "nav.admin", icon: IconSettings, perm: "plant.admin" },
  ] },
];

/** Counts shown next to a menu entry (from the dashboard summary, shared with the dashboard page). */
interface NavCounts {
  my_open_work?: number; open_emergencies?: number; new_requests?: number; pm_pending_approvals?: number; lube_overdue?: number;
  open_alerts?: { critical: number; warning: number };
}
function navCount(href: string, s: NavCounts | undefined): { n: number; color: string } | null {
  if (!s) return null;
  const v: Record<string, [number | undefined, string]> = {
    "/my-work": [s.my_open_work, "brand.4"], "/work-orders": [s.open_emergencies, "red"], "/requests": [s.new_requests, "accent"],
    "/pm": [s.pm_pending_approvals, "accent"], "/lubrication": [s.lube_overdue, "orange"], "/pdm": [s.open_alerts?.critical, "red"],
  };
  const e = v[href];
  return e && e[0] ? { n: e[0], color: e[1] } : null;
}

const humanRole = (code: string) => { const s = code.replace(/_/g, " "); return s.charAt(0).toUpperCase() + s.slice(1); };
const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

export function AppFrame({ children }: { children: ReactNode }) {
  const { me, loading, plant, setPlant, can, logout, setLocale } = useSession();
  const { t, i18n } = useTranslation();
  const [opened, { toggle, close }] = useDisclosure();
  const [pwOpen, pw] = useDisclosure();
  const pathname = usePathname();
  const router = useRouter();
  const net = useNetwork();
  const notif = useQ<{ unread: number }>("/notifications", { limit: 1, unread: true }, { refetchInterval: 60_000 });
  const counts = useQ<NavCounts>("/dashboard/summary", undefined, { refetchInterval: 60_000 });
  const { setColorScheme } = useMantineColorScheme();
  const dark = useComputedColorScheme("light", { getInitialValueInEffect: true }) === "dark";

  useEffect(() => { if (!loading && !me) router.replace("/login"); }, [loading, me, router]);
  useEffect(() => close(), [pathname, close]);
  if (loading || !me) return <Loading />;
  if (!plant) return <Text p="xl">{t("app.noPlants")}</Text>;

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 260, breakpoint: "md", collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header className="pp-header">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" aria-label="menu" />
            <Link href="/" style={{ textDecoration: "none", color: "inherit" }}><Group gap={10} wrap="nowrap">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/icons/icon.svg" alt="" width={32} height={32} style={{ display: "block" }} />
              <Stack gap={0} visibleFrom="xs">
                <Text fw={800} size="lg" lh={1.1} c="var(--pp-strong)">{t("app.name")}</Text>
                <Text size="xs" c="dimmed" lh={1.2} truncate maw={260}>{plant.plant_name}</Text>
              </Stack>
            </Group></Link>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Tooltip label={net.online ? t("app.online") : t("app.offline")}>
              <Badge data-testid="net-status" color={net.online ? "teal" : "red"} variant="light" leftSection={net.online ? <IconWifi size={14} /> : <IconWifiOff size={14} />}>
                <Text span size="xs" visibleFrom="sm">{net.online ? t("app.online") : t("app.offline")}</Text>
              </Badge>
            </Tooltip>
            {me.plants.length > 1 ? (
              <Select size="xs" w={150} aria-label={t("app.plant")} value={plant.plant_id} onChange={(v) => v && setPlant(v)} allowDeselect={false}
                data={me.plants.map((p) => ({ value: p.plant_id, label: p.plant_code }))} />
            ) : <Badge variant="outline" visibleFrom="sm">{plant.plant_code}</Badge>}
            <Indicator disabled={!notif.data?.unread} label={notif.data?.unread} size={16} color="red">
              <ActionIcon variant="subtle" component={Link} href="/notifications" aria-label={t("nav.notifications")}><IconBell size={20} /></ActionIcon>
            </Indicator>
            <Tooltip label={dark ? t("app.lightMode") : t("app.darkMode")}>
              <ActionIcon variant="subtle" aria-label={dark ? t("app.lightMode") : t("app.darkMode")} data-testid="color-scheme"
                onClick={() => setColorScheme(dark ? "light" : "dark")}>{dark ? <IconSun size={20} /> : <IconMoon size={20} />}</ActionIcon>
            </Tooltip>
            <Menu>
              <Menu.Target><ActionIcon variant="subtle" aria-label={t("app.language")}><IconLanguage size={20} /></ActionIcon></Menu.Target>
              <Menu.Dropdown>
                {LANGS.map((l) => <Menu.Item key={l.code} onClick={() => void setLocale(l.code)} fw={i18n.language === l.code ? 700 : 400}>{l.label}</Menu.Item>)}
              </Menu.Dropdown>
            </Menu>
            <Menu>
              <Menu.Target><ActionIcon variant="subtle" aria-label="account" data-testid="account-menu"><IconUserCheck size={20} /></ActionIcon></Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>{me.full_name}<br />{plant.plant_name} · {plant.role}</Menu.Label>
                <Menu.Item leftSection={<IconKey size={16} />} onClick={pw.open}>{t("auth.changePassword")}</Menu.Item>
                <Menu.Item leftSection={<IconLogout size={16} />} onClick={() => void logout()}>{t("app.logout")}</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs" className="pp-nav">
        <AppShell.Section grow component={ScrollArea} scrollbarSize={6}>
          {NAV_GROUPS.map((g) => {
            const items = g.items.filter((n) => !n.perm || can(n.perm));
            if (items.length === 0) return null;
            return (
              <div key={g.key ?? "top"}>
                {g.key && <div className="pp-nav-group">{t(g.key)}</div>}
                {items.map((n) => {
                  const c = navCount(n.href, counts.data);
                  return (
                    <NavLink key={n.href} component={Link} href={n.href} label={t(n.key)} leftSection={<n.icon size={19} stroke={1.7} />}
                      className="tap-target pp-navlink" active={n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)}
                      rightSection={c ? <Badge size="sm" circle={c.n < 10} color={c.color} variant="filled" aria-hidden>{c.n}</Badge> : undefined}
                      aria-label={t(n.key)} />
                  );
                })}
              </div>
            );
          })}
        </AppShell.Section>
        <AppShell.Section className="pp-user">
          <Group gap="sm" wrap="nowrap">
            <Avatar color="accent" variant="filled" radius="xl" size={36}>{initials(me.full_name)}</Avatar>
            <Stack gap={0} style={{ minWidth: 0 }}>
              <Text size="sm" fw={600} c="white" truncate>{me.full_name}</Text>
              <Text size="xs" c="var(--pp-nav-text)" truncate>{plant.plant_code} · {humanRole(plant.role)}</Text>
            </Stack>
          </Group>
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main className="pp-main pp-has-bottom-nav">{children}</AppShell.Main>
      {!opened && <BottomNav pathname={pathname} unread={notif.data?.unread ?? 0} myOpen={counts.data?.my_open_work ?? 0} />}
      <ChangePassword opened={pwOpen} onClose={pw.close} />
    </AppShell>
  );
}

/** Phones and tablets: the four things a technician does most, always one tap away; the full menu stays in the burger. */
function BottomNav({ pathname, unread, myOpen }: { pathname: string; unread: number; myOpen: number }) {
  const { t } = useTranslation();
  const { can } = useSession();
  const item = (href: string, label: string, Icon: typeof IconDashboard, n = 0) => (
    <Link href={href} data-active={(href === "/" ? pathname === "/" : pathname.startsWith(href)) || undefined} aria-label={label}>
      <Indicator disabled={!n} label={n} size={16} color="red" offset={2}><Icon size={24} stroke={1.7} /></Indicator>
      <span style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
    </Link>
  );
  return (
    <Box hiddenFrom="md" component="nav" className="pp-bottom-nav" data-testid="bottom-nav" aria-label="shortcuts">
      {item("/", t("nav.dashboard"), IconDashboard)}
      {can("wo.view") && item("/my-work", t("nav.myWork"), IconUserCheck, myOpen)}
      {can("request.create") && (
        <Link href="/requests?new=1" className="pp-fab" aria-label={t("req.new")}><span className="pp-fab-circle"><IconPlus size={28} stroke={2.2} /></span></Link>
      )}
      {can("asset.view") && item("/scan", t("nav.scan"), IconQrcode)}
      {item("/notifications", t("nav.notifications"), IconBell, unread)}
    </Box>
  );
}

export function Guard({ perm, children }: { perm: string; children: ReactNode }) {
  const { can } = useSession();
  const { t } = useTranslation();
  // UX only: the backend enforces every permission independently.
  if (!can(perm)) return <Text c="dimmed" p="xl">{t("app.noAccess")}</Text>;
  return <>{children}</>;
}

function ChangePassword({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const empty = { current: "", next: "", repeat: "" };
  const [f, setF] = useState(empty);
  const done = () => { setF(empty); onClose(); };
  const m = useMut(() => post("/auth/change-password", { current_password: f.current, new_password: f.next }), { success: t("auth.passwordChanged"), onDone: done });
  const mismatch = f.repeat.length > 0 && f.repeat !== f.next;
  return (
    <Modal opened={opened} onClose={done} title={t("auth.changePassword")}>
      <Stack>
        <PasswordInput label={t("auth.currentPassword")} autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.currentTarget.value })} />
        <PasswordInput label={t("auth.newPassword")} description={t("auth.passwordRule")} autoComplete="new-password" value={f.next} onChange={(e) => setF({ ...f, next: e.currentTarget.value })} />
        <PasswordInput label={t("auth.repeatPassword")} autoComplete="new-password" value={f.repeat} error={mismatch ? t("auth.passwordMismatch") : undefined}
          onChange={(e) => setF({ ...f, repeat: e.currentTarget.value })} />
        <Button onClick={() => m.mutate(undefined)} loading={m.isPending} disabled={!f.current || f.next.length < 12 || f.next !== f.repeat}>{t("common.save")}</Button>
      </Stack>
    </Modal>
  );
}
