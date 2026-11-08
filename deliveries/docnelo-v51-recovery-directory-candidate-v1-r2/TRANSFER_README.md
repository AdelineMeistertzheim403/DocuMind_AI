# Recovery Control Directory v1-r2 - transfert pour examen uniquement

Aucun remplacement de v1, aucun GO P3, Docker operationnel, S2, Lifecycle 10, Public Beta ou production. Aucun conteneur cree ou demarre.

Windows CPython 3.13.7 : 170 tests passes, dont 119 P1 inchanges et 51 nouveaux ; 0 skip/xfail et aucune E/S interdite. La campagne finale 003 est incluse avec JUnit.

Ancre candidate SHA256SUMS : 18bbaa4ac6640d90eedd19c39ba008f91a0a751b97e19905ee5d8d86313b5719
Ancre candidat v1 conserve : c1099170790274d9a0bfc813d44f17afb907e1d68eb101a9c5fc887022030eba

Debian hors ligne : verifier les empreintes externes par un canal de confiance, puis executer sha256sum -c SHA256SUMS dans ce nouveau dossier de transfert. Extraire avec unzip -n dans un nouveau repertoire development vide, jamais dans un candidat, une release, une preuve ou un namespace existant. Verifier PACKAGE-SHA256SUMS depuis la racine extraite, puis SHA256SUMS depuis recovery-control-directory-v1-r2. Les SHA ne sont pas des signatures.

Lire REPORT_R2.md et DEBIAN_OFFLINE_PROTOCOL.md, en particulier P3-r2. Ne pas relancer P2 : le preflight source+rendu+hote lit le marqueur existant sans publication, transition ou chmod. create_host_path: false reste obligatoire dans le YAML ; bind: {} seul ne suffit jamais. Ne pas utiliser le rendu JSON comme fichier Compose et ne creer/demarrer aucun conteneur au titre de cette revision.

La campagne Debian13/CPython3.11.18, Compose2.26.1-4 et Engine est NON EXECUTEE. Aucune image ni fermeture wheelhouse CP311 supplementaire fournie. Les locks source et metadonnees des dependances sont inventories, sans garantie d une fermeture offline complete. Inspections Engine avant start, D11, UID/GID effectifs, RO/DAC, TOCTOU et propagation restent a qualifier apres autorisation distincte. Sans prerequis : arret, jamais de contournement.
