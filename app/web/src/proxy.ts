import { NextResponse, type NextRequest } from "next/server";
import { guardRequest } from "@/lib/server/auth/proxy-guard";

/**
 * Sign-in guard (CONTRACTS.md 7.1), Node.js runtime. With `AUTH_MODE=off` every request goes on
 * unchanged; with `AUTH_MODE=cognito`, see `guardRequest`.
 */
export function proxy(request: NextRequest): Response {
  return guardRequest(request) ?? NextResponse.next();
}

export const config = {
  // Next.js internals and the icon carry nothing personal.
  matcher: ["/((?!_next/|__nextjs|icon\\.svg|favicon\\.ico).*)"],
};
