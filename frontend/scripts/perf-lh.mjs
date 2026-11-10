import { spawn } from 'node:child_process'
import { cpus, freemem, totalmem } from 'node:os'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = path.resolve(frontendRoot, '..')
const args = parseArgs(process.argv.slice(2))
const tbtBenchmarkIndexThreshold = 2500
const runsPerPreset = Number(args.runs ?? 5)
const presets = String(args.presets ?? 'mobile,desktop').split(',').map((value) => value.trim())
const outputPath = args.output
  ? path.resolve(process.cwd(), args.output)
  : path.join(repoRoot, 'docs/redesign/phase6-7-part2/lighthouse-ab.json')
const chromePath = args['chrome-path'] ?? process.env.CHROME_PATH
if (args.help) {
  console.log('Usage: npm run perf:lh -- --a <url> --b <url> [--runs 5] [--presets mobile,desktop] [--output <path>] [--chrome-path <path>]')
  process.exit(0)
}
const chromeFlags = [
  '--headless',
  '--no-sandbox',
  '--disable-gpu',
  '--disable-background-networking',
  '--disable-component-update',
  '--disable-sync',
  '--disable-default-apps',
  '--disable-extensions',
  '--no-first-run',
  '--no-default-browser-check',
].join(' ')

if (!args.a || !args.b) throw new Error('Usage: npm run perf:lh -- --a <url> --b <url> [--runs 5]')
if (!Number.isInteger(runsPerPreset) || runsPerPreset < 1) throw new Error('--runs must be a positive integer')
if (presets.some((preset) => !['mobile', 'desktop'].includes(preset))) throw new Error('Presets must be mobile and/or desktop')

const temporaryDirectory = await mkdtemp(path.join(process.env.TEMP ?? process.env.TMP ?? '/tmp', 'turbineiq-lh-'))
const allRuns = []
await mkdir(path.dirname(outputPath), { recursive: true })

try {
  for (const preset of presets) {
    for (let index = 0; index < runsPerPreset; index += 1) {
      for (const label of ['A', 'B']) {
        const url = args[label.toLowerCase()]
        const reportPath = path.join(temporaryDirectory, `${preset}-${index + 1}-${label}.json`)
        const before = systemSnapshot()
        const startedAt = new Date().toISOString()
        const commandArgs = [
          path.join(frontendRoot, 'node_modules/lighthouse/cli/index.js'),
          url,
          '--output=json',
          `--output-path=${reportPath}`,
          '--only-categories=performance,accessibility,best-practices',
          '--quiet',
          `--chrome-flags=${chromeFlags}`,
          ...(preset === 'desktop' ? ['--preset=desktop'] : ['--form-factor=mobile']),
          ...(chromePath ? [`--chrome-path=${chromePath}`] : []),
        ]
        console.log(`Running ${preset} ${index + 1}/${runsPerPreset} ${label}: ${url}`)
        await run(process.execPath, commandArgs, { cwd: repoRoot })
        const after = systemSnapshot()
        const report = JSON.parse(await readFile(reportPath, 'utf8'))
        const record = readRun(report, {
          label,
          build: args[label === 'A' ? 'label-a' : 'label-b'] ?? label,
          preset,
          index: index + 1,
          url,
          startedAt,
          before,
          after,
        })
        allRuns.push(record)
        warnIfTbtNotComparable(record)
        console.log(formatRun(record))
      }
    }
  }

  const result = {
    schemaVersion: 1,
    method: 'Alternating Lighthouse 13.6.0 A/B runs on local production builds; both categories and presets use identical browser flags.',
    tbtBenchmarkIndexThreshold,
    lighthouseVersion: '13.6.0',
    nodeVersion: process.version,
    platform: process.platform,
    cpuCount: cpus().length,
    memoryMiB: Math.round(totalmem() / 1024 / 1024),
    chromePath: chromePath ? '<configured Chrome binary>' : 'Lighthouse default discovery',
    runsPerPreset: runsPerPreset,
    builds: { A: args['label-a'] ?? 'A', B: args['label-b'] ?? 'B' },
    presets,
    runs: allRuns,
    summaries: summarize(allRuns),
  }
  await writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, { encoding: 'utf8' })
  console.log(`\nWrote ${path.relative(repoRoot, outputPath)}`)
  console.log(JSON.stringify(result.summaries, null, 2))
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true })
}

function parseArgs(values) {
  const parsed = {}
  for (let index = 0; index < values.length; index += 1) {
    const argument = values[index].replace(/^--/, '')
    const divider = argument.indexOf('=')
    const key = divider === -1 ? argument : argument.slice(0, divider)
    const nextValue = values[index + 1]
    parsed[key] = divider === -1
      ? nextValue && !nextValue.startsWith('--') ? values[++index] : true
      : argument.slice(divider + 1)
  }
  return parsed
}

