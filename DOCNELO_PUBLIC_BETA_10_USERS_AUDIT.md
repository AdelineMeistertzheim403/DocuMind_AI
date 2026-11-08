# Docnelo Public Beta — Audit de préparation à dix admissions

31 octobre 2026. **NO-GO pour l’ouverture.** Aucune modification VPS, inscription réelle, activation IA, migration, modification de quota, de latch ou de configuration n’a été effectuée.

## Références et niveau de preuve

Le déploiement Web R2 et le succès de verify-state sont des éléments transmis par l’opérateur. La référence Web locale est le commit b046e5d8256d45b65bf575a8a006351616b69fc9, image ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362. Son BFF et ses textes juridiques ont été figés en R2. Ils sont conservés sans modification dans cette mission.

**Ce commit ne prouve pas la provenance de l’API active.** L’export local exports/public-beta-candidate-20261030T234818Z contient 65 fichiers Python backend, dont 17 diffèrent du backend Git associé à R2 ou y sont absents, notamment Beta Lite. Le dossier exports n’est pas une attestation Docker. Deux contextes synthétiques distincts sont donc examinés : sources Git R2 et hypothèse API de l’export candidat. Les tests ne sont pas présentés comme une certification de l’API VPS. candidate-api-inventory.json donne les empreintes comparées. L’opérateur doit confirmer l’ID/digest de l’API, ses sources, son profil, ses flags effectifs et ses migrations ; aucune API active n’a été inspectée à distance.

Le workspace principal contient des changements fonctionnels et juridiques non déployés. Ils ne sont ni recopiés comme référence active, ni corrigés en place. En particulier, frontend/src/legal/documents.ts du workspace a déjà des textes différents sous beta-2026-10-v1 : **ne pas le publier tel quel pour remplacer une version historique**.

## Ce qui est compté

| Mesure | Sens et source | Effet du plafond |
| --- | --- | --- |
| Admissions attribuées | public_registration_quota.issued_count, cumul historique | Plafond de dix envisagé ; jamais remis à zéro |
| Comptes présents | Lignes users, tous registration_kind | Peut inclure comptes historiques/invités hors quota public |
| Comptes publics non vérifiés | registration_kind=public, email_verified_at NULL | Admission déjà consommée après commit |
| Comptes vérifiés | email_verified_at renseigné | Ne consomme pas une seconde admission |
| Connexions simultanées | Sessions authentifiées | Aucun plafond de dix sessions découlant de ce quota |

La demande « dix utilisateurs maximum » est interprétée comme **dix admissions publiques cumulatives au total**, pas dix nouvelles places en plus des cinq, ni dix sessions. S’il existe des comptes invités/historiques, ce mécanisme seul ne borne pas le nombre total de comptes/personnes. Le recensement opérateur doit trancher cette condition avant GO ; utiliser invite contournerait le quota public dans le profil standard.

## Quota SQL et concurrence

backend/public_registration.py réalise un UPDATE conditionnel atomique : id=public, closed=false, issued_count >= 0 et issued_count < limite ; incrément et RETURNING dans la transaction de création du compte/workspace/token. PostgreSQL sérialise les mises à jour concurrentes de cette ligne. Une vérification préalable SELECT seule ne serait pas suffisante ; le contrôle effectif est bien dans l’UPDATE. La contrainte d’unicité d’email et le rollback empêchent les doublons de consommer une admission SQL supplémentaire.

Le sémaphore RAM limite une admission par instance, mais ne constitue pas la garantie interprocessus ; les tests utilisent deux applications et deux connexions PostgreSQL distinctes. La limite repose aussi sur l’hypothèse opérationnelle d’une même configuration et d’un même quota pour toutes les instances. Un writer administratif ou une seconde API configurée avec une limite supérieure ne serait pas protégé par un CHECK SQL « <=10 » inexistant.

