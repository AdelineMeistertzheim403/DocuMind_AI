# Docnelo — Runbook de recette isolée

31 octobre 2026. **BLOCKED pour l'inscription complète** : l'API exacte refuse l'admission sous garde durable. Ne pas transformer les commandes ci-dessous en procédure VPS.

## Examiner la recette déjà exécutée

Depuis `C:\Users\Adeline\Documents\DocuMind_AI`, lire les rapports et les fichiers `archive-proof.json`, `test-results.json`, `post-restart-proof.json`, `smtp-proof.json`, `loopback-proof.json`, `runtime-isolation-final.json` et `final-state.json` sous `deliveries/docnelo-signup-e2e-lab/`.

Le laboratoire est arrêté. Les données sont intégralement synthétiques. Ne pas réexécuter les scripts de première préparation dans ce dossier : ils refusent les collisions et les preuves existantes doivent être conservées.

## Inspection manuelle optionnelle depuis le poste

Le transport HTTPS local a été testé, sans interaction navigateur. Le certificat de laboratoire est valable deux jours depuis sa création ; vérifier sa validité avant cette option. Après expiration, préparer une nouvelle recette avec de nouveaux certificats et volumes.

Dans PowerShell, définir ces variables locales et vérifier la configuration :

```powershell
$Lab = 'C:\Users\Adeline\Documents\DocuMind_AI\deliveries\docnelo-signup-e2e-lab'
$Python = 'C:\Users\Adeline\AppData\Local\Programs\Python\Python313\python.exe'
$DockerLab = @('--host', 'npipe:////./pipe/docker_engine', 'compose', '--env-file', "$Lab\empty.env", '-p', 'docnelo-signup-lab-7c98f505cd', '-f', "$Lab\compose.json")
& $Python -c "import sys; sys.path.insert(0, r'$Lab'); from run_lab import audit; print(audit())"
& docker @DockerLab config --quiet
& docker @DockerLab up -d --wait db smtp legal
& docker @DockerLab up -d --wait api web proxy
```

Ces commandes réutilisent uniquement les volumes synthétiques de cette recette. Ne pas refaire les migrations ou le provisionnement lifecycle pour une simple inspection.

Dans une seconde console locale, lancer au premier plan :

```powershell
& 'C:\Users\Adeline\AppData\Local\Programs\Python\Python313\python.exe' 'C:\Users\Adeline\Documents\DocuMind_AI\deliveries\docnelo-signup-e2e-lab\loopback_relay.py'
```

Le relais refuse un port déjà occupé. Ouvrir **https://localhost:19446/register** ; l'écoute est limitée à **127.0.0.1:19446**. Utiliser `localhost` pour le nom TLS/SNI. L'URL utilisant directement l'adresse IP sélectionne le certificat par défaut de Traefik et n'est pas l'URL validée.

Utiliser un profil navigateur temporaire, sans données personnelles. Comparer le certificat présenté au certificat `tls/lab.crt` avant une éventuelle exception locale limitée à ce site. Son empreinte et ses dates sont consultables avec :

```powershell
& 'C:\Program Files\Git\usr\bin\openssl.exe' x509 -in "$Lab\tls\lab.crt" -noout -fingerprint -sha256 -dates
```

Ne pas installer une autorité globale ni désactiver globalement les contrôles TLS. Le test automatisé `check_loopback.py` utilise explicitement ce certificat, sans exception TLS et sans proxy système.

Observer l'état d'inscription fermé et consulter `/lab-legal/terms`, `/lab-legal/privacy`, `/lab-legal/notice`. La version juridique synthétique diffère volontairement de celle embarquée dans R2 ; ne pas présenter cette inspection comme une acceptation graphique des CGU synthétiques. Utiliser uniquement des identités `example.test` et des mots de passe de test.

Pour arrêter : Ctrl+C dans la console du relais, puis :

```powershell
& docker @DockerLab stop -t 15
```

Ne pas utiliser de commande globale de nettoyage Docker. Les volumes synthétiques peuvent rester arrêtés ; aucune suppression n'est nécessaire pour consulter les rapports.

## Préparer une nouvelle exécution reproductible

Créer un nouveau dossier frère du laboratoire et un nouveau worktree détaché sur `b046e5d8256d45b65bf575a8a006351616b69fc9`. Copier uniquement les scripts `.py` du laboratoire, sans `compose.json`, `lab.json`, TLS, archives dérivées ou preuves. Le programme `prepare_lab.py` attend son worktree dans `source/` et crée un nom de projet aléatoire. Il capture le programme de provisionnement à deux phases du Compose local : revoir cette entrée et la comparaison de son empreinte si elle a évolué depuis cette recette.

Ordre de première exécution dans ce nouveau dossier :

1. `verify_archives.py` : vérifier les archives et produire la copie API sans tags. Refuser toute différence d'identifiant ou de couches.
2. Si nécessaire, charger uniquement cette copie sans tags avec le moteur local ; ne pas remplacer de tag existant. Web et auxiliaires doivent déjà être présents aux identifiants de l'architecture, sans téléchargement automatique.
3. `prepare_lab.py`, puis examiner le Compose généré et exécuter `run_lab.py`. Le précontrôle refuse les ressources de même projet déjà présentes, les montages hors labo, les réseaux externes, les ports Docker, les références d'image mutables et les flags lifecycle affaiblis.
4. `run_checks.py` une seule fois sur cette base neuve : HTTP/TLS réel, échecs, SMTP de capture, contrats directs et redémarrage.
5. `check_loopback.py` : relais temporaire, quatre GET HTTPS depuis le poste, arrêt automatique du relais.
6. `finalize_lab.py` : vérifications après redémarrage, isolation finale, arrêt du laboratoire. Conserver les journaux, y compris les essais échoués.

`resume_setup.py` documente uniquement la réparation du premier essai de cette session ; la génération finale inclut déjà le tmpfs de socket PostgreSQL et l'attente de disponibilité nécessaires.

## Scénarios restant à qualifier

Après livraison séparée d'une API durable qualifiée et clarification du contrat de CGU synthétiques avec R2, refaire une recette neuve : interaction réelle du formulaire, refus sans consentement, admission durable, message causé par cette admission, connexion interdite avant vérification, mot de passe incorrect, vérification valide, rejeu et expiration via HTTP, connexion réussie et accès authentifié, doublons/concurrence, dernière place, fermeture du quota, panne SMTP et panne lifecycle sans admission incohérente, puis redémarrage et reconnexion.

Ne pas désactiver les reçus durables, activer les mutations synthétiques ou remplacer une autorité durable pour obtenir artificiellement ce parcours. Tant que la garde échoue, conserver **BLOCKED**. Les approbations juridiques réelles restent une condition distincte d'ouverture ; aucune commande de ce runbook n'agit sur le VPS.
