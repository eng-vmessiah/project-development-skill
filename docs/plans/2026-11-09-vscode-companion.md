# VS Code Companion Implementation Plan

> **For Hermes/Codex:** Codex edits and tests; Hermes reviews the diff, runs the
> gates, and commits. Do not push from the worker.

**Goal:** Ship a read-only VS Code companion that shows PD status, runs
`pd validate`, and opens the active SPEC without mutating `.spec`.

**Architecture:** A small TypeScript extension (`extensions/vscode/`) invokes the
existing Python CLI with `execFile` (no shell), parses `pd status --json` into a
typed object, and renders a status bar plus three commands. Pure parsing/resolution
logic lives in `src/pd.ts` so it is testable without a VS Code host.

**Tech Stack:** TypeScript 5.x, VS Code Extension API, Node 22, Node's built-in
`node:test`, Python 3.10+ CLI, GitHub Actions.

**Contract:** `docs/PHASE3-IDE-CONTRACT.md`.

---

## Task 0: Capture the baseline

**Objective:** Record the current CLI JSON shape before writing the parser.

**Files:** none.

**Step 1:** Run:

```bash
cd /home/vitor/project/project-development-skill
/usr/bin/python3 scripts/pd.py status --json
```

**Expected:** a JSON object with `feature`, `phase`, `phase_name`,
`total_phases`, `phase_pct`, `status`, `tasks_done`, `tasks_total`, `tasks_pct`,
`checkpoints`, `created_at`, `updated_at`.

**Step 2:** Save the observed output in the task log. Do not edit `.spec`.

---

## Task 1: Scaffold the extension

**Objective:** Create the package manifest, TypeScript config, and build output
ignore rules.

**Files:**
- Create: `extensions/vscode/package.json`
- Create: `extensions/vscode/tsconfig.json`
- Modify: `.gitignore`

**Step 1:** Create `extensions/vscode/package.json`:

```json
{
  "name": "pd-vscode-companion",
  "displayName": "PD Companion",
  "description": "Read-only status and validation for Project Development features.",
  "version": "0.1.0",
  "publisher": "eng-vmessiah",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Other"],
  "capabilities": {
    "untrustedWorkspaces": {
      "supported": false,
      "description": "PD Companion runs the workspace's Python CLI; trust is required."
    }
  },
  "activationEvents": ["onStartupFinished"],
  "main": "./out/src/extension.js",
  "contributes": {
    "commands": [
      { "command": "pd.showStatus", "title": "PD: Show Status" },
      { "command": "pd.validate", "title": "PD: Validate" },
      { "command": "pd.openSpec", "title": "PD: Open SPEC" }
    ],
    "configuration": {
      "title": "PD Companion",
      "properties": {
        "pd.pythonPath": {
          "type": "string",
          "default": "python3",
          "description": "Python executable used to run scripts/pd.py."
        },
        "pd.scriptPath": {
          "type": "string",
          "default": "scripts/pd.py",
          "description": "Path to pd.py, relative to the workspace root."
        }
      }
    }
  },
  "scripts": {
    "compile": "tsc -p ./",
    "watch": "tsc -watch -p ./",
    "test": "npm run compile && node --test out/test",
    "vscode:prepublish": "npm run compile"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/vscode": "^1.85.0",
    "typescript": "^5.6.0"
  }
}
```

**Step 2:** Create `extensions/vscode/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "moduleResolution": "node",
    "outDir": "out",
    "rootDir": ".",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "types": ["node", "vscode"]
  },
  "include": ["src/**/*.ts", "test/**/*.ts"],
  "exclude": ["node_modules", "out"]
}
```

**Step 3:** Append to `.gitignore`:

```gitignore

# PD Companion build output
extensions/vscode/node_modules/
extensions/vscode/out/
extensions/vscode/*.vsix
```

**Step 4:** Generate the lockfile:

```bash
cd extensions/vscode
npm install --package-lock-only
```

