import {Link,useParams} from 'react-router-dom'
import {legalNotice,privacy,termsArchive,TERMS_VERSION,type LegalDocument} from '../legal/documents'

export function LegalNavigation(){
  return <nav className="settings-actions" aria-label="Documents juridiques — brouillons">
    <Link to="/mentions-legales">Mentions légales (brouillon)</Link>
    <Link to="/confidentialite">Confidentialité (brouillon)</Link>
    <Link to="/cgu">CGU (brouillon)</Link>
  </nav>
}
export function LegalPage({kind}:{kind:'notice'|'privacy'|'terms'}){
  const {version}=useParams()
  const requestedVersion=version||TERMS_VERSION
  const archived=Object.prototype.hasOwnProperty.call(termsArchive,requestedVersion)?termsArchive[requestedVersion]:undefined
  const document:LegalDocument|undefined=kind==='notice'?legalNotice:kind==='privacy'?privacy:archived
  return <main className="page account-access"><article className="panel settings-card">
    <Link to="/legal">Informations sur la bêta</Link>
    <h1>{document?.title||'Version des CGU introuvable'}</h1>
    <p className="notice" role="note"><strong>Brouillon non approuvé — ne vaut pas validation juridique.</strong> Les informations manquantes nécessitent la validation de l’exploitante. Ces pages n’autorisent ni inscription ni ouverture publique.</p>
    {document?<><p>Version : <strong>{document.version}</strong></p>
      {document.sections.map(section=><section key={section.title}><h2>{section.title}</h2>{section.text&&<p>{section.text}</p>}{section.items&&<ul>{section.items.map(item=><li key={item}>{item}</li>)}</ul>}
        {section.blocks?.map((block,index)=>block.kind==='paragraph'?<p key={index}>{block.text}</p>:block.kind==='list'?<ul key={index}>{block.items.map(item=><li key={item}>{item}</li>)}</ul>:<div key={index} style={{overflowX:'auto'}}><table aria-label={section.title}><thead><tr>{block.headers.map(header=><th key={header} scope="col">{header}</th>)}</tr></thead><tbody>{block.rows.map((row,rowIndex)=><tr key={rowIndex}>{row.map((cell,column)=><td key={column}>{cell}</td>)}</tr>)}</tbody></table></div>)}
      </section>)}
      {kind==='terms'&&<p><Link to={`/cgu/versions/${document.version}`}>Lien permanent de cette version</Link></p>}
    </>:<p>Cette version n’est pas disponible. Aucune autre version ne lui est substituée.</p>}
    {kind==='terms'&&<section><h2>Versions conservées</h2><ul>{Object.keys(termsArchive).map(key=><li key={key}><Link to={`/cgu/versions/${key}`}>{key} — brouillon</Link></li>)}</ul></section>}
    <LegalNavigation/><Link to="/login">Revenir à la connexion</Link>
  </article></main>
}
