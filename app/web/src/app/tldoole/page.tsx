import type { Metadata } from "next";
import { TldooleFeed } from "@/components/tldoole/feed-view";

export const metadata: Metadata = { title: "tldoole" };

export default function TldoolePage() {
  return <TldooleFeed />;
}
