// Published versions must be retained unchanged; add a new entry for each revision.
export const TERMS_VERSION = 'beta-2026-10-v1'
export type LegalBlock = {kind:'paragraph'; text:string}|{kind:'list'; items:readonly string[]}|{kind:'table'; headers:readonly string[]; rows:readonly (readonly string[])[]}
export type LegalDocument = {title:string; version:string; sections:readonly {title:string; text:string; items?:readonly string[]; blocks?:readonly LegalBlock[]}[]}
export const termsArchive:Readonly<Record<string,LegalDocument>> = {
  [TERMS_VERSION]: {
  "title": "Conditions générales d’utilisation",
  "version": "beta-2026-10-v1",
  "sections": [
    {
      "title": "Version et statut",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Version proposée : beta-2026-10-v1"
        }
      ]
    },
    {
      "title": "Article 1 — Objet",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Les présentes Conditions générales d'utilisation (CGU) définissent les modalités d'accès et d'utilisation de DocuMind AI, un service web de gestion et d'analyse documentaire proposé en version bêta."
        },
        {
          "kind": "paragraph",
          "text": "Le service est édité par Meistertzheim Adeline, entrepreneur individuel (EI)."
        }
      ]
    },
    {
      "title": "Article 2 — Public concerné",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "La bêta est destinée aux utilisateurs particuliers et professionnels majeurs, autorisés à utiliser le service et les documents qu'ils importent."
        },
        {
          "kind": "paragraph",
          "text": "Les utilisateurs professionnels restent responsables du respect de leurs propres obligations contractuelles et réglementaires."
        },
        {
          "kind": "paragraph",
          "text": "L'accès à la bêta est limité à cinq inscriptions publiques cumulatives."
        },
        {
          "kind": "paragraph",
          "text": "Une inscription consomme une place dans ce quota, y compris lorsque le compte reste non vérifié ou est supprimé. La suppression d'un compte ne libère donc pas automatiquement une nouvelle place."
        }
      ]
    },
    {
      "title": "Article 3 — Gratuité",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "La participation à la bêta est entièrement gratuite."
        },
        {
          "kind": "paragraph",
          "text": "Aucun moyen de paiement n'est demandé pour accéder aux fonctionnalités proposées dans cette version."
        },
        {
          "kind": "paragraph",
          "text": "Le passage éventuel à une offre payante fera l'objet d'une proposition distincte. Aucun paiement ni abonnement payant ne sera appliqué automatiquement au titre de ces CGU."
        }
      ]
    },
    {
      "title": "Article 4 — Inscription et sécurité du compte",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "La création d'un compte nécessite une adresse email valide, un mot de passe et l'acceptation de la version des CGU applicable au moment de l'inscription."
        },
        {
          "kind": "paragraph",
          "text": "Une vérification de l'adresse email est nécessaire à l'activation du compte."
        },
        {
          "kind": "paragraph",
          "text": "L'utilisateur doit préserver la confidentialité de ses identifiants et signaler toute suspicion d'accès non autorisé à adelinemeistertzheim40@gmail.com."
        }
      ]
    },
    {
      "title": "Article 5 — Fonctionnalités de la bêta",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "DocuMind AI propose des fonctionnalités de dépôt, consultation, gestion et analyse documentaire selon les capacités effectivement disponibles dans l'application."
        },
        {
          "kind": "paragraph",
          "text": "Les fonctionnalités peuvent évoluer au cours de la bêta."
        },
        {
          "kind": "paragraph",
          "text": "Les fonctions d'intelligence artificielle sont désactivées pendant cette phase initiale et ne font pas partie des prestations disponibles."
        }
      ]
    },
    {
      "title": "Article 6 — Documents autorisés",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Seuls les documents non sensibles peuvent être importés."
        },
        {
          "kind": "paragraph",
          "text": "Sont notamment interdits :"
        },
        {
          "kind": "list",
          "items": [
            "Les documents médicaux et autres données personnelles sensibles.",
            "Les pièces d'identité et documents comportant des secrets d'authentification.",
            "Les documents confidentiels appartenant à des tiers sans autorisation.",
            "Les documents protégés par un secret professionnel ou une obligation de confidentialité incompatible avec leur importation.",
            "Les contenus illicites ou portant atteinte aux droits de tiers."
          ]
        },
        {
          "kind": "paragraph",
          "text": "L'utilisateur garantit disposer des autorisations nécessaires pour les documents importés."
        },
        {
          "kind": "paragraph",
          "text": "DocuMind AI ne garantit pas la détection automatique des contenus interdits."
        }
      ]
    },
    {
      "title": "Article 7 — Propriété des documents",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "L'utilisateur conserve ses droits sur les documents déposés."
        },
        {
          "kind": "paragraph",
          "text": "Il autorise leur traitement technique dans la mesure nécessaire à la fourniture des fonctionnalités sollicitées et selon la Politique de confidentialité applicable."
        },
        {
          "kind": "paragraph",
          "text": "Cette autorisation ne constitue pas une cession de propriété intellectuelle à l'éditeur."
        }
      ]
    },
    {
      "title": "Article 8 — Disponibilité et caractère expérimental",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "La bêta est une version expérimentale susceptible de comporter des erreurs et des interruptions."
        },
        {
          "kind": "paragraph",
          "text": "L'éditeur peut intervenir pour corriger des anomalies, maintenir la sécurité ou faire évoluer le service."
        },
        {
          "kind": "paragraph",
          "text": "Ces dispositions ne limitent pas les droits impératifs reconnus aux utilisateurs par la législation applicable."
        }
      ]
    },
    {
      "title": "Article 9 — Durée de la bêta",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Date d'ouverture : 27/10/2026"
        },
        {
          "kind": "paragraph",
          "text": "Date de fin ou modalités de clôture : 08/11/2026"
        },
        {
          "kind": "paragraph",
          "text": "Les utilisateurs seront informés des modalités de fin de la bêta et, lorsque cela est applicable, des possibilités de récupération de leurs documents avant fermeture du service."
        },
        {
          "kind": "paragraph",
          "text": "Les modalités techniques de récupération et les délais de préavis devront être définis et vérifiés avant publication."
        }
      ]
    },
    {
      "title": "Article 10 — Suspension et suppression des comptes",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Un compte peut être suspendu lorsque cela est nécessaire pour assurer la sécurité du service, prévenir un abus ou faire respecter les présentes CGU."
        },
        {
          "kind": "paragraph",
          "text": "L'utilisateur peut demander la fermeture de son compte conformément aux fonctionnalités proposées et aux modalités de contact indiquées."
        },
        {
          "kind": "paragraph",
          "text": "La fermeture du compte ne signifie pas nécessairement l'effacement physique immédiat de toutes les données et copies de sauvegarde."
        },
        {
          "kind": "paragraph",
          "text": "Les demandes d'effacement et les données conservées pour des motifs légitimes sont traitées conformément à la Politique de confidentialité et aux règles applicables."
        }
      ]
    },
    {
      "title": "Article 11 — Protection des données",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Le traitement des données personnelles est décrit dans la Politique de confidentialité accessible à l'adresse :"
        },
        {
          "kind": "paragraph",
          "text": "https://documind.adelinemeistertzheim.fr/confidentialite"
        },
        {
          "kind": "paragraph",
          "text": "Cette politique est distincte des présentes CGU."
        }
      ]
    },
    {
      "title": "Article 12 — Responsabilités",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "L'utilisateur est responsable des documents qu'il choisit d'importer, des autorisations associées et de l'utilisation qu'il fait du service."
        },
        {
          "kind": "paragraph",
          "text": "L'éditeur met en œuvre les mesures nécessaires au fonctionnement et à la sécurité de l'application conformément à ses obligations."
        },
        {
          "kind": "paragraph",
          "text": "Les limitations contractuelles éventuellement retenues ne peuvent exclure les responsabilités que la loi interdit d'écarter."
        }
      ]
    },
    {
      "title": "Article 13 — Assistance et réclamations",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Pour toute demande concernant l'utilisation du service :"
        },
        {
          "kind": "paragraph",
          "text": "adelinemeistertzheim40@gmail.com"
        },
        {
          "kind": "paragraph",
          "text": "Les procédures de réclamation et de règlement des litiges, y compris les informations relatives à la médiation de la consommation lorsqu'elles sont applicables, doivent être précisées avant publication."
        }
      ]
    },
    {
      "title": "Article 14 — Droit applicable",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Les présentes CGU sont soumises au droit français, sous réserve des dispositions impératives applicables aux consommateurs et de leurs protections légales."
        }
      ]
    },
    {
      "title": "Article 15 — Modifications des CGU",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Toute version approuvée des CGU porte un identifiant unique et une date d'entrée en vigueur."
        },
        {
          "kind": "paragraph",
          "text": "Lorsqu'une modification nécessite une nouvelle acceptation, celle-ci est demandée à l'utilisateur dans les conditions prévues par le service et la réglementation applicable."
        },
        {
          "kind": "paragraph",
          "text": "Les versions antérieures sont conservées pour permettre de déterminer le texte applicable à chaque acceptation."
        },
        {
          "kind": "paragraph",
          "text": "Date d'entrée en vigueur : 26/10/2026"
        },
        {
          "kind": "paragraph",
          "text": "Version : beta-2026-10-v1"
        }
      ]
    }
  ]
},
  'beta-2026-10-26-draft-1': {
    title:'Conditions générales d’utilisation', version:'beta-2026-10-26-draft-1',
    sections:[
      {title:'Objet de la bêta',text:'DocuMind permet d’importer des PDF et TXT dans un espace personnel et d’effectuer des analyses documentaires classiques. La future bêta est limitée à cinq admissions cumulatives, comptes en attente de vérification compris. Une suppression ne restitue pas une place. Les inscriptions peuvent rester fermées.'},
      {title:'Compte et vérification',text:'Une adresse e-mail et un mot de passe sont nécessaires. La vérification de l’adresse est requise pour utiliser le compte public. Les liens expirent et sont à usage unique. Une réponse à une demande ne garantit ni admission ni livraison d’un e-mail ; un renvoi protégé est prévu.'},
      {title:'Documents et fonctionnalités',text:'Les documents et le texte extrait sont stockés sur le serveur du service, avec contrôle d’accès par propriétaire. Les fonctionnalités IA ne sont pas disponibles dans cette bêta. Une éventuelle activation future nécessitera une décision et une information distinctes.'},
      {title:'Suppression et fin du compte',text:'La demande de suppression désactive le compte et révoque ses sessions. L’effacement final relève d’un traitement administratif. Des copies de sauvegarde et certaines traces peuvent subsister. Les délais et procédures doivent encore être définis et approuvés.'},
      {title:'Clauses à compléter et valider',text:'À compléter par l’exploitante : identité des parties, public éligible et âge, gratuité ou prix, durée et fin de la bêta, droits sur les documents, usages interdits, assistance, suspension, responsabilités, réclamations et droit applicable. Aucune clause de renonciation aux droits ou garantie de disponibilité n’est présumée.'},
    ],
  },
}
export const legalNotice:LegalDocument = {
  title:'Mentions légales',version:'2026-10-26-draft-2',sections:[
    {
      title: 'Mentions légales — DocuMind AI',
      text: ""
    },
    {title:'1. Éditeur du service',text:'Le service DocuMind AI, accessible à l’adresse https://documind.adelinemeistertzheim.fr, est édité par :',items:[
      'Nom : Meistertzheim Adeline',
      'Statut : Entrepreneur individuel (EI), régime de la micro-entreprise',
      'SIREN : 523651404',
      'Adresse professionnelle : 42 rue de Rouffach, 68200 Mulhouse',
      'Email professionnel : adelinemeistertzheim40@gmail.com',
      'Téléphone professionnel : 0617293623',
      'Directrice de la publication : Meistertzheim Adeline',
    ]},
    {title:'2. Hébergement',text:'L’application DocuMind AI est hébergée par :',items:[
      'Hébergeur contractuel : OVH',
      'Adresse : 2 rue Kellermann, 59100 Roubaix, France',
      'Téléphone : 1007',
      'Localisation de l’infrastructure utilisée : France',
    ]},
    {title:'Services distincts',text:'Des services distincts peuvent être utilisés pour les sauvegardes et les emails transactionnels. Ces prestataires sont précisés dans la politique de confidentialité lorsque leur intervention concerne des données personnelles.'},
    {title:'3. Présentation du service',text:'DocuMind AI est une application web de gestion et d’analyse de documents. Une version bêta gratuite est prévue pour un nombre limité d’utilisateurs particuliers et professionnels. L’accès à la bêta est soumis aux Conditions générales d’utilisation. Les fonctionnalités d’intelligence artificielle sont désactivées pendant cette première phase de test.'},
    {title:'4. Propriété intellectuelle',text:'Sauf indication contraire, les éléments propres à DocuMind AI, notamment son interface, ses textes originaux, ses signes distinctifs et son code, sont soumis aux droits de leurs titulaires respectifs et aux licences applicables. Les utilisateurs conservent leurs droits sur les documents qu’ils importent. L’utilisation de DocuMind AI n’entraîne aucun transfert de propriété de ces documents à l’éditeur.'},
    {title:'5. Données personnelles',text:'Les modalités de traitement des données personnelles sont décrites dans la Politique de confidentialité, disponible à l’adresse : https://documind.adelinemeistertzheim.fr/confidentialite'},
    {title:'6. Contact',text:'Pour toute question relative au service : adelinemeistertzheim40@gmail.com. Pour toute demande relative aux données personnelles : adelinemeistertzheim40@gmail.com.'},
  ],
}
export const privacy:LegalDocument = {
  "title": "Politique de confidentialité",
  "version": "2026-10-26-draft-2",
  "sections": [
    {
      "title": "1. Responsable du traitement",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "DocuMind AI est exploité par :"
        },
        {
          "kind": "paragraph",
          "text": "Mme Adeline Meistertzheim, entrepreneur individuel (EI)."
        },
        {
          "kind": "paragraph",
          "text": "Adresse professionnelle : 42 rue de Rouffach, 68200 Mulhouse"
        },
        {
          "kind": "paragraph",
          "text": "Contact pour la protection des données : adelinemeistertzheim40@gmail.com"
        },
        {
          "kind": "paragraph",
          "text": "Pour les données nécessaires à la gestion des comptes et à l'exploitation du service, l'éditeur intervient en qualité de responsable du traitement."
        },
        {
          "kind": "paragraph",
          "text": "Le rôle juridique applicable aux contenus documentaires déposés par des utilisateurs professionnels doit être déterminé selon les usages et responsabilités effectifs."
        }
      ]
    },
    {
      "title": "2. Données traitées",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Pour fournir le service, DocuMind AI peut traiter les catégories suivantes :"
        },
        {
          "kind": "list",
          "items": [
            "Compte : adresse email, identifiant, empreinte sécurisée du mot de passe, statut de vérification, dates et version des CGU acceptées.",
            "Authentification : informations de session et données techniques nécessaires à la sécurité du compte.",
            "Documents importés : fichiers, noms, métadonnées, texte extrait et résultats des analyses proposées.",
            "Exploitation et sécurité : événements techniques, traces d'erreur, tentatives d'accès et événements de protection contre les abus.",
            "Correspondances : demandes d'assistance, demandes de suppression ou d'exercice des droits."
          ]
        },
        {
          "kind": "paragraph",
          "text": "Les champs effectivement obligatoires sont ceux nécessaires à la création du compte et au fonctionnement des fonctionnalités sollicitées. Sans les données indispensables, certaines fonctionnalités ne peuvent pas être fournies."
        }
      ]
    },
    {
      "title": "3. Finalités et bases légales",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Les traitements poursuivent les finalités suivantes :"
        },
        {
          "kind": "table",
          "headers": [
            "Finalité",
            "Base légale envisagée, à confirmer"
          ],
          "rows": [
            [
              "Création et gestion des comptes",
              "Exécution des CGU / du contrat de service"
            ],
            [
              "Vérification email et récupération d'accès",
              "Exécution du contrat et sécurité du service"
            ],
            [
              "Stockage et traitement des documents demandés",
              "Exécution du contrat, sous réserve de la qualification des rôles"
            ],
            [
              "Prévention des abus et protection de l'infrastructure",
              "Intérêt légitime, à documenter"
            ],
            [
              "Traitement des demandes relatives aux données",
              "Obligation légale, selon le droit exercé"
            ],
            [
              "Conservation de certaines preuves ou données",
              "Base légale à préciser selon la finalité"
            ]
          ]
        },
        {
          "kind": "paragraph",
          "text": "L'acceptation des CGU ne constitue pas un consentement général à tous les traitements de données."
        },
        {
          "kind": "paragraph",
          "text": "Aucun usage des adresses email à des fins de prospection commerciale n'est prévu pour cette bêta."
        }
      ]
    },
    {
      "title": "4. Documents autorisés",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Pendant la bêta, seuls les documents non sensibles sont autorisés."
        },
        {
          "kind": "paragraph",
          "text": "Les utilisateurs ne doivent notamment pas importer :"
        },
        {
          "kind": "list",
          "items": [
            "des données de santé ;",
            "des informations révélant les opinions politiques, convictions religieuses, appartenance syndicale, origine ethnique ou vie sexuelle ;",
            "des données biométriques ou génétiques sensibles ;",
            "des documents d'identité, mots de passe, identifiants bancaires ou secrets d'authentification ;",
            "des informations confidentielles appartenant à des tiers sans autorisation ;",
            "des documents soumis à un secret professionnel ou à des restrictions incompatibles avec le service."
          ]
        },
        {
          "kind": "paragraph",
          "text": "Les documents ordinaires peuvent néanmoins contenir des données personnelles : leur caractère « non sensible » ne les soustrait pas au RGPD."
        },
        {
          "kind": "paragraph",
          "text": "Cette restriction est une règle d'utilisation et ne constitue pas une garantie de détection automatique du contenu importé."
        }
      ]
    },
    {
      "title": "5. Stockage et sécurité",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Les documents sont conservés dans un environnement serveur exploité pour DocuMind AI, et non exclusivement sur l'appareil de l'utilisateur."
        },
        {
          "kind": "paragraph",
          "text": "Les données de compte et les informations documentaires sont enregistrées dans les systèmes techniques nécessaires au service."
        },
        {
          "kind": "paragraph",
          "text": "Des mesures d'authentification, de contrôle d'accès et de protection de l'infrastructure sont mises en œuvre."
        },
        {
          "kind": "paragraph",
          "text": "Aucune garantie de sécurité absolue, de chiffrement applicatif systématique au repos ou de localisation exclusivement française des données n'est formulée."
        }
      ]
    },
    {
      "title": "6. Prestataires et destinataires",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Les données peuvent être accessibles, dans la limite de leurs fonctions, à l'éditeur et aux prestataires techniques nécessaires à l'exploitation du service."
        },
        {
          "kind": "paragraph",
          "text": "Prestataires à documenter :"
        },
        {
          "kind": "list",
          "items": [
            "Hébergement : OVH",
            "Sauvegardes : Backblaze B2",
            "Email de vérification et de récupération : Google / Gmail ",
          ]
        },
      ]
    },
    {
      "title": "7. Intelligence artificielle",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Les fonctions d'intelligence artificielle sont désactivées pendant la bêta initiale."
        },
        {
          "kind": "paragraph",
          "text": "Les documents ne sont pas envoyés à un fournisseur d'IA du seul fait de leur importation."
        },
        {
          "kind": "paragraph",
          "text": "Toute activation ultérieure de fonctionnalités reposant sur un prestataire d'IA nécessitera une information adaptée et, si nécessaire, une évolution des conditions contractuelles et du cadre de protection des données."
        }
      ]
    },
    {
      "title": "8. Durées de conservation",
      "text": "",
      "blocks": [
        {
          "kind": "table",
          "headers": [
            "Catégorie",
            "Durée"
          ],
          "rows": [
            [
              "Comptes actifs",
              "Pendant l'utilisation du service, puis selon le traitement de fermeture"
            ],
            [
              "Comptes non vérifiés",
              "7 jours après création"
            ],
            [
              "Documents actifs",
              "Jusqu'à leur suppression ou fermeture du service, selon la procédure applicable"
            ],
            [
              "Données résiduelles de compte",
              "Conservation minimale justifiée par la sécurité et les quotas, à définir"
            ],
            [
              "Logs de sécurité",
              "90 jours"
            ],
            [
              "Sauvegardes locales et distantes",
              "3 mois"
            ],
            [
              "Demandes RGPD",
              "3 ans après clôture du dossier"
            ]
          ]
        },
        {
          "kind": "paragraph",
          "text": "La suppression d'un document ou d'un compte dans l'application ne garantit pas son effacement instantané dans toutes les copies de sauvegarde."
        },
        {
          "kind": "paragraph",
          "text": "Les suppressions demandées doivent être suivies dans les systèmes actifs et traitées selon une procédure documentée, y compris après restauration d'une sauvegarde."
        }
      ]
    },
    {
      "title": "9. Cookies et sessions",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "DocuMind AI utilise des mécanismes de session nécessaires à l'authentification et à la sécurisation des accès."
        },
        {
          "kind": "paragraph",
          "text": "Le recensement des cookies et autres traceurs effectivement utilisés devra être confirmé avant publication."
        },
        {
          "kind": "paragraph",
          "text": "Tout traceur non strictement nécessaire sera soumis aux règles d'information et, le cas échéant, de consentement applicables."
        }
      ]
    },
    {
      "title": "10. Droits des personnes",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Dans les conditions prévues par la réglementation, vous pouvez demander l'accès, la rectification, l'effacement ou la limitation du traitement de vos données personnelles, et exercer vos autres droits applicables, notamment d'opposition ou de portabilité selon les situations."
        },
        {
          "kind": "paragraph",
          "text": "Pour exercer ces droits :"
        },
        {
          "kind": "paragraph",
          "text": "adresse email : adelinemeistertzheim40@gmail.com"
        },
        {
          "kind": "paragraph",
          "text": "Une demande peut nécessiter une vérification proportionnée de l'identité afin de protéger les comptes contre les accès non autorisés."
        },
        {
          "kind": "paragraph",
          "text": "Vous pouvez également déposer une réclamation auprès de la Commission nationale de l'informatique et des libertés (CNIL) : https://www.cnil.fr."
        }
      ]
    },
    {
      "title": "11. Modifications",
      "text": "",
      "blocks": [
        {
          "kind": "paragraph",
          "text": "Cette politique peut être mise à jour pour refléter les évolutions du service et de ses traitements."
        },
        {
          "kind": "paragraph",
          "text": "Les modifications substantielles feront l'objet d'une information adaptée avant leur application lorsque cela est nécessaire."
        },
        {
          "kind": "paragraph",
          "text": "Date d'entrée en vigueur : 26 octobre 2026"
        },
      ]
    }
  ]
}
