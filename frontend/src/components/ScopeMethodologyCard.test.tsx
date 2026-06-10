/** ScopeMethodologyCard — 范围与方法 transparency section (M4). */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { ScopeMethodology } from '../api/types';
import { ScopeMethodologyCard } from './ScopeMethodologyCard';

afterEach(cleanup);

const SCOPE: ScopeMethodology = {
  mode: 'directed',
  competitors: [
    { name: 'Notion', reason: '由用户指定纳入分析' },
    { name: 'Linear', reason: '由用户指定纳入分析' },
  ],
  source_stats: {
    total: 33,
    by_source_mode: { SIMULATED: 5, CACHED: 28 },
    by_source_type: { survey: 4, interview: 1, web: 10, official: 15, review: 3 },
    independent_domains: 7,
  },
  admission: { proposed_claims: 10, admitted_claims: 6, withheld_claims: 4 },
  excluded: {
    withheld_count: 4,
    issue_codes: ['HALLUCINATED_SNIPPET', 'SCHEMA_GAP', 'VALUE_UNSUPPORTED'],
    uncovered_fields: ['swot'],
    disclosures: ['模拟问卷数据仅作展示, 不参与可信度分档'],
  },
  method: {
    rule_count: 6,
    statements: [
      '证据准入由确定性代码规则裁定 (共 6 类 QA 判定码), 全程无 LLM 参与真值裁定 (LLM 仅提议, 代码裁决)',
      '每条证据片段逐字核验: 必须是来源原文的子串, 否则拒绝 (verbatim-or-reject)',
    ],
  },
};

describe('ScopeMethodologyCard', () => {
  it('renders nothing when scope is absent (older API)', () => {
    const { container } = render(<ScopeMethodologyCard scope={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders scope, source stats, exclusions and method statements', () => {
    render(<ScopeMethodologyCard scope={SCOPE} />);
    expect(screen.getByTestId('scope-methodology')).toBeInTheDocument();
    // 纳入范围: mode label + both competitors with the inclusion reason.
    expect(screen.getByText('指定竞品模式')).toBeInTheDocument();
    expect(screen.getByText('Notion')).toBeInTheDocument();
    expect(screen.getByText('Linear')).toBeInTheDocument();
    // 数据源: totals + independent domains + admission funnel.
    const stats = screen.getByTestId('scope-source-stats');
    expect(stats.textContent).toContain('共 33 个来源');
    expect(stats.textContent).toContain('独立信源域 7 个');
    expect(stats.textContent).toContain('提议 10 条 → 准入 6 条');
    // 未纳入项: withheld count + issue codes + uncovered field + disclosure.
    const excluded = screen.getByTestId('scope-excluded');
    expect(excluded.textContent).toContain('4 条结论被确定性 QA 留存');
    expect(screen.getByText('HALLUCINATED_SNIPPET')).toBeInTheDocument();
    expect(excluded.textContent).toContain('证据不足，诚实留空');
    expect(excluded.textContent).toContain('模拟问卷数据仅作展示, 不参与可信度分档');
    // 方法 statements rendered verbatim.
    expect(screen.getByText(/verbatim-or-reject/)).toBeInTheDocument();
    // The section is labeled as deterministic, not LLM copy.
    expect(screen.getByText('确定性生成 · 非 LLM 文案')).toBeInTheDocument();
  });

  it('omits the 未纳入项 block when nothing was excluded', () => {
    render(
      <ScopeMethodologyCard
        scope={{
          ...SCOPE,
          excluded: { withheld_count: 0, issue_codes: [], uncovered_fields: [], disclosures: [] },
        }}
      />,
    );
    expect(screen.queryByTestId('scope-excluded')).not.toBeInTheDocument();
  });
});
