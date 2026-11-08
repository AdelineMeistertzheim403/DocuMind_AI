# Docnelo Public Beta — Préparation juridique des dix admissions

31 octobre 2026. **NON APPROUVÉ — NO-GO juridique.** Ce document recense le travail nécessaire ; il ne remplace pas la décision de l’exploitante ni une validation juridique. Aucun texte publié, version acceptée ou flag PUBLIC_LEGAL_READY n’est modifié.

## Documents effectivement présents dans Web R2

| Document | Référence | Écart avant ouverture |
| --- | --- | --- |
| CGU courantes | beta-2026-10-v1 | Marque DocuMind AI et plafond cinq ; litiges/médiation à préciser ; rendu marqué brouillon |
| CGU historiques | beta-2026-10-26-draft-1 | Clauses explicitement à compléter ; conserver le texte et son URL |
| Mentions légales | 2026-10-26-draft-2 | Identité EI, SIREN, adresse, téléphone, contact et directrice déjà renseignés ; ne pas les qualifier de champs vides. Vérifier leur exactitude et l’hébergeur contractuel OVH/infrastructure France ; nouvelle version pour Docnelo |
| Confidentialité | 2026-10-26-draft-2 | OVH, Backblaze B2 et Google/Gmail déjà cités ; « prestataires à documenter », durées et résidus à confirmer, cookies à recenser ; DocuMind persiste |
| Rendu commun | Legal.tsx, LegalNavigation | Avertissement de non-approbation et liens « brouillon » partout ; aucun état d’approbation publié n’est implémenté |

La présence de coordonnées ne prouve pas leur exactitude. Le domaine technique documind.adelinemeistertzheim.fr peut rester ; il doit être clairement relié à Docnelo dans la nouvelle notice. Les occurrences DocuMind des archives restent historiques. Les contenus non committés du workspace ne sont pas une nouvelle version autorisée.

## Décisions humaines et preuves manquantes

| Sujet | Décision / preuve à recueillir |
| --- | --- |
| Capacité de cohorte | Dix admissions publiques cumulatives, comptes en attente/supprimés inclus ; préciser les comptes historiques/invités et les conditions de fin de bêta |
| Exploitante | Coordonnées publiées, statut, identification professionnelle, publication et règles de réclamation/médiation applicables validées |
| Hébergement | Identité exacte de l’entité contractuelle OVH, coordonnées et localisation effective de cette infrastructure, pièces opérateur |
| B2 | Entité contractuelle, région réelle du bucket, sous-traitants, accès/support, chiffrement et gestion des clés, rétention effective ; la région n’est pas déduite de la marque Backblaze |
| SMTP | Prestataire réellement utilisé, contrat/configuration et garanties ; distinguer Gmail personnel et offre professionnelle éventuelle sans inventer laquelle est active |
| Transferts | Cartographie des flux et accès hors EEE éventuels, mécanismes/garanties applicables à vérifier ; un bucket européen ou le chiffrement ne suffit pas à affirmer « aucun transfert » |
| Conservation | Le texte promet non-vérifiés 7 jours, logs 90 jours, sauvegardes 3 mois, demandes RGPD 3 ans. Prouver les tâches/procédures correspondantes ; « données résiduelles … à définir » reste incomplet |
| Effacement | Responsable du traitement manuel, délais, exceptions justifiées, témoins anti-retour et réapplication après restauration ; aucun recyclage de place |
| Traceurs | Inventaire réel des cookies/session/CSRF, finalités, durées et attributs ; ne pas ajouter un bandeau ou une nouvelle base de consentement sans besoin établi |
| Droits et bases légales | Vérifier finalités/bases, destinataires, canal de demande, délais, réclamations, rôles pour documents professionnels ; accepter les CGU n’équivaut pas à consentir à tous les traitements RGPD |
| IA | Texte explicite d’indisponibilité pendant cette phase ; aucune activation implicite ou promesse de service IA |

Les obligations d’information couvrent notamment finalités, bases, destinataires, conservation et droits ; elles doivent être cohérentes avec les traitements réels. Référence consultée : [CNIL — Informer les personnes](https://www.cnil.fr/fr/informer-les-personnes). L’identification de l’éditeur et de l’hébergeur doit être vérifiée selon le statut : [Service Public — Mentions obligatoires](https://entreprendre.service-public.gouv.fr/vosdroits/F37351?lang=fr). Pour d’éventuels transferts, vérifier le mécanisme approprié au flux constaté : [CNIL — Garanties de transfert hors UE](https://www.cnil.fr/fr/cnil-direct/question/reglement-europeen-quelles-formalites-pour-les-transferts-hors-ue?trk=article-ssr-frontend-pulse_x-social-details_comments-action_comment-text). Ces références ne certifient pas la conformité du service.

## Préparation des nouvelles versions

Préparer une entrée distincte de CGU, un document de confidentialité versionné et une notice nouvelle. L’identifiant final, la date d’effet, l’empreinte de chaque texte et la décision d’approbation doivent figurer dans le dossier opérateur. Le brouillon de travail peut s’appeler docnelo-beta-10-2026-10-v1-draft ; il n’est ni référencé par l’API ni publié par ce travail.

Proposition de clause de capacité à soumettre à approbation : « Cette phase de bêta est limitée à dix admissions publiques cumulatives au total. Une admission est attribuée lors de la création validée du compte, avant vérification de l’adresse email. Un abandon, une absence de vérification ou une suppression ultérieure ne restitue pas de place. Les comptes historiques et invités sont traités selon les conditions de cohorte précisées par l’exploitante. Les nouvelles inscriptions peuvent être fermées sans empêcher l’accès des comptes existants éligibles. Les fonctionnalités d’intelligence artificielle restent indisponibles. »

Ne pas publier la dernière phrase relative aux comptes historiques sans décision explicite ; ne pas inventer les régions B2/SMTP ou des durées. Reprendre les clauses valides existantes dans de nouvelles versions, corriger DocuMind vers Docnelo seulement dans celles-ci, conserver les anciens textes et liens inchangés. La notice/confidentialité actuelle n’a pas le même mécanisme d’archives multiples que les CGU : il faut prévoir l’archivage des nouvelles versions et leurs URL avant de remplacer les pages courantes.

L’UI ne doit retirer ses avertissements qu’après la publication approuvée. PUBLIC_LEGAL_READY est une garde de configuration déclarative, pas une validation automatique de contenu. Vérifier l’égalité entre version des CGU API, version affichée, URL permanente, payload d’inscription et preuve sauvegardée.

## Acceptations et historique

Le profil public standard enregistre terms_version et terms_accepted_at sur users, avec date de vérification séparée. Les jetons ne servent pas de preuve d’acceptation. Les archives CGU fournissent le texte auquel se réfère l’identifiant. Ne pas réassigner rétroactivement une nouvelle version aux comptes existants. Pour toute réacceptation future, définir un enregistrement distinct conservant l’ancienne preuve ; le code courant n’est pas un journal exhaustif des réacceptations.

Les sauvegardes incluent la base contenant ces champs ; les preuves lifecycle doivent rester cohérentes après restauration. Une sauvegarde restaurable ne démontre pas à elle seule la conformité de conservation ni l’approbation des documents.

**NO-GO tant que les contenus sont brouillons, les promesses de conservation non étayées et les décisions humaines non consignées.**
