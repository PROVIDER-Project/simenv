import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cpus } from 'node:os'
import { chromium } from 'playwright'
import { mockPlayback, webUrl } from './playback-fixtures.mjs'

test('profiles post-response calculation separately from transport and rendering', { timeout: 240000 }, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    console.log(JSON.stringify({ browser: browser.version(), cpu: cpus()[0].model, cpuCount: cpus().length, cpuThrottling: 1 }))
    for (const fixture of [{ name: 'representative', count: 45, metrics: 3 }, { name: 'large', count: 1000, metrics: 13 }]) {
      const context = await browser.newContext()
      const page = await context.newPage()
      const requests = await mockPlayback(page, fixture)
      await page.addInitScript(() => {
        window.playbackMeasurements = []
        window.playbackInteractions = []
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) window.playbackMeasurements.push({ name: entry.name, duration: entry.duration })
        }).observe({ entryTypes: ['measure', 'longtask'] })
        for (const name of ['input', 'click']) document.addEventListener(name, () => {
          const began = performance.now()
          requestAnimationFrame(() => requestAnimationFrame(() => window.playbackInteractions.push(performance.now() - began)))
        }, true)
      })
      await page.goto(webUrl)
      await page.getByRole('button', { name: 'Pause', exact: true }).click()
      // Warm up, then three repeat seek/playback trials, including page arrivals.
      await page.getByRole('slider', { name: 'Simulation step' }).fill('150')
      await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '150')
      // Keep arrival samples; steady-state projection samples also cover warm trials.
      const interaction = []
      for (let trial = 0; trial < 3; trial++) {
        for (const target of [250, 0, 150]) {
          const began = performance.now()
          await page.getByRole('slider', { name: 'Simulation step' }).fill(String(target))
          await page.waitForFunction(target => document.querySelector('[aria-label="Simulation step"]')?.value === String(target), target)
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
          interaction.push(performance.now() - began)
        }
        await page.getByRole('button', { name: 'Play', exact: true }).click()
        await page.waitForTimeout(500)
        await page.getByRole('button', { name: 'Pause', exact: true }).click()
      }
      const samples = await page.evaluate(() => window.playbackMeasurements)
      const percentile = (values, p) => [...values].sort((a, b) => a - b)[Math.min(values.length - 1, Math.floor(values.length * p))] ?? null
      const stats = Object.fromEntries([...new Set(samples.map(s => s.name))].map(name => {
        const values = samples.filter(s => s.name === name).map(s => s.duration)
        return [name, { count: values.length, p50: percentile(values, .5), p95: percentile(values, .95) }]
      }))
      assert.ok(samples.some(sample => sample.name === 'playback.project'))
      assert.ok(requests.every(request => request.limit === 100))
      const browserInteraction = await page.evaluate(() => window.playbackInteractions)
      console.log(JSON.stringify({ fixture: fixture.name, stats,
        inputToPaintMs: { p50: percentile(browserInteraction, .5), p95: percentile(browserInteraction, .95) },
        seekEndToEndMs: { p50: percentile(interaction, .5), p95: percentile(interaction, .95) }, requests: requests.length }))
      await context.close()
    }
  } finally { await browser.close() }
})

test('profiles an actual recorded run with its persisted nodes and edges', {
  timeout: 180000,
  skip: !process.env.SIMENV_REAL_WEB_URL && 'set SIMENV_REAL_WEB_URL to a running stack with a completed run',
}, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    const requests = []
    page.on('request', request => {
      if (request.url().includes('/frames?')) requests.push(new URL(request.url()))
    })
    await page.addInitScript(() => {
      window.playbackMeasurements = []
      window.playbackInteractions = []
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) window.playbackMeasurements.push({ name: entry.name, duration: entry.duration })
      }).observe({ entryTypes: ['measure', 'longtask'] })
      for (const name of ['input', 'click']) document.addEventListener(name, () => {
        const began = performance.now()
        requestAnimationFrame(() => requestAnimationFrame(() => window.playbackInteractions.push(performance.now() - began)))
      }, true)
    })
    const sceneResponse = page.waitForResponse(response => /\/scenarios\/\d+\/scene$/.test(response.url()))
    await page.goto(process.env.SIMENV_REAL_WEB_URL)
    const recordedScene = await (await sceneResponse).json()
    assert.ok(recordedScene.nodes.length > 1 && recordedScene.edges.length > 0)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    for (let trial = 0; trial < 3; trial++) {
      for (const period of [150, 250, 0]) {
        await page.getByRole('slider', { name: 'Simulation step' }).fill(String(period))
        await page.waitForFunction(period => document.querySelector('[aria-label="Simulation step"]')?.value === String(period), period)
      }
      await page.getByRole('button', { name: 'Play', exact: true }).click()
      await page.waitForTimeout(500)
      await page.getByRole('button', { name: 'Pause', exact: true }).click()
    }
    const samples = await page.evaluate(() => window.playbackMeasurements)
    const interactions = await page.evaluate(() => window.playbackInteractions)
    const p95 = values => [...values].sort((a, b) => a - b)[Math.floor(values.length * .95)] ?? null
    const stats = Object.fromEntries([...new Set(samples.map(s => s.name))].map(name => [name, {
      count: samples.filter(s => s.name === name).length,
      p95: p95(samples.filter(s => s.name === name).map(s => s.duration)),
    }]))
    assert.ok(samples.some(s => s.name === 'playback.project'))
    assert.ok(requests.some(url => url.searchParams.get('start') === '200'))
    assert.ok(requests.every(url => url.searchParams.get('limit') === '100'))
    console.log(JSON.stringify({ fixture: 'recorded', run: recordedScene.run_id,
      nodes: recordedScene.nodes.length, edges: recordedScene.edges.length,
      stats, inputToPaintP95Ms: p95(interactions), requests: requests.length }))
  } finally { await browser.close() }
})
