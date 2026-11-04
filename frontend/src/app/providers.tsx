"use client";

import { DirectionProvider, MantineProvider, createTheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { InstanceBanner } from "@/components/InstanceBanner";
import i18n from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";

// PlantPulse brand (same as the website): navy #17324D with amber #F5A623 accents. Fonts are self-hosted
// (Inter for Latin, IBM Plex Sans Arabic for Arabic), so they also load with the strict CSP and in the installed app.
const FONT = "'Inter Variable', 'IBM Plex Sans Arabic', system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans Arabic', 'Noto Sans Bengali', 'Nirmala UI', Vrinda, Tahoma, sans-serif";
const theme = createTheme({
  colors: {
    brand: ["#eef3f8", "#dbe4ee", "#b4c7da", "#89a7c5", "#6589b0", "#4c74a2", "#2f5a85", "#17324D", "#122a41", "#0b1d2e"],
    // Dark mode in the brand's navy instead of Mantine's neutral grey (body = 7, borders = 4, text = 0).
    dark: ["#dbe4ee", "#b4c2d0", "#8d9cad", "#66788c", "#2a3b4e", "#223244", "#1c2a3a", "#172331", "#101a24", "#0b131b"],
    accent: ["#fff7e6", "#ffecc4", "#ffdc8f", "#fdcb57", "#f9bb34", "#F5A623", "#de9312", "#c97f00", "#a06500", "#7a4c00"],
  },
  primaryColor: "brand",
  primaryShade: { light: 7, dark: 6 },
  fontFamily: FONT,
  headings: { fontFamily: FONT, fontWeight: "700" },
  defaultRadius: "md",
  cursorType: "pointer",
  components: {
    Card: { defaultProps: { shadow: "xs", radius: "md" } },
    Paper: { defaultProps: { radius: "md" } },
    Badge: { defaultProps: { radius: "sm" } },
  },
});

export function Providers({ children }: { children: ReactNode }) {
  const [qc] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 15_000, retry: (n, e) => n < 2 && (e as { status?: number }).status !== 403 && (e as { status?: number }).status !== 404, refetchOnWindowFocus: false } },
  }));
  useEffect(() => {
    // PWA: cache only the static app shell. API data is never cached offline (no silent stale writes).
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
  }, []);
  return (
    <I18nextProvider i18n={i18n}>
      <DirectionProvider detectDirection>
        <MantineProvider theme={theme} defaultColorScheme="light">
          <Notifications position="top-center" />
          <InstanceBanner />
          <QueryClientProvider client={qc}>
            <SessionProvider>{children}</SessionProvider>
          </QueryClientProvider>
        </MantineProvider>
      </DirectionProvider>
    </I18nextProvider>
  );
}
