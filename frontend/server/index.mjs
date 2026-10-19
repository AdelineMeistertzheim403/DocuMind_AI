import { createApp } from './app.mjs'
import { loadConfig } from './config.mjs'

try {
  const config = loadConfig()
  const server = createApp(config).listen(config.port, config.host, () => {
    console.log(`DocuMind AI : http://${config.host}:${config.port}`)
  })
  server.requestTimeout = 60000
  server.headersTimeout = 10000
  const shutdown = () => server.close(() => process.exit(0))
  process.on('SIGTERM', shutdown)
  process.on('SIGINT', shutdown)
} catch {
  console.error('BFF non démarré : vérifiez la clé serveur et la configuration documentée dans le README.')
  process.exitCode = 1
}
