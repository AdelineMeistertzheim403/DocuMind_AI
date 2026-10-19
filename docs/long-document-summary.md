# Résumés approfondis — correction des documents longs

## Origine du rejet

Le résumé du Sprint 3 regroupait les chunks sous `AI_MAX_INPUT_TOKENS` (16000 par défaut), en comptant prudemment les octets UTF-8 du texte, des instructions et du schéma JSON, plus une marge. Le nombre de groupes, augmenté d’une réduction finale unique, devait rester sous `AI_MAX_SUMMARY_STEPS=5`. Cette condition applicative déclenchait 413 **avant tout envoi**, bien avant la fenêtre réelle du modèle. Une unique réduction pouvait aussi devenir trop grande.

Les documents, pages et chunks existants restent la source des textes et références. Les plafonds d’import restent 10 Mo, 200 pages et un million de caractères par défaut ; ils ne sont pas augmentés. La borne d’entrée par appel et la borne de sortie ne sont pas augmentées non plus.

## Nouveau plan hiérarchique

`LongDocumentSummarizer`, dans `backend/ai/long_plan.py`, produit un plan déterministe et chiffré **sans appel fournisseur**. Un document qui tient dans un seul appel conserve le résumé direct. Les autres passent par une tâche persistante.

Le découpage privilégie les paragraphes et les titres de sections reconnus. Lorsque les chunks de l’extracteur coupent une section ou qu’un paragraphe est trop grand, des groupes de fragments bornés sont utilisés, avec préférence pour les frontières de phrases et un chevauchement contrôlé de 200 caractères. Les chunks et leurs textes enregistrés ne sont jamais modifiés. Chaque fragment garde son UUID de chunk et sa page.

Chaque groupe donne un résumé intermédiaire compact et structuré. Les résultats sont ensuite fusionnés deux par deux sur plusieurs niveaux. Un arbre de `N` parties nécessite `2N−1` étapes, sans appel supplémentaire pour un nœud isolé d’un niveau. Le dernier appel produit le contrat global `SummaryContent` déjà utilisé : résumé général, points clés, informations importantes, limites et sources.

La taille maximale d’un intermédiaire est calculée pour que **deux intermédiaires puissent toujours tenir** dans l’appel suivant, y compris le schéma final. Cette vérification prend aussi en compte les échappements JSON les plus coûteux. Les entrées réelles sont contrôlées à nouveau avant chaque envoi. Le comptage est une borne prudente par octets UTF-8 compatible avec une tokenisation byte-level BPE ; ce n’est pas une approximation « caractères divisés par quatre ».

