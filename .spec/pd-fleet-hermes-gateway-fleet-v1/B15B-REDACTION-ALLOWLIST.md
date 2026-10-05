# B15B — Redaction Allowlist/Denylist (pacote G-2)

**Status:** `draft_v0_2_for_approval` — G-2 (owner: security; papel acumulado no owner neste contexto solo). Nada embutido em runtime; o seam B15b.1 tem 0 call sites e não embute bounds pré-ativação. **Review:** v0.1 → `PASS_WITH_BLOCKERS` (6 achados — aplicados na v0.2); v0.2 → **`PASS`** (zero regressões; pronto para aprovação G-2).
**Data:** 2026-10-05 · **Autoria:** ISIS (orchestrator) · **Fonte:** `G4-SECURITY.md` (§5 · §8) · `G4-CLOSURE.md` (§4) · `G1-CONTRACT.md` (§4 · §5) · `B15B-SEAM-CONTRACT.md` v0.3 (§4 — bounds congelados).
**Evidência de fechamento (G4-SECURITY §8):** "denylist/allowlist tests with sensitive fixtures" — §4 abaixo.

## 1. Escopo e regra de ouro

- v1 é **allowlist-only** (metadata-only): só os campos abaixo atravessam. Redaction **ANTES** de buffer/persistência/translação/replay/audit/log/métrica/entrega (G4-SECURITY §5).
- Unknown field / unknown enum / oversized / malformado / versão não suportada ⇒ **fail-closed** (rejeitar; nunca repassar).

## 2. Allowlist

### 2.1 Envelope (G1 §4 — schema fechado)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | const | exatamente `pd-fleet-gateway-bridge:v1` |
| `event_id` | opaque ref | ≤128; charset de ref; único |
| `event_type` | closed enum | os 6 eventos de §2.2 |
| `occurred_at` | ISO-8601 UTC | **informativo — nunca ordering** |
| `source.system` | const | `hermes-gateway` |
| `source.instance_ref` | opaque ref | ≤128 |
| `event_origin` | closed enum | `gateway_native` \| `fleet_reconciled` (nunca republish derivado como nativo) |
| `session.session_ref` / `session.association_ref` | opaque ref | ≤128 |
| `session.ownership_mode` | closed enum | `user_owned_session` |
| `stream_epoch` | opaque ref | ≤128 |
| `sequence` | int | ≥0; contíguo por `(association, epoch)` |
| `payload` | objeto fechado por evento | ≤4KiB |
| `provenance.transport` | const | `gateway-event-stream` |
| `provenance.correlation_id` | opaque ref | ≤128 |

### 2.2 Payload por evento (G1 §5 — schema fechado por evento)

| Evento | Campos permitidos | Regras |
|---|---|---|
| `session.registered` | `runtime_surface`, `metadata_version` | enum* + int ≥0 |
| `session.status_changed` | `status`, `reason_code`, `metadata_version` | enums* + int |
| `session.heartbeat` | `heartbeat_sequence`, `observed_at`, `ttl_ms` | ints ≥0 + timestamp; **`ttl_ms` ≤300000 = novo candidato a aprovar** (rationale: liveness ≤5min — mesma escala do TTL de ativação candidato em G4-CLOSURE §2) |
| `session.metadata_changed` | `metadata_version`, `changed_fields` | int + **lista de enum fechado** (sem mapa/valores) |
| `session.detached` | `reason_code`, `metadata_version` | enum* + int |
| `session.ended` | `terminal_state`, `reason_code`, `metadata_version` | enums* + int |

\* **Enums candidatos a aprovar** (conjunto final congelado neste documento na aprovação): `runtime_surface` ∈ {`cli`, `gateway`, `api`, `tui`} · `status` ∈ {`active`, `idle`, `stale`, `ended`} · `reason_code` ∈ {`none`, `timeout`, `detached`, `error`, `closed`} · `terminal_state` ∈ {`ended`, `error`} · `changed_fields` ⊆ {`status`, `metadata_version`} (v1: `ownership_mode` é single-value — transição impossível, fora do conjunto).

## 3. Denylist (deny-by-default mesmo se a fonte contiver)

`prompt` · `history` · conteúdo de mensagem · `tool name/arguments/results` · resposta de provider/modelo · **conteúdo/payload de approval** · credenciais/tokens/keys/cookies · filesystem paths · terminal frames · **env vars** · endereços de rede além de refs opacos aprovados · mapas arbitrários/metadata livre · binário · arrays/strings/objetos aninhados além dos bounds congelados.

## 4. Fixtures nomeadas (evidência do G-2)

Convenção `redaction_<alvo>_<caso>`; execução: unit no **B15b.2** + buckets live no **B15b.5**.

- **Por campo permitido (passa íntegro):** `redaction_<evento>_<campo>_allowed` — ex.: `redaction_status_changed_status_allowed`, `redaction_heartbeat_ttl_ms_allowed`, `redaction_metadata_changed_changed_fields_allowed`.
- **Por categoria negada (fixtures sensíveis):** `redaction_deny_prompt`, `redaction_deny_history`, `redaction_deny_message_content`, `redaction_deny_tool_material` (name/arguments/results), `redaction_deny_provider_response`, `redaction_deny_approval_payload`, `redaction_deny_credentials`, `redaction_deny_paths`, `redaction_deny_terminal_frames`, `redaction_deny_env_vars`, `redaction_deny_network_address`.
- **Estruturais (fail-closed):** `redaction_unknown_field_fail_closed`, `redaction_unknown_enum_fail_closed`, `redaction_oversized_payload_rejected`, `redaction_arbitrary_map_rejected`, `redaction_binary_rejected`, `redaction_nested_beyond_depth_rejected`, `redaction_malformed_provenance_fail_closed`, `redaction_unsupported_schema_fail_closed` (espelha `version_unsupported` do seam).
- **Envelope:** `redaction_envelope_closed_fields` — cobre explicitamente os **15 campos-folha** do §2.1 (um por um); unknown/extra ⇒ reject.

## 5. Aprovação (gate G-2)

- [ ] **Security (owner acumulado):** aprovar §2 (allowlist + enums candidatos + bound candidato `ttl_ms`) · §3 (denylist) · §4 (fixtures).
- [ ] Review independente do pacote (dispatchado).
- Evidência final: este documento aprovado + fixtures executadas no B15b.2 (e re-verificadas nos buckets live no B15b.5).
