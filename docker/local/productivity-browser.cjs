const { chromium, expect } = require('@playwright/test')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    for (const [label, user, agent] of [['admin', 'Administrator', false], ['staff', 'dev2.sales.a@example.invalid', false], ['agent-a', 'dev2.agent.a@example.invalid', true]]) {
      const context = await browser.newContext({ baseURL: 'http://127.0.0.1:18000', viewport: { width: 1440, height: 1000 } })
      await context.addInitScript(() => localStorage.setItem('crm_persona_captured', '1'))
      expect((await context.request.post('/api/method/login', { form: { usr: user, pwd: 'Local-Dev2-Only-2026' } })).status()).toBe(200)
      const page = await context.newPage(), errors = []
      page.on('pageerror', error => errors.push(error.message))
      const method = agent ? 'crm.api.agent.my_day' : 'crm.api.productivity.my_day'
      const response = await context.request.get('/api/method/' + method)
      expect(response.status()).toBe(200)
      const data = (await response.json()).message
      const overdue = data.tasks.overdue.items.find(row => row.title === `My Day Browser ${label} overdue`)
      expect(overdue).toBeTruthy()
      for (const group of Object.values(data.tasks)) expect(group.items.some(row => row.title.includes('My Day Browser agent-b'))).toBe(false)
      await page.goto(agent ? '/crm-agent' : '/crm/my-day')
      if (agent) await page.getByRole('button', { name: 'My Day', exact: true }).click()
      const card = page.locator(`[data-task="${overdue.name}"]`)
      await expect(card).toContainText(overdue.title)
      await card.getByRole('button', { name: 'Mark done', exact: true }).click()
      await expect(card).toHaveCount(0)
      await expect(page.getByText(`My Day Browser ${label} today`, { exact: true })).toBeVisible()
      await expect(page.getByText(`My Day Browser ${label} meeting`, { exact: true })).toBeVisible()
      await expect(page.getByText('My Day Browser agent-b overdue', { exact: true })).toHaveCount(0)
      if (!agent) {
        const event = page.locator('[data-event]').filter({ hasText: `My Day Browser ${label} meeting` })
        await event.getByRole('button', { name: 'View appointment', exact: true }).click()
        await expect(page.locator('dialog[open]')).toContainText(`My Day Browser ${label} meeting`)
        await page.goto('/crm/my-day')
        await page.getByRole('button', { name: 'Book appointment', exact: true }).first().click()
        await expect(page.locator('dialog[open]')).toBeVisible()
        await page.goto('/crm/my-day')
        await expect(page.getByText('Your daily focus', { exact: true })).toBeVisible()
      } else {
        expect((await context.request.get('/api/method/crm.api.productivity.my_day')).status()).toBe(403)
        await page.getByRole('button', { name: 'My calendar', exact: true }).click()
        await expect(page.getByRole('heading', { name: 'My calendar', exact: true })).toBeVisible()
        await page.getByRole('button', { name: 'My Day', exact: true }).click()
      }
      if (agent) {
        await expect(page.getByRole('heading', { name: 'My Day', exact: true })).toBeVisible()
      } else {
        await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled()
        const onboarding = page.locator('div.fixed.z-50.right-0.w-80')
        if (await onboarding.isVisible()) await onboarding.locator(':scope > div').first().getByRole('button').last().click()
      }
      await page.screenshot({ path: `test-results/my-day-${label}.png`, fullPage: true })
      await page.setViewportSize({ width: 390, height: 844 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      expect(errors).toEqual([])
      await context.close()
    }
    console.log('PASS: Administrator, staff and agent My Day; date buckets, scoped results, task completion, calendar details/booking, agent endpoint boundary and mobile overflow.')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
