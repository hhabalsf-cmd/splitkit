import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { assign, bucket, fnv1a32 } from "../src/assign.js";

interface VectorCase {
  salt: string;
  user_id: string;
  variants: { name: string; weight: number }[];
  expected: string;
}

const vectorsPath = fileURLToPath(new URL("../../tests/vectors/assignment_vectors.json", import.meta.url));
const vectors = JSON.parse(readFileSync(vectorsPath, "utf8")) as { cases: VectorCase[] };

describe("fnv1a32", () => {
  it.each([
    ["", 0x811c9dc5],
    ["a", 0xe40c292c],
    ["foobar", 0xbf9cf968],
  ])("matches published value for %j", (text, expected) => {
    expect(fnv1a32(text)).toBe(expected);
  });

  it("hashes UTF-8 bytes, not UTF-16 code units", () => {
    // "é" is 2 UTF-8 bytes; a code-unit implementation would match Python only by accident
    expect(fnv1a32("é")).not.toBe(fnv1a32("e"));
  });
});

describe("assign", () => {
  it("agrees with the Python reference on every shared vector", () => {
    expect(vectors.cases.length).toBeGreaterThan(0);
    for (const c of vectors.cases) {
      expect(assign(c.variants, c.salt, c.user_id), JSON.stringify(c)).toBe(c.expected);
    }
  });

  it("is deterministic and bounded", () => {
    const b = bucket("salt", "user-42");
    expect(b).toBeGreaterThanOrEqual(0);
    expect(b).toBeLessThan(1);
    expect(bucket("salt", "user-42")).toBe(b);
  });

  it("splits sequential ids evenly", () => {
    const ab = [
      { name: "control", weight: 0.5 },
      { name: "treatment", weight: 0.5 },
    ];
    let treatment = 0;
    const n = 100_000;
    for (let i = 0; i < n; i++) if (assign(ab, "exp-salt", `user-${i}`) === "treatment") treatment++;
    // 4 standard deviations of a fair binomial
    expect(Math.abs(treatment - n / 2)).toBeLessThan(4 * Math.sqrt(n / 4));
  });

  it("rejects invalid variant sets", () => {
    expect(() => assign([{ name: "a", weight: 1 }], "s", "u")).toThrow();
    expect(() => assign([{ name: "a", weight: 0.5 }, { name: "b", weight: 0.4 }], "s", "u")).toThrow();
    expect(() => assign([{ name: "a", weight: 0.5 }, { name: "a", weight: 0.5 }], "s", "u")).toThrow();
    expect(() => assign([{ name: "a", weight: 0 }, { name: "b", weight: 1 }], "s", "u")).toThrow();
  });
});
