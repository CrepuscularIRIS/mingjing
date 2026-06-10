/**
 * ActivityFeed — Vertical, color-coded list of trace events as human-readable
 * verbs. Each event is colored by its originating agent role (Collector /
 * Analyst / QA / Writer), and a heartbeat pulse at the top reassures the
 * viewer that the 2-second poll is alive even when no new event has arrived.
 */

import type { TraceEvent } from '../api/types';
import { describeEvent, roleStyle } from '../lib/trace';

export interface ActivityFeedProps {
  events: TraceEvent[];
  /** When true, show the heartbeat pulse (polling is active). */
  live?: boolean;
}

/**
 * `created_at` is a float epoch-seconds value (REAL column in SQLite).
 * Multiply by 1000 to get milliseconds for Date construction.
 */
function timeLabel(epochS: number): string {
  const d = new Date(epochS * 1000);
  const t = d.getTime();
  return Number.isNaN(t) ? '' : d.toLocaleTimeString();
}

/** Return an ISO-8601 string suitable for the `dateTime` attribute. */
function toDateTimeAttr(epochS: number): string {
  const d = new Date(epochS * 1000);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString();
}

/** A rendered feed row: the representative event plus how many consecutive
 *  identical events it stands for (1 = no duplicates). */
interface FeedRow {
  event: TraceEvent;
  count: number;
}

/**
 * Collapse runs of consecutive identical events into a single row carrying a
 * count. Bursty collectors can emit the same line ~20x in a second, which reads
 * like a stuck loop; a "×N" badge keeps the activity honestly represented
 * without the visual flood. Ordering and distinct events are preserved.
 */
function collapseConsecutive(events: TraceEvent[]): FeedRow[] {
  const rows: FeedRow[] = [];
  for (const ev of events) {
    const last = rows[rows.length - 1];
    // Same agent + same human-readable verb => a duplicate of the prior row.
    if (last && last.event.agent === ev.agent && describeEvent(last.event) === describeEvent(ev)) {
      last.count += 1;
    } else {
      rows.push({ event: ev, count: 1 });
    }
  }
  return rows;
}

export function ActivityFeed({ events, live = false }: ActivityFeedProps): React.ReactElement {
  return (
    <div>
      {live && (
        <div className="flex items-center gap-2 mb-3 text-xs text-ink-500" aria-label="Live">
          <span
            className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"
            data-testid="feed-heartbeat"
            aria-hidden="true"
          />
          Live · polling every 2s
        </div>
      )}

      {events.length === 0 ? (
        <div className="text-sm text-ink-400 py-4 text-center">Waiting for activity…</div>
      ) : (
        <ol className="relative border-l border-ink-200 space-y-3 pl-4" aria-label="Activity feed">
          {collapseConsecutive(events).map(({ event: ev, count }) => {
            const style = roleStyle(ev.agent);
            return (
              <li key={ev.id} className="relative">
                <span
                  aria-hidden="true"
                  className={['absolute -left-[1.15rem] top-1.5 w-2 h-2 rounded-full', style.dot].join(' ')}
                />
                <div className="flex items-start gap-2">
                  <p className={['text-sm font-medium leading-snug', style.text].join(' ')}>
                    {describeEvent(ev)}
                    {count > 1 && (
                      <span
                        data-testid="event-count"
                        className="ml-1.5 inline-block rounded-full bg-ink-200 px-1.5 py-0.5 text-[0.65rem] font-semibold leading-none text-ink-500 align-middle"
                      >
                        ×{count}
                      </span>
                    )}
                  </p>
                  <time
                    className="ml-auto text-xs text-ink-400 shrink-0"
                    dateTime={toDateTimeAttr(ev.created_at)}
                  >
                    {timeLabel(ev.created_at)}
                  </time>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

export default ActivityFeed;
