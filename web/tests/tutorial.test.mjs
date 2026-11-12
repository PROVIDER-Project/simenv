import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockPlayback, webUrl, origin, run } from './playback-fixtures.mjs'

const stepIds = ['scenario', 'disruption', 'execution', 'results', 'runs', 'timeline', 'speed', 'stepping', 'reference', 'component', 'indicators']

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

test('restart shares the title row at the configurator gutter', async () => {
  const { browser, page } = await setup()
  try {
    await page.keyboard.press('Escape')
    const boxes = await page.evaluate(() => {
      const box = selector => {
        const r = document.querySelector(selector).getBoundingClientRect()
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }
      }
      return { title: box('.sim-frame-heading h1'), header: box('.sim-frame-heading'),
        restart: box('.sim-tutorial-restart'), configurator: box('.sim-configurator'), subtitle: box('.sim-frame-subtitle') }
    })
    assert.ok(boxes.restart.top < boxes.title.bottom && boxes.title.top < boxes.restart.bottom, 'restart must share the title row')
    assert.ok(boxes.title.right <= boxes.restart.left, 'restart must not overlap the title')
    assert.ok(Math.abs(boxes.restart.right - boxes.header.right) <= 1, 'restart is anchored to the center header right edge')
    assert.ok(Math.abs(boxes.configurator.left - boxes.restart.right - 16) <= 1, 'preserve the configurator gutter')
    assert.ok(boxes.subtitle.top >= Math.max(boxes.title.bottom, boxes.restart.bottom), 'subtitle remains below the title row')
  } finally { await browser.close() }
})

test('heading keeps accessible entry focus without a textbox outline; buttons retain keyboard outlines', async () => {
  const { browser, page, tour } = await setup()
  try {
    await tour.waitFor()
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Restart tutorial', exact: true }).press('Enter')
    const heading = tour.getByRole('heading', { name: 'Name your scenario', exact: true })
    assert.equal(await heading.evaluate(el => el === document.activeElement), true)
    assert.equal(await heading.evaluate(el => getComputedStyle(el).outlineStyle), 'none')
    const next = tour.getByRole('button', { name: 'Next', exact: true })
    await next.focus()
    assert.equal(await next.evaluate(el => getComputedStyle(el).outlineStyle), 'solid')
    await next.press('Enter')
    assert.equal(await tour.getByRole('heading').evaluate(el => el === document.activeElement), true)
    assert.equal(await tour.getByRole('heading').evaluate(el => getComputedStyle(el).outlineStyle), 'none')
    await page.keyboard.press('Escape')
    const restart = page.getByRole('button', { name: 'Restart tutorial', exact: true })
    assert.equal(await restart.evaluate(el => el === document.activeElement), true)
    assert.equal(await restart.evaluate(el => getComputedStyle(el).outlineStyle), 'solid')
  } finally { await browser.close() }
})

