# Docnelo — Rapport de recette du parcours d'inscription

Date : 31 octobre 2026, Europe/Paris. **Verdict global : BLOCKED**.

La recette a exécuté Web R2 et l'API exacte `4aa850…` sur PostgreSQL 17, avec SMTP STARTTLS captif et magasins lifecycle neufs. Elle n'a créé aucun compte. Le refus d'admission est confirmé avant et après redémarrage, avec reçus durables requis et mutations synthétiques désactivées.

## Résultats observés

La sonde principale contient **26 contrôles PASS** dans `deliveries/docnelo-signup-e2e-lab/test-results.json`. Ils ne constituent pas 26 parcours réussis. Les contrats directs sont identifiés séparément ci-dessous.

| Scénario | Résultat | Portée de la preuve |
| --- | --- | --- |
| Archives API/Web et couches | PASS | Identifiants exacts, 15 et 11 couches ; pas d'attestation VPS |
| PostgreSQL, migrations, lifecycle-init | PASS après correction du harnais | Base neuve, magasins séparés, UID 1000, fichiers 0600 ; clés 0:1000 en 0440 |
| HTML R2 et route `/register` | PASS | GET HTTPS via proxy et BFF réels ; interaction formulaire non exécutée |
| Textes synthétiques | PASS | GET du texte de laboratoire servi séparément |
| Options publiques | PASS | Mode laboratoire public, disponibilité fermée, quota non ouvert |
| CSRF absent | PASS | POST refusé avec 403 |
| CGU refusées / version incorrecte | PASS | POST refusés avec 400 |
| Challenge valide + CGU synthétiques acceptées | **BLOCKED** | Challenge résolu ; admission refusée avec 503 par la garde stricte |
| Création ou consommation de place | PASS pour l'absence d'effet | `issued_count=0, closed=true`, zéro utilisateur et zéro jeton |
| Vérification avec jeton inconnu | PASS | HTTP 400 |
| Connexion d'une identité non admise | PASS | HTTP 401 |
| Accès anonyme au compte | PASS | HTTP 401 |
| SMTP de capture | PASS partiel | Appel séparé au véritable expéditeur API ; un email synthétique capturé sous TLS |
| Quota fermé / quota plein | PASS partiel | Fonction SQL de quota dans transactions synthétiques annulées ; aucun test de dernière admission durable |
| Expiration et rejeu de jetons | PASS partiel | Fonction réelle de consommation SQL, jetons synthétiques, transactions annulées ; aucune vérification réussie via HTTP |
| Expiration et rejeu du challenge | PASS partiel | Objet réel de challenge avec horloge de test ; pas d'attente réelle de cinq minutes |
| Garde légale | PASS | Configuration publique refusée si `PUBLIC_LEGAL_READY=false` |
| Redémarrage DB/API/Web | PASS partiel | Services disponibles, projection fermée identique, refus d'admission toujours 503 |
| Accès depuis le poste | PASS | Quatre GET HTTPS, certificat vérifié, relais lié à 127.0.0.1 |
| Interaction navigateur / consentement graphique | BLOCKED / non exécuté | Version juridique R2 différente du texte synthétique ; aucune automatisation navigateur lancée |
| Admission → email → vérification → connexion → accès authentifié | **BLOCKED** | Aucune admission obtenue ; aucune étape aval réussie ne peut être revendiquée |

Le message SMTP capturé a été provoqué par un appel séparé à `send_verification` avec une adresse `capture-only@example.test` et un jeton aléatoire sans compte associé. Il ne prouve pas l'émission d'email après inscription. Aucun email réel n'a été expédié.

## Blocage lifecycle démontré

L'API exacte refuse l'appel d'admission après validation du consentement et avant mutation de quota. La garde `require_synthetic_mutation` lève une erreur lorsque les reçus durables sont requis et que les mutations synthétiques sont désactivées. Le POST réel retourne **503**. Un contrôle direct supplémentaire après redémarrage confirme la même garde. Aucun flag n'a été changé pour la franchir.

Le quota est aussi fermé par défaut dans la base neuve. La disponibilité fermée de l'interface n'est donc pas attribuée uniquement au lifecycle. Le test d'admission et le contrôle direct établissent séparément le blocage durable. Le quota synthétique n'a jamais été ouvert par un commit ; les essais de fonction quota ont tous été annulés.

Web R2 embarque la version juridique `beta-2026-10-v1`, alors que l'API de laboratoire annonce `lab-only-v1`. Le POST de test accepte explicitement le texte synthétique ; il ne simule pas une interaction graphique réussie avec les archives réelles de R2.

## Incidents du harnais et corrections

- Premier PostgreSQL : racine en lecture seule, socket `/var/run/postgresql` non inscriptible. Correction par tmpfs dédié UID/GID 70 et nouveau volume `database_retry`, sans réutiliser l'initialisation interrompue. Ajout d'une dépendance à l'état healthy avant migration.
- Première sonde : nom de module de base incorrect, puis hypothèse erronée sur `closed=false`. Corrections du harnais ; état réel `closed=true` conservé.
- Publication Docker sur réseau interne inaccessible depuis le poste. Publication retirée ; relais TCP via Docker local, sans ajout de réseau externe.
- Essai HTTPS par IP : certificat par défaut Traefik rejeté. URL `https://localhost:19446` vérifiée avec le certificat dédié, sans désactiver TLS.
- Sonde de finalisation : encodage stdin Windows corrigé en UTF-8.
- Arrêt du serveur SMTP de capture : code 137 après le délai d'arrêt de 15 secondes, capture déjà enregistrée. L'arrêt gracieux de cette fixture n'est pas qualifié.

Ces incidents n'ont entraîné aucune modification du code applicatif, des gardes, des branches ou du VPS. Les journaux des essais initiaux ne sont pas effacés ; les preuves JSON finales établissent les résultats retenus.

## Limites et clôture

Non qualifiés : succès du formulaire, admission durable, email issu de l'admission, vérification réussie, authentification et session d'un compte admis, reconnexion après redémarrage, concurrence de dernières places, panne SMTP pendant admission et récupération d'une admission interrompue. Les tests directs de jeton ne remplacent pas ces parcours.

Le VPS n'a été ni consulté ni modifié. Son état fourni par l'utilisateur — limite 5, `issued_count=0`, `closed=true`, mode disabled — reste une donnée de contexte non recontrôlée ici. Les CGU réelles, mentions légales et confidentialité restent non approuvées. Le lifecycle durable à 10 reste hors de cette recette.

État final attesté dans `final-state.json` : laboratoire arrêté, relais arrêté, worktree propre ; seuls des volumes synthétiques neufs sont conservés.

**Laboratoire : BLOCKED pour le parcours complet, contrôles de refus et d'isolation réussis. VPS : non qualifié, aucune ouverture autorisée.**
