import type { PromptType } from '../api'

export interface ResultTreeNode {
  id: string
  label: string
  content?: string
  preview?: string
  children?: ResultTreeNode[]
}

const ROUND_HEADER_RE =
  /(?:^|\n)(?:#{1,3}\s*)?(?:Round\s+(\d+)\s*[-–—]\s*(\d+)|\[(\d+)\s*[-–—]\s*(\d+)\])\s*(?::|\n|$)/gi

function textPreview(text: string, max = 72): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  if (!flat) return ''
  return flat.length <= max ? flat : `${flat.slice(0, max)}…`
}

export function splitRoundSections(text: string): { label: string; content: string }[] {
  const trimmed = text.trim()
  if (!trimmed) return []

  const matches: { index: number; end: number; startRound: number; endRound: number }[] = []
  const re = new RegExp(ROUND_HEADER_RE.source, ROUND_HEADER_RE.flags)
  let match: RegExpExecArray | null
  while ((match = re.exec(trimmed)) !== null) {
    const startRound = Number(match[1] ?? match[3])
    const endRound = Number(match[2] ?? match[4])
    matches.push({
      index: match.index,
      end: match.index + match[0].length,
      startRound,
      endRound,
    })
  }

  if (!matches.length) {
    return [{ label: '全文', content: trimmed }]
  }

  const sections: { label: string; content: string }[] = []
  const preamble = trimmed.slice(0, matches[0].index).trim()
  if (preamble) {
    sections.push({ label: '前言', content: preamble })
  }

  for (let i = 0; i < matches.length; i += 1) {
    const current = matches[i]
    const next = matches[i + 1]
    const content = trimmed.slice(current.end, next ? next.index : trimmed.length).trim()
    sections.push({
      label: `${current.startRound}-${current.endRound}`,
      content,
    })
  }

  return sections
}

interface PipelineSegmentRow {
  start_round?: number
  end_round?: number
  history_segment?: string
}

function pipelineSegmentNodes(idPrefix: string, segments: PipelineSegmentRow[]): ResultTreeNode {
  return {
    id: `${idPrefix}-history_segment`,
    label: 'history_segment',
    children: segments.map((segment, index) => {
      const start = Number(segment.start_round)
      const end = Number(segment.end_round)
      const text = String(segment.history_segment ?? '')
      const label =
        Number.isFinite(start) && Number.isFinite(end) ? `Round ${start}-${end}` : `段 ${index + 1}`
      return {
        id: `${idPrefix}-history_segment-seg-${index}`,
        label,
        content: text,
        preview: textPreview(text),
      }
    }),
  }
}

function roundSectionNodes(idPrefix: string, key: string, text: string): ResultTreeNode {
  const sections = splitRoundSections(text)
  const hasRoundRanges = sections.length > 1 || sections[0]?.label !== '全文'

  if (!hasRoundRanges) {
    return {
      id: `${idPrefix}-${key}`,
      label: key,
      content: text,
      preview: textPreview(text),
    }
  }

  return {
    id: `${idPrefix}-${key}`,
    label: key,
    children: sections.map((section, index) => ({
      id: `${idPrefix}-${key}-round-${index}`,
      label: section.label === '前言' ? '前言' : `Round ${section.label}`,
      content: section.content,
      preview: textPreview(section.content),
    })),
  }
}

function valueToNode(idPrefix: string, key: string, value: unknown): ResultTreeNode {
  if (value === null || value === undefined) {
    return {
      id: `${idPrefix}-${key}`,
      label: key,
      content: String(value),
    }
  }

  if (typeof value === 'string') {
    if (key === 'history_segment' || key === 'history_memory') {
      return roundSectionNodes(idPrefix, key, value)
    }
    return {
      id: `${idPrefix}-${key}`,
      label: key,
      content: value,
      preview: textPreview(value),
    }
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return {
      id: `${idPrefix}-${key}`,
      label: key,
      content: String(value),
    }
  }

  if (Array.isArray(value)) {
    if (!value.length) {
      return {
        id: `${idPrefix}-${key}`,
        label: `${key} (空)`,
        content: '[]',
      }
    }

    return {
      id: `${idPrefix}-${key}`,
      label: `${key} (${value.length})`,
      children: value.map((item, index) => {
        if (item && typeof item === 'object' && !Array.isArray(item)) {
          const row = item as Record<string, unknown>
          const itemId = String(row.id ?? `#${index + 1}`)
          const status = row.status ? ` · ${String(row.status)}` : ''
          return {
            id: `${idPrefix}-${key}-${index}`,
            label: `${itemId}${status}`,
            children: Object.entries(row).map(([childKey, childValue]) =>
              valueToNode(`${idPrefix}-${key}-${index}`, childKey, childValue),
            ),
          }
        }
        return valueToNode(`${idPrefix}-${key}`, `#${index + 1}`, item)
      }),
    }
  }

  const entries = Object.entries(value as Record<string, unknown>)
  if (!entries.length) {
    return {
      id: `${idPrefix}-${key}`,
      label: `${key} (空)`,
      content: '{}',
    }
  }

  return {
    id: `${idPrefix}-${key}`,
    label: key,
    children: entries.map(([childKey, childValue]) => valueToNode(`${idPrefix}-${key}`, childKey, childValue)),
  }
}

function buildHistorySegmentNode(
  parsed: Record<string, unknown>,
  idPrefix: string,
  preferLatestOnly: boolean,
): ResultTreeNode | null {
  const pipelineSegments = parsed.pipeline_segments
  if (
    !preferLatestOnly
    && Array.isArray(pipelineSegments)
    && pipelineSegments.length > 0
  ) {
    return pipelineSegmentNodes(idPrefix, pipelineSegments as PipelineSegmentRow[])
  }
  if ('history_segment' in parsed) {
    return valueToNode(idPrefix, 'history_segment', parsed.history_segment)
  }
  return null
}

export function buildResultTree(
  parsed: Record<string, unknown>,
  promptType: PromptType,
): ResultTreeNode[] {
  if (promptType === 'segment_compress') {
    const nodes: ResultTreeNode[] = []
    const hasMergePreview = Boolean(parsed._merge_history_memory)

    if (hasMergePreview) {
      nodes.push(
        valueToNode('root', 'history_memory (合并)', parsed._merge_history_memory),
      )
    }

    const historySegmentNode = buildHistorySegmentNode(parsed, 'root', hasMergePreview)
    if (historySegmentNode) {
      nodes.push(historySegmentNode)
    }

    if ('memory_state' in parsed) {
      nodes.push(valueToNode('root', 'memory_state', parsed.memory_state))
    }
    return nodes.length ? nodes : Object.entries(parsed).map(([key, value]) => valueToNode('root', key, value))
  }

  if ('history_memory' in parsed) {
    return [valueToNode('root', 'history_memory', parsed.history_memory)]
  }

  return Object.entries(parsed).map(([key, value]) => valueToNode('root', key, value))
}
