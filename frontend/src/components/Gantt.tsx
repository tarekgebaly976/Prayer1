"use client";

import { Box, Group, ScrollArea, Text } from "@mantine/core";

export interface GanttItem { id: string; label: string; start: string | null; end: string | null; critical?: boolean; progress?: number; color?: string }

/** Lightweight dependency-free Gantt: bars positioned by time between the window bounds. */
export function Gantt({ items, from, to }: { items: GanttItem[]; from: string; to: string }) {
  const t0 = new Date(from).getTime();
  const t1 = Math.max(new Date(to).getTime(), ...items.map((i) => (i.end ? new Date(i.end).getTime() : 0)));
  const span = Math.max(t1 - t0, 1);
  const pct = (v: string) => ((new Date(v).getTime() - t0) / span) * 100;
  const ticks = 6;
  return (
    <ScrollArea type="auto">
      <Box miw={640} dir="ltr">
        <Group justify="space-between" mb={4} ps={160}>
          {Array.from({ length: ticks + 1 }, (_, i) => (
            <Text key={i} size="xs" c="dimmed">{new Date(t0 + (span * i) / ticks).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" })}</Text>
          ))}
        </Group>
        {items.map((it) => (
          <Group key={it.id} gap={0} wrap="nowrap">
            <Text size="xs" w={160} truncate pe={6}>{it.label}</Text>
            <div className="gantt-row" style={{ flex: 1 }}>
              {it.start && it.end && (
                <div className="gantt-bar" title={`${it.label}: ${new Date(it.start).toLocaleString()} → ${new Date(it.end).toLocaleString()}`}
                  style={{ left: `${pct(it.start)}%`, width: `${Math.max(pct(it.end) - pct(it.start), 0.8)}%`,
                    background: it.color ?? (it.critical ? "var(--mantine-color-red-7)" : "var(--mantine-color-indigo-6)") }}>
                  {it.progress !== undefined ? `${Math.round(it.progress)}%` : ""}
                </div>
              )}
            </div>
          </Group>
        ))}
      </Box>
    </ScrollArea>
  );
}
