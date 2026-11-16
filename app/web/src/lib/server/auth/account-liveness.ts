import "server-only";
import { AdminGetUserCommand } from "@aws-sdk/client-cognito-identity-provider";
import { getConfig, userPoolIdOf } from "../config";
import { awsDeletionClients } from "./account-deletion";
import { identityOf, unauthorized, type Identity } from "./guard";
import { nowSeconds } from "./seal";
import { revokeAccount, type AccountSession } from "./session";

/**
 * Is the account of a session still there? A session is a sealed cookie the server cannot recall. After « Supprimer
 * mon compte », the process that deleted the account refuses its sessions (`revokeAccount`), but another ECS task,
 * or the same one after a restart, does not know: a cookie kept on another device would open the base again, and
 * `session.start` would recreate it (and, in aws mode, a client Knowledge Base on the quota of 100).
 *
 * So in aws mode with sign-in, every route that reads or writes a base asks Cognito (`AdminGetUser`, username = sub),
 * at most every LIVE_SECONDS per account. A deleted account (`UserNotFoundException`) is revoked here too and gets
 * 401. Any other error lets the request through, logged: Cognito having a bad minute must not sign everybody out.
 * Not in the proxy (synchronous, and the AWS SDK stays out of its bundle): `liveIdentityOf` is called by the routes.
 */
const LIVE_SECONDS = 300;
/** After a failed check, the next one waits this long: no AdminGetUser per request while Cognito is unwell. */
const UNKNOWN_SECONDS = 30;
/** A check under way serves the concurrent requests of the same account. */
const PENDING_SECONDS = 10;
const TIMEOUT_MS = 2_000;

type Verdict = "live" | "gone" | "unknown";
type Check = { until: number; verdict: Promise<Verdict> };

const store = globalThis as unknown as { __alphaforgeLiveness?: Map<string, Check> };
const checks = (store.__alphaforgeLiveness ??= new Map<string, Check>());

async function askCognito(session: AccountSession, userPoolId: string, region: string): Promise<Verdict> {
  try {
    const command = new AdminGetUserCommand({ UserPoolId: userPoolId, Username: session.sub });
    await awsDeletionClients(region).cognito.send(command, { abortSignal: AbortSignal.timeout(TIMEOUT_MS) });
    return "live";
  } catch (error) {
    if (error instanceof Error && error.name === "UserNotFoundException") return "gone";
    const reason = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    console.warn(`Account check skipped for client_id=${session.client_id} (AdminGetUser failed): ${reason}`);
    return "unknown";
  }
}

const KEEP_SECONDS: Record<Verdict, number> = { live: LIVE_SECONDS, unknown: UNKNOWN_SECONDS, gone: 0 };

function verdictOf(session: AccountSession, userPoolId: string, region: string): Promise<Verdict> {
  const known = checks.get(session.sub);
  if (known && known.until > nowSeconds()) return known.verdict;
  const verdict = askCognito(session, userPoolId, region);
  checks.set(session.sub, { until: nowSeconds() + PENDING_SECONDS, verdict });
  void verdict.then((result) => {
    if (result === "gone") checks.delete(session.sub);
    else checks.set(session.sub, { until: nowSeconds() + KEEP_SECONDS[result], verdict });
  });
  return verdict;
}

/** The region when the server calls AWS (`AGENT_MODE=aws`); null otherwise, or when the configuration is broken (the route says so). */
function awsRegion(): string | null {
  try {
    const config = getConfig();
    return config.AGENT_MODE === "aws" ? config.AWS_REGION : null;
  } catch {
    return null;
  }
}

/** Throws `unauthorized` (401) when Cognito says the account of the session no longer exists. */
export async function assertAccountLive(identity: Identity): Promise<void> {
  if (identity.mode === "off") return;
  const region = awsRegion();
  if (!region) return;
  if ((await verdictOf(identity.session, userPoolIdOf(identity.config), region)) !== "gone") return;
  revokeAccount(identity.session);
  throw unauthorized();
}

/** `identityOf`, then the check of the account with Cognito. */
export async function liveIdentityOf(request: Request): Promise<Identity> {
  const identity = identityOf(request);
  await assertAccountLive(identity);
  return identity;
}
