# Sprint 14.6.1 — Sécurisation du rollback, B14-10

26 octobre 2026. Travail exclusivement local depuis les 58 fichiers modifiés/non
suivis des phases précédentes, inventoriés et hachés avant intervention. Branche
conservée : `preparation/sprint-14-5-ux-email-abuse`. Base de production annoncée :
`8243e0511c5505a9cc70f76ad02392f7a816590d`, schéma 0007. Les rapports 14.1 à 14.6
et le runbook 14.7 ont servi de référence ; aucune opération distante.

**B14-10 est corrigé localement dans les chemins de livraison pris en charge.**
Ce résultat ne constitue ni une certification cryptographique d'origine ni une
autorisation de publication/déploiement. Aucun compte réel, secret ou document de
production ; aucune activation des inscriptions ou de l'IA ; aucune migration nouvelle.

## 1. Cause démontrée et chemins audités

Avant correction, les trois nouveaux tests négatifs échouent : `can_rollback()`
renvoie true pour un candidat 0007 sans attestation, avec un profil autodéclaré ou
avec un profil inventé. La fonction ne contrôlait que `supported_schema_revisions`.

Chemins identifiés :

1. `execute(..., rollback=True)` : candidat manuel compatible au schéma seulement.
2. Bloc d'erreur : `previous.call('up', ..., 'api', 'web')` après échec de backup,
   migration, démarrage ou HTTPS ; fermeture SQL ne prouvait pas les fixes du binaire.
3. Workflow : exécution de `$TARGET/deploy_production.py`, donc code du candidat,
   éventuellement ancien et ignorant les nouveaux contrôles.
4. Correction en avant/récupération : ancien current conservé après refus de retour.
5. Sauvegarde quotidienne et `--resume`/`ExecStopPost` : reprise de ce current ancien,
   susceptible de contourner indirectement le refus du déployeur.

Les fonctions de récupération `--recover-from`/`--recover-after-https` ne redémarrent
pas leur source défaillante ; la nouvelle cible passe les mêmes contrôles renforcés
si le contexte les exige. Leurs vérifications de chaîne, schéma, mounts/images et
PostgreSQL conservé ne sont pas supprimées.

## 2. Politique : compatibilité et autorisation distinctes

`schema_compatible()` ne fait qu'un contrôle structurel de révision.
`can_rollback()` refuse désormais par défaut sans preuve indépendante ; une valeur
de schéma ou un champ de manifeste ne constitue jamais cette preuve.

Le profil reconnu est **`public-beta-2026-10-v1`**, pour le schéma **0007** et les
correctifs applicatifs 14.2–14.5 complétés par les guards 14.6.1. Il ne certifie pas
juridiquement la bêta, la délivrabilité SMTP, les CVE actuelles ou une configuration
de production réellement observée.

La politique renforcée s'applique :

- à tout rollback manuel, même en mode disabled ;
- aux livraisons/retours avec source ou cible publique ;
- si une identité publique existe, **même bloquée, en attente ou désactivée**, ou
  si le compteur cumulatif est positif, même après disparition des identités ;
- si la cible ou le current adopte le nouveau profil ;
- si un marqueur de maintenance de sécurité persiste.

La détection lit le SQL réel, pas seulement `REGISTRATION_MODE`. En 0007, une ligne
absente, JSON invalide ou état incohérent est refusé, sans repli historique. Le mode
effectif résolu du précédent est aussi contrôlé : `approve_public_beta` ne permet
pas de masquer une source publique derrière une cible disabled.

Lorsque source/cible publique ou histoire publique l'exige, le déployeur exige le
verrou SQL fermé et un compteur valide. Il ne modifie ni `issued_count`, ni la
limite, ni le verrou. Fermer reste une action opératrice préalable. `initialize`,
`allow_migration` et `approve_public_beta` ne dispensent jamais d'autorisation.

**Compatibilité historique :** les opérations ordinaires fermées, sans passé public
et sans adoption de profil peuvent continuer avec des manifests historiques. Une
reprise automatique de ce contexte privé peut rester autorisée par compatibilité
de schéma, explicitement rapportée comme legacy non certifié. Ce n'est pas un moyen
de revenir après adoption du profil ou avec des données publiques. Un rollback manuel
historique non attesté est désormais refusé : incompatibilité volontaire documentée.

