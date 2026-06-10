/**
 * ContradictionCard component tests.
 *
 * Evidence-conflict contract:
 *   1. Renders the "证据冲突" header.
 *   2. Renders TWO conflicting source chips side by side (each with a label,
 *      optional Admiralty grade).
 *   3. Renders an explicit "置信度由 {from} 降至 {to}" confidence delta.
 */

import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, it, expect } from 'vitest';
import { ContradictionCard } from './ContradictionCard';

afterEach(() => {
  cleanup();
});

describe('ContradictionCard', () => {
  it('renders the 证据冲突 header', () => {
    render(
      <ContradictionCard
        sourceA={{ label: '来源A' }}
        sourceB={{ label: '来源B' }}
        from="很可能"
        to="可能"
      />,
    );
    expect(screen.getByText(/证据冲突/)).toBeInTheDocument();
  });

  it('renders both source labels', () => {
    render(
      <ContradictionCard
        sourceA={{ label: 'TechCrunch' }}
        sourceB={{ label: 'CompanyBlog' }}
        from="很可能"
        to="可能"
      />,
    );
    expect(screen.getByText('TechCrunch')).toBeInTheDocument();
    expect(screen.getByText('CompanyBlog')).toBeInTheDocument();
  });

  it('renders the "降至" confidence delta with from and to', () => {
    render(
      <ContradictionCard
        sourceA={{ label: '来源A' }}
        sourceB={{ label: '来源B' }}
        from="很可能"
        to="可能"
      />,
    );
    const delta = screen.getByText(/降至/);
    expect(delta).toBeInTheDocument();
    expect(delta.textContent).toContain('很可能');
    expect(delta.textContent).toContain('可能');
  });

  it('renders the Admiralty grade on a source chip when provided', () => {
    render(
      <ContradictionCard
        sourceA={{ label: '来源A', grade: 'B2' }}
        sourceB={{ label: '来源B', grade: 'D4' }}
        from="很可能"
        to="可能"
      />,
    );
    expect(screen.getByText('B2')).toBeInTheDocument();
    expect(screen.getByText('D4')).toBeInTheDocument();
  });
});
