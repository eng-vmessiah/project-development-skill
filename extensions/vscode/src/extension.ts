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

function requireTrusted(): void {
  if (!vscode.workspace.isTrusted) {
    throw new Error("Trust this workspace before running PD.");
  }
}

async function readStatus(): Promise<PdStatus> {
  requireTrusted();
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
    requireTrusted();
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
    if (
      !status.feature ||
      status.feature === "." ||
      status.feature === ".." ||
      status.feature.includes("/") ||
      status.feature.includes("\\")
    ) {
      throw new Error("PD returned an unsafe feature name.");
    }
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
