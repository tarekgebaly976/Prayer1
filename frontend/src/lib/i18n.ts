import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { ar } from "./locales/ar";
import { bn } from "./locales/bn";
import { en } from "./locales/en";

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar }, bn: { translation: bn } },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React escapes output
  returnNull: false,
});

/** The interface languages, in menu order; `label` is the language's own name. */
export const LANGS = [
  { code: "en", label: "English" },
  { code: "ar", label: "العربية" },
  { code: "bn", label: "বাংলা" },
] as const;
export type Lang = (typeof LANGS)[number]["code"];
const RTL = new Set<string>(["ar"]);

export const toLang = (l: string | null | undefined): Lang => (LANGS.find((x) => x.code === l)?.code ?? "en");

export function applyDirection(lang: Lang): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = lang;
  document.documentElement.dir = RTL.has(lang) ? "rtl" : "ltr";
}

export default i18n;