**Expected:** `package-lock.json` exists; no `node_modules` is required yet.

---

## Task 2: Parser and command resolver (TDD)

**Objective:** Implement pure functions that parse `status --json` and build a
safe `execFile` command.

**Files:**
- Create: `extensions/vscode/src/pd.ts`
- Create: `extensions/vscode/test/pd.test.ts`

**Step 1:** Write the failing tests in `test/pd.test.ts`:

```ts
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
  assert.throws(() => parseStatus("{}"), /phase/);
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
```

**Step 2:** Run:

```bash
cd extensions/vscode
npm test
```

**Expected:** FAIL — `src/pd.ts` is missing.

**Step 3:** Create `src/pd.ts`:

```ts
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

export interface PdStatus {
  feature: string;
  phase: number;
  phase_name: string;
  total_phases: number;
  phase_pct: number;
  status: string;
  tasks_done: number;
  tasks_total: number;
  tasks_pct: number;
  checkpoints: number;
  created_at: string;
  updated_at: string;
}

export interface PdCommand {
  executable: string;
  args: string[];
  cwd: string;
}

export interface PdResult {
  stdout: string;
  stderr: string;
  code: number;
}

const REQUIRED_FIELDS: Array<[keyof PdStatus, "string" | "number"]> = [
  ["feature", "string"], ["phase", "number"], ["phase_name", "string"],
  ["total_phases", "number"], ["phase_pct", "number"], ["status", "string"],
  ["tasks_done", "number"], ["tasks_total", "number"], ["tasks_pct", "number"],
  ["checkpoints", "number"], ["created_at", "string"], ["updated_at", "string"],
];

export function parseStatus(raw: string): PdStatus {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("PD status did not return valid JSON.");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("PD status did not return a JSON object.");
  }
  const record = value as Record<string, unknown>;
  for (const [field, expected] of REQUIRED_FIELDS) {
    if (typeof record[field] !== expected) {
      throw new Error(`PD status is missing or invalid: ${field}.`);
    }
  }
  return record as unknown as PdStatus;
}

export function resolveCommand(
  workspaceRoot: string,
  pythonPath: string,
  scriptPath: string,
  command: "status" | "validate",
): PdCommand {
  const script = path.isAbsolute(scriptPath)
    ? scriptPath
    : path.resolve(workspaceRoot, scriptPath);
  if (!fs.existsSync(script)) {
    throw new Error(`PD CLI not found: ${script}`);
  }
  return { executable: pythonPath, args: [script, command, "--json"], cwd: workspaceRoot };
}

export function runPd(command: PdCommand): Promise<PdResult> {
  return new Promise((resolve) => {
    execFile(
      command.executable,
      command.args,
      { cwd: command.cwd, timeout: 30_000, maxBuffer: 1024 * 1024, windowsHide: true },
      (error, stdout, stderr) => {
        const code = error && typeof error.code === "number" ? error.code : error ? 1 : 0;
        resolve({ stdout, stderr, code });
      },
    );
  });
}
```

**Step 4:** Run:

```bash
cd extensions/vscode
npm test
```

**Expected:** `4` tests pass.

**Step 5:** Hermes commits:

```bash
git add .gitignore extensions/vscode
git commit -m "feat(vscode): scaffold read-only pd companion"
```

---

## Task 3: Extension surface

**Objective:** Register the status bar and the three read-only commands.

**Files:**
- Create: `extensions/vscode/src/extension.ts`

**Step 1:** Create `src/extension.ts`:

