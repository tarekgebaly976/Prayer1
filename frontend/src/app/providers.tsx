"use client";

import { DirectionProvider, MantineProvider, createTheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { InstanceBanner } from "@/components/InstanceBanner";
import i18n from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";

const theme = createTheme({
  primaryColor: "indigo",
  fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans Arabic', 'Noto Sans Bengali', 'Nirmala UI', Vrinda, Tahoma, sans-serif",
  defaultRadius: "md",
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
