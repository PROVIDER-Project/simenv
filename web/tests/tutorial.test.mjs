import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, webUrl } from './playback-fixtures.mjs'

async function setup(viewport = { width: 1440, height: 1000 }, storageFails = false) {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport })
  page.setDefaultTimeout(5000)
  await mockPlayback(page, { tutorial: true })
  if (storageFails) await page.addInitScript(() => {
    Storage.prototype.getItem = Storage.prototype.setItem = Storage.prototype.removeItem = () => { throw new Error('blocked') }
  })
  await page.goto(webUrl)
  return { browser, page, tour: page.getByRole('region', { name: 'Interactive tutorial' }) }
}

test('first visit guides without editing inputs; Finish persists and restart retains German', async () => {
  const { browser, page, tour } = await setup()
  try {
    await tour.waitFor()
    assert.equal(await tour.getByRole('heading').evaluate(el => el === document.activeElement), true)
    await page.getByRole('textbox', { name: 'Scenario name' }).fill('My own scenario')
    await page.getByRole('checkbox', { name: 'US emergency supply' }).uncheck()
    const inputs = await page.locator('textarea').evaluateAll(elements => elements.map(el => el.value))
    await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
    for (let i = 0; i < 8; i++) await tour.getByRole('button', { name: 'Weiter', exact: true }).click()
    assert.equal(await page.getByRole('textbox', { name: 'Scenario name' }).inputValue(), 'My own scenario')
    assert.deepEqual(await page.locator('textarea').evaluateAll(elements => elements.map(el => el.value)), inputs)
    await tour.getByRole('button', { name: 'Abschließen', exact: true }).click()
    await page.reload()
    await page.getByRole('button', { name: 'Restart tutorial' }).waitFor()
    assert.equal(await tour.count(), 0)
    await page.getByRole('button', { name: 'Restart tutorial' }).click()
    await tour.getByRole('heading', { name: 'Szenario benennen' }).waitFor()
    await page.reload()
    await tour.getByRole('heading', { name: 'Szenario benennen' }).waitFor()
  } finally { await browser.close() }
})

test('Escape dismisses only this session and keyboard navigation restores focus', async () => {
  const { browser, page, tour } = await setup()
  try {
    await tour.waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await tour.count(), 0)
    const restart = page.getByRole('button', { name: 'Restart tutorial' })
    assert.equal(await restart.evaluate(el => el === document.activeElement), true)
    await restart.press('Enter')
    await tour.getByRole('button', { name: 'Next', exact: true }).press('Enter')
    await tour.getByRole('button', { name: 'Back', exact: true }).press('Enter')
    await tour.getByRole('heading', { name: 'Name your scenario' }).waitFor()
    await page.reload()
    await tour.waitFor()
  } finally { await browser.close() }
})

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`reveals panels and keeps target reachable at ${viewport.width}px even without storage`, async () => {
    const { browser, page, tour } = await setup(viewport, true)
    try {
      await tour.waitFor()
      // The real source mounts additional panels asynchronously before the
      // configurator. The initial reveal must wait for that layout to settle.
      await page.getByRole('combobox', { name: 'Reference condition' }).waitFor()
      await page.waitForFunction(() => {
        const el = document.querySelector('[data-tutorial="scenario"]')
        const r = el?.getBoundingClientRect()
        return r && r.top >= -1 && r.bottom <= innerHeight + 1
      })
      await page.getByRole('textbox', { name: 'Scenario name' }).fill('Reachable')
      for (let i = 0; i < 9; i++) {
        const box = await tour.boundingBox()
        assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1)
        if (i === 4) {
          assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).evaluate(el => {
            const r = el.getBoundingClientRect()
            return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) === el
          }), true, 'restart control must not cover recorded scenario selection')
        }
        if (i === 5) {
          await page.getByRole('button', { name: 'Pause', exact: true }).click()
          await page.getByRole('slider', { name: 'Simulation step' }).fill('121')
          await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]').value === '121')
        }
        if (i === 7) {
          const selector = page.getByRole('combobox', { name: 'Inspect component' })
          await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
          await selector.waitFor()
          assert.equal(await selector.evaluate(el => {
            const r = el.getBoundingClientRect()
            const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
            return el === hit || el.contains(hit)
          }), true, 'component selector must remain reachable beside the popover')
        }
        if (i < 8) await tour.getByRole('button', { name: 'Next', exact: true }).click()
      }
      await tour.getByRole('button', { name: 'Finish', exact: true }).click()
      assert.equal(await tour.count(), 0)
    } finally { await browser.close() }
  })
}

