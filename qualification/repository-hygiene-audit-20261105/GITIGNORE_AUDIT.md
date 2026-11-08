# Audit des exclusions

Proposition uniquement; `.gitignore` et `.git\info\exclude` ne sont pas modifies.

## Regles effectives

`.gitignore:1-18` couvre `.venv`, `.ci-venv`, le build racine, `__pycache__`,
`*.pyc`, `.pytest_cache`, `.env`, `.env.production`, `.env.*.local`, `var`,
egg-info, `.coverage`, node_modules, dist/tsbuildinfo/rapports Playwright du
frontend et `var/tls`.
`.gitignore:20-33` exclut des familles documentaires privees precises.
`.gitignore:35-36` exclut une experience Cloudflare autonome.
Ne pas retirer ces protections en les prenant pour du code mort.

`.git\info\exclude:7-20` comporte des exclusions locales de R2, de l'archive API
active, de la candidate lifecycle dix admissions et de diagnostics Compose.
**Ces exclusions cachent des travaux utiles et des preuves, pas seulement du bruit.**
Elles ne sont pas transportees par un clone; les sauvegarder avec le contexte Git.
Les `.gitignore` des sources historiques restent inchanges.

Aucun `core.excludesFile` configure n'a ete trouve dans les portees examinees.
`core.ignorecase=true`; `core.autocrlf=false` utilisateur prend le pas sur le
reglage systeme true. Pas de `.gitattributes` suivi. Ne pas introduire maintenant
une normalisation de fins de ligne qui changerait les empreintes des preuves.
Aucun des 338 chemins suivis ne correspond aux exclusions actuelles.

## Lacunes verifiees

`git check-ignore -v --no-index --stdin -z` a confirme la couverture du cache
Python et de la candidate localement exclue. Les exemples ci-dessous n'avaient
pas de regle applicable; certains sont des chemins synthetiques, pas des fichiers
dont l'existence serait affirmee.

| Motif propose | Justification et limite |
|---|---|
| `/.mypy_cache/`, `/.ruff_cache/` | Caches racine regenerables; pas d'installation d'outil |
| `/.coverage.*`, `/htmlcov/` | Mesures locales racine; ne pas cacher les rapports de qualification |
| `/venv/` | Environnement racine alternatif, sans ignorer les wheelhouses de preuve |
| `/frontend/.next/`, `.vite/`, `.cache/`, `.nyc_output/`, `coverage/` | Sorties locales du frontend uniquement; `.next` est preventif, le projet actuel utilise Vite |
| `/.env.*` avec exceptions de modeles | Protege de futures variantes privees a la racine, preserve `.env.example` et `.env.*.example` |
| `/deliveries/docnelo-web-branding-r1/npm-cache/` | 596 fichiers de cache en attente; sauvegarde prealable, aucune suppression |
| `/deliveries/docnelo-signup-e2e-lab/tls/lab.key` | Candidat cle privee non suivi actuellement visible; contenu non inspecte |

Les barres obliques dans les motifs sont la syntaxe Git, pas des chemins de
commandes PowerShell. Le patch joint n'ajoute ni `*.sql`, ni `*.db`, ni `*.key`
global, ni `*.log`, ni exclusion generale de `dist`, `docs`, `qualification`,
`deliveries`, `exports` ou `candidates`.

## Preuves et sorties de build

Les 27 fichiers dist visibles ne sont pas assimilables au cache npm.
`deliveries\docnelo-web-branding-r1\payload\DOCNELO_PUBLIC_BETA_BRANDING_R1_FILE_INVENTORY.md:30-50`
ancre 13 artefacts statiques et conserve explicitement un favicon historique.
La reproductibilite suppose aussi les dependances disponibles hors ligne;
une etiquette « cache » ne dispense donc pas de sauvegarde avant decision.

Conserver migrations, fixtures non sensibles, modeles d'environnement, manifestes,
recus, rapports, sources candidates et livraisons scellees.
Les bases runtime et WAL/SHM sous `var` sont deja exclus; une base ailleurs
necessite une decision par chemin, pas un motif global qui cacherait des fixtures.
Les certificats ne sont pas automatiquement des cles privees.

## Effet attendu et autorisation

Le patch est volontairement limite : le cache npm et la cle candidate expliquent
597 entrees actuellement visibles; les autres ajouts sont preventifs ou preserves
par les exceptions. L'essentiel des 4 236 entrees restera a classer et conserver.
Une simulation des regles et un controle `git apply --check` sans application
font partie de la verification documentaire de cette proposition.

Ne pas faire `git add .`, `git rm --cached` ou appliquer le patch dans cette phase.
Une regle d'exclusion ne retire pas un fichier deja suivi, ne purge pas
l'historique et ne securise ni une copie filesystem ni une archive.
