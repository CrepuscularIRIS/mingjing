/**
 * CorrectionControls unit tests.
 *
 * Covers:
 *   - 采纳 calls correctClaim({action:'accept'}) then onCorrected
 *   - 驳回 calls correctClaim({action:'reject'}) then onCorrected
 *   - edit flow: open form, edit statement/value, submit → correctClaim({action:'edit', ...})
 *   - malformed JSON in value blocks submit + shows inline error
 *   - disabled state when claim.id is missing/empty
 *   - inline error message on API failure (no crash)
 *   - "提交中…" shown while request is in-flight
 *   - note textarea renders (GA8)
 *   - note included in 采纳/驳回/edit payloads when entered (GA8)
 *   - note omitted from payload when blank (GA8)
 */

import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { Claim, ClaimCorrectionResponse } from '../api/types';
import { CorrectionControls } from './CorrectionControls';

vi.mock('../api/client');

const MOCK_VERSION: ClaimCorrectionResponse = {
  claim_id: 'c1',
  version: 3,
  status: 'pass',
  produced_by: 'human:correction',
};

const MOCK_CLAIM: Claim = {
  id: 'c1',
  competitor: 'Acme',
  statement: 'Acme starter plan costs $10/mo.',
  evidence_strength: 'strong',
  value: { amount: 10 },
  evidence_source_ids: ['s1', 's2'],
  version: 2,
};

const CLAIM_NO_ID: Claim = {
  competitor: 'Acme',
  statement: 'Some claim without id.',
  evidence_strength: 'weak',
  value: {},
  evidence_source_ids: [],
};

