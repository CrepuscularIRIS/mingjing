/**
 * CitedSentence tests — the shared cited-sentence renderer used across every
 * brief section (BLUF / 建议 / SWOT / 对比 / 缺口).
 *
 * Asserts: the sentence text renders; each claim_id renders a clickable
 * [cN] chip that calls onCite with the right id; chips for unresolvable ids
 * are disabled; an optional dual-axis ConfidenceChip renders when present.
 */

import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CitedSentence } from './CitedSentence';

afterEach(cleanup);

describe('CitedSentence', () => {
  it('renders the sentence text', () => {
    render(<CitedSentence sentence={{ text: 'Acme leads on price.', claim_ids: [] }} onCite={() => {}} />);
    expect(screen.getByText('Acme leads on price.')).toBeInTheDocument();
  });

  it('renders a clickable [cN] chip per claim id and calls onCite with the id', () => {
    const onCite = vi.fn();
    render(
      <CitedSentence
        sentence={{ text: 'Priced low.', claim_ids: ['c1', 'c2'] }}
        onCite={onCite}
      />,
    );
    fireEvent.click(screen.getByTestId('citation-chip-c2'));
    expect(onCite).toHaveBeenCalledWith('c2');
    expect(screen.getByText('[c1]')).toBeInTheDocument();
  });

  it('disables chips for unresolvable claim ids', () => {
    const onCite = vi.fn();
    render(
      <CitedSentence
        sentence={{ text: 'Ghost cite.', claim_ids: ['cX'] }}
        onCite={onCite}
        canCite={() => false}
      />,
    );
    const chip = screen.getByTestId('citation-chip-cX');
    expect(chip).toBeDisabled();
    fireEvent.click(chip);
    expect(onCite).not.toHaveBeenCalled();
  });

  it('renders the dual-axis ConfidenceChip when likelihood + band are present', () => {
    render(
      <CitedSentence
        sentence={{ text: 'Probable.', claim_ids: [], likelihood: '很可能', confidence_band: 'high' }}
        onCite={() => {}}
      />,
    );
    expect(screen.getByText('很可能')).toBeInTheDocument();
  });
});
