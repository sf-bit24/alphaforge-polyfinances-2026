import "server-only";
import { DELETE_CONFIRMATION, DeleteAccountRequest, isDeleteConfirmation, type DeleteAccountResponse, type DeletionStepName } from "@/lib/contract/auth";
import { getMockRuntime } from "@/lib/mock/runtime";
import { ConfigError, getDeletionConfig, type CognitoConfig, type DeletionConfig, type GatewayConfig } from "../config";
import { GatewayError, jsonResponse, localeOf, toGatewayError } from "../errors";
import { configOrThrow } from "../gateway";
import { awsDeletionClients, DeletionError, deleteAccountData, type DeletionClients, type DeletionReport } from "./account-deletion";
import { authConfigOrThrow, forbidden, unauthorized } from "./guard";
import { logoutUrl } from "./oidc";
import { isCrossSitePost } from "./routes";
import { clearedSessionCookie, noticeCookie, readSession, revokeAccount, type AccountSession } from "./session";

/**
 * `POST /api/auth/delete-account` (CONTRACTS.md 7.1): « Supprimer mon compte ». Session required, a form from another
 * site refused (same rule as the sign-out), and the confirmation word in the body. Only the base of the session's
 * client_id is deleted: no identifier is read from the body.
 */

const STEP_TEXT: Record<DeletionStepName, { fr: string; en: string }> = {
  knowledge_base: {
    fr: "la Knowledge Base de votre profil n’a pas pu être supprimée",
    en: "your profile’s Knowledge Base could not be deleted",
  },
  vector_index: {
    fr: "l’index de recherche de votre profil n’a pas pu être supprimé",
    en: "your profile’s search index could not be deleted",
  },
  objects: { fr: "les documents de votre base n’ont pas pu être supprimés", en: "the documents of your base could not be deleted" },
  account: {
    fr: "vos données sont supprimées, mais le compte de connexion n’a pas pu l’être",
    en: "your data is deleted, but the sign-in account could not be",
  },
};

function notFound(): GatewayError {
  return new GatewayError(
    "not_found",
    { fr: "Aucun compte à supprimer : la connexion n’est pas activée.", en: "No account to delete: sign-in is not on." },
    404,
  );
}

function badRequest(text: { fr: string; en: string }, details: Record<string, unknown> = {}): GatewayError {
  return new GatewayError("bad_request", text, 400, details);
}

/** The confirmation of the body, checked here: the word of either language, nothing else. */
async function requireConfirmation(request: Request): Promise<void> {
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    throw badRequest({ fr: "Votre demande n’a pas pu être lue.", en: "Your request could not be read." });
  }
  const parsed = DeleteAccountRequest.safeParse(await request.json().catch(() => null));
  if (!parsed.success || !isDeleteConfirmation(parsed.data.confirmation)) {
    throw badRequest(
      {
        fr: `Confirmation absente ou fausse : tapez ${DELETE_CONFIRMATION.fr}.`,
        en: `Missing or wrong confirmation: type ${DELETE_CONFIRMATION.en}.`,
      },
      { field: "confirmation" },
    );
  }
}

function deletionConfigOrThrow(auth: CognitoConfig): DeletionConfig {
  try {
    return getDeletionConfig(auth);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    const names = error.issues.map((issue) => issue.variable).join(", ");
    throw new GatewayError(
      "internal",
      { fr: `Configuration de la suppression invalide : ${names}`, en: `Invalid account deletion configuration: ${names}` },
      500,
      { issues: error.issues },
    );
  }
}

function stoppedAt(error: DeletionError): GatewayError {
  const text = STEP_TEXT[error.step];
  const reason = error.reason instanceof Error ? error.reason : null;
  console.error(`Account deletion stopped at ${error.step}:`, reason ? `${reason.name}: ${reason.message}` : String(error.reason));
  return new GatewayError(
    "internal",
    {
      fr: `Suppression interrompue : ${text.fr}. Votre compte est gardé, réessayez dans un instant.`,
      en: `Deletion stopped: ${text.en}. Your account is kept, try again in a moment.`,
    },
    502,
    { step: error.step, completed: error.completed, aws_error: reason?.name ?? null },
  );
}

/** `mock`: the simulated client is forgotten; `aws`: the four steps of account-deletion.ts; `local`: refused. */
async function runDeletion(gateway: GatewayConfig, auth: CognitoConfig, session: AccountSession, clients?: DeletionClients): Promise<DeletionReport> {
  if (gateway.AGENT_MODE === "mock") {
    const objects = getMockRuntime().forgetClient(session.client_id) ?? 0;
    return { knowledge_bases: [], vector_index: "absent", objects, account: "deleted" };
  }
  if (gateway.AGENT_MODE === "local") {
    throw badRequest(
      { fr: "La suppression du compte n’est pas disponible ici.", en: "Account deletion is not available here." },
      { mode: "local" },
    );
  }
  const names = deletionConfigOrThrow(auth);
  const target = {
    clientId: session.client_id,
    sub: session.sub,
    userPoolId: names.USER_POOL_ID,
    bucket: names.ALPHAFORGE_BUCKET,
    kbPrefix: names.ALPHAFORGE_CLIENT_KB_PREFIX,
    vectorBucket: names.ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET,
  };
  try {
    return await deleteAccountData(target, clients ?? awsDeletionClients(gateway.AWS_REGION));
  } catch (error) {
    throw error instanceof DeletionError ? stoppedAt(error) : error;
  }
}

function deletedResponse(config: CognitoConfig, report: DeletionReport): Response {
  const body: DeleteAccountResponse = { ok: true, deleted: report, logout_url: logoutUrl(config).toString() };
  const headers = new Headers({ "content-type": "application/json", "cache-control": "no-store" });
  headers.append("set-cookie", clearedSessionCookie(config));
  headers.append("set-cookie", noticeCookie(config, "account_deleted"));
  return new Response(JSON.stringify(body), { status: 200, headers });
}

/** The account of the request, after the checks that need no body: sign-in on, same site, a session. */
function callerOf(request: Request): { config: CognitoConfig; session: AccountSession } {
  const config = authConfigOrThrow();
  if (config.AUTH_MODE === "off") throw notFound();
  if (isCrossSitePost(request, config.APP_URL)) {
    const details = { origin: request.headers.get("origin"), sec_fetch_site: request.headers.get("sec-fetch-site") };
    throw forbidden({ fr: "Suppression refusée : demande venue d’un autre site.", en: "Deletion refused: request from another site." }, details);
  }
  const session = readSession(request, config);
  if (!session) throw unauthorized();
  return { config, session };
}

/**
 * Delete the account of the session, then answer with Cognito's `/logout` URL: the session cookie is cleared and
 * the `/login` page will say « Compte supprimé ». A failed step answers 502 and keeps the account and the session.
 */
export async function handleDeleteAccount(request: Request, clients?: DeletionClients): Promise<Response> {
  try {
    const { config, session } = callerOf(request);
    await requireConfirmation(request);
    const report = await runDeletion(configOrThrow(), config, session, clients);
    revokeAccount(session);
    console.info(`Account deleted: client_id=${session.client_id} objects=${report.objects} knowledge_bases=${report.knowledge_bases.length}`);
    return deletedResponse(config, report);
  } catch (error) {
    const gatewayError = toGatewayError(error);
    return jsonResponse(gatewayError.status, gatewayError.envelope(localeOf(request)));
  }
}
