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

/** The word to type to confirm « Supprimer mon compte », in each language; the server accepts either. */
export const DELETE_CONFIRMATION = { fr: "SUPPRIMER", en: "DELETE" } as const;

/** `POST /api/auth/delete-account` body: the confirmation word, typed by the investor. */
export const DeleteAccountRequest = z.object({ confirmation: z.string().max(64) });

/** Steps of the deletion, in order (a failed step comes back in `error.details.step`). */
export const DELETION_STEPS = ["knowledge_base", "vector_index", "objects", "account"] as const;
export type DeletionStepName = (typeof DELETION_STEPS)[number];

/** What was deleted; then the browser goes to `logout_url` (Cognito's `/logout`, back to the interface). */
export const DeleteAccountResponse = z.object({
  ok: z.literal(true),
  deleted: z.object({
    knowledge_bases: z.array(z.string()),
    vector_index: z.enum(["deleted", "absent"]),
    objects: z.number().int().nonnegative(),
    account: z.enum(["deleted", "absent"]),
  }),
  logout_url: z.url(),
});
export type DeleteAccountResponse = z.infer<typeof DeleteAccountResponse>;

/** True when `value` is the confirmation word of either language (spaces and case aside). */
export function isDeleteConfirmation(value: string): boolean {
  const word = value.normalize("NFC").trim().toUpperCase();
  return word === DELETE_CONFIRMATION.fr || word === DELETE_CONFIRMATION.en;
}
