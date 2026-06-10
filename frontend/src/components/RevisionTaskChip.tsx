/**
 * RevisionTaskChip — A small chip representing a single QA revision task.
 * STUB: shows task type label and status indicator; full data in next task.
 */

export type RevisionStatus = 'pending' | 'running' | 'done' | 'failed';

export interface RevisionTaskChipProps {
  taskType: string;
  status: RevisionStatus;
  label?: string;
}

const STATUS_STYLES: Record<RevisionStatus, string> = {
  pending: 'bg-ink-200 text-ink-500 border-ink-300',
  running: 'bg-mirror-50 text-mirror-700 border-mirror-600 animate-pulse',
  done: 'bg-[#e0f0e9] text-[#1a6638] border-[#2e9e5a]',
  failed: 'bg-orange-50 text-orange-700 border-orange-300',
};

export function RevisionTaskChip({
  taskType,
  status,
  label,
}: RevisionTaskChipProps): React.ReactElement {
  return (
    <span
      className={[
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium',
        STATUS_STYLES[status],
      ].join(' ')}
      title={`${taskType}: ${status}`}
    >
      <span>{label ?? taskType}</span>
      <span className="text-[10px] opacity-70">({status})</span>
    </span>
  );
}

export default RevisionTaskChip;
