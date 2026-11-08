import { createApp } from './app.mjs'
import { loadConfig } from './config.mjs'
import { createBffServer } from './http-server.mjs'
import {createSecurityLogger} from './security-audit.mjs'
const audit=createSecurityLogger()

try {
  const config = loadConfig()
  const app = createApp(config)
  const server = createBffServer(app)
  // Let the application validate admission before emitting 100 Continue.
  server.listen(config.port, config.host, () => {
    audit.emit('system.started',{operation:'system',reason_code:'started'})
  })
  const shutdown = () => server.close(() => process.exit(0))
  process.on('SIGTERM', shutdown)
  process.on('SIGINT', shutdown)
} catch {
  audit.emit('system.security_config.invalid',{operation:'system',reason_code:'security_unavailable'})
  process.exitCode = 1
}
