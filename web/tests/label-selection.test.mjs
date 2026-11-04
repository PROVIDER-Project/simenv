import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, origin, webUrl, scene, page as frames } from './playback-fixtures.mjs'
import { aimAtMarker, clickMarker } from './globe-browser-utils.mjs'

async function fixture(page) {
  await mockPlayback(page)
  await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
    const parts = new URL(route.request().url()).pathname.split('/')
    const result = scene(parts[2], Number(parts[4]))
    result.nodes.push({ id: 'argentina_farms', label: 'Argentina processing workshop', role: 'processor',
      entityIds: ['argentina_farms'], placements: [], hasRecordedData: true })
    result.nodes.push({ id: 'port', label: 'Workshop port', role: 'port', entityIds: ['port'],
      placements: [{ entityId: 'port', label: 'Workshop port', lat: -24, lng: -46, illustrative: false }], hasRecordedData: false })
    result.edges.push({ id: 'link', source: 'argentina_farms', target: 'brazil_farms', isSeaCrossing: false })
    return route.fulfill({ json: result })
  })
  await page.route(`${origin}/runs/*/scenarios/*/frames*`, route => {
    const url = new URL(route.request().url()), parts = url.pathname.split('/')
    const result = frames(parts[2], Number(parts[4]), Number(url.searchParams.get('start')))
    for (const frame of result.frames) frame.agents.push({ entity_id: 'argentina_farms', agent_id: 0, role: 'processor',
      values: { unit_price: 100, quantity_available: 100, input_received: 100, input_processed: 70, unused_input: 30 } })
    return route.fulfill({ json: result })
  })
  await page.goto(webUrl)
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await page.getByRole('slider', { name: 'Simulation step' }).fill('150')
  await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '150')
}

async function settled(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
}

async function position(page) {
  return page.evaluate(() => {
    const app = document.querySelector('.sim-app'), sidebar = document.querySelector('.sim-playback-sidebar')
    const panel = document.querySelector('.sim-status-panel'), r = panel.getBoundingClientRect()
    return { app: app.scrollTop, sidebar: sidebar.scrollTop, box: [r.x, r.y, r.width] }
  })
}

function samePosition(actual, expected) {
  assert.ok(Math.abs(actual.app - expected.app) <= 1, 'page position must be retained')
  assert.ok(Math.abs(actual.sidebar - expected.sidebar) <= 1, 'sidebar position must be retained')
  actual.box.forEach((value, index) => assert.ok(Math.abs(value - expected.box[index]) <= 1, `panel position ${index} changed`))
}

test('projected node labels select with real pointer and native Enter/Space while retaining focus', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await fixture(page)
    await aimAtMarker(page, 'argentina_farms')
    const label = page.locator('.sim-label--node').filter({ hasText: 'Argentina processing workshop' })
    const box = await label.boundingBox()
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
    await settled(page)
    assert.equal(await page.getByRole('combobox', { name: 'Inspect component' }).inputValue(), 'argentina_farms')
    assert.equal(await label.evaluate(element => element.tagName), 'BUTTON')
    await page.getByRole('combobox', { name: 'Inspect component' }).selectOption('port')
    await label.focus()
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'argentina_farms')
    await page.getByRole('combobox', { name: 'Inspect component' }).selectOption('port')
    await label.focus()
    const before = await position(page)
    await page.keyboard.press('Space')
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'argentina_farms')
    await settled(page)
    samePosition(await position(page), before)
    assert.equal(await label.evaluate(element => element === document.activeElement), true)
    assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), '150')
    await page.getByRole('button', { name: 'Play', exact: true }).click()
    await label.focus()
    await page.waitForFunction(() => Number(document.querySelector('[aria-label="Simulation step"]')?.value) > 153)
    assert.equal(await label.evaluate(element => element === document.activeElement), true, 'playback updates must not recreate focused labels')
  } finally { await browser.close() }
})

for (const viewport of [{ width: 1440, height: 1000 }, { width: 1100, height: 800 }]) {
  test(`selection retains intermediate and bottom scroll positions at ${viewport.width}px`, async () => {
    const browser = await chromium.launch({ headless: true })
    try {
      const page = await browser.newPage({ viewport })
      await fixture(page)
      const selector = page.getByRole('combobox', { name: 'Inspect component' })
      await selector.selectOption('argentina_farms')
      await settled(page)
      for (const bottom of [false, true]) {
        await page.evaluate(atBottom => {
          const sidebar = document.querySelector('.sim-playback-sidebar')
          const scroller = getComputedStyle(sidebar).overflowY === 'auto' ? sidebar : document.querySelector('.sim-app')
          scroller.scrollTop = atBottom ? scroller.scrollHeight : Math.min(300, scroller.scrollHeight - scroller.clientHeight)
        }, bottom)
        const before = await position(page)
        await selector.selectOption('port')
        await settled(page)
        samePosition(await position(page), before)
        await selector.selectOption('argentina_farms')
        await settled(page)
        samePosition(await position(page), before)
      }
      if (viewport.width > 1100) {
        const before = await position(page)
        await clickMarker(page, 'port')
        await page.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'port')
        await settled(page)
        samePosition(await position(page), before)
      }
    } finally { await browser.close() }
  })
}

test('retained inspector space survives collapse and resets to natural height at a new width', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await fixture(page)
    const selector = page.getByRole('combobox', { name: 'Inspect component' })
    await selector.selectOption('argentina_farms'); await settled(page)
    const range = await page.locator('.sim-playback-sidebar').evaluate(element => element.scrollHeight)
    await selector.selectOption('port'); await settled(page)
    await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Show disturbance impact' }).click()
    await settled(page)
    assert.ok(Math.abs(await page.locator('.sim-playback-sidebar').evaluate(element => element.scrollHeight) - range) <= 1)
    await page.setViewportSize({ width: 390, height: 844 }); await settled(page)
    assert.ok(await page.locator('.sim-stable-inspector').evaluate(element =>
      Math.abs(element.getBoundingClientRect().height - element.firstElementChild.getBoundingClientRect().height) <= 1),
    'a genuine width change releases obsolete height from the previous layout')
  } finally { await browser.close() }
})

test('projected pooled member labels select the owning component', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await mockPlayback(page)
    await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
      const parts = new URL(route.request().url()).pathname.split('/')
      const result = scene(parts[2], Number(parts[4]))
      result.nodes.push({ id: 'eu_farmers', label: 'EU livestock farms', role: 'consumer',
        entityIds: ['poultry_farms', 'pig_farms'], placements: [], hasRecordedData: true })
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await aimAtMarker(page, 'eu_farmers::pig_farms')
    await page.getByRole('button', { name: 'Select EU pig farms', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'eu_farmers')
    assert.match(await page.getByRole('region', { name: 'Component status' }).innerText(), /Pooled component: EU poultry farms, EU pig farms/)
  } finally { await browser.close() }
})
