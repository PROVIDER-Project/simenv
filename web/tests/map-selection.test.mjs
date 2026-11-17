import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { dismissInitialTutorial } from './browser-setup.mjs'
import { mockPlayback, origin, webUrl, scene } from './playback-fixtures.mjs'

import { clickMarker } from './globe-browser-utils.mjs'

test('a map icon selects details without moving the sidebar and synchronizes the dropdown', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await mockPlayback(page)
    await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
      const parts = new URL(route.request().url()).pathname.split('/')
      const result = scene(parts[2], Number(parts[4]))
      result.nodes[0] = { ...result.nodes[0], label: 'Workshop North Farm', placements: [] }
      result.nodes.push({ id: 'argentina_farms', label: 'Sojaanbau Argentinien', role: 'producer', entityIds: ['argentina_farms'], placements: [], hasRecordedData: true })
      result.edges.push({ id: 'argentina-brazil', source: 'argentina_farms', target: 'brazil_farms', isSeaCrossing: false })
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await page.getByRole('slider', { name: 'Simulation step' }).fill('150')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '150')
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
    await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
    const scrollTop = await page.locator('.sim-playback-sidebar').evaluate(element => element.scrollTop)
    await clickMarker(page, 'argentina_farms')
    const selector = page.getByRole('combobox', { name: 'Inspect component' })
    await selector.waitFor({ state: 'visible' })
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'argentina_farms')
    assert.equal(await selector.isVisible(), true)
    await page.getByRole('region', { name: 'Component status' }).getByRole('heading', { name: 'Argentina soy farms · step 150' }).waitFor()
    assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), '150')
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'start')
    assert.equal(await page.locator('.sim-playback-sidebar').evaluate(element => element.scrollTop), scrollTop,
      'map selection updates content without scrolling to the inspector')
    await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
    await clickMarker(page, 'argentina_farms')
    await selector.waitFor({ state: 'visible' })
    assert.equal(await selector.isVisible(), true, 'clicking an already selected icon reopens details')
    await selector.selectOption('brazil_farms')
    await page.getByRole('region', { name: 'Component status' }).getByRole('heading', { name: /Workshop North Farm/ }).waitFor()
    await page.locator('.sim-label--node').filter({ hasText: 'Workshop North Farm' }).waitFor()
    await clickMarker(page, 'argentina_farms')
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'argentina_farms')
    assert.equal(await selector.inputValue(), 'argentina_farms')
  } finally { await browser.close() }
})

test('the shipped static demo displays English node, connection and detail labels', { skip: !process.env.SIMENV_STATIC_WEB_URL }, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await dismissInitialTutorial(page)
    await page.goto(process.env.SIMENV_STATIC_WEB_URL)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    const options = await page.getByRole('combobox', { name: 'Inspect component' }).locator('option').allTextContents()
    assert.doesNotMatch(options.join(' '), /Sojaanbau|Hafen |Ölmühlen|Futtermittelhersteller|Geflügelbetriebe|Schweinebetriebe|Milchwirtschaft/)
    assert.doesNotMatch(await page.locator('.sim-label').allTextContents().then(text => text.join(' ')), /Sojaanbau|Hafen |Ölmühlen|Futtermittelhersteller/)
    await page.getByRole('combobox', { name: 'Inspect component' }).selectOption('poultry_farms')
    assert.match(await page.getByRole('region', { name: 'Component status' }).innerText(), /EU poultry farms/)
    await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
    await clickMarker(page, 'argentina_farms')
    await page.getByRole('region', { name: 'Component status' }).getByRole('heading', { name: /Argentina soy farms/ }).waitFor()
  } finally { await browser.close() }
})

test('pooled map icons select their owning component while playback continues', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await mockPlayback(page)
    await page.route(`${origin}/runs/*/scenarios/*/scene`, route => {
      const parts = new URL(route.request().url()).pathname.split('/')
      const result = scene(parts[2], Number(parts[4]))
      result.nodes.push({ id: 'eu_farmers', role: 'consumer', label: 'Geflügelbetriebe / Schweinebetriebe',
        entityIds: ['poultry_farms', 'pig_farms'], placements: [], hasRecordedData: true })
      result.edges.push({ id: 'pooled', source: 'brazil_farms', target: 'eu_farmers', isSeaCrossing: true })
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl)
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await clickMarker(page, 'eu_farmers::poultry_farms')
    const selector = page.getByRole('combobox', { name: 'Inspect component' })
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"] select')?.value === 'eu_farmers')
    assert.match(await page.getByRole('region', { name: 'Component status' }).innerText(), /Pooled component: EU poultry farms, EU pig farms/)
    await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
    const period = Number(await page.getByRole('slider', { name: 'Simulation step' }).inputValue())
    await page.getByRole('button', { name: 'Play', exact: true }).click()
    await clickMarker(page, 'eu_farmers::pig_farms')
    await selector.waitFor({ state: 'visible' })
    assert.equal(await selector.inputValue(), 'eu_farmers')
    await page.waitForFunction(previous => Number(document.querySelector('[aria-label="Simulation step"]')?.value) > previous, period)
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'first')
    assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).inputValue(), '1')
    assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'auto')
  } finally { await browser.close() }
})
