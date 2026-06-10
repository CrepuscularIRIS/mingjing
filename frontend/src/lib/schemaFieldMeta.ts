/**
 * Display-only Chinese labels for competitive-knowledge `schema_field` keys.
 *
 * The backend (schema_registry, scoring, QA gate) keys every claim/section by a
 * raw snake_case field id (e.g. `pricing_model`). Those keys are the contract and
 * MUST NOT change. This map is a pure presentation layer: it translates a field
 * key into a human Chinese label for rendering only. It never affects scoring,
 * QA admission, or the data sent to the backend.
 *
 * Unknown keys fall back to the raw key unchanged (identity), so a new domain
 * field still renders without a code change — and never silently mislabels.
 */

const FIELD_LABELS: Record<string, string> = {
  // Default competitive-product domain (5 fields)
  pricing_model: '定价模型',
  feature_tree: '功能树',
  user_persona: '用户画像',
  user_sentiment: '用户口碑',
  swot: 'SWOT 分析',
  // AI-agent domain
  autonomy_level: '自主度等级',
  capability_matrix: '能力矩阵',
  integration_ecosystem: '集成生态',
  model_backbone: '模型底座',
  safety_guardrails: '安全护栏',
  // Enterprise-SaaS domain
  integration_matrix: '集成矩阵',
  compliance_certifications: '合规认证',
  deployment_model: '部署模式',
};

/**
 * Chinese display label for a `schema_field` key. Display-only — the raw key is
 * still what the backend/QA use. Unknown keys return unchanged (identity).
 */
export function getSchemaFieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}
