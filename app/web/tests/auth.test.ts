/**
 * Sign-in (CONTRACTS.md 7.1): the client_id of an account, the encrypted cookies, the OIDC flow
 * against a local key, and the guard of the gateway in cognito mode and in off mode.
 */
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT, type JWTVerifyGetKey } from "jose";
import { ErrorEnvelope } from "@/lib/contract/schemas";
import { accountClientId } from "@/lib/server/auth/client-id";
import { bindPortfolioBody, type Identity } from "@/lib/server/auth/guard";
import { guardRequest } from "@/lib/server/auth/proxy-guard";
import { handleCallback, handleLogin, handleLogout, handleMe, safeNext } from "@/lib/server/auth/routes";
import { seal, unseal } from "@/lib/server/auth/seal";
import { sessionCookie, type AccountSession } from "@/lib/server/auth/session";
import { getAuthConfig, type CognitoConfig } from "@/lib/server/config";
import { handleAgent, handleCollectGet, handleCollectPost, handlePortfolio } from "@/lib/server/gateway";
import LoginPage from "@/app/login/page";

const keys = vi.hoisted(() => ({ get: null as unknown as JWTVerifyGetKey }));
const page = vi.hoisted(() => ({ cookies: new Map<string, string>() }));

// The /login page reads its cookies with next/headers and leaves with redirect(): both stand in here.
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => (page.cookies.has(name) ? { name, value: page.cookies.get(name) } : undefined) }),
}));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT ${url}`);
  },
}));

// The user pool's JWKS is a local key here: no network.
vi.mock("jose", async (importOriginal) => {
  const actual = await importOriginal<typeof import("jose")>();
  return { ...actual, createRemoteJWKSet: () => (...args: Parameters<JWTVerifyGetKey>) => keys.get(...args) };
});

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const OWN = "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90";
const OTHER = "0f1e2d3c-4b5a-4968-8776-655443322110";
const SECRET = "test-secret-of-at-least-thirty-two-characters";

const COGNITO_ENV = {
  AUTH_MODE: "cognito",
  COGNITO_ISSUER: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Test123",
  COGNITO_CLIENT_ID: "client123abc",
  COGNITO_DOMAIN: "https://alphaforge-test.auth.us-east-1.amazoncognito.com",
  APP_URL: "https://d123.cloudfront.net",
  AUTH_SESSION_SECRET: SECRET,
};
const ENV_NAMES = [...Object.keys(COGNITO_ENV), "AGENT_MODE"];
const saved = Object.fromEntries(ENV_NAMES.map((name) => [name, process.env[name]]));

function setEnv(values: Record<string, string | undefined>) {
  for (const name of ENV_NAMES) {
    if (values[name] === undefined) delete process.env[name];
    else process.env[name] = values[name];
  }
}

afterAll(() => setEnv(saved));

const cognito = () => getAuthConfig() as CognitoConfig;
const inAnHour = () => Math.floor(Date.now() / 1000) + 3600;

/** The `name=value` part of a Set-Cookie header, ready for a Cookie header. */
const cookiePair = (setCookie: string) => setCookie.split(";")[0] ?? "";

function sessionFor(overrides: Partial<AccountSession> = {}): string {
  const session: AccountSession = { sub: OWN, email: "ana@example.com", groups: [], client_id: OWN, exp: inAnHour(), ...overrides };
  return cookiePair(sessionCookie(session, cognito()));
}

const post = (path: string, body: unknown, cookie?: string) =>
  new Request(`http://localhost${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
    body: JSON.stringify(body),
  });

const get = (path: string, cookie?: string) => new Request(`http://localhost${path}`, { headers: cookie ? { cookie } : {} });

async function errorCode(response: Response): Promise<string> {
  return ErrorEnvelope.parse(await response.json()).error.code;
}

describe("client_id of an account", () => {
  it("keeps a Cognito sub that is a UUID v4", () => {
    expect(accountClientId(OWN)).toBe(OWN);
    expect(accountClientId(OWN.toUpperCase())).toBe(OWN);
  });

  it("derives a stable UUID v4 from any other sub", () => {
    const id = accountClientId("google_1234567890");
    expect(id).toBe("760f8f4d-efaf-42b6-a653-8766bb29b152");
    expect(id).toMatch(UUID_V4);
    expect(accountClientId("google_1234567890")).toBe(id);
    // A UUID of another version is not used as is.
    const v1 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8";
    expect(accountClientId(v1)).not.toBe(v1);
    expect(accountClientId(v1)).toMatch(UUID_V4);
    expect(accountClientId("a")).not.toBe(accountClientId("b"));
  });
});

