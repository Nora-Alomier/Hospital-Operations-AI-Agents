# Verification Results

Verified locally on 22 October 2026 from the repository root.

## Offline suite

Command:

```bash
.venv/bin/python -m pytest -q
```

Observed result:

```text
22 passed, 2 skipped
```

The skipped tests are intentionally marked `live_ollama`; every SQLite, RAG, tool, authorization, approval, audit, text-tool compatibility, false-success, and regression test ran.

## Live Ollama integration

Ollama was running locally and `llama3.2:latest` was installed. Command:

```bash
RUN_OLLAMA_TESTS=1 .venv/bin/python -m pytest -q -m live_ollama
```

Observed result:

```text
2 passed, 22 deselected
```

The live tests verify both normal Ollama tool use and a secure external-recipient email request that must reach a real backend `DENIED` result without creating an outbox record.

## Complete suite with live integration

Command:

```bash
RUN_OLLAMA_TESTS=1 .venv/bin/python -m pytest -q
```

Observed result:

```text
24 passed
```

## Deterministic security demonstration

Command:

```bash
.venv/bin/python demo_security.py --reset
```

Observed state:

- Plain unauthorized external email record created: `true`.
- Secure external-recipient record created: `false`.
- Secure authorized and approved internal record created: `true`.

Rerun these commands after future code changes to verify that the documented behavior still holds.
