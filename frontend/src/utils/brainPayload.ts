import {
  getVersionDoc,
  getVersionMeta,
  getVersionPrompt,
  type PromptType,
  type RpEvalDetail,
  type VersionsListResponse,
} from '../api'
import type { RpEvalParsed } from './parseRpEvalJson'
import { isMultiCompareEval, parseRpEvalJson } from './parseRpEvalJson'

const PROMPT_EXCERPT_MAX = 12_000
const DOC_EXCERPT_MAX = 2000

function truncateText(text: string, max: number): { excerpt: string; truncated: boolean; total_length: number } {
  const total = text.length
  if (total <= max) {
    return { excerpt: text, truncated: false, total_length: total }
  }
  return {
    excerpt: `${text.slice(0, max)}\n\n…（已截断，全文 ${total} 字符）`,
    truncated: true,
    total_length: total,
  }
}

function summarizeEvalForBrain(evalResult: Record<string, unknown>) {
  const parsed = parseRpEvalJson(JSON.stringify(evalResult))
  if (!parsed.ok || !parsed.data) {
    return {
      parse_ok: false,
      raw_keys: Object.keys(evalResult),
    }
  }
  const d = parsed.data
  if (isMultiCompareEval(d)) {
    return {
      parse_ok: true,
      eval_mode: 'multi_compare' as const,
      overall_score: d.overall_score,
      overall_confidence: d.overall_confidence,
      summary: d.summary,
      recommendations: d.recommendations,
      model_scores: d.model_scores.map((m) => ({
        model: m.model,
        overall_score: m.overall_score,
        overall_confidence: m.overall_confidence,
        summary: m.summary,
      })),
      cross_model_comparison: d.cross_model_comparison,
    }
  }
  const weakDimensions = (mod: RpEvalParsed['segment_compress'], label: string) => {
    if (!mod.available) return []
    return mod.dimensions
      .filter((dim) => dim.score < 70 || dim.issues.length > 0)
      .map((dim) => ({
        module: label,
        id: dim.id,
        name: dim.name,
        score: dim.score,
        confidence: dim.confidence,
        evidence: dim.evidence,
        issues: dim.issues,
      }))
  }
  return {
    parse_ok: true,
    overall_score: d.overall_score,
    overall_confidence: d.overall_confidence,
    summary: d.summary,
    recommendations: d.recommendations,
    segment_compress: d.segment_compress,
    history_merge: d.history_merge,
    cross_consistency: d.cross_consistency,
    weak_dimensions: [
      ...weakDimensions(d.segment_compress, 'segment_compress'),
      ...weakDimensions(d.history_merge, 'history_merge'),
    ],
  }
}

async function loadModulePromptContext(version: string, promptType: PromptType) {
  const meta = await getVersionMeta(version)
  const prompt = await getVersionPrompt(version, promptType, 'zh', true)
  const { excerpt, truncated, total_length } = truncateText(prompt.content || '', PROMPT_EXCERPT_MAX)
  let changelog_excerpt = ''
  let changelog_truncated = false
  try {
    const doc = await getVersionDoc(version)
    const docTrunc = truncateText(doc.content || '', DOC_EXCERPT_MAX)
    changelog_excerpt = docTrunc.excerpt
    changelog_truncated = docTrunc.truncated
  } catch {
    changelog_excerpt = ''
  }
  return {
    evaluated_version: version,
    prompt_type: promptType,
    base_version: meta.base_version || (meta.is_baseline ? version : ''),
    is_baseline: meta.is_baseline,
    status: meta.status,
    prompt_excerpt: excerpt,
    prompt_truncated: truncated,
    prompt_total_length: total_length,
    changelog_excerpt,
    changelog_truncated,
  }
}

export interface BuildBrainPayloadInput {
  evalDetail: RpEvalDetail
  versionCatalog: VersionsListResponse
}

export async function buildBrainUserPayload(input: BuildBrainPayloadInput): Promise<string> {
  const { evalDetail, versionCatalog } = input
  const evalSummary = summarizeEvalForBrain(evalDetail.eval_result)

  const modules: Awaited<ReturnType<typeof loadModulePromptContext>>[] = []
  if (evalDetail.has_compress && evalDetail.compress_prompt_version) {
    modules.push(
      await loadModulePromptContext(evalDetail.compress_prompt_version, 'segment_compress'),
    )
  }
  if (evalDetail.has_merge && evalDetail.merge_prompt_version) {
    modules.push(
      await loadModulePromptContext(evalDetail.merge_prompt_version, 'history_merge'),
    )
  }

  const payload = {
    meta: {
      eval_id: evalDetail.id,
      role_name: evalDetail.role_name,
      round_start: evalDetail.round_start,
      round_end: evalDetail.round_end,
      compress_prompt_version: evalDetail.compress_prompt_version,
      merge_prompt_version: evalDetail.merge_prompt_version,
      eval_model: evalDetail.model,
    },
    eval_summary: evalSummary,
    modules,
    version_catalog: {
      baselines: versionCatalog.baselines,
      custom: versionCatalog.custom.map((v) => ({
        version: v.version,
        base_version: v.base_version,
        status: v.status,
      })),
      drafts: versionCatalog.drafts.map((v) => ({
        version: v.version,
        base_version: v.base_version,
      })),
    },
  }

  return JSON.stringify(payload, null, 2)
}