test('missing completed-results target is acquired after explicit execution, exact run survives tour navigation', async () => {
  const { browser, page, tour } = await setup()
  try {
    const job = { id: 'second', label: 'Submitted example', status: 'completed', error: null,
      progress: { scenario_id: 1, step: 300, scenario_total_steps: 300, completed_steps: 300, total_steps: 300, percent_complete: 100 } }
    let submissions = 0
    await page.route('**/api/simulations', async route => {
      if (route.request().method() === 'POST') { submissions++; return route.fulfill({ status: 202, json: job }) }
      return route.fulfill({ json: { items: [], total: 0 } })
    })
    await tour.waitFor()
    for (let i = 0; i < 3; i++) await tour.getByRole('button', { name: 'Next', exact: true }).click()
    await tour.getByRole('status').waitFor()
    assert.equal(submissions, 0, 'tour navigation never submits a simulation')
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
    await page.getByRole('button', { name: 'View results', exact: true }).waitFor()
    await page.waitForFunction(() => !document.querySelector('.sim-tutorial [role="status"]'))
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('[aria-label="Recorded run"]').value === 'second')
    await tour.getByRole('heading', { name: 'Open the completed run' }).waitFor()
    assert.equal(submissions, 1)
    await tour.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('first')
    await tour.getByRole('heading', { name: 'Choose recorded playback' }).waitFor()
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    await tour.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]').value === '250')
    await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
    await tour.getByRole('button', { name: 'Next', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Hide disturbance impact' }).getAttribute('aria-expanded'), 'true')
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
    await tour.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('combobox', { name: 'Inspect component' }).selectOption('brazil_farms')
    await page.getByRole('region', { name: 'Component status' }).waitFor()
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'second')
    assert.equal(await page.getByRole('slider', { name: 'Simulation step' }).inputValue(), '250')
  } finally { await browser.close() }
})

test('step entry reveals collapsed panels once, nested scrolling tracks highlight without stealing focus', async () => {
  const { browser, page, tour } = await setup()
  try {
    await tour.waitFor()
    await page.getByRole('button', { name: 'Hide playback selection' }).click()
    for (let i = 0; i < 4; i++) await tour.getByRole('button', { name: 'Next', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Hide playback selection' }).getAttribute('aria-expanded'), 'true')
    await page.getByRole('button', { name: 'Hide playback selection' }).click()
    await page.waitForTimeout(200)
    assert.equal(await page.getByRole('button', { name: 'Show playback selection' }).getAttribute('aria-expanded'), 'false', 'tour must allow users to collapse the panel again')
    await tour.getByRole('button', { name: 'Next', exact: true }).click()
    await tour.getByRole('button', { name: 'Next', exact: true }).click()
    const reference = page.getByRole('combobox', { name: 'Reference condition' })
    await reference.selectOption('start')
    await reference.focus()
    await page.locator('.sim-playback-sidebar').evaluate(el => { el.scrollTop += 50 })
    await page.waitForTimeout(100)
    const scroll = await page.locator('.sim-playback-sidebar').evaluate(el => el.scrollTop)
    await page.waitForTimeout(250)
    assert.equal(await page.locator('.sim-playback-sidebar').evaluate(el => el.scrollTop), scroll, 'playback must not repeatedly reveal the active target')
    const target = await page.locator('[data-tutorial="reference"]').boundingBox()
    const highlight = await page.locator('.sim-tutorial-highlight').boundingBox()
    assert.ok(Math.abs(highlight.y - (target.y - 4)) < 2)
    assert.equal(await reference.evaluate(el => el === document.activeElement), true)
    await page.setViewportSize({ width: 1100, height: 700 })
    await page.waitForTimeout(100)
    const box = await tour.boundingBox()
    assert.ok(box.x >= 0 && box.x + box.width <= 1100 && box.y >= 0 && box.y + box.height <= 700)
  } finally { await browser.close() }
})

test('static mode explains its separation from submitted results', { skip: !process.env.SIMENV_STATIC_WEB_URL }, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await page.goto(process.env.SIMENV_STATIC_WEB_URL)
    const tour = page.getByRole('region', { name: 'Interactive tutorial' })
    await tour.waitFor()
    for (let i = 0; i < 4; i++) await tour.getByRole('button', { name: 'Next', exact: true }).click()
    assert.match(await tour.innerText(), /Static demo: separate from submitted runs/)
    await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
    assert.match(await tour.innerText(), /Statische Demo: keine Verbindung/)
  } finally { await browser.close() }
})

async function assertPointerReachable(locator) {
  await locator.page().waitForFunction(element => {
    const r = element.getBoundingClientRect()
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
    return r.top >= 0 && r.bottom <= innerHeight + 1 && (hit === element || element.contains(hit))
  }, await locator.elementHandle())
}

