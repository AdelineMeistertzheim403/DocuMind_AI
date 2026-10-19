import {request} from './api'

export interface Profile { id:string; email:string|null; username:string; owner_id:string; workspace:string }
export interface SessionInfo { id:string; current:boolean; expires_at:number }
export const account={
  me:()=>request<Profile>('/account'),
  options:()=>request<{registration_mode:'disabled'|'invite'}>('/auth/options'),
  sessions:()=>request<{items:SessionInfo[]}>('/account/sessions'),
}
export const accountPost=(path:string,body:object)=>request<Record<string,unknown>>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
