import {createServer} from 'node:http'

export const REQUEST_TIMEOUT_MS = 60000
export const HEADERS_TIMEOUT_MS = 10000

export function createBffServer(app) {
  const server = createServer(app)
  server.on('checkContinue', app)
  server.requestTimeout = REQUEST_TIMEOUT_MS
  server.headersTimeout = HEADERS_TIMEOUT_MS
  return server
}
