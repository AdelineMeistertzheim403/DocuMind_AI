# Audit du rebranding Docnelo — Public Beta

Date : 31 octobre 2026, Europe/Paris. Branche vérifiée : `branding/docnelo`. HEAD : `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`. L'essentiel des changements examinés est **non commité** ; le nom de branche et ce SHA ne suffisent pas à identifier une release Docnelo.

## Décision

**NO-GO pour construire ou déployer directement l'arbre de travail actuel.** Le build CSS échoue et le périmètre mélange rebranding et fonctions nouvelles. Une release **Web seule, limitée aux ressources statiques**, est la voie recommandée après isolation des changements et validation d'un nouveau build. Aucun besoin fonctionnel de modifier l'API, la base, les migrations ou les sauvegardes n'a été identifié pour ce lot limité.

Le rebranding complet de tous les canaux n'est pas possible en Web seul : les emails et le titre OpenAPI proviennent de l'API. Leur changement est à reporter dans un lot distinct, sans embarquer les autres modifications backend. La persistance temporaire de « DocuMind » dans ces canaux doit être explicitement acceptée avant publication du lot Web.

Cette intervention n'a modifié aucun code applicatif, configuration, fichier de sauvegarde ni artefact des livraisons V5/V5.1. Seuls les trois rapports demandés sont ajoutés ; tests/builds locaux ont pu actualiser leurs sorties et caches ignorés par Git. Aucun accès au VPS, build d'image, déploiement ou opération de production.

## Références et portée de la preuve

- Release applicative déclarée : `/opt/documind-public-beta/public-beta-candidate-20261030T234818Z`.
- Conteneurs déclarés : `documind-public-beta-db-1`, `documind-public-beta-api-1`, `documind-public-beta-web-1`.
- Sauvegarde V5 via V5.1, confirmation Restic B2 et restauration PostgreSQL 17 : éléments validés fournis par l'opérateur, sans nouvelle exécution dans cet audit.
- Référence locale examinée : `exports/public-beta-candidate-20261030T234818Z`. Aucun digest du conteneur réellement actif n'a été lu à distance ; cette référence ne prouve pas à elle seule l'identité du VPS actuel.

L'exporteur `ops/public_beta/export_public_beta_candidate.ps1` commence par git archive HEAD, puis recopie backend et migrations de l'image API, et server/dist/package*.json de l'image Web. **Il ne remplace pas frontend/src par les sources de cette image.** Son dossier peut donc associer des sources frontend historiques et un dist effectivement différent. La release propre devra retrouver le commit/source exact ayant produit l'image Web active, pas simplement reconstruire les sources de l'export.

Après normalisation BOM/fins de ligne, les fichiers backend suivis modifiés sont identiques à l'export local, sauf les textes dans account_api.py, main.py et ai/providers.py. Plusieurs évolutions Beta Lite sont donc déjà dans l'export API : les différences face à HEAD ne doivent pas être présentées comme autant de nouveautés par rapport au VPS. À l'inverse, le BFF local app.mjs diffère de l'export sur 45 lignes ajoutées/retirées : téléchargement, suppression et ui-config notamment. Cela interdit de réutiliser aveuglément le BFF local pour un lot graphique.

## Charte effectivement intégrée

Référence : `docs/docnelo/brand-kit/CHARTE_GRAPHIQUE_DOCNELO.md`, v1.0, explicitement une **proposition**, et non une charte finale certifiée.

