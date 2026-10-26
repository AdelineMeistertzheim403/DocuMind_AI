import {useEffect,useState,type FormEvent} from 'react'
import {Link,Navigate,Outlet,useLocation} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {account,accountPost} from '../services/account'
import {api,ApiError,request} from '../services/api'
import {ErrorState,SectionTitle,Spinner} from '../components/ui'
import {registrationProof} from '../services/registration'

export function RequireAccount(){
  const location=useLocation()
  const query=useQuery({queryKey:['account'],queryFn:account.me,retry:false,staleTime:0,refetchOnWindowFocus:true,refetchInterval:30000})
  if(query.isPending)return <Spinner label="Vérification de votre session…"/>
  if(query.error instanceof ApiError && [401,403].includes(query.error.status))return <Navigate to="/login" replace state={{from:location.pathname}}/>
  if(query.error)return <ErrorState error={query.error}/>
  return <Outlet/>
}

export function AccountAccess({mode}:{mode:'login'|'register'|'forgot'|'reset'|'verify'|'resend'}){
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[invitation,setInvitation]=useState('')
  const [token,setToken]=useState(()=>new URLSearchParams(location.hash.slice(1)).get('token')||'')
  const [website,setWebsite]=useState(''),[terms,setTerms]=useState(false)
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null),[message,setMessage]=useState('')
  const secure=location.protocol==='https:'
  const options=useQuery({queryKey:['account-options'],queryFn:account.options,retry:false,enabled:secure})
  useEffect(()=>{if(['reset','verify'].includes(mode)&&location.hash)history.replaceState(null,'',location.pathname)},[mode])
  const isPublic=options.data?.registration_mode==='public'
  const canRegister=options.data?.registration_mode==='invite'||(isPublic&&options.data?.public_capacity_configured===true)
  const title={login:'Connexion',register:'Inscription',forgot:'Mot de passe oublié',reset:'Réinitialiser le mot de passe',verify:'Vérifier mon adresse e-mail',resend:'Renvoyer le lien de vérification'}[mode]
  async function submit(event:FormEvent){
    event.preventDefault();setBusy(true);setError(null);setMessage('')
    const entered=password;setPassword('')
    try{
      if(mode==='login'){
        await accountPost('/auth/login',{email,password:entered});window.location.assign('/');return
      }
      if(mode==='register'){
        const code=invitation;setInvitation('')
        const body=isPublic?{email,password:entered,website,terms_accepted:terms,terms_version:options.data?.terms_version,...await registrationProof()}:{email,password:entered,invitation:code}
        await accountPost('/auth/register',body)
        setMessage(isPublic?'Demande reçue. Cette réponse ne confirme ni l’admission ni l’envoi d’un e-mail. Vérifiez vos courriers indésirables ; vous pouvez demander un nouveau lien.':'Compte créé. Vous pouvez vous connecter.')
      }
      if(mode==='resend'){
        await accountPost('/auth/resend-verification',{email,password:entered,website,...await registrationProof()})
        setMessage('Demande reçue. Si elle est éligible, un nouveau lien pourra être envoyé. Cette réponse ne confirme pas l’envoi. Seul le dernier lien émis reste valable.')
      }
      if(mode==='verify'){
        await accountPost('/auth/verify-email',{token,password:entered});setToken('')
        setMessage('Adresse vérifiée. Vous pouvez maintenant vous connecter.')
      }
      if(mode==='forgot'){
        await accountPost('/auth/forgot-password',{email})
        setMessage('Demande reçue. Un compte éligible peut recevoir un lien de récupération. Cette réponse ne confirme pas l’envoi d’un e-mail.')
      }
      if(mode==='reset'){
        await accountPost('/auth/reset-password',{token,password:entered});setToken('')
        setMessage('Mot de passe modifié. Toutes les sessions ont été révoquées. Reconnectez-vous.')
      }
    }catch(failure){setError(failure)}finally{setBusy(false)}
  }
  return <main className="page account-access"><section className="panel settings-card"><Link className="brand" to="/login">DocuMind AI</Link><SectionTitle eyebrow="VOTRE ESPACE PERSONNEL" title={title}/>
    {!secure&&<p className="notice">Une connexion HTTPS est nécessaire. <a href="https://localhost:8443/login">Ouvrir la connexion locale sécurisée</a>.</p>}
    {options.error&&<ErrorState error={options.error}/>}
    {mode==='register'&&<p className="notice" role="status">{options.isPending?'Vérification de la disponibilité des inscriptions…':options.error?'La disponibilité des inscriptions ne peut pas être confirmée. Réessayez ultérieurement.':options.data?.registration_mode==='invite'?'Inscription sur invitation personnelle, valable 24 heures.':canRegister?'Bêta limitée à cinq admissions cumulatives. Une admission consomme une place avant la vérification de l’e-mail.':options.data?.public_registration_availability==='full'?'Le plafond d’admissions de cette bêta est atteint. Les comptes existants restent accessibles.':'Les nouvelles inscriptions sont fermées. Les comptes existants restent accessibles.'}</p>}
    {['register','login'].includes(mode)&&<p>Les fonctionnalités IA seront disponibles ultérieurement. Les comptes vérifiés conservent les fonctions documentaires classiques.</p>}
    {mode==='resend'&&<p className="notice">Utilisez le mot de passe choisi à l’inscription. Le renvoi reste possible après fermeture des nouvelles inscriptions, selon les limites de sécurité. Attendez avant une nouvelle demande, notamment sur un réseau partagé.</p>}
    {mode==='verify'&&<p className="notice">Saisissez le mot de passe choisi lors de votre inscription. N’activez pas une inscription que vous n’avez pas demandée.</p>}
    <form onSubmit={submit} aria-busy={busy}>
      {!['reset','verify'].includes(mode)&&<><label className="field-label" htmlFor="account-email">{mode==='login'?'Email ou identifiant historique':'Email'}</label><input id="account-email" className="text-input" type={mode==='login'?'text':'email'} autoComplete="username" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)} disabled={busy||!secure}/></>}
      {mode!=='forgot'&&<><label className="field-label" htmlFor="account-password">Mot de passe</label><input id="account-password" className="text-input" type="password" autoComplete={mode==='login'?'current-password':'new-password'} required minLength={mode==='login'?1:12} maxLength={256} value={password} onChange={e=>setPassword(e.target.value)} disabled={busy||!secure}/></>}
      {mode==='register'&&options.data?.registration_mode==='invite'&&<><label className="field-label" htmlFor="account-invitation">Invitation</label><input id="account-invitation" type="password" className="text-input" autoComplete="off" required value={invitation} onChange={e=>setInvitation(e.target.value)} disabled={busy||!secure}/></>}
      {(mode==='resend'||(mode==='register'&&isPublic))&&<div aria-hidden="true" style={{position:'absolute',left:'-10000px'}}><label htmlFor="account-website">Site internet</label><input id="account-website" name="website" tabIndex={-1} autoComplete="off" maxLength={200} value={website} onChange={e=>setWebsite(e.target.value)}/></div>}
      {mode==='register'&&isPublic&&<label><input type="checkbox" required checked={terms} onChange={e=>setTerms(e.target.checked)} disabled={busy||!secure}/> J’ai consulté les <LegalLink url={options.data?.terms_url}>conditions d’utilisation</LegalLink> et les <LegalLink url={options.data?.privacy_url}>informations de confidentialité</LegalLink>, et j’accepte les conditions.</label>}
      {mode==='reset'&&!token&&<p className="notice">Ouvrez le lien de réinitialisation reçu par email. Les liens sont temporaires et à usage unique.</p>}
      {mode==='verify'&&!token&&!message&&<p className="notice">Ouvrez le lien reçu par e-mail. Il expire et ne peut être utilisé qu’une fois.</p>}
      <button className="button primary" disabled={busy||!secure||(mode==='register'&&!canRegister)||(['reset','verify'].includes(mode)&&!token)}>{busy?'Traitement…':title}</button>
    </form>
    {error!=null&&<ErrorState error={error}/>} {message&&<p role="status" className="notice">{message}</p>}
    {error instanceof ApiError&&error.status===400&&['verify','reset'].includes(mode)&&<p>Le lien peut être invalide, expiré ou déjà utilisé, ou la vérification incorrecte. Demandez un nouveau lien et utilisez uniquement le plus récent.</p>}
    <nav className="settings-actions"><Link to="/login">Connexion</Link><Link to="/register">Inscription</Link><Link to="/forgot-password">Mot de passe oublié</Link><Link to="/resend-verification">Renvoyer la vérification</Link><Link to="/legal">Informations et confidentialité</Link></nav>
    <p>Vos identifiants DocuMind restent indépendants de votre clé OpenAI.</p>
  </section></main>
}

