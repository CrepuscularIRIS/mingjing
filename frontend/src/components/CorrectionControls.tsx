/**
 * CorrectionControls — Human-in-the-loop overrides for a selected claim.
 *
 * Three actions: 采纳 (accept), 驳回 (reject), 编辑 (edit).
 * Sits in the right panel, above or below the EvidenceDrawer.
 *
 * The optional `note` field lets the reviewer record a rationale for the
 * correction. It is included in the API payload for all three action types
 * and persisted by the backend on the resulting claim version.
 */

import { useState } from 'react';

import { correctClaim } from '../api/client';
import type { Claim } from '../api/types';

export interface CorrectionControlsProps {
  runId: string;
  claim: Claim;
  /** Called after a successful correction so the parent can refetch. */
  onCorrected: () => void;
}

export function CorrectionControls({
  runId,
  claim,
  onCorrected,
}: CorrectionControlsProps): React.ReactElement {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  // Correction note — optional human rationale; applies to all action types.
  const [note, setNote] = useState('');

  // Edit form state
  const [editedStatement, setEditedStatement] = useState(claim.statement);
  const [editedValueRaw, setEditedValueRaw] = useState(
    Object.keys(claim.value).length > 0 ? JSON.stringify(claim.value, null, 2) : '',
  );
  const [valueJsonError, setValueJsonError] = useState<string | null>(null);

  const noId = !claim.id;

  /** Spread note into the payload only when non-empty (matches backend optional field). */
  function notePayload(): { note?: string } {
    const trimmed = note.trim();
    return trimmed !== '' ? { note: trimmed } : {};
  }

  async function handleAccept(): Promise<void> {
    if (!claim.id) return;
    setSubmitting(true);
    setError(null);
    try {
      await correctClaim(runId, claim.id, { action: 'accept', ...notePayload() });
      onCorrected();
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReject(): Promise<void> {
    if (!claim.id) return;
    setSubmitting(true);
    setError(null);
    try {
      await correctClaim(runId, claim.id, { action: 'reject', ...notePayload() });
      onCorrected();
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEditSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!claim.id) return;

    // Validate JSON value if provided
    let parsedValue: Record<string, unknown> | undefined;
    if (editedValueRaw.trim() !== '') {
      try {
        const parsed = JSON.parse(editedValueRaw) as unknown;
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          setValueJsonError('Value 必须是 JSON 对象（如 {"key": "val"}）');
          return;
        }
        parsedValue = parsed as Record<string, unknown>;
        setValueJsonError(null);
      } catch {
        setValueJsonError('JSON 格式有误，请检查');
        return;
      }
    } else {
      setValueJsonError(null);
    }

    setSubmitting(true);
    setError(null);
    try {
      await correctClaim(runId, claim.id, {
        action: 'edit',
        statement: editedStatement,
        ...(parsedValue !== undefined ? { value: parsedValue } : {}),
        ...notePayload(),
      });
      setEditing(false);
      onCorrected();
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }

  if (noId) {
    return (
      <div className="px-4 py-3 border-b border-border text-xs text-ink-400">
        此条暂无 id，无法修正
      </div>
    );
  }

  return (
    <div className="px-4 py-3 border-b border-border space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-400">人工修正</p>

      {!editing && (
        <div className="flex items-center gap-2 flex-wrap">
          {/* Accept */}
          <button
            type="button"
            disabled={submitting}
            onClick={() => { void handleAccept(); }}
            className="px-3 py-1 rounded text-xs font-medium bg-primary text-primary-foreground hover:bg-mirror-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? '提交中…' : '采纳'}
          </button>

          {/* Reject */}
          <button
            type="button"
            disabled={submitting}
            onClick={() => { void handleReject(); }}
            className="px-3 py-1 rounded text-xs font-medium border border-border text-ink-700 hover:bg-ink-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? '提交中…' : '驳回'}
          </button>

          {/* Edit trigger */}
          <button
            type="button"
            disabled={submitting}
            onClick={() => {
              setEditedStatement(claim.statement);
              setEditedValueRaw(
                Object.keys(claim.value).length > 0
                  ? JSON.stringify(claim.value, null, 2)
                  : '',
              );
              setValueJsonError(null);
              setError(null);
              setEditing(true);
            }}
            className="px-3 py-1 rounded text-xs font-medium border border-border text-ink-700 hover:bg-ink-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            编辑
          </button>
        </div>
      )}

      {editing && (
        <form onSubmit={(e) => { void handleEditSubmit(e); }} className="space-y-2">
          <div>
            <label className="block text-xs text-ink-500 mb-1" htmlFor="edit-statement">
              说法 (statement)
            </label>
            <textarea
              id="edit-statement"
              rows={3}
              value={editedStatement}
              onChange={(e) => setEditedStatement(e.target.value)}
              className="w-full text-xs border border-input rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring resize-y"
            />
          </div>
          <div>
            <label className="block text-xs text-ink-500 mb-1" htmlFor="edit-value">
              Value（JSON，可选）
            </label>
            <textarea
              id="edit-value"
              rows={3}
              value={editedValueRaw}
              onChange={(e) => {
                setEditedValueRaw(e.target.value);
                setValueJsonError(null);
              }}
              className={[
                'w-full text-xs font-mono border rounded px-2 py-1.5 focus:outline-none focus:ring-1 resize-y',
                valueJsonError
                  ? 'border-destructive focus:ring-destructive'
                  : 'border-input focus:ring-ring',
              ].join(' ')}
              placeholder="{}"
            />
            {valueJsonError && (
              <p className="text-xs text-destructive mt-1" role="alert">
                {valueJsonError}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="px-3 py-1 rounded text-xs font-medium bg-primary text-primary-foreground hover:bg-mirror-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? '提交中…' : '保存'}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => { setEditing(false); setError(null); }}
              className="px-3 py-1 rounded text-xs font-medium border border-border text-ink-700 hover:bg-ink-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              取消
            </button>
          </div>
        </form>
      )}

      {/* Shared note textarea — always rendered (not inside either branch).
          Reviewer enters rationale here; included in API payload for any action. */}
      <div>
        <label className="block text-xs text-ink-500 mb-1" htmlFor="correction-note">
          修正说明（可选）
        </label>
        <textarea
          id="correction-note"
          data-testid="correction-note-input"
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="记录本次人工修正/采信的理由…"
          className="w-full text-xs border border-input rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring resize-y"
        />
      </div>

      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export default CorrectionControls;
