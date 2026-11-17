import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { dismissInitialTutorial } from './browser-setup.mjs'

// Acceptance test against a running frontend and the real PR #50 API.
// No local API mock is shipped. Each case creates a real simulation job.
const completionTimeout = Number(process.env.SIMENV_TEST_TIMEOUT_MS || 120000)
assert.ok(Number.isFinite(completionTimeout) && completionTimeout > 0, 'SIMENV_TEST_TIMEOUT_MS must be positive')

test('soy workshop executes edited documents and reuses its frontend-managed unshocked reference', { timeout: completionTimeout * 3 + 30000 }, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
    await dismissInitialTutorial(page)
    const baselinePosts = []
    page.on('request', request => {
      if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/simulations') && request.postDataJSON()?.cascade === 'unshocked_reference') baselinePosts.push(request.postDataJSON())
    })
    await page.goto(process.env.SIMENV_WEB_URL || 'http://127.0.0.1:5173')
    const run = page.getByRole('button', { name: 'Run simulation', exact: true })
    await run.waitFor()

    let referenceId
    for (const loss of [55, 65]) {
      const cascade = 'soy_crisis_cascade'
      const activeCascade = page.getByRole('combobox', { name: 'Active cascade' })
      assert.equal(await activeCascade.isDisabled(), true)
      assert.equal(await activeCascade.inputValue(), cascade)
      const label = `Browser acceptance soy loss ${loss}`
      await page.getByRole('textbox', { name: 'Scenario name' }).fill(label)
      await page.getByRole('slider', { name: 'Brazil drought loss' }).fill(String(loss))
      await page.getByRole('checkbox', { name: 'US emergency supply' }).uncheck()
      const pdl = await page.locator('textarea').nth(0).inputValue()
      const roster = await page.locator('textarea').nth(1).inputValue()
      assert.match(pdl, new RegExp(`supply: "-${loss}%"`))
      assert.doesNotMatch(pdl, /id: us_supply_activated/)

      const responsePromise = page.waitForResponse(response =>
        new URL(response.url()).pathname.endsWith('/simulations') && response.request().method() === 'POST' && response.request().postDataJSON()?.label === label,
      )
      await run.click()
      assert.equal(await run.isDisabled(), true)
      const response = await responsePromise
      const job = await response.json()
      assert.equal(response.status(), 202, JSON.stringify(job))
      assert.deepEqual(response.request().postDataJSON(), { pdl, roster, cascade, label })
      await page.getByText(job.id, { exact: true }).waitFor()
      await page.getByRole('textbox', { name: 'Scenario name' }).fill('Edits for the next run')
      const hiddenPoll = page.waitForResponse(response =>
        new URL(response.url()).pathname.endsWith(`/simulations/${job.id}`) && response.request().method() === 'GET',
      )
      await page.getByRole('button', { name: 'Hide', exact: true }).click()
      assert.equal((await hiddenPoll).status(), 200)
      await page.getByRole('button', { name: 'Open', exact: true }).click()
      await page.getByText('Results saved by the API.', { exact: false }).waitFor({ timeout: completionTimeout })
      assert.equal(await run.isEnabled(), true)
      const status = page.getByRole('region', { name: 'Simulation execution' }).getByRole('status')
      assert.match(await status.innerText(), new RegExp(label))
      assert.match(await status.innerText(), /completed/)
      assert.match(await status.innerText(), /365\/365 total steps/)
      assert.equal(await page.getByRole('progressbar').getAttribute('value'), '100')
      const recorded = page.getByRole('combobox', { name: 'Recorded run', exact: true })
      await page.getByRole('button', { name: 'View results', exact: true }).click()
      await page.waitForFunction(id => document.querySelector('[aria-label="Recorded run"]')?.value === id, job.id)
      assert.equal(await recorded.inputValue(), job.id)
      assert.equal(await page.getByRole('combobox', { name: 'Recorded scenario', exact: true }).inputValue(), '1')
      await page.getByRole('button', { name: 'Pause', exact: true }).click()
      await page.getByRole('region', { name: 'Component status' }).waitFor({ timeout: completionTimeout })
      assert.equal(await page.getByRole('combobox', { name: 'Reference condition' }).inputValue(), 'auto')
      const explanation = await page.getByRole('region', { name: 'Reference comparison' }).innerText()
      const match = explanation.match(/Recorded unshocked reference: ([^,]+), scenario 1/)
      assert.ok(match, explanation)
      if (referenceId) assert.equal(match[1], referenceId, 'second soy configuration reuses the same reference')
      referenceId = match[1]
      const saved = await page.request.get(new URL(`/api/simulations/${referenceId}/inputs`, page.url()).href)
      assert.equal(saved.status(), 200)
      const inputs = await saved.json()
      assert.deepEqual(inputs.pdl.events, [])
      assert.deepEqual(inputs.pdl.cascades, [{ id: 'unshocked_reference', timeline: [] }])
      const componentNames = await page.getByRole('combobox', { name: 'Inspect component' }).locator('option').allTextContents()
      assert.ok(componentNames.length > 0, 'completed scene exposes component names')
      assert.doesNotMatch(componentNames.join(' '), /Sojaanbau|Hafen |Ölmühlen|Futtermittelhersteller|Geflügelbetriebe|Schweinebetriebe|Milchwirtschaft/)
      const frames = page.waitForResponse(response =>
        response.url().includes(`/runs/${job.id}/scenarios/1/frames?start=200&limit=100`),
      )
      await page.getByRole('slider', { name: 'Simulation step' }).fill('250')
      assert.equal((await frames).status(), 200)
      await page.waitForFunction(() => document.querySelector('[aria-label="Simulation step"]')?.value === '250')
    }
    assert.ok(baselinePosts.length <= 1, 'at most one missing reference is submitted')
  } finally {
    await browser.close()
  }
})
