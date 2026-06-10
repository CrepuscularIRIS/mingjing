/**
 * ComparisonMatrix — deterministic competitor × field grid projected from the
 * QA-passed ledger. Renders only with >= 2 competitors; every populated cell is
 * click-to-cite and strength-coloured.
 */
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ReportSection } from '../api/types';
import { ComparisonMatrix } from './ComparisonMatrix';

afterEach(cleanup);

function sections(): ReportSection[] {
  return [
    {
      schema_field: 'pricing_model',
      claims: [
        { id: 'c1', competitor: 'Notion', statement: 'Notion pricing', evidence_strength: 'moderate', value: {}, evidence_source_ids: [] },
        { id: 'c2', competitor: 'Linear', statement: 'Linear pricing', evidence_strength: 'strong', value: {}, evidence_source_ids: [] },
      ],
    },
    {
      schema_field: 'user_sentiment',
      claims: [
        { id: 'c3', competitor: 'Notion', statement: 'Notion sentiment', evidence_strength: 'weak', value: {}, evidence_source_ids: [] },
        // Linear has no user_sentiment claim → empty cell.
      ],
    },
  ];
}

describe('ComparisonMatrix', () => {
  it('renders nothing with fewer than 2 competitors', () => {
    const single: ReportSection[] = [
      { schema_field: 'pricing_model', claims: [{ id: 'c1', competitor: 'Notion', statement: 's', evidence_strength: 'strong', value: {}, evidence_source_ids: [] }] },
    ];
    const { container } = render(<ComparisonMatrix sections={single} onCite={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a competitor × field grid with strength badges', () => {
    render(<ComparisonMatrix sections={sections()} onCite={() => {}} />);
    expect(screen.getByTestId('comparison-matrix')).toBeInTheDocument();
    expect(screen.getByText('Notion')).toBeInTheDocument();
    expect(screen.getByText('Linear')).toBeInTheDocument();
    // Linear/pricing is a strong cell.
    const cell = screen.getByTestId('matrix-cell-Linear-pricing_model');
    expect(cell.querySelector('[data-strength="strong"]')).not.toBeNull();
  });

  it('shows an empty marker where a competitor has no claim for a field', () => {
    render(<ComparisonMatrix sections={sections()} onCite={() => {}} />);
    // Linear has no user_sentiment claim → no cell button there.
    expect(screen.queryByTestId('matrix-cell-Linear-user_sentiment')).not.toBeInTheDocument();
  });

  it('cells are click-to-cite when citeable', () => {
    const onCite = vi.fn();
    render(<ComparisonMatrix sections={sections()} onCite={onCite} canCite={() => true} />);
    fireEvent.click(screen.getByTestId('matrix-cell-Notion-pricing_model'));
    expect(onCite).toHaveBeenCalledWith('c1');
  });

  it('renders ALL claims in a cell when a (competitor, field) has multiple (no silent hide)', () => {
    const multi: ReportSection[] = [
      {
        schema_field: 'pricing_model',
        claims: [
          { id: 'a1', competitor: 'Notion', statement: 'claim A', evidence_strength: 'strong', value: {}, evidence_source_ids: [] },
          { id: 'a2', competitor: 'Notion', statement: 'claim B', evidence_strength: 'weak', value: {}, evidence_source_ids: [] },
          { id: 'b1', competitor: 'Linear', statement: 'linear', evidence_strength: 'moderate', value: {}, evidence_source_ids: [] },
        ],
      },
    ];
    render(<ComparisonMatrix sections={multi} onCite={() => {}} canCite={() => true} />);
    // Both Notion/pricing claims render (base testid + -1 suffix).
    expect(screen.getByTestId('matrix-cell-Notion-pricing_model')).toBeInTheDocument();
    expect(screen.getByTestId('matrix-cell-Notion-pricing_model-1')).toBeInTheDocument();
  });
});
