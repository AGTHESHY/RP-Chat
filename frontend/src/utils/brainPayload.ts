import {
  getVersionDoc,
  getVersionMeta,
  getVersionPrompt,
  type PromptType,
  type RpEvalDetail,
  type VersionsListResponse,
} from '../api'
import type { RpEvalModuleResult, RpEvalParsed } from './parseRpEvalJson'
import { isMultiCompareEval, parseRpEvalJson } from './parseRpEvalJson'
import { buildVersionContext, type BrainVersionContext } from './brainVersionContext'

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

function weakDimensionsFromModule(
  mod: RpEvalModuleResult,
  label: string,
  sourceModel?: string,
) {
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
      ...(sourceModel ? { source_model: sourceModel } : {}),
    }))
}

function buildEvalSnapshot(
  parsed: RpEvalParsed,
  promptType: PromptType,
): Record<string, unknown> {
  if (isMultiCompareEval(parsed)) {
    const perModel = parsed.model_scores.map((ms) => {
      const mod =
        promptType === 'segment_compress' ? ms.segment_compress : ms.history_merge
      return {
        model: ms.model,
        subscore: mod.subscore,
        confidence: mod.confidence,
        weak_dimensions: weakDimensionsFromModule(mod, promptType, ms.model),
      }
    })
    const available = perModel.filter((p) => p.weak_dimensions.length > 0 || p.subscore > 0)
    const avgSubscore =
      available.length > 0
        ? Math.round(available.reduce((s, p) => s + p.subscore, 0) / available.length)
        : 0
    const allWeak = perModel.flatMap((p) => p.weak_dimensions)
    return {
      mode: 'multi_compare',
      avg_subscore: avgSubscore,
      per_model: perModel,
      weak_dimensions: allWeak,
    }
  }

  const mod =
    promptType === 'segment_compress' ? parsed.segment_compress : parsed.history_merge
  return {
    mode: 'single',
    subscore: mod.subscore,
    confidence: mod.confidence,
    available: mod.available,
    weak_dimensions: weakDimensionsFromModule(mod, promptType),
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
        segment_compress: m.segment_compress,
        history_merge: m.history_merge,
        cross_consistency: m.cross_consistency,
        weak_dimensions: [
          ...weakDimensionsFromModule(m.segment_compress, 'segment_compress', m.model),
          ...weakDimensionsFromModule(m.history_merge, 'history_merge', m.model),
        ],
      })),
      cross_model_comparison: d.cross_model_comparison,
    }
  }

  return {
    parse_ok: true,
    eval_mode: 'single' as const,
    overall_score: d.overall_score,
    overall_confidence: d.overall_confidence,
    summary: d.summary,
    recommendations: d.recommendations,
    segment_compress: d.segment_compress,
    history_merge: d.history_merge,
    cross_consistency: d.cross_consistency,
    weak_dimensions: [
      ...weakDimensionsFromModule(d.segment_compress, 'segment_compress'),
      ...weakDimensionsFromModule(d.history_merge, 'history_merge'),
    ],
  }
}

async function loadModulePromptContext(
  version: string,
  promptType: PromptType,
  evalSnapshot: Record<string, unknown>,
) {
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
    eval_snapshot: evalSnapshot,
  }
}

export interface BuildBrainPayloadInput {
  evalDetail: RpEvalDetail
  versionCatalog: VersionsListResponse
}

export function hasMultiModelEvalDimensions(evalResult: Record<string, unknown>): boolean {
  const parsed = parseRpEvalJson(JSON.stringify(evalResult))
  if (!parsed.ok || !parsed.data || !isMultiCompareEval(parsed.data)) return true
  return parsed.data.model_scores.some(
    (m) =>
      m.segment_compress.dimensions.length > 0 || m.history_merge.dimensions.length > 0,
  )
}

export async function buildBrainUserPayload(input: BuildBrainPayloadInput): Promise<string> {
  const { evalDetail, versionCatalog } = input
  const parsedEval = parseRpEvalJson(JSON.stringify(evalDetail.eval_result))
  const evalSummary = summarizeEvalForBrain(evalDetail.eval_result)

  const evaluatedModels = Array.isArray(evalDetail.evaluated_models)
    ? evalDetail.evaluated_models
    : []
  const evalMode = evalDetail.eval_mode ?? (evaluatedModels.length > 1 ? 'multi_compare' : 'single')

  const versionContexts: BrainVersionContext[] = []
  const versionSet = new Set<string>()
  if (evalDetail.compress_prompt_version) versionSet.add(evalDetail.compress_prompt_version)
  if (evalDetail.merge_prompt_version) versionSet.add(evalDetail.merge_prompt_version)
  for (const v of versionSet) {
    versionContexts.push(await buildVersionContext(v, versionCatalog))
  }

  const modules: Awaited<ReturnType<typeof loadModulePromptContext>>[] = []
  if (evalDetail.has_compress && evalDetail.compress_prompt_version && parsedEval.ok && parsedEval.data) {
    modules.push(
      await loadModulePromptContext(
        evalDetail.compress_prompt_version,
        'segment_compress',
        buildEvalSnapshot(parsedEval.data, 'segment_compress'),
      ),
    )
  }
  if (evalDetail.has_merge && evalDetail.merge_prompt_version && parsedEval.ok && parsedEval.data) {
    modules.push(
      await loadModulePromptContext(
        evalDetail.merge_prompt_version,
        'history_merge',
        buildEvalSnapshot(parsedEval.data, 'history_merge'),
      ),
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
      eval_mode: evalMode,
      evaluated_models: evaluatedModels,
      judge_model: evalDetail.model,
    },
    eval_summary: evalSummary,
    modules,
    version_context: versionContexts,
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
