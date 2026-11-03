import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, origin, webUrl, scene, page as framePage } from './playback-fixtures.mjs'

// Test-only inspection of React's mounted ref, using the real GlobeMethods API.
// No application hooks or alternative renderer are installed for these checks.
async function inspectGlobe(page) {
  return page.evaluate(() => {
    const root = document.querySelector('#root')
    const fiber = root[Object.keys(root).find(key => key.startsWith('__reactContainer'))]
    function find(node) {
      if (!node) return null
      let hook = node.memoizedState
      while (hook) {
        if (typeof hook.memoizedState?.current?.scene === 'function') return hook.memoizedState.current
        hook = hook.next
      }
      return find(node.child) || find(node.sibling)
    }
    const globe = find(fiber.stateNode?.current ?? fiber)
    if (!globe) throw new Error('Mounted globe ref not found')
    globe.controls().autoRotate = false
    globe.pauseAnimation()
    const curves = []
    globe.scene().traverse(object => {
      if (object.geometry?.type === 'TubeGeometry') curves.push(object)
    })
    const geometry = curves.map(object => {
      const position = object.geometry.getAttribute('position'), color = object.geometry.getAttribute('color')
      const path = object.geometry.parameters.path
      return { positions: position.count, colors: color?.count ?? 0,
        finite: [...position.array, ...color.array].every(Number.isFinite), rgba: [...color.array.slice(0, 4)],
        start: path.getPoint(0).toArray(), end: path.getPoint(1).toArray(), height: path.getPoint(.5).length() }
    })
    const renderer = globe.renderer(), gl = renderer.getContext()
    const pixels = () => {
      renderer.render(globe.scene(), globe.camera())
      const result = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4)
      gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, result)
      return result
    }
    const visible = pixels()
    curves.forEach(object => { object.visible = false })
    const hidden = pixels()
    curves.forEach(object => { object.visible = true })
    renderer.render(globe.scene(), globe.camera())
    let changedPixels = 0
    for (let i = 0; i < visible.length; i += 4) if (visible[i] !== hidden[i] || visible[i + 1] !== hidden[i + 1] || visible[i + 2] !== hidden[i + 2]) changedPixels++
    globe.resumeAnimation()
    return { geometry, changedPixels, radius: globe.getGlobeRadius(),
      farm: Object.values(globe.getCoords(-15, -50, 0)), port: Object.values(globe.getCoords(-24, -46, 0)), eu: Object.values(globe.getCoords(50, 10, 0)) }
  })
}

test('connections retain real finite geometry, visible pixels and status colors while seeking', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await mockPlayback(page)
    await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
      const parts = new URL(route.request().url()).pathname.split('/')
      const result = scene(parts[2], Number(parts[4]))
      for (const [id, lat, lng] of [['port', -24, -46], ['eu', 50, 10]]) result.nodes.push({
        id, label: id, role: 'port', entityIds: [id], hasRecordedData: false,
        placements: [{ entityId: id, label: id, lat, lng, illustrative: false }],
      })
      result.edges = [{ id: 'short', source: 'brazil_farms', target: 'port', isSeaCrossing: false },
        { id: 'long', source: 'brazil_farms', target: 'eu', isSeaCrossing: true }]
      return route.fulfill({ json: result })
    })
    await page.route(`${origin}/runs/*/scenarios/*/frames*`, route => {
      const url = new URL(route.request().url()), parts = url.pathname.split('/')
      const scenario = Number(parts[4]), start = Number(url.searchParams.get('start'))
      const result = framePage(parts[2], scenario, start)
      for (const frame of result.frames) frame.agents[0].values = scenario === 1 && frame.period >= 280 ? {}
        : { unit_price: 100, quantity_available: scenario === 1 && frame.period >= 100 && frame.period < 200 ? 50 : 100, active: 1 }
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    const states = []
    for (const period of [0, 150, 250, 290]) {
      await page.getByRole('slider', { name: 'Simulation step' }).fill(String(period))
      await page.waitForFunction(step => document.querySelector('[aria-label="Component status"]')?.dataset.period === String(step), period)
      await page.waitForFunction(() => !document.querySelector('[aria-label="Reference comparison"] [role="status"]'))
      assert.deepEqual(errors, [], 'edge-bearing playback must not throw inside the globe renderer')
      const actual = await inspectGlobe(page)
      assert.equal(actual.geometry.length, 6, 'short and long connections each retain halo/glow/core')
      assert.ok(actual.changedPixels > 50, 'connections must produce visible canvas pixels, not just labels')
      for (const curve of actual.geometry) {
        assert.ok(curve.positions > 0 && curve.finite)
        assert.equal(curve.colors, curve.positions)
        assert.ok(curve.height > actual.radius)
      }
      const distance = (a, b) => Math.hypot(...a.map((value, index) => value - b[index]))
      actual.geometry.forEach((curve, index) => {
        assert.ok(distance(curve.start, actual.farm) < .001, 'connection starts at its recorded source placement')
        assert.ok(distance(curve.end, index < 3 ? actual.port : actual.eu) < .001, 'connection ends at its target placement')
      })
      assert.deepEqual(actual.geometry.map(curve => Number(curve.rgba[3].toFixed(2))), [.16, .34, .92, .16, .34, .92])
      states.push(actual.geometry[2].rgba.slice(0, 3))
    }
    assert.deepEqual(states[0], states[2], 'recovery restores the healthy connection color')
    assert.ok(states[0][1] > states[0][0], 'healthy connection is green')
    assert.ok(states[1][0] > states[1][1], 'disturbed connection is red')
    assert.notDeepEqual(states[3], states[0], 'unknown connection is distinct from healthy')
    assert.ok(states[3][2] > states[3][1] && states[3][1] > states[3][0], 'unknown uses the shared gray-blue palette')
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    assert.equal((await inspectGlobe(page)).geometry.length, 6, 'switching runs does not lose or duplicate connections')
    await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).selectOption('0')
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    assert.equal((await inspectGlobe(page)).geometry.length, 6, 'switching scenarios preserves connections')
  } finally { await browser.close() }
})

