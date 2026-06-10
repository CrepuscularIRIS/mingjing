/**
 * Typed shapes for the MingJing Evidence API.
 * Field names are matched exactly to the Python API contract in mingjing/api.py.
 */

// ---------------------------------------------------------------------------
// POST /runs
// ---------------------------------------------------------------------------

export interface CreateRunBody {
  category: string;
  /**
   * Competitors to analyze. Provide a non-empty list for **Directed Mode**.
   * Leave empty for **Discovery Mode** — the backend runs a bounded discovery
   * pre-step from `category` (+ `market_scope` / `seed_competitors`).
   */
  competitors?: string[];
  goal: string;
  /** Optional analysis domain (validated server-side against available domains). */
  domain?: string;
  /** Discovery Mode: market scope hint — `"global"` / `"china"` / a free string. */
  market_scope?: string;
  /** Discovery Mode: max competitors to discover (server clamps to 1..6). */
  max_competitors?: number;
  /** Discovery Mode: names always included in the discovered set. */
  seed_competitors?: string[];
}

export interface CreateRunResponse {
  run_id: string;
}

// ---------------------------------------------------------------------------
// GET /runs  (recent-runs picker)
// ---------------------------------------------------------------------------

/**
 * One recent run, as returned by GET /runs. `passed_claims` is the count of
 * latest-version claims with status "pass" — used to pick a good corpus-driven
 * example run and to show a "✓ N 条已验证" badge in the 近期运行 list.
 */
export interface RunSummary {
  run_id: string;
  category: string | null;
  competitors: string[];
  goal: string | null;
  status: string | null;
  created_at: number | null;
  /** Analysis domain the run used (null when it used the default). */
  domain?: string | null;
  passed_claims: number;
}

