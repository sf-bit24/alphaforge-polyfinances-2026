/**
 * `mock` mode of the `portfolio` runtime: the responses of `build` for the three FICTION demo profiles.
 *
 * The fixtures are real outputs of the finance engine (`build_portfolio` in rules mode), written by
 * app/agents/scripts/finance/export_web_fixtures.py; no number in them is written by hand. Regenerate:
 *   cd app/agents && ALPHAFORGE_BT_DATA=<long data> uv run --group finance python scripts/finance/export_web_fixtures.py
 */
import amira from "@/lib/fixtures/portfolio-amira.json";
import mateo from "@/lib/fixtures/portfolio-mateo.json";
import robert from "@/lib/fixtures/portfolio-robert.json";
import { DEMO_PERSONAS, type DemoPersona, type PortfolioBuildRequest } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";

export const PORTFOLIO_FIXTURES: Readonly<Record<DemoPersona, unknown>> = { amira, mateo, robert };

/** The response `build` would give, as the runtime's envelope (success or error). */
export function mockPortfolioBuild(request: PortfolioBuildRequest, locale: Locale): unknown {
  if (!request.persona) {
    return {
      ok: false,
      release: "mock",
      error: {
        code: "not_found",
        message:
          locale === "en"
            ? "In the simulator, only the demo profiles (Amira, Mateo, Robert) have a simulated portfolio."
            : "Dans le simulateur, seuls les profils de démonstration (Amira, Mateo, Robert) ont un portefeuille simulé.",
        details: { personas: DEMO_PERSONAS },
      },
    };
  }
  return { ...(PORTFOLIO_FIXTURES[request.persona] as Record<string, unknown>), persona: request.persona };
}
