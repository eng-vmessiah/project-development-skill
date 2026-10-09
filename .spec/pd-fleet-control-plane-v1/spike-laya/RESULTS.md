# Laya routing spike — RESULTS (T-203)

- **Run:** 2026-10-09T23:06:11+00:00 · backend `torch` · model `multilingual`
- **N events:** 21 (bus `~/.hermes/activity/events.jsonl`, fonte `hermes`)
- **Sink agreement vs baseline:** 3/21 (14%)
- **Notify agreement vs baseline (p>=0.5):** 15/21 (71%)
- **Latency:** {'min': 208.97, 'median': 261.72, 'max': 284.11}

## Caveats (não negociáveis)
- Laya é **zero-shot fraca** aqui (base de fine-tune) — concordância mede alinhamento com a regra atual, não verdade.
- Threshold 0.5 **não calibrado** — re-derivar por backend antes de qualquer uso com qualidade.
- **Zero wire:** nada roteia/persiste/notifica; isto é medição + dataset de calibração.

## Disagreements (sink)

- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5428)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5267)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5685)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5577)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.586)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5123)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5344)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.566)
- `hermes:cron` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5391)
- `hermes:cli` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.7047)
- `hermes:cli` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.6837)
- `hermes:cli` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.6531)
- `hermes:cli` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.5555)
- `hermes:cli` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.6623)
- `hermes:cli` status/done · baseline=`ledger` · laya=`stream_only` (conf 0.7109)

## Artefatos

- `decisions.jsonl` (1 linha por evento: baseline × laya × latência)