## 3. Attestation et véritable ancre de confiance

### Déclaration produite par CI

`release_manifest.py --security-profile public-beta-2026-10-v1` ajoute une déclaration
de profil reconnue, sans changer le format 1 ni accepter un autre schéma pour v1.
`release_security.py create` génère `security-attestation.json` après publication
des trois digests et copie des fichiers. Le statement comprend :

- SHA complet et profil, schéma 0007 et références exactes backend/frontend/postgres ;
- repository, chemin `.github/workflows/ci.yml`, run et tentative de production ;
- SHA-256 des huit fichiers immuables : manifeste, Compose, déployeur, helper backup
  local, orchestrateur backup, validateur de manifeste, politique publique et
  module de sécurité.

Le bundle CI comprend donc **neuf fichiers** avec le statement. `images.env` et les
rapports d'exécution restent des sorties séparées, non modifiées pour les « certifier ».
Les trois images reçoivent le label de profil en plus du label de révision. Docker
les référence par digest ; le déployeur vérifie les labels des images correspondantes.
Un label seul n'est pas une autorité. Les exceptions historiques de PostgreSQL
retenu dans une récupération restent explicitement suivies par le digest source
et le rapport existant ; le profil vise les garanties applicatives, pas une nouvelle
certification de sécurité du serveur PostgreSQL conservé.

### Approbation extérieure au bundle

L'ancre est `/etc/documind-ai/release-security-trust.json`, chemin fixe non substituable
par env ou flag. Fichier régulier, root, non inscriptible groupe/autres, répertoire
root non inscriptible groupe/autres et non symlink ; ouverture no-follow sous Linux.
Lecture bornée, JSON sans clés dupliquées. Les fichiers de preuve du bundle sont
eux aussi bornés, réguliers, non symlink et vérifiés par checksum.

Schéma du registre (valeurs fictives, pas une approbation à installer) :

```json
{
  "format": 1,
  "releases": {
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {
      "profile": "public-beta-2026-10-v1",
      "attestation_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "repository": "example/documind",
      "workflow": ".github/workflows/ci.yml",
      "run_id": "123",
      "run_attempt": "1"
    }
  }
}
```

L'opératrice doit vérifier **séparément** l'origine réelle : repository, SHA, workflow
revu sur main protégé, run/attempt réussi, tests, digests et contenu des fixes, puis
approuver le hash exact du statement. Modifier le SHA, les digests, un fichier du
bundle ou fabriquer un nouveau statement change cette empreinte et ne donne aucune
approbation root. Un ancien bundle ne peut donc pas s'autoriser avec un simple champ.

`check` vérifie seulement structure/checksums et le dit explicitement ; `propose-trust`
produit une proposition sans écrire `/etc`, approuver une origine ou modifier un
registre existant. Aucun secret/signing key nouveau, aucune installation réelle.

**Limite assumée :** il n'y a pas de signature cryptographique CI/Sigstore. Les
SHA-256 prouvent l'intégrité relativement au registre approuvé, pas l'origine par
eux-mêmes. La provenance repose sur GitHub consulté par canal authentifié, la revue
et l'administration du registre. Compromission du CI, du root hôte ou d'un compte
Docker privilégié n'est pas résolue par ce mécanisme. Ne pas présenter cela comme
une attestation cryptographique autonome.

## 4. Contrôleur indépendant et vérifications répétées

Le workflow conserve ses vérifications d'environnement protégé, source CI réussie,
SHA et repository. Il contrôle le statement localement, puis copie un contrôleur
du **checkout actuel de main** dans un chemin `deploy-controls/...` distinct.
Il exécute ce contrôleur avec `--bundle TARGET`, jamais le script d'un ancien TARGET.
Le rapport est écrit dans le bundle cible, sans écraser une tentative précédente.

Les opérations ordinaires avec anciens artefacts 5/6 fichiers restent lisibles ;
public et rollback manuel exigent le nouveau bundle. Aucune publication sur PR,
aucun déploiement sur simple push, aucune modification des trois gates CI obligatoires.

