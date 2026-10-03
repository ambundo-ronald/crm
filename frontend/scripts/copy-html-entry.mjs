import { copyFile, mkdir } from 'node:fs/promises'
import { URL } from 'node:url'

const source = new URL('../../crm/public/frontend/index.html', import.meta.url)
const destination = new URL('../../crm/www/crm.html', import.meta.url)

await mkdir(new URL('.', destination), { recursive: true })
await copyFile(source, destination)
