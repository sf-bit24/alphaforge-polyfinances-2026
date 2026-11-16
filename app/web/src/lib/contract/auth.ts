/**
 * `GET /api/auth/me` (CONTRACTS.md 7.1): the sign-in mode of the server and the signed-in account.
 * In cognito mode without a session, the route answers 401 with the error envelope (`unauthorized`).
 */
import { z } from "zod";

export const AUTH_MODES = ["off", "cognito"] as const;

export const AccountUser = z.object({
  email: z.string().nullable(),
  /** The account's client_id: its base is `clients/<client_id>/`. */
  client_id: z.uuid(),
  groups: z.array(z.string()),
  /** Member of the `admin` group: may start a collection run. */
  admin: z.boolean(),
  expires_at: z.string(),
});
export type AccountUser = z.infer<typeof AccountUser>;

export const AuthMeResponse = z.discriminatedUnion("mode", [
  z.object({ ok: z.literal(true), mode: z.literal("off"), user: z.null() }),
  z.object({ ok: z.literal(true), mode: z.literal("cognito"), user: AccountUser }),
]);
export type AuthMeResponse = z.infer<typeof AuthMeResponse>;
