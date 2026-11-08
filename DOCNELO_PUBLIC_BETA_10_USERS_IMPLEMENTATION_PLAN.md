# Docnelo Public Beta — Plan de préparation à dix admissions

31 octobre 2026. Statut : **préparation uniquement, ouverture NO-GO**. Aucun patch applicatif, fichier .env, image, volume, migration, outil de sauvegarde, document juridique actif ou latch existant n’est modifié par ce travail.

## Ordre des lots séparés

1. **Attester l’API réelle.** Collecter ID/plateforme/labels, empreintes des modules d’admission/configuration/admin/lifecycle, profils et flags non secrets, révision SQL, schéma du quota et agrégats de comptes. Comparer aux deux inventaires locaux. Un succès verify-state de R2 prouve la stabilité API pendant la bascule, pas son origine ni son aptitude à dix admissions.
2. **Décision de cohorte.** Dix admissions publiques cumulatives au total ; conserver toutes les admissions déjà attribuées, y compris comptes supprimés/non vérifiés et réserves incertaines. Si l’objectif porte sur dix personnes/comptes tous modes confondus, définir aussi le traitement des comptes historiques et invités avant toute ouverture. Pas de quota de connexions simultanées implicite.
3. **Protocole lifecycle dix, release API/outillage dédiée.** Faire approuver la sécurité de mutations réelles ; conserver les gardes existantes tant que cette approbation manque. Étendre les bornes de façon explicite, versionner le protocole/ancre si la capacité entre dans le payload signé, migrer les tables SQLite existantes sans recréer les historiques. Préserver séquences, user_id, clés, HMAC, droits, watermark, états pending/settled et preuves de restauration. Produire tests 6..10, 11, concurrence, crash, commit incertain, ancien backup, ancre plus récente et retour arrière. Les fichiers SQLite de cinq ne deviennent pas compatibles par CREATE TABLE IF NOT EXISTS.
4. **Administration et livraison.** Concevoir une commande revue de réouverture à dix avec verrou de ligne, dry-run, état lifecycle cohérent et accord explicite. Préserver l’opération close et l’invariant jamais de décrément/reset. Actualiser la politique de livraison Public Beta et inventorier l’impact des gardes à cinq ; ne pas modifier les outils Production dans ce lot. Définir le traitement de l’ancien outillage si des compteurs >5 le font refuser.
5. **Juridique.** Préparer de nouveaux identifiants et nouvelles archives consultables ; faire valider identité, hébergement, B2/SMTP, conservation effective, exercice des droits, cookies et cohérence contractuelle. Aucun changement de beta-2026-10-v1 ou beta-2026-10-26-draft-1. Réserver par exemple docnelo-beta-10-2026-10-v1-draft (non publié et non approuvé) ; choisir l’identifiant final et date d’effet lors de l’approbation.
6. **Messages ciblés.** Future UI : remplacer uniquement le texte de capacité cinq par dix, continuer à utiliser les options existantes. Future API : sujet vérification « Vérification Docnelo », sujet reset « Réinitialisation Docnelo », lien « Ouvrez ce lien Docnelo ». Conserver route, fragment #token, TTL, méthodes, payloads, code 202 générique et validation du mot de passe. Éviter la recopie des fichiers Account ou account_api mixtes du workspace. Pas de réparation du téléchargement BFF ni de nouveaux contrats Lite.
7. **Recette finale de la release approuvée.** Résoudre les dix erreurs de teardown du contexte candidat (fixture historique modifiant ai_enabled après startup, arrêt d’un thread non démarré), en fixant le cycle de vie testé et ses fixtures sur les sources attestées ; ne pas activer l’IA réelle comme correction. Rejouer les parcours complets avec le mode durable réel, PostgreSQL 17, SMTP TLS synthétique, BFF R2 et toutes les migrations de laboratoire. Sceller commit, image API candidate, éventuelle image Web, outillage et manifeste. Les tests du présent dossier sont diagnostiques ; ils ne remplacent pas cette recette.
8. **Préparer puis décider l’ouverture.** Configurer ultérieurement une release indépendante, conserver Web R2 et les overrides actifs, sauvegarder avant l’ouverture et obtenir une décision opérateur explicite. Aucun déploiement n’est fait ici.

