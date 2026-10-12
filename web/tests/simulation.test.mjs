import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

// Acceptance test against a running frontend and the real PR #50 API.
// No local API mock is shipped. Each case creates a real simulation job.
const completionTimeout = Number(process.env.SIMENV_TEST_TIMEOUT_MS || 120000)
assert.ok(Number.isFinite(completionTimeout) && completionTimeout > 0, 'SIMENV_TEST_TIMEOUT_MS must be positive')

test('configurator executes its edited documents and tracks both cascades', { timeout: completionTimeout * 2 + 30000 }, async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
    await page.goto(process.env.SIMENV_WEB_URL || 'http://127.0.0.1:5173')
    const run = page.getByRole('button', { name: 'Run simulation', exact: true })
    await run.waitFor()

    for (const cascade of ['soy_crisis_cascade', 'energy_food_cascade']) {
      await page.getByRole('combobox', { name: 'Active cascade' }).selectOption(cascade)
      const label = `Browser acceptance ${cascade}`
      await page.getByRole('textbox', { name: 'Scenario name' }).fill(label)
      if (cascade === 'soy_crisis_cascade') {
        await page.getByRole('slider', { name: 'Brazil drought loss' }).fill('55')
        await page.getByRole('checkbox', { name: 'US emergency supply' }).uncheck()
      } else {
        await page.getByRole('slider', { name: 'Gas price increase' }).fill('300')
      }
      const pdl = await page.locator('textarea').nth(0).inputValue()
      const roster = await page.locator('textarea').nth(1).inputValue()
      if (cascade === 'soy_crisis_cascade') {
        assert.match(pdl, /supply: "-55%"/)
        assert.doesNotMatch(pdl, /id: us_supply_activated/)
      } else {
        assert.match(pdl, /price: "\+300%"/)
      }

      const responsePromise = page.waitForResponse(response =>
        new URL(response.url()).pathname.endsWith('/simulations') && response.request().method() === 'POST',
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
      const status = page.getByRole('status')
      assert.match(await status.innerText(), new RegExp(label))
      assert.match(await status.innerText(), /completed/)
      assert.match(await status.innerText(), /730\/730 total steps/)
      assert.equal(await page.getByRole('progressbar').getAttribute('value'), '100')
    }
  } finally {
    await browser.close()
  }
})
