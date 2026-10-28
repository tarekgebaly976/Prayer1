"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { get, post, setApiContext } from "./api";
import type { Me, PlantAccess } from "./types";
import i18n, { applyDirection, toLang, type Lang } from "./i18n";

interface SessionValue {
  me: Me | null;
  loading: boolean;
  plant: PlantAccess | null;
  setPlant: (id: string) => void;
  can: (perm: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setLocale: (l: Lang) => Promise<void>;
}

const Ctx = createContext<SessionValue | null>(null);
const PLANT_KEY = "cmms.plant"; // UI preference only (an id, not a credential)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [plantId, setPlantId] = useState<string | null>(null);
  const router = useRouter();
  const qc = useQueryClient();

  const adopt = useCallback((m: Me) => {
    setMe(m);
    setApiContext({ csrf: m.csrf_token });
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(PLANT_KEY) : null;
    const pick = m.plants.find((p) => p.plant_id === saved) ?? m.plants[0] ?? null;
    setPlantId(pick?.plant_id ?? null);
    setApiContext({ plantId: pick?.plant_id ?? null });
    const loc = toLang(m.locale);
    void i18n.changeLanguage(loc);
    applyDirection(loc);
  }, []);

  useEffect(() => {
    setApiContext({ onUnauthorized: () => { setMe(null); router.replace("/login"); } });
    get<Me>("/auth/me").then(adopt).catch(() => setMe(null)).finally(() => setLoading(false));
  }, [adopt, router]);

  const plant = useMemo(() => me?.plants.find((p) => p.plant_id === plantId) ?? null, [me, plantId]);

  const value: SessionValue = {
    me, loading, plant,
    setPlant: (id) => {
      setPlantId(id);
      setApiContext({ plantId: id });
      window.localStorage.setItem(PLANT_KEY, id);
      qc.clear();
    },
    can: (perm) => !!plant?.permissions.includes(perm),
    login: async (email, password) => {
      const m = await post<Me>("/auth/login", { email, password });
      adopt(m);
    },
    logout: async () => {
      try { await post("/auth/logout"); } finally { setMe(null); qc.clear(); router.replace("/login"); }
    },
    setLocale: async (l) => {
      await i18n.changeLanguage(l);
      applyDirection(l);
      if (me) await post("/auth/locale", { locale: l }).catch(() => undefined);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSession outside SessionProvider");
  return v;
}