| Élément | Constat dans les fichiers | Écart ou limite |
| --- | --- | --- |
| Logo horizontal sombre | BrandMark référence docnelo-horizontal-dark-transparent.png, alt=Docnelo ; utilisé dans Layout et AccountAccess | PNG RGBA 1060×310, image examinée visuellement ; légers contours issus du détourage à vérifier au rendu final |
| Taille du logo | CSS width=156px, height=auto ; ratio préservé, attribut HTML height=28 supplanté par CSS | Charte conseille 160px minimum ; protection et rendu mobile non certifiés |
| Icônes | PNG RGBA réels 32, 64, 192 et 512 carrés ; chemins présents et tailles cohérentes | Icône 32 examinée ; pas de capture navigateur du rendu final |
| Favicon | ICO contient 16, 32, 48 et 64px ; index référence ICO + PNG 32/64 + Apple 192 | Ancien public/favicon.svg conservé mais plus référencé par l'index courant |
| PWA | Nouveau manifest : name/short_name Docnelo, icônes 192/512, display standalone, start_url=/ | Aucune preuve de service worker ni de fonctionnement hors ligne ; pas de promesse PWA supplémentaire |
| Couleurs | Tokens marine #0B1D3B, bleu #126BEE, azur #5BAAF5, menthe #3AD8B4 ; alias brand-* et certains boutons utilisent ces tokens | Import CSS bloquant ; nombreux anciens violets #8B5CF6, mint #34E4D4 et surfaces codées en dur subsistent |
| Fonds | Application dark-first #0B1120 / #151F35 ; theme-color identique | Diffère des fonds proposés #091426 / #12243D ; thème clair non implémenté par ce rebranding |
| Typographies | Segoe UI, Inter, ui-sans-serif, system-ui ; pas de @font-face ni de Google Fonts | Inter n'est ni fourni ni prioritaire. Les postes Debian/Linux peuvent afficher une police système différente |
| Business | Deux logos Business stockés dans public mais non référencés par les composants | Ils seraient néanmoins servis publiquement par la copie de public ; à exclure du lot minimal |
| Accessibilité | Alt du logo, skip-link, focus/menu clavier et reduced-motion présents | Pas d'audit exhaustif des contrastes, des lecteurs d'écran ou du zoom ; CSS désactivé dans Vitest |

Le kit est donc intégré pour le nom, le logo, les favicons, les métadonnées et une partie des couleurs. Ce n'est pas une application exhaustive de toute la charte.

## Écrans et navigation

- Connexion, inscription, récupération, reset et vérification email utilisent AccountAccess et le logo Docnelo ; les explications de compte citent Docnelo.
- Navigation commune, footer et avatar DN ont été renommés. Tableau de bord, documents/détail/analyse, bibliothèque, comparaison, paramètres IA, profil/sécurité/confidentialité sont toujours accessibles par les routes existantes.
- Assistant et paramètres IA ont reçu les nouveaux libellés. Le message d'erreur de connexion cite Docnelo.
- Les titres des écrans restent génériques ; le titre HTML est Docnelo — Votre espace documentaire. Aucun document.title par route, Open Graph ou Twitter metadata n'a été trouvé. Ce n'est pas un blocage pour ce lot.
- Le fil d'Ariane affiche toujours « Documents » pour toute route hors accueil, y compris paramètres : limite préexistante, sans correction fonctionnelle dans ce lot.
- Le badge d'environnement dépend maintenant de /bff/ui-config et UI_ENVIRONMENT_LABEL. Ce dernier n'est pas transmis par le Compose Public Beta examiné ; le badge/footer peuvent disparaître. Pour le lot statique, conserver un libellé Public Beta fixe dans le composant, sans nouvel endpoint ni variable.
- Les mentions de Beta Lite et les nouveaux parcours d'admission/suppression dans Account et Workspace sont fonctionnels. Ils ne doivent pas être sélectionnés en bloc avec les changements de marque.

## Références restantes à DocuMind

Recherche insensible à la casse dans src hors tests, index et public textuel : **trois lignes** contenant DocuMind, toutes dans documents.ts sous forme d'URL du domaine actuel (232, 331 et 349 à l'audit). Aucun autre libellé de marque DocuMind n'a été trouvé dans ces sources UI courantes. Cela ne vaut pas certification des erreurs retournées par une API réelle, du HTML externe ou des emails actifs.

