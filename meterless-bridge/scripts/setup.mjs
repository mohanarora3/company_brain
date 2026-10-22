// Vendors the Meterless reference engines (Apache-2.0) into meterless-bridge/vendor/.
//
//   npm run setup                         # sparse git clone at the pinned commit
//   METERLESS_SRC=/path/to/Meterless npm run setup   # copy from a local checkout instead
//
// Mirrors the official agentathon-starter, which vendors engines/hmem/reference the same way.

import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PINNED = "1742dec56a66e58eef9dda2d2b865823758ca8cd"; // Meterless/Meterless main, 19 Oct 2026
const REPO = "https://github.com/Meterless/Meterless.git";
const here = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.join(here, "..", "vendor");
const ENGINES = { hmem: "engines/hmem/reference", "world-model": "engines/world-model/reference" };

function copyEngine(src, name) {
  const from = path.join(src, ENGINES[name]);
  if (!fs.existsSync(path.join(from, "src", "index.ts"))) throw new Error(`missing ${from}/src/index.ts`);
  const to = path.join(vendor, name);
  fs.rmSync(to, { recursive: true, force: true });
  fs.mkdirSync(to, { recursive: true });
  fs.cpSync(path.join(from, "src"), path.join(to, "src"), { recursive: true });
  for (const f of ["package.json", "README.md"]) {
    if (fs.existsSync(path.join(from, f))) fs.copyFileSync(path.join(from, f), path.join(to, f));
  }
  console.log(`vendored ${name} <- ${ENGINES[name]}`);
}

function main() {
  fs.mkdirSync(vendor, { recursive: true });
  let src = process.env.METERLESS_SRC;
  let tmp;
  let commit = "local checkout";
  if (!src) {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "meterless-"));
    console.log(`cloning ${REPO} @ ${PINNED.slice(0, 12)} ...`);
    execSync(`git clone --quiet --filter=blob:none --no-checkout ${REPO} "${tmp}"`, { stdio: "inherit" });
    execSync(`git -C "${tmp}" sparse-checkout set --no-cone ${Object.values(ENGINES).join(" ")} LICENSE`, { stdio: "inherit" });
    execSync(`git -C "${tmp}" checkout --quiet ${PINNED}`, { stdio: "inherit" });
    src = tmp;
    commit = PINNED;
  }
  for (const name of Object.keys(ENGINES)) copyEngine(src, name);
  if (fs.existsSync(path.join(src, "LICENSE"))) fs.copyFileSync(path.join(src, "LICENSE"), path.join(vendor, "LICENSE"));
  fs.writeFileSync(path.join(vendor, "PINNED_COMMIT"), commit + "\n");
  if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
  console.log("done. Start the bridge with: npm start");
}

try {
  main();
} catch (e) {
  console.error(`setup failed: ${e.message}`);
  console.error("Alternative: git clone https://github.com/Meterless/Meterless and run METERLESS_SRC=/path/to/Meterless npm run setup");
  process.exit(1);
}
