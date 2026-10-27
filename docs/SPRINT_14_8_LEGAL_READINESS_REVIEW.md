# DocuMind AI — Préparation juridique de la bêta à cinq comptes

26 octobre 2026. Audit du dépôt local, sans modification applicative, des paramètres
de production, du verrou SQL ou de l'IA. Aucun accès au VPS ni consultation de
`.env.production`. Aucun test local relancé. Les configurations réellement déployées,
contrats et documents éventuellement hébergés ailleurs ne sont pas vérifiés.

**Verdict : préparation technique partielle ; ouverture publique non justifiée
par les preuves du dépôt.** Le frontend possède une page publique d'information
et un mécanisme de liens, mais pas trois textes juridiques complets. Le plafond
de cinq admissions ne constitue pas une validation juridique ou une dispense
automatique des obligations applicables. Les décisions ci-dessous appartiennent
à l'exploitante, avec validation juridique adaptée à son statut et à ses utilisateurs.

## 1. Pages et accessibilité réellement implémentées

| Élément | Constat dans le code | Limite |
| --- | --- | --- |
| `/legal` | `PublicInformationPage`, `frontend/src/pages/Account.tsx`, route déclarée dans `frontend/src/App.tsx` avant `RequireAccount`. Présentation de la bêta, nom/contact configurés, trois liens, explication sommaire de suppression. | Page d'orientation, pas mentions légales/CGU/politique complètes. Contient des indications « à renseigner » si options absentes. |
| Mentions, confidentialité, CGU | Trois liens HTTPS issus des options API. Aucun texte autonome ni routes `/legal-notice`, `/privacy`, `/terms` trouvés dans les routes/pages/public du frontend. | Ces chemins utilisés dans les tests sont fictifs ; ils ne prouvent pas l'existence des pages. Des documents externes pourraient convenir, mais aucun n'est vérifié ici. |
| Accès anonyme | `/legal` ne demande pas de session. Le BFF sert la SPA ; `/bff/auth/options` est explicitement public, tout en exigeant HTTPS et les protections Host/proxy. Backend `GET /auth/options` sans session utilisateur. | Disponibilité des options dépend de l'API ; la page ne présente pas explicitement l'erreur de chargement et peut afficher les valeurs de remplacement. Aucun parcours navigateur de production exécuté. |
| Avant inscription | `AccountAccess` propose un lien « Informations et confidentialité » depuis les pages d'accès. En mode public, case requise avec liens CGU et confidentialité. | Les liens ne garantissent ni HTTP 200, ni accès anonyme à la cible, ni un contenu validé. |
| Navigation connectée | `Layout.tsx` propose `/settings/privacy`, protégée par session ; footer sans lien vers `/legal` ou les trois textes. | La gestion privée des données n'est pas une politique publique. Ajouter un accès permanent aux textes dans la navigation/footer. |

`LegalLink()` refuse les URL non HTTPS ou comportant identifiant/mot de passe et
affiche sinon « document non configuré ». Il n'inspecte pas la destination.
Pointer les trois variables sur `/legal` créerait des liens circulaires sans textes.
Pointer vers `/privacy` ou `/terms` sans créer les routes aboutirait au fallback
de la SPA, sous le groupe protégé, pas à une politique publique.

## 2. Paramètres et preuve d'acceptation

| Paramètre | Comportement vérifié | Validation supplémentaire nécessaire |
| --- | --- | --- |
| `PUBLIC_LEGAL_NOTICE_URL` | Retourné par `options()` et affiché dans `/legal`. | URL absolue HTTPS d'un vrai document de l'exploitant, lisible sans compte. |
| `PUBLIC_PRIVACY_URL` | Retourné et lié depuis `/legal` et le formulaire public. | Politique conforme aux traitements réels, disponible au moment de la collecte. |
| `PUBLIC_TERMS_URL` | Retourné et lié depuis `/legal` et l'acceptation. | CGU complètes, lisibles avant acceptation, version archivée. |
| `PUBLIC_TERMS_VERSION` | Maximum 40 caractères ; exigé non vide en mode public. Comparaison exacte avec la valeur envoyée dans `admit()` ; persisté avec `terms_accepted_at` sur `User`. | Identifiant stable relié au texte exact publié ; pas de remplacement silencieux d'une version. Le code ne conserve pas une copie immuable du texte ni son empreinte. |
| `PUBLIC_LEGAL_READY` | Faux par défaut. `Settings.validate_keys()` refuse le mode public s'il reste faux. | Déclaration de l'exploitante, **pas contrôle juridique**, ni téléchargement/test des documents. Ne le passer à vrai qu'après validation documentée. |

