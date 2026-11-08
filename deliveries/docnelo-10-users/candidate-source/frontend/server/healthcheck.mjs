// node:http preserves the explicit Host header on loopback, unlike some Node fetch versions.
import { request } from 'node:http'
import { loadConfig } from './config.mjs'

try {
  const config = loadConfig()
  const probe = request({ hostname: '127.0.0.1', port: config.port, path: '/bff/health',
    method: 'GET', headers: { Host: config.allowedHosts[0] }, timeout: 3000 }, response => {
    response.resume()
    response.on('end', () => process.exit(response.statusCode === 200 ? 0 : 1))
    response.on('error', () => process.exit(1))
  })
  probe.on('timeout', () => probe.destroy(new Error('Healthcheck timeout')))
  probe.on('error', () => process.exit(1))
  probe.end()
} catch { process.exit(1) }
