import assert from "node:assert/strict"
import crypto from "node:crypto"

import { getDirectory } from "../../packages/util/src/path.ts"

const CASES = [
  { name: "readme", input: "README.md", expectedHash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" },
  { name: "root_file", input: "/file.txt", expectedHash: "8a5edab282632443219e051e4ade2d1d5bbc671c781051bf1437897cbdfea0f1" },
  { name: "nested_file", input: "src/index.ts", expectedHash: "e88f707fcae6f35251afab324d28934cd6ffc27aad1ce25e820164d568286403" },
  { name: "windows_file", input: "C:\\file.txt", expectedHash: "8545a81f99f36eda523c5e88e45567d21aaf5ea733e5595596cb07dd7364e8e4" },
]

function digest(value: string) {
  return crypto.createHash("sha256").update(value).digest("hex")
}

for (const testCase of CASES) {
  const actual = getDirectory(testCase.input)
  const actualHash = digest(actual)
  assert.ok(actualHash === testCase.expectedHash, `${testCase.name} mismatch`)
}
