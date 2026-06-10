# MingJing Observability

## Self-built tracing (always active — the live-demo main)

Every LLM call is logged to the `llm_calls` table via `trace.log_llm`, and
every graph step emits structured events to `trace_events`.  The Reactflow DAG
on tab ⑤ of the workbench renders these events in real time.  This path
requires no external service, works fully air-gapped, and is the primary
evidence layer shown to judges.

---

## Optional: LangSmith tracing (endorsement layer — unset by default)

`langsmith` 0.8.7 is installed as a dependency but **nothing is imported and no
overhead is incurred unless you set the env vars below**.  When set, each
`call_llm` call is wrapped with `langsmith.wrappers.wrap_openai`, which feeds
model name, token counts, and full message lists into LangSmith automatically —
producing a clean run tree useful as a screenshot for 答辩 materials.

### How to enable

Set the following environment variables (e.g. in `.env`):

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-key-from-smith.langchain.com>
LANGSMITH_PROJECT=mingjing
# Optional — only needed for the EU region:
# LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
```

The deprecated aliases `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, and
`LANGCHAIN_PROJECT` also work (the LangSmith SDK recognises them).

### What judges see in LangSmith

A run tree with one child span per `call_llm` invocation, showing:

- Model name (`MiniMax-M2.7` or configured variant)
- Token counts (prompt / completion / total)
- Full message list (system + user + assistant)
- Wall-clock latency per call

This is the **endorsement layer** — a third-party trace that corroborates
MingJing's own `trace_events` log.  The self-built DAG and evidence panel
remain the live-demo main and are always active regardless of this setting.

### Unset-by-default guarantee

When neither `LANGSMITH_TRACING` nor `LANGCHAIN_TRACING_V2` is set (or both
are set to a non-truthy value such as `false`/`0`):

- `tracing_enabled()` returns `False`
- `_maybe_wrap_openai` returns the original client object unchanged (`is`
  identity)
- **No `import langsmith` statement is ever executed** — the import is fully
  lazy and guarded inside `_maybe_wrap_openai`
- Behavior is byte-identical to a build without langsmith installed

This means the air-gapped / offline demo path is completely unaffected.

### Graceful degradation

If `langsmith` is somehow unavailable at runtime despite the env flag being
set, `_maybe_wrap_openai` logs a `WARNING` and returns the unwrapped client.
A run is never aborted due to a missing tracing library.

### Capturing the 答辩 screenshot

1. Set the env vars above and run a full analysis.
2. Open `https://smith.langchain.com` → project `mingjing`.
3. Click the latest run to see the per-call trace tree.
4. Screenshot the tree and include it in your 答辩 slide deck as evidence of
   structured agent tracing.
