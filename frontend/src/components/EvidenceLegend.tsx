/**
 * EvidenceLegend — a persistent, static "how to read this" strip.
 *
 * The whole trust system (3-tier evidence strength + provenance modes) is
 * otherwise only decodable by hovering 6+ different chips. This strip makes it
 * self-explaining in <10s at a glance (NN/g progressive-disclosure: surface the
 * key, don't hide it behind hover). PURE display — no data, no backend, no
 * motion. Reuses the named strength/provenance tokens so colors stay consistent
 * with the chips they explain.
 */
import type { ReactElement } from 'react';

function Dot({ className }: { className: string }): ReactElement {
  return <span aria-hidden="true" className={['inline-block w-2 h-2 rounded-full', className].join(' ')} />;
}

export function EvidenceLegend(): ReactElement {
  return (
    <div
      data-testid="evidence-legend"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-500"
      title="证据强度判定规则 + 来源时效标记 —— 整套信任系统的图例"
    >
      <span className="font-medium text-ink-600">证据图例</span>
      <span className="inline-flex items-center gap-1">
        <Dot className="bg-strong-border" />强 = 2+ 独立来源含权威
      </span>
      <span className="inline-flex items-center gap-1">
        <Dot className="bg-moderate-border" />中 = 2+ 独立来源印证
      </span>
      <span className="inline-flex items-center gap-1">
        <Dot className="bg-weak-border" />弱 = 单一来源
      </span>
      <span className="text-ink-300">·</span>
      <span className="text-ink-500">LIVE 实时 / 快照 摘要 / 模拟 问卷·访谈（明确标注，不参与分档）</span>
    </div>
  );
}

export default EvidenceLegend;
