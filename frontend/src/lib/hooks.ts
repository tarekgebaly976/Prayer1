"use client";

import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ApiError, get, post, type Query } from "./api";
import { useSession } from "./session";

/** Query bound to the active plant (plant id is part of the cache key → no cross-plant cache bleed). */
export function useQ<T>(path: string | null, query?: Query, opts?: Partial<UseQueryOptions<T>>) {
  const { plant } = useSession();
  return useQuery<T>({
    queryKey: [plant?.plant_id, path, query],
    queryFn: () => get<T>(path as string, query),
    enabled: !!plant && !!path && (opts?.enabled ?? true),
    ...opts,
  } as UseQueryOptions<T>);
}

/** Code of each asset id shown in a list (plants have thousands of assets, so they are looked up by id). */
export function useAssetCodes(ids: (string | null | undefined)[]): Map<string, string> {
  const { plant } = useSession();
  const uniq = [...new Set(ids.filter((x): x is string => !!x))].sort();
  const q = useQuery<Record<string, string>>({
    queryKey: [plant?.plant_id, "/assets/codes", uniq],
    queryFn: () => post<Record<string, string>>("/assets/codes", { ids: uniq }),
    enabled: !!plant && uniq.length > 0,
    staleTime: 300_000,
  });
  return new Map(Object.entries(q.data ?? {}));
}

export function useMut<TArgs, TRes = unknown>(fn: (a: TArgs) => Promise<TRes>, opts?: { success?: string | false; onDone?: (r: TRes) => void }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation<TRes, ApiError, TArgs>({
    mutationFn: fn,
    onSuccess: (r) => {
      void qc.invalidateQueries();
      if (opts?.success !== false) notifications.show({ color: "teal", message: opts?.success ?? t("common.saved") });
      opts?.onDone?.(r);
    },
    onError: (e) => notifications.show({ color: "red", title: t("common.error"), message: e.message, autoClose: 8000 }),
  });
}

export function fmtDate(v: string | null | undefined, tz?: string, withTime = false): string {
  if (!v) return "—";
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  if (Number.isNaN(d.getTime())) return v;
  if (v.length === 10) return v;
  return new Intl.DateTimeFormat(undefined, withTime ? { dateStyle: "medium", timeStyle: "short", timeZone: tz } : { dateStyle: "medium", timeZone: tz }).format(d);
}

export function fmtNum(v: number | string | null | undefined, digits = 2): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: digits }) : String(v);
}

export function fmtMoney(v: number | string | null | undefined, currency: string): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(v));
}

/** datetime-local input value (plant-agnostic browser local) ↔ ISO */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
export const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);
