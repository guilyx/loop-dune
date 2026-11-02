import { describe, expect, it } from "vitest";

import { bearerMatches } from "@/lib/revalidate";

describe("bearerMatches", () => {
  it("accepts the configured token", () => {
    expect(bearerMatches("Bearer s3cret", "s3cret")).toBe(true);
  });

  it.each([
    ["wrong token", "Bearer nope", "s3cret"],
    ["missing header", null, "s3cret"],
    ["other scheme", "Basic s3cret", "s3cret"],
    ["unset secret", "Bearer ", undefined],
    ["empty secret", "Bearer ", ""],
  ])("rejects %s", (_, header, secret) => {
    expect(bearerMatches(header, secret)).toBe(false);
  });
});
