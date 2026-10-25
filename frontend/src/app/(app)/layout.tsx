import type { ReactNode } from "react";
import { AppFrame } from "@/components/AppFrame";

export default function AppLayout({ children }: { children: ReactNode }) {
  return <AppFrame>{children}</AppFrame>;
}
