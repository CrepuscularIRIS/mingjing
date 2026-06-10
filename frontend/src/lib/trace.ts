/**
 * Trace-event helpers shared by the ActivityFeed and the two hero views.
 *
 * The backend serializes raw DB rows, so a trace event's payload arrives as a
 * JSON STRING in `payload_json`. These helpers parse it defensively and map
 * raw event/agent data onto human-readable, color-coded UI primitives.
 */

import type { TraceEvent } from '../api/types';

/**
 * Idempotently merge a freshly-polled batch of trace events into the accumulated
 * list, deduping by event `id`. The /trace poll is incremental (since-cursor),
 * but React StrictMode double-invokes the polling effect in dev and two in-flight
 * polls can race with the same cursor — either path can deliver the same events
 * twice. A blind `[...prev, ...incoming]` then produces duplicate keys, and React
 * duplicates/omits those children. Deduping here keeps every consumer of `events`
 * (ActivityFeed, FinalReport, ExecutionTrace, EvidenceAndQA) correct.
 *
 * Returns the SAME `prev` reference when nothing is fresh, so React can bail out
 * of a re-render.
 */
export function mergeTraceEvents(prev: TraceEvent[], incoming: TraceEvent[]): TraceEvent[] {
  if (incoming.length === 0) return prev;
  const seen = new Set(prev.map((e) => e.id));
  const fresh: TraceEvent[] = [];
  for (const e of incoming) {
    if (!seen.has(e.id)) {
      seen.add(e.id);
      fresh.push(e);
    }
  }
  return fresh.length === 0 ? prev : [...prev, ...fresh];
}

/** Parse a trace event's payload, tolerating the string/object/missing cases. */
export function parseEventPayload(event: TraceEvent): Record<string, unknown> {
  if (event.payload && typeof event.payload === 'object') return event.payload;
  if (typeof event.payload_json === 'string') {
    try {
      const parsed: unknown = JSON.parse(event.payload_json);
      if (parsed && typeof parsed === 'object') {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // Malformed payloads are non-fatal — fall through to empty.
    }
  }
  return {};
}

/**
 * Per-agent role color. Used to color-code the ActivityFeed so the four roles
 * are visually distinguishable as events stream in. Deliberately avoids
 * red-for-anything (consistent with the Badge redundant-encoding rationale).
 */
export interface RoleStyle {
  /** Tailwind text color class. */
  text: string;
  /** Tailwind background color class for the timeline dot. */
  dot: string;
  /** Human-readable role name. */
  label: string;
}

// Role text colors brightened to the -400 ramp so they read with AA contrast on
// the dark intelligence canvas (the -700 shades were too dark to read). Dots stay
// at -500 (bright enough as small accents).
const ROLE_STYLES: Record<string, RoleStyle> = {
  collector: { text: 'text-sky-400', dot: 'bg-sky-500', label: 'Collector' },
  analyst: { text: 'text-violet-400', dot: 'bg-violet-500', label: 'Analyst' },
  qa: { text: 'text-emerald-400', dot: 'bg-emerald-500', label: 'QA' },
  writer: { text: 'text-amber-400', dot: 'bg-amber-500', label: 'Writer' },
};

const DEFAULT_ROLE_STYLE: RoleStyle = {
  text: 'text-ink-600',
  dot: 'bg-ink-400',
  label: 'System',
};

export function roleStyle(agent: string | null | undefined): RoleStyle {
  if (!agent) return DEFAULT_ROLE_STYLE;
  return ROLE_STYLES[agent.toLowerCase()] ?? DEFAULT_ROLE_STYLE;
}

/** Turn an event_type token into a human-readable verb phrase. */
export function humanizeEventType(eventType: string): string {
  const map: Record<string, string> = {
    node_enter: 'started',
    claim_skipped: 'skipped a claim',
    source_skipped: 'skipped a thin source',
    discovery_started: 'started discovering competitors',
    competitors_discovered: 'discovered competitors',
    discovery_empty: 'found no competitors to analyze',
    collect_start: 'started collecting',
    collect_done: 'finished collecting',
    analyze_start: 'started analyzing',
    analyze_done: 'finished analyzing',
    qa_pass: 'passed QA',
    qa_fail: 'flagged weak evidence',
    revise_start: 'started a revision',
    revise_done: 'finished a revision',
    run_partial: 'ended partial',
    run_complete: 'completed',
    // `node_exit` and `qa_verdict` are reserved — not currently emitted by the
    // backend (the live vocabulary is node_enter + the collect/analyze/qa/
    // revise/run_* tokens above). Kept out of the map so they are not silently
    // mislabeled; an unknown token falls through to a humanized default below.
  };
  return map[eventType] ?? eventType.replace(/_/g, ' ');
}

/**
 * Compose a single human-readable line for a trace event, e.g.
 * "Collector started analyzing — Acme".
 */
export function describeEvent(event: TraceEvent): string {
  const style = roleStyle(event.agent);
  const verb = humanizeEventType(event.event_type);
  const payload = parseEventPayload(event);
  const detail =
    (payload['competitor'] as string | undefined) ??
    (payload['node'] as string | undefined) ??
    (payload['message'] as string | undefined) ??
    (event.node ?? undefined);
  const base = `${style.label} ${verb}`;
  return detail ? `${base} — ${detail}` : base;
}
