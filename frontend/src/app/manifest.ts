import type { MetadataRoute } from "next";

// Generated per request: a test copy (CMMS_INSTANCE_LABEL set on its web container) gets its own name and the red
// TEST icon, so on a phone's home screen it cannot be mistaken for the real system. The public demo is marked DEMO (blue).
export const dynamic = "force-dynamic";

const BASE = {
  id: "/",
  name: "PlantPulse – Maintenance",
  short_name: "PlantPulse",
  description: "PlantPulse: maintenance management for industrial plants: work orders, preventive maintenance, lubrication, condition monitoring, QR scanning and shift rosters.",
  lang: "en",
  dir: "auto",
  start_url: "/my-work",
  scope: "/",
  display: "standalone",
  orientation: "any",
  background_color: "#ffffff",
  theme_color: "#17324D",
  categories: ["business", "productivity", "utilities"],
} satisfies MetadataRoute.Manifest;

const icons = (dir: string): MetadataRoute.Manifest["icons"] => [
  { src: `${dir}/icon-192.png`, sizes: "192x192", type: "image/png", purpose: "any" },
  { src: `${dir}/icon-512.png`, sizes: "512x512", type: "image/png", purpose: "any" },
  { src: `${dir}/icon-192-maskable.png`, sizes: "192x192", type: "image/png", purpose: "maskable" },
  { src: `${dir}/icon-512-maskable.png`, sizes: "512x512", type: "image/png", purpose: "maskable" },
  { src: `${dir}/icon.svg`, sizes: "any", type: "image/svg+xml", purpose: "any" },
];

export default function manifest(): MetadataRoute.Manifest {
  const label = (process.env.CMMS_INSTANCE_LABEL ?? "").trim();
  if (!label) return { ...BASE, icons: icons("/icons") };
  // Public demo (label starting with DEMO): its own name and the blue DEMO colour, the normal icon.
  if (label.toUpperCase().startsWith("DEMO")) {
    return { ...BASE, id: "/?instance=demo", name: "PlantPulse DEMO – Maintenance (sample data)", short_name: "PlantPulse DEMO",
      theme_color: "#1565C0", icons: icons("/icons") };
  }
  return {
    ...BASE,
    id: "/?instance=test",
    name: "PlantPulse TEST – Maintenance (test copy)",
    short_name: "PlantPulse TEST",
    theme_color: "#C62828",
    icons: icons("/icons/test"),
  };
}
