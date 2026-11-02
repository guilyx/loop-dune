import { createHash, timingSafeEqual } from "node:crypto";

/**
 * Constant-time check of an `Authorization: Bearer <token>` header against the
 * configured secret. An unset or empty secret never matches.
 */
export function bearerMatches(header: string | null, secret: string | undefined): boolean {
  if (!secret || !header?.startsWith("Bearer ")) return false;
  const digest = (value: string) => createHash("sha256").update(value).digest();
  return timingSafeEqual(digest(header.slice("Bearer ".length).trim()), digest(secret));
}
