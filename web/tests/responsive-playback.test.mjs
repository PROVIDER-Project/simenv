import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, webUrl } from './playback-fixtures.mjs'

async function setup(viewport, tutorial = false) {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport })
  page.setDefaultTimeout(5000)
  await mockPlayback(page, { tutorial })
  await page.goto(webUrl)
  await page.getByRole('region', { name: 'Component status' }).waitFor()
  const open = page.getByRole('button', { name: 'Open', exact: true })
  if (await open.count()) await open.click()
  return { browser, page }
}

async function reachable(locator) {
  await locator.scrollIntoViewIfNeeded()
  assert.equal(await locator.evaluate(el => {
    const r = el.getBoundingClientRect()
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
    return r.width > 0 && r.top >= 0 && r.bottom <= innerHeight + 1 && (hit === el || el.contains(hit))
  }), true, `pointer reachability: ${locator}`)
}

async function keyboardToggle(page, name) {
  // When the tour targets component evidence its floating card may cover the
  // unrelated timeline. Set up preferences with the native keyboard action.
  const button = page.getByRole('button', { name, exact: true })
  await button.focus()
  await button.press('Space')
}

async function geometry(page, desktop) {
  if (desktop) await page.locator('.sim-app').evaluate(el => { el.scrollTop = 0 })
  const boxes = await page.evaluate(() => {
    const box = selector => {
      const r = document.querySelector(selector).getBoundingClientRect()
      return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, height: r.height, width: r.width }
    }
    return { left: box('.sim-playback-sidebar'), right: box('.sim-configurator'), timeline: box('.sim-timeline'), app: box('.sim-app') }
  })
  const { left, right, timeline, app } = boxes
  if (desktop) {
    assert.ok(left.right + 15 <= timeline.x, JSON.stringify(boxes))
    assert.ok(timeline.right + 15 <= right.x, JSON.stringify(boxes))
    assert.ok(timeline.width >= 360, 'minimum usable center width')
    assert.ok(left.height >= app.height - 210, 'timeline must not squeeze sidebar')
    assert.ok(timeline.y - (app.y + 155) >= 180, 'preserve usable globe above timeline')
    if (timeline.bottom > app.bottom) {
      assert.equal(await page.locator('.sim-app').evaluate(el => getComputedStyle(el).overflowY), 'auto', 'oversized timeline must scroll instead of clipping')
    }
  } else {
    assert.ok(left.bottom <= timeline.y && timeline.bottom <= right.y, 'flow controls must not overlap')
  }
  const controls = [
    page.getByRole('button', { name: /^(Play|Pause)$/ }),
    page.getByRole('slider', { name: 'Simulation step' }),
    page.getByRole('button', { name: /^(Show|Hide) indicators$/ }),
    page.getByRole('combobox', { name: 'Recorded scenario', exact: true }),
    page.getByRole('textbox', { name: 'Scenario name' }),
  ]
  for (const control of controls) await reachable(control)
}

for (const [width, height, desktop, expanded] of [
  [1275, 605, true, false], [1280, 720, true, false], [1440, 1000, true, false],
  [1920, 1080, true, true], [390, 844, false, false], [1280, 500, false, false],
  [1159, 1000, false, false], [1160, 1000, true, false],
  [1500, 801, true, false], [1501, 801, true, true], [1501, 800, true, false],
  [1280, 540, false, false], [1280, 541, true, false],
]) {
  test(`coordinated layout and indicator defaults ${width}x${height}`, async () => {
    const { browser, page } = await setup({ width, height })
    try {
      await geometry(page, desktop)
      for (const card of await page.getByRole('group', { name: 'Network indicators' }).locator('[data-metric]').all()) await reachable(card)
      const toggle = page.getByRole('button', { name: /^(Show|Hide) indicators$/ })
      assert.equal(await toggle.getAttribute('aria-expanded'), String(expanded))
      const id = await toggle.getAttribute('aria-controls')
      assert.ok(id)
      assert.equal(await page.locator(`[id="${id}"]`).isVisible(), expanded)
      await toggle.click()
      assert.equal(await page.getByRole('button', { name: 'Pause', exact: true }).count(), 1, 'toggle must not pause active playback')
      await toggle.click()
      await page.getByRole('button', { name: 'Pause', exact: true }).click()
      await page.getByRole('slider', { name: 'Simulation step' }).fill('121')
      await toggle.click()
      assert.equal(await toggle.getAttribute('aria-controls'), id)
      assert.equal(await page.locator(`[id="${id}"]`).isVisible(), !expanded)
      await geometry(page, desktop)
      for (const card of await page.getByRole('group', { name: 'Network indicators' }).locator('[data-metric]').all()) await reachable(card)
      assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), '121')
      assert.equal(await page.getByRole('button', { name: 'Play', exact: true }).count(), 1)
      assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'first')
    } finally { await browser.close() }
  })
}

