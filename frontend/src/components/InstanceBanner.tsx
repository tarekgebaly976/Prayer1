"use client";

import { Badge } from "@mantine/core";
import { useEffect, useState } from "react";

const TEST_PREFIX = "TEST · ";

/** In a test copy: the red TEST icon in the browser tab / iPhone home screen, and "TEST · " in front of the tab title. */
function markTestCopy(): () => void {
  const apply = () => {
    for (const link of document.querySelectorAll<HTMLLinkElement>('link[rel~="icon"], link[rel="apple-touch-icon"]')) {
      const path = new URL(link.href).pathname;
      if (path.startsWith("/icons/") && !path.startsWith("/icons/test/")) link.href = path.replace("/icons/", "/icons/test/");
    }
    if (!document.title.startsWith(TEST_PREFIX)) document.title = TEST_PREFIX + document.title;
  };
  apply();
  // The app re-renders the head on navigation; put the TEST icon and title back each time.
  const obs = new MutationObserver(apply);
  obs.observe(document.head, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["href"] });
  return () => obs.disconnect();
}

/** Red label on every page of a test installation (CMMS_INSTANCE_LABEL on the server); nothing on the real one. */
export function InstanceBanner() {
  const [label, setLabel] = useState("");
  useEffect(() => {
    fetch("/api/v1/meta").then((r) => (r.ok ? r.json() : null)).then((m: { instance_label?: string } | null) => {
      setLabel(m?.instance_label ?? "");
    }).catch(() => undefined);
  }, []);
  useEffect(() => (label ? markTestCopy() : undefined), [label]);
  if (!label) return null;
  return (
    <Badge color="red" size="xl" radius="sm" variant="filled" data-testid="instance-banner"
      style={{ position: "fixed", bottom: 12, left: "50%", transform: "translateX(-50%)", zIndex: 1000, pointerEvents: "none", boxShadow: "0 2px 8px rgba(0,0,0,.3)" }}>
      {label}
    </Badge>
  );
}