for (const viewport of [{ width: 844, height: 390 }, { width: 320, height: 568 }]) {
  for (const language of ['en', 'de']) {
    test(`short-screen controls remain pointer reachable ${viewport.width}x${viewport.height} ${language}`, async () => {
      const { browser, page, tour } = await setup(viewport)
      try {
        await page.getByRole('region', { name: 'Component status' }).waitFor()
        if (language === 'de') await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
        const next = tour.getByRole('button', { name: language === 'de' ? 'Weiter' : 'Next', exact: true })
        await assertPointerReachable(page.getByRole('textbox', { name: 'Scenario name' }))
        await next.click()
        for (const label of ['Brazil drought loss', 'Drought duration', 'Drought start day']) {
          const slider = page.getByRole('slider', { name: label })
          await assertPointerReachable(slider)
          await slider.click()
        }
        await next.click()
        await assertPointerReachable(page.getByRole('button', { name: 'Run simulation', exact: true }))
        await next.click()
        await next.click()
        for (const name of ['Recorded run', 'Recorded scenario']) {
          await assertPointerReachable(page.getByRole('combobox', { name, exact: true }))
        }
        await assertPointerReachable(page.getByRole('button', { name: 'Refresh runs', exact: true }))
        await next.click()
        const pause = page.getByRole('button', { name: 'Pause', exact: true })
        await assertPointerReachable(pause)
        await pause.click()
        const seek = page.getByRole('slider', { name: 'Simulation step' })
        await assertPointerReachable(seek)
        await seek.click()
        await page.getByRole('button', { name: 'Play', exact: true }).waitFor()
        await next.click()
        const reference = page.getByRole('combobox', { name: 'Reference condition' })
        await assertPointerReachable(reference)
        await reference.selectOption('start')
        await next.click()
        const component = page.getByRole('combobox', { name: 'Inspect component' })
        await assertPointerReachable(component)
        await component.selectOption('brazil_farms')
        await page.keyboard.press('Escape')
        const restart = page.getByRole('button', { name: 'Restart tutorial', exact: true })
        assert.equal(await restart.evaluate(el => el === document.activeElement), true, 'dismissal returns focus to header restart')
        await restart.scrollIntoViewIfNeeded()
        await assertPointerReachable(restart)
        assert.equal(await restart.evaluate(el => {
          const header = el.closest('.sim-frame-heading')
          if (!header) return false
          const text = header.querySelector('.sim-frame-subtitle').getBoundingClientRect()
          const button = el.getBoundingClientRect()
          const controls = document.querySelector('.sim-playback-sidebar').getBoundingClientRect()
          return text.bottom <= button.top && button.bottom <= header.getBoundingClientRect().bottom && header.getBoundingClientRect().bottom <= controls.top
        }), true, 'restart follows heading text before narrow/short flow controls')
        await restart.click()
        await tour.getByRole('heading', { name: language === 'de' ? 'Szenario benennen' : 'Name your scenario' }).waitFor()
        assert.equal(await tour.getByRole('heading').evaluate(el => el === document.activeElement), true)
        await assertPointerReachable(page.getByRole('textbox', { name: 'Scenario name' }))
        await page.keyboard.press('Escape')
        assert.equal(await restart.evaluate(el => el === document.activeElement), true)
      } finally { await browser.close() }
    })
  }
}

test('orientation reveals an inaccessible active target once without overriding subsequent user scrolling or collapse', async () => {
  const { browser, page, tour } = await setup({ width: 390, height: 844 })
  try {
    const name = page.getByRole('textbox', { name: 'Scenario name' })
    await assertPointerReachable(name)
    await page.setViewportSize({ width: 844, height: 390 })
    await assertPointerReachable(name)
    await name.fill('After rotation')
    const app = page.locator('.sim-app')
    await app.evaluate(el => { el.scrollTop = 0 })
    await page.waitForTimeout(400)
    assert.equal(await app.evaluate(el => el.scrollTop), 0, 'playback updates must respect deliberate scrolling')
    await page.setViewportSize({ width: 844, height: 420 })
    await page.waitForTimeout(250)
    assert.equal(await app.evaluate(el => el.scrollTop), 0, 'resize must not reclaim a target the user deliberately scrolled away from')
    await page.getByRole('button', { name: 'Hide', exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(200)
    assert.equal(await page.getByRole('button', { name: 'Open', exact: true }).getAttribute('aria-expanded'), 'false')
    await tour.getByRole('status').waitFor()
  } finally { await browser.close() }
})

for (const height of [600, 700]) {
  for (const language of ['en', 'de']) {
    test(`docked run selection remains operable after resize to 1200x${height} ${language}`, async () => {
      const { browser, page, tour } = await setup({ width: 844, height: 390 })
      try {
        await page.getByRole('region', { name: 'Component status' }).waitFor()
        if (language === 'de') await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
        for (let i = 0; i < 4; i++) {
          await tour.getByRole('button', { name: language === 'de' ? 'Weiter' : 'Next', exact: true }).click()
        }
        const scenario = page.getByRole('combobox', { name: 'Recorded scenario', exact: true })
        await assertPointerReachable(scenario)
        await page.setViewportSize({ width: 1200, height })
        await assertPointerReachable(scenario)
        await scenario.click()
        await page.keyboard.press('Home')
        await page.keyboard.press('Enter')
        assert.equal(await scenario.inputValue(), '0')
        await tour.getByRole('heading', { name: language === 'de' ? 'Aufzeichnung auswählen' : 'Choose recorded playback' }).waitFor()
      } finally { await browser.close() }
    })
  }
}
