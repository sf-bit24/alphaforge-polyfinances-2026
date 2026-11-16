import { describe, expect, it } from "vitest";
import { dictionaries } from "@/lib/i18n/dictionary";
import { OKF_TYPES, okfTypeLabel } from "@/lib/i18n/okf-types";

/**
 * The client-language guard of LANGAGE.md: no technical word in a text the client can see.
 * It walks every string of both dictionaries (functions are called with sample arguments).
 */

/** Words a client never reads. Add one when you find a new one (LANGAGE.md, « Le garde-fou »). */
const FORBIDDEN: RegExp[] = [
  /\bAWS\b/,
  /AgentCore/i,
  /Bedrock/i,
  /Knowledge Base/,
  /Guardrails?/,
  /Cognito/i,
  /Step Functions/i,
  /\bLambda\b/,
  /DynamoDB/i,
  /\bS3\b/,
  /CloudWatch/i,
  /X-?Ray/i,
  /OpenSearch/i,
  /Next\.js/i,
  /\bzod\b/i,
  /\bruntimes?\b/i,
  /\bpasserelle\b/i,
  /\bgateway\b/i,
  /\bAPI\b/,
  /\bendpoints?\b/i,
  /\btokens?\b/i,
  /client_id/i,
  /\bJSON\b/i,
  /\bYAML\b/i,
  /Markdown/i,
  /\.md\b/,
  /\bLLM\b/i,
  /\bprompts?\b/i,
  /\bmock\b/i,
  /\bfixture\b/i,
  /\brelease\b/i,
  /\bdéploiement\b|\bdeployment\b|\bdéployé\b|\bdeployed\b/i,
  /\bserveur\b|\bserver\b/i,
  /\bA[1-6]\b/,
  /\bJudge\b/,
  /\blentilles?\b|\blens(es)?\b/i,
  /\bétape 0\b|\bstep 0\b/i,
  /\ble code\b|\bthe code\b/i,
  /\bOKF\b/,
  /\bAGENT_MODE\b|\bAUTH_MODE\b/,
  /\btraces?\b/i,
];

/**
 * Sections only the team's view shows (`useOperator`, LANGAGE.md): they may keep technical words.
 * A path matches when it starts with one of these prefixes.
 */
const OPERATOR_ONLY: string[] = ["mode.", "collect."];

const SAMPLE_ARGS = [2, "x", "y", "z"];

function collect(value: unknown, path: string, out: [string, string][]): void {
  if (typeof value === "string") {
    out.push([path, value]);
  } else if (typeof value === "function") {
    try {
      const result: unknown = (value as (...args: unknown[]) => unknown)(...SAMPLE_ARGS);
      if (typeof result === "string") out.push([path, result]);
    } catch {
      // A function that needs richer arguments: its literal parts are checked by review.
    }
  } else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) collect(child, path ? `${path}.${key}` : key, out);
  }
}

function clientStrings(root: unknown): [string, string][] {
  const out: [string, string][] = [];
  collect(root, "", out);
  return out.filter(([path]) => !OPERATOR_ONLY.some((prefix) => path.startsWith(prefix)));
}

function offenders(root: unknown): string[] {
  return clientStrings(root).flatMap(([path, text]) =>
    FORBIDDEN.filter((pattern) => pattern.test(text)).map((pattern) => `${path} ${pattern} « ${text} »`),
  );
}

describe("client language (LANGAGE.md)", () => {
  for (const locale of ["fr", "en"] as const) {
    it(`no technical word in the ${locale} dictionary`, () => {
      expect(offenders(dictionaries[locale])).toEqual([]);
    });
  }

  it("no technical word in the document type labels", () => {
    for (const locale of ["fr", "en"] as const) {
      expect(offenders(Object.fromEntries(OKF_TYPES.map((type) => [type, okfTypeLabel(type, locale)])))).toEqual([]);
    }
  });

  it("the guard catches a technical word", () => {
    expect(offenders({ a: "Lancé sur AWS AgentCore", b: (n: number) => `${n} fichiers JSON` })).toHaveLength(3);
  });
});
