# DocuMind AI — Sprint 14.13 : recette technique et conformité avant bêta publique

27 octobre 2026. Consolidation locale des rapports Sprint 14.8 à 14.12 et de
l'état du dépôt. Aucun VPS, SMTP, B2/Restic, reverse proxy, donnée utilisateur
réelle ou paramètre de production n'a été consulté ou modifié.

## Verdict

**NO-GO : l'ouverture publique n'est pas autorisée.** Le développement local
prépare plusieurs prérequis, mais les documents juridiques ne sont pas approuvés,
la rétention destructive reste désactivée, les preuves de production sont
absentes et le lot local n'est pas encore une release attestée.

| État | Conclusion |
| --- | --- |
| Développement local | Partiel et testé par lots : routes légales publiques de brouillon, inscription publique protégée mais fermée, quota cumulatif, IA désactivée, simulations de rétention, purge à 7 jours par défaut et téléchargement individuel. |
| Politique et textes | Non approuvés. Les brouillons et les valeurs locales ne valent ni validation juridique, ni configuration d'exploitation. |
| Livraison contrôlée | Non démontrée : le worktree contient des changements non committés et aucune CI/release/digest de ce lot n'est attesté. |
| Autorisation d'ouverture | Non acquise. Conserver `REGISTRATION_MODE=disabled`, le verrou SQL fermé, l'IA désactivée et `PUBLIC_LEGAL_READY` inchangé. |

## 1. État fonctionnel consolidé

| Domaine | Preuve locale | Limite avant bêta |
| --- | --- | --- |
| Inscriptions | Limite SQL atomique de cinq admissions cumulatives ; une admission non vérifiée ou supprimée ne rend pas de place ; fermeture d'urgence séparée. | Vérifier le compteur, le verrou et le profil réellement actifs sur VPS. Ne pas exécuter de test qui consomme une admission. |
| Email Gmail/SMTP | Vérification, renvoi et récupération sont couverts avec SMTP fictif ; le parcours ne promet pas la livraison. | Vérifier avec une boîte de recette de l'exploitante, TLS, expéditeur, SPF/DKIM/DMARC, réception et expiration des liens. |
| IA | Refus côté API/BFF lorsque désactivée ; aucun appel IA requis pour les fonctions documentaires classiques. | Vérifier les valeurs résolues dans l'image et le service déployés ; ne pas appeler de fournisseur IA. |
| Pages légales | `/mentions-legales`, `/confidentialite` et `/cgu` sont des routes publiques statiques, avec versions locales et liens permanents. | Les textes sont des brouillons ; l'URL configurée et `PUBLIC_TERMS_VERSION` acceptés en inscription doivent correspondre à la version approuvée, pas à une version locale par défaut. |
| Documents | Import, accès propriétaire, analyse classique, suppression contrôlée et téléchargement original PDF/TXT sont implémentés. | Recette HTTPS de production à réaliser ; ZIP global non livré. |
| Sauvegardes/rétention | Sauvegarde/intégrité et restauration isolée existent ; simulation 7 quotidiennes / 4 hebdomadaires / 3 mensuelles avec fail-closed. | Aucun `forget`, `prune` ni effacement local/distant réel n'est activé ; la restauration B2/VPS n'est pas démontrée. |
| Comptes non vérifiés | `purge-pending` simule par défaut ; seuil par défaut de sept jours, exécution explicite requise. | Aucun timer ni preuve d'opération périodique ; l'exécution ne doit pas être activée sans approbation. |
| Cookies/traceurs | Cookie de session `__Host-…` sécurisé et protection CSRF ; aucun stockage navigateur, analytics ou pixel applicatif identifié dans le code examiné. | Inventaire dans un navigateur sur la stack livrée, y compris Traefik/CDN/support, nécessaire avant toute conclusion de consentement. |

## 2. Pages publiques, CGU et cohérence juridique

Les pages locales sont accessibles sans session et les versions inconnues de CGU
sont refusées. Elles restent explicitement des **brouillons non approuvés**.
Le formulaire d'inscription utilise les options API ; les liens et la version
qu'il accepte ne doivent être préparés qu'après approbation humaine, archivage
de la version exacte, empreinte et contrôle HTTPS/anonyme de chaque cible.

