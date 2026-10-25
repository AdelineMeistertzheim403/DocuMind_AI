import express from 'express'
import helmet from 'helmet'
import { Transform, Readable } from 'node:stream'
import { existsSync } from 'node:fs'
import { timingSafeEqual, createHmac, randomBytes, randomUUID } from 'node:crypto'
import {createSecurityLogger,auditOperation} from './security-audit.mjs'
import {isIP} from 'node:net'

const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
const detailRoute = new RegExp(`^/bff/documents/${uuid}$`)
const analyzeRoute = new RegExp(`^/bff/documents/${uuid}/analyze$`)
const analysisRoute = new RegExp(`^/bff/documents/${uuid}/analysis$`)
const aiPost = new RegExp(`^/bff/documents/${uuid}/(?:summarize|ask)$`)
const aiGet = new RegExp(`^/bff/documents/${uuid}/(?:summaries|ai-history)$`)
const indexRoute = new RegExp(`^/bff/documents/${uuid}/index$`)
const comparisonRoute = new RegExp(`^/bff/comparisons/${uuid}$`)
const comparisonSummary = new RegExp(`^/bff/comparisons/${uuid}/summarize$`)
const summaryJob = new RegExp(`^/bff/summary-jobs/${uuid}$`)
const summaryJobAction = new RegExp(`^/bff/summary-jobs/${uuid}/(?:resume|cancel)$`)
const documentSummaryJob = new RegExp(`^/bff/documents/${uuid}/summary-jobs$`)
const summaryPlan = new RegExp(`^/bff/documents/${uuid}/summary-plan$`)
const accountSession = /^\/bff\/account\/sessions\/[a-f0-9]{64}$/
const privateDelete = new RegExp(`^/bff/documents/${uuid}/(?:ai-results|embeddings)$`)
const aiCodes = {
    'output_truncated': 'La réponse IA a atteint la limite de sortie avant de terminer. Les étapes validées sont conservées.',
    'provider_refusal': 'Le fournisseur a refusé cette étape. Les étapes validées sont conservées.',
    'invalid_json': 'Le fournisseur a renvoyé un JSON illisible. Les étapes validées sont conservées.',
    'invalid_schema': 'La réponse IA ne respecte pas le format demandé. Les étapes validées sont conservées.',
    'invalid_references': 'La réponse IA cite une source absente du contexte. Les étapes validées sont conservées.',

  disabled: 'L’IA est désactivée côté serveur.', budget_exhausted: 'Le budget disponible ne permet pas cette opération.',
  quota_reached: 'Votre quota est atteint.', rate_limit: 'Trop de requêtes IA. Attendez une minute.', busy: 'Des traitements IA sont déjà en cours.',
  request_in_progress: 'Cette demande est en cours ou sa consommation nécessite une réconciliation.', idempotency_conflict: 'Cette demande ne peut pas réutiliser cet identifiant.',
  invalid_output: 'Le fournisseur a refusé la demande ou retourné une réponse ou des sources invalides.',
  provider_uncertain: 'Réponse fournisseur incertaine. La réservation reste bloquée ; ne relancez pas la même opération.',
  usage_unknown: 'Consommation inconnue : réservation conservée.', provider_rate_limit: 'Le fournisseur limite les requêtes.',
  provider_unavailable: 'Le fournisseur est indisponible ou mal configuré.', pricing_unverified: 'Les tarifs du modèle doivent être vérifiés côté serveur.',
  document_too_long: 'Le plan dépasse le nombre maximal de parties ou d’appels autorisé. Aucun texte envoyé.', context_limit: 'Limite de contexte atteinte. Des étapes intermédiaires peuvent avoir été comptabilisées.',
  byok_disconnected: 'Connectez votre clé personnelle dans les paramètres IA.', byok_unvalidated: 'Validez votre clé personnelle dans les paramètres IA.',
  document_limit: 'La sélection dépasse la limite de documents ou de passages.',
  comparison_limit: 'Ces documents dépassent les limites de comparaison. Réduisez leur taille.',
  comparison_same_document: 'Sélectionnez deux fichiers distincts.',
  consent_required: 'Autorisez explicitement l’envoi au fournisseur avant cette opération.',
  estimate_changed: 'Le coût maximal a changé. Rechargez le plan et confirmez la nouvelle estimation.',
  session_required: 'Reconnectez votre compte et sa clé avant de reprendre la tâche.',
}
const messages = {
  400: 'La requête est invalide.',
  401: 'La connexion au service est mal configurée. Vérifiez la clé du BFF côté serveur.',
  402: 'Budget IA insuffisant.', 403: 'Cette opération nécessite une connexion HTTPS ou est désactivée.',
  409: 'Une opération est déjà en cours ou les paramètres de session doivent être vérifiés.',
  404: 'Ce document ou cette analyse est introuvable.',
  413: 'Le fichier dépasse la taille autorisée.',
  415: 'Seuls les fichiers PDF et TXT sont acceptés.',
  422: 'Le fichier est illisible, vide ou protégé, les paramètres sont invalides, ou une limite de traitement a été atteinte.',
  429: 'Trop de requêtes. Réessayez dans un instant.',
  503: 'Le service est indisponible ou occupé. Réessayez dans un instant.',
}

