import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { dismissInitialTutorial } from './browser-setup.mjs'
import { origin, webUrl, run, scene, page as frames } from './playback-fixtures.mjs'

test('frontend creates one empty-events reference, waits for playable data and reuses it', async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await dismissInitialTutorial(page)
    const source = { pdl: { scenario: { name: 'Disturbed' }, entities: [], events: [{ id: 'drought' }],
      cascades: [{ id: 'soy_crisis_cascade', timeline: [{ at: 0, event: 'drought' }] }] }, roster: { economics: { example: 1 } },
      cascade: 'soy_crisis_cascade', parameters: { period_num: 300, farm_size_seed: 42 },
      current_parameters: { period_num: 300, farm_size_seed: 42 }, evidence: 'execution-hashes' }
    let posted = null, complete = false, published = false, submissions = 0
    const job = id => ({ id, status: id === 'reference' && !complete ? 'running' : 'completed', label: id, error: null,
      progress: { scenario_id: 1, step: 300, scenario_total_steps: 300, completed_steps: 300, total_steps: 300, percent_complete: 100 } })
    await page.route('**/api/simulations**', route => {
      const url = new URL(route.request().url())
      if (route.request().method() === 'POST') {
        posted = route.request().postDataJSON(); submissions++
        return route.fulfill({ status: 202, json: job('reference') })
      }
      if (url.pathname.endsWith('/inputs')) {
        const ref = url.pathname.includes('/reference/')
        return route.fulfill({ json: ref ? { ...source, pdl: JSON.parse(posted.pdl), roster: JSON.parse(posted.roster), cascade: posted.cascade } : source })
      }
      if (url.pathname.endsWith('/reference')) return route.fulfill({ json: job('reference') })
      return route.fulfill({ json: { items: [job('shock'), job('second'), ...(posted ? [job('reference')] : [])], total: posted ? 3 : 2 } })
    })
    await page.route(`${origin}/**`, route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/runs') return route.fulfill({ json: { items: [
        { ...run('shock'), scenario_ids: [1] }, { ...run('second'), scenario_ids: [1] }, ...(published ? [{ ...run('reference'), scenario_ids: [1] }] : []),
      ], total: published ? 3 : 2 } })
      const [, , id, , scenario, kind] = url.pathname.split('/')
      if (kind === 'scene') return route.fulfill({ json: scene(id, Number(scenario)) })
      const result = frames(id, Number(scenario), Number(url.searchParams.get('start')))
      for (const frame of result.frames) frame.agents[0].values = { unit_price: 100, quantity_available: id === 'reference' ? 100 : 50, active: 1 }
      return route.fulfill({ json: result })
    })
    await page.goto(webUrl)
    const reference = page.getByRole('combobox', { name: 'Reference condition' })
    assert.equal(await reference.inputValue(), 'auto')
    await page.waitForFunction(() => document.querySelector('[aria-label="Reference comparison"]')?.textContent.includes('running'))
    assert.equal(submissions, 1)
    assert.deepEqual(JSON.parse(posted.pdl).events, [])
    assert.deepEqual(JSON.parse(posted.pdl).cascades, [{ id: 'unshocked_reference', timeline: [] }])
    assert.deepEqual(JSON.parse(posted.roster), source.roster)
    assert.equal(await page.getByRole('region', { name: 'Component status' }).count(), 0, 'no start-relative comparison while preparing')
    if (process.env.SIMENV_CAPTURE_BASELINE) await page.screenshot({ path: '../docs/automatic-reference-preparing.png' })
    // Remount the selected playback while its accepted job continues in the
    // source-scoped coordinator. StrictMode is also active in the real app.
    await page.getByRole('combobox', { name: 'Recorded run', exact: true }).selectOption('second')
    complete = true
    await page.getByText(/awaiting playback/i).waitFor()
    assert.equal(await page.getByRole('region', { name: 'Component status' }).count(), 0)
    published = true
    await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    assert.equal(await page.getByRole('combobox', { name: 'Recorded run', exact: true }).inputValue(), 'second', 'late baseline completion must not replace the selected run')
    await page.getByRole('button', { name: 'Pause', exact: true }).click()
    await page.getByRole('slider', { name: 'Simulation step' }).fill('0')
    await page.waitForFunction(() => document.querySelector('[aria-label="Component status"]')?.dataset.period === '0')
    assert.match(await page.getByRole('region', { name: 'Component status' }).innerText(), /Supply availability down 50%/)
    if (process.env.SIMENV_CAPTURE_BASELINE) {
      await page.screenshot({ path: '../docs/automatic-reference-ready.png' })
      await page.locator('.sim-playback-sidebar').evaluate(sidebar => {
        sidebar.scrollTop += sidebar.querySelector('[aria-label="Component status"]').getBoundingClientRect().top - sidebar.getBoundingClientRect().top - 12
      })
      await page.screenshot({ path: '../docs/automatic-reference-details.png' })
    }
    await page.reload()
    await page.getByRole('region', { name: 'Component status' }).getByText('Supply availability down 50%', { exact: true }).first().waitFor()
    assert.equal(submissions, 1, 'verified recorded baseline is reused after reload')
    const cascade = page.getByRole('combobox', { name: 'Active cascade' })
    assert.equal(await cascade.inputValue(), 'soy_crisis_cascade')
    assert.equal(await cascade.isDisabled(), true)
  } finally { await browser.close() }
})
