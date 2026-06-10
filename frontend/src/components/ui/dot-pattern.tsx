/**
 * DotPattern — a STATIC ambient dot-grid background.
 *
 * Adapted from magicui (MIT) but deliberately stripped to a pure SVG (no `motion`,
 * no per-dot animation): the visual direction allows an ambient dot-grid only at
 * LOW opacity in chrome gutters (sidebar/topbar), never behind dense text, and
 * forbids glow/particle motion. A tiling `<pattern>` keeps it cheap and infinite
 * without measuring the container. Color via `text-*` (currentColor); set opacity
 * with a className like `opacity-[0.06]`.
 */

import { useId } from 'react';

import { cn } from '../../lib/utils';

interface DotPatternProps extends React.SVGProps<SVGSVGElement> {
  /** Grid spacing in px. @default 16 */
  gap?: number;
  /** Dot radius in px. @default 1 */
  radius?: number;
}

export function DotPattern({
  gap = 18,
  radius = 1,
  className,
  ...props
}: DotPatternProps): React.ReactElement {
  const id = useId();
  return (
    <svg
      aria-hidden="true"
      className={cn('pointer-events-none absolute inset-0 h-full w-full text-ink-300', className)}
      {...props}
    >
      <defs>
        <pattern id={id} width={gap} height={gap} patternUnits="userSpaceOnUse" patternContentUnits="userSpaceOnUse">
          <circle cx={radius} cy={radius} r={radius} fill="currentColor" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}

export default DotPattern;
