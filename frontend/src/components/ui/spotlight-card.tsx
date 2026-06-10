/**
 * SpotlightCard — a depth card with a soft pointer-following radial spotlight.
 *
 * Vendored & adapted from react-bits (MIT). Adaptations: light/brand surface
 * instead of the dark default (uses the project `depth-card` look via className);
 * mirror-teal spotlight by default; the spotlight is a CSS opacity transition
 * (GPU-cheap, and the prefers-reduced-motion reset collapses the transition).
 * Use for evidence/source cards — one layer of depth on hover, no continuous motion.
 */

import { useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';

import { cn } from '../../lib/utils';

interface SpotlightCardProps extends React.PropsWithChildren {
  className?: string;
  /** rgba spotlight tint. @default mirror-600 @ 0.10 */
  spotlightColor?: string;
  style?: React.CSSProperties;
}

export function SpotlightCard({
  children,
  className = '',
  spotlightColor = 'rgba(35, 106, 103, 0.10)',
  style,
}: SpotlightCardProps): React.ReactElement {
  const divRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [opacity, setOpacity] = useState(0);
  // Under prefers-reduced-motion we render a plain depth card with NO pointer
  // tracking and NO spotlight layer — not just a disabled transition.
  const reduceMotion = useReducedMotion();

  const onMove: React.MouseEventHandler<HTMLDivElement> = (e) => {
    const el = divRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  if (reduceMotion) {
    return (
      <div className={cn('relative overflow-hidden rounded-xl', className)} style={style}>
        {children}
      </div>
    );
  }

  return (
    <div
      ref={divRef}
      onMouseMove={onMove}
      onMouseEnter={() => setOpacity(1)}
      onMouseLeave={() => setOpacity(0)}
      className={cn('relative overflow-hidden rounded-xl', className)}
      style={style}
    >
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-500 ease-in-out"
        style={{
          opacity,
          background: `radial-gradient(220px circle at ${pos.x}px ${pos.y}px, ${spotlightColor}, transparent 70%)`,
        }}
      />
      {children}
    </div>
  );
}

export default SpotlightCard;
