/**
 * The demo scenarios of the « Portefeuille simulé » view: the three FICTION profiles of the finance
 * engine (tests/finance/policy/_personas.py) and what each one asks. Robert's request is the input
 * of the brief's « push back » case; it is sent as is, never derived.
 */
import { DEMO_PERSONAS, type DemoPersona, type InvestorRequest } from "@/lib/contract/portfolio";

export interface DemoScenario {
  persona: DemoPersona;
  /** A precise request of the investor, forwarded as `request` to `build`. */
  request?: InvestorRequest;
}

export const DEMO_SCENARIOS: Readonly<Record<DemoPersona, DemoScenario>> = {
  amira: { persona: "amira" },
  mateo: { persona: "mateo" },
  robert: { persona: "robert", request: { ticker: "TSLA", amount_cad: 50_000 } },
};

export { DEMO_PERSONAS };
