import {webcrypto} from 'node:crypto'
import {expect,it,vi} from 'vitest'
import {registrationProof} from './registration'
import * as api from './api'

it('calcule réellement une preuve de difficulté 12 avec WebCrypto',async()=>{
  vi.stubGlobal('crypto',webcrypto)
  try{
    const challenge='A'.repeat(43)
    vi.spyOn(api,'request').mockResolvedValue({challenge,difficulty:12,expires_in:300})
    const result=await registrationProof()
    const digest=new Uint8Array(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(`${result.challenge}:${result.proof}`)))
    expect(((digest[0]<<8)|digest[1])>>>4).toBe(0)
    expect(result.proof).toMatch(/^\d{1,12}$/)
  }finally{vi.unstubAllGlobals()}
},25000)