`PUBLIC_OPERATOR_NAME` et `PUBLIC_CONTACT_EMAIL` complètent le dispositif. Le
validateur vérifie nom non blanc et présence de `@` dans le contact, pas l'identité
juridique ou la délivrabilité. Les URL backend exigent schéma HTTPS, hostname,
absence d'identifiants et fragment ; cela ne certifie pas propriété du domaine,
accessibilité ou pertinence. Une version faite seulement d'espaces n'est pas
explicitement normalisée : un contrôle ciblé de valeur non blanche est recommandé.

Les deux fichiers `.env.example` et `.env.production.example` laissent les URL et
version vides, `PUBLIC_LEGAL_READY=false`. Ce sont des modèles, pas les valeurs
actives. Le service API du Compose reçoit l'env de production ; les valeurs sont
ensuite exposées par `/auth/options`, pas compilées dans React. Les contrôleurs de
livraison s'appuient aussi sur la validation Settings dans l'image. Ils ne lisent
pas les textes juridiques. Aucun paramètre modifié dans cet audit.

La case actuelle distingue consultation de la confidentialité et acceptation
des conditions ; conserver cette distinction. L'acceptation des CGU n'est pas
un consentement global à tous les traitements ni à un futur envoi IA.

## 3. Correspondance entre information et traitements

| Fonction réelle / fichiers | Ce que les textes doivent couvrir | Écart ou réserve |
| --- | --- | --- |
| Compte/workspace : `backend/public_registration.py`, `auth.py`, `account_models.py` | Email, identifiant, hash du mot de passe, workspace personnel, statut de vérification, dates/version acceptée, finalités et base juridique à qualifier. | Pas de politique détaillée fournie. Cinq admissions cumulatives, comptes en attente inclus, pas cinq seuls comptes actifs ; suppression sans restitution de place. |
| Email : `account_api.py`, `public_registration.py` | Vérification obligatoire, renvoi, récupération, fournisseur SMTP, destinataires techniques, durée des jetons et des traces. | Vérification par jeton haché stocké et usage unique, TTL par défaut 3600 s ; reset 900 s. L'expiration du jeton ne signifie pas effacement immédiat de sa ligne/email. Notification potentiellement absente après commit : ne pas promettre un envoi garanti (SQL-03). |
| Sessions : `auth.py`, BFF `app.mjs` | Cookie d'authentification et sécurité, session serveur, durée effective, révocation ; aucun marketing déduit de la création du compte. | Cookie `__Host-documind`, Secure/HttpOnly/SameSite=Strict ; TTL de session par défaut 1800 s, configurable. Documenter la valeur adoptée, pas affirmer une durée immuable. |
| Documents : `models.py`, `services/documents.py`, `compose.production.yaml` | Fichiers PDF/TXT, noms/métadonnées, texte/pages/chunks, analyses classiques, stockage serveur privé et accès opérationnels habilités. | Documents dans volume serveur `/app/var`, données PostgreSQL ; pas seulement dans le navigateur. Ni absence totale d'accès administrateur ni chiffrement applicatif au repos démontrés. |
| Suppression documentaire : `delete_document()`, `services/document_integrity.py` | Suppression active et données liées, copies de sauvegarde séparées, gestion des erreurs. | Effacement du fichier après confirmation durable de suppression SQL ; fichier conservé si état incertain, nettoyage pouvant échouer. Ne pas promettre un effacement physique instantané dans tous les cas. Réconciliation administrative nécessaire. |
| Suppression compte : `account_api.deletion()`, `account_admin.purge_account()` | Désactivation immédiate, révocation, demande d'effacement et traitement administratif avec délai décidé. | Pas de purge complète automatique à la demande. Le CLI conserve notamment owner/workspace et comptabilité pour empêcher reset ; UUID résiduel ne prouve pas une anonymisation irréversible. Qualifier et borner ces conservations. |
| Comptes non vérifiés : `purge_pending()` | Politique de traitement des comptes abandonnés. | Commande explicite, simulation par défaut, seuil configurable minimum 48 h ; aucune preuve de purge périodique ou délai garanti. |
| Sauvegardes : `tools/backup_production.py`, `backup_local.py`, `retention_production.py` | Base et documents sauvegardés, archives locales et dépôt Restic/B2, accès, durée, suppression après échéance, réapplication des suppressions après restauration. | La conservation fournie est en **simulation** : le code interdit l'exécution réelle. Les 7 quotidiens/4 hebdomadaires/6 mensuels envisagés ne démontrent pas une durée d'effacement effective ou une purge installée. |
| Sécurité/alertes : `backend/security_audit.py`, `frontend/server/security-audit.mjs`, outils ops | Traces techniques, anti-abus, accès autorisés, rotation/rétention et éventuels prestataires d'alerte. | Événements allowlistés sans documents/tokens prévus ; rotation Docker bornée en taille, pas délai calendaire garanti. Logs Traefik/OS/prestataires et export réels non inspectés. |
| IA et BYOK : `backend/ai/`, paramètres publics | Bêta initiale : fonctions IA indisponibles, aucun usage OpenAI à promettre comme actif. | Les écrans privés parlent encore d'IA/BYOK et de traitements autorisés. Distinguer clairement fonctionnalité future et service offert ; tout futur changement nécessite information et décision propres, sans activer l'IA ici. |

