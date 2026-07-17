# Fleet Status: `<plan-id>`

Visão humana do estado persistido da fleet. Atualize após cada transição,
gate ou checkpoint; não substitui o plano nem os relatórios dos agents.

## Overview

- **Plan:** `<plan-id>`
- **Schema version:** `1`
- **Last updated:** `<YYYY-MM-DDThh:mm:ssZ>`
- **Overall status:** `pending` | `running` | `blocked` | `failed` | `completed`
- **Owner/orchestrator:** `<agent-id>`

## Waves

| Wave | Status | Tasks | Gates | Notes |
|---|---|---|---|---|
| `<wave-id>` | `pending` | `<completed>/<total>` | `<gate-ids>` | `<notes>` |

## Tasks

| Task | Wave | Owner | Status | Depends on | Parallel group | Evidence |
|---|---:|---|---|---|---|---|
| `<task-id>` | `<wave>` | `<agent-id>` | `pending` | `<ids ou —>` | `<group ou —>` | `<report path ou —>` |

## Agents

| Agent | Role | Capabilities | Status | Current task | Last heartbeat |
|---|---|---|---|---|---|
| `<agent-id>` | `<role>` | `<capabilities>` | `available` | `<task-id ou —>` | `<timestamp>` |

## Gates

| Gate | Kind | Scope | Owner | Status | Decision | Evidence |
|---|---|---|---|---|---|---|
| `G1` | `review` | `plan` | `<owner>` | `pending` | `<pending/pass/fail>` | `<path ou —>` |

## Blockers and risks

- **Blockers:** `<none ou lista com task/gate afetado>`
- **Risks:** `<none ou lista com mitigação>`
- **Human decisions pending:** `<none ou decisão necessária>`

## Checkpoint / resume

- **Checkpoint:** `<path ou —>`
- **Resume from:** `<wave/task ou —>`
- **Last validated command:** `<comando ou —>`
