const { chromium, expect } = require('@playwright/test')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const context = await browser.newContext({ baseURL: 'http://127.0.0.1:18000', extraHTTPHeaders: { 'X-Frappe-Site-Name': 'crm.localhost' } })
    await context.addInitScript(() => localStorage.setItem('crm_persona_captured', '1'))
    expect((await context.request.post('/api/method/login', { form: { usr: 'Administrator', pwd: 'Local-Dev2-Only-2026' } })).status()).toBe(200)
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    await page.goto('/crm/leads')
    await page.locator('button').filter({ has: page.locator('.lucide-chevron-down') }).first().click()
    await page.getByText('Settings', { exact: true }).click()
    await page.locator('[data-page="ERPNext sync"]').click()
    await expect(page.getByRole('heading', { name: 'ERPNext appointments', exact: true })).toBeVisible()
    const response = page.waitForResponse(r => r.url().includes('crm.migration.appointments.preview'))
    await page.getByRole('button', { name: 'Preview appointments', exact: true }).click()
    expect((await response).status()).toBe(200)
    // Controlled display fixture; backend scope and mutation rules have separate integration tests.
    await page.route('**/api/method/crm.api.appointments.list_appointments', route => route.fulfill({ json: { message: {
      appointments: [{ name: 'erpnext-appointment:browser-fixture', subject: 'Imported appointment browser fixture', starts_on: '2026-10-20 10:00:00', ends_on: '2026-10-20 10:30:00', status: 'Open', read_only: true, reference_docname: null }],
      time_zone: 'Africa/Nairobi', truncated: false,
    } } }))
    await page.goto('/crm/appointments')
    await page.locator('input[type="date"]').first().fill('2026-10-20')
    await page.locator('input[type="date"]').first().dispatchEvent('change')
    await page.getByText('Imported appointment browser fixture', { exact: true }).first().click()
    const detail = page.locator('dialog[open]')
    await expect(detail).toContainText('read-only. Update it in ERPNext.')
    await expect(detail.getByRole('button', { name: 'Reschedule / edit' })).toHaveCount(0)
    await expect(detail.getByRole('button', { name: 'Complete appointment' })).toHaveCount(0)
    await expect(detail.getByRole('button', { name: 'Cancel appointment' })).toHaveCount(0)
    expect(errors).toEqual([])
    console.log('PASS: real sync preview endpoint and read-only imported calendar display; no source data changed.')
  } finally { await browser.close() }
})().catch(e => { console.error(e); process.exitCode = 1 })

