import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = fileURLToPath(new URL('../', import.meta.url))
const targets = [resolve(repoRoot, 'README.md'), resolve(repoRoot, 'docs')]
const textExtensions = new Set(['.md', '.txt', '.json', '.jsonc', '.py', '.yml', '.yaml', '.log', '.csv', '.svg', '.html', '.xml'])
const forbidden = [
  { label: 'Windows drive path', pattern: /\b[A-Za-z]:[\\/]/g },
  { label: 'user home path', pattern: /(?:^|[^A-Za-z0-9])\/(?:Users|home)\/[^\s/<>"'`]+/g },
]
const violations = []

function visit(path) {
  const info = statSync(path)
  if (info.isDirectory()) {
    for (const entry of readdirSync(path)) visit(resolve(path, entry))
    return
  }
  if (!textExtensions.has(path.slice(path.lastIndexOf('.')).toLowerCase())) return

  const bytes = readFileSync(path)
  let content
  if (bytes[0] === 0xff && bytes[1] === 0xfe) {
    content = bytes.toString('utf16le', 2)
  } else if (bytes[0] === 0xfe && bytes[1] === 0xff) {
    const littleEndian = Buffer.from(bytes.subarray(2))
    for (let index = 0; index + 1 < littleEndian.length; index += 2) {
      const first = littleEndian[index]
      littleEndian[index] = littleEndian[index + 1]
      littleEndian[index + 1] = first
    }
    content = littleEndian.toString('utf16le')
  } else {
    content = bytes.toString('utf8')
    if (content.includes('\u0000')) content = bytes.toString('utf16le')
  }
  for (const { label, pattern } of forbidden) {
    pattern.lastIndex = 0
    for (const match of content.matchAll(pattern)) {
      const line = content.slice(0, match.index).split('\n').length
      violations.push(`${relative(repoRoot, path)}:${line}: ${label}`)
    }
  }
}

for (const target of targets) visit(target)

if (violations.length > 0) {
  console.error(`Found local absolute paths in documentation:\n${violations.join('\n')}`)
  process.exitCode = 1
} else {
  console.log('Documentation path scan passed (README.md and docs/).')
}
