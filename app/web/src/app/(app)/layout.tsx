import type { ReactNode } from "react";
import { AppNav } from "@/components/layout/app-nav";

/** Dashboard, details, knowledge base and settings: the drafts' top navigation above the page. */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <AppNav />
      <main id="main" tabIndex={-1} className="flex min-h-[calc(100dvh-65px)] flex-col focus:outline-none">
        {children}
      </main>
    </>
  );
}
