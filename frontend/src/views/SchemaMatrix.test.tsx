/**
 * SchemaMatrix view integration tests.
 *
 * The API client is mocked — no real backend is hit. Covers:
 *  - column headers from domain field definitions
 *  - Badge cell rendered for a present (competitor, field) claim
 *  - gap-cell (缺口) rendered for a missing claim
 *  - both competitor rows visible
 *  - switching domain triggers getSchemaDomain and re-renders columns
 *  - no-run state: dropdown + columns render, getReport not called, "Start a run" message
 */

import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { DomainSchemaResponse, ReportResponse, SchemasListResponse } from '../api/types';
import { SchemaMatrix } from './SchemaMatrix';

vi.mock('../api/client');

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_SCHEMAS_LIST: SchemasListResponse = {
  domains: ['default', 'ai_agent', 'hr'],
  active: 'default',
};

const MOCK_DOMAIN_DEFAULT: DomainSchemaResponse = {
  domain: 'default',
  fields: {
    pricing_model: { required: ['price'], sub_fields: ['tier', 'currency'] },
    swot: { required: ['strengths'], sub_fields: ['weaknesses', 'opportunities'] },
    market_share: { required: ['pct'], sub_fields: [] },
  },
  source_weights: {
    weights: { official: 'A' },
    fallback: { official: 'B', news: 'C', web: 'D' },
    unknown_letter: 'F',
  },
};

const MOCK_DOMAIN_AI_AGENT: DomainSchemaResponse = {
  domain: 'ai_agent',
  fields: {
    model_capability: { required: ['benchmark'], sub_fields: [] },
    context_window: { required: ['tokens'], sub_fields: [] },
  },
  source_weights: { weights: {}, fallback: { official: 'B', web: 'D' }, unknown_letter: 'F' },
};