describe("encrypted cookie values", () => {
  const options = { secret: SECRET, purpose: "session" as const };

  it("opens what it sealed, with its expiry", () => {
    const token = seal({ sub: OWN }, { ...options, expiresAt: inAnHour() });
    expect(token).toMatch(/^v1\.[A-Za-z0-9_-]+$/);
    expect(token).not.toContain(OWN);
    expect(unseal(token, options)).toMatchObject({ sub: OWN });
  });

  it("refuses an altered, expired, foreign or missing value", () => {
    const token = seal({ sub: OWN }, { ...options, expiresAt: inAnHour() });
    const body = token.slice(3);
    const flipped = `v1.${body.slice(0, -2)}${body.at(-2) === "A" ? "B" : "A"}${body.at(-1)}`;
    expect(unseal(flipped, options)).toBeNull();
    expect(unseal(token, { ...options, secret: `${SECRET}-other` })).toBeNull();
    expect(unseal(token, { ...options, purpose: "login" })).toBeNull();
    expect(unseal(seal({ sub: OWN }, { ...options, expiresAt: 1 }), options)).toBeNull();
    expect(unseal("v1.garbage", options)).toBeNull();
    expect(unseal("not a token", options)).toBeNull();
    expect(unseal(undefined, options)).toBeNull();
  });
});

/** Every way found to write `//evil.example` once the URL is normalized, plus other sites and backslashes. */
const OPEN_REDIRECTS = [
  "//evil.example",
  "/.//evil.example",
  "/a/..//evil.example",
  "/%2e//evil.example",
  "/%2E//evil.example",
  "/././/evil.example",
  "/.\\/evil.example",
  "/\\evil.example",
  "/\\/evil.example",
  "/dashboard\\..\\..\\/evil.example",
  "/\t/evil.example",
  "https://evil.example/",
  "javascript:alert(1)",
];

describe("return path after sign-in", () => {
  it("keeps a path of the interface", () => {
    expect(safeNext("/dashboard?tab=1")).toBe("/dashboard?tab=1");
    expect(safeNext("/knowledge")).toBe("/knowledge");
    // Encoded slashes stay a path segment, never a host.
    expect(safeNext("/%2F%2Fevil.example")).toBe("/%2F%2Fevil.example");
  });

  it.each(OPEN_REDIRECTS)("never sends the browser to another site: %s", (value) => {
    expect(safeNext(value)).toBe("/");
  });

  it("drops /login, the API routes and missing values", () => {
    expect(safeNext("/api/agent")).toBe("/");
    expect(safeNext("/login")).toBe("/");
    expect(safeNext(null)).toBe("/");
    expect(safeNext("")).toBe("/");
  });
});

