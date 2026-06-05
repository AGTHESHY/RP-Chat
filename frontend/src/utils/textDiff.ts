export type DiffLineType = 'unchanged' | 'added' | 'removed' | 'modified'
export type CharDiffType = 'unchanged' | 'added' | 'removed' | 'modified'

export interface DiffLine {
  type: DiffLineType
  oldText: string
  newText: string
}

export interface CharSegment {
  type: CharDiffType
  text: string
}

export interface DiffSideSegment {
  type: DiffLineType
  text: string
  /** modified 行内的字符级差异 */
  chars?: CharSegment[]
}

type LcsOp = 'match' | 'remove' | 'add'

function splitLines(text: string): string[] {
  if (!text) return []
  return text.split('\n')
}

function buildLcsOps<T>(oldItems: T[], newItems: T[], equals: (a: T, b: T) => boolean): LcsOp[] {
  const m = oldItems.length
  const n = newItems.length
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0))

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (equals(oldItems[i - 1], newItems[j - 1])) {
        dp[i][j] = dp[i - 1][j - 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1])
      }
    }
  }

  const ops: LcsOp[] = []
  let i = m
  let j = n
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && equals(oldItems[i - 1], newItems[j - 1])) {
      ops.push('match')
      i--
      j--
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push('add')
      j--
    } else {
      ops.push('remove')
      i--
    }
  }
  ops.reverse()
  return ops
}

function appendCharSegment(raw: CharSegment[], type: CharDiffType, text: string) {
  const last = raw[raw.length - 1]
  if (last?.type === type) {
    last.text += text
  } else {
    raw.push({ type, text })
  }
}

function pairCharRuns(raw: CharSegment[], side: 'old' | 'new'): CharSegment[] {
  const result: CharSegment[] = []
  let i = 0
  while (i < raw.length) {
    if (raw[i].type === 'removed') {
      const removedText = raw[i].text
      let j = i + 1
      while (j < raw.length && raw[j].type === 'removed') {
        // 已合并为单段，正常不会连续出现
        j++
      }
      let addedText = ''
      if (j < raw.length && raw[j].type === 'added') {
        addedText = raw[j].text
        j++
      }
      if (addedText) {
        result.push({
          type: 'modified',
          text: side === 'old' ? removedText : addedText,
        })
        i = j
        continue
      }
      if (side === 'old') result.push(raw[i])
      i++
      continue
    }
    if (raw[i].type === 'added') {
      if (side === 'new') result.push(raw[i])
      i++
      continue
    }
    result.push(raw[i])
    i++
  }
  return result
}

function computeCharDiff(oldText: string, newText: string, side: 'old' | 'new'): CharSegment[] {
  const oldChars = [...oldText]
  const newChars = [...newText]
  const ops = buildLcsOps(oldChars, newChars, (a, b) => a === b)
  const raw: CharSegment[] = []
  let oi = 0
  let ni = 0

  for (const op of ops) {
    if (op === 'match') {
      appendCharSegment(raw, 'unchanged', oldChars[oi])
      oi++
      ni++
    } else if (op === 'remove') {
      appendCharSegment(raw, 'removed', oldChars[oi])
      oi++
    } else {
      appendCharSegment(raw, 'added', newChars[ni])
      ni++
    }
  }

  return pairCharRuns(raw, side)
}

function opsToDiffLines(oldLines: string[], newLines: string[], ops: LcsOp[]): DiffLine[] {
  const raw: DiffLine[] = []
  let oi = 0
  let ni = 0

  for (const op of ops) {
    if (op === 'match') {
      raw.push({
        type: 'unchanged',
        oldText: oldLines[oi],
        newText: newLines[ni],
      })
      oi++
      ni++
    } else if (op === 'remove') {
      raw.push({
        type: 'removed',
        oldText: oldLines[oi],
        newText: '',
      })
      oi++
    } else {
      raw.push({
        type: 'added',
        oldText: '',
        newText: newLines[ni],
      })
      ni++
    }
  }

  return pairAdjacentChanges(raw)
}

function pairAdjacentChanges(lines: DiffLine[]): DiffLine[] {
  const result: DiffLine[] = []
  let i = 0
  while (i < lines.length) {
    if (lines[i].type === 'removed') {
      const removed: string[] = []
      let j = i
      while (j < lines.length && lines[j].type === 'removed') {
        removed.push(lines[j].oldText)
        j++
      }
      const added: string[] = []
      let k = j
      while (k < lines.length && lines[k].type === 'added') {
        added.push(lines[k].newText)
        k++
      }
      if (added.length > 0) {
        const pairs = Math.max(removed.length, added.length)
        for (let p = 0; p < pairs; p++) {
          const oldLine = removed[p] ?? ''
          const newLine = added[p] ?? ''
          if (oldLine && newLine) {
            result.push({ type: 'modified', oldText: oldLine, newText: newLine })
          } else if (oldLine) {
            result.push({ type: 'removed', oldText: oldLine, newText: '' })
          } else if (newLine) {
            result.push({ type: 'added', oldText: '', newText: newLine })
          }
        }
        i = k
        continue
      }
    }
    result.push(lines[i])
    i++
  }
  return result
}

export function computeLineDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = splitLines(oldText)
  const newLines = splitLines(newText)
  if (oldLines.length === 0 && newLines.length === 0) return []
  const ops = buildLcsOps(oldLines, newLines, (a, b) => a === b)
  return opsToDiffLines(oldLines, newLines, ops)
}

function lineToSegment(line: DiffLine, side: 'old' | 'new'): DiffSideSegment | null {
  if (line.type === 'unchanged') {
    return { type: 'unchanged', text: side === 'old' ? line.oldText : line.newText }
  }
  if (side === 'old') {
    if (line.type === 'removed') return { type: 'removed', text: line.oldText }
    if (line.type === 'modified') {
      return {
        type: 'modified',
        text: line.oldText,
        chars: computeCharDiff(line.oldText, line.newText, 'old'),
      }
    }
    return null
  }
  if (line.type === 'added') return { type: 'added', text: line.newText }
  if (line.type === 'modified') {
    return {
      type: 'modified',
      text: line.newText,
      chars: computeCharDiff(line.oldText, line.newText, 'new'),
    }
  }
  return null
}

export function toOldSideSegments(lines: DiffLine[]): DiffSideSegment[] {
  const segments: DiffSideSegment[] = []
  for (const line of lines) {
    const seg = lineToSegment(line, 'old')
    if (seg) segments.push(seg)
  }
  return segments
}

export function toNewSideSegments(lines: DiffLine[]): DiffSideSegment[] {
  const segments: DiffSideSegment[] = []
  for (const line of lines) {
    const seg = lineToSegment(line, 'new')
    if (seg) segments.push(seg)
  }
  return segments
}

export function hasDiffChanges(lines: DiffLine[]): boolean {
  return lines.some((line) => line.type !== 'unchanged')
}

export function textsHaveDiff(oldText: string, newText: string): boolean {
  return oldText !== newText
}