Les engagements suivants ne doivent pas être publiés comme des faits tant qu'ils
ne sont pas validés et opérationnels :

- suppression complète ou immédiate de toutes les copies ;
- durées effectives de logs, sauvegardes, demandes RGPD ou comptes inactifs ;
- conservation 7/4/3 réellement appliquée à B2/archives locales ;
- localisation exclusive des données, contrats/régions des prestataires,
  transferts ou chiffrement applicatif au repos ;
- préavis de fermeture de 30 jours, export global ou assistance d'export
  avant la recette correspondante ;
- médiation de consommation, rôle responsable/sous-traitant et bases légales
  sans qualification juridique et contractuelle.

## 3. Matrice de recette

| Domaine | Test à réaliser | Données / résultat attendu | État |
| --- | --- | --- | --- |
| Pages publiques | Charger les trois URLs HTTPS sans session, en navigation privée et après panne API. | Titres/textes attendus, pas de redirection login, avertissement de brouillon tant que non approuvé. | À réaliser sur stack cible. |
| CGU | Vérifier URL, version API, texte archivé et preuve d'acceptation avec fixture. | Version exacte cohérente ; aucune ancienne version substituée. | À réaliser après approbation. |
| Inscription | Utiliser au plus les comptes fictifs autorisés dans une recette isolée. | Mode/limite 5, IA/demo/legacy fermés, compteur monotone, aucun reset. | Préproduction locale couverte ; VPS à vérifier fermé. |
| SMTP | Envoyer uniquement vers la boîte de recette de l'exploitante. | TLS, expéditeur, liens HTTPS, réception/expiration/renvoi observés sans log de secret. | À autoriser et réaliser. |
| Téléchargement | Télécharger PDF et TXT d'un compte de recette via HTTPS ; tenter compte tiers, session expirée, fichier absent/corrompu et interruption. | Contenu/nom fidèles ; 404 tiers, 401 session, erreur contrôlée d'intégrité, fermeture du flux ; aucun chemin interne. | Couvert localement sauf interruption/réseau sur VPS. |
| Récupération fermeture | Pendant une fenêtre de recette isolée, tester le téléchargement pour plusieurs tailles et une assistance simulée. | Route disponible pendant le préavis ; limites/timeout connus, aucune promesse ZIP. | Bloquant avant préavis de 30 jours. |
| Rétention | Exécuter simulations, archives incohérentes, panne réseau et verrou concurrent sur fixtures. | Plan 7/4/3, audit minimalisé, aucune suppression réelle en incertitude. | Couvert localement ; B2/VPS à contrôler sans suppression. |
| Restauration | Restaurer un snapshot identifié dans une cible vide isolée. | Empreintes, schéma, documents, compteur et verrou vérifiés ; réconciliation des suppressions documentée. | Bloquant, à autoriser. |
| Cookies/traceurs | Capturer cookies, stockage et requêtes tierces des parcours public, connexion, téléchargement et erreur. | Inventaire signé ; consentement seulement si un traceur non nécessaire est observé. | Bloquant documentaire. |
| Retour fermé | Fermer en simulation puis, avec autorisation, vérifier le verrou fermé après livraison contrôlée. | Aucune nouvelle admission ; comptes existants conservés ; aucun reset/restauration. | Procédure disponible, exécution VPS à autoriser. |

Les campagnes locales récentes rapportent 84 tests de rétention/inscription, 22
tests de téléchargement backend, la suite BFF, 64 tests UI et un build frontend
réussi. Elles ne constituent ni une recette navigateur HTTPS de production, ni
une preuve B2/SMTP/VPS.

## 4. Assistance et récupération pendant un préavis de fermeture

Avant de communiquer un préavis de 30 jours, désigner un canal d'assistance,
son responsable et un registre minimal des demandes. Pendant le préavis :

1. conserver l'authentification, les routes de téléchargement individuel et
   l'accès aux documents actifs ;
2. communiquer la date/heure de fermeture, les formats récupérables (PDF/TXT
   originaux), les limites connues et l'absence d'archive ZIP globale ;
3. traiter les échecs de récupération avec une vérification d'identité
   proportionnée, sans demander les fichiers par email ni exposer de chemins ;
4. journaliser seulement l'identifiant interne, la décision et l'issue de
   l'assistance ; appliquer la procédure de suppression/rétention distincte
   après fermeture ;
