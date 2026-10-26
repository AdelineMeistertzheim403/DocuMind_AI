# Sprint 14.7.7 — Publication GitHub et Pull Request Draft

26 octobre 2026. Opérations limitées à l'autorisation fournie : branche, whitelist
de 79 fichiers, commit unique, push de cette branche, création de PR Draft et lecture
des premiers résultats CI. Référence du périmètre :
[préparation 14.7.6](SPRINT_14_7_6_PR_PREPARATION_REPORT.md).

**Publication de branche et ouverture de PR réussies. La CI n'est pas terminée.**
La PR ne constitue ni une RC utilisable approuvée, ni une permission de fusion,
de publication d'images, de déploiement ou d'ouverture publique.

## 1. Vérifications préalables

- Dépôt local confirmé : `C:/Users/Adeline/Documents/DocuMind_AI`.
- Branche initiale : `preparation/sprint-14-5-ux-email-abuse` ; HEAD initial
  `8243e0511c5505a9cc70f76ad02392f7a816590d` ; index vide.
- Exactement **79 chemins**, 35 suivis modifiés et 44 non suivis ; correspondance
  exacte avec la whitelist de la section 1 du rapport 14.7.6, sans ajout inattendu.
- Chaque chemin régulier, non symlink, résolu à l'intérieur du dépôt ; aucun var,
  env privé, document personnel, archive, dump, base, certificat, wheelhouse, log,
  venv, dist ou résultat Playwright parmi les candidats.
- Scan des contenus candidats : aucun marqueur de clé privée ou credential courant
  identifié. Aucun secret affiché ; ce scan ne remplace pas une revue humaine.
- Origines fetch **et** push confirmées vers le même dépôt GitHub attendu.
- Identité de commit configurée ; aucun hook Git actif détecté.
- Branche locale et distante de revue absentes avant création. Aucune PR existante
  sur cette branche ni PR ouverte correspondante au travail Sprint 14.
- GitHub confirme l'accès en écriture du compte authentifié au dépôt et `main`
  protégée, pointant sur le HEAD initial. Son ascendance est vérifiée localement.
- Les quatre rapports demandés, les workflows et leurs modifications ont été lus.
  CI : push limité à main, événement pull_request autorisé, publish conditionné à
  main hors PR et aux trois jobs réussis. Deploy : workflow_dispatch uniquement,
  main et environnement production. Aucun pull_request_target/workflow_run ajouté.

Le CLI `gh` n'était pas disponible dans le PATH ni aux emplacements vérifiés.
L'opération a utilisé Git natif et l'API REST GitHub avec l'authentification existante
du gestionnaire d'identifiants Git. Le credential reste en mémoire ; aucun token
dans un fichier, une URL, un argument de commande, un rapport ou une sortie de log.
Aucun outil installé et aucun réglage d'authentification/secrets modifié.

## 2. Branche et index

Branche créée depuis l'arbre courant, sans checkout de main :
`preparation/sprint-14-review`.

Indexation par une liste explicite de **79 arguments de chemins**, issue de la
whitelist validée ; aucun add global, aucun glob. Contrôles avant commit :

- noms indexés exactement égaux aux 79 chemins autorisés ;
- `git diff --cached --check` réussi ;
- contenu intégral indexé comparé aux empreintes de l'instantané approuvé ;
- aucun filtre/normalisation n'a changé les octets, aucun fichier binaire ;
- 44 Python indexés analysés par AST ; recherche de marqueurs sensibles sur les blobs ;
- présence des modules CI et des sources du bundle ; diff des workflows recontrôlé ;
- aucun changement restant hors index et aucun fichier non suivi inattendu.

Le diff complet de 720 133 octets a été conservé uniquement sous var pour contrôle,
SHA-256 `584aa3e5fc15c4a95a76a8083bdfff232f643c5e0ea30da1c9ce7f2fd92ec509`.
Il n'est pas joint à la PR. L'inventaire détaillé publié reste dans le rapport 14.7.6.

Le bundle de sécurité demeure neuf fichiers générés/copiés par la CI selon le code
validé ; les inventaires des runners restent séparés. Aucun bundle de release réel,
digest d'image ou approbation root n'est fabriqué par cette publication Git.

