# Docnelo V5.1 - Recovery Control Directory r3, examen uniquement

Nouveau transfert independant. Aucun remplacement de v1/r2. Aucun GO P3 operationnel, Docker, S2, Lifecycle 10, Public Beta ou production.

Correction limitee a mem_limit rendu : seuls str "128m", int 134217728 et str "134217728" sont approuves. Pas de float, conversion generique, arrondi ou changement du YAML source. Les create_host_path: false explicites, source+rendu+parametres+P2+hote et les gardes historiques restent requis. bind: {} seul est toujours insuffisant.

Windows CPython3.13.7 : 209 passes (119 P1 + 51 r2 + 39 r3), sans skip/xfail ou E/S interdite. JUnit final et entrees du manifeste final inclus dans windows-evidence/windows-preparation-final-002.
SHA256 de SHA256SUMS candidat r3 : 5f3cc1598423107c5616d630d63d31b849b939cbd9f3ce9ce25fc0bf3440f8d4
SHA256 de INPUTS.json r3 : c33358f734bcee252a39b1b10f9ed7a459c4ee30d29f46630523ac1aad208ed2

Verifier le SHA externe par un canal de confiance independant. Les SHA ne sont pas des signatures. Aucun secret, image ou nouveau wheelhouse fourni.

Debian hors ligne : copier ce nouveau dossier de transfert sans toucher aux anciens. Depuis ce dossier, sha256sum -c SHA256SUMS. Extraire avec unzip -n dans un nouveau repertoire development vide, jamais une release, un candidat, une evidence ou un namespace existant. Depuis la racine extraite : sha256sum -c PACKAGE-SHA256SUMS. Depuis le sous-repertoire recovery-control-directory-v1-r3 : sha256sum -c SHA256SUMS.

Lire le rapport R3 et DEBIAN_OFFLINE_PROTOCOL.md, section P3-r3. Definir CANDIDATE au chemin absolu de la copie extraite, sans remplacement. Les chemins candidates/... du rapport decrivent le depot de preparation ; dans cette archive le candidat est directement sous la racine extraite. Les anciens rapports/generateurs sont de provenance : ne pas les executer. build_r3_inventory.py est reserve a la preparation avec v1/r2 presents, pas necessaire au lanceur/preflight autonome dans le laboratoire.

Aucun Docker, nouveau namespace synthetique, changement de permissions ou mutation du latch P2 execute ici. Ne pas relancer P2 : preflight en lecture seule sur le marqueur et les sources existants ; sortie dans une evidence Debian neuve uniquement. Ne pas transformer le rendu natif en fichier Compose ni le modifier pour contourner un refus.

NON EXECUTES : Debian13/CPython3.11.18 r3, Compose2.26.1-4 natif, D11, UID/GID effectifs, Engine, RO/DAC, TOCTOU et propagation D01-D20. Une fermeture offline CP311/PyYAML et images approuvees restent des prerequis distincts. Aucune creation/demarrage de conteneur autorisee automatiquement par ce transfert. Examen uniquement.
