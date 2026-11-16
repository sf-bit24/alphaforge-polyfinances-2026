import { handleDeleteAccount } from "@/lib/server/auth/delete-account";

export const dynamic = "force-dynamic";

/** « Supprimer mon compte » (CONTRACTS.md 7.1): the account's data, then its Cognito user, then sign-out. */
export function POST(request: Request): Promise<Response> {
  return handleDeleteAccount(request);
}
