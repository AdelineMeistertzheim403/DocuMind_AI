import {request} from './api'

export async function registrationProof(){
  const {challenge,difficulty}=await request<{challenge:string;difficulty:number;expires_in:number}>('/auth/registration-challenge')
  if(!/^[A-Za-z0-9_-]{43}$/.test(challenge)||!Number.isInteger(difficulty)||difficulty<10||difficulty>18||!crypto.subtle){
    throw new Error('Vérification de sécurité indisponible. Utilisez un navigateur récent sur HTTPS.')
  }
  const encoder=new TextEncoder(),started=performance.now()
  for(let candidate=0;candidate<4194304;candidate++){
    if(performance.now()-started>20000)break
    const bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(`${challenge}:${candidate}`)))
    if(((bytes[0]<<16)|(bytes[1]<<8)|bytes[2]) >>> (24-difficulty) === 0)return {challenge,proof:String(candidate)}
    if(candidate%256===0)await new Promise(resolve=>setTimeout(resolve,0))
  }
  throw new Error('La vérification de sécurité a expiré. Réessayez.')
}