```ts
import * as path from "node:path";
import * as vscode from "vscode";
import { parseStatus, resolveCommand, runPd, PdStatus } from "./pd";

let statusBar: vscode.StatusBarItem;
let output: vscode.OutputChannel;

function workspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function settings(): { pythonPath: string; scriptPath: string } {
  const config = vscode.workspace.getConfiguration("pd");
  return {
    pythonPath: config.get<string>("pythonPath", "python3"),
    scriptPath: config.get<string>("scriptPath", "scripts/pd.py"),
  };
}

async function readStatus(): Promise<PdStatus> {
  const root = workspaceRoot();
  if (!root) throw new Error("Open a PD workspace first.");
  const { pythonPath, scriptPath } = settings();
  const result = await runPd(resolveCommand(root, pythonPath, scriptPath, "status"));
  if (result.code !== 0) {
    throw new Error(result.stderr.trim() || `pd status exited with code ${result.code}.`);
  }
  return parseStatus(result.stdout);
}

function tooltip(status: PdStatus): vscode.MarkdownString {
  const tip = new vscode.MarkdownString();
  tip.appendText(`${status.phase_name} (${status.phase}/${status.total_phases})`);
  tip.appendText(`Status: ${status.status}`);
  tip.appendText(`Tasks: ${status.tasks_done}/${status.tasks_total} (${status.tasks_pct}%)`);
  tip.appendText(`Checkpoints: ${status.checkpoints}`);
  tip.appendText(`Updated: ${status.updated_at}`);
  return tip;
}

async function refresh(showMessage: boolean): Promise<void> {
  try {
    const status = await readStatus();
    statusBar.text = `PD: ${status.feature} P${status.phase}/${status.total_phases} · ${status.tasks_done}/${status.tasks_total}`;
    statusBar.tooltip = tooltip(status);
    statusBar.show();
    if (showMessage) {
      vscode.window.showInformationMessage(
        `PD: ${status.feature} — ${status.phase_name}, ${status.tasks_done}/${status.tasks_total} tasks.`,
      );
    }
  } catch (error) {
    statusBar.hide();
    if (showMessage) {
      vscode.window.showErrorMessage(`PD: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

