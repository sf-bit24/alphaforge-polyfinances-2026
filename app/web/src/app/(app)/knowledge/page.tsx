import type { Metadata } from "next";
import { KnowledgeView } from "@/components/kb/knowledge-view";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.kb.title };
}

export default function KnowledgePage() {
  return <KnowledgeView />;
}
