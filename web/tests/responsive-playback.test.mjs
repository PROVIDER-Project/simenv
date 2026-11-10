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
    return r.width > 0 && r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1 && (hit === el || el.contains(hit))
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
    return { left: box('.sim-playback-sidebar'), right: box('.sim-configurator'), timeline: box('.sim-timeline'), app: box('.sim-app'), header: box('.sim-frame-heading'), subtitle: box('.sim-frame-subtitle'), restart: box('.sim-tutorial-restart'), footer: box('.sim-frame-meta') }
  })
  const { left, right, timeline, app, header, subtitle, restart, footer } = boxes
  if (desktop) {
    assert.equal(right.width, app.width <= 1500 ? 320 : 420, 'medium screens reserve a narrower configurator column')
    assert.equal(left.y, app.y + 24, 'left sidebar starts at app top + 24px')
    assert.equal(right.y, app.y + 24, 'right sidebar starts at app top + 24px')
    assert.ok(header.x >= left.right + 15 && header.right + 15 <= right.x, 'header stays in center column')
    assert.ok(left.right + 15 <= timeline.x, JSON.stringify(boxes))
    assert.ok(timeline.right + 15 <= right.x, JSON.stringify(boxes))
    assert.ok(timeline.width >= 360, 'minimum usable center width')
    assert.ok(left.height >= app.height - 210, 'timeline must not squeeze sidebar')
    assert.ok(timeline.y - header.bottom >= 196, 'preserve usable globe below normal-flow header')
    assert.ok(Math.abs(left.bottom - timeline.bottom) <= 1 && Math.abs(right.bottom - timeline.bottom) <= 1, 'sidebars extend through timeline bottom')
    assert.ok(footer.y >= timeline.bottom + 15, 'footer follows panels and timeline')
    if (timeline.bottom > app.bottom) {
      assert.equal(await page.locator('.sim-app').evaluate(el => getComputedStyle(el).overflowY), 'auto', 'oversized timeline must scroll instead of clipping')
    }
  } else {
    assert.ok(header.bottom <= left.y, 'header and restart precede flow controls')
    assert.ok(left.bottom <= timeline.y && timeline.bottom <= right.y, 'flow controls must not overlap')
  }
  assert.ok(restart.y >= subtitle.bottom, 'restart must follow header text without overlap')
  assert.ok(restart.bottom <= header.bottom, 'header must contain restart in normal flow')
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

test('medium configurator controls and labels fit the narrower panel', async () => {
  const { browser, page } = await setup({ width: 1275, height: 605 })
  try {
    const panel = page.locator('.sim-configurator')
    assert.equal((await panel.boundingBox()).width, 320)
    for (const control of [
      panel.getByRole('button', { name: 'Hide', exact: true }),
      panel.getByRole('button', { name: 'Run simulation', exact: true }),
      panel.getByRole('textbox', { name: 'Scenario name' }),
      panel.getByRole('slider', { name: 'Brazil drought loss' }),
      panel.getByRole('checkbox', { name: 'Santos port congestion' }),
      page.getByRole('button', { name: 'Restart tutorial', exact: true }),
    ]) await reachable(control)
    assert.equal(await panel.evaluate(el => el.scrollWidth <= el.clientWidth), true, 'panel must not overflow horizontally')
    for (const label of await panel.locator('label').all()) {
      assert.equal(await label.evaluate(el => {
        const bounds = el.getBoundingClientRect()
        const panel = el.closest('.sim-configurator').getBoundingClientRect()
        return el.scrollWidth <= el.clientWidth && bounds.left >= panel.left && bounds.right <= panel.right
      }), true, `configurator label remains within the panel: ${await label.innerText()}`)
    }
    assert.equal(await page.locator('.sim-app').evaluate(el => el.scrollWidth <= el.clientWidth), true)
  } finally { await browser.close() }
})

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
      await cards.waitFor({ state: 'hidden' })
      assert.equal(await cards.isVisible(), false, 'temporary reveal restores responsive preference')
      await next.click()
      await cards.waitFor()
      await back.click()
      await keyboardToggle(page, 'Show indicators')
      await keyboardToggle(page, 'Hide indicators')
      await next.click()
      await cards.waitFor()
      await back.click()
      await cards.waitFor({ state: 'hidden' })
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
      await cards.waitFor({ state: 'hidden' })
      assert.equal(await cards.isVisible(), false, 'closing tour releases temporary override')
    } finally { await browser.close() }
  })
}
