import { describe, expect, it } from 'vitest';

import type { ReportResponse, SynthesisResponse, WithheldItem } from '../api/types';
import { buildReportMarkdown } from './reportMarkdown';

const REPORT: ReportResponse = {
  sections: [
    {
      schema_field: 'pricing',
      claims: [
        {
          id: 'c1',
          competitor: 'Acme',
          statement: 'Acme starter plan costs $10/mo.',
          evidence_strength: 'strong',
          value: { amount: 10 },
          evidence_source_ids: ['s1'],
          version: 2,
        },
        {
          id: 'c2',
          competitor: 'Beta',
          statement: 'Beta lacks a free tier.',
          evidence_strength: 'weak',
          value: {},
          evidence_source_ids: ['s2'],
          version: 1,
        },
      ],
    },
  ],
  strength_tally: { strong: 1, moderate: 0, weak: 1 },
};

const SYNTHESIS: SynthesisResponse = {
  bluf: { text: 'Acme leads on price but trails on support.', claim_ids: ['c1'] },
  recommendations: [{ text: 'Undercut Acme support SLA.', claim_ids: ['c1'] }],
  swot: {
    strengths: [{ text: 'Acme has the lowest entry price.', claim_ids: ['c1'] }],
    weaknesses: [{ text: 'Beta has no free tier.', claim_ids: ['c2'] }],
    opportunities: [],
    threats: [],
  },
  comparison: [{ text: 'Acme $10/mo vs Beta paid-only.', claim_ids: ['c1', 'c2'] }],
  intelligence_gap: [],
  key_assumptions: [],
  referenced_claim_ids: ['c1', 'c2'],
};

const WITHHELD: WithheldItem[] = [
  { claim_id: 'wc1', issue_codes: ['VALUE_UNSUPPORTED', 'WEAK_EVIDENCE'], round: 2 },
];

describe('buildReportMarkdown', () => {
  it('serializes title, BLUF, recommendations, SWOT, comparison, claims and withheld', () => {
    const md = buildReportMarkdown({
      report: REPORT,
      synthesis: SYNTHESIS,
      withheld: WITHHELD,
      runId: 'run-42',
    });

    // Title + run id
    expect(md).toContain('# 明镜 · 竞品分析简报');
    expect(md).toContain('run-42');

    // BLUF
    expect(md).toContain('## 核心结论（BLUF）');
    expect(md).toContain('Acme leads on price but trails on support.');

    // Recommendations + SWOT + comparison
    expect(md).toContain('## 战略建议');
    expect(md).toContain('Undercut Acme support SLA.');
    expect(md).toContain('## SWOT 分析');
    expect(md).toContain('Acme has the lowest entry price.');
    expect(md).toContain('## 竞品对比');
    expect(md).toContain('Acme $10/mo vs Beta paid-only.');

    // 已验证结论 — each claim line with competitor · field · statement · strength
    expect(md).toContain('## 已验证结论（2 条）');
    expect(md).toContain('**Acme** · pricing · Acme starter plan costs $10/mo. · 证据强度: 强');
    expect(md).toContain('**Beta** · pricing · Beta lacks a free tier. · 证据强度: 弱');

    // WITHHELD section with claim_id + issue codes
    expect(md).toContain('## 未采纳（WITHHELD，1 条）');
    expect(md).toContain('`wc1`');
    expect(md).toContain('VALUE_UNSUPPORTED, WEAK_EVIDENCE');
  });

  it('always emits the WITHHELD section even when there is nothing withheld', () => {
    const md = buildReportMarkdown({
      report: REPORT,
      synthesis: SYNTHESIS,
      withheld: [],
      runId: 'run-43',
    });
    expect(md).toContain('## 未采纳（WITHHELD，0 条）');
    expect(md).toContain('本次运行无被质检打回的结论。');
  });

  it('does NOT claim "no withheld" before the withheld fetch has resolved (honesty)', () => {
    const md = buildReportMarkdown({
      report: REPORT,
      synthesis: SYNTHESIS,
      withheld: [],
      withheldLoaded: false,
      runId: 'run-43b',
    });
    // Must qualify, not assert a clean gate, and must not show a (possibly wrong) count.
    expect(md).toContain('质检披露数据尚未加载，未纳入本次导出。');
    expect(md).not.toContain('本次运行无被质检打回的结论。');
    expect(md).not.toContain('## 未采纳（WITHHELD，0 条）');
  });

  it('omits synthesis sections when synthesis is absent but still lists claims + withheld', () => {
    const md = buildReportMarkdown({
      report: REPORT,
      synthesis: null,
      withheld: WITHHELD,
      runId: 'run-44',
    });
    // No synthesis-driven sections.
    expect(md).not.toContain('## 核心结论（BLUF）');
    expect(md).not.toContain('## 战略建议');
    expect(md).not.toContain('## SWOT 分析');
    expect(md).not.toContain('## 竞品对比');
    // Claims + withheld are still serialized.
    expect(md).toContain('## 已验证结论（2 条）');
    expect(md).toContain('## 未采纳（WITHHELD，1 条）');
  });

  it('handles an empty report (no claims) without throwing', () => {
    const md = buildReportMarkdown({
      report: { sections: [], strength_tally: { strong: 0, moderate: 0, weak: 0 } },
      synthesis: null,
      withheld: [],
      runId: null,
    });
    expect(md).toContain('## 已验证结论（0 条）');
    expect(md).toContain('暂无通过质检的结论。');
    expect(md).toContain('未知'); // runId null → 未知
  });
});
