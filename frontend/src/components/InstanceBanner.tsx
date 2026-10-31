"use client";

import { Badge } from "@mantine/core";
import { useEffect, useState } from "react";

/** Red label on every page of a test installation (CMMS_INSTANCE_LABEL on the server); nothing on the real one. */
export function InstanceBanner() {
  const [label, setLabel] = useState("");
  useEffect(() => {
    fetch("/api/v1/meta").then((r) => (r.ok ? r.json() : null)).then((m: { instance_label?: string } | null) => {
      setLabel(m?.instance_label ?? "");
    }).catch(() => undefined);
  }, []);
  if (!label) return null;
  return (
    <Badge color="red" size="xl" radius="sm" variant="filled" data-testid="instance-banner"
      style={{ position: "fixed", bottom: 12, left: "50%", transform: "translateX(-50%)", zIndex: 1000, pointerEvents: "none", boxShadow: "0 2px 8px rgba(0,0,0,.3)" }}>
      {label}
    </Badge>
  );
}
