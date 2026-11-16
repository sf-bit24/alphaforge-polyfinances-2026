import "server-only";
import type { ErrorEnvelope, Locale } from "@/lib/contract/schemas";

/** HTTP status the gateway uses for each contract error code. */
export const STATUS_BY_CODE: Record<string, number> = {
  bad_request: 400,
  unknown_action: 400,
  unauthorized: 401,
  forbidden: 403,
  invalid_answer: 422,
  not_found: 404,
  conflict: 409,
  guardrail_blocked: 422,
  model_error: 502,
  internal: 500,
};

/**
 * An error raised by the gateway itself (not by a runtime). Codes stay within the contract's list;
 * `unauthorized` and `forbidden` come from the sign-in only (CONTRACTS.md 7.1).
 */
export class GatewayError extends Error {
  constructor(
    readonly code: "bad_request" | "unknown_action" | "unauthorized" | "forbidden" | "not_found" | "internal",
    readonly text: { fr: string; en: string },
    readonly status: number,
    readonly details: Record<string, unknown> = {},
  ) {
    super(text.en);
  }

  envelope(locale: Locale): ErrorEnvelope {
    return {
      ok: false,
      release: null,
      error: { code: this.code, message: this.text[locale], details: { source: "gateway", ...this.details } },
    };
  }
}

export function localeOf(request: Request): Locale {
  return request.headers.get("x-alphaforge-locale") === "en" ? "en" : "fr";
}

export function jsonResponse(status: number, body: unknown): Response {
  return Response.json(body, { status, headers: { "cache-control": "no-store" } });
}

export function statusOfEnvelope(body: unknown, fallback = 200): number {
  if (body && typeof body === "object" && (body as { ok?: unknown }).ok === false) {
    const code = (body as { error?: { code?: unknown } }).error?.code;
    return typeof code === "string" ? (STATUS_BY_CODE[code] ?? 500) : 500;
  }
  return fallback >= 200 && fallback < 300 ? fallback : 200;
}

/** Wrap anything thrown while calling a runtime into a gateway error. */
export function toGatewayError(error: unknown): GatewayError {
  if (error instanceof GatewayError) return error;
  const message = error instanceof Error ? error.message : String(error);
  return new GatewayError(
    "internal",
    { fr: `Erreur inattendue de la passerelle : ${message}`, en: `Unexpected gateway error: ${message}` },
    500,
  );
}