async function validate(): Promise<void> {
  output.show(true);
  try {
    const root = workspaceRoot();
    if (!root) throw new Error("Open a PD workspace first.");
    const { pythonPath, scriptPath } = settings();
    const result = await runPd(resolveCommand(root, pythonPath, scriptPath, "validate"));
    output.appendLine(result.stdout.trim() || result.stderr.trim() || "(no output)");
    if (result.code !== 0) {
      throw new Error(`pd validate exited with code ${result.code}.`);
    }
    vscode.window.showInformationMessage("PD: validation passed.");
  } catch (error) {
    output.appendLine(`ERROR: ${error instanceof Error ? error.message : String(error)}`);
    vscode.window.showErrorMessage(`PD: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function openSpec(): Promise<void> {
  try {
    const root = workspaceRoot();
    if (!root) throw new Error("Open a PD workspace first.");
    const status = await readStatus();
    const uri = vscode.Uri.file(path.join(root, ".spec", status.feature, "SPEC.md"));
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document);
  } catch (error) {
    vscode.window.showErrorMessage(`PD: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBar.command = "pd.showStatus";
  output = vscode.window.createOutputChannel("PD");
  context.subscriptions.push(statusBar, output);
  context.subscriptions.push(vscode.commands.registerCommand("pd.showStatus", () => refresh(true)));
  context.subscriptions.push(vscode.commands.registerCommand("pd.validate", validate));
  context.subscriptions.push(vscode.commands.registerCommand("pd.openSpec", openSpec));
  void refresh(false);
}

export function deactivate(): void {}
```

**Step 2:** Compile:

```bash
cd extensions/vscode
npm run compile
```

**Expected:** exit 0; `out/extension.js` and `out/src/pd.js` exist.

---

## Task 4: Extension README

**Objective:** Document local run, settings, and the read-only boundary.

**Files:**
- Create: `extensions/vscode/README.md`
- Modify: `README.md` (root, one short section)

**Step 1:** Create `extensions/vscode/README.md`:

```markdown
# PD Companion (VS Code)

Read-only status and validation for a Project Development workspace.

## Run locally

```bash
cd extensions/vscode
npm install
npm run compile
code --extensionDevelopmentPath="$PWD" /path/to/pd-workspace
```

## Commands

- `PD: Show Status` — read `pd status --json`.
- `PD: Validate` — run `pd validate --json` and print it in the `PD` output channel.
- `PD: Open SPEC` — open `.spec/<feature>/SPEC.md`.

## Settings

- `pd.pythonPath` — Python executable (default `python3`).
- `pd.scriptPath` — path to `pd.py` relative to the workspace (default `scripts/pd.py`).

## Boundary

This extension never mutates `.spec`, never edits files, and never calls the
network. Mutating commands are intentionally out of scope for this slice.
```

**Step 2:** Add to root `README.md` before `## Fleet Orchestration Evolution`:

```markdown
## IDE companion (read-only)

The Phase 3 VS Code slice is specified in `docs/PHASE3-IDE-CONTRACT.md`. It reads
`pd status --json` and `pd validate --json`; it does not mutate state.
```

**Step 3:** Run the Markdown checker:

```bash
python3 scripts/check_markdown_links.py
```

**Expected:** `PASS`.

---

## Task 5: CI for the extension

**Objective:** Compile and test the extension on Node 22 without weakening the
Python matrix.

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1:** Add a job after `docs`:

```yaml
  vscode:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4

    - name: Set up Node
      uses: actions/setup-node@v4
      with:
        node-version: '22'
        cache: npm
        cache-dependency-path: extensions/vscode/package-lock.json

    - name: Install extension dependencies
      working-directory: extensions/vscode
      run: npm ci

    - name: Compile and test extension
      working-directory: extensions/vscode
      run: npm test
```

**Step 2:** Local equivalent:

```bash
cd extensions/vscode
npm ci
npm test
```

**Expected:** compile succeeds; `4` tests pass.

---

## Task 6: Roadmap and docs index

**Objective:** Mark the slice as planned without claiming it shipped.

**Files:**
- Modify: `ROADMAP.md`
- Modify: `docs/COMPOSITION-GUIDE.md` only if it has an IDE section; otherwise skip.

**Step 1:** Under `## Phase 3: Ecosystem — future`, add:

```markdown
### Slice 1 — read-only VS Code companion (planned)

- [ ] Extension scaffold, status bar, `PD: Show Status`, `PD: Validate`,
  `PD: Open SPEC`.
- Contract: `docs/PHASE3-IDE-CONTRACT.md`; plan:
  `docs/plans/2026-11-09-vscode-companion.md`.
- No state mutation, network, telemetry, or marketplace publication in this slice.
```

**Step 2:** Check docs:

```bash
python3 scripts/check_markdown_links.py
./scripts/release_preflight.sh
```

**Expected:** both PASS.

---

## Task 7: Final verification

**Objective:** Prove the extension and the Python project are green together.

**Step 1:** Run:

```bash
cd extensions/vscode
npm ci
npm test
cd /home/vitor/project/project-development-skill
/usr/bin/python3 -m pytest tests -q
uvx ruff check scripts tests
./scripts/release_preflight.sh
```

**Expected:** extension tests `4 passed`; Python `1479 passed, 1 skipped`; Ruff
`All checks passed!`; preflight `PASS`.

**Step 2:** Manual smoke test:

```bash
cd /home/vitor/project/project-development-skill
code --extensionDevelopmentPath="$PWD/extensions/vscode" "$PWD"
```

**Expected:** status bar shows the active PD feature; `PD: Validate` prints the
JSON result; `PD: Open SPEC` opens the SPEC. No file under `.spec` changes.

---

## Handoff

After Task 2, Hermes reviews the parser/test diff. After Task 3, Hermes runs a
manual extension-host smoke test; if the extension host is unavailable, record
that as `NOT VERIFIED` rather than claiming it passed. Independent review should
focus on command injection, workspace trust, and the read-only boundary.
