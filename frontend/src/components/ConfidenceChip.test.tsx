/**
 * ConfidenceChip component tests.
 *
 * Dual-axis confidence contract:
 *   1. Renders TWO visually distinct segments — the likelihood WORD
 *      (e.g. "很可能") and a coarse BAND indicator (high/moderate/low).
 *   2. BANDS ONLY — never a decimal/percentage. A "."-decimal must never render.
 *   3. The band indicator's class differs by band so high/moderate/low are
 *      visually distinguishable.
 */

import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, it, expect } from 'vitest';
import { ConfidenceChip } from './ConfidenceChip';

afterEach(() => {
  cleanup();
});

describe('ConfidenceChip', () => {
  it('renders the likelihood word segment', () => {
    render(<ConfidenceChip likelihood="很可能" band="high" />);
    expect(screen.getByText('很可能')).toBeInTheDocument();
  });

  it('renders a band indicator segment with the band data attribute', () => {
    const { container } = render(<ConfidenceChip likelihood="很可能" band="high" />);
    expect(container.querySelector('[data-band="high"]')).toBeInTheDocument();
  });

  it('renders both segments (likelihood + band) inside the chip', () => {
    const { container } = render(<ConfidenceChip likelihood="Likely" band="moderate" />);
    // likelihood word
    expect(screen.getByText('Likely')).toBeInTheDocument();
    // band indicator dot/pill is a separate element
    expect(container.querySelector('[data-band="moderate"]')).toBeInTheDocument();
  });

  it('renders no decimal/number-with-dot (bands only, never a numeric score)', () => {
    const { container } = render(<ConfidenceChip likelihood="很可能" band="high" />);
    expect(container.textContent ?? '').not.toMatch(/\d\.\d/);
    // also no bare decimal point at all in the rendered text
    expect(container.textContent ?? '').not.toContain('.');
  });

  it('uses a different band indicator class for high vs moderate vs low', () => {
    const { container: cHigh } = render(<ConfidenceChip likelihood="很可能" band="high" />);
    const { container: cMod } = render(<ConfidenceChip likelihood="可能" band="moderate" />);
    const { container: cLow } = render(<ConfidenceChip likelihood="不太可能" band="low" />);

    const high = cHigh.querySelector('[data-band="high"]')?.getAttribute('class');
    const mod = cMod.querySelector('[data-band="moderate"]')?.getAttribute('class');
    const low = cLow.querySelector('[data-band="low"]')?.getAttribute('class');

    expect(high).not.toEqual(mod);
    expect(mod).not.toEqual(low);
    expect(high).not.toEqual(low);
  });
});
