/**
 * Client tests for listRuns (GET /runs).
 * Stubs global fetch so no network is hit.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { listRuns } from './client';
import type { RunListResponse } from './types';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('listRuns', () => {
  it('GETs /runs with the given limit and returns the parsed list', async () => {
    const payload: RunListResponse = {
      runs: [
        {
          run_id: 'r1',
          category: 'CRM',
          competitors: ['Acme'],
          goal: 'g',
          status: 'complete',
          created_at: 1,
          passed_claims: 3,
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const res = await listRuns(8);

    expect(fetchMock).toHaveBeenCalledWith('/runs?limit=8', undefined);
    expect(res.runs[0].run_id).toBe('r1');
    expect(res.runs[0].passed_claims).toBe(3);
  });

  it('defaults the limit to 20', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ runs: [] }),
    } as Response);
    vi.stubGlobal('fetch', fetchMock);

    await listRuns();

    expect(fetchMock).toHaveBeenCalledWith('/runs?limit=20', undefined);
  });
});