function routeAllowed(method, path) {
  if(path==='/bff/auth/registration-challenge' && method==='GET')return true
  if(['/bff/auth/verify-email','/bff/auth/resend-verification'].includes(path) && method==='POST')return true
  if (path === '/bff/auth/csrf' && method === 'GET') return true
  if (path === '/bff/auth/options' && method === 'GET') return true
  if (['/bff/auth/register','/bff/auth/forgot-password','/bff/auth/reset-password','/bff/account/password','/bff/account/deletion-request'].includes(path) && method === 'POST') return true
  if (['/bff/account','/bff/account/sessions'].includes(path) && method === 'GET') return true
  if ((accountSession.test(path)||privateDelete.test(path)) && method === 'DELETE') return true
  return (path === '/bff/documents' && ['GET', 'POST'].includes(method)) ||
    (detailRoute.test(path) && ['GET', 'DELETE'].includes(method)) ||
    (analyzeRoute.test(path) && method === 'POST') ||
    (analysisRoute.test(path) && method === 'GET') ||
    (aiPost.test(path) && method === 'POST') || (aiGet.test(path) && method === 'GET') ||
    (indexRoute.test(path) && ['GET', 'POST'].includes(method)) ||
    (path === '/bff/search/status' && method === 'GET') ||
    (['/bff/search/semantic', '/bff/search/ask', '/bff/documents/compare'].includes(path) && method === 'POST') ||
    (comparisonRoute.test(path) && method === 'GET') || (comparisonSummary.test(path) && method === 'POST') ||
    ((summaryPlan.test(path)||summaryJob.test(path))&&method==='GET') ||
    (documentSummaryJob.test(path)&&['GET','POST'].includes(method)) || (summaryJobAction.test(path)&&method==='POST') ||
    (path === '/bff/ai/status' && method === 'GET') ||
    (path === '/bff/ai/usage' && method === 'GET') ||
    (path === '/bff/ai/settings' && ['GET', 'PUT'].includes(method)) ||
    (path === '/bff/ai/key' && ['POST', 'DELETE'].includes(method)) ||
    (path === '/bff/ai/key/validate' && method === 'POST') ||
    (['/bff/auth/login', '/bff/auth/logout'].includes(path) && method === 'POST') ||
    (path === '/bff/health' && method === 'GET')
}