beforeEach(() => {
  vi.mocked(client.correctClaim).mockResolvedValue(MOCK_VERSION);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderControls(claim: Claim = MOCK_CLAIM, onCorrected = vi.fn()) {
  return { onCorrected, ...render(
    <CorrectionControls runId="run-1" claim={claim} onCorrected={onCorrected} />,
  )};
}

describe('CorrectionControls', () => {
  it('renders 采纳, 驳回, 编辑 buttons', () => {
    renderControls();
    expect(screen.getByRole('button', { name: '采纳' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '驳回' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '编辑' })).toBeInTheDocument();
  });

  it('clicking 采纳 calls correctClaim with {action:accept} and then onCorrected', async () => {
    const { onCorrected } = renderControls();

    fireEvent.click(screen.getByRole('button', { name: '采纳' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', { action: 'accept' });
    });
    await waitFor(() => {
      expect(onCorrected).toHaveBeenCalledTimes(1);
    });
  });

  it('clicking 驳回 calls correctClaim with {action:reject} and then onCorrected', async () => {
    const { onCorrected } = renderControls();

    fireEvent.click(screen.getByRole('button', { name: '驳回' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', { action: 'reject' });
    });
    await waitFor(() => {
      expect(onCorrected).toHaveBeenCalledTimes(1);
    });
  });

  it('edit flow: open form, change statement, submit → calls correctClaim with {action:edit, statement, value}', async () => {
    const { onCorrected } = renderControls();

    // Open the edit form
    fireEvent.click(screen.getByRole('button', { name: '编辑' }));

    // The textarea should be pre-filled with the claim's statement
    const statementArea = screen.getByLabelText(/说法/i) as HTMLTextAreaElement;
    expect(statementArea.value).toBe(MOCK_CLAIM.statement);

    // Edit the statement
    fireEvent.change(statementArea, { target: { value: 'Updated statement.' } });

    // The value textarea should be prefilled with JSON
    const valueArea = screen.getByLabelText(/value/i) as HTMLTextAreaElement;
    expect(valueArea.value).toContain('"amount"');

    // Submit
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', {
        action: 'edit',
        statement: 'Updated statement.',
        value: { amount: 10 },
      });
    });
    await waitFor(() => {
      expect(onCorrected).toHaveBeenCalledTimes(1);
    });
  });

  it('blocks submit and shows inline error when value JSON is malformed', async () => {
    renderControls();

    fireEvent.click(screen.getByRole('button', { name: '编辑' }));

    const valueArea = screen.getByLabelText(/value/i) as HTMLTextAreaElement;
    fireEvent.change(valueArea, { target: { value: '{ bad json' } });

    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    // Inline JSON error should appear
    expect(await screen.findByRole('alert')).toBeInTheDocument();

    // correctClaim should NOT have been called
    expect(client.correctClaim).not.toHaveBeenCalled();
  });

  it('also blocks submit when value is a JSON array (not an object)', async () => {
    renderControls();

    fireEvent.click(screen.getByRole('button', { name: '编辑' }));

    const valueArea = screen.getByLabelText(/value/i) as HTMLTextAreaElement;
    fireEvent.change(valueArea, { target: { value: '[1, 2, 3]' } });

    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(client.correctClaim).not.toHaveBeenCalled();
  });

  it('omits value from payload when value textarea is blank', async () => {
    const { onCorrected } = renderControls();

    fireEvent.click(screen.getByRole('button', { name: '编辑' }));

    // Clear the value field
    const valueArea = screen.getByLabelText(/value/i) as HTMLTextAreaElement;
    fireEvent.change(valueArea, { target: { value: '' } });

    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', {
        action: 'edit',
        statement: MOCK_CLAIM.statement,
      });
    });
    expect(onCorrected).toHaveBeenCalledTimes(1);
  });

  it('shows disabled hint and no action buttons when claim.id is missing', () => {
    renderControls(CLAIM_NO_ID);
    expect(screen.getByText(/此条暂无 id，无法修正/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '采纳' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '驳回' })).not.toBeInTheDocument();
  });

  it('shows an inline error message on API failure without crashing', async () => {
    vi.mocked(client.correctClaim).mockRejectedValueOnce(new Error('Network error'));

    renderControls();
    fireEvent.click(screen.getByRole('button', { name: '采纳' }));

    const errorMsg = await screen.findByRole('alert');
    expect(errorMsg).toHaveTextContent('Network error');
    // Component still renders (not crashed)
    expect(screen.getByRole('button', { name: '采纳' })).toBeInTheDocument();
  });

  it('shows 提交中… while a request is in flight and re-enables after', async () => {
    let resolveCorrect!: () => void;
    vi.mocked(client.correctClaim).mockReturnValue(
      new Promise<ClaimCorrectionResponse>((resolve) => {
        resolveCorrect = () => resolve(MOCK_VERSION);
      }),
    );

    renderControls();
    fireEvent.click(screen.getByRole('button', { name: '采纳' }));

    // Should show "提交中…" while pending
    expect(await screen.findAllByText('提交中…')).not.toHaveLength(0);

    // Resolve the promise
    resolveCorrect();

    // Buttons should return to normal text
    await waitFor(() => {
      expect(screen.queryByText('提交中…')).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// GA8: note input
// ---------------------------------------------------------------------------

describe('CorrectionControls — note input (GA8)', () => {
  it('renders the note textarea with the correct testid and placeholder', () => {
    renderControls();
    const noteArea = screen.getByTestId('correction-note-input') as HTMLTextAreaElement;
    expect(noteArea).toBeInTheDocument();
    expect(noteArea.placeholder).toMatch(/修正\/采信/);
  });

  it('包含 note 在 采纳 payload when note is entered', async () => {
    renderControls();

    const noteArea = screen.getByTestId('correction-note-input');
    fireEvent.change(noteArea, { target: { value: '第三方报告交叉验证，可信' } });

    fireEvent.click(screen.getByRole('button', { name: '采纳' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', {
        action: 'accept',
        note: '第三方报告交叉验证，可信',
      });
    });
  });

  it('包含 note 在 驳回 payload when note is entered', async () => {
    renderControls();

    const noteArea = screen.getByTestId('correction-note-input');
    fireEvent.change(noteArea, { target: { value: '数据已过期，来源失效' } });

    fireEvent.click(screen.getByRole('button', { name: '驳回' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', {
        action: 'reject',
        note: '数据已过期，来源失效',
      });
    });
  });

  it('包含 note 在 edit payload when note is entered', async () => {
    renderControls();

    // Enter a note
    const noteArea = screen.getByTestId('correction-note-input');
    fireEvent.change(noteArea, { target: { value: '手动更正定价' } });

    // Open edit form and submit
    fireEvent.click(screen.getByRole('button', { name: '编辑' }));
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith(
        'run-1',
        'c1',
        expect.objectContaining({ action: 'edit', note: '手动更正定价' }),
      );
    });
  });

  it('omits note from payload when note textarea is blank', async () => {
    renderControls();

    // Leave note empty
    fireEvent.click(screen.getByRole('button', { name: '采纳' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', { action: 'accept' });
    });
    // Verify no `note` key in the call
    const callArg = vi.mocked(client.correctClaim).mock.calls[0][2];
    expect(callArg).not.toHaveProperty('note');
  });

  it('omits note from payload when note is whitespace only', async () => {
    renderControls();

    const noteArea = screen.getByTestId('correction-note-input');
    fireEvent.change(noteArea, { target: { value: '   ' } });

    fireEvent.click(screen.getByRole('button', { name: '采纳' }));

    await waitFor(() => {
      expect(client.correctClaim).toHaveBeenCalledWith('run-1', 'c1', { action: 'accept' });
    });
    const callArg = vi.mocked(client.correctClaim).mock.calls[0][2];
    expect(callArg).not.toHaveProperty('note');
  });
});