| Catégorie | Références | Décision |
| --- | --- | --- |
| Visible, domaine conservé | https://documind.adelinemeistertzheim.fr et /confidentialite | Conserver selon la demande ; ne pas confondre URL avec libellé de marque |
| Visible, historique juridique | Versions de CGU antérieurement présentées/acceptées, à vérifier dans la référence déployée | Conserver leur contenu historique exact ; le nom ancien peut y rester légitimement |
| Emails de l'API de référence | Vérification DocuMind, Réinitialisation DocuMind, Ouvrez ce lien DocuMind | Restent dans une release Web seule ; correction API distincte si nécessaire |
| OpenAPI de référence | FastAPI title=DocuMind AI | Hors lot Web ; pas de contrat API à renommer dans ce déploiement |
| Technique | __Host-documind, __Host-documind-csrf, x-documind-gateway/secure/client-ip, DOCUMIND_GATEWAY_TOKEN | Conserver intégralement pour sessions, CSRF et confiance proxy |
| Technique | documind-web (NPM), documind-bff (logs), projets/labels/réseaux/volumes documind-*, DB/users, chemins Restic, tags de sauvegarde | Conserver ; aucune migration ou rotation motivée par le nom |
| Tests/docs/outils | URLs documind.test, fixtures, packaging et documentation historique | Hors libellés de l'interface active ; aucun remplacement global |

## Emails, confidentialité et textes juridiques

Les seules différences de marque backend face à l'export local sont les sujets/corps de mails dans account_api.py, le titre FastAPI dans main.py et le nom du prompt dans ai/providers.py. Le transport SMTP, l'expéditeur et les URLs sont configurés ailleurs ; ne pas les changer pour un lot Web. Aucun mail n'a été envoyé pour cet audit.

Les pages juridiques locales sont marquées brouillons non approuvés ; elles ne constituent pas une validation ni une autorisation d'inscription. Les informations d'exploitante et le domaine sont conservés. La confidentialité cite OVH, Backblaze B2 et Google/Gmail ; ce sont des déclarations des sources, dont la conformité à la configuration réelle n'a pas été vérifiée à distance.

**Point bloquant de traçabilité :** documents.ts remplace DocuMind par Docnelo dans termsArchive sans changer TERMS_VERSION=beta-2026-10-v1, ni l'identifiant beta-2026-10-26-draft-1. Le commentaire du fichier impose la conservation des versions publiées. Une modification de texte de marque ne justifie pas de réécrire une version déjà acceptée. Les identifiants de mentions/confidentialité ne sont pas renouvelés non plus. Les tests vérifient le fonctionnement des pages, pas l'immutabilité historique du contenu.

Le lot Web minimal doit donc conserver les contenus juridiques de référence et leurs versions ; une éventuelle mention Docnelo peut être présentée hors du contenu versionné. Toute nouvelle édition doit avoir son propre identifiant et rester un brouillon distinct, sans modifier les termes/admissions configurés sur l'API. Ni nouvelle approbation légale, ni PUBLIC_LEGAL_READY=true, ni ouverture d'inscription dans ce plan.

## Absence de dérive fonctionnelle : ce qui est démontré et ce qui ne l'est pas

| Domaine | État observé | Conséquence pour la release proposée |
| --- | --- | --- |
| Migrations Alembic | Aucun fichier migrations suivi modifié ; versions 0001 à 0007 présentes | Aucune commande de migration à construire ou exécuter |
| Modèles/tables | auth.py, account_models.py et modèles usuels non modifiés dans le diff suivi | Ne prouve pas absence de mutations : les nouvelles routes/lite peuvent modifier les données |
| API/auth/admissions | Nombreuses différences fonctionnelles face à HEAD ; plusieurs déjà présentes dans l'export API | Exclure tout backend de la release Web ; ne pas conclure que la branche entière est purement graphique |
| BFF | Téléchargement, deletion-status, cookie de suppression, ui-config : différences face au BFF exporté | Conserver octets et dépendances du BFF réellement actif via image de base figée |
| Frontend | Account, Workspace, services/account et api mêlent marque et fonctions | Sélection de changements textuels uniquement sur une base de provenance vérifiée ; pas de copie intégrale |
| Sauvegardes/Restic | Outils et rapports V5/V5.1 présents parmi les changements locaux | Exclusion totale du contexte de livraison Web ; ne rien relancer |
| Production/config | .env.production.example et Compose de recette modifiés ; exemples Public Beta non suivis | Exclusion totale ; ne pas recopier de .env.example |
| Inscription | .env.public-beta.example contient PUBLIC_LEGAL_READY=true et des paramètres d'ouverture | Exemple incompatible avec cette préparation ; ne pas le déployer ni l'utiliser comme base |

