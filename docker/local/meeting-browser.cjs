const { chromium, expect } = require('@playwright/test')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    for (const [user, agent] of [['Administrator', false], ['dev2.sales.a@example.invalid', false], ['dev2.agent.a@example.invalid', true]]) {
      const context = await browser.newContext({ baseURL: 'http://127.0.0.1:18000' })
      await context.addInitScript(() => localStorage.setItem('crm_persona_captured', '1'))
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      const login = await context.request.post('/api/method/login', { form: { usr: user, pwd: 'Local-Dev2-Only-2026' } })
      expect(login.status()).toBe(200)
      await page.goto(agent ? '/crm-agent' : '/crm/appointments')
      if (!agent) {
        await expect(page.getByRole('button', { name: 'Book appointment', exact: true })).toBeEnabled()
        const onboarding = page.locator('div.fixed.z-50.right-0.w-80')
        if (await onboarding.isVisible()) await onboarding.locator(':scope > div').first().getByRole('button').last().click()
        await page.getByLabel('View', { exact: true }).selectOption('Schedule')
      }
      try {
        await page.getByRole('button', { name: agent ? 'Book meeting (no lead)' : 'Book appointment', exact: true }).click({ timeout: 30000 })
        const title = 'Visitor introduction ' + Date.now()
        await page.getByLabel('Appointment title', { exact: true }).fill(title)
        await page.getByLabel(agent ? /^Starts \(/ : 'Starts', { exact: !agent }).fill('2035-06-14T10:00')
        await page.getByLabel(agent ? /^Ends \(/ : 'Ends', { exact: !agent }).fill('2035-06-14T11:00')
        await page.getByLabel('Location or meeting URL').fill('Reception')
        await page.getByRole('button', { name: 'Save', exact: true }).click()
        const card = page.locator('article').filter({ hasText: title })
        await expect(card).toContainText('No lead yet')
        await card.getByRole('button', { name: 'Complete appointment', exact: true }).click()
        await card.getByRole('button', { name: 'Create lead from meeting', exact: true }).click()
        await page.getByLabel('First name', { exact: true }).fill('Introduced visitor')
        await page.getByLabel('Email', { exact: true }).fill('visitor@example.invalid')
        const converted = page.waitForResponse(response => response.url().includes(agent ? 'convert_appointment_to_lead' : 'convert_to_lead'))
        await page.getByRole('button', { name: 'Save', exact: true }).click()
        const response = await converted
        expect(response.status()).toBe(200)
        const result = (await response.json()).message
        expect(result.created).toBe(true)
        await expect(card.getByRole('button', { name: 'Open lead', exact: true })).toBeVisible()
        await expect(card).not.toContainText('No lead yet')
        if (!agent) {
          await card.getByRole('button', { name: 'Open lead', exact: true }).click()
          const activity = page.getByRole('article', { name: 'Appointment activity' }).filter({ hasText: title })
          await expect(activity).toContainText('Completed')
          await expect(activity).toContainText('Reception')
          await expect(page.getByRole('button', { name: 'Book appointment', exact: true })).toBeVisible()
          await page.getByRole('button', { name: 'Book appointment', exact: true }).click()
          await expect(page.getByRole('dialog')).toContainText(result.lead)
          const followupTitle = title + ' follow-up'
          await page.getByLabel('Appointment title', { exact: true }).fill(followupTitle)
          await page.getByLabel('Starts', { exact: true }).fill('2035-06-15T10:00')
          await page.getByLabel('Ends', { exact: true }).fill('2035-06-15T11:00')
          await page.getByRole('button', { name: 'Save', exact: true }).click()
          await page.getByLabel('View', { exact: true }).selectOption('Schedule')
          const followup = page.locator('article').filter({ hasText: followupTitle })
          await followup.getByRole('button', { name: 'Cancel appointment', exact: true }).click()
          await expect(followup).toContainText('Cancelled')
          await followup.getByRole('button', { name: 'Open lead', exact: true }).click()
          const followupActivity = page.getByRole('article', { name: 'Appointment activity' }).filter({ hasText: followupTitle })
          await expect(followupActivity).toContainText('Cancelled')
          await expect(followupActivity).toHaveCount(1)

        }
        expect(errors).toEqual([])
        console.log('PASS: ' + user + ' books an unlinked meeting, completes it and creates a linked lead')
      } catch (error) {
        console.log('URL:', page.url())
        console.log((await page.locator('body').innerText()).slice(0, 4500))
        throw error
      } finally { await context.close() }
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
