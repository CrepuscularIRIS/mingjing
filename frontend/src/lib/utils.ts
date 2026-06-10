/**
 * cn — className combiner used by all shadcn/ui + Magic UI primitives.
 *
 * clsx resolves conditionals/arrays; tailwind-merge dedupes conflicting
 * Tailwind utilities so later classes win (e.g. `px-2 px-4` → `px-4`).
 */
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