L'API, la DB et Restic resteront inchangés **par construction du lot proposé**, et non parce que l'arbre courant serait exempt de changements. La démonstration finale doit comparer les artefacts retenus à la référence réelle avant go.

## Tests et blocages

Voir [le rapport de tests](DOCNELO_PUBLIC_BETA_BRANDING_TEST_REPORT.md). Résultat : 123 tests réussis, aucun test échoué ; build de production échoué dans Tailwind sur l'import CSS absolu. Aucun E2E contre le VPS, aucune image construite.

Conditions de levée du NO-GO : provenance exacte de l'image Web/source ; sélection de changements statiques sans routes/nouveaux contrats ; correction de l'import CSS dans le lot isolé ; conservation des versions juridiques ; build propre ; recette navigateur CSS active sur base/API figées ; preuve du maintien des inscriptions ; manifeste et image Web immuables. Les écarts de charte non bloquants doivent être listés comme acceptés, sans annoncer une intégration totale.

## Inventaire exact

Les annexes ci-dessous sont produites depuis Git au moment de l'audit. « Modifié » signifie différence préexistante dans le workspace, pas modification effectuée par cet audit. Les trois fichiers ajoutés par cette intervention sont :

- DOCNELO_PUBLIC_BETA_BRANDING_AUDIT.md
- DOCNELO_PUBLIC_BETA_BRANDING_DEPLOYMENT_PLAN.md
- DOCNELO_PUBLIC_BETA_BRANDING_TEST_REPORT.md

### Fichiers frontend presents dans le diff : 14 modifies suivis et 14 nouveaux non suivis

| Chemin exact | Etat | Analyse |
| --- | --- | --- |
| frontend/index.html | M | Marque et metadonnees ; selection possible |
| frontend/public/brand/docnelo/docnelo-business-dark-transparent.png | nouveau | Asset non reference par UI/index actuels ; exclure du lot minimal |
| frontend/public/brand/docnelo/docnelo-business-transparent.png | nouveau | Asset non reference par UI/index actuels ; exclure du lot minimal |
| frontend/public/brand/docnelo/docnelo-horizontal-dark-transparent.png | nouveau | Asset graphique utilise dans le lot minimal |
| frontend/public/brand/docnelo/docnelo-horizontal-transparent.png | nouveau | Asset non reference par UI/index actuels ; exclure du lot minimal |
| frontend/public/brand/docnelo/docnelo-icon-192.png | nouveau | Asset graphique utilise dans le lot minimal |
| frontend/public/brand/docnelo/docnelo-icon-32.png | nouveau | Asset graphique utilise dans le lot minimal |
| frontend/public/brand/docnelo/docnelo-icon-512.png | nouveau | Asset graphique utilise dans le lot minimal |
| frontend/public/brand/docnelo/docnelo-icon-64.png | nouveau | Asset graphique utilise dans le lot minimal |
| frontend/public/brand/docnelo/docnelo-icon-transparent.png | nouveau | Asset non reference par UI/index actuels ; exclure du lot minimal |
| frontend/public/brand/docnelo/docnelo-tokens.css | nouveau | Asset graphique utilise dans le lot minimal |
| frontend/public/brand/docnelo/favicon.ico | nouveau | Asset graphique utilise dans le lot minimal |
| frontend/public/manifest.webmanifest | nouveau | Nouvelles metadonnees de marque |
| frontend/server/app.mjs | M | BFF fonctionnel + ui-config ; exclure, heriter du runtime actif |
| frontend/server/app.test.mjs | M | Tests fonctionnels ; ne pas copier en bloc |
| frontend/src/components/Assistant.tsx | M | Libelle de marque seulement (hors BOM) |
| frontend/src/components/Brand.tsx | nouveau | Nouveau composant graphique |
| frontend/src/components/Layout.tsx | M | Marque + contrat ui-config + avertissements modifies ; selection requise |
| frontend/src/components/Workspace.tsx | M | Suppression/statuts : fonctionnel, exclure |
| frontend/src/legal/documents.ts | M | Marque sous versions existantes : bloquer, conserver reference historique |
| frontend/src/pages/AISettings.tsx | M | Libelles de marque (hors BOM) |
| frontend/src/pages/Account.tsx | M | Marque + Beta Lite/admissions/suppression : selection requise |
| frontend/src/pages/BetaLite.test.tsx | nouveau | Tests fonctionnels Beta Lite, hors lot |
| frontend/src/services/account.ts | M | Contrats Beta Lite : fonctionnel, exclure |
| frontend/src/services/api.ts | M | Message de marque + contrats ui-config/suppression : selection requise |
| frontend/src/styles.css | M | Tokens/styles de marque ; build CSS bloque |
| frontend/src/test/app.test.tsx | M | Tests de fonctions et ui-config ; adapter depuis reference isolee |
| frontend/src/types/api.ts | M | Contrat UiConfig nouveau, exclure du lot statique |