**Formulations à corriger avant ouverture :** `Layout.tsx` affiche « Vos documents
restent dans votre environnement local » et « Environnement local ». En SaaS,
remplacer par une description exacte du stockage serveur privé et renvoyer vers
la politique validée. Le footer « Sprint 04 · IA optionnelle » et le guide parlant
d'un assistant optionnel ne reflètent pas nettement la bêta IA désactivée.
`PrivacyPage` ne doit pas laisser entendre que toutes les copies disparaissent
immédiatement, ni qu'une durée de sauvegarde encore indéfinie est déjà approuvée.

## 4. Informations à fournir par l'exploitante

### Identité et cadre contractuel — bloquant avant ouverture

Déterminer le statut réel (personne physique/entreprise/société), pays et public
visé, gratuité ou offre payante, identité/coordonnées de l'éditeur, responsable
de publication et hébergeur. Les numéros d'immatriculation, forme/capital et
mentions complémentaires dépendent du statut : ne rien inventer à partir du nom
GitHub ou du domaine. Faire valider les clauses bêta, durée/fin du service,
disponibilité, propriété des documents, usages permis/interdits, suspension,
responsabilité, réclamation et droit applicable. CGU et CGV ne sont pas interchangeables.
Référence officielle : [Service Public — mentions d'un site professionnel](https://entreprendre.service-public.gouv.fr/vosdroits/F37351?lang=fr).

### Confidentialité — bloquant avant ouverture

Identifier le responsable de traitement et son contact, finalités/bases par
traitement, caractère obligatoire des données, destinataires, durées ou critères,
droits applicables et leur canal d'exercice, réclamation CNIL et transferts
éventuels. Décrire l'information au moment de collecte, y compris les personnes
dont les données figurent dans des documents importés. À qualifier : rôle de
DocuMind pour les comptes et rôle éventuel de sous-traitant pour les contenus
professionnels, contrats correspondants, données sensibles autorisées ou exclues,
public mineur et nécessité éventuelle d'une analyse d'impact. Ne pas affirmer une
certification ou un régime d'hébergement spécifique non établi.
Référence : [CNIL — information et transparence](https://www.cnil.fr/fr/conformite-rgpd-information-des-personnes-et-transparence).

### Prestataires et lieux — à documenter, pas à supposer

OVH et Backblaze B2 sont annoncés dans le contexte d'exploitation ; relever les
entités contractuelles, services/régions réellement choisis, accès et contrats de
sous-traitance, transferts et garanties applicables. Ne pas déduire « toutes les
données restent en France » du seul VPS. Le fournisseur SMTP transactionnel est
configurable et doit être identifié ; l'éventuel Gmail d'alerte est distinct.
GitHub/Registry servent la livraison logicielle : ne pas les présenter sans preuve
comme recevant les documents utilisateurs. OpenAI est une intégration future
désactivée pour cette bêta, pas un destinataire actif déduit du nom du produit.

### Cookies et preuve contractuelle

Inventorier les cookies/traceurs réellement présents dans le navigateur de la
stack retenue. L'authentification strictement nécessaire peut relever de
l'exemption de consentement ; cela n'exempte pas les traitements associés du
RGPD. Ne pas ajouter un bandeau universel sans identifier des traceurs qui le
nécessitent. [CNIL — cookies et conformité](https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies/comment-mettre-mon-site-web-en-conformite).

Archiver les textes datés et leur version correspondant à `terms_version` ;
prévoir preuve de publication/acceptation et modalités de changements. Ne pas
collecter une IP supplémentaire uniquement par réflexe de « preuve ». Les
durées de conservation des preuves sont une décision proportionnée à valider.

## 5. Corrections recommandées, non appliquées

1. Faire rédiger/valider les trois textes avec les informations factuelles
   ci-dessus. Conserver les inconnues en dossier de préparation, pas en documents
   prétendument finalisés. Aucune modification du verrou SQL ou du mode requise.
2. Choisir soit des pages publiques versionnées dans la SPA, soit des documents
   HTTPS externes maîtrisés. Si internes : déclarer les routes hors RequireAccount,
   ajouter des liens permanents dans `Layout.tsx` et conserver l'accès depuis les
   formulaires. Ne pas réutiliser `/settings/privacy` comme politique publique.
3. Rendre le portail juridique fiable lorsque l'API est indisponible : contenu
   statique versionné ou liens de secours revus, état d'erreur explicite. Garder
   les validations d'URL et l'échec fermé du formulaire public.
4. Corriger les libellés stockage local/IA et les promesses d'effacement selon
   les comportements documentés. Distinguer suppression logique, fichiers retenus
   pour intégrité et copies de sauvegarde ; définir responsable, délai, suivi.
5. Décider et mettre en œuvre séparément une conservation effective vérifiable,
   y compris backups locaux/B2, logs, comptes abandonnés et traces résiduelles.
   Ne pas activer une purge ou modifier les sauvegardes au titre de cet audit.
6. Après validation humaine seulement, préparer les URL finales, version exacte
   et preuve d'approbation associée à `PUBLIC_LEGAL_READY`. Tester sans ouvrir les
   inscriptions ; tout changement de production exige son autorisation propre.

Fichiers probablement concernés par une future correction :
`frontend/src/App.tsx`, `pages/Account.tsx`, `components/Layout.tsx`, nouvelles
pages/textes validés, `pages/PublicBeta.test.tsx`, `backend/config.py` si validation
non-blanche renforcée, documentation du runbook et procédures de conservation.
Pas de migration nécessaire démontrée pour publier des textes ; une preuve de
versions plus élaborée ferait l'objet d'une conception séparée.

## 6. Tests existants et recette ciblée à prévoir

`frontend/src/pages/PublicBeta.test.tsx` couvre les liens/acceptation et le refus
d'un lien non HTTPS ; `tests/test_public_beta.py` couvre les garde-fous légaux
de configuration et le refus d'inscription sans acceptation. Ces fixtures emploient
des URL et une identité fictives : elles ne valident pas des textes juridiques.

Après correction uniquement, ajouter/vérifier : accès direct anonyme aux trois
documents en HTTPS, absence de redirection login, navigation mobile/clavier,
visibilité avant collecte, état API en erreur, URL manquante ou cible inexistante,
CGU/version cohérentes, refus d'ancienne version sans compte créé, accessibilité
après fermeture des inscriptions et après déconnexion. Un HTTP 200 de la SPA
ne suffit pas : vérifier titre et contenu attendu. Ne pas refaire toutes les
suites déjà vertes pour ce seul audit documentaire.

## 7. Checklist avant ouverture

- [ ] Identité/statut, contacts, éditeur/hébergeur et éventuelles mentions spécifiques validés.
- [ ] Trois textes complets approuvés et archivés avec date/version, sans placeholders.
- [ ] Pages réellement publiques, lisibles sans authentification, liens permanents fonctionnels.
- [ ] URL configurées pointant sur les vrais textes ; version acceptée liée au texte archivé.
- [ ] Bases juridiques, rôles responsable/sous-traitant, catégories de documents et droits validés.
- [ ] Régions, contrats, destinataires SMTP/backup/alertes et transferts documentés.
- [ ] Politique de conservation applicable et procédures d'effacement/reprise éprouvées, pas simple simulation.
- [ ] Canal droits/réclamation opérationnel et responsable du traitement des demandes désigné.
- [ ] Cookies nécessaires inventoriés ; aucun traceur non nécessaire sans cadre adapté.
- [ ] Information exacte : cinq admissions cumulatives, email non garanti, IA indisponible, stockage serveur.
- [ ] Validation humaine de PUBLIC_LEGAL_READY documentée, distincte d'une validation automatique.
- [ ] Autorisation d'ouverture distincte après les prérequis techniques et opérationnels du runbook.

**Aucune ouverture recommandée à ce stade sur la seule preuve locale.** Les
textes externes et paramètres actifs peuvent exister, mais doivent être fournis
et vérifiés avant de lever ce constat. Le rapport propose les corrections ;
aucune configuration, donnée ou fonctionnalité n'a été modifiée.