test('responsive defaults follow resizing until explicit preference; both choices survive selection remounts', async () => {
  const { browser, page } = await setup({ width: 1440, height: 1000 })
  try {
    const toggle = page.getByRole('button', { name: /^(Show|Hide) indicators$/ })
    assert.equal(await toggle.getAttribute('aria-expanded'), 'false')
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.getByRole('button', { name: 'Hide indicators', exact: true }).waitFor()
    await page.setViewportSize({ width: 1280, height: 720 })
    await page.getByRole('button', { name: 'Show indicators', exact: true }).click()
    for (const expanded of [true, false]) {
      if (!expanded) await page.getByRole('button', { name: 'Hide indicators', exact: true }).click()
      await page.setViewportSize({ width: 1920, height: 1080 })
      await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption(expanded ? 'second' : 'first')
      await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).selectOption('0')
      await page.getByRole('region', { name: 'Component status' }).waitFor()
      assert.equal(await toggle.getAttribute('aria-expanded'), String(expanded))
      await page.setViewportSize({ width: 1275, height: 605 })
      assert.equal(await toggle.getAttribute('aria-expanded'), String(expanded))
      await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).selectOption('1')
      await page.getByRole('region', { name: 'Component status' }).waitFor()
      assert.equal(await toggle.getAttribute('aria-expanded'), String(expanded))
    }
  } finally { await browser.close() }
})

for (const language of ['en', 'de']) {
  test(`tutorial indicators temporary reveal, dismissal, revisit and orientation ${language}`, async () => {
    const { browser, page } = await setup({ width: 844, height: 390 }, true)
    try {
      const tour = page.getByRole('region', { name: 'Interactive tutorial' })
      if (language === 'de') await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
      const next = tour.getByRole('button', { name: language === 'de' ? 'Weiter' : 'Next', exact: true })
      const back = tour.getByRole('button', { name: language === 'de' ? 'Zurück' : 'Back', exact: true })
      for (let i = 0; i < 8; i++) await next.click()
      const cards = page.getByRole('group', { name: 'Network indicators' })
      await cards.waitFor()
      assert.equal(await cards.locator('[data-metric]').count(), 4)
      assert.equal(await page.locator('.sim-tutorial-shell--docked').count(), 1)
      assert.equal(await page.locator('.sim-app').evaluate(el => getComputedStyle(el).display), 'block', 'docked inset uses effective app height')
      await reachable(page.getByRole('button', { name: 'Hide indicators', exact: true }))
      await page.getByRole('button', { name: 'Hide indicators', exact: true }).click()
      await page.setViewportSize({ width: 1200, height: 600 })
      await page.waitForTimeout(250)
      assert.equal(await cards.isVisible(), false, 'same entry respects close after resize and playback updates')
      await back.click()
      await next.click()
      await cards.waitFor()
      await reachable(page.getByRole('button', { name: 'Hide indicators', exact: true }))
      await back.click()
      assert.equal(await cards.isVisible(), false, 'temporary reveal restores responsive preference')
      await next.click()
      await cards.waitFor()
      await back.click()
      await keyboardToggle(page, 'Show indicators')
      await keyboardToggle(page, 'Hide indicators')
      await next.click()
      await cards.waitFor()
      await back.click()
      assert.equal(await cards.isVisible(), false, 'restore explicit collapsed preference')
      await keyboardToggle(page, 'Show indicators')
      await next.click()
      await page.getByRole('button', { name: 'Hide indicators', exact: true }).click()
      await back.click()
      await cards.waitFor()
      assert.equal(await page.getByRole('button', { name: 'Hide indicators', exact: true }).getAttribute('aria-expanded'), 'true', 'tutorial-only close must not replace explicit expanded preference')
      await keyboardToggle(page, 'Hide indicators')
      await next.click()
      await cards.waitFor()
      await page.keyboard.press('Escape')
      assert.equal(await cards.isVisible(), false, 'closing tour releases temporary override')
    } finally { await browser.close() }
  })
}
