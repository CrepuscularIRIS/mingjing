/**
 * Typed API client for the MingJing Evidence API.
 * All functions return Promises with fully-typed shapes; no `any` in signatures.
 * In dev, the Vite proxy forwards /runs, /sources, /health to localhost:8000.
 */

import type {
  ClaimCorrectionBody,
  ClaimCorrectionResponse,
  ClaimHistoryResponse,
  CreateRunBody,
  CreateRunResponse,
  CredibilityResponse,
  DomainSchemaResponse,
  LlmCallsResponse,
  MetricsResponse,
  ReportResponse,
  RunListResponse,
  SchemasListResponse,
  SourceProvenance,
  SurveyDesign,
  SynthesisResponse,
  TraceResponse,
  WithheldResponse,
} from './types';

const BASE = '';  // relative — Vite proxy handles routing in dev; same origin in prod

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  // NOTE: This cast trusts that the server response shape matches T.
  // There is no runtime validation here — if the API contract changes,
  // callers may receive unexpected data without an immediate error.
  return res.json() as Promise<T>;
}

/**
 * Create a new analysis run.
 * POST /runs  →  { run_id }  (201)
 */
export async function createRun(body: CreateRunBody): Promise<CreateRunResponse> {
  return request<CreateRunResponse>('/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/**
 * List recent runs, newest-first.
 * GET /runs?limit=N  →  { runs: RunSummary[] }
 *
 * Powers the workbench "查看示例分析" one-click example and the 近期运行 list.
 */
export async function listRuns(limit: number = 20): Promise<RunListResponse> {
  return request<RunListResponse>(`/runs?limit=${limit}`);
}

/**
 * Fetch incremental trace events for a run.
 * GET /runs/{id}/trace?since=N  →  { events, max_seq }
 *
 * Pass `since = prevResponse.max_seq` on subsequent calls to receive
 * only new events (cursor-based incremental polling).
 */
export async function getTrace(
  runId: string,
  since: number = 0,
): Promise<TraceResponse> {
  return request<TraceResponse>(`/runs/${runId}/trace?since=${since}`);
}

/**
 * Fetch the final report for a completed run.
 * GET /runs/{id}/report  →  { sections, strength_tally }
 */
export async function getReport(runId: string): Promise<ReportResponse> {
  return request<ReportResponse>(`/runs/${runId}/report`);
}

/** GET /runs/{id}/survey-design → SurveyDesign | {} (empty when none). */
export async function getSurveyDesign(runId: string): Promise<Partial<SurveyDesign>> {
  return request<Partial<SurveyDesign>>(`/runs/${runId}/survey-design`);
}

/**
 * Fetch the full version history for a single claim, oldest-first.
 * GET /runs/{id}/claims/{claim_id}/history  →  { claim_id, versions }
 *
 * Powers the QA Replay before/after view (pass-1 weak vs pass-2 strong).
 */
export async function getClaimHistory(
  runId: string,
  claimId: string,
): Promise<ClaimHistoryResponse> {
  return request<ClaimHistoryResponse>(
    `/runs/${runId}/claims/${encodeURIComponent(claimId)}/history`,
  );
}

/**
 * Fetch source provenance and raw content.
 * GET /sources/{id}  →  SourceProvenance
 */
export async function getSource(sourceId: string): Promise<SourceProvenance> {
  return request<SourceProvenance>(`/sources/${sourceId}`);
}

/**
 * Fetch all LLM call records for a run.
 * GET /runs/{id}/llm_calls  →  { calls: [...] }
 *
 * Each call carries the prompt/messages (as a raw JSON string), the model
 * output text, and token usage figures. Secrets are redacted at write time
 * by the backend's trace.log_llm — the response is safe to display directly.
 */
export async function getLlmCalls(runId: string): Promise<LlmCallsResponse> {
  return request<LlmCallsResponse>(`/runs/${runId}/llm_calls`);
}

/**
 * Fetch business-metric KPIs for a completed (or in-progress) run.
 * GET /runs/{id}/metrics  →  MetricsResponse
 */
export async function getMetrics(runId: string): Promise<MetricsResponse> {
  return request<MetricsResponse>(`/runs/${runId}/metrics`);
}

/**
 * Submit a human correction for a claim (accept / reject / edit).
 * POST /runs/{id}/claims/{cid}/correct  →  201 {claim_id, version, status, produced_by}
 */
export async function correctClaim(
  runId: string,
  claimId: string,
  body: ClaimCorrectionBody,
): Promise<ClaimCorrectionResponse> {
  return request<ClaimCorrectionResponse>(
    `/runs/${runId}/claims/${encodeURIComponent(claimId)}/correct`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

/**
 * Fetch the projected synthesis (BLUF / SWOT / comparison / recommendations /
 * intelligence_gap / key_assumptions) for a run.
 * GET /runs/{id}/synthesis  →  SynthesisResponse | {} (when no synthesis yet)
 *
 * Synthesis is non-fatal: the endpoint returns an empty object when the run has
 * no synthesis row, and 404 when the run does not exist. Both cases resolve to
 * `null` here so callers can fall back to the deterministic claim ledger.
 */
export async function getSynthesis(runId: string): Promise<SynthesisResponse | null> {
  const res = await fetch(`${BASE}/runs/${runId}/synthesis`);
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  const data = (await res.json()) as Partial<SynthesisResponse>;
  // Empty {} (no bluf and no sections) → treat as absent so callers fall back.
  if (!data || !data.referenced_claim_ids) {
    return null;
  }
  return data as SynthesisResponse;
}

/**
 * Fetch the credibility KPI panel for a run.
 * GET /runs/{id}/credibility  →  CredibilityResponse
 *
 * `repair_delta` is the headline: positive = groundedness improved across QA
 * rounds (real closed loop). Fetched once when a run completes; not polled.
 */
export async function getCredibility(runId: string): Promise<CredibilityResponse> {
  return request<CredibilityResponse>(`/runs/${runId}/credibility`);
}

/**
 * Fetch the withheld-claims disclosure for a run (advisory, no LLM).
 * GET /runs/{id}/withheld  →  { withheld: [{claim_id, issue_codes, round}] }
 *
 * Powers the self-explaining empty/partial run state: claims that the last QA
 * round flagged correctly stay `draft` (absent from the report); this lists
 * exactly which were withheld and why.
 */
export async function getWithheld(runId: string): Promise<WithheldResponse> {
  return request<WithheldResponse>(`/runs/${runId}/withheld`);
}

/**
 * Fetch the list of available schema domains and the active default.
 * GET /schemas  →  { domains, active }
 */
export async function getSchemas(): Promise<SchemasListResponse> {
  return request<SchemasListResponse>('/schemas');
}

/**
 * Fetch the field definitions for a specific schema domain.
 * GET /schemas/{domain}  →  { domain, fields }
 */
export async function getSchemaDomain(domain: string): Promise<DomainSchemaResponse> {
  return request<DomainSchemaResponse>(`/schemas/${encodeURIComponent(domain)}`);
}
