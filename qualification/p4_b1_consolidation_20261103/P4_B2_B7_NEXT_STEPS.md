# Suite B2-B7 - sans requalification historique

**BLOCKED. Aucun GO build/create/start/run/pull/import/production.**

Le scope B1 contenus est independant. Meme clos, il ne demontre ni
l'origine des fichiers P3 ni leur aptitude a la base P4. Ne pas utiliser
P3 comme base approuvee par heritage ; nouveau rootfs P4 uniquement.
Les definitions B2-B7 de v3 restent inchangees.

| Etape | Ce qui manque reellement | Critere et suite autorisable, pas autorisation presente |
|---|---|---|
|B2 - systeme Debian13 coherent |Paquets exacts/versions/arch/hashes : libc6:amd64, libgcc-s1:amd64, libstdc++6:amd64, zlib1g:amd64, puis besoins supplementaires effectifs |Source approuvee externe au labo, chaine InRelease/Release signe -> Packages -> .deb ; dep paquets et fichiers/liens traces ; selection coherente et revue avant constitution d'un rootfs neuf |
|B3 - CPython |Provenance runtime/source3.11.18, configuration, toolchain/build recipe, stdlib/lib-dynload, hashes |Archive/runtime verifie et build reproductible documente, SOABI/configuration/identite binaire ; Python3.11 du P3 ou hash identique ne suffit pas |
|B4 - natif recursif |Fournisseurs reels des89 liens systeme, chargeur et transitifs Python/stdlib, scopes globaux |Chaque DT_NEEDED/PT_INTERP -> vrai chemin/SHA/package ; verneed/verdef/symboles/relocations/TLS/IFUNC/ISA, RPATH/RUNPATH/cache, dlopen/NSS ; pas de fallback hote |
|B5 - execution cible |Bootstrap pip25.2 wheel-only, imports, pip check,43 installees exactes, ABI et ASGI |Plan de probes isolees autorise, puis preuves Debian dans l'image effectivement retenue ; jamais docker run diagnostic ni entrypoint Docnelo |
|B6 - builder et identite P4 |Driver/frontend locaux qualifies offline, recette/contexte/epoch/ownership attendus, preuve rootfs P4 -> couches -> ID final |Prouver zero resolution registry/builder pull ; build autorise distinct, logs/retours/IDs/diff IDs/export ; comparaison selon contrat P4 fige, pas selon les tolerances B1 historiques |
|B7 - revue et autorisations |Decisions de provenance/composants/recette, mandats et receipts |Revue independante puis actes separes build, create et start ; tous restent false ici ; aucun GO production |

Les familles B2 sont des candidats, pas des versions approuvees ni une
fermeture apt complete. Les besoins CPython/stdlib peuvent ajouter
OpenSSL/libffi/sqlite/bz2/lzma/etc. Ne pas copier /lib ou le venv hote.
Ne pas melanger revisions libc/chargeur et bibliotheques trouvees ailleurs.
La fusion de fonctions glibc ne supprime pas DT_NEEDED, les vraies DSO
compat et contraintes de versions/scope. Aucun faux lien libpthread/
libdl/librt vers libc ; aucun patch des dependencies pour faire passer.

Les31 liens wheel-local et1223 references versionnees coherentes de v3
sont conserves comme preuves existantes. Ne pas les refaire sans bytes
changes ou lacune identifiee. Les2210 references non versionnees sans
scope prouve ne sont pas2210 erreurs : elles requierent notamment le
vrai contexte Python/chargeur. L'egalite de contenus P3 n'apporte pas
ces fournisseurs ni leurs paquets d'origine.

## Ordre et points d'arret

1. Revue des materiaux B2/B3, puis fermeture B4 statique et plan des
   preuves cibles. ARRET si absent/non qualifie. Livraison de materiaux
   neuve et scellee ; jamais de correction en place de P3/v1/v2/v3.
2. Qualifier B6 offline et faire revoir la recette complete en B7.
   Une pin/digest, --pull=false ou --network=none seul n'exclut pas les
   resolutions du frontend/builder. Aucun Dockerfile executable ici.
3. **Autorisation build** distincte avec perimetre/ID de demande, outils,
   materiaux et limites, puis build controle. Les probes cibles qui
   exigent un processus ne sont pas considerees faites avant ce build.
4. **Autorisation create** distincte : nouveau namespace P4 synthetique,
   ID approuve/pull never, reseau none, aucun port/socket, non-root/GID
   lecteur, cap-drop ALL, no-new-privileges, rootfs RO, limites CPU/RAM/
   swap/pids, candidat et controle RO, evidence neuve0700 RW, tmpfs/tmp.
5. Inspect complet du conteneur jamais demarre, sources/montages/
   alias/permissions/USER/groupes/entrypoint/environment exacts ;
   **autorisation start** distincte. Un echec d'inspection interdit start.
6. Preuves B5 sur cette cible, arret controle et receipts numeriques.
   Standard/beta_lite restent ceux du protocole r3/v1 : RCD_EVENT,
   publication atomique post-startup, closed/sentinel,503 distincts des403
   Lite. Aucune campagne historique relancee et aucune execution ici.

Une probe de composants prealable sur une autre cible necessite elle
aussi un mandat separe, create/inspect/start si conteneur, pas un
contournement pour realiser B5 sans autorisation. Les resultats sont
ensuite confirmes sur l'image finale ; ne pas creer une condition
circulaire exigeant des preuves post-build avant tout mandat build.

La future comparaison P4 doit declarer avant build les UID/GID, modes,
mtimes, liens et traitement de racine attendus. Les10334 differences
1000->0 historiques ne sont **pas une tolerance automatique P4**.
Le constructeur et le comparateur devront correspondre au format reel,
sans modifier les exigences ou outils historiques pour obtenir PASS.
