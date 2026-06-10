/**
 * SourceTypeBreakdown — advisory per-cell source-type axis. Renders ordered chips
 * (authoritative first), nothing for empty/absent counts.
 */
import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { SourceTypeBreakdown } from './SourceTypeBreakdown';

afterEach(cleanup);

describe('SourceTypeBreakdown', () => {
  it('renders nothing for empty / absent counts', () => {
    const { container: a } = render(<SourceTypeBreakdown counts={undefined} />);
    expect(a.firstChild).toBeNull();
    const { container: b } = render(<SourceTypeBreakdown counts={{}} />);
    expect(b.firstChild).toBeNull();
  });

  it('renders chips with counts', () => {
    render(<SourceTypeBreakdown counts={{ official: 2, news: 1 }} competitor="X" field="pricing_model" />);
    expect(screen.getByTestId('cell-srctypes-X-pricing_model')).toBeInTheDocument();
    expect(screen.getByTestId('srctype-official')).toHaveTextContent('官方·2');
    expect(screen.getByTestId('srctype-news')).toHaveTextContent('新闻·1');
  });

  it('orders authoritative types before non-authoritative', () => {
    render(<SourceTypeBreakdown counts={{ news: 1, official: 1, interview: 1 }} competitor="X" field="f" />);
    const chips = screen.getAllByTestId(/^srctype-/);
    const order = chips.map((c) => c.getAttribute('data-testid'));
    // official + interview (authoritative) precede news.
    expect(order.indexOf('srctype-official')).toBeLessThan(order.indexOf('srctype-news'));
    expect(order.indexOf('srctype-interview')).toBeLessThan(order.indexOf('srctype-news'));
  });
});