L'autorisation est vérifiée avant pull/arrêt/migration puis avant démarrage et avant
activation de current ; elle est relue avant fallback. La révocation d'une entrée
du registre ou l'altération du bundle bloque la reprise. Le candidat doit être
compatible au schéma **et** autorisé. Tous les contrôles Host/HTTPS/CSRF, réseau,
images, sauvegardes, approbation migration et pointeurs restent présents.

Le déployeur impose aussi que les scripts **installés root**
`ops/backup_production.py` et `ops/release_security.py` correspondent aux hashes de
la version approuvée. Il refuse sinon avant arrêt des services renforcés. Cette
condition nécessite une future mise à jour explicite des outils ops ; déployer
seulement les images ne suffit pas.

## 5. Échec, sauvegardes et correction en avant

Avant de stopper une application sous politique renforcée, le contrôleur crée
`var/security-maintenance.json` sous verrou commun. Le fichier ne contient que des
métadonnées techniques, aucun secret. Une reprise ne réécrit pas les preuves de la
tentative antérieure. Si son contenu change, le contrôleur refuse de le supprimer.

En cas d'échec : arrêt d'API/BFF de la cible, aucun stop/drop/rm PostgreSQL, aucune
restauration ou descente de schéma automatique. Le précédent n'est démarré que si
ses propres preuves, son profil, ses images, son schéma, sa configuration et les
guards installés sont acceptés, avec contrôle de santé. Sinon les applications
restent arrêtées et le marqueur reste en place, même si current désigne encore
l'ancienne release. Aucun current artificiel n'est créé.

La sauvegarde, son préflight, son `restart()` et son `--resume` refusent ce marqueur.
Cela ferme le chemin indirect via ExecStopPost. En fonctionnement normal, le préflight
et la reprise relisent aussi le contexte SQL, l'approbation du current et ses labels
depuis le module ops **installé**, jamais depuis un module fourni par current.
Une sauvegarde normale reprend la même version certifiée et conserve le quota
ouvert ou fermé ; elle ne réalise pas une fermeture de bêta à chaque nuit.

Après succès et santé/HTTPS validés, ou retour certifié réellement healthy, le
contrôleur retire son propre marqueur. La correction en avant utilise un nouveau
bundle attesté/explicitement approuvé, compatible 0007, via le contrôleur actuel.
Une maintenance de sauvegarde préexistante ne peut pas être supprimée pour forcer
cette opération : elle nécessite une revue distincte, surtout si le current a été révoqué.

Les timers, Restic, secrets, rétention en simulation et verrou partagé ne changent
pas. Le patch ops ne lance aucune migration, aucun transfert B2 ou email réel.

## 6. Définition et obtention d'un secours sûr

Un secours admissible doit posséder :

1. Correctifs 14.2–14.5 et guards 14.6.1 revus, schéma 0007 effectivement supporté.
2. CI requise réussie, trois digests immuables, statement complet et cohérent.
3. Approbation indépendante exacte dans le registre root, non révoquée.
4. Images correspondantes vérifiées et deux helpers ops compatibles exactement avec
   ceux installés. Des helpers plus anciens/différents sont refusés par défaut.
5. Configuration autorisée et, pour un retour en contexte public, quota fermé cohérent.

Le préparer par une **future** publication CI d'une version corrigée, revue et
approuvée, puis installation coordonnée du registre/helpers. Aucun candidat n'est
certifié maintenant : le code local non commité et les images d'overlay de recette
ne sont pas des releases CI. Sprint 13 ne devient pas sûr en ajoutant un label ou
une entrée inventée. Aucun retagging ni rétro-certification.

Lors du premier déploiement corrigé, un précédent attesté peut ne pas exister :
accepter explicitement l'arrêt sûr et préparer une correction en avant. À l'avenir,
conserver au moins un secours corrigé avec les mêmes versions de guards ops ; si
les helpers évoluent, requalifier les secours avant livraison, pas en pleine panne.

## 7. Tests exécutés et portée

| Campagne | Réussis | Ignorés | Échoués |
| --- | --- | --- | --- |
| Reproduction négative initiale B14-10 | 0 | 0 | 3, avant correction |
| Windows ciblé final sécurité/déploiement/14.2/backup | 266 | 5 | 0 |
| Linux Docker, même sélection en processus root jetable | 268 | 3 | 0 |
| PostgreSQL Docker, sécurité + concurrence + 14.2–14.5 + backups | 330 | 2 | 0 |
| Windows Python 3.13.7, suite complète finale | 755 | 68 | 0 |
| Confinement Docker, utilisateur applicatif | 72 | 0 | 0 |