const guidanceViews = [{ width: 1440, height: 1000 }, { width: 320, height: 568 }, { width: 844, height: 390 }]
for (const { viewport, language } of guidanceViews.flatMap(viewport => ['en', 'de'].map(language => ({ viewport, language })))) {
  test(`speed and stepping guidance follow timeline without changing playback ${viewport.width}x${viewport.height} ${language}`, async () => {
    const { browser, page, tour } = await setup(viewport)
    try {
      await tour.waitFor()
      if (language === 'de') await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
      const next = tour.getByRole('button', { name: language === 'de' ? 'Weiter' : 'Next', exact: true })
      await moveTo(tour, 'timeline', language)
      await page.getByRole('button', { name: 'Pause', exact: true }).click()
      const seek = page.getByRole('slider', { name: 'Simulation step' })
      await seek.fill('121')
      await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]').value === '121')
      await next.click()
      await assertStep(tour, 'speed')
      assert.equal(await tour.getByRole('heading').innerText(), language === 'de' ? 'Wiedergabegeschwindigkeit ändern' : 'Change playback speed')
      assert.match(await tour.innerText(), language === 'de' ? /0,25×.*0,5×.*1×.*2×.*4×/ : /0\.25×.*0\.5×.*1×.*2×.*4×/)
      await assertTargetReachable(page, 'speed')
      await next.click()
      await assertStep(tour, 'stepping')
      assert.equal(await tour.getByRole('heading').innerText(), language === 'de' ? 'Einzelne Schritte prüfen' : 'Inspect one step at a time')
      await assertTargetReachable(page, 'stepping')
      assert.equal(await seek.inputValue(), '121', 'tour entry must not seek')
      assert.equal(await page.getByRole('button', { name: 'Play', exact: true }).count(), 1, 'tour entry must not resume playback')
      assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'first')
      await next.click()
      assert.equal(await tour.getByRole('heading').innerText(), language === 'de' ? 'Referenz und Legende verstehen' : 'Understand the reference and legend')
    } finally { await browser.close() }
  })
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
    await moveTo(tour, 'indicators', 'de')
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
      for (const id of stepIds) {
        await moveTo(tour, id)
        const box = await tour.boundingBox()
        assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1)
        if (id === 'runs') {
          assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).evaluate(el => {
            const r = el.getBoundingClientRect()
            return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) === el
          }), true, 'restart control must not cover recorded scenario selection')
        }
        if (id === 'timeline') {
          await page.getByRole('button', { name: 'Pause', exact: true }).click()
          await page.getByRole('slider', { name: 'Simulation step' }).fill('121')
          await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]').value === '121')
        }
        if (id === 'component') {
          const selector = page.getByRole('combobox', { name: 'Inspect component' })
          await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
          await selector.waitFor()
          assert.equal(await selector.evaluate(el => {
            const r = el.getBoundingClientRect()
            const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
            return el === hit || el.contains(hit)
          }), true, 'component selector must remain reachable beside the popover')
        }
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
    await moveTo(tour, 'results')
    await tour.getByRole('status').waitFor()
    assert.equal(submissions, 0, 'tour navigation never submits a simulation')
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
    await page.getByRole('button', { name: 'View results', exact: true }).waitFor()
    await assertStep(tour, 'results')
    await page.waitForFunction(() => !document.querySelector('.sim-tutorial [role="status"]'))
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('[aria-label="Recorded run"]').value === 'second')
    await tour.getByRole('heading', { name: 'Choose recorded playback' }).waitFor()
    assert.equal(submissions, 1)
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('first')
    await tour.getByRole('heading', { name: 'Choose recorded playback' }).waitFor()
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    await moveTo(tour, 'timeline')
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
    await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]').value === '250')
    await page.getByRole('button', { name: 'Hide disturbance impact' }).click()
    await moveTo(tour, 'reference')
    assert.equal(await page.getByRole('button', { name: 'Hide disturbance impact' }).getAttribute('aria-expanded'), 'true')
    await page.getByRole('combobox', { name: 'Reference condition' }).selectOption('start')
    await moveTo(tour, 'component')
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
    await moveTo(tour, 'runs')
    assert.equal(await page.getByRole('button', { name: 'Hide playback selection' }).getAttribute('aria-expanded'), 'true')
    await page.getByRole('button', { name: 'Hide playback selection' }).click()
    await page.waitForTimeout(200)
    assert.equal(await page.getByRole('button', { name: 'Show playback selection' }).getAttribute('aria-expanded'), 'false', 'tour must allow users to collapse the panel again')
    await moveTo(tour, 'reference')
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
    await moveTo(tour, 'runs')
    assert.match(await tour.innerText(), /Static demo: separate from submitted runs/)
    await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
    assert.match(await tour.innerText(), /Statische Demo: keine Verbindung/)
  } finally { await browser.close() }
})

async function assertPointerReachable(locator) {
  await locator.page().waitForFunction(element => {
    const r = element.getBoundingClientRect()
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
    return r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1 && (hit === element || element.contains(hit))
  }, await locator.elementHandle())
}