## Configuration cible, sans application

```text
PUBLIC_REGISTRATION_LIMIT=10
AI_ENABLED=false
OWNER_DEMO_ENABLED=false
LEGACY_API_ENABLED=false
```

REGISTRATION_MODE reste disabled et PUBLIC_LEGAL_READY reste dans son état actuel pendant la préparation. Le passage ultérieur à public et à un état légal prêt est conditionné par l’approbation humaine, les preuves techniques et la livraison qualifiée. Ne pas mettre lifecycle_synthetic_mutations_enabled=true ni lifecycle_durable_receipts_required=false sur VPS. Le profil standard est l’hypothèse du circuit public ; si le VPS est Beta Lite, arrêter et revoir le circuit, pas changer le profil opportunément.

## Faut-il toucher à la ligne public_registration_quota ?

| État constaté | Action future autorisable après qualification |
| --- | --- |
| 0<=issued_count<10, closed=false, preuves cohérentes | La variable fixe la capacité SQL restante ; ne pas changer le compteur |
| 0<=issued_count<10, closed=true | La variable ne rouvre pas ; il faut la future commande de réouverture approuvée, inexistante à dix aujourd’hui |
| issued_count=10 | Rester complet, éventuellement fermer explicitement ; aucune réouverture à dix |
| issued_count>10, négatif, ligne absente, incohérence témoin | NO-GO, investigation ; jamais de correction par remise à zéro |
| Réserves pending/commit incertain | Réconciliation indépendante préalable, pas d’addition/soustraction au compteur au jugé |

L’augmentation est **une évolution de code/protocole et d’outillage**, pas uniquement un .env ou une requête UPDATE. Le schéma PostgreSQL BigInteger existant supporte dix ; aucune migration Alembic de capacité n’est justifiée à ce stade. La migration lifecycle et sa stratégie de compatibilité restent à développer et à tester hors production.

## Critères de réception

- SQL et témoins concordants pour 0, 5, 6, 9 et 10 ; état cohérent après restart et restauration ; refus 11 malgré accès concurrent par plusieurs processus.
- Pannes avant/après commit et SMTP ne libèrent jamais une admission attribuée ; vérification/renvoi ne créent pas une seconde admission.
- Commande close sûre à dix ; réouverture réservée à une procédure explicitement approuvée et jamais automatique au restart.
- Nouvelle version juridique reliée aux acceptations futures, archives historiques byte-identiques, décision humaine tracée ; pas de simple retrait du mot brouillon.
- IA interdite, accès inter-owner refusé, CSRF/cookies/contrats BFF inchangés, SMTP réel validé uniquement après autorisation dédiée.
- Sauvegarde V5.1 et restauration/réconciliation de dix admissions qualifiées avec l’outillage cible ; aucun nettoyage destructeur du dépôt.

## Retour arrière prévu

Fermer d’abord les nouvelles admissions sans toucher aux comptes, puis conserver le plafond dix et les historiques si des admissions >5 existent. Un rollback API vers une version bornée à cinq pourrait rendre l’administration, les sauvegardes ou la reprise incohérentes : il doit être refusé sans preuve de compatibilité. Préparer une version de fermeture compatible dix plutôt qu’un downgrade aveugle. Ne jamais restaurer une base préouverture pour annuler les inscriptions réelles : cela perdrait comptes, consentements et documents. Le rollback Web peut conserver R2 ; aucun retour à la référence historique R1 n’est requis.

**NO-GO ouverture ; plan de correction prêt à revue.** Le périmètre de cette livraison est documentaire et tests isolés, pas un contournement des gardes lifecycle.