export function createApp(config, upstreamFetch = fetch, {auditSink}={}) {
  const app = express()
  const audit=createSecurityLogger(auditSink)
  let pendingUploadChecks = 0
  let activeUploads = 0
  app.disable('x-powered-by')
  app.use((req,res,next)=>{
    req.auditId=randomUUID().replaceAll('-','')
    res.set('X-Request-ID',req.auditId)
    let recorded=false
    const record=aborted=>{
      if(recorded)return
      recorded=true
      if(req.auditHandledByAPI && !aborted)return
      const upload=req.method==='POST' && req.path.replace(/\/+$/,'')==='/bff/documents'
      let entry=req.auditEvent
      if(aborted && upload)entry=['upload.aborted','disconnected']
      if(!entry && req.path.startsWith('/bff')) {
        const status=res.statusCode
        entry=status===401?['auth.session.invalid','missing_session']:
          [400,403,404].includes(status)?['access.denied','local_guard']:
          status===413?['upload.size.exceeded','size']:
          status===408?['upload.timeout','timeout']:
          status>=500?['system.api.unavailable','upstream_unavailable']:null
      }
      if(entry)audit.emit(entry[0],{request_id:req.auditId,operation:upload?'upload':auditOperation(req.path),
        http_status:aborted?499:res.statusCode,reason_code:entry[1]})
    }
    res.once('finish',()=>record(false))
    res.once('close',()=>record(!res.writableFinished))
    next()
  })
  app.use((req, res, next) => {
    if (req.method === 'POST' && req.path.replace(/\/+$/, '') === '/bff/documents') {
      // Do not drain an unauthenticated body to reuse an upstream HTTP/1 connection.
      res.set('Connection', 'close')
      res.once('finish', () => { if (!req.complete) req.socket.end() })
    }
    next()
  })
  app.use(helmet({ contentSecurityPolicy: { directives: {
    defaultSrc: ["'self'"], scriptSrc: ["'self'"], styleSrc: ["'self'", "'unsafe-inline'"],
    imgSrc: ["'self'", 'data:'], fontSrc: ["'self'"], connectSrc: ["'self'"],
    objectSrc: ["'none'"], frameAncestors: ["'none'"], upgradeInsecureRequests: null,
  } }, strictTransportSecurity: false }))

  app.use((req, res, next) => {
    // Check Host before serving private local data (including DNS rebinding).
    let hostname
    try { hostname = new URL(`http://${req.headers.host}`).hostname.replace(/^\[|\]$/g, '') } catch { return res.status(403).json({ detail: 'Hôte refusé.' }) }
    if (!config.allowedHosts.includes(hostname)) return res.status(403).json({ detail: 'Hôte refusé.' })
    if (req.path.startsWith('/bff')) {
      res.set('Cache-Control', 'no-store')
      if (req.headers['sec-fetch-site'] === 'cross-site') return res.status(403).json({ detail: 'Origine refusée.' })
      if (req.headers.origin) {
        try {
          if (new URL(req.headers.origin).host !== req.headers.host) return res.status(403).json({ detail: 'Origine refusée.' })
        } catch { return res.status(403).json({ detail: 'Origine refusée.' }) }
      }
    }
    next()
  })

  app.get('/bff/config', (req, res) => res.json({ max_upload_bytes: config.maxUploadBytes }))

  // Readiness is public only after the same Host/origin validation as all BFF routes.
  // No session, cookie, user data or upstream response body is exposed by this probe.
  app.get('/bff/health', async (req, res) => {
    if (Object.keys(req.query).length) return res.status(400).json({ detail: messages[400] })
    try {
      const response = await upstreamFetch(`${config.upstream}/api/v1/health`, {
        headers: { accept: 'application/json', 'X-API-Key': config.apiKey, 'X-Request-ID':req.auditId },
        signal: AbortSignal.timeout(3000), redirect: 'manual',
      })
      await response.body?.cancel()
      return res.status(response.status === 200 ? 200 : 503).json({ status: response.status === 200 ? 'ok' : 'unavailable' })
    } catch { return res.status(503).json({ status: 'unavailable' }) }
  })

  app.use(async (req, res, next) => {
    if (!req.path.startsWith('/bff')) return next()
    if (!routeAllowed(req.method, req.path)) return res.status(404).json({ detail: 'Route non autorisée.' })
    const url = new URL(req.originalUrl, 'http://local.invalid')
    const isList = (req.path === '/bff/documents' || req.path === '/bff/ai/usage' || aiGet.test(req.path)) && req.method === 'GET'
    for (const [key, value] of url.searchParams) {
      const allowed = isList && ['offset', 'limit'].includes(key) && /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) &&
        (key !== 'limit' || (Number(value) >= 1 && Number(value) <= 100)) && url.searchParams.getAll(key).length === 1
      if (!allowed) return res.status(400).json({ detail: messages[400] })
    }
    const headers = { accept: 'application/json', 'X-API-Key': config.apiKey, 'X-Request-ID':req.auditId }
    const gateway = req.headers['x-documind-gateway'] || ''
    const peer=(req.socket.remoteAddress||'').replace(/^::ffff:/,'')
    const trustedProxy=(config.trustedProxyIPs||[]).includes(peer) || Boolean(config.gatewayToken && typeof gateway === 'string' && Buffer.byteLength(gateway) === Buffer.byteLength(config.gatewayToken) && timingSafeEqual(Buffer.from(gateway), Buffer.from(config.gatewayToken)))
    const secure = req.secure || (trustedProxy && req.headers['x-forwarded-proto'] === 'https')
    const protectedSessionRoute = /^\/bff\/(?:auth\/|account(?:\/|$)|ai\/(?:settings|key))/.test(req.path)
    if (protectedSessionRoute && !secure) return res.status(403).json({ detail: 'Ouvrez la connexion HTTPS locale pour gérer votre compte et votre clé.' })
    const token = /(?:^|;\s*)__Host-documind=([A-Za-z0-9_-]{40,100})(?:;|$)/.exec(req.headers.cookie || '')?.[1]
    const publicRoute = /^\/bff\/auth\/(?:csrf|options|login|register|forgot-password|reset-password|verify-email|resend-verification|registration-challenge)$/.test(req.path) || req.path==='/bff/health'
    if (config.requireLogin && !publicRoute && (!secure || !token)) return res.status(401).json({detail:'Connectez votre compte sur HTTPS.',code:'login_required'})
    const sign = nonce => createHmac('sha256',config.apiKey).update(`${token||'anonymous'}:${nonce}`).digest('hex')
    if (req.path==='/bff/auth/csrf') {
      const nonce=randomBytes(32).toString('hex'), value=`${nonce}.${sign(nonce)}`
      res.set('Set-Cookie',`__Host-documind-csrf=${value}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=3600`)
      return res.json({csrf_token:value})
    }
    if (config.csrfProtection && !['GET','HEAD'].includes(req.method)) {
      const csrf=/(?:^|;\s*)__Host-documind-csrf=([a-f0-9]{64}\.[a-f0-9]{64})(?:;|$)/.exec(req.headers.cookie||'')?.[1]
      const supplied=req.headers['x-csrf-token']
      if (!secure || !csrf || typeof supplied!=='string' || supplied!==csrf || csrf!==`${csrf.slice(0,64)}.${sign(csrf.slice(0,64))}`) return res.status(403).json({detail:'Protection CSRF : rechargez la page puis réessayez.'})
      if (req.headers.origin && new URL(req.headers.origin).protocol!=='https:') return res.status(403).json({detail:'Origine HTTPS requise.'})
    }
    if (secure) headers['x-documind-secure'] = '1'
    const forwarded=typeof req.headers['x-forwarded-for']==='string'?req.headers['x-forwarded-for'].split(',').at(-1).trim():''
    headers['x-documind-client-ip'] = secure && trustedProxy && isIP(forwarded) ? forwarded : req.socket.remoteAddress || 'unknown'
    if (secure && token) headers.authorization = `Bearer ${token}`
    const isAI = aiPost.test(req.path) || (indexRoute.test(req.path) && req.method === 'POST') ||
      comparisonSummary.test(req.path) || ['/bff/search/semantic', '/bff/search/ask'].includes(req.path) ||
      ((documentSummaryJob.test(req.path)||summaryJobAction.test(req.path))&&req.method==='POST')
    if (isAI && (!secure || !token)) return res.status(403).json({ detail: 'Connectez votre compte sur l’accès HTTPS avant tout traitement IA.', code: 'login_required' })
    const upload = req.method === 'POST' && req.path === '/bff/documents'
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), upload ? (config.uploadTimeoutMs || 75000) : isAI ? (config.aiTimeoutMs || config.workerTimeoutMs) : config.workerTimeoutMs)
    let exceeded = false
    let readTimedOut = false
    let uploadReserved = false
    let readDeadline, idleDeadline
    let limiter
    const onAborted = () => controller.abort()
    const onResponseClosed = () => { if (!res.writableFinished) controller.abort() }
    req.on('aborted', onAborted)
    res.on('close', onResponseClosed)
    try {
      const options = { method: req.method, headers, signal: controller.signal, redirect: 'manual' }
      if (upload && config.requireLogin) {
        req.pause()
        if (pendingUploadChecks >= (config.uploadMaxPreflights || 8)) {
          req.auditEvent=['upload.capacity.exceeded','capacity']
          return res.status(503).json({detail:messages[503]})
        }
        pendingUploadChecks++
        try {
          const response = await upstreamFetch(`${config.upstream}/api/v1/internal/upload-admission`, {
            method: 'GET', headers, redirect: 'manual',
            signal: AbortSignal.any([controller.signal, AbortSignal.timeout(config.uploadAuthTimeoutMs || 3000)]),
          })
          await response.body?.cancel()
          if (response.status !== 204) {
            const status = [401,403,429].includes(response.status) ? response.status : 503
            req.auditHandledByAPI=[401,403,429,503].includes(response.status)
            if (status === 401) res.set('Set-Cookie','__Host-documind=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0')
            return res.status(status).json({detail:status===401?'Connectez votre compte ; la session est invalide.':messages[status]})
          }
        } catch { req.auditEvent=['system.api.unavailable','upstream_unavailable']; return res.status(503).json({detail:messages[503]}) }
        finally { pendingUploadChecks-- }
      }
      if (upload) {
        if (activeUploads >= (config.uploadMaxConcurrent || 2)) {
          req.auditEvent=['upload.capacity.exceeded','capacity']
          return res.status(503).json({detail:messages[503]})
        }
        activeUploads++
        uploadReserved = true
      }
      if (['POST', 'PUT'].includes(req.method)) {
        const contentType = req.headers['content-type'] || ''
        if (upload ? !/^multipart\/form-data;\s*boundary=/i.test(contentType) : !/^application\/json(?:;|$)/i.test(contentType)) {
          return res.status(415).json({ detail: 'Format de requête non pris en charge.' })
        }
        headers['content-type'] = contentType
        const maximum = upload ? config.maxUploadBytes + 65536 : 32768
        if (Number(req.headers['content-length']) > maximum) return res.status(413).json({ detail: messages[413] })
        let length = 0
        limiter = new Transform({ transform(chunk, encoding, done) {
          if (upload) {
            clearTimeout(idleDeadline)
            idleDeadline = setTimeout(() => { readTimedOut = true; controller.abort() }, config.uploadIdleTimeoutMs || 5000)
          }
          length += chunk.length
          if (length > maximum) { exceeded = true; done(new Error('Request size limit')) } else done(null, chunk)
        } })
        if (upload) {
          const abortRead = () => { readTimedOut = true; controller.abort() }
          readDeadline = setTimeout(abortRead, config.uploadReadTimeoutMs || 30000)
          idleDeadline = setTimeout(abortRead, config.uploadIdleTimeoutMs || 5000)
          req.once('end', () => { clearTimeout(readDeadline); clearTimeout(idleDeadline) })
          if (req.headers.expect?.toLowerCase() === '100-continue') res.writeContinue()
        }
        req.pipe(limiter)
        options.body = Readable.toWeb(limiter)
        options.duplex = 'half'
      }
      const upstreamPath = req.path.replace(/^\/bff/, '/api/v1')
      const response = await upstreamFetch(`${config.upstream}${upstreamPath}${url.search}`, options)
      if (response.status === 204) {req.auditHandledByAPI=true;return res.status(204).end()}
      if (!response.ok) {
        req.auditHandledByAPI=true
        let code
        try { const error = await response.json(); if (Object.hasOwn(aiCodes, error.detail?.code)) code = error.detail.code } catch { /* Controlled fallback */ }
        const status = messages[response.status] ? response.status : 502
        if (response.status === 401 && token) res.set('Set-Cookie', '__Host-documind=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0')
        return res.status(status).json({ detail: response.status === 401 && (token || protectedSessionRoute) ? 'Connectez votre compte ; la session ou les identifiants sont invalides.' : code ? aiCodes[code] : messages[status] || 'Le service a renvoyé une réponse inattendue.', ...(code ? { code } : {}) })
      }
      const data = await response.json()
      req.auditHandledByAPI=true
      if (req.path === '/bff/ai/status' && (!secure || !token)) { data.available = false; data.reason = data.enabled ? 'login_required' : 'disabled' }
      if (req.path === '/bff/auth/login') {
        if (typeof data.session_token !== 'string' || !/^[A-Za-z0-9_-]{40,100}$/.test(data.session_token)) {
          req.auditHandledByAPI=false
          req.auditEvent=['system.worker.failed','unexpected_error']
          return res.status(502).json({ detail: 'Session invalide.' })
        }
        res.set('Set-Cookie', `__Host-documind=${data.session_token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${Math.min(3600, Number(data.expires_in) || 1800)}`)
        return res.json({ connected: true })
      }
      if (['/bff/auth/logout','/bff/account/password','/bff/account/deletion-request'].includes(req.path)) res.set('Set-Cookie', '__Host-documind=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0')
      // Never forward upstream headers, cookies, redirects, or a supplied client API key.
      return res.status(response.status).json(data)
    } catch {
      const status = exceeded ? 413 : readTimedOut ? 408 : controller.signal.aborted ? 504 : 502
      return res.status(status).json({ detail: exceeded ? messages[413] : readTimedOut ? 'Délai de réception dépassé.' : status === 504 ? 'Le traitement a pris trop de temps.' : 'Impossible de joindre le service documentaire.' })
    } finally {
      clearTimeout(timeout)
      clearTimeout(readDeadline)
      clearTimeout(idleDeadline)
      if (uploadReserved) activeUploads--
      req.removeListener('aborted', onAborted)
      res.removeListener('close', onResponseClosed)
      if (limiter) { req.unpipe(limiter); limiter.destroy() }
    }
  })

  if (existsSync(config.dist)) {
    app.use(express.static(config.dist, { index: false }))
    app.get('/{*path}', (req, res) => res.sendFile(`${config.dist}/index.html`))
  }
  app.use((req, res) => res.status(404).json({ detail: 'Page introuvable.' }))
  app.use((error,req,res,next)=>{
    req.auditEvent=['system.worker.failed','unexpected_error']
    if(res.headersSent)return res.end()
    return res.status(500).json({detail:'Erreur interne du service'})
  })
  return app
}
