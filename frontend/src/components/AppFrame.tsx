"use client";

import { ActionIcon, AppShell, Badge, Burger, Button, Group, Indicator, Menu, Modal, NavLink, PasswordInput, ScrollArea, Select, Stack, Text, Tooltip } from "@mantine/core";
import { useDisclosure, useNetwork } from "@mantine/hooks";
import {
  IconAlertTriangle, IconBell, IconBox, IconCalendarTime, IconChartBar, IconClipboardList, IconDashboard, IconDroplet, IconHeartRateMonitor,
  IconKey, IconLanguage, IconLogout, IconQrcode, IconSettings, IconSitemap, IconTool, IconToolsKitchen, IconUserCheck, IconWifi, IconWifiOff,
} from "@tabler/icons-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { post } from "@/lib/api";
import { useMut, useQ } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { Loading } from "./ui";

const NAV: { href: string; key: string; icon: typeof IconDashboard; perm?: string }[] = [
  { href: "/", key: "nav.dashboard", icon: IconDashboard },
  { href: "/my-work", key: "nav.myWork", icon: IconUserCheck, perm: "wo.view" },
  { href: "/scan", key: "nav.scan", icon: IconQrcode, perm: "asset.view" },
  { href: "/requests", key: "nav.requests", icon: IconAlertTriangle, perm: "request.create" },
  { href: "/work-orders", key: "nav.workOrders", icon: IconClipboardList, perm: "wo.view" },
  { href: "/assets", key: "nav.assets", icon: IconSitemap, perm: "asset.view" },
  { href: "/pm", key: "nav.pm", icon: IconCalendarTime, perm: "pm.view" },
  { href: "/lubrication", key: "nav.lubrication", icon: IconDroplet, perm: "lube.view" },
  { href: "/pdm", key: "nav.pdm", icon: IconHeartRateMonitor, perm: "pdm.view" },
  { href: "/shifts", key: "nav.shifts", icon: IconToolsKitchen, perm: "shift.view" },
  { href: "/inventory", key: "nav.inventory", icon: IconBox, perm: "inventory.view" },
  { href: "/shutdowns", key: "nav.shutdowns", icon: IconTool, perm: "shutdown.view" },
  { href: "/kpis", key: "nav.kpis", icon: IconChartBar, perm: "kpi.view" },
  { href: "/admin", key: "nav.admin", icon: IconSettings, perm: "plant.admin" },
];

export function AppFrame({ children }: { children: ReactNode }) {
  const { me, loading, plant, setPlant, can, logout, setLocale } = useSession();
  const { t, i18n } = useTranslation();
  const [opened, { toggle, close }] = useDisclosure();
  const [pwOpen, pw] = useDisclosure();
  const pathname = usePathname();
  const router = useRouter();
  const net = useNetwork();
  const notif = useQ<{ unread: number }>("/notifications", { limit: 1, unread: true }, { refetchInterval: 60_000 });

  useEffect(() => { if (!loading && !me) router.replace("/login"); }, [loading, me, router]);
  useEffect(() => close(), [pathname, close]);
  if (loading || !me) return <Loading />;
  if (!plant) return <Text p="xl">{t("app.noPlants")}</Text>;

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 250, breakpoint: "md", collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" aria-label="menu" />
            <Text fw={700} visibleFrom="xs">{t("app.name")}</Text>
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
            <Menu>
              <Menu.Target><ActionIcon variant="subtle" aria-label={t("app.language")}><IconLanguage size={20} /></ActionIcon></Menu.Target>
              <Menu.Dropdown>
                <Menu.Item onClick={() => void setLocale("en")} fw={i18n.language === "en" ? 700 : 400}>English</Menu.Item>
                <Menu.Item onClick={() => void setLocale("ar")} fw={i18n.language === "ar" ? 700 : 400}>العربية</Menu.Item>
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
      <AppShell.Navbar p="xs">
        <ScrollArea>
          {NAV.filter((n) => !n.perm || can(n.perm)).map((n) => (
            <NavLink key={n.href} component={Link} href={n.href} label={t(n.key)} leftSection={<n.icon size={18} />} className="tap-target"
              active={n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)} />
          ))}
        </ScrollArea>
      </AppShell.Navbar>
      <AppShell.Main>{children}</AppShell.Main>
      <ChangePassword opened={pwOpen} onClose={pw.close} />
    </AppShell>
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
