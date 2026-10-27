// Same-origin API client. The session lives in an HttpOnly cookie (never readable here); the CSRF token
// is echoed in a header for every state-changing request; the active plant travels in X-Plant-Id.

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public body?: unknown) {
    super(message);
  }
}

let currentPlant: string | null = null;
let csrfToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setApiContext(opts: { plantId?: string | null; csrf?: string | null; onUnauthorized?: () => void }): void {
  if (opts.plantId !== undefined) currentPlant = opts.plantId;
  if (opts.csrf !== undefined) csrfToken = opts.csrf;
  if (opts.onUnauthorized) onUnauthorized = opts.onUnauthorized;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m?.[1] ? decodeURIComponent(m[1]) : null;
}

function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg ?? ""}`).join("; ");
    if (d && typeof d === "object" && "message" in d) return String((d as { message: unknown }).message);
  }
  return fallback;
}

export type Query = Record<string, string | number | boolean | null | undefined | string[]>;

export function qs(q?: Query): string {
  if (!q) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function api<T = unknown>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (currentPlant) headers["X-Plant-Id"] = currentPlant;
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken ?? readCookie("cmms_csrf") ?? "";
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api/v1${path}${qs(query)}`, { method, headers, body: payload, credentials: "same-origin", cache: "no-store" });
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data: unknown = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized && !path.startsWith("/auth/login")) onUnauthorized();
    const code = data && typeof data === "object" && "code" in data ? String((data as { code: unknown }).code) : undefined;
    throw new ApiError(res.status, messageFrom(data, res.statusText), code, data);
  }
  return data as T;
}

export const get = <T>(path: string, query?: Query) => api<T>("GET", path, undefined, query);
export const post = <T>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const patch = <T>(path: string, body: unknown) => api<T>("PATCH", path, body);
export const put = <T>(path: string, body: unknown) => api<T>("PUT", path, body);
export const del = <T>(path: string) => api<T>("DELETE", path);

/** Authenticated download (blob) for exports/reports/attachments, preserving cookies and plant header. */
export async function download(path: string, query?: Query, filename?: string): Promise<void> {
  const res = await fetch(`/api/v1${path}${qs(query)}`, { headers: currentPlant ? { "X-Plant-Id": currentPlant } : {}, credentials: "same-origin" });
  if (!res.ok) {
    const detail = await res.json().then((j: { detail?: unknown }) => (typeof j.detail === "string" ? j.detail : null)).catch(() => null);
    throw new ApiError(res.status, detail ?? `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename ?? (res.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "download");
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** POST a form and save the response body as a file (e.g. import error reports). */
export async function downloadPost(path: string, body: FormData, filename: string): Promise<void> {
  const headers: Record<string, string> = { "X-CSRF-Token": csrfToken ?? readCookie("cmms_csrf") ?? "" };
  if (currentPlant) headers["X-Plant-Id"] = currentPlant;
  const res = await fetch(`/api/v1${path}`, { method: "POST", body, headers, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, `Download failed (${res.status})`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** Fetch an authenticated binary (e.g. QR PNG) as an object URL for <img>. */
export async function blobUrl(path: string): Promise<string> {
  const res = await fetch(`/api/v1${path}`, { headers: currentPlant ? { "X-Plant-Id": currentPlant } : {}, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, `Load failed (${res.status})`);
  return URL.createObjectURL(await res.blob());
}