describe("guard in cognito mode", () => {
  beforeEach(() => setEnv({ ...COGNITO_ENV, AGENT_MODE: "mock" }));

  it("sends a page without a session to /login, answers 401 on the API, lets public routes through", async () => {
    const page = guardRequest(get("/dashboard?x=1"));
    expect(page?.status).toBe(307);
    expect(page?.headers.get("location")).toBe("https://d123.cloudfront.net/login?next=%2Fdashboard%3Fx%3D1");
    const api = guardRequest(post("/api/agent", { action: "health" }));
    expect(api?.status).toBe(401);
    expect(await errorCode(api as Response)).toBe("unauthorized");
    for (const path of ["/login", "/api/auth/login", "/api/auth/callback", "/api/health", "/api/ping"]) {
      expect(guardRequest(get(path))).toBeNull();
    }
    expect(guardRequest(get("/dashboard", sessionFor()))).toBeNull();
    expect(guardRequest(get("/dashboard", "af_session=v1.forged"))?.status).toBe(307);
  });

  it("fails closed on a broken configuration, except the load balancer's probe", async () => {
    setEnv({ ...COGNITO_ENV, AUTH_SESSION_SECRET: "short", AGENT_MODE: "mock" });
    const response = guardRequest(get("/dashboard"));
    expect(response?.status).toBe(500);
    expect(await errorCode(response as Response)).toBe("internal");
    expect(guardRequest(get("/api/ping"))).toBeNull();
  });

  it("answers 401 in every gateway route without a session, even past the proxy", async () => {
    expect(await errorCode(await handleAgent(post("/api/agent", { action: "session.start", locale: "fr" })))).toBe("unauthorized");
    expect((await handlePortfolio(post("/api/portfolio", { persona: "amira" }))).status).toBe(401);
    expect((await handleCollectGet(get("/api/collect"))).status).toBe(401);
    expect((await handleCollectPost(post("/api/collect", {}))).status).toBe(401);
  });

  it("takes the client_id from the session: session.start opens the account's base", async () => {
    const cookie = sessionFor();
    const started = await handleAgent(post("/api/agent", { action: "session.start", locale: "fr" }, cookie));
    expect(started.status).toBe(200);
    expect(((await started.json()) as { client_id: string }).client_id).toBe(OWN);
    const resumed = await handleAgent(post("/api/agent", { action: "session.resume" }, cookie));
    expect(((await resumed.json()) as { client_id: string }).client_id).toBe(OWN);
  });

  it("refuses another client_id in the body (403)", async () => {
    const cookie = sessionFor();
    const response = await handleAgent(post("/api/agent", { action: "profile.get", client_id: OTHER }, cookie));
    expect(response.status).toBe(403);
    expect(await errorCode(response)).toBe("forbidden");
    const start = await handleAgent(post("/api/agent", { action: "session.start", locale: "fr", client_id: OTHER }, cookie));
    expect(start.status).toBe(403);
    // The same id in another case is the same client.
    const upper = await handleAgent(post("/api/agent", { action: "profile.get", client_id: OWN.toUpperCase() }, cookie));
    expect(upper.status).not.toBe(403);
  });

  it("refuses a clients/ prefix or key of another base (403), serves the account's own and general/", async () => {
    const cookie = sessionFor();
    await handleAgent(post("/api/agent", { action: "session.start", locale: "fr" }, cookie));
    const foreignList = await handleAgent(post("/api/agent", { action: "kb.list", prefix: `clients/${OTHER}/` }, cookie));
    expect(foreignList.status).toBe(403);
    const foreignGet = await handleAgent(post("/api/agent", { action: "kb.get", key: `clients/${OTHER}/profil.md` }, cookie));
    expect(foreignGet.status).toBe(403);
    const sneaky = await handleAgent(post("/api/agent", { action: "kb.get", key: `clients/${OTHER}/profil.md`, client_id: OWN }, cookie));
    expect(sneaky.status).toBe(403);
    const own = await handleAgent(post("/api/agent", { action: "kb.list", prefix: `clients/${OWN}/` }, cookie));
    expect(own.status).toBe(200);
    const general = await handleAgent(post("/api/agent", { action: "kb.list", prefix: "general/" }, cookie));
    expect(general.status).toBe(200);
  });

  it("builds a FICTION persona for any account, and only the account's own profile otherwise", async () => {
    const cookie = sessionFor();
    expect((await handlePortfolio(post("/api/portfolio", { action: "build", persona: "amira" }, cookie))).status).toBe(200);
    expect((await handlePortfolio(post("/api/portfolio", { action: "build", client_id: OTHER }, cookie))).status).toBe(403);
    const session: Identity = { mode: "cognito", config: cognito(), session: { sub: OWN, email: null, groups: [], client_id: OWN, exp: inAnHour() } };
    expect(bindPortfolioBody({ action: "build" }, session)).toEqual({ action: "build", client_id: OWN });
    expect(bindPortfolioBody({ action: "build", persona: "robert" }, session)).toEqual({ action: "build", persona: "robert" });
  });

  it("lets only the admin group start a collection run; any account reads the runs", async () => {
    const member = sessionFor();
    const refused = await handleCollectPost(post("/api/collect", {}, member));
    expect(refused.status).toBe(403);
    expect(await errorCode(refused)).toBe("forbidden");
    expect((await handleCollectGet(get("/api/collect", member))).status).toBe(200);
    const admin = sessionFor({ groups: ["admin"] });
    expect((await handleCollectPost(post("/api/collect", {}, admin))).status).toBe(200);
  });

  it("describes the account on /api/auth/me, 401 without a session", async () => {
    const me = await handleMe(get("/api/auth/me", sessionFor({ groups: ["admin"] })));
    expect(await me.json()).toMatchObject({ ok: true, mode: "cognito", user: { email: "ana@example.com", client_id: OWN, admin: true } });
    expect((await handleMe(get("/api/auth/me"))).status).toBe(401);
  });
});

