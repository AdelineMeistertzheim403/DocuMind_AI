// Only constants and generated technical correlation IDs reach stdout.
const levels = {
  'access.denied':'WARNING', 'auth.session.invalid':'WARNING',
  'upload.capacity.exceeded':'WARNING', 'upload.size.exceeded':'WARNING',
  'upload.timeout':'WARNING', 'upload.aborted':'INFO',
  'system.api.unavailable':'ERROR', 'system.worker.failed':'ERROR',
  'system.security_config.invalid':'CRITICAL', 'system.started':'INFO', 'system.audit.dropped':'WARNING',
}
const reasons = new Set(['local_guard','missing_session','capacity','size','timeout','disconnected',
  'upstream_unavailable','unexpected_error','security_unavailable','started','dropped'])
const operations = new Set(['upload','login','logout','account','documents','ai','other','system'])
// A failed Docker stdout pipe must not become an unhandled stream error.
process.stdout.on('error', () => {})

function stdout(line) {
  if (process.stdout.destroyed || process.stdout.writableNeedDrain) return false
  return process.stdout.write(line+'\n', () => {})
}

export function createSecurityLogger(sink=stdout) {
  let window=-1, count=0, reported=0, lastReport=-1
  const stats={dropped:0,failed:0}
  const emit=(event, fields={})=>{
    try {
      if (!Object.hasOwn(levels,event)) return false
      const now=Math.floor(performance.now()/1000)
      if (now!==window) {window=now;count=0}
      if (++count>100) {stats.dropped++;return false}
      const record={timestamp:new Date().toISOString(),level:levels[event],service:'documind-bff',event,
        operation:operations.has(fields.operation)?fields.operation:'other',
        outcome:levels[event]==='ERROR'||levels[event]==='CRITICAL'?'error':levels[event]==='WARNING'?'denied':event==='upload.aborted'?'aborted':'success'}
      if (typeof fields.request_id==='string' && /^[0-9a-f]{32}$/.test(fields.request_id)) record.request_id=fields.request_id
      if (Number.isInteger(fields.http_status) && fields.http_status>=100 && fields.http_status<=599) record.http_status=fields.http_status
      if (reasons.has(fields.reason_code)) record.reason_code=fields.reason_code
      if (sink(JSON.stringify(record))===false) {stats.dropped++;return false}
      const lost=stats.dropped+stats.failed
      if(lost>reported && now!==lastReport) {
        const summary={timestamp:new Date().toISOString(),level:'WARNING',service:'documind-bff',
          event:'system.audit.dropped',operation:'system',outcome:'error',reason_code:'dropped',
          dropped_count:Math.min(lost-reported,1000000000)}
        if(sink(JSON.stringify(summary))!==false) {reported=lost;lastReport=now}
      }
      return true
    } catch {stats.failed++;return false}
  }
  return {emit,stats}
}

export function auditOperation(path) {
  if (path==='/bff/documents') return 'documents'
  if (path==='/bff/auth/login') return 'login'
  if (path==='/bff/auth/logout') return 'logout'
  for (const [prefix,name] of [['/bff/account','account'],['/bff/documents/','documents'],['/bff/ai','ai']]) {
    if(path.startsWith(prefix))return name
  }
  return 'other'
}
