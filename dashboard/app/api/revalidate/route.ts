import { revalidatePath } from "next/cache";

import { bearerMatches } from "@/lib/revalidate";

export const dynamic = "force-dynamic";

/**
 * On-demand refresh: rebuild every cached page from the database now instead of at
 * the next hourly revalidation. Called by the indexer after each cycle and by the
 * VPS deploy script; disabled (404) unless REVALIDATE_TOKEN is set.
 */
export async function POST(request: Request): Promise<Response> {
  const secret = process.env.REVALIDATE_TOKEN;
  if (!secret) return new Response("not found", { status: 404 });
  if (!bearerMatches(request.headers.get("authorization"), secret)) {
    return new Response("unauthorized", { status: 401 });
  }
  revalidatePath("/", "layout");
  return Response.json({ revalidated: true, at: new Date().toISOString() });
}
