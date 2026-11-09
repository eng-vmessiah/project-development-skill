import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { parseStatus, resolveCommand } from "../src/pd";

const valid = {
  feature: "example", phase: 1, phase_name: "Setup", total_phases: 8,
  phase_pct: 12, status: "in_progress", tasks_done: 2, tasks_total: 5,
  tasks_pct: 40, checkpoints: 1, created_at: "2026-11-09T00:00:00",
  updated_at: "2026-11-09T00:10:00",
};

test("parses a valid status payload", () => {
  assert.deepEqual(parseStatus(JSON.stringify(valid)), valid);
});

test("rejects a malformed status payload", () => {
  assert.throws(() => parseStatus("{}"), /feature/);
});

test("resolves a workspace-relative CLI path", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pd-ext-"));
  fs.mkdirSync(path.join(root, "scripts"));
  fs.writeFileSync(path.join(root, "scripts", "pd.py"), "");
  const command = resolveCommand(root, "python3", "scripts/pd.py", "status");
  assert.equal(command.executable, "python3");
  assert.deepEqual(command.args, [path.join(root, "scripts", "pd.py"), "status", "--json"]);
  assert.equal(command.cwd, root);
  fs.rmSync(root, { recursive: true, force: true });
});

test("rejects a missing CLI", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pd-ext-"));
  assert.throws(() => resolveCommand(root, "python3", "scripts/pd.py", "status"), /not found/);
  fs.rmSync(root, { recursive: true, force: true });
});
