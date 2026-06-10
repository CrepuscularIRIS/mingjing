/** ClaimRow — explicit affirmative QA verdict stamp (audit item-2 fix). */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { Claim } from '../api/types';
import { ClaimRow } from './ClaimRow';

afterEach(cleanup);

function claim(over: Partial<Claim> = {}): Claim {
  return {
    id: 'c1',
    competitor: 'Acme',
    schema_field: 'pricing_model',
    claim_type: 'fact',
    statement: 'Pro tier costs $10/month.',
    value: {},
    evidence_strength: 'moderate',
    evidence_source_ids: ['s1', 's2'],
    status: 'pass',
    version: 4,
    ...over,
  } as Claim;
}

describe('ClaimRow QA verdict stamp', () => {
  it('renders an explicit 准入 stamp with the version for a revised claim', () => {
    render(<ClaimRow claim={claim({ version: 4 })} />);
    const stamp = screen.getByTestId('qa-verdict-stamp');
    expect(stamp).toHaveTextContent('QA✓ 准入 · v4');
    expect(stamp.title).toContain('经打回重审');
  });

  it('labels a first-round pass (version 1) as 首轮通过 in the tooltip', () => {
    render(<ClaimRow claim={claim({ version: 1 })} />);
    const stamp = screen.getByTestId('qa-verdict-stamp');
    expect(stamp).toHaveTextContent('QA✓ 准入 · v1');
    expect(stamp.title).toContain('首轮通过');
  });
});