async function assertTargetHighlighted(page, id) {
  try {
    await page.waitForFunction(id => {
      const target = document.querySelector(`[data-tutorial="${id}"]`)
      const highlight = document.querySelector('.sim-tutorial-highlight')
      if (!target || !highlight) return false
      const r = target.getBoundingClientRect(), h = highlight.getBoundingClientRect()
      const app = document.querySelector('.sim-app').getBoundingClientRect()
      const card = document.querySelector('.sim-tutorial').getBoundingClientRect()
      const overlapsCard = r.left < card.right && card.left < r.right && r.top < card.bottom && card.top < r.bottom
      return r.top >= app.top - 1 && r.bottom <= innerHeight + 1 && !overlapsCard
        && Math.abs(h.x - (r.x - 4)) < 2 && Math.abs(h.y - (r.y - 4)) < 2
        && Math.abs(h.width - (r.width + 8)) < 2 && Math.abs(h.height - (r.height + 8)) < 2
    }, id)
  } catch (error) {
    const geometry = await page.evaluate(id => {
      const rect = element => {
        if (!element) return null
        const r = element.getBoundingClientRect()
        return { x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom }
      }
      const target = document.querySelector(`[data-tutorial="${id}"]`)
      return { step: document.querySelector('.sim-tutorial')?.getAttribute('data-step'),
        target: rect(target), highlight: rect(document.querySelector('.sim-tutorial-highlight')),
        app: rect(document.querySelector('.sim-app')), card: rect(document.querySelector('.sim-tutorial')),
        docked: !!document.querySelector('.sim-tutorial-shell--docked'),
        controls: [...(target?.querySelectorAll('input, button') ?? [])].map(element => {
          const r = element.getBoundingClientRect()
          const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
          return { bounds: rect(element), pointerReachable: hit === element || element.contains(hit) }
        }) }
    }, id)
    error.message += `\nTutorial target ${id}: ${JSON.stringify(geometry)}`
    throw error
  }
}

async function assertTargetReachable(page, id) {
  await assertTargetHighlighted(page, id)
  const buttons = page.locator(`[data-tutorial="${id}"] button`)
  assert.equal(await buttons.count(), 2, `${id} highlights its two controls`)
  for (const button of await buttons.all()) await assertPointerReachable(button)
}

const completedJob = { id: 'second', label: 'Submitted example', status: 'completed', error: null,
  progress: { scenario_id: 1, step: 300, scenario_total_steps: 300, completed_steps: 300, total_steps: 300, percent_complete: 100 } }
const queuedJob = { ...completedJob, status: 'queued', progress: { scenario_id: null, step: 0, scenario_total_steps: 300, completed_steps: 0, total_steps: 300, percent_complete: 0 } }

async function moveTo(tour, step, language = 'en') {
  await tour.waitFor()
  const current = stepIds.indexOf(await tour.getAttribute('data-step'))
  const target = stepIds.indexOf(step)
  assert.ok(current >= 0 && target >= 0, `known tutorial step: ${step}`)
  for (let i = current; i < target; i++) {
    await tour.getByRole('button', { name: language === 'de' ? 'Weiter' : 'Next', exact: true }).click()
    await assertStep(tour, stepIds[i + 1])
  }
  for (let i = current; i > target; i--) {
    await tour.getByRole('button', { name: language === 'de' ? 'Zurück' : 'Back', exact: true }).click()
    await assertStep(tour, stepIds[i - 1])
  }
}
async function assertStep(tour, step) {
  await tour.page().locator(`.sim-tutorial[data-step="${step}"]`).waitFor()
  assert.equal(await tour.locator('.sim-tutorial-bar > span').innerText(), `${stepIds.indexOf(step) + 1} / ${stepIds.length}`)
}
async function prepareCompleted(page) {
  await page.route('**/api/simulations', route => route.fulfill({ status: 202, json: completedJob }))
  const refreshed = page.waitForResponse(response => response.url().startsWith(`${origin}/runs`))
  await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
  await refreshed
  await page.getByRole('button', { name: 'View results', exact: true }).waitFor()
}
async function holdResponse(page, url, json) {
  let release, entered
  const gate = new Promise(resolve => { release = resolve })
  const started = new Promise(resolve => { entered = resolve })
  await page.route(url, async route => { entered(); await gate; await route.fulfill({ json }) })
  return { started, release }
}