Les totaux se recouvrent, ils ne s'additionnent pas comme des tests distincts.
La suite complète finale dure 599,81 s. Les 68 ignorés sont les 40 tests Linux
natifs, 11 tests PostgreSQL, six snapshots Docker, huit E2E opt-in et trois tests
de propriété de fichiers spécifiques Linux/root/non-root. Ils ne sont pas attribués
comme réussis à Windows. Les tests root/non-root/PG propres à cette correction
sont exécutés dans les campagnes dédiées. Une première collecte complète intermédiaire
(750 réussis/68 ignorés) précède les derniers scénarios ops ; seule la seconde est
présentée comme suite complète finale. Aucun timeout applicatif n'est augmenté.
Windows ciblé : 2 tests root, un test Linux non-root et 2 tests PG ignorés.
Docker root : test non-root et les 2 tests PG ignorés. PG (utilisateur applicatif) :
seuls les 2 tests root sont ignorés. Les tests root sont réellement exécutés dans
le conteneur séparé sans réseau, volumes, capacité privilégiée ou secret ; aucun
fichier `/etc` de l'hôte n'est créé. Le processus non-root prouve le refus d'un
registre appartenant à l'utilisateur ordinaire.

Cas couverts : anciennes releases 0007 non attestées, faux profil, bundle incomplet,
checksum/SHA/digest/producteur incorrect, statement régénéré non approuvé, révocation,
permissions/symlinks root, rollback approuvé, absence de secours, schéma incompatible,
source publique derrière cible disabled, flags non substituables, données publiques
bloquées ou compteur positif, source current certifiée, maintien du marqueur et
refus backup/resume, reprise normale sans mutation du quota, validation du vrai
code du step CI sur un bundle généré, contrôleur distinct du candidat.

Le test PostgreSQL insère une identité **fictive bloquée** avec compteur toujours
zéro ; la politique détecte son existence. Après fermeture opératrice de la base de
test, son autorisation n'émet que des SELECT. Les neuf entrelacements PostgreSQL
14.4, le verrou 14.2 et la désactivation IA passent dans la campagne PG.

Les premiers harnais ont nécessité corrections : variable lambda masquant `args`,
fixture de bundle plat oubliant le module nouveau, simulateur de quota basé sur
un nombre d'appels devenu périmé et objet ActiveRelease fictif sans root/préflight.
Les fixtures sont adaptées aux préconditions réelles ; aucun contrôle de sécurité
n'est assoupli. Les confirmations ci-dessus utilisent les sources corrigées.

Les simulations du déployeur ne lancent ni Registry/SSH, ni vraie livraison Docker
de trois images publiées. Les preuves root utilisent des fichiers et données CI
fictifs ; elles vérifient la politique, pas la disponibilité des approbations futures.
Pas de suite frontend/BFF ou E2E applicatif relancée dans ce lot : leurs sources
sont inchangées et les preuves 14.6 restent distinctes. Aucune CI distante déclenchée.

