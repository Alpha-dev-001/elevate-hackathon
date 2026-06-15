/**
 * Minimal CSV parser for the product drop. Expected columns (header row,
 * any order): name, price, stock, image_url, category. Rows missing a name
 * or a numeric price/stock are skipped rather than failing the whole import.
 */
import type { ProductCSVRowInput } from '@/lib/api'

function splitLine(line: string): string[] {
  const out: string[] = []
  let cur = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
    } else if (ch === ',' && !inQuotes) {
      out.push(cur)
      cur = ''
    } else {
      cur += ch
    }
  }
  out.push(cur)
  return out.map((s) => s.trim())
}

export interface CsvParseResult {
  rows: ProductCSVRowInput[]
  skipped: number
}

export function parseProductCsv(text: string): CsvParseResult {
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  if (lines.length < 2) return { rows: [], skipped: 0 }

  const header = splitLine(lines[0]).map((h) => h.toLowerCase())
  const col = (name: string) => header.indexOf(name)
  const ni = col('name')
  const pi = col('price')
  const si = col('stock')
  const ii = col('image_url')
  const ci = col('category')

  const rows: ProductCSVRowInput[] = []
  let skipped = 0
  for (const line of lines.slice(1)) {
    const c = splitLine(line)
    const name = ni >= 0 ? c[ni] : ''
    const price = pi >= 0 ? parseFloat(c[pi]) : NaN
    const stock = si >= 0 ? parseInt(c[si], 10) : NaN
    if (!name || Number.isNaN(price) || Number.isNaN(stock)) {
      skipped++
      continue
    }
    rows.push({
      name,
      price,
      stock,
      image_url: ii >= 0 && c[ii] ? c[ii] : undefined,
      category: ci >= 0 && c[ci] ? c[ci] : undefined,
    })
  }
  return { rows, skipped }
}