`AI_MODEL_CONTEXT_TOKENS=128000` est une borne applicative prudente ; entrée et sortie doivent tenir ensemble. La [fiche OpenAI du modèle configuré](https://developers.openai.com/api/docs/models/gpt-5.6-luna), consultée le 19 octobre 2026, annonce une fenêtre plus grande. La configuration reste sous le seuil de tarification des contextes longs. Pour un autre modèle, vérifier ses capacités et adapter cette borne ainsi que les tarifs ; aucun changement automatique de modèle n’est effectué.

Les nouvelles limites sont explicites :

| Variable | Défaut | Rôle |
|---|---|---|
| `LONG_SUMMARY_MAX_PARTS` | 128 | Groupes de lecture maximum |
| `LONG_SUMMARY_MAX_CALLS` | 255 | Étapes logiques maximum |
| `LONG_SUMMARY_OVERLAP_CHARS` | 200 | Recouvrement de texte entre groupes, au maximum |
| `AI_MODEL_CONTEXT_TOKENS` | 128000 | Fenêtre applicative entrée + sortie |

Les tentatives fournisseur sont également bornées : au maximum deux fois le nombre d’étapes prévu, sans dépassement de la réservation. Le plafond de parties ou d’appels peut encore refuser un document exceptionnellement volumineux ; aucun texte n’est tronqué pour le faire passer.

## Réservation, coûts et reprise

Le plan affiche la réservation maximale : borne d’entrée et de sortie × nombre d’étapes × marge de deux tentatives. L’application réserve cette somme dans **une transaction atomique unique**, avec les mêmes verrous, plafonds et contrôles BYOK qu’au Sprint 3. Un résumé utilisateur représente une seule réservation et un seul décompte du quota résumé ; ses appels internes alimentent les lignes d’usage, pas de nouveaux quotas utilisateur.

Le frontend demande une confirmation spécifique du coût maximal et transmet `approved_maximum_usd`. Si le plan a augmenté entre affichage et confirmation, le serveur renvoie 409 et demande de recharger l’estimation. Les appels directs à l’API peuvent également fournir ce plafond ; sans ce champ, le consentement explicite et le plafond du compte restent obligatoires.

Les tokens réels sont enregistrés à chaque réponse, y compris une sortie invalide. Les étapes réussies sont validées et persistées avant la suivante. La réservation globale reste en place durant une pause afin de permettre une reprise sans nouvelle admission ni nouveau décompte du quota. Le coût connu est réconcilié et le reliquat libéré à la fin ou à l’annulation.

Une erreur connue peut être reprise dans la même tâche, dans les limites restantes. Les étapes validées sont relues en base et ne sont pas refacturées. Un appel réseau ambigu conserve sa réservation et bloque la reprise automatique : il a pu être facturé. La procédure administrative du Sprint 3 permet de comptabiliser conservativement son maximum ; elle ne rembourse pas une charge inconnue.

L’annulation empêche les appels suivants. Elle ne peut pas annuler un appel déjà transmis : sa réponse est comptabilisée avant l’arrêt. Une annulation après un échec ambigu ne libère pas une charge incertaine. Une nouvelle demande après annulation est une nouvelle admission, nécessite une nouvelle confirmation et réutilise les étapes compatibles déjà validées. Sa réservation reste calculée prudemment sur le plan complet.

Les plafonds DocuMind restent **estimatifs**, sans garantie de plafond absolu de facturation OpenAI. Les consommations d’autres applications ne sont pas prises en compte.

## Worker et stockage

La migration `0005_persistent_long_summary_steps.py` ajoute :

- `long_summary_jobs` : propriétaire, document, réservation unique, plan, configuration non secrète figée, état, progression et demande d’annulation ;
- `summary_steps` : nœud unique par tâche, état, résumé validé, chunks et pages sources.

Les états sont `pending`, `processing`, `completed`, `partial`, `failed` et `cancelled`. Une page n’est affichée comme entièrement traitée que lorsque tous les groupes qui la contiennent sont validés. Les pages vides sont distinguées. Les parties encore absentes et les résumés intermédiaires disponibles sont consultables ; une tâche partielle n’est jamais présentée comme un résultat intégral.

Un **thread worker dédié**, distinct des handlers HTTP, consomme les tâches. La réponse de création est immédiate, sans attendre les appels OpenAI. Le plan, les étapes et la comptabilité sont persistants ; la file d’exécution et les références de session restent en mémoire.

Ce worker reste dans le même processus API pour accéder au coffre BYOK éphémère, qui ne peut pas être lu depuis un autre processus. Un service worker distribué exigerait d’abord un coffre de sessions sécurisé et un transport interne adaptés. Le MVP conserve donc la contrainte d’un seul processus API ; il ne prétend pas fournir une file distribuée avec reprise automatique.

Avant chaque appel, le worker revalide session, clé et mode. Après expiration, déconnexion ou arrêt, une reconnexion et une reprise explicite sont nécessaires. Une étape marquée `processing` lors d’un arrêt brutal devient incertaine au redémarrage et n’est pas relancée. Les clés et tokens de session ne sont jamais enregistrés dans le plan ou la configuration de la tâche.

Les textes restent des données non fiables, sans outils ou exécution autorisés au modèle. Chaque référence intermédiaire doit appartenir au contexte reçu. La réduction ne peut citer que les références validées de ses enfants. Le résultat final est rattaché aux vrais chunks/pages. Les résumés peuvent néanmoins perdre des détails ou contenir une erreur factuelle ; une référence valide ne remplace pas la vérification humaine.

La suppression applicative conserve le blocage des documents ayant une réservation active. Les tâches et étapes sont supprimées par cascade avec le document ; les écritures financières restent conservées sans texte.

## API et interface

| Route `/api/v1` | Fonction |
|---|---|
| `GET /documents/{id}/summary-plan` | Plan, parties, étapes, niveaux et maximum estimé ; aucun appel IA |
| `POST /documents/{id}/summary-jobs` | Consentement, UUID et plafond approuvé facultatif ; 202 |
| `GET /documents/{id}/summary-jobs` | Dix dernières tâches autorisées |
| `GET /summary-jobs/{id}` | Progression persistée, pages restantes, intermédiaires et résultat éventuel |
| `POST /summary-jobs/{id}/resume` | Reprise idempotente après reconnexion, consentement requis |
| `POST /summary-jobs/{id}/cancel` | Annulation des étapes restantes |

`POST /documents/{id}/summarize` reste compatible pour les petits documents : 200 avec le résultat direct. Pour un document long, il renvoie désormais 202 avec la tâche au lieu du rejet fondé sur cinq étapes. Le frontend utilise l’endpoint de tâche après affichage et confirmation du plan. L’historique final reste accessible par les routes du Sprint 3.

Les erreurs réutilisent 401/403/404 pour authentification et isolation, 402 pour le budget, 409 pour conflit/coût modifié/charge incertaine, 413 pour les limites, 429 pour quota ou concurrence, et des codes fournisseur contrôlés. Une tâche acceptée peut ensuite être partielle ou échouée : consulter son état. Aucun message ne contient une clé ou du texte privé.

## Validation et mémoire local

Les tests MockAIProvider couvrent résumés directs, PDF synthétiques de 20, 53 et 200 pages, pages vides, frontières de paragraphes, arbre multi-niveaux, budget initial, concurrence, erreurs connues et ambiguës, interruption/reprise, annulation, isolation, BYOK, sources inventées et unicité du décompte utilisateur. React vérifie confirmation du coût, progression provenant du serveur et reprise sans nouvelle demande.

Deux documents de 53 pages présents dans la base ont été examinés **uniquement pour construire le plan**. Leur texte actuellement enregistré compte environ **93142 caractères**, au lieu des 92319 signalés initialement. Le plan calculé est de **16 parties, 31 étapes, cinq niveaux**, avec une réservation maximale de **0,33728 USD** selon les paramètres locaux lors de la vérification. Aucun texte n’a été envoyé à OpenAI pour cette validation.

Pour valider réellement le mémoire :

1. Se reconnecter sur HTTPS après la mise à jour ; reconnecter et valider sa clé si nécessaire.
2. Ouvrir sa fiche, puis « Résumé approfondi ». Vérifier le plan et le maximum actuel, qui peuvent varier avec les paramètres et tarifs.
3. Vérifier que le plafond disponible couvre toute la réservation. Ne pas augmenter arbitrairement la borne d’entrée.
4. Autoriser l’envoi, cocher la confirmation chiffrée, puis lancer volontairement la tâche.
5. Suivre les étapes réelles ; quitter puis rouvrir la fiche pour vérifier leur persistance.
6. Contrôler couverture des pages, limites, résumé final, sources et coûts. En cas d’expiration, se reconnecter et reprendre les étapes restantes.

La génération réelle de ce mémoire n’a pas été effectuée par l’agent : elle attend votre confirmation explicite dans l’interface. Sa qualité et son coût réellement facturé restent donc à valider.


## Correction des réponses rejetées pendant la réduction

Diagnostic du 19 octobre 2026 : sur le mémoire de 53 pages, les 16 parties puis quatre
réductions ont été validées (20 étapes sur 31). La réduction suivante a échoué plusieurs
fois. Les anciennes réponses rejetées ne sont pas conservées : le code `invalid_output`
ne permet pas de déterminer rétrospectivement la cause exacte. Un ancien appel avait
atteint 1 200 tokens de sortie ; les derniers appels rejetés étaient sous cette limite.

Les sources sont désormais restreintes aux identifiants du contexte par une énumération
dans le schéma Structured Outputs, avec une seconde validation locale. Les références
valides r?pétées sont dédupliquées ; aucune source inconnue n'est acceptée. La taille de
cette énumération est incluse dans le calcul conservateur du contexte des nouveaux plans.
Les étapes validées des tâches existantes restent compatibles.

Les nouveaux codes distinguent `output_truncated`, `provider_refusal`, `invalid_json`,
`invalid_schema` et `invalid_references`. Les journaux de validation contiennent uniquement
les catégories d'erreurs, jamais le texte du fournisseur. Les tokens des réponses rejetées
restent comptabilisés. Le compteur de tentatives est corrigé pour compter les appels
réellement effectu?s, y compris lorsqu'une validation échoue.

Après mise à jour des conteneurs : recharger la page, reconnecter le compte et la clé BYOK,
puis utiliser **Reprendre les étapes restantes** sur la tâche partielle. Ne pas l'annuler
pour en recréer une. Le redémarrage ne lance aucun appel ; seule la reprise explicite le fait.
Une reprise peut être facturée ; les appels déjà réalisés ne sont pas remboursés.

Référence : [documentation officielle OpenAI sur Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
La correction est vérifiée avec des fournisseurs simulés ; aucune nouvelle génération payante
sur le mémoire n'est exécutée pendant le diagnostic.


Validation de cette correction : 85 tests backend existants passent ; cinq nouveaux cas
fournisseur et un nouveau cas de reprise passent aussi (91 cas distincts au total).
Frontend : 34 tests React et 19 tests BFF passent ; compilation TypeScript/Vite et
construction des images Docker API/web valides. Les simulations couvrent sortie tronquee,
refus, JSON invalide, enumeration des sources, deduplication, rejet d'une source inventee,
conservation des tokens facturables et reprise avec une seule reservation.
