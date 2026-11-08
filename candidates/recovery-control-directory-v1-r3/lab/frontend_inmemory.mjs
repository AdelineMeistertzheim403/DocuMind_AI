// Deferred D20: real Express pipeline, memory streams only, no listening server.
import assert from 'node:assert/strict'
import {Duplex} from 'node:stream'
import {syncBuiltinESMExports} from 'node:module'
import net from 'node:net'
import http from 'node:http'
import https from 'node:https'
import tls from 'node:tls'
import dns from 'node:dns'
import dgram from 'node:dgram'
import childProcess from 'node:child_process'

const violations = []
const deny = label => () => {
  violations.push(label)
  throw new Error(`Forbidden I/O: ${label}`)
}
for (const [module, names] of [
  [net, ['connect', 'createConnection', 'createServer']],
  [http, ['request', 'get', 'createServer']],
  [https, ['request', 'get', 'createServer']],
  [tls, ['connect', 'createServer']],
  [dns, ['lookup', 'resolve', 'resolve4', 'resolve6', 'reverse']],
  [dns.promises, ['lookup', 'resolve', 'resolve4', 'resolve6', 'reverse']],
  [dgram, ['createSocket']],
  [childProcess, ['exec', 'execSync', 'execFile', 'execFileSync', 'spawn', 'spawnSync', 'fork']],
]) {
  for (const name of names) module[name] = deny(name)
}
net.Socket.prototype.connect = deny('Socket.connect')
net.Server.prototype.listen = deny('Server.listen')
globalThis.fetch = deny('fetch')
syncBuiltinESMExports()

const {createApp} = await import('../source/frontend/server/app.mjs')
let upstreamCalls = 0
const app = createApp({
  apiKey: 'synthetic-only-bff-key-0000000000000001',
  upstream: 'http://inprocess.invalid', maxUploadBytes: 32, workerTimeoutMs: 1000,
  allowedHosts: ['localhost'], dist: '/nonexistent-synthetic-dist', requireLogin: true,
}, async url => {
  upstreamCalls++
  assert.equal(url, 'http://inprocess.invalid/api/v1/health')
  return Response.json({private: 'must-not-be-relayed'}, {status: 503})
}, {auditSink: () => {}})

async function inject(path, headers = {}) {
  const chunks = []
  const memory = new Duplex({
    read() {},
    write(chunk, encoding, callback) { chunks.push(Buffer.from(chunk)); callback() },
  })
  memory.remoteAddress = '127.0.0.1'
  memory.remoteFamily = 'IPv4'
  const request = new http.IncomingMessage(memory)
  request.method = 'GET'
  request.url = path
  request.httpVersionMajor = 1
  request.httpVersionMinor = 1
  request.httpVersion = '1.1'
  request.headers = {host: 'localhost', ...headers}
  const response = new http.ServerResponse(request)
  response.assignSocket(memory)
  let timeout
  try {
    await Promise.race([
      new Promise((resolve, reject) => {
        response.on('finish', resolve)
        response.on('error', reject)
        app.handle(request, response, error => {
          if (error) reject(error)
          else { response.statusCode = 404; response.end() }
        })
        request.push(null)
      }),
      new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('memory request timeout')), 3000) }),
    ])
    return {status: response.statusCode, raw: Buffer.concat(chunks).toString('utf8')}
  } finally {
    clearTimeout(timeout)
    memory.destroy()
  }
}

const health = await inject('/bff/health')
assert.equal(health.status, 503)
assert(!health.raw.includes('must-not-be-relayed'))
assert.equal((await inject('/bff/config')).status, 200)
assert.equal((await inject('/bff/health', {host: 'forbidden.invalid'})).status, 403)
assert.equal((await inject('/bff/health', {'sec-fetch-site': 'cross-site'})).status, 403)
assert.equal(upstreamCalls, 1)
assert.deepEqual(violations, [])
console.log(JSON.stringify({D20: 'PASS_BFF_INMEMORY_ONLY', upstreamCalls,
  api503_health503: true, localConfig200: true, host403: true, origin403: true,
  forbidden_io_events: violations}))
