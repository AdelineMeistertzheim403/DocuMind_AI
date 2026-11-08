# Docnelo — Sécurité et isolation de la recette

31 octobre 2026. **PASS pour les contrôles d'isolation réalisés ; BLOCKED pour la qualification du parcours complet.**

## Périmètre réellement utilisé

Le moteur Docker est local, explicitement ciblé par `npipe:////./pipe/docker_engine`. Aucune commande SSH, SCP, déploiement, push, registre ou connexion au VPS n'a été exécutée. L'accès Docker et l'enregistrement du worktree ont nécessité une élévation hors bac à sable ; ces opérations locales ont été autorisées par le mécanisme de revue. Aucune revue automatique n'a rejeté une action.

Le worktree est détaché de toutes les branches en cours et propre en fin d'exécution. Aucun fichier existant du produit ou de l'autre phase lifecycle n'a été édité. Les livrables racine et le nouveau dossier de laboratoire sont les ajouts de cette mission. Aucun changement global de configuration Git n'a été fait ; les exceptions de propriété Git sont limitées aux commandes concernées.

## Contrôles et preuves

| Contrôle | Constat vérifié |
| --- | --- |
| Réseau | Un réseau neuf, `Internal=true`, aucun réseau externe ou existant sur les six conteneurs permanents |
| Volumes | Volumes neufs portant uniquement le préfixe du projet ; aucun volume Production/Public Beta référencé |
| Bind mounts | Fichiers générés dans le laboratoire, montés en lecture seule |
| Images | Identifiants SHA-256 immuables, `pull_policy=never`, aucune publication ; API chargée sans tags |
| Configuration | Pas de `env_file` de service, fichier d'interpolation vide explicite, aucun secret hôte transmis au runtime |
| ENV héritée des images | Aucun nom de variable contenant PASSWORD/SECRET/TOKEN/SMTP/DATABASE_URL/API_KEY détecté ; valeurs non journalisées |
| Bases | Hôte `db` interne, nom/utilisateur synthétiques, mot de passe de laboratoire ; aucune copie de base réelle |
| Lifecycle | Cinq magasins neufs dans des répertoires séparés ; clés générées par `secrets.token_bytes`, aucune clé utilisateur importée |
| Permissions | Magasins app:app 0600, répertoires 0700 ; clés root:app 0440, clés non modifiables par l'API |
| Gardes | Reçus durables requis, mutations synthétiques désactivées, profil standard ; refus durable confirmé |
| SMTP | Serveur captif sans fonction de relais, STARTTLS avec certificat du labo ; aucune route réseau externe |
| Accès poste | Relais explicite 127.0.0.1:19446 uniquement, HTTPS vérifié, aucun port Docker final publié |
| Durcissement | Racines en lecture seule, toutes capacités retirées sauf celles du provisionnement ponctuel, no-new-privileges |
| Clôture | Tous les conteneurs du projet et le relais arrêtés ; aucun service préexistant arrêté ou supprimé |

Preuves finales : `runtime-isolation-final.json`, `safety-preflight-final.json`, `post-restart-proof.json`, `smtp-proof.json`, `loopback-proof.json`, `final-state.json` sous `deliveries/docnelo-signup-e2e-lab/`.

La restriction réseau est établie par la configuration et l'inspection Docker. Aucun test vers une adresse externe réelle n'a été lancé pour « prouver » le blocage. Le contrôle d'ENV héritée n'est pas un audit exhaustif de secrets dans toutes les couches des images ; la provenance reste limitée à l'identité vérifiée des artefacts privés fournis.

## Données et conditions synthétiques

Tous les destinataires applicatifs utilisent `example.test`. Aucun nom de client, document, compte, clé utilisateur, bucket, secret SMTP, sauvegarde ou export de base réel n'a été utilisé. Les certificats TLS et clés lifecycle ont été créés pour ce laboratoire. Les mots de passe/configurations de test ne doivent pas être réutilisés ailleurs.

Le seul email capturé ne correspond à aucun compte admis. Les jetons de test ont été créés puis consommés ou expirés uniquement dans des transactions SQL annulées. Les projections temporaires de quota plein ont elles aussi été annulées. Les preuves finales comptent **zéro utilisateur, zéro jeton, zéro admission**, quota fermé.

La déclaration légale `PUBLIC_LEGAL_READY=true` est limitée aux textes explicitement synthétiques `lab-only-v1`. Aucun document légal réel n'a été approuvé ou modifié. Le contrôle inverse avec false reste bloquant. Aucun flag n'a désactivé les protections durables, y compris dans ce laboratoire.

## Accès manuel et conservation

Le relais optionnel utilise l'accès local Docker déjà disponible au développeur. Il n'expose ni le socket Docker ni une API d'administration à HTTP ; son unique destination est le proxy TLS interne du projet fixé dans `lab.json`. Il écoute sur IPv4 loopback uniquement et reste au premier plan lors d'un usage manuel. Le test automatisé l'a démarré temporairement puis arrêté.

Les archives API/Web, `api-untagged.tar`, les fichiers Compose contenant les clés fictives, les clés TLS et les volumes de capture restent des artefacts privés locaux. Ne pas committer ou publier le dossier de livraison en bloc. Les quatre rapports et les empreintes constituent les livrables consultables ; l'accès aux artefacts privés conserve les contrôles du poste Windows. Aucun ACL Windows global n'a été changé.

Aucun effacement de volume ou nettoyage global Docker n'a été effectué. Le volume du premier essai et les volumes synthétiques finaux restent arrêtés pour inspection ; leur conservation n'implique aucun besoin d'accès au VPS.

## Quota réel et limites de qualification

La limite de laboratoire est 5. Aucune écriture n'a ciblé une base, un magasin lifecycle, une clé ou un réseau du VPS. Une admission locale ne pourrait pas alimenter le quota public réel avec cette topologie ; en pratique aucune admission locale n'a abouti.

Le plafond réel n'a pas été modifié. L'état réel fourni par l'utilisateur n'a pas été recontrôlé à distance. Ces résultats n'attestent ni les réseaux du VPS, ni sa configuration SMTP, ni sa chaîne de sauvegarde, ni sa conformité juridique, ni son futur lifecycle à 10.

**Verdict du parcours : BLOCKED. Aucune ouverture ou modification du VPS réalisée ou autorisée par cette recette.**
