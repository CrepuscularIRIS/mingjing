/**
 * ShineBorder — a restrained animated shimmering border.
 *
 * Vendored & adapted from magicui (MIT): https://magicui.design/docs/components/shine-border
 * Adaptations: relative `cn` import; uses the project's `motion-safe:animate-shine`
 * keyframe (tailwind.config.js) so it is AUTOMATICALLY disabled under
 * prefers-reduced-motion (CSS-only, no JS). RESERVED for the credibility hero
 * (repair_delta / 真闭环确认) per the visual-direction guardrails — do not scatter it.
 *
 * Usage: place as a sibling inside a `relative` rounded container; it overlays an
 * animated gradient ring via mask-compositing without affecting layout.
 */

import * as React from 'react';

import { cn } from '../../lib/utils';

interface ShineBorderProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Border width in px. @default 1 */
  borderWidth?: number;
  /** Animation duration in seconds. @default 14 */
  duration?: number;
  /** Single color or gradient stops. @default brand mirror→strong */
  shineColor?: string | string[];
}

export function ShineBorder({
  borderWidth = 1,
  duration = 14,
  shineColor = ['#236a67', '#2e9e5a'],
  className,
  style,
  ...props
}: ShineBorderProps): React.ReactElement {
  return (
    <div
      style={
        {
          '--border-width': `${borderWidth}px`,
          '--duration': `${duration}s`,
          backgroundImage: `radial-gradient(transparent,transparent, ${
            Array.isArray(shineColor) ? shineColor.join(',') : shineColor
          },transparent,transparent)`,
          backgroundSize: '300% 300%',
          mask: `linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)`,
          WebkitMask: `linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)`,
          WebkitMaskComposite: 'xor',
          maskComposite: 'exclude',
          padding: 'var(--border-width)',
          ...style,
        } as React.CSSProperties
      }
      className={cn(
        'motion-safe:animate-shine pointer-events-none absolute inset-0 size-full rounded-[inherit] will-change-[background-position]',
        className,
      )}
      {...props}
    />
  );
}

export default ShineBorder;
