const { chromium, expect } = require('@playwright/test')
const fs = require('node:fs/promises')
async function check(locator, theme) {
  await expect(locator.first()).toBeVisible()
  const colors = await locator.first().evaluate(el => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1
    const ctx = canvas.getContext('2d')
    const parse = value => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = value; ctx.fillRect(0, 0, 1, 1); const rgba = [...ctx.getImageData(0, 0, 1, 1).data]; rgba[3] /= 255; return rgba }
    let node = el, bg
    while (node) { bg = parse(getComputedStyle(node).backgroundColor); if (bg.length < 4 || bg[3] > 0.99) break; node = node.parentElement }
    return { bg, fg: parse(getComputedStyle(el).color) }
  })
  const lum = c => c.slice(0, 3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4 }).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0)
  const bg = lum(colors.bg), fg = lum(colors.fg)
  if (theme === 'dark') expect(bg).toBeLessThan(.2)
  else expect(bg).toBeGreaterThan(.6)
  expect((Math.max(bg, fg) + .05) / (Math.min(bg, fg) + .05), `${locator} ${theme}: ${JSON.stringify(colors)}`).toBeGreaterThanOrEqual(4.5)
}
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  await fs.mkdir('test-results', { recursive: true })
  try {
    for (const theme of ['dark', 'light']) {
      const context = await browser.newContext({ baseURL: 'http://127.0.0.1:18000', viewport: { width: 1440, height: 1000 } })
      await context.addInitScript(value => { localStorage.setItem('theme', value); localStorage.setItem('crm_persona_captured', '1') }, theme)
      await context.request.post('/api/method/login', { form: { usr: 'Administrator', pwd: 'Local-Dev2-Only-2026' } })
      const page = await context.newPage(), errors = []
      page.on('pageerror', e => errors.push(e.message))
      const dismiss = async () => { const panel = page.locator('div.fixed.z-50.right-0.w-80'); if (await panel.isVisible()) await panel.locator(':scope > div').first().getByRole('button').last().click() }
      await page.goto('/crm/my-day')
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled()
      await dismiss()
      await check(page.locator('main').last(), theme)
      await check(page.locator('#daily-appointments h2'), theme)
      await page.screenshot({ path: `test-results/theme-my-day-${theme}.png`, fullPage: true })
      await page.goto('/crm/appointments')
      await expect(page.locator('.calendar-content')).toHaveAttribute('aria-busy', 'false')
      await dismiss()
      await check(page.locator('.calendar-shell'), theme)
      await check(page.getByLabel('Search appointments', { exact: true }), theme)
      for (const view of ['Week', 'Day', 'Schedule', 'Month']) {
        await page.getByLabel('View', { exact: true }).selectOption(view)
        await expect(page.locator('.calendar-content')).toHaveAttribute('aria-busy', 'false')
        await check(page.locator('.calendar-shell'), theme)
      }
      for (const kind of ['linked', 'intro', 'completed', 'cancelled']) {
        await page.locator('.calendar-shell').evaluate((el, kind) => { const sample = document.createElement('button'); sample.id = 'theme-event-sample'; sample.className = 'month-event ' + kind; for (const attr of el.getAttributeNames().filter(name => name.startsWith('data-v-'))) sample.setAttribute(attr, ''); sample.textContent = kind; el.append(sample) }, kind)
        await check(page.locator('#theme-event-sample'), theme)
        await page.locator('#theme-event-sample').evaluate(el => el.remove())
      }
      await page.screenshot({ path: `test-results/theme-calendar-${theme}.png`, fullPage: true })
      await page.getByRole('button', { name: 'Book appointment', exact: true }).click()
      await check(page.locator('dialog[open]'), theme)
      await check(page.getByLabel('Appointment title', { exact: true }), theme)
      await check(page.getByLabel('Starts', { exact: true }), theme)
      await page.screenshot({ path: `test-results/theme-booking-${theme}.png`, fullPage: true })
      await page.goto('/crm/erpnext-sync')
      await expect(page.getByRole('heading', { name: 'ERPNext sync', exact: true })).toBeVisible()
      await check(page.locator('.crm-themed-panel'), theme)
      await check(page.getByLabel('ERPNext record ID', { exact: true }), theme)
      await check(page.getByLabel('Source type', { exact: true }), theme)
      await page.screenshot({ path: `test-results/theme-sync-${theme}.png`, fullPage: true })
      await page.getByRole('button', { name: /Administrator/ }).first().click()
      await page.getByText('Settings', { exact: true }).click()
      await page.locator('[data-page="Agents"]').click()
      await check(page.locator('.crm-themed-panel').last(), theme)
      await check(page.getByLabel('First name', { exact: true }), theme)
      await page.screenshot({ path: `test-results/theme-agents-${theme}.png`, fullPage: true })
      expect(errors).toEqual([])
      await context.close()
    }
    const context = await browser.newContext({ baseURL: 'http://127.0.0.1:18000', colorScheme: 'dark' })
    await context.request.post('/api/method/login', { form: { usr: 'dev2.agent.a@example.invalid', pwd: 'Local-Dev2-Only-2026' } })
    const page = await context.newPage()
    await page.goto('/crm-agent')
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.getByRole('button', { name: 'My Day', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'My Day', exact: true })).toBeVisible()
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('Theme', { exact: true }).selectOption(theme)
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await check(page.locator('#detail'), theme)
      await page.screenshot({ path: `test-results/theme-workspace-${theme}.png`, fullPage: true })
      await page.getByRole('button', { name: 'Book meeting (no lead)', exact: true }).click()
      await check(page.locator('dialog[open]'), theme)
      await check(page.getByLabel('Appointment title', { exact: true }), theme)
      await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    }
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.getByLabel('Theme', { exact: true }).selectOption('system')
    await page.emulateMedia({ colorScheme: 'light' })
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    console.log('PASS: light/dark surfaces and text contrast across My Day, all calendar views/event states/dialogs, sync and agent settings; agent theme persistence/system switching and mobile layout. No records changed.')
  } finally { await browser.close() }
})().catch(e => { console.error(e); process.exitCode = 1 })
