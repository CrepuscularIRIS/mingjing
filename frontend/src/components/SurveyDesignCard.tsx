import type { SurveyDesign } from '../api/types';

/** 问卷设计 (Collector) — the deterministic questionnaire the collector designed.
 *  Renders nothing when no design (e.g. fetch returned {}). */
export function SurveyDesignCard({ design }: { design: Partial<SurveyDesign> }): React.ReactElement | null {
  const questions = design.questions ?? [];
  if (questions.length === 0) return null;
  return (
    <details className="rounded-lg border border-border bg-card shadow-card p-3" data-testid="survey-design-card" open>
      <summary className="text-sm font-semibold text-ink-700 cursor-pointer">
        📋 问卷设计 (Collector) · {design.survey_id} · {questions.length} 题
      </summary>
      <ul className="mt-2 space-y-1">
        {questions.map((q) => (
          <li key={q.id} className="text-xs text-ink-600 flex items-start gap-2">
            <span className="flex-1">{q.text}</span>
            {q.field && (
              <span className="text-[10px] font-medium text-mirror-700 bg-mirror-50 px-1.5 py-0.5 rounded">
                {q.field}
              </span>
            )}
            {q.pii_scrub && (
              <span className="text-[10px] text-amber-700">脱敏</span>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] text-amber-700">
        ⚠ 示例数据：以下问卷的回答为策展演示样本（标记为「模拟」），非真实投放调研。
        模拟回答可做字面值溯源，但不参与证据分档与佐证计数。
      </p>
    </details>
  );
}

export default SurveyDesignCard;
