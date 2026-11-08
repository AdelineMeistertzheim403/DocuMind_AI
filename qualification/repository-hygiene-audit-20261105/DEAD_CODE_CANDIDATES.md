# Candidats au code mort - aucune suppression

Analyse statique de 303 fichiers de code/tests hors instantanes ignores, sans
importer l'application; 2 536 definitions de fonctions Python analysees, aucune
erreur de parsing dans ce perimetre. References textuelles, routes, CLI,
chargements dynamiques, migrations, tests, procedures et copies historiques
ont ete confrontes aux alertes. Pas de graphe dynamique exhaustif.

La confiance est celle du statut indique. Aucun fichier ne devient supprimable
sur la seule absence d'import ou de reference statique.

| Chemin et statut | Role et references constatees | Indice d'inutilisation / risque | Confiance / verification restante |
|---|---|---|---|
| `analyseur_documents\ui\interface_helpers.py:449-530`, `creer_figure_analyse` : **PROBABLEMENT_INUTILISÉ** | Ancienne figure composite; aucune reference externe trouvee dans les sources actives/tests/procedures inspectes. `interface.py:20-22,448-451` utilise maintenant `creer_figures_analyse` au pluriel. La definition existe dans des copies historiques. | Variante remplacee dans l'UI courante. Risque beta direct faible, mais compatibilite desktop/API Python externe inconnue. | 8/10; rechercher consommateurs externes et historiques autorises, tester UI/export desktop; conserver copies scellees |
| `analyseur_documents\core\analyseur_phrases.py:531-545`, `decouper_phrases` : **À_EXAMINER** | Wrapper retournant les chaines de `decouper_phrases_details`; aucune reference externe exacte trouvee dans le perimetre actif. La variante detaillee est utilisee dans le module. | Peut etre une API de compatibilite publique d'un package distribue. Risque moyen; pas une preuve de mort. | 6/10; verifier usages desktop/outils externes, versions distribuees et contrat public avant deprecier |
| `.tmp_patch_backup_local.py`, `.tmp_patch_backup_local_v4_v5.py`, `.tmp_patch_validate_restore.py`, `.tmp_patch_verify_snapshot.py`, `.tmp_rework_backup_local_keys_flag.py` : **À_EXAMINER** | Scripts racine de remplacement de source; le premier cible backup_local et v4 vers v5 (`:1-18`). Aucun appel courant trouve dans code, tests ou procedures examines. | Noms temporaires, mais trace possible d'un travail non integre. Reexecution dangereuse; risque de perte de provenance moyen. | 8/10 sur role temporaire, pas sur suppression; sauvegarder, comparer transformations aux sources et archiver apres accord |
| `main.py:1-12`, `analyseur_documents\ui\interface.py` : **UTILISÉ** | Entree desktop directe et `AnalyseurApp`; extras desktop dans `pyproject.toml`. | Hors chemin API courant ne signifie pas inutilise pour le produit desktop. | 10/10 sur reference; decision produit distincte avant abandon du desktop |
| `analyseur_documents\core\analyseur.py` : **UTILISÉ** | Import differe depuis `backend\services\worker.py:22-32`. | Renommage du produit ne supprime pas le moteur historique. | 10/10; conserver tests d'analyse et extraction |
| `documind_extractor\runner.py:1-52` : **UTILISÉ** | Point d'entree isole `-I -S`, imports differes engine/sandbox; courtier `backend\services\extraction.py`. | Un import Python ordinaire n'est volontairement pas le mode d'appel. | 10/10; conserver essais Linux d'isolation et limites |
| `backend\accounts.py:17-50` : **UTILISÉ** | CLI `python -m backend.accounts`, reference `README.md:85`; creation compte distincte de l'API HTTP. | Ne pas confondre accounts et account_api. | 10/10; verifier procedures avant tout remplacement |
| `backend\maintenance.py:59-90`, `backend\ai\maintenance.py:13-41` : **UTILISÉ** | CLI et tests lifecycle/transactions pour le premier; procedure AI pour le second. Reconciliation stockage et budget AI sont deux roles differents. | Faible indegre d'import normal pour des CLI; risque suppression eleve. | 10/10 sur references; ne pas executer les commandes de maintenance pendant cet audit |
| `tools\historical_pre_v3.py:17-53`, `historical_pre_v3_backup_source.txt` : **HISTORIQUE_A_CONSERVER** | Helper charge par `exec` apres verification de son SHA-256 et blob Git; `tests\test_historical_pre_v3.py`, rapport RC. | Le fichier texte est du code intentionnellement fige, pas un document inutile. | 10/10; ne pas moderniser la copie historique |
| `migrations\env.py:1-8` et `migrations\versions` : **UTILISÉ** | Alembic decouvre les revisions; imports models a effet d'enregistrement de metadonnees. | Aucun appel direct d'une fonction upgrade n'est attendu dans l'application. | 10/10; ne pas executer ni retirer de migration |
| `frontend\src\pages\Analysis.tsx` : **UTILISÉ** | Import lazy dans `frontend\src\App.tsx:17`, route `:40`. | Faux positif si recherche des seuls imports statiques. | 10/10; conserver test navigation et chunk |
| `frontend\src\pages\IntelligentLibrary.tsx`, `CompareDocuments.tsx`, `AISettings.tsx` : **UTILISÉ** | Imports et routes `App.tsx:12-14,41-47`. | Fonctionnalite desactivee ou non exposee au profil beta n'implique pas code mort. | 10/10 sur routage, pas sur autorisation metier |
| `backend\account_api.py:286-295`, `backend\ai\settings_api.py:85-152`, routes `backend\api.py` et `backend\rag\api.py` : **UTILISÉ** | Decorateurs de route; routers inclus dans `backend\main.py:192-197`. | Fonctions non appelees par nom en interne mais invoquees par HTTP. | 10/10; verifier contrats HTTP, pas supprimer sur un resultat AST |
| `tests\conftest.py:25-47` : **UTILISÉ** | Hooks et fixtures decouverts par pytest. | Autres faux positifs de recherche de references. | 10/10; conserver protections des tests |
| `deliveries`, `exports`, `candidates`, qualification P4 : **HISTORIQUE_A_CONSERVER** | Sources et tests attaches a des manifestes/rapports; 346 groupes de copies source/tests identiques en attente. | Duplication de bytes volontaire pour provenance. Une copie non importee par le HEAD n'est pas morte. | 10/10 sur conservation; cataloguer par candidate et empreinte |
| Cache npm R1 : **GÉNÉRÉ** | 596 fichiers de cache, distincts des sources et distributions R1. | Candidat exclusion, pas suppression automatique; disponibilite offline a preserver. | 9/10; sauvegarder et verifier fermeture des materiaux avant abandon |
| Dist R1/reference/export : **GÉNÉRÉ** | 27 fichiers, dont distribution R1 inventoriee par empreintes. | Genere et historique peuvent etre vrais simultanement; aucun retrait propose. | 10/10 sur generation; conserver evidence de runtime |

La recherche des exports de fonctions/constantes/classes dans le frontend courant
n'a pas isole de declaration qui ne soit mentionnee que par sa definition dans
ce perimetre. Ce n'est pas une preuve de couverture des styles, routes effectives,
plugins, imports construits ou consommateurs externes.

**Conclusion : aucune suppression de module a faible risque n'est demontree.**
La fonction de figure ancienne est le candidat le mieux etaye pour une future
deprecation localisee; ne pas supprimer son fichier, le package desktop ni ses
copies historiques. Aucun ancien endpoint ou test ne peut etre retire avec
assurance sur la seule base de cet audit.
