import {useEffect,useState,type FormEvent} from 'react'
import {Link,Navigate,Outlet,useLocation} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {account,accountPost} from '../services/account'
import {api,ApiError,request} from '../services/api'
import {ErrorState,SectionTitle,Spinner} from '../components/ui'

export function RequireAccount(){
  const location=useLocation()
  const query=useQuery({queryKey:['account'],queryFn:account.me,retry:false,staleTime:0,refetchOnWindowFocus:true,refetchInterval:30000})
  if(query.isPending)return <Spinner label="Vérification de votre session…"/>
  if(query.error instanceof ApiError && [401,403].includes(query.error.status))return <Navigate to="/login" replace state={{from:location.pathname}}/>
  if(query.error)return <ErrorState error={query.error}/>
  return <Outlet/>
}

export function AccountAccess({mode}:{mode:'login'|'register'|'forgot'|'reset'}){
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[invitation,setInvitation]=useState('')
  const [token,setToken]=useState(()=>new URLSearchParams(location.hash.slice(1)).get('token')||'')
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null),[message,setMessage]=useState('')
  const secure=location.protocol==='https:'
  const options=useQuery({queryKey:['account-options'],queryFn:account.options,retry:false,enabled:secure})
  useEffect(()=>{if(mode==='reset'&&location.hash)history.replaceState(null,'',location.pathname)},[mode])
  const title={login:'Connexion',register:'Inscription',forgot:'Mot de passe oublié',reset:'Réinitialiser le mot de passe'}[mode]
  async function submit(event:FormEvent){
    event.preventDefault();setBusy(true);setError(null);setMessage('')
    const entered=password;setPassword('')
    try{
      if(mode==='login'){
        await accountPost('/auth/login',{email,password:entered});window.location.assign('/');return
      }
      if(mode==='register'){
        const code=invitation;setInvitation('')
        await accountPost('/auth/register',{email,password:entered,invitation:code})
        setMessage('Compte créé. Vous pouvez vous connecter.')
      }
      if(mode==='forgot'){
        await accountPost('/auth/forgot-password',{email})
        setMessage('Si ce compte est éligible, un message de récupération sera envoyé.')
      }
      if(mode==='reset'){
        await accountPost('/auth/reset-password',{token,password:entered});setToken('')
        setMessage('Mot de passe modifié. Toutes les sessions ont été révoquées. Reconnectez-vous.')
      }
    }catch(failure){setError(failure)}finally{setBusy(false)}
  }
  return <main className="page account-access"><section className="panel settings-card"><Link className="brand" to="/login">DocuMind AI</Link><SectionTitle eyebrow="VOTRE ESPACE PERSONNEL" title={title}/>
    {!secure&&<p className="notice">Une connexion HTTPS est nécessaire. <a href="https://localhost:8443/login">Ouvrir la connexion locale sécurisée</a>.</p>}
    {mode==='register'&&<p className="notice">{options.data?.registration_mode==='invite'?'Inscription sur invitation personnelle, valable 24 heures.':'Les inscriptions sont désactivées. Contactez votre administrateur.'}</p>}
    <form onSubmit={submit}>
      {mode!=='reset'&&<><label className="field-label" htmlFor="account-email">{mode==='login'?'Email ou identifiant historique':'Email'}</label><input id="account-email" className="text-input" type={mode==='login'?'text':'email'} autoComplete="username" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)} disabled={busy||!secure}/></>}
      {mode!=='forgot'&&<><label className="field-label" htmlFor="account-password">Mot de passe</label><input id="account-password" className="text-input" type="password" autoComplete={mode==='login'?'current-password':'new-password'} required minLength={mode==='login'?1:12} maxLength={256} value={password} onChange={e=>setPassword(e.target.value)} disabled={busy||!secure}/></>}
      {mode==='register'&&<><label className="field-label" htmlFor="account-invitation">Invitation</label><input id="account-invitation" type="password" className="text-input" autoComplete="off" required value={invitation} onChange={e=>setInvitation(e.target.value)} disabled={busy||!secure}/></>}
      {mode==='reset'&&!token&&<p className="notice">Ouvrez le lien de réinitialisation reçu par email. Les liens sont temporaires et à usage unique.</p>}
      <button className="button primary" disabled={busy||!secure||(mode==='register'&&options.data?.registration_mode!=='invite')||(mode==='reset'&&!token)}>{busy?'Traitement…':title}</button>
    </form>
    {error!=null&&<ErrorState error={error}/>} {message&&<p role="status" className="notice">{message}</p>}
    <nav className="settings-actions"><Link to="/login">Connexion</Link><Link to="/register">Inscription</Link><Link to="/forgot-password">Mot de passe oublié</Link></nav>
    <p>Vos identifiants DocuMind restent indépendants de votre clé OpenAI.</p>
  </section></main>
}

export function ProfilePage(){
  const profile=useQuery({queryKey:['account'],queryFn:account.me})
  return <div className="page"><SectionTitle eyebrow="MON COMPTE" title="Profil"/><section className="panel settings-card">{profile.isPending?<Spinner/>:profile.error?<ErrorState error={profile.error}/>:<><h2>{profile.data?.email||profile.data?.username}</h2><p>{profile.data?.workspace}</p><p>Identifiant historique : {profile.data?.username}</p>{!profile.data?.email&&<p className="notice">Demandez à l’administrateur d’associer votre email vérifié pour activer la récupération de mot de passe.</p>}</>}<nav className="settings-actions"><Link to="/settings/security">Sécurité</Link><Link to="/settings/ai">Paramètres IA</Link><Link to="/settings/privacy">Confidentialité</Link></nav></section></div>
}

