import type { Metadata } from "next";
import { PortfolioView } from "@/components/portfolio/portfolio-view";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.portfolioView.title };
}

export default function PortfolioPage() {
  return <PortfolioView />;
}