test('impact stays below run selection in a narrow independently collapsible sidebar', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await mockPlayback(page); await page.goto(webUrl)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    const run = page.getByRole('region', { name: 'Recorded playback', exact: true })
    const impact = page.getByRole('complementary', { name: 'Disturbance impact' })
    const runBox = await run.boundingBox(), impactBox = await impact.boundingBox()
    assert.ok(impactBox.y >= runBox.y + runBox.height, 'impact belongs below, not beside run selection')
    assert.equal(impactBox.x, runBox.x)
    assert.ok(impactBox.x + impactBox.width < 1440 / 3)
    await page.getByRole('slider', { name: 'Simulation step' }).fill('150')
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
    const hideImpact = page.getByRole('button', { name: 'Hide disturbance impact' })
    await hideImpact.click()
    assert.equal(await page.getByRole('button', { name: 'Show disturbance impact' }).getAttribute('aria-expanded'), 'false')
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).isVisible(), false)
    await page.getByRole('button', { name: 'Hide playback selection' }).click()
    await page.getByRole('button', { name: 'Play', exact: true }).click()
    await page.waitForFunction(() => Number(document.querySelector('[aria-label="Simulation step"]')?.value) > 150)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    const period = await page.getByRole('slider', { name: 'Simulation step' }).inputValue()
    await page.getByRole('button', { name: 'Show disturbance impact' }).click()
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'start')
    await page.setViewportSize({ width: 1440, height: 600 })
    await page.getByRole('combobox', { name: 'Inspect component' }).scrollIntoViewIfNeeded()
    assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), period)
    await page.setViewportSize({ width: 390, height: 844 })
    assert.ok(await page.evaluate(() => document.querySelector('.sim-app').scrollWidth <= innerWidth))
    assert.equal(await page.locator('.sim-playback-sidebar').evaluate(element => getComputedStyle(element).overflowY), 'visible')
    await page.getByRole('combobox', { name: 'Inspect component' }).scrollIntoViewIfNeeded()
    await page.setViewportSize({ width: 1440, height: 1000 })
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'start')
    assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), period)
  } finally { await browser.close() }
})

test('expanded sidebar never intercepts timeline controls on a narrow short desktop', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1101, height: 600 } })
    await mockPlayback(page); await page.goto(webUrl)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    const slider = page.getByRole('slider', { name: 'Simulation step' })
    await slider.fill('150')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '150')
    assert.equal(await slider.evaluate(element => {
      const rect = element.getBoundingClientRect(), y = rect.y + rect.height / 2
      return [rect.x + 2, rect.right - 2].every(x => document.elementFromPoint(x, y) === element)
    }), true, 'both slider endpoints must receive pointer input')
    const rect = await slider.boundingBox()
    await page.mouse.click(rect.x + 2, rect.y + rect.height / 2)
    await page.waitForFunction(() => Number(document.querySelector('[aria-label="Simulation step"]')?.value) < 5)
    assert.equal(await page.getByRole('button', { name: 'Play', exact: true }).evaluate(element => {
      const r = element.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
      return hit === element || element.contains(hit)
    }), true)
  } finally { await browser.close() }
})