for (const language of ['en', 'de']) {
  test(`accepted queued execution and successful exact View results each advance once ${language}`, async () => {
    const { browser, page, tour } = await setup()
    try {
      if (language === 'de') await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
      await moveTo(tour, 'execution', language)
      let submissions = 0
      await page.route('**/api/simulations', route => { submissions++; return route.fulfill({ status: 202, json: queuedJob }) })
      const poll = await holdResponse(page, '**/api/simulations/second', completedJob)
      await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
      await assertStep(tour, 'results')
      assert.match(await page.getByRole('region', { name: 'Simulation execution' }).innerText(), /queued/)
      await poll.started
      poll.release()
      await page.getByRole('button', { name: 'View results', exact: true }).waitFor()
      await assertStep(tour, 'results')
      await page.getByRole('button', { name: 'View results', exact: true }).click()
      await assertStep(tour, 'runs')
      assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'second')
      assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).inputValue(), '1')
      assert.equal(submissions, 1)
    } finally { await browser.close() }
  })
}

test('failed execution and results stay on their steps; successful retries advance', async () => {
  const { browser, page, tour } = await setup()
  try {
    await moveTo(tour, 'execution')
    await page.route('**/api/simulations', route => route.fulfill({ status: 503, json: { detail: 'Submission unavailable' } }))
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'Submission unavailable' }).waitFor()
    await assertStep(tour, 'execution')
    await prepareCompleted(page)
    await assertStep(tour, 'results')
    await page.route(`${origin}/runs?*`, route => route.fulfill({ status: 503, json: { detail: 'Results unavailable' } }))
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await page.getByRole('alert').waitFor()
    await assertStep(tour, 'results')
    await page.unroute(`${origin}/runs?*`)
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await assertStep(tour, 'runs')
  } finally { await browser.close() }
})

for (const action of ['execution', 'results']) {
  for (const navigation of ['next', 'revisit', 'restart', 'close', 'finish', 'outside']) {
    test(`pending ${action} cannot advance after ${navigation}`, async () => {
      const { browser, page, tour } = await setup()
      try {
        const step = stepIds.indexOf(action)
        if (action === 'results') await prepareCompleted(page)
        await moveTo(tour, stepIds[navigation === 'outside' ? step - 1 : step])
        const pending = await holdResponse(page, action === 'execution' ? '**/api/simulations' : `${origin}/runs?*`, action === 'execution' ? completedJob : { items: [run('first'), run('second')], total: 2 })
        const button = page.getByRole('button', { name: action === 'execution' ? 'Run simulation' : 'View results', exact: true })
        // Keyboard activation also exercises actions outside the highlighted step.
        await button.focus(); await button.press('Enter')
        await pending.started
        await assertStep(tour, stepIds[navigation === 'outside' ? step - 1 : step])
        let expected = step
        if (navigation === 'outside') await moveTo(tour, action)
        else if (navigation === 'next') { await moveTo(tour, stepIds[step + 1]); expected++ }
        else if (navigation === 'revisit') { await moveTo(tour, stepIds[step - 1]); await moveTo(tour, action) }
        else if (navigation === 'restart') {
          await page.getByRole('button', { name: 'Restart tutorial', exact: true }).focus()
          await page.getByRole('button', { name: 'Restart tutorial', exact: true }).press('Enter')
          await moveTo(tour, action)
        } else if (navigation === 'finish') {
          await moveTo(tour, 'indicators')
          await tour.getByRole('button', { name: 'Finish', exact: true }).click()
        } else await tour.getByRole('button', { name: 'Close for session', exact: true }).click()
        pending.release()
        await page.getByRole('button', { name: 'View results', exact: true }).waitFor()
        if (action === 'results') await page.waitForFunction(() => document.querySelector('[aria-label="Recorded run"]').value === 'second')
        if (navigation === 'close' || navigation === 'finish') assert.equal(await tour.count(), 0)
        else await assertStep(tour, stepIds[expected])
      } finally { await browser.close() }
    })
  }
}