À dix, la disponibilité devient full et la onzième demande admissible reçoit la réponse générique 202 sans compte. **closed n’est pas automatiquement basculé à true** : le prédicat de capacité suffit. Relever ensuite la limite avec closed=false rendrait de nouvelles admissions possibles dans un profil sans autres gardes. Aucun mécanisme automatique ne doit être confondu avec une fermeture administrative persistante.

## Cycle de vie d’une tentative

| Situation | SQL / admission | Suite |
| --- | --- | --- |
| Mauvaises CGU, preuve invalide, honeypot, email déjà présent | Aucun nouveau compte attribué | Erreur explicite CGU ou réponse générique ; ne pas énumérer les emails |
| Exception avant commit | Transaction SQL annulée | Nouvelle tentative possible, après contrôle des témoins si une réserve durable a été créée |
| SMTP absent détecté avant commit | Pas de compte SQL validé | Indisponibilité ; corriger la livraison, pas le compteur |
| Commit réussi, file pleine ou échec SMTP asynchrone | Compte et admission conservés | Renvoi protégé vers le compte existant ; pas une nouvelle inscription consommant une place |
| Abandon après commit, compte jamais vérifié | Admission conservée | Purge éventuelle ne recycle aucune place |
| Suppression du compte | Admission conservée | Ne jamais décrémenter issued_count |
| Commit incertain, ancre pending ou settle échoué | État à réconcilier indépendamment | Fail closed ; pas de reset ou de retry aveugle |

Le redémarrage recrée les challenges, limites de débit RAM et sessions RAM ; il ne réinitialise pas la ligne PostgreSQL. Une session perdue exige une nouvelle connexion, pas une nouvelle admission. Une restauration d’une ancienne base peut en revanche faire reculer le compteur : le latch, les témoins indépendants et leur réconciliation restent indispensables même après une restauration techniquement réussie.

## Blocages du passage de cinq à dix

| Emplacement | Garde observée | Conséquence |
| --- | --- | --- |
| backend/config.py | Entier 0..10000, mais Beta Lite exige exactement 5 dans l’export | La validation Settings standard seule ne qualifie pas dix |
| backend/lifecycle_durability.py | SQLite admissions CHECK(sequence BETWEEN 1 AND 5), bornes réserve/lecture/restauration | Migration lifecycle distincte requise ; changer une variable ne change pas une table existante |
| backend/lifecycle_admissions.py | Témoins/ancre bornés à 5, configured_admissions exige 5 | Capacité stricte dix indisponible, même avec PostgreSQL capable de dix |
| backend/lifecycle_durability.py | require_synthetic_mutation refuse les mutations expérimentales sans opt-in synthétique | Ne jamais activer le flag synthétique sur le VPS pour contourner cette garde |
| backend/account_admin.py | reopen refuse le mode durable actuel ; sinon exige public/5 | Aucune commande approuvée de réouverture durable à dix aujourd’hui |
| tools/public_beta_policy.py | Livraison publique exige exactement 5 et accord explicite | La chaîne de livraison doit évoluer et être requalifiée |
| tools/deploy_production.py, backup_production.py | Certaines validations bornent issued_count à 5 | Analyse d’impact requise, sans toucher Production dans ce lot |
| frontend/src/pages/Account.tsx de R2 | Texte « cinq admissions cumulatives » | Nouvelle release Web ciblée nécessaire après validation, sans modifier les contrats BFF |
| CGU actives R2 | Cinq admissions, statut brouillon | Nouvelle version et approbation humaine nécessaires |

La migration PostgreSQL 0007 ajoute le compteur et les champs d’acceptation ; son schéma ne nécessite pas, à lui seul, un changement pour stocker dix. **Ne pas rejouer cette migration pour réinitialiser le compteur.** Les migrations SQLite, le protocole signé et la réconciliation sont un autre chantier. Ne pas faire un remplacement global de « 5 » : le format V5 des sauvegardes et la durée de cinq minutes d’un challenge ne sont pas des capacités de cohorte.

## Beta Lite