### Ensemble des fichiers suivis modifies avant cet audit (42)

Cette liste complete du diff suivi sert a exclure les autres lots ; elle ne constitue pas un plan de livraison. Les gros repertoires non suivis exports/deliveries ne sont pas une source a copier. Les scripts et fichiers de production ci-dessous etaient deja modifies ; cet audit ne les a pas touches.

```text
.env.production.example
backend/account_admin.py
backend/account_api.py
backend/ai/providers.py
backend/ai/settings_api.py
backend/api.py
backend/authentication.py
backend/config.py
backend/lifecycle_durability.py
backend/main.py
backend/public_registration.py
backend/recovery_quarantine.py
backend/services/documents.py
compose.public-beta-test.yaml
frontend/index.html
frontend/server/app.mjs
frontend/server/app.test.mjs
frontend/src/components/Assistant.tsx
frontend/src/components/Layout.tsx
frontend/src/components/Workspace.tsx
frontend/src/legal/documents.ts
frontend/src/pages/AISettings.tsx
frontend/src/pages/Account.tsx
frontend/src/services/account.ts
frontend/src/services/api.ts
frontend/src/styles.css
frontend/src/test/app.test.tsx
frontend/src/types/api.ts
ops/testing/combined_restore_lab.py
ops/testing/prepare_beta_recipe.py
ops/testing/validate_beta_recipe.py
pyproject.toml
requirements.runtime.lock
requirements.test.lock
tests/fixtures/public_beta_browser.mjs
tests/test_pinned_builds.py
tests/test_snapshot_backup_integrity.py
tools/backup_local.py
tools/backup_production.py
tools/retention_production.py
tools/validate_restore.py
tools/verify_snapshot.py
```

### Documentation de marque preexistante non suivie (9)

```text
docs/docnelo/DOCNELO_BRANDING_AUDIT.md
docs/docnelo/DOCNELO_BRANDING_INTEGRATION.md
docs/docnelo/DOCNELO_BRANDING_TEST_REPORT.md
docs/docnelo/DOCNELO_PUBLIC_BETA_DEPLOYMENT.md
docs/docnelo/DOCNELO_PUBLIC_BETA_FRONTEND_AUDIT.md
docs/docnelo/DOCNELO_ROLLBACK_PLAN.md
docs/docnelo/brand-kit/CHARTE_GRAPHIQUE_DOCNELO.md
docs/docnelo/brand-kit/CHARTE_GRAPHIQUE_DOCNELO.pdf
docs/docnelo/brand-kit/apercu-declinaisons.png
```

Les anciens plans de deploiement ci-dessus ne sont pas revalides par cet audit. La reference pour ce lot est DOCNELO_PUBLIC_BETA_BRANDING_DEPLOYMENT_PLAN.md, sans volet Production.

### Images a reconstruire

| Image | Decision |
| --- | --- |
| documind-public-beta-web:docnelo-20261031-r1 (nom propose, tag neuf + ID exact/digest dans la release) | Une seule nouvelle image, statiques remplaces, runtime BFF herite de la base active |
| Image API actuellement active | Ne pas reconstruire ni recreer pour ce lot ; emails/OpenAPI reportes |
| Image PostgreSQL 17 et autres images | Ne pas reconstruire ni recreer |

