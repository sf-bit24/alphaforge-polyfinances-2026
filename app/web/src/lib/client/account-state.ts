import { AuthMeResponse, type AccountUser } from "@/lib/contract/auth";

/**
 * The sign-in state of this browser (CONTRACTS.md 7.1), read once from `GET /api/auth/me`.
 * `off`: no sign-in on this server, the client_id stays in localStorage as before.
 * `signed_in`: the account's client_id is the only one the server accepts.
 * `signed_out`: sign-in is on but there is no session (the `/login` page).
 */
export type AccountState =
  | { status: "loading" }
  | { status: "off" }
  | { status: "signed_in"; user: AccountUser }
  | { status: "signed_out" };

/** The state of a `/api/auth/me` answer. A server without the route, or a failed read, means no sign-in. */
export async function readAccount(response: Response): Promise<AccountState> {
  if (response.status === 401) return { status: "signed_out" };
  const parsed = AuthMeResponse.safeParse(await response.json().catch(() => null));
  if (!parsed.success || parsed.data.mode === "off") return { status: "off" };
  return { status: "signed_in", user: parsed.data.user };
}
