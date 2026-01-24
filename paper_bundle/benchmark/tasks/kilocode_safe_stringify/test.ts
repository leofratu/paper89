import assert from "node:assert/strict"
import crypto from "node:crypto"

import { argToString, safeStringify } from "../../packages/agent-runtime/src/utils/safe-stringify.ts"

const EXPECTED_HASHES = {
  top_level: "378e07195a24018246e6e7caf7103e37c36e1fe15b9ec74a79a292bff9f826ed",
  nested_object: "f34f2f4a258aa396e331ea601e47f72c0ba6ac5d82ad0d8f9d8e16f8766fa0f7",
}

function digest(value: string | object) {
  const normalized = typeof value === "string" ? value : JSON.stringify(value)
  return crypto.createHash("sha256").update(normalized).digest("hex")
}

function expectHash(label: string, actual: string | object, expectedHash: string) {
  const actualHash = digest(actual)
  assert.ok(actualHash === expectedHash, `${label} mismatch`)
}

expectHash("top_level", argToString(12n), EXPECTED_HASHES.top_level)

const nestedObject = safeStringify({ value: 9007199254740993n })
expectHash("nested_object", nestedObject as object, EXPECTED_HASHES.nested_object)