L’export candidat connaît application_profile=beta_lite, impose invite/5, IA désactivée, cohorte et empreinte de CGU, autorité et état de reprise. Son circuit d’admission est distinct, avec autorité opérationnelle indépendante. Passer arbitrairement en invite ou Beta Lite ne constitue ni l’ouverture publique à dix ni une solution au protocole standard limité à cinq. Le profil et l’autorité réellement actifs restent à prouver sur VPS ; aucun nouveau contrat Lite n’est intégré ici.

## Emails, droits et exploitation

Les liens vérification et reset utilisent des jetons aléatoires, empreintes en base, dates d’expiration et consommation atomique à usage unique. Vérification : mot de passe choisi également requis ; TTL par défaut 3600 s. Reset : TTL 900 s, révocation des sessions de l’utilisateur après succès. Le renvoi invalide les anciens liens de vérification non consommés. Les sujets et corps des deux emails contiennent encore DocuMind dans les deux sources examinées. Le changement de ces seuls littéraux est à préparer sur une future release API identifiée, pas via une modification du conteneur actif.

L’API expose disponibilité booléenne/available/full/closed, pas de nombre exact de places restantes. Conserver le contrat ; afficher « dix admissions cumulatives » et « complet/fermé » dans la future UI, sans prétendre afficher un compteur live inexistant.

L’acceptation stocke terms_version et terms_accepted_at sur le compte. Ce n’est pas un registre historique complet de toutes les acceptations successives, ni une preuve d’acceptation séparée de chaque document. Les versions de notice/confidentialité ne sont pas liées individuellement au compte standard. Un journal immuable d’acceptations et d’empreintes est une évolution séparée à concevoir si nécessaire ; ne pas inventer cette garantie ni réécrire les comptes existants.

Anti-abus : preuve de travail liée à l’IP, durée 300 s, usage unique, honeypot, buckets signup global=10/minute et IP/email par heure, challenge global=60/minute et IP=5/minute, queues et capacité bornées. Ces buckets sont en mémoire par processus et repartent à zéro au restart ; aucune garantie de rate limit distribué. Les IP ne sont fiables que derrière le proxy/BFF approuvé. Le gate IP Traefik existant couvre aussi verify-email/resend : tester la réception/vérification depuis le réseau réel du testeur, sans supprimer ce gate au hasard.

Le BFF R2 conserve ses cookies, sessions, contrôles HTTPS/Origin et CSRF ; les tests de non-régression sont rejoués. L’isolation documentaire passe par l’identité owner/workspace et les filtres backend, pas seulement la navigation. Defaults source : upload 10 Mio, 100 documents/owner, 500 Mio/owner et 5 Gio global ; ce sont des paramètres à relever sur l’API réelle. Dix utilisateurs à 500 Mio saturent la limite globale théorique, et il faut en plus compter PostgreSQL, extraits, index, fichiers temporaires, logs et sauvegardes. Le téléchargement BFF connu 404 de R2 n’est pas réparé dans ce lot.

La sauvegarde/restauration V5.1 réussie est confirmée par l’opérateur ; elle ne prouve ni la fraîcheur future ni une rétention effective de trois mois ni la capacité de réconciliation après dix admissions. La rétention automatique n’est pas qualifiée ici ; retention_production.py est un planificateur en lecture seule pour d’autres formats, pas une tâche Public Beta V5 opérationnelle démontrée. Aucun forget/prune ou nettoyage n’est proposé.

## Verdict

**NO-GO ouverture à dix** : plafond lifecycle persistant à cinq, mutations de production non approuvées dans cette référence, réouverture non disponible, textes juridiques brouillons et à cinq, provenance API/flags/compteurs actuels non attestés. Les succès du quota SQL en laboratoire ne lèvent pas ces blocages. La suite Git passe 188 tests, le BFF 50 et les deux contrôles par nouveau processus passent ; la suite candidate conserve dix erreurs de teardown liées à une fixture modifiant le flag IA après startup (188 phases de test passées). Cette incompatibilité de qualification doit être résolue sans activer l’IA réelle. Voir le plan, la readiness juridique, les tests et le runbook associés pour les conditions de réexamen.