Commandes principales exécutées, dossiers temporaires neufs, sans cache pytest :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_security.py tests/test_deployment.py tests/test_public_beta_authorization.py tests/test_production_backups.py -q -p no:cacheprovider --basetemp=var/pytest-14-6-1-freeze --tb=short
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=var/pytest-14-6-1-windows-final --tb=short
```

Linux utilise une image **locale de test non publiable**, construite hors ligne
avec le Dockerfile de recette 14.6, tag `documind-s14-6-1-proofs:local`. Vérifications
root : réseau none, root uniquement pour créer des fichiers réellement root sur
tmpfs, rootfs readonly, capacités ALL supprimées et no-new-privileges. Confinement :
mêmes restrictions, **utilisateur applicatif**. PG : utilisateur applicatif, réseau
interne neuf `s14-6-1-security-9ca2`, PostgreSQL/pgvector neuf sur tmpfs, aucun port
publié. Commandes Docker explicitement dirigées vers le pipe local Desktop.

La sélection PG contient `test_release_security.py`, les tests publics/concurrence/
state/autorisation/IA fermée/déploiement/backups. Le SQL d'histoire est exécuté contre
le vrai PostgreSQL, pas SQLite. Aucune suite Linux complète nouvelle n'est revendiquée
à partir de ces sélections ; la suite Linux complète 14.6 reste un résultat antérieur.
Les warnings Starlette/httpx préexistants restent visibles.

Après les campagnes, le conteneur `s14-6-1-security-pg-9ca2` et son seul réseau ont
été arrêtés/supprimés après contrôle des labels et de l'absence de montage persistant.
Les conteneurs de preuve étaient `--rm`. Aucun conteneur/réseau de cette mission ne
reste ; image de test et preuves fictives privées conservées dans le workspace/`var/`.
Le registre root testé n'a jamais été installé sur Windows ni sur le VPS.

## 8. Fichiers et préservation

| Fichier | Changement 14.6.1 |
| --- | --- |
| `tools/release_security.py` | Statement CI, checksums, registre root indépendant, propositions sans approbation automatique. |
| `tools/release_manifest.py` | Profil facultatif reconnu et option CI ; ancien format lisible sans certification. |
| `tools/deploy_production.py` | Contrôleur/candidat séparés, contexte SQL, autorisations et images, fallback fermé et maintenance. |
| `tools/backup_production.py` | Verrou de sécurité et réautorisation du current avant reprise/backup ; comportement historique conservé. |
| `.github/workflows/ci.yml` | Labels, manifeste profilé et bundle neuf à neuf fichiers ; gates et architectures inchangés. |
| `.github/workflows/deploy.yml` | Validation du statement et exécution du contrôleur actuel indépendant du bundle. |
| `tests/test_release_security.py` | Matrice négative/positive, vrai registre root et PostgreSQL, provenance locale du workflow. |
| `tests/test_deployment.py` | Séparation schéma/sécurité et simulateur de lecture d'histoire. |
| `tests/test_public_beta_authorization.py` | Fixture réellement attestée, import plat et simulation déterministe de dérive après backup. |
| `tests/test_production_backups.py` | Préconditions du nouveau préflight de reprise. |
| Runbook 14.7 et ce rapport | Approbation, bootstrap ops, limites et procédure sans secours. |

Les autres fichiers des lots précédents sont préservés. Aucun code d'inscription,
authentification applicative, quota, IA, sandbox, Compose de production ou migration
n'est changé par 14.6.1. Aucun fichier n'est indexé/commité ; aucun push/merge, accès
VPS, activation de service/timer, changement de secret ou publication d'image.

Contrôle final : **52 des 58 fichiers initialement modifiés/non suivis sont strictement
identiques**. Les six autres sont étendus intentionnellement : workflows CI/deploy,
déployeur, tests de déploiement/autorisation et runbook. Trois fichiers auparavant
propres sont modifiés (manifest, orchestrateur backup et son test) et trois fichiers
sont nouveaux (module de sécurité, tests dédiés et ce rapport), soit 64 chemins en
cours au total. Aucune modification précédente n'est retirée ou réinitialisée.
Syntaxe AST Python, parsing YAML des workflows, imports plats et `git diff --check`
réussissent. Aucun accès distant n'a été nécessaire pour ces contrôles.

## 9. Verdict et prérequis futurs

Rollback manuel : **refus fermé sans attestation et approbation**. Reprise automatique :
**mêmes exigences en contexte renforcé**, y compris disabled avec histoire publique,
et protection du chemin backup/resume. Aucun secours disponible n'est inventé.

**Le correctif est prêt pour une revue Git locale**, avec les limites de confiance
et les prérequis d'exploitation explicités, après les campagnes finales réussies.
Avant une future publication : revue de tous les fichiers non commités, audit CI,
acceptations de risques adaptées à cette publication (ne pas réutiliser RF10-03),
puis autorisations explicites. Avant déploiement : registre root réellement revu,
mise à jour des deux scripts ops, contrôle du candidat et du secours, recette des
digests publiés et Linux 6.12/ABI 6. Les dépendances/délivrabilité SMTP, textes légaux,
sauvegarde/restauration et surveillance restent des validations séparées.

**L'ouverture publique reste No-Go.** La protection locale n'autorise aucune opération
distante et ne transforme pas un ancien déployeur ou une ancienne sauvegarde en
composant certifié sans mise à jour/approbation effective.
