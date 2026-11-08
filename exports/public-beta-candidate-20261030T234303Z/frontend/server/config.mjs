import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import dotenv from 'dotenv'
import {isIP} from 'node:net'
import {REQUEST_TIMEOUT_MS, HEADERS_TIMEOUT_MS} from './http-server.mjs'

export function loadConfig(env = process.env) {
  if (env === process.env) {
    dotenv.config({ path: fileURLToPath(new URL('../../.env', import.meta.url)), quiet: true })
  }
  let apiKey = env.BFF_SERVICE_KEY || env.BFF_API_KEY
  if (!apiKey) {
    let keys
    try { keys = Object.keys(JSON.parse(env.API_KEYS || '{}')) } catch { throw new Error('API_KEYS doit être un objet JSON valide') }
    if (keys.length !== 1) throw new Error('Définissez BFF_API_KEY, ou une seule clé dans API_KEYS')
    apiKey = keys[0]
  }
  if (typeof apiKey !== 'string' || apiKey.length < 32 || /[\r\n]/.test(apiKey)) throw new Error('Clé BFF invalide')
  const upstream = new URL(env.BFF_BACKEND_URL || `http://127.0.0.1:${env.API_PORT || '8000'}`)
  if (!['http:', 'https:'].includes(upstream.protocol) || upstream.username || upstream.password || upstream.pathname !== '/' || upstream.search || upstream.hash) {
    throw new Error('BFF_BACKEND_URL doit désigner une origine HTTP sans identifiants')
  }
  const maxUploadBytes = Number(env.MAX_UPLOAD_BYTES || 10485760)
  const port = Number(env.BFF_PORT || 3000)
  const uploadNumber = (name, fallback, minimum, maximum) => {
    const value = Number(env[name] ?? fallback)
    if (!Number.isFinite(value) || value < minimum || value > maximum) throw new Error('Limites upload BFF invalides')
    return value
  }
  const trustedProxyIPs=(env.BFF_TRUSTED_PROXY_IPS||'').split(',').map(value=>value.trim()).filter(Boolean)
  if(trustedProxyIPs.some(value=>!isIP(value))) throw new Error('BFF_TRUSTED_PROXY_IPS doit contenir des adresses IP exactes')
  if (!Number.isSafeInteger(maxUploadBytes) || maxUploadBytes < 1 || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Limites BFF invalides')
  const config = {
    apiKey, upstream: upstream.origin, maxUploadBytes, port,
    requireLogin: true, csrfProtection: true,
    uploadMaxConcurrent: uploadNumber('UPLOAD_MAX_CONCURRENT', 2, 1, 8),
    uploadMaxPreflights: uploadNumber('UPLOAD_MAX_PREFLIGHTS', 8, 1, 32),
    uploadAuthTimeoutMs: uploadNumber('UPLOAD_AUTH_TIMEOUT_SECONDS', 3, .001, 10) * 1000,
    uploadReadTimeoutMs: uploadNumber('UPLOAD_READ_TIMEOUT_SECONDS', 30, .001, 120) * 1000,
    uploadIdleTimeoutMs: uploadNumber('UPLOAD_IDLE_TIMEOUT_SECONDS', 5, .001, 30) * 1000,
    uploadTimeoutMs: uploadNumber('UPLOAD_TOTAL_TIMEOUT_SECONDS', 75, 1, 300) * 1000,
    trustedProxyIPs,
    gatewayToken: env.DOCUMIND_GATEWAY_TOKEN || '',
    host: env.BFF_HOST || '127.0.0.1',
    allowedHosts: (env.BFF_ALLOWED_HOSTS || 'localhost,127.0.0.1,::1').split(',').map(s => s.trim()),
    dist: resolve(fileURLToPath(new URL('../dist', import.meta.url))),
    workerTimeoutMs: Math.max(10000, (Number(env.WORKER_TIMEOUT_SECONDS) || 30) * 1000 + 15000),
    aiTimeoutMs: Math.max(15000, ((Number(env.AI_TIMEOUT_SECONDS) || 30) * 2 + 2) * (Number(env.AI_MAX_SUMMARY_STEPS) || 5) * 1000),
  }
  if (!Number.isInteger(config.uploadMaxConcurrent) || !Number.isInteger(config.uploadMaxPreflights) ||
      config.uploadIdleTimeoutMs > config.uploadReadTimeoutMs ||
      config.uploadAuthTimeoutMs + config.uploadReadTimeoutMs + HEADERS_TIMEOUT_MS > REQUEST_TIMEOUT_MS ||
      config.uploadTimeoutMs < config.uploadAuthTimeoutMs + config.uploadReadTimeoutMs +
        (Number(env.WORKER_TIMEOUT_SECONDS) || 30) * 1000 + 5000) {
    throw new Error('Délais ou capacités upload incohérents')
  }
  return config
}
