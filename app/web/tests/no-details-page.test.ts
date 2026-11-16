import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = fileURLToPath(new URL("../src", import.meta.url));

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(tsx?|css)$/.test(entry.name) ? [path] : [];
  });
}

describe("the Details page is gone", () => {
  it("has no route left", () => {
    expect(existsSync(join(SRC, "app", "(app)", "details"))).toBe(false);
    expect(existsSync(join(SRC, "components", "details"))).toBe(false);
  });

  it("is linked from no screen, the navigation and the assistant's example replies included", () => {
    const linking = sourceFiles(SRC).filter((path) => /["'`]\/details\b/.test(readFileSync(path, "utf8")));
    expect(linking).toEqual([]);
  });
});