describe("OIDC flow with Cognito", () => {
  let privateKey: CryptoKey;
  const fetchMock = vi.fn<typeof fetch>();

  beforeAll(async () => {
    const pair = await generateKeyPair("RS256");
    privateKey = pair.privateKey;
    keys.get = createLocalJWKSet({ keys: [{ ...(await exportJWK(pair.publicKey)), kid: "test", alg: "RS256" }] });
  });

  beforeEach(() => {
    setEnv({ ...COGNITO_ENV, AGENT_MODE: "mock" });
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  function idToken(claims: Record<string, unknown>, options: { audience?: string; expires?: string | number } = {}) {
    return new SignJWT({ token_use: "id", email: "ana@example.com", ...claims })
      .setProtectedHeader({ alg: "RS256", kid: "test" })
      .setIssuer(COGNITO_ENV.COGNITO_ISSUER)
      .setAudience(options.audience ?? COGNITO_ENV.COGNITO_CLIENT_ID)
      .setSubject(OWN)
      .setIssuedAt()
      .setExpirationTime(options.expires ?? "1h")
      .sign(privateKey);
  }

  /** Start a sign-in: the managed login URL and the login cookie. */
  function login(locale = "en", next = "/portfolio") {
    const response = handleLogin(get(`/api/auth/login?next=${encodeURIComponent(next)}`, `af_locale=${locale}`));
    const location = new URL(response.headers.get("location") ?? "");
    const setCookie = response.headers.getSetCookie()[0] ?? "";
    return { response, location, setCookie, cookie: cookiePair(setCookie) };
  }

  const callback = (state: string, cookie: string) => handleCallback(get(`/api/auth/callback?code=the-code&state=${state}`, cookie));

  it("redirects to the managed login with code, PKCE S256, state, nonce and the interface language", () => {
    const { response, location, setCookie } = login("en");
    expect(response.status).toBe(302);
    expect(`${location.origin}${location.pathname}`).toBe(`${COGNITO_ENV.COGNITO_DOMAIN}/oauth2/authorize`);
    expect(Object.fromEntries(location.searchParams)).toMatchObject({
      response_type: "code",
      client_id: COGNITO_ENV.COGNITO_CLIENT_ID,
      redirect_uri: "https://d123.cloudfront.net/api/auth/callback",
      scope: "openid email profile",
      code_challenge_method: "S256",
      lang: "en",
    });
    expect(location.searchParams.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(setCookie).toMatch(new RegExp(`^af_login_${location.searchParams.get("state")?.slice(0, 16)}=v1\\.`));
    expect(setCookie).toContain("Path=/api/auth; Max-Age=600; HttpOnly; SameSite=Lax; Secure");
    expect(login("fr").location.searchParams.get("lang")).toBe("fr");
  });

  it("exchanges the code, verifies the ID token and opens the session", async () => {
    const { location, cookie } = login();
    const token = await idToken({ nonce: location.searchParams.get("nonce"), "cognito:groups": ["admin"] });
    fetchMock.mockResolvedValue(Response.json({ id_token: token, access_token: "a", refresh_token: "r" }));
    const response = await callback(location.searchParams.get("state") ?? "", cookie);
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://d123.cloudfront.net/portfolio");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe(`${COGNITO_ENV.COGNITO_DOMAIN}/oauth2/token`);
    expect(Object.fromEntries(new URLSearchParams(String(init?.body)))).toMatchObject({
      grant_type: "authorization_code",
      client_id: COGNITO_ENV.COGNITO_CLIENT_ID,
      code: "the-code",
      redirect_uri: "https://d123.cloudfront.net/api/auth/callback",
    });
    const cookies = response.headers.getSetCookie();
    expect(cookies[0]).toMatch(/^af_login_[A-Za-z0-9_-]{16}=; Path=\/api\/auth; Max-Age=0/);
    const session = cookies.find((value) => value.startsWith("af_session=")) ?? "";
    expect(session).toContain("HttpOnly; SameSite=Lax; Secure");
    expect(session).not.toContain(token);
    const me = await handleMe(get("/api/auth/me", cookiePair(session)));
    expect(await me.json()).toMatchObject({ mode: "cognito", user: { client_id: OWN, admin: true, email: "ana@example.com" } });
  });

  it("refuses a wrong state, nonce, audience, expired token or a denied sign-in", async () => {
    const { location, cookie } = login();
    const state = location.searchParams.get("state") ?? "";
    const nonce = location.searchParams.get("nonce");
    expect((await callback("forged", cookie)).headers.get("location")).toBe("https://d123.cloudfront.net/login?error=state");
    expect((await callback(state, "")).headers.get("location")).toContain("error=state");
    const bad = [
      await idToken({ nonce: "other" }),
      await idToken({ nonce }, { audience: "another-client" }),
      await idToken({ nonce }, { expires: Math.floor(Date.now() / 1000) - 60 }),
      await idToken({ nonce, token_use: "access" }),
    ];
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    for (const token of bad) {
      fetchMock.mockResolvedValueOnce(Response.json({ id_token: token }));
      const response = await callback(state, cookie);
      expect(response.headers.get("location")).toBe("https://d123.cloudfront.net/login?error=token");
      expect(response.headers.getSetCookie().some((value) => value.startsWith("af_session="))).toBe(false);
    }
    fetchMock.mockResolvedValueOnce(Response.json({ error: "invalid_grant" }, { status: 400 }));
    expect((await callback(state, cookie)).headers.get("location")).toContain("error=token");
    const denied = await handleCallback(get("/api/auth/callback?error=access_denied", cookie));
    expect(denied.headers.get("location")).toContain("error=denied");
  });

  /** A whole sign-in, from /api/auth/login to the callback, with a valid ID token. */
  async function signIn(next: string) {
    const { location, cookie } = login("fr", next);
    fetchMock.mockResolvedValueOnce(Response.json({ id_token: await idToken({ nonce: location.searchParams.get("nonce") }) }));
    return callback(location.searchParams.get("state") ?? "", cookie);
  }

  it.each(OPEN_REDIRECTS)("comes back to the interface, never to another site: %s", async (next) => {
    expect((await signIn(next)).headers.get("location")).toBe("https://d123.cloudfront.net/");
  });

  it("comes back to the page asked for, query included", async () => {
    expect((await signIn("/dashboard?tab=1")).headers.get("location")).toBe("https://d123.cloudfront.net/dashboard?tab=1");
  });

  it("lets two tabs sign in at once: each sign-in has its own cookie", async () => {
    const first = login();
    const second = login();
    expect(first.cookie.split("=")[0]).not.toBe(second.cookie.split("=")[0]);
    const both = `${first.cookie}; ${second.cookie}`;
    for (const tab of [first, second]) {
      fetchMock.mockResolvedValueOnce(Response.json({ id_token: await idToken({ nonce: tab.location.searchParams.get("nonce") }) }));
      const response = await callback(tab.location.searchParams.get("state") ?? "", both);
      expect(response.headers.get("location")).toBe("https://d123.cloudfront.net/portfolio");
      expect(response.headers.getSetCookie().some((value) => value.startsWith("af_session=v1."))).toBe(true);
    }
    // The state of one tab never opens the sign-in of the other.
    const crossed = await callback(second.location.searchParams.get("state") ?? "", first.cookie);
    expect(crossed.headers.get("location")).toContain("error=state");
  });

  it("refuses a sign-out posted from another site (Origin), accepts the interface's own", () => {
    const from = (origin: string) =>
      handleLogout(new Request("http://localhost/api/auth/logout", { method: "POST", headers: { origin, cookie: sessionFor() } }));
    const refused = from("https://evil.example");
    expect(refused.status).toBe(403);
    expect(refused.headers.getSetCookie()).toEqual([]);
    expect(from("https://d123.cloudfront.net").status).toBe(303);
  });

  it("decides on Sec-Fetch-Site when the browser sends it, even with Origin: null (Referrer-Policy: no-referrer)", () => {
    const from = (headers: Record<string, string>) =>
      handleLogout(new Request("http://localhost/api/auth/logout", { method: "POST", headers: { ...headers, cookie: sessionFor() } }));
    // What Chrome sends for the interface's own form under Referrer-Policy: no-referrer.
    expect(from({ origin: "null", "sec-fetch-site": "same-origin" }).status).toBe(303);
    expect(from({ "sec-fetch-site": "none" }).status).toBe(303);
    for (const site of ["cross-site", "same-site"]) {
      const refused = from({ origin: "null", "sec-fetch-site": site });
      expect(refused.status).toBe(403);
      expect(refused.headers.getSetCookie()).toEqual([]);
    }
    expect(from({ origin: "https://d123.cloudfront.net", "sec-fetch-site": "cross-site" }).status).toBe(403);
    // Without Sec-Fetch-Site (older browsers), Origin: null proves nothing either way.
    expect(from({ origin: "null" }).status).toBe(303);
  });

  it("signs out: clears the session, then Cognito's /logout back to the interface", () => {
    const response = handleLogout(post("/api/auth/logout", {}, sessionFor()));
    expect(response.status).toBe(303);
    const location = new URL(response.headers.get("location") ?? "");
    expect(`${location.origin}${location.pathname}`).toBe(`${COGNITO_ENV.COGNITO_DOMAIN}/logout`);
    expect(location.searchParams.get("client_id")).toBe(COGNITO_ENV.COGNITO_CLIENT_ID);
    expect(location.searchParams.get("logout_uri")).toBe("https://d123.cloudfront.net/");
    expect(response.headers.getSetCookie()[0]).toMatch(/^af_session=; Path=\/; Max-Age=0; HttpOnly; SameSite=Lax; Secure$/);
  });

  it("drops Secure on http://localhost (next dev)", () => {
    setEnv({ ...COGNITO_ENV, APP_URL: "http://localhost:3000", AGENT_MODE: "mock" });
    const { setCookie, location } = login();
    expect(setCookie).not.toContain("Secure");
    expect(location.searchParams.get("redirect_uri")).toBe("http://localhost:3000/api/auth/callback");
  });
});

describe("/login page", () => {
  beforeEach(() => {
    setEnv({ ...COGNITO_ENV, AGENT_MODE: "mock" });
    page.cookies.clear();
  });

  const open = (next: string) => LoginPage({ searchParams: Promise.resolve({ next }) });

  it("sends a signed-in account on, to a path of the interface only", async () => {
    page.cookies.set("af_session", sessionFor().slice("af_session=".length));
    await expect(open("/dashboard?tab=1")).rejects.toThrow(/^NEXT_REDIRECT \/dashboard\?tab=1$/);
    for (const next of OPEN_REDIRECTS) await expect(open(next)).rejects.toThrow(/^NEXT_REDIRECT \/$/);
  });

  it("shows the sign-in without a session, with a safe return path", async () => {
    const view = (await open("/.//evil.example")) as { props: { next: string } };
    expect(view.props.next).toBe("/");
    page.cookies.set("af_session", "v1.forged");
    expect(((await open("/portfolio")) as { props: { next: string } }).props.next).toBe("/portfolio");
  });

  it("with sign-in off, sends the browser on, to a path of the interface only", async () => {
    setEnv({ AGENT_MODE: "mock" });
    await expect(open("/.//evil.example")).rejects.toThrow(/^NEXT_REDIRECT \/$/);
    await expect(open("/settings")).rejects.toThrow(/^NEXT_REDIRECT \/settings$/);
  });
});

describe("sign-in off (default): behavior unchanged", () => {
  beforeEach(() => setEnv({ AGENT_MODE: "mock" }));

  it("lets every request through and keeps the browser's client_id", async () => {
    expect(guardRequest(get("/dashboard"))).toBeNull();
    expect(guardRequest(post("/api/agent", { action: "health" }))).toBeNull();
    const started = await handleAgent(post("/api/agent", { action: "session.start", locale: "fr" }));
    const { client_id } = (await started.json()) as { client_id: string };
    expect(client_id).toMatch(UUID_V4);
    expect(client_id).not.toBe(OWN);
    const resumed = await handleAgent(post("/api/agent", { action: "session.resume", client_id }));
    expect(resumed.status).toBe(200);
    expect((await handleCollectPost(post("/api/collect", {}))).status).toBe(200);
  });

  it("reports the mode on /api/auth/me and sends the auth routes back to the interface", async () => {
    expect(await (await handleMe(get("/api/auth/me"))).json()).toEqual({ ok: true, mode: "off", user: null });
    const login = handleLogin(get("/api/auth/login?next=/settings"));
    expect(login.headers.get("location")).toBe("/settings");
    expect(login.headers.getSetCookie()).toEqual([]);
    expect(handleLogout(post("/api/auth/logout", {})).headers.get("location")).toBe("/");
    for (const next of OPEN_REDIRECTS) {
      expect(handleLogin(get(`/api/auth/login?next=${encodeURIComponent(next)}`)).headers.get("location")).toBe("/");
    }
  });
});