function systemSnapshot() {
  const cpu = cpus().reduce((totals, core) => {
    for (const [key, value] of Object.entries(core.times)) totals[key] = (totals[key] ?? 0) + value
    return totals
  }, {})
  return { cpu, freeMemoryBytes: freemem(), nodeRssBytes: process.memoryUsage().rss }
}

function readRun(report, context) {
  const cpuBefore = context.before.cpu
  const cpuAfter = context.after.cpu
  const elapsedCpuMs = Object.keys(cpuAfter).reduce((sum, key) => sum + cpuAfter[key] - (cpuBefore[key] ?? 0), 0)
  const idleMs = cpuAfter.idle - cpuBefore.idle
  const totalCpuPercent = elapsedCpuMs > 0 ? Math.round(((elapsedCpuMs - idleMs) / elapsedCpuMs) * 1000) / 10 : null
  const audit = (id) => report.audits[id]?.numericValue ?? null
  const bootup = report.audits['bootup-time']?.details?.items ?? []
  return {
    id: `${context.preset}-${context.index}-${context.label}`,
    label: context.label,
    build: context.build,
    preset: context.preset,
    index: context.index,
    startedAt: context.startedAt,
    url: context.url,
    performance: Math.round((report.categories.performance.score ?? 0) * 100),
    accessibility: Math.round((report.categories.accessibility.score ?? 0) * 100),
    bestPractices: Math.round((report.categories['best-practices'].score ?? 0) * 100),
    tbtMs: round(audit('total-blocking-time')),
    lcpMs: round(audit('largest-contentful-paint')),
    cls: round(audit('cumulative-layout-shift'), 6),
    payloadBytes: Math.round(audit('total-byte-weight') ?? 0),
    benchmarkIndex: report.environment?.benchmarkIndex ?? null,
    systemLoad: {
      cpuUtilizationPercentDuringRun: totalCpuPercent,
      freeMemoryMiBBefore: round(context.before.freeMemoryBytes / 1024 / 1024),
      freeMemoryMiBAfter: round(context.after.freeMemoryBytes / 1024 / 1024),
      nodeRssMiB: round(context.after.nodeRssBytes / 1024 / 1024),
      cpuCount: cpus().length,
    },
    bootupTasks: bootup
      .map((item) => ({ url: item.url, totalMs: round(item.total), scriptingMs: round(item.scripting) }))
      .sort((left, right) => right.totalMs - left.totalMs)
      .slice(0, 8),
  }
}

function summarize(records) {
  const metrics = ['performance', 'accessibility', 'bestPractices', 'tbtMs', 'lcpMs', 'cls', 'payloadBytes', 'benchmarkIndex']
  const summaries = {}
  for (const preset of new Set(records.map((record) => record.preset))) {
    summaries[preset] = {}
    for (const label of ['A', 'B']) {
      const selected = records.filter((record) => record.preset === preset && record.label === label)
      summaries[preset][label] = Object.fromEntries(metrics.map((metric) => [
        metric,
        range(selected.map((record) => record[metric]), metric === 'cls' ? 6 : metric === 'lcpMs' || metric === 'benchmarkIndex' ? 1 : 0),
      ]))
    }
  }
  return summaries
}

function range(values, digits = 1) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!sorted.length) return { median: null, min: null, max: null }
  const middle = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
  return { median: round(median, digits), min: round(sorted[0], digits), max: round(sorted.at(-1), digits) }
}

function round(value, digits = 1) {
  if (!Number.isFinite(value)) return null
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function formatRun(record) {
  return `  perf ${record.performance} · TBT ${record.tbtMs} ms · LCP ${record.lcpMs} ms · CLS ${record.cls} · payload ${(record.payloadBytes / 1024).toFixed(0)} KiB · benchmarkIndex ${record.benchmarkIndex} · CPU ${record.systemLoad.cpuUtilizationPercentDuringRun}% · free RAM ${record.systemLoad.freeMemoryMiBBefore}→${record.systemLoad.freeMemoryMiBAfter} MiB`
}

function warnIfTbtNotComparable(record) {
  if (!Number.isFinite(record.benchmarkIndex)) {
    console.warn(`WARNING: ${record.id} has no benchmarkIndex; its TBT cannot be compared against the ${tbtBenchmarkIndexThreshold} threshold.`)
  } else if (record.benchmarkIndex < tbtBenchmarkIndexThreshold) {
    console.warn(`WARNING: ${record.id} benchmarkIndex ${record.benchmarkIndex} is below ${tbtBenchmarkIndexThreshold}; its TBT is not comparable.`)
  }
}

function run(command, commandArgs, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { ...options, stdio: 'inherit', windowsHide: true })
    child.once('error', reject)
    child.once('exit', (code) => (code === 0 ? resolve() : reject(new Error(`Lighthouse exited with ${code}`))))
  })
}
