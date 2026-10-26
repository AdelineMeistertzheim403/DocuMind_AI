import {request} from './api'

export interface Profile { id:string; email:string|null; username:string; owner_id:string; workspace:string }
export interface SessionInfo { id:string; current:boolean; expires_at:number }
export interface AccountOptions {registration_mode:'disabled'|'invite'|'public'; public_capacity_configured?:boolean;
  public_registration_availability?:'available'|'closed'|'full';
  terms_version?:string;legal_notice_url?:string;privacy_url?:string;terms_url?:string;operator_name?:string;contact_email?:string}
export const account={
  me:()=>request<Profile>('/account'),
  options:()=>request<AccountOptions>('/auth/options'),
  sessions:()=>request<{items:SessionInfo[]}>('/account/sessions'),
}
export const accountPost=(path:string,body:object)=>request<Record<string,unknown>>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