## 3. Commit unique

```text
f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2
```

Message exact :

```text
feat(security): préparer la revue de la bêta contrôlée et sécuriser la livraison
```

Parent unique : `8243e0511c5505a9cc70f76ad02392f7a816590d`.
**79 fichiers : 10 171 insertions, 153 suppressions**, documentation comprise.
Vérification après commit : mêmes chemins, même parent attendu, message exact et
arbre propre. Aucun commit existant réécrit, aucun rebase, amend ou merge.

## 4. Identité distante et push

Dépôt : [AdelineMeistertzheim403/DocuMind_AI](https://github.com/AdelineMeistertzheim403/DocuMind_AI).
Dépôt public au contrôle API ; cela est distinct de la Registry privée d'images.

Avant push : `git fetch origin` réussi, validation de `origin/main` comme ancêtre,
un seul commit d'avance, absence de branche distante vérifiée à nouveau, arbre
propre, origins et règles CI relues depuis le commit.

Seule branche poussée, avec upstream :

```text
origin/preparation/sprint-14-review
f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2
```

Push réussi et SHA distant confirmé en lecture par ls-remote. Aucun force push,
push main ou autre branche ; aucun second push. Le push de cette branche n'entre
pas dans le filtre push/main de ci.yml. Aucun workflow lancé manuellement.

## 5. Pull Request créée et relue

**[PR nº 6](https://github.com/AdelineMeistertzheim403/DocuMind_AI/pull/6)**

| Propriété | Valeur confirmée après création |
| --- | --- |
| Source | preparation/sprint-14-review |
| Source SHA | f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2 |
| Cible | main |
| Base SHA observée | 8243e0511c5505a9cc70f76ad02392f7a816590d |
| État | open |
| Draft | true |
| Auto-merge | absent/désactivé |

Titre exact :

```text
Sprint 14 : bêta contrôlée, intégrité documentaire et livraison sécurisée — revue en brouillon
```

La description de la section 4 du rapport 14.7.6 a été reprise, avec RF10-04
également explicité dans la liste des risques. Elle conserve tous les résultats
locaux et limites SQL-01/02/03, RF10-03, SMTP/B2/VPS, fusion et ouverture. Le titre,
le corps, la source, la cible, le SHA et le statut Draft ont été relus depuis GitHub.
Aucune preuve privée de var jointe, aucune conversion en Ready for review.
Un seul appel de création, sans retry ; aucune fusion ou modification ultérieure.

## 6. CI automatiquement déclenchée

Dernière observation : **26 octobre 2026, 12:58:08 UTC**.

[Run CI nº 15 — ID 40326201923](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923),
tentative **1**, événement `pull_request`, workflow `.github/workflows/ci.yml`.
Le run est relié à la PR nº 6, à la branche de revue et au SHA source attendu.

| Job | État API observé | Conclusion disponible |
| --- | --- | --- |
| [python](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583422638) | in_progress | Aucune ; ne pas annoncer réussi |
| [windows](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583423054) | in_progress | Aucune ; ne pas annoncer réussi |
| [frontend](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583422920) | completed | success |
| publish | Pas de job exposé dans la liste API à cette observation | Non exécuté ; exclusion prévue par la condition PR, état terminal skipped pas encore observé |
| deploy | Aucun run associé au SHA de cette mission | Non déclenché |

Aucune étape en échec dans les jobs retournés lors de ce contrôle. Cela n'est pas
une promesse de succès final : python/windows sont encore en cours. Les nombres
exacts de tests CI et leurs éventuels ignorés n'ont pas été relevés dans les logs
à ce stade ; ne pas réutiliser les chiffres locaux comme des résultats CI.
Aucun job annulé, relancé ou exécuté manuellement par cette mission.

SHA source/run : `f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`.
SHA de merge synthétique de PR indiqué par l'API :
`502b1e07ceb4ddd98d53b46a17cfb4e48afbe205`.
Ce dernier est un commit de test de PR, **pas une fusion autorisée sur main**.
Le checkout réel de chaque job n'est pas certifié par lecture de ses logs dans
ce premier contrôle ; la relation run/source/base/PR est confirmée via l'API.

## 7. Publication Registry et déploiement : portée des preuves

Aucun appel direct de l'agent à la Registry privée, aucune publication d'image,
aucun lancement manuel de publish/deploy, aucun accès SSH/VPS. La CI autorisée
peut construire/puller ses images de test sur son runner ; ce n'est pas une
publication de release dans la Registry privée.

La condition publish est fausse pour l'événement pull_request observé ; aucun
job de publication exécuté n'est retourné par l'API. Aucun workflow deploy associé
à ce SHA n'est observé. Aucune approbation production, modification de main,
installation systemd ou action de déploiement effectuée.

Cette conclusion porte sur les actions de la mission et les runs associés au SHA
consulté. La Registry et le VPS n'ont volontairement pas été inspectés ; elle ne
certifie pas l'absence d'activité indépendante par un autre acteur. Le statut final
skipped de publish reste à relire lorsque la CI terminera.

## 8. Anomalies, risques et limites

Aucun échec des contrôles bloquants Git, de commit, de push ou de création de PR.
L'absence de gh est traitée par l'API existante, sans installation ni changement
de permissions. Les validations locales de 14.7.6 ne sont pas relancées ou annoncées
comme de nouvelles suites réussies dans cette mission de publication.

- **R14-SQL-01** : cause historique du 503 toujours inconnue.
- **R14-SQL-02** : corrigé localement et testé sous les fautes définies ; pas de
  réparation automatique d'une incohérence ancienne.
- **R14-SQL-03** : issue d'inscription incertaine et mail absent possibles ; décisions
  opératrice et procédure de récupération encore nécessaires.
- **RF10-03** : supply chain partiellement verrouillée ; onze wheels Linux 3.13,
  outils PEP 517, bases, paquets système, commit pgvector et provenance à qualifier.
- **RF10-04** : publication partielle possible lors d'une livraison ultérieure ;
  arrêt et conservation des preuves, aucune suppression/retagging/relance automatique.
- Aucun test réel SMTP/B2/VPS dans cette mission ; aucun risque accepté implicitement.

La PR Draft n'est pas une RC approuvée. Une future fusion pourrait déclencher la
publication automatique sur main ; elle reste expressément interdite sans décision
nouvelle couvrant cet effet. Inscriptions publiques, IA, quota cinq cumulatif et
schéma 0007 ne sont pas modifiés par cette publication de branche.

## 9. État local après opérations

Juste après push et création de PR : branche synchronisée avec son upstream,
arbre propre. Le présent rapport est ensuite créé **localement seulement** :

```text
## preparation/sprint-14-review...origin/preparation/sprint-14-review
?? docs/SPRINT_14_7_7_GITHUB_DRAFT_PR_REPORT.md
```

Index vide ; ce rapport est intentionnellement non suivi, absent du commit et de
la PR. Aucun second commit, amend, ajout silencieux ou second push pour le publier.
Les scripts d'opération, whitelist, empreintes, corps de PR et constats techniques
restent sous var, ignoré ; aucun token n'y est enregistré.

## 10. Prochaines étapes recommandées

1. Attendre puis relire les conclusions réelles de python/windows/frontend sur
   le même SHA ; relever les totaux/ignorés et publish skipped, sans rerun automatique.
2. Si échec, conserver les diagnostics expurgés, analyser et obtenir une décision
   avant correction, nouveau commit ou push. Ne pas retenter la publication en bloc.
3. Maintenir la PR Draft et l'auto-merge désactivé ; réaliser la revue humaine des
   79 fichiers, des invariants et des risques ouverts.
4. Traiter séparément la qualification RF10-03 et les décisions SQL-01/SQL-03,
   selon le plan 14.7.6 ; aucune acquisition ou activation supplémentaire ici.
5. Exiger des autorisations distinctes pour tout futur commit/push, changement de
   statut, fusion/publication, intervention VPS et ouverture. Le rapport local ne
   doit pas être poussé silencieusement.

**Résultat : branche GitHub publiée et PR nº 6 ouverte en brouillon ; frontend vert,
python et windows encore en cours au dernier contrôle. Arrêt après ce rapport.
Aucune fusion, RC utilisable approuvée, livraison ou ouverture publique.**