5. conserver les sauvegardes selon la politique approuvée et ne pas promettre
   leur effacement instantané.

Ce dispositif reste à approuver et à tester. Sans lui, un préavis de 30 jours
ne doit pas être annoncé.

## 5. Déploiement contrôlé, toujours fermé

La procédure future doit rester séparée de toute autorisation d'ouverture :

1. revue humaine du lot, `git diff --check`, CI complète et production de
   digests amd64 ; aucun fichier runtime, secret ou artefact local ne doit
   entrer dans la release ;
2. vérifier l'attestation, le bundle et l'ancre de confiance depuis les outils
   actuels revus ; ne jamais approuver une release via un simple hash local ;
3. avec autorisation, vérifier la sauvegarde existante, l'espace disque, les
   timers, le snapshot complet et les marqueurs de maintenance, sans
   `forget`, `prune`, restauration de production ni divulgation de secrets ;
4. déployer le bundle attesté en configuration fermée, puis contrôler schéma,
   digests, HTTPS, santé API/BFF, verrou/counter et IA désactivée ;
5. exécuter les recettes autorisées avec données fictives et conserver les
   preuves minimisées ;
6. en incident, fermer les admissions explicitement et rester fermé. Ne pas
   réinitialiser le compteur, supprimer une donnée pour libérer une place,
   restaurer une ancienne base ou contourner le contrôleur de release.

La réouverture SQL, même après une livraison réussie, exige une décision humaine
distincte et ultérieure.

## 6. Décisions humaines et juridiques restantes

- [ ] Valider l'identité de l'exploitant, public visé, gratuité, hébergeur,
  prestataires, régions, transferts et contrats applicables.
- [ ] Qualifier responsable/sous-traitant, finalités, bases, catégories de
  documents, droits et canal de traitement des demandes.
- [ ] Choisir/valider un médiateur de la consommation si le cadre applicable
  l'exige, sans en désigner un sans preuve.
- [ ] Approuver les textes, leur archivage, leur version API et leurs URLs
  HTTPS publiques ; ne pas confondre brouillon, développement et approbation.
- [ ] Approuver les durées, responsabilités, journalisation et procédures de
  rétention/suppression/restauration ; la simulation ne vaut pas activation.
- [ ] Autoriser séparément les contrôles SMTP/B2/VPS et la recette de
  production fermée.
- [ ] Décider du calendrier de six mois, du préavis de 30 jours, de
  l'assistance et de l'absence actuelle d'export ZIP.
- [ ] Produire une autorisation datée de livraison puis, seulement si tous les
  points ci-dessous sont démontrés, une autorisation distincte d'ouverture.

## 7. Checklist Go / No-Go

### No-Go actuel

- [x] Inscriptions publiques fermées, verrou SQL conservé, IA désactivée.
- [x] Suppression des sauvegardes désactivée et protections de release conservées.
- [ ] Worktree propre, lot revu, CI/digests/bundle attestés.
- [ ] Sauvegarde et restauration isolée de la stack cible démontrées.
- [ ] Timers, logs, SMTP, B2, reverse proxy et alertes vérifiés sans secrets.
- [ ] Pages/lien/version des CGU réellement publics, HTTPS, anonymes et approuvés.
- [ ] Textes juridiques, prestataires, rôles, durées, réclamations/médiation validés.
- [ ] Inventaire de cookies/traceurs sur la stack livrée et décision de consentement.
- [ ] Téléchargement HTTPS et parcours d'assistance de fermeture validés.
- [ ] Décisions explicites de livraison, maintien fermé et ouverture séparées.

**Règle de décision :** toute case non cochée maintient le No-Go. Une CI verte,
un déploiement fermé, un brouillon juridique ou une simulation de rétention ne
vaut pas autorisation d'ouverture.

## Sources

- `docs/SPRINT_14_8_LEGAL_READINESS_REVIEW.md`
- `docs/SPRINT_14_9_LEGAL_PAGES_IMPLEMENTATION_REPORT.md`
- `docs/SPRINT_14_10_COMPLIANCE_READINESS_REPORT.md`
- `docs/SPRINT_14_11_DATA_LIFECYCLE_REPORT.md`
- `docs/SPRINT_14_12_DOCUMENT_EXPORT_REPORT.md`
- `docs/SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md`
