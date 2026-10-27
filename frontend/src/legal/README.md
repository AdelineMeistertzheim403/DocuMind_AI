# Documents juridiques : brouillons uniquement

Source unique des textes affichés : `documents.ts`. Les trois documents sont
explicitement non approuvés. Les valeurs d'identité, contacts, prestataires,
durées, bases juridiques et garanties doivent être complétées après validation
humaine. Ne pas renseigner PUBLIC_LEGAL_READY à partir de la présence de ces pages.

## CGU et archives

Version initiale : `beta-2026-10-26-draft-1`, accessible à
`/cgu/versions/beta-2026-10-26-draft-1`, conservée sans modification.
Version courante proposée par l'exploitante : `beta-2026-10-v1`, accessible à
`/cgu/versions/beta-2026-10-v1`, toujours **brouillon non approuvé** malgré son
identifiant sans suffixe draft. `/cgu` désigne ce brouillon courant.
Une version inconnue ne retombe jamais sur le texte courant.

Pour une révision ultérieure, conserver l'entrée existante de `termsArchive`
et ajouter une nouvelle entrée avec un identifiant unique et le texte intégral.
Changer ensuite TERMS_VERSION. Ne pas réécrire une version déjà publiée, même
pour corriger une phrase : créer une révision. Les tests doivent vérifier que
les anciens liens continuent de rendre leur texte d'origine. Git apporte la
traçabilité ; ce registre applicatif n'est pas un stockage immuable certifié.

L'interface actuelle affiche toutes ces versions comme brouillons. Pour adopter
une première version approuvée, une modification revue doit expliciter son statut
et la preuve de validation ; ne pas retirer globalement les avertissements des
anciennes versions. Archiver le texte, sa version, son empreinte, sa date de
publication et la décision de l'exploitante dans un dossier adapté.

Les liens locaux de préparation sont distincts des URL configurées par l'API
pour accepter des conditions lors d'une inscription. L'envoi de terms_version
reste fondé sur les options API et validé côté serveur, sans substitution par
la version de brouillon. Après approbation, prévoir une URL absolue HTTPS vers
la version approuvée et PUBLIC_TERMS_VERSION identique ; URL de confidentialité
et mentions correspondantes. Aucun env n'est modifié par ce lot.