function LegalLink({url,children}:{url?:string;children:React.ReactNode}){
  try{const parsed=new URL(url||'');if(parsed.protocol==='https:'&&!parsed.username&&!parsed.password)return <a href={parsed.href} rel="noreferrer">{children}</a>}catch{/* No unvalidated URL */}
  return <span>{children} (document non configuré)</span>
}

export function PublicInformationPage(){
  const options=useQuery({queryKey:['account-options'],queryFn:account.options,retry:false,enabled:location.protocol==='https:'})
  return <main className="page account-access"><section className="panel settings-card"><h1>Informations sur la bêta DocuMind AI</h1><p>Cette application analyse des documents privés. Une session personnelle est nécessaire pour consulter vos contenus.</p>
    <p>Exploitant : {options.data?.operator_name||'à renseigner avant ouverture publique'}. Contact : {options.data?.contact_email||'à renseigner avant ouverture publique'}.</p>
    <ul><li><LegalLink url={options.data?.legal_notice_url}>Mentions de l’exploitant</LegalLink></li><li><LegalLink url={options.data?.privacy_url}>Politique de confidentialité</LegalLink></li><li><LegalLink url={options.data?.terms_url}>Conditions d’utilisation</LegalLink></li></ul>
    <p>La création publique exige la vérification de l’e-mail. La première bêta est limitée à cinq admissions cumulatives, y compris les comptes en attente de vérification. Les fonctionnalités IA seront disponibles ultérieurement. Les comptes vérifiés peuvent utiliser les fonctions documentaires classiques.</p>
    <p>Une suppression de compte le désactive immédiatement. L’effacement final est traité par l’administrateur ; les copies de sauvegarde suivent la conservation approuvée. Les durées et coordonnées applicables doivent être précisées dans les documents de l’exploitant avant ouverture.</p><Link to="/login">Revenir à la connexion</Link>
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
