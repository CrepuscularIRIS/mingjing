/**
 * Pure logic helpers for the ExecutionTrace DAG view.
 * Separated from the component file so fast-refresh lint is satisfied
 * (react-refresh/only-export-components fires when a file exports both
 * components and non-component values).
 */

import type { TraceEvent } from '../api/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type NodeId =
  | 'discover'
  | 'intake'
  | 'plan'
  | 'collect'
  | 'analyze'
  | 'qa'
  | 'route'
  | 'revise'
  | 'write'
  | 'synthesis';

/**
 * ``empty`` = a node that ran to completion but produced no real payload (today
 * only the synthesis node, when ``run_synthesis`` yielded no brief). It is a
 * neutral honest state — neither a green ``done`` (a brief WAS produced) nor a
 * red ``flagged`` (a QA rejection). Keeps the trace from a false positive.
 */
export type NodeStatus = 'pending' | 'running' | 'done' | 'flagged' | 'empty';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** All logical DAG node IDs in topology order. ``discover`` is the optional
 * Discovery-Mode pre-step (only entered when a run had no competitors); it stays
 * ``pending`` for Directed-Mode runs. */
export const ALL_NODE_IDS: NodeId[] = [
  'discover',
  'intake',
  'plan',
  'collect',
  'analyze',
  'qa',
  'route',
  'revise',
  'write',
  'synthesis',
];

// ---------------------------------------------------------------------------
// Status derivation
// ---------------------------------------------------------------------------

/**
 * Map a trace event's node string / event_type to the logical NodeId.
 * Returns null if the event doesn't clearly belong to one of our 9 nodes.
 */
function eventToNodeId(event: TraceEvent): NodeId | null {
  const et = event.event_type;
  const node = event.node ?? '';

  // Explicit event_type → node mappings (highest priority)
  if (et === 'discovery_started' || et === 'competitors_discovered' || et === 'discovery_empty')
    return 'discover';
  if (et === 'collect_start' || et === 'collect_done') return 'collect';
  if (et === 'analyze_start' || et === 'analyze_done') return 'analyze';
  if (et === 'qa_pass' || et === 'qa_fail') return 'qa';
  if (et === 'revise_start' || et === 'revise_done') return 'revise';
  if (et === 'run_complete' || et === 'run_partial') return 'write';
  if (et === 'synthesis_start' || et === 'synthesis_done' || et === 'synthesis_empty')
    return 'synthesis';

  // node string fallback
  if (node.includes('discover')) return 'discover';
  if (node.includes('collect')) return 'collect';
  if (node.includes('analyze')) return 'analyze';
  if (node.includes('qa')) return 'qa';
  if (node.includes('revise')) return 'revise';
  if (node.includes('synthesis')) return 'synthesis';
  if (node.includes('write')) return 'write';
  if (node.includes('plan')) return 'plan';
  if (node.includes('route')) return 'route';
  if (node.includes('intake')) return 'intake';

  // node_enter: derive from node name
  if (et === 'node_enter') {
    if (node.includes('intake')) return 'intake';
    if (node.includes('plan')) return 'plan';
    if (node.includes('route')) return 'route';
  }

  return null;
}

/**
 * Derive per-node status from the accumulated trace events.
 *
 * Rules:
 *   done    — node has a terminal event (collect_done/analyze_done/qa_pass/
 *             run_complete/run_partial for write; revise_done; synthesis_done)
 *   empty   — synthesis node ran but produced no brief (synthesis_empty)
 *   flagged — qa node when latest qa event is qa_fail
 *   running — node has a start/enter event but no terminal event yet
 *   pending — no events reference the node
 *
 * Note: intake/plan/route are waypoint nodes the backend only ever marks with
 * ``node_enter`` (no terminal token), so mid-run they show ``running`` until
 * the run settles. Once the run has SETTLED — a clean ``synthesis_done`` /
 * ``synthesis_empty``, or a hard ``run_error`` — nothing can still be running,
 * so lingering ``running`` nodes are demoted: → ``done`` on a clean settle
 * (the run advanced past them), → ``empty`` on a hard error (the node ran but
 * its payload is unproven). Prevents a finished run from showing a perpetual
 * "◎ running" node (judge-facing correctness).
 */
export function deriveNodeStatus(events: TraceEvent[]): Record<NodeId, NodeStatus> {
  const result: Record<NodeId, NodeStatus> = {
    discover: 'pending',
    intake: 'pending',
    plan: 'pending',
    collect: 'pending',
    analyze: 'pending',
    qa: 'pending',
    route: 'pending',
    revise: 'pending',
    write: 'pending',
    synthesis: 'pending',
  };

  let lastQaEvent: string | null = null;

  for (const event of events) {
    const et = event.event_type;
    const nodeId = eventToNodeId(event);
    if (nodeId === null) continue;

    if (nodeId === 'qa') {
      lastQaEvent = et;
    }

    // Terminal events → done
    if (
      et === 'collect_done' ||
      et === 'analyze_done' ||
      et === 'qa_pass' ||
      et === 'revise_done' ||
      et === 'run_complete' ||
      et === 'run_partial' ||
      et === 'synthesis_done' ||
      et === 'competitors_discovered' ||
      et === 'discovery_empty'
    ) {
      result[nodeId] = 'done';
      continue;
    }

    // synthesis_empty → empty (ran to completion but produced no brief).
    // Terminal + honest: distinct from a green ``done`` (a brief was produced).
    if (et === 'synthesis_empty') {
      result[nodeId] = 'empty';
      continue;
    }

    // Start/enter events → running (only if not already done)
    if (
      et === 'collect_start' ||
      et === 'analyze_start' ||
      et === 'revise_start' ||
      et === 'synthesis_start' ||
      et === 'discovery_started' ||
      et === 'node_enter'
    ) {
      if (result[nodeId] === 'pending') {
        result[nodeId] = 'running';
      }
      continue;
    }

    // qa_fail → flagged
    if (et === 'qa_fail') {
      result[nodeId] = 'flagged';
      continue;
    }
  }

  // Final qa override: if last qa event was qa_fail and it wasn't later overridden by qa_pass
  if (lastQaEvent === 'qa_fail') {
    result['qa'] = 'flagged';
  }

  // Settled-run demotion: after the run is genuinely over no node may keep a
  // live "running" state. run_partial/run_complete are NOT settle signals here
  // (synthesis still runs after them); synthesis_done/synthesis_empty and
  // run_error are.
  const settledClean = events.some(
    (e) => e.event_type === 'synthesis_done' || e.event_type === 'synthesis_empty',
  );
  const settledError = !settledClean && events.some((e) => e.event_type === 'run_error');
  if (settledClean || settledError) {
    for (const id of ALL_NODE_IDS) {
      if (result[id] === 'running') {
        result[id] = settledClean ? 'done' : 'empty';
      }
    }
  }

  return result;
}
