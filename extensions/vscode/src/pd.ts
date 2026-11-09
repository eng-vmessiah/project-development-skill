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
