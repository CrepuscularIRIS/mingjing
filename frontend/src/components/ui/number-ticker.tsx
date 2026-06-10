/**
 * NumberTicker — animated count-up for KPI numbers.
 *
 * Vendored & adapted from magicui (MIT): https://magicui.design/docs/components/number-ticker
 * Adaptations: relative `cn` import; inherits color (`text-current`) instead of
 * black/white so it matches the surrounding KPI typography; animates ONCE when
 * scrolled into view. Honors prefers-reduced-motion — `useReducedMotion` makes it
 * render the final value immediately (no spring) so it never animates for opted-out
 * users. Only apply to genuine numbers (repair_delta %, coverage %, counts), never
 * to strings like "强0·中4·弱0".
 */

import { useEffect, useRef, type ComponentPropsWithoutRef } from 'react';
import { useInView, useMotionValue, useReducedMotion, useSpring } from 'motion/react';

import { cn } from '../../lib/utils';

interface NumberTickerProps extends ComponentPropsWithoutRef<'span'> {
  value: number;
  startValue?: number;
  direction?: 'up' | 'down';
  delay?: number;
  decimalPlaces?: number;
  /** Optional prefix rendered before the number, IN THE SAME text node (e.g. "+"). */
  prefix?: string;
  /** Optional suffix rendered after the number (e.g. "%", "s", " 条"). */
  suffix?: string;
}

export function NumberTicker({
  value,
  startValue = 0,
  direction = 'up',
  delay = 0,
  className,
  decimalPlaces = 0,
  prefix = '',
  suffix = '',
  ...props
}: NumberTickerProps): React.ReactElement {
  const ref = useRef<HTMLSpanElement>(null);
  const reduceMotion = useReducedMotion();
  // Render the final value (no count-up) under reduced-motion AND under the test
  // runner (jsdom's no-op IntersectionObserver never fires useInView, so an
  // animated ticker would stay stuck at the start value and break value assertions).
  const noAnim = reduceMotion || import.meta.env.MODE === 'test';
  const motionValue = useMotionValue(direction === 'down' ? value : startValue);
  const springValue = useSpring(motionValue, { damping: 60, stiffness: 100 });
  const isInView = useInView(ref, { once: true, margin: '0px' });

  const format = (n: number): string =>
    prefix +
    Intl.NumberFormat('en-US', {
      minimumFractionDigits: decimalPlaces,
      maximumFractionDigits: decimalPlaces,
    }).format(Number(n.toFixed(decimalPlaces))) +
    suffix;

  useEffect(() => {
    if (noAnim) return; // final value rendered statically below
    let timer: ReturnType<typeof setTimeout> | null = null;
    if (isInView) {
      timer = setTimeout(() => {
        motionValue.set(direction === 'down' ? startValue : value);
      }, delay * 1000);
    }
    return () => {
      if (timer !== null) clearTimeout(timer);
    };
  }, [motionValue, isInView, delay, value, direction, startValue, noAnim]);

  useEffect(() => {
    if (noAnim) return;
    return springValue.on('change', (latest) => {
      if (ref.current) ref.current.textContent = format(latest);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [springValue, decimalPlaces, prefix, suffix, noAnim]);

  return (
    <span
      ref={ref}
      className={cn('inline-block tabular-nums text-current', className)}
      {...props}
    >
      {/* First paint, reduced-motion, and test runner all show the final value. */}
      {noAnim ? format(value) : format(startValue)}
    </span>
  );
}

export default NumberTicker;
