/**
 * IntelligenceGapPanel — empty-state copy gating.
 *
 * Regression guard: the pessimistic "暂无达到可信门槛的结论" copy must only appear
 * when there are genuinely ZERO verified claims. When the synthesis brief is absent
 * but the ledger has verified claims, the panel must instead point to the ledger —
 * never contradict it.
 */

import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { IntelligenceGapPanel } from './IntelligenceGapPanel';

afterEach(cleanup);

describe('IntelligenceGapPanel empty-state gating', () => {
  it('shows the pessimistic "no credible conclusions" copy only when zero claims', () => {
    render(<IntelligenceGapPanel emptyState admittedClaimCount={0} onCite={vi.fn()} />);
    expect(screen.getByTestId('no-passing-claims')).toBeInTheDocument();
    expect(screen.queryByTestId('synthesis-absent-note')).not.toBeInTheDocument();
  });

  it('points to the ledger (not "no conclusions") when claims exist but the brief is absent', () => {
    render(<IntelligenceGapPanel emptyState admittedClaimCount={4} onCite={vi.fn()} />);
    expect(screen.queryByTestId('no-passing-claims')).not.toBeInTheDocument();
    const note = screen.getByTestId('synthesis-absent-note');
    expect(note).toHaveTextContent(/综合简报暂未生成/);
    expect(note).toHaveTextContent(/4 条/);
  });

  it('renders neither empty-state copy when not in emptyState mode', () => {
    render(<IntelligenceGapPanel onCite={vi.fn()} />);
    expect(screen.queryByTestId('no-passing-claims')).not.toBeInTheDocument();
    expect(screen.queryByTestId('synthesis-absent-note')).not.toBeInTheDocument();
  });
});