export interface RunListResponse {
  runs: RunSummary[];
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/trace
// ---------------------------------------------------------------------------

/**
 * A single trace event emitted by the graph executor.
 * The `id` field is the monotonically increasing sequence number used
 * as the `since` cursor for incremental polling.
 *
 * NOTE: The backend serializes the raw DB row, so the payload arrives as a
 * JSON STRING in `payload_json` (not a parsed object), and `agent`/`node`
 * carry the originating graph role. `payload` remains optional for forward
 * compatibility / mocks that pre-parse it. Use `parseEventPayload` to read it.
 */
export interface TraceEvent {
  id: number;
  run_id: string;
  agent?: string | null;
  node?: string | null;
  event_type: string;
  payload_json?: string;
  payload?: Record<string, unknown>;
  /**
   * Float epoch seconds (REAL column in SQLite). Matches the backend's
   * `trace_events.created_at` column type — same as `LlmCall.created_at`.
   * Previously typed `string` in error; consumers that call `Number(...)` on
   * it already tolerate both forms, but the correct type is `number`.
   */
  created_at: number;
}

export interface TraceResponse {
  events: TraceEvent[];
  max_seq: number;
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/report
// ---------------------------------------------------------------------------

export type EvidenceStrength = 'strong' | 'moderate' | 'weak';

/**
 * Shallow Admiralty Code grade, e.g. "B2" — a single letter (source
 * reliability A–F) plus a single digit (information credibility 1–6).
 * Carried as a secondary signal alongside the primary `evidence_strength`;
 * the backend only attaches it when available, so it is always optional.
 */
export type AdmiraltyGrade = string;

/** Whether an evidence item supports, refutes, or is neutral toward a claim. */
export type EvidenceStance = 'supports' | 'refutes' | 'neutral';

/** One side of a source-vs-source conflict on a claim. */
export interface ContradictionSource {
  /** Registrable domain (e.g. "acme.com"). */
  label: string;
  /** Canonical URL for the source, if known. */
  url?: string;
  /** Optional Admiralty grade (e.g. "B2"). */
  grade?: string;
}

/**
 * A source-vs-source contradiction surfaced on a claim: two sources on distinct
 * domains disagree, and the conflict demoted confidence from `from` to `to`.
 * Present only when the backend detected such a conflict (else omitted).
 */
export interface Contradiction {
  source_a: ContradictionSource;
  source_b: ContradictionSource;
  /** Evidence-strength tier BEFORE the contradiction cap. */
  from: string;
  /** Evidence-strength tier AFTER the demotion. */
  to: string;
}

export interface Claim {
  id?: string;
  competitor?: string;
  statement: string;
  evidence_strength: EvidenceStrength;
  value: Record<string, unknown>;
  evidence_source_ids: string[];
  /**
   * Advisory per-source-type tally of this claim's cited sources, e.g.
   * `{ official: 2, news: 1 }`. Display-only (the matrix's source-type axis) —
   * never a verdict/tier signal; the scorer dedupes by registrable domain.
   */
  source_types?: Record<string, number>;
  version?: number;
  /** Secondary source-reliability/credibility grade (e.g. "B2"); optional. */
  admiralty?: AdmiraltyGrade;
  /** Stance of the supporting evidence toward this claim; optional. */
  stance?: EvidenceStance;
  /** Ids of the claims this (inference) claim was derived from; optional. */
  based_on?: string[];
  /** Source-vs-source conflict + confidence demotion; present only when detected. */
  contradiction?: Contradiction;
}

export interface ReportSection {
  schema_field: string;
  claims: Claim[];
}

export interface StrengthTally {
  strong: number;
  moderate: number;
  weak: number;
}

/**
 * Deterministic "范围与方法 (Scope & Methodology)" projection attached to the
 * report (M4): WHAT was analyzed, from WHICH sources, what was EXCLUDED and
 * why, and HOW conclusions are gated. Pure backend projection (scope.py) —
 * optional for older API responses.
 */
export interface ScopeMethodology {
  mode: 'directed' | 'discovery';
  competitors: { name: string; reason: string }[];
  source_stats: {
    total: number;
    by_source_mode: Record<string, number>;
    by_source_type: Record<string, number>;
    independent_domains: number;
  };
  admission: {
    proposed_claims: number;
    admitted_claims: number;
    withheld_claims: number;
  };
  excluded: {
    withheld_count: number;
    issue_codes: string[];
    uncovered_fields: string[];
    disclosures: string[];
  };
  method: {
    rule_count: number;
    statements: string[];
  };
}

export interface ReportResponse {
  sections: ReportSection[];
  strength_tally: StrengthTally;
  scope_methodology?: ScopeMethodology;
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/survey-design
// ---------------------------------------------------------------------------

export interface SurveyDesignQuestion {
  id: string;
  text: string;
  field: string | null;
  pii_scrub?: boolean;
}

export interface SurveyDesign {
  survey_id: string;
  competitor: string;
  goal: string;
  questions: SurveyDesignQuestion[];
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/claims/{claim_id}/history
// ---------------------------------------------------------------------------

/**
 * One persisted version of a claim. Revisions supersede by `version`, so the
 * history list shows how `evidence_strength` and `statement` evolved across
 * QA rounds — the data behind the QA Replay weak→strong upgrade.
 */
export interface ClaimVersion {
  id: string;
  competitor?: string | null;
  schema_field?: string | null;
  statement: string;
  evidence_strength: EvidenceStrength;
  status?: string | null;
  value: Record<string, unknown>;
  evidence_source_ids: string[];
  version: number;
  produced_by?: string | null;
  /** Reviewer rationale persisted on HITL correction versions; null for machine-produced versions. */
  note?: string | null;
}

export interface ClaimHistoryResponse {
  claim_id: string;
  versions: ClaimVersion[];
}

// ---------------------------------------------------------------------------
// GET /sources/{id}
// ---------------------------------------------------------------------------

// `SNIPPET` = a source whose stored raw_text is the search-result snippet only
// (no full-page fetch happened — robots-disallowed or fetch failed); the backend
// persists this mode (collector.py). It is an honest provenance qualifier, NOT an
// evidence-strength signal.
/** SIMULATED: fixture-seeded demo survey/interview rows — visible + groundable
 *  but excluded from all credibility computation (tier/corroboration). */
export type SourceMode = 'LIVE' | 'CACHED' | 'INGESTED' | 'SNIPPET' | 'SIMULATED';

export interface SourceProvenance {
  id: string;
  url: string;
  source_mode: SourceMode;
  source_type: string;
  // Epoch SECONDS when the source was fetched, or null (never fetched / snapshot).
  // The backend stores an integer epoch, not an ISO string (db.py get_source).
  fetched_at: number | null;
  raw_text: string;
  content_hash: string;
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/llm_calls
// ---------------------------------------------------------------------------

/**
 * One LLM call record as returned by GET /runs/{id}/llm_calls.
 *
 * Field names match the database columns exactly (see db.py llm_calls table).
 * `prompt_json` is the raw JSON string stored in the database (an array of
 * message objects). Secrets are redacted at write time by `trace.log_llm`.
 */
export interface LlmCall {
  id: number;
  agent: string | null;
  model: string | null;
  /** Raw JSON string — parse with JSON.parse to get the message list. */
  prompt_json: string;
  output_text: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  created_at: number;
}

export interface LlmCallsResponse {
  calls: LlmCall[];
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/metrics
// ---------------------------------------------------------------------------

export interface EfficiencyMetrics {
  elapsed_s: number;
  source_count: number;
  llm_calls: number;
  total_tokens: number;
  /**
   * Human-analyst baseline for ONE manual competitive-analysis pass — an
   * INDUSTRY ESTIMATE (16–40h), never a measured quantity. Optional for
   * backward compatibility with older API responses.
   */
  human_baseline_hours_low?: number;
  human_baseline_hours_high?: number;
  /**
   * Speedup ratio derived from the REAL `elapsed_s` vs the human estimate.
   * `null` when `elapsed_s` is 0 (no division). Optional + nullable so older
   * APIs and pre-elapsed runs degrade gracefully.
   */
  speedup_low?: number | null;
  speedup_high?: number | null;
}

export interface MetricsResponse {
  coverage: number;
  citation_rate: number;
  strong_rate: number;
  human_correction_rate: number;
  efficiency: EfficiencyMetrics;
  accuracy_caveat: string;
}

// ---------------------------------------------------------------------------
// POST /runs/{id}/claims/{cid}/correct
// ---------------------------------------------------------------------------

export interface ClaimCorrectionBody {
  action: 'accept' | 'reject' | 'edit';
  statement?: string;
  value?: Record<string, unknown>;
  note?: string;
}

/** Response from POST /runs/{id}/claims/{cid}/correct — the new superseding version's summary. */
export interface ClaimCorrectionResponse {
  claim_id: string;
  version: number;
  status: string;
  produced_by: string;
  /** Reviewer note echoed back by the /correct endpoint (present when the correction carried a note). */
  note?: string | null;
}

// ---------------------------------------------------------------------------
// GET /schemas  and  GET /schemas/{domain}
// ---------------------------------------------------------------------------

export interface FieldSchema {
  required: string[];
  sub_fields: string[];
}

export interface SchemasListResponse {
  domains: string[];
  active: string;
}

/**
 * ADVISORY source-type → Admiralty reliability-letter metadata for the legend.
 * `weights` = the domain's own map (may be empty); `fallback` = built-in defaults;
 * `unknown_letter` = letter for types in neither. Display-only — never affects
 * scoring (the 3-tier scorer is independent of Admiralty letters).
 */
export interface SourceWeightsView {
  weights: Record<string, string>;
  fallback: Record<string, string>;
  unknown_letter: string;
}

export interface DomainSchemaResponse {
  domain: string;
  fields: Record<string, FieldSchema>;
  /** Optional (additive; older responses omit it). */
  source_weights?: SourceWeightsView;
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/credibility
// ---------------------------------------------------------------------------

/**
 * Credibility KPI panel — quantified proof of the deterministic QA loop.
 *
 * `repair_delta` is the headline: groundedness improvement from round 1 to
 * the last round. Positive = real closed loop; negative = regression.
 * All rates are 0..1.
 */
export interface CredibilityResponse {
  avg_groundedness: number;
  claim_admission_rate: number;
  coverage: number;
  repair_delta: number;
  rounds: number;
  /**
   * Admission waterfall (advisory): proposed → admitted → withheld, over
   * distinct latest-version claims. Optional for backward compatibility with
   * older API responses. Makes "少而精" legible: a low admitted/proposed ratio
   * is the deterministic QA gate working, not a failure.
   */
  proposed_claims?: number;
  admitted_claims?: number;
  withheld_claims?: number;
  /**
   * Run terminal-state signal ('running' | 'partial' | 'complete' | 'error').
   * An in-flight run reports pre-final zeros; the zero-admitted honesty gate
   * only fires once the run has settled (run_status !== 'running'). Optional
   * for older API responses (absent ⇒ treated as settled).
   */
  run_status?: string | null;
  /** Coverage gaps (advisory): required-schema field NAMES only (never values). */
  covered_fields?: string[];
  uncovered_fields?: string[];
  /**
   * Honest weak→strong signal: True iff at least one claim's version history
   * shows a strict TIER increase (weak<moderate<strong). Distinct from
   * `repair_delta`, which is a groundedness scalar that can move within a
   * single tier. Optional for backward compatibility with older API responses.
   * (Frontend consumption is a later task; typed here only.)
   */
  is_tier_upgrade?: boolean;
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/withheld
// ---------------------------------------------------------------------------

/** One claim withheld from the report because the last QA round flagged it. */
export interface WithheldItem {
  claim_id: string;
  issue_codes: string[];
  round: number;
}

export interface WithheldResponse {
  withheld: WithheldItem[];
}

// ---------------------------------------------------------------------------
// GET /runs/{id}/synthesis
// ---------------------------------------------------------------------------

/** Dual-axis confidence: a likelihood word plus a coarse band (never a decimal). */
export type ConfidenceBand = 'high' | 'moderate' | 'low';

export interface ConfidenceLabel {
  likelihood: string;
  band: ConfidenceBand;
}

/**
 * One projected synthesis sentence. The backend guarantees `{text, claim_ids}`
 * for every factual sentence (it may cite ONLY ids of passed claims). Scaffold
 * sections (intelligence_gap / key_assumptions) may carry an empty `claim_ids`.
 * `likelihood`/`confidence_band` are optional, present only if the backend ever
 * attaches dual-axis confidence to a sentence.
 */
export interface SynthesisSentence {
  text: string;
  claim_ids: string[];
  likelihood?: string;
  confidence_band?: ConfidenceBand;
}

/**
 * GET /runs/{id}/synthesis  →  the latest projected synthesis payload.
 *
 * Synthesis is non-fatal: the endpoint returns `{}` when no synthesis row
 * exists yet, so every section is optional. `referenced_claim_ids` is always
 * present in a real (non-empty) payload — `project_synthesis` always sets it.
 */
export interface SynthesisResponse {
  bluf?: SynthesisSentence;
  swot?: {
    strengths: SynthesisSentence[];
    weaknesses: SynthesisSentence[];
    opportunities: SynthesisSentence[];
    threats: SynthesisSentence[];
  };
  comparison?: SynthesisSentence[];
  recommendations?: SynthesisSentence[];
  intelligence_gap?: SynthesisSentence[];
  key_assumptions?: SynthesisSentence[];
  referenced_claim_ids: string[];
}