export function SecurityPage(){
  const sessions=useQuery({queryKey:['account-sessions'],queryFn:account.sessions,retry:false})
  const [password,setPassword]=useState(''),[next,setNext]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null)
  async function perform(action:()=>Promise<unknown>){setBusy(true);setError(null);try{await action();await sessions.refetch()}catch(e){setError(e)}finally{setBusy(false)}}
  return <div className="page"><SectionTitle eyebrow="MON COMPTE" title="Sécurité"/><section className="panel settings-card"><h2>Sessions actives</h2><p>Les sessions expirent après 30 minutes par défaut. Révoquer une session supprime aussi sa clé BYOK temporaire.</p>{sessions.data?.items.map(s=><div className="settings-heading" key={s.id}><span>{s.current?'Cette session':'Autre session'} · expire à {new Date(s.expires_at*1000).toLocaleTimeString('fr-FR')}</span><button className="button secondary" disabled={busy} onClick={()=>perform(async()=>{await request(`/account/sessions/${s.id}`,{method:'DELETE'});if(s.current)window.location.assign('/login')})}>Révoquer</button></div>)}{sessions.error&&<ErrorState error={sessions.error}/>}<button className="button secondary" disabled={busy} onClick={()=>perform(async()=>{await accountPost('/auth/logout',{});window.location.assign('/login')})}>Se déconnecter</button></section>
    <section className="panel settings-card"><h2>Changer mon mot de passe</h2><form onSubmit={e=>{e.preventDefault();const old=password,replacement=next;setPassword('');setNext('');perform(async()=>{await accountPost('/account/password',{password:old,new_password:replacement});window.location.assign('/login')})}}><label className="field-label" htmlFor="current-password">Mot de passe actuel</label><input id="current-password" type="password" className="text-input" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/><label className="field-label" htmlFor="new-password">Nouveau mot de passe</label><input id="new-password" type="password" className="text-input" autoComplete="new-password" minLength={12} maxLength={256} required value={next} onChange={e=>setNext(e.target.value)}/><button className="button primary" disabled={busy}>Modifier et révoquer toutes les sessions</button></form></section>{error!=null&&<ErrorState error={error}/>}</div>
}

export function PrivacyPage(){
  const docs=useQuery({queryKey:['privacy-documents'],queryFn:()=>api.documents(0,100)})
  const [id,setId]=useState(''),[confirmed,setConfirmed]=useState(false),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null),[message,setMessage]=useState('')
  async function erase(kind:'document'|'ai-results'|'embeddings'){
    setBusy(true);setError(null);try{if(kind==='document')await api.remove(id);else await request(`/documents/${id}/${kind}`,{method:'DELETE'});setMessage('Suppression effectuée. Les éventuelles sauvegardes suivent leur délai de conservation.');setConfirmed(false);await docs.refetch()}catch(e){setError(e)}finally{setBusy(false)}
  }
  return <div className="page"><SectionTitle eyebrow="VOS DONNÉES" title="Confidentialité"/><section className="panel settings-card"><h2>Gérer les données documentaires</h2><p>La suppression d’un document efface son fichier, son texte, ses analyses, ses résumés et ses embeddings. Les traces de consommation restent pour empêcher la remise à zéro des budgets.</p><label className="field-label" htmlFor="privacy-document">Document</label><select id="privacy-document" className="text-input" value={id} onChange={e=>{setId(e.target.value);setConfirmed(false)}}><option value="">Choisir un document</option>{docs.data?.items.map(d=><option key={d.id} value={d.id}>{d.filename}</option>)}</select>{docs.error&&<ErrorState error={docs.error}/>}<label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> Je confirme la suppression des données sélectionnées.</label><div className="settings-actions">{(['document','ai-results','embeddings'] as const).map((k,i)=><button className="button secondary" key={k} disabled={!id||!confirmed||busy} onClick={()=>erase(k)}>{['Supprimer le document','Effacer les résultats IA','Effacer les embeddings'][i]}</button>)}</div><Link to="/settings/ai">Déconnecter ma clé BYOK</Link></section>
    <section className="panel settings-card"><h2>Demander la suppression de mon compte</h2><p>Votre compte sera immédiatement désactivé et vos sessions révoquées. L’administrateur traitera ensuite l’effacement des contenus et des sauvegardes selon la politique de conservation. Cette demande nécessite votre mot de passe.</p><form onSubmit={async e=>{e.preventDefault();setBusy(true);setError(null);const entered=password;setPassword('');try{await accountPost('/account/deletion-request',{password:entered});window.location.assign('/login')}catch(f){setError(f)}finally{setBusy(false)}}}><label className="field-label" htmlFor="deletion-password">Mot de passe de confirmation</label><input id="deletion-password" className="text-input" type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/><button className="button secondary" disabled={busy}>Demander la suppression et désactiver le compte</button></form></section>
    <section className="panel settings-card"><h2>Conservation et fournisseur IA</h2><p>La clé BYOK reste uniquement en session serveur jusqu’à déconnexion ou expiration. Les documents ne sont envoyés au fournisseur que pour les traitements explicitement autorisés. DocuMind n’affiche pas le solde réel de votre compte OpenAI.</p><p>Les sauvegardes peuvent contenir des données supprimées jusqu’à leur expiration. Les durées et procédures applicables doivent être définies par l’exploitant avant la mise en production. Une validation juridique et organisationnelle reste nécessaire pour la politique de confidentialité.</p></section>{busy&&<Spinner/>}{error!=null&&<ErrorState error={error}/>} {message&&<p role="status">{message}</p>}</div>
}