test('results superseded by manual recorded run selection do not advance', async () => {
  const { browser, page, tour } = await setup()
  try {
    await prepareCompleted(page)
    await moveTo(tour, 'results')
    const pending = await holdResponse(page, `${origin}/runs?*`, { items: [run('first'), run('second')], total: 2 })
    await page.getByRole('button', { name: 'View results', exact: true }).click()
    await pending.started
    const selector = page.getByRole('combobox', { name: 'Recorded run', exact: true })
    await selector.focus(); await selector.selectOption('second')
    pending.release()
    // Aborting the real fetch rejects before App's post-fetch selection check.
    await page.getByRole('alert').waitFor()
    await assertStep(tour, 'results')
    assert.equal(await selector.inputValue(), 'second')
  } finally { await browser.close() }
})

test('job polling completion never advances execution entered after submission', async () => {
  const { browser, page, tour } = await setup()
  try {
    await moveTo(tour, 'disruption')
    await page.route('**/api/simulations', route => route.fulfill({ status: 202, json: queuedJob }))
    const poll = await holdResponse(page, '**/api/simulations/second', completedJob)
    const button = page.getByRole('button', { name: 'Run simulation', exact: true })
    await button.focus(); await button.press('Enter')
    await poll.started
    await moveTo(tour, 'execution')
    poll.release()
    await page.getByRole('button', { name: 'View results', exact: true }).waitFor()
    await assertStep(tour, 'execution')
  } finally { await browser.close() }
})

for (const language of ['en', 'de']) {
  test(`dock recovery waits for the committed layout ${language}`, async () => {
    const browser = await chromium.launch({ headless: true })
    try {
      const page = await browser.newPage({ viewport: { width: 844, height: 390 } })
      page.setDefaultTimeout(5000)
      await mockPlayback(page, { tutorial: true })
      await page.addInitScript(() => {
        const nativeFrame = requestAnimationFrame.bind(window)
        window.tutorialEarlyFrames = 0
        window.requestAnimationFrame = callback => {
          const title = document.querySelector('.sim-tutorial h2')?.textContent
          // Reproduce two tutorial measurements before React commits the dock,
          // rather than relying on machine load to produce that ordering.
          if (callback.name === 'update' && ['Shape the disruption', 'Störung gestalten'].includes(title) && window.tutorialEarlyFrames < 2) {
            window.tutorialEarlyFrames++
            callback(performance.now())
            return 0
          }
          return nativeFrame(callback)
        }
      })
      await page.goto(webUrl)
      await page.getByRole('region', { name: 'Component status' }).waitFor()
      const tour = page.getByRole('region', { name: 'Interactive tutorial' })
      if (language === 'de') await tour.getByRole('button', { name: 'Deutsch', exact: true }).click()
      await assertPointerReachable(page.getByRole('textbox', { name: 'Scenario name' }))
      await tour.getByRole('button', { name: language === 'de' ? 'Weiter' : 'Next', exact: true }).click()
      assert.equal(await page.evaluate(() => window.tutorialEarlyFrames), 2, 'exercise both pre-commit measurements')
      await assertTargetHighlighted(page, 'disruption')
      for (const name of ['Brazil drought loss', 'Drought duration', 'Drought start day']) {
        const slider = page.getByRole('slider', { name })
        await assertPointerReachable(slider)
        await slider.click()
      }
      // Recovery is one-shot: it must still respect a subsequent deliberate scroll.
      await page.locator('.sim-app').evaluate(el => { el.scrollTop = 0 })
      await page.waitForTimeout(250)
      assert.equal(await page.locator('.sim-app').evaluate(el => el.scrollTop), 0)
    } finally { await browser.close() }
  })
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
        await assertTargetHighlighted(page, 'disruption')
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
        await moveTo(tour, 'reference', language)
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
          const title = header.querySelector('h1').getBoundingClientRect()
          const subtitle = header.querySelector('.sim-frame-subtitle').getBoundingClientRect()
          const button = el.getBoundingClientRect()
          const controls = document.querySelector('.sim-playback-sidebar').getBoundingClientRect()
          const bounds = header.getBoundingClientRect()
          return title.right <= button.left && title.top < button.bottom && button.top < title.bottom
            && Math.abs(button.right - bounds.right) <= 1 && subtitle.top >= Math.max(title.bottom, button.bottom)
            && bounds.bottom <= controls.top
        }), true, 'restart shares the title row before narrow/short flow controls')
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
        await moveTo(tour, 'runs', language)
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
