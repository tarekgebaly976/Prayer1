"use client";

import { Alert, Button, Group, Stack, Text, TextInput } from "@mantine/core";
import jsQR from "jsqr";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/ui";
import { get } from "@/lib/api";
import type { Asset } from "@/lib/types";

/** Labels encode "cmms:asset:<token>" (assets) or "cmms:lube:<token>" (lubrication points). */
export default function Scan() {
  const { t } = useTranslation();
  const router = useRouter();
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [running, setRunning] = useState(false);
  const [manual, setManual] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  async function resolve(raw: string) {
    const text = raw.trim();
    const m = text.match(/^cmms:(asset|lube):([0-9a-f]+)$/i);
    const [kind, token] = m ? [m[1]!.toLowerCase(), m[2]!] : ["asset", text];
    try {
      if (kind === "lube") {
        const p = await get<{ id: string; asset_id: string }>(`/lubrication/points/by-qr/${encodeURIComponent(token)}`);
        router.push(`/assets/${p.asset_id}?tab=lube`);
      } else {
        const a = await get<Asset>(`/assets/by-qr/${encodeURIComponent(token)}`);
        setMsg(`${t("scan.found")} ${a.code}`);
        router.push(`/assets/${a.id}`);
      }
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  function stop() {
    stream.current?.getTracks().forEach((tr) => tr.stop());
    stream.current = null;
    setRunning(false);
  }

  async function start() {
    setMsg(null);
    if (!navigator.mediaDevices?.getUserMedia) { setMsg(t("scan.notSupported")); return; }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      if (video.current) { video.current.srcObject = stream.current; await video.current.play(); }
      setRunning(true);
    } catch {
      setMsg(t("scan.notSupported"));
    }
  }

  useEffect(() => {
    if (!running) return;
    let raf = 0;
    const tick = () => {
      const v = video.current, c = canvas.current;
      if (v && c && v.readyState === v.HAVE_ENOUGH_DATA) {
        c.width = v.videoWidth;
        c.height = v.videoHeight;
        const ctx = c.getContext("2d", { willReadFrequently: true });
        if (ctx) {
          ctx.drawImage(v, 0, 0);
          const img = ctx.getImageData(0, 0, c.width, c.height);
          const code = jsQR(img.data, img.width, img.height);
          if (code?.data) { stop(); void resolve(code.data); return; }
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  useEffect(() => () => stop(), []);

  return (
    <>
      <PageHeader title={t("scan.title")} />
      <Stack maw={520}>
        <video ref={video} playsInline muted style={{ width: "100%", borderRadius: 8, background: "#000", display: running ? "block" : "none" }} />
        <canvas ref={canvas} style={{ display: "none" }} />
        <Group>
          {!running ? <Button onClick={() => void start()} className="tap-target">{t("scan.start")}</Button> : <Button color="gray" onClick={stop}>{t("scan.stop")}</Button>}
        </Group>
        {msg && <Alert color="blue">{msg}</Alert>}
        <Text size="sm" c="dimmed">{t("scan.manual")}</Text>
        <Group>
          <TextInput value={manual} onChange={(e) => setManual(e.currentTarget.value)} placeholder="cmms:asset:…" style={{ flex: 1 }} data-testid="qr-manual" />
          <Button onClick={() => void resolve(manual)} disabled={!manual}>{t("common.open")}</Button>
        </Group>
      </Stack>
    </>
  );
}
