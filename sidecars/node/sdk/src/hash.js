const FNV_OFFSET_BASIS = 0xcbf29ce484222325n;
const FNV_PRIME = 0x100000001b3n;
const MASK_64 = (1n << 64n) - 1n;

function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value !== null && typeof value === "object") {
    const sorted = {};
    for (const key of Object.keys(value).sort()) {
      sorted[key] = canonicalize(value[key]);
    }
    return sorted;
  }
  return value;
}

export function canonicalJson(value) {
  return Buffer.from(JSON.stringify(canonicalize(value)), "utf8");
}

export function fnv1a64(data) {
  let digest = FNV_OFFSET_BASIS;
  for (const byte of data) {
    digest ^= BigInt(byte);
    digest = (digest * FNV_PRIME) & MASK_64;
  }
  return digest.toString(16).padStart(16, "0");
}

export function schemaHash(descriptor) {
  return fnv1a64(canonicalJson(descriptor));
}
