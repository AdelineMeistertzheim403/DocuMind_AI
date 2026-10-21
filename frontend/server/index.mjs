import { createApp } from './app.mjs'
import { loadConfig } from './config.mjs'
import { createBffServer } from './http-server.mjs'

try {
  const config = loadConfig()
  const app = createApp(config)
  const server = createBffServer(app)
  // Let the application validate admission before emitting 100 Continue.
  server.listen(config.port, config.host, () => {
    console.log(`DocuMind AI : http://${config.host}:${config.port}`)
  })
  const shutdown = () => server.close(() => process.exit(0))
  process.on('SIGTERM', shutdown)
  process.on('SIGINT', shutdown)
} catch {
  console.error('BFF non démarré : vérifiez la clé serveur et la configuration documentée dans le README.')
  process.exitCode = 1
}
