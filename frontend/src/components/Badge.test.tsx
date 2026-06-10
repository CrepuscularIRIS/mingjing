/**
 * Badge component tests.
 *
 * These assertions enforce the redundant-encoding contract:
 *   1. Each tier renders its TEXT LABEL (no color-only communication).
 *   2. Each tier renders a DISTINCT SHAPE communicated via aria-label
 *      (so color-blind users and screen-reader users get the signal).
 *   3. The tiers are visually distinct from each other (different aria-labels).
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Badge } from './Badge';

describe('Badge', () => {
  describe('strong tier', () => {
    it('renders the "Strong" label text', () => {
      render(<Badge strength="strong" />);
      expect(screen.getByText('Strong')).toBeInTheDocument();
    });

    it('renders a shape icon with aria-label for strong evidence', () => {
      render(<Badge strength="strong" />);
      const icon = screen.getByRole('img', { name: /strong evidence/i });
      expect(icon).toBeInTheDocument();
    });

    it('applies the strong data attribute', () => {
      const { container } = render(<Badge strength="strong" />);
      expect(container.querySelector('[data-strength="strong"]')).toBeInTheDocument();
    });
  });

  describe('moderate tier', () => {
    it('renders the "Moderate" label text', () => {
      render(<Badge strength="moderate" />);
      expect(screen.getByText('Moderate')).toBeInTheDocument();
    });

    it('renders a shape icon with aria-label for moderate evidence', () => {
      render(<Badge strength="moderate" />);
      const icon = screen.getByRole('img', { name: /moderate evidence/i });
      expect(icon).toBeInTheDocument();
    });

    it('applies the moderate data attribute', () => {
      const { container } = render(<Badge strength="moderate" />);
      expect(container.querySelector('[data-strength="moderate"]')).toBeInTheDocument();
    });
  });

  describe('weak tier', () => {
    it('renders the "Weak" label text', () => {
      render(<Badge strength="weak" />);
      expect(screen.getByText('Weak')).toBeInTheDocument();
    });

    it('renders a shape icon with aria-label for weak evidence', () => {
      render(<Badge strength="weak" />);
      const icon = screen.getByRole('img', { name: /weak evidence/i });
      expect(icon).toBeInTheDocument();
    });

    it('applies the weak data attribute', () => {
      const { container } = render(<Badge strength="weak" />);
      expect(container.querySelector('[data-strength="weak"]')).toBeInTheDocument();
    });
  });

  describe('redundant encoding: tiers are distinct', () => {
    it('strong and moderate aria-labels are different', () => {
      const { container: cStrong } = render(<Badge strength="strong" />);
      const { container: cModerate } = render(<Badge strength="moderate" />);
      const strongLabel = cStrong.querySelector('[role="img"]')?.getAttribute('aria-label');
      const moderateLabel = cModerate.querySelector('[role="img"]')?.getAttribute('aria-label');
      expect(strongLabel).not.toEqual(moderateLabel);
    });

    it('moderate and weak aria-labels are different', () => {
      const { container: cModerate } = render(<Badge strength="moderate" />);
      const { container: cWeak } = render(<Badge strength="weak" />);
      const moderateLabel = cModerate.querySelector('[role="img"]')?.getAttribute('aria-label');
      const weakLabel = cWeak.querySelector('[role="img"]')?.getAttribute('aria-label');
      expect(moderateLabel).not.toEqual(weakLabel);
    });

    it('strong and weak aria-labels are different', () => {
      const { container: cStrong } = render(<Badge strength="strong" />);
      const { container: cWeak } = render(<Badge strength="weak" />);
      const strongLabel = cStrong.querySelector('[role="img"]')?.getAttribute('aria-label');
      const weakLabel = cWeak.querySelector('[role="img"]')?.getAttribute('aria-label');
      expect(strongLabel).not.toEqual(weakLabel);
    });

    /**
     * Shape regression guard: moderate must render 2 <path> elements (one filled
     * left semicircle + one stroke-only right semicircle), while strong renders
     * exactly 1 filled <path>. If the moderate icon regresses to a single filled
     * circle — which is visually identical to strong — this test catches it.
     */
    it('moderate SVG renders 2 path elements (half-filled shape), strong renders 1', () => {
      const { container: cStrong } = render(<Badge strength="strong" />);
      const { container: cModerate } = render(<Badge strength="moderate" />);

      const strongPaths = cStrong.querySelectorAll('[role="img"] path');
      const moderatePaths = cModerate.querySelectorAll('[role="img"] path');

      // Strong: single filled circle → 1 path
      expect(strongPaths).toHaveLength(1);
      // Moderate: filled left half + stroke-only right half → 2 paths
      expect(moderatePaths).toHaveLength(2);
    });

    it('moderate SVG has a stroke-only (fill-none) path, confirming the right half is outline', () => {
      const { container } = render(<Badge strength="moderate" />);
      const paths = Array.from(container.querySelectorAll('[role="img"] path'));
      // At least one path must carry a class that includes "fill-none" (the outline right half).
      const hasStrokeOnlyPath = paths.some((p) =>
        p.getAttribute('class')?.includes('fill-none'),
      );
      expect(hasStrokeOnlyPath).toBe(true);
    });
  });

  describe('optional admiralty grade (back-compat)', () => {
    it('does not render a secondary admiralty tag when the prop is absent', () => {
      render(<Badge strength="strong" />);
      // primary label unchanged
      expect(screen.getByText('Strong')).toBeInTheDocument();
      // no secondary admiralty tag
      expect(screen.queryByText('B2')).not.toBeInTheDocument();
      expect(screen.queryByText(/^[A-F][1-6]$/)).not.toBeInTheDocument();
    });

    it('renders the secondary "B2" tag while keeping the primary label unchanged', () => {
      render(<Badge strength="strong" admiralty="B2" />);
      // primary label unchanged
      expect(screen.getByText('Strong')).toBeInTheDocument();
      // secondary monospace tag
      expect(screen.getByText('B2')).toBeInTheDocument();
    });

    it('attaches a title/tooltip gloss on the admiralty tag', () => {
      render(<Badge strength="moderate" admiralty="B2" />);
      const tag = screen.getByText('B2');
      expect(tag.getAttribute('title')).toMatch(/来源可靠性/);
    });
  });

  describe('optional sourceCount', () => {
    it('shows source count when provided', () => {
      render(<Badge strength="strong" sourceCount={3} />);
      expect(screen.getByText('(3)')).toBeInTheDocument();
    });

    it('does not show count when not provided', () => {
      render(<Badge strength="weak" />);
      expect(screen.queryByText(/\(\d+\)/)).not.toBeInTheDocument();
    });
  });
});
