/**
 * Deterministic assignment. Must stay byte-for-byte identical to
 * src/splitkit/assignment.py; tests/vectors/assignment_vectors.json enforces it.
 *
 *   bucket = fnv1a32(String(fnv1a32(`${salt}:${userId}`))) / 2**32
 */
import type { Variant } from "./types.js";

const FNV_OFFSET = 0x811c9dc5;
const FNV_PRIME = 0x01000193;
const encoder = new TextEncoder();

export function fnv1a32(text: string): number {
  let h = FNV_OFFSET;
  for (const byte of encoder.encode(text)) {
    h ^= byte;
    h = Math.imul(h, FNV_PRIME) >>> 0;
  }
  return h >>> 0;
}

export function bucket(salt: string, userId: string): number {
  return fnv1a32(String(fnv1a32(`${salt}:${userId}`))) / 2 ** 32;
}

export function validateVariants(variants: readonly Variant[]): void {
  if (variants.length < 2) throw new Error("an experiment needs at least 2 variants");
  if (new Set(variants.map((v) => v.name)).size !== variants.length) {
    throw new Error("variant names must be unique");
  }
  if (variants.some((v) => !(v.weight > 0 && v.weight <= 1))) {
    throw new Error("variant weights must be in (0, 1]");
  }
  const total = variants.reduce((sum, v) => sum + v.weight, 0);
  if (Math.abs(total - 1) > 1e-9) throw new Error("variant weights must sum to 1");
}

export function assign(variants: readonly Variant[], salt: string, userId: string): string {
  validateVariants(variants);
  const b = bucket(salt, userId);
  let cumulative = 0;
  for (const v of variants) {
    cumulative += v.weight;
    if (b < cumulative) return v.name;
  }
  return variants[variants.length - 1]!.name; // float round-off guard
}