// Two competitors: CompA has pricing_model but NOT swot; CompB has swot but NOT pricing_model.
const MOCK_REPORT: ReportResponse = {
  sections: [
    {
      schema_field: 'pricing_model',
      claims: [
        {
          id: 'c1',
          competitor: 'CompA',
          statement: 'CompA charges $10/mo',
          evidence_strength: 'strong',
          value: {},
          evidence_source_ids: ['s1', 's2'],
          source_types: { official: 1, news: 1 },
          version: 1,
        },
      ],
    },
    {
      schema_field: 'swot',
      claims: [
        {
          id: 'c2',
          competitor: 'CompB',
          statement: 'CompB has a wide moat',
          evidence_strength: 'moderate',
          value: {},
          evidence_source_ids: ['s3'],
          version: 1,
        },
      ],
    },
  ],
  strength_tally: { strong: 1, moderate: 1, weak: 0 },
};

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(client.getSchemas).mockResolvedValue(MOCK_SCHEMAS_LIST);
  vi.mocked(client.getSchemaDomain).mockImplementation(async (domain) => {
    if (domain === 'ai_agent') return MOCK_DOMAIN_AI_AGENT;
    return MOCK_DOMAIN_DEFAULT;
  });
  vi.mocked(client.getReport).mockResolvedValue(MOCK_REPORT);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SchemaMatrix', () => {
  it('renders column headers from the default domain fields', async () => {
    render(<SchemaMatrix runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('col-header-pricing_model')).toBeInTheDocument();
      expect(screen.getByTestId('col-header-swot')).toBeInTheDocument();
      expect(screen.getByTestId('col-header-market_share')).toBeInTheDocument();
    });
  });

  it('renders a Badge cell for a present (competitor, field) claim', async () => {
    render(<SchemaMatrix runId="run-1" />);
    // Wait for columns and rows to load
    await waitFor(() => {
      expect(screen.getByTestId('col-header-pricing_model')).toBeInTheDocument();
    });
    await waitFor(() => {
      // CompA has a strong claim for pricing_model
      expect(screen.getAllByText(/Strong/i).length).toBeGreaterThan(0);
    });
  });

  it('renders the source-type breakdown axis for a cell that has source_types', async () => {
    render(<SchemaMatrix runId="run-1" />);
    // CompA / pricing_model has source_types {official:1, news:1}.
    expect(await screen.findByTestId('cell-srctypes-CompA-pricing_model')).toBeInTheDocument();
    expect(await screen.findByTestId('srctype-official')).toBeInTheDocument();
    expect(await screen.findByTestId('srctype-news')).toBeInTheDocument();
  });

  it('omits the breakdown for a cell whose claim has no source_types (back-compat)', async () => {
    render(<SchemaMatrix runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('col-header-pricing_model')).toBeInTheDocument();
    });
    // CompB / swot claim has no source_types → no breakdown container.
    expect(screen.queryByTestId('cell-srctypes-CompB-swot')).not.toBeInTheDocument();
  });

  it('renders the source_weights legend with the domain weight preferred over fallback', async () => {
    render(<SchemaMatrix runId="run-1" />);
    expect(await screen.findByTestId('source-weights-legend')).toBeInTheDocument();
    // default domain overrides official → 'A' (not the fallback 'B').
    expect(await screen.findByTestId('weight-official')).toHaveTextContent('A');
    expect(await screen.findByTestId('weight-news')).toHaveTextContent('C');
  });

  it('does not render the legend when source_weights is absent (back-compat)', async () => {
    vi.mocked(client.getSchemaDomain).mockResolvedValue({
      domain: 'default',
      fields: MOCK_DOMAIN_DEFAULT.fields,
    } as DomainSchemaResponse);
    render(<SchemaMatrix runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('col-header-pricing_model')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('source-weights-legend')).not.toBeInTheDocument();
  });

  it('renders gap-cell (缺口) for missing (competitor, field) combination', async () => {
    render(<SchemaMatrix runId="run-1" />);
    await waitFor(() => {
      // There should be at least one gap cell (e.g. CompA for swot, CompB for pricing_model)
      expect(screen.getAllByTestId('gap-cell').length).toBeGreaterThan(0);
    });
  });

  it('shows both competitor rows', async () => {
    render(<SchemaMatrix runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText('CompA')).toBeInTheDocument();
      expect(screen.getByText('CompB')).toBeInTheDocument();
    });
  });

  it('switching domain triggers getSchemaDomain and re-renders columns', async () => {
    render(<SchemaMatrix runId="run-1" />);

    // Wait for the domain select to appear
    const select = await screen.findByTestId('domain-select');

    // Change to ai_agent domain
    fireEvent.change(select, { target: { value: 'ai_agent' } });

    await waitFor(() => {
      expect(client.getSchemaDomain).toHaveBeenCalledWith('ai_agent');
    });

    await waitFor(() => {
      expect(screen.getByTestId('col-header-model_capability')).toBeInTheDocument();
      expect(screen.getByTestId('col-header-context_window')).toBeInTheDocument();
    });

    // Old default columns should be gone
    expect(screen.queryByTestId('col-header-pricing_model')).not.toBeInTheDocument();
    expect(screen.queryByTestId('col-header-swot')).not.toBeInTheDocument();
  });

  it('with runId=null: dropdown + columns render and no-run empty message shows, getReport not called', async () => {
    render(<SchemaMatrix runId={null} />);

    // Domain dropdown still renders
    const select = await screen.findByTestId('domain-select');
    expect(select).toBeInTheDocument();

    // Column headers still render from domain schema
    await waitFor(() => {
      expect(screen.getByTestId('col-header-pricing_model')).toBeInTheDocument();
    });

    // no-run empty message shows
    expect(screen.getByTestId('no-run-message')).toBeInTheDocument();
    expect(screen.getByTestId('no-run-message').textContent).toContain('发起一次运行后');

    // getReport must NOT have been called
    expect(client.getReport).not.toHaveBeenCalled();
  });

  it('shows skeleton when runId set but report has no competitors yet (no flicker)', async () => {
    vi.mocked(client.getReport).mockResolvedValue({
      sections: [],
      strength_tally: { strong: 0, moderate: 0, weak: 0 },
    });

    render(<SchemaMatrix runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('matrix-loading-skeleton')).toBeInTheDocument();
    });
    // Plain "等待分析结果…" text is gone — replaced by the pulse skeleton.
    expect(screen.queryByText('等待分析结果…')).not.toBeInTheDocument();
  });
});
