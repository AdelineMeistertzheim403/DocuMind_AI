// Test-only loopback HTTPS reverse proxy and real BFF; never reads the project's .env.
import {createServer as httpServer,request} from 'node:http'
import {createServer as httpsServer} from 'node:https'
import {readFileSync} from 'node:fs'
import {once} from 'node:events'
import {createApp} from '../../frontend/server/app.mjs'
import {loadConfig} from '../../frontend/server/config.mjs'

let input=''
for await(const chunk of process.stdin)input+=chunk
const settings=JSON.parse(input)
const config=loadConfig({BFF_SERVICE_KEY:settings.key,BFF_BACKEND_URL:settings.api,
  BFF_ALLOWED_HOSTS:'localhost',BFF_TRUSTED_PROXY_IPS:'127.0.0.1',BFF_PORT:'3000'})
const bff=httpServer(createApp(config))
bff.listen(0,'127.0.0.1');await once(bff,'listening')
const proxy=httpsServer({key:readFileSync(settings.privateKey),cert:readFileSync(settings.certificate)},(req,res)=>{
  // The proxy replaces, rather than trusts, caller-supplied forwarding identities.
  const headers={...req.headers,'x-forwarded-proto':'https','x-forwarded-for':'192.0.2.50'}
  delete headers['x-documind-gateway'];delete headers['x-forwarded-host']
  const upstream=request({hostname:'127.0.0.1',port:bff.address().port,method:req.method,path:req.url,headers},response=>{
    res.writeHead(response.statusCode,response.headers);response.pipe(res)
  })
  upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end()})
  req.on('aborted',()=>upstream.destroy());req.pipe(upstream)
})
proxy.listen(0,'127.0.0.1');await once(proxy,'listening')
console.log(JSON.stringify({origin:`https://localhost:${proxy.address().port}`}))
function stop(){proxy.closeAllConnections();proxy.close();bff.closeAllConnections();bff.close()}
process.on('SIGTERM',stop);process.on('SIGINT',stop)
