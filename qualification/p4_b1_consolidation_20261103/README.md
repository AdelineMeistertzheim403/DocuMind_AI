# Consolidation B1 - complement independant du 20261103

**BLOCKED, review-only. Aucun GO Docker ni production.**

Identite des9771 contenus etayee par les resultats operateur ; cloture
formelle en attente de revue des pieces/captures/code et decision C5.
Pas d'egalite metadata :10334 UID/GID differents, racine `.` non comparee.
Pas d'approbation base P4 ou de provenance.

Lire P4_B1_QUALIFICATION_REPORT.md, P4_B1_DECISION.json et
P4_B1_OBSERVED_REFERENCES.json, puis DEBIAN_B1_VERIFICATION_PROTOCOL.md.
P4_B2_B7_NEXT_STEPS.md isole les vrais travaux restants sans repeter
les campagnes validees. TRANSFER.md contient le mode de verification.

evidence_check.py controle seulement les hashes de copies de preuves ;
il ne suppose pas le schema du rapport brut et ne prononce pas la cloture.
transfer.py extrait ce paquet de revue, jamais une image/rootfs.
Aucun ancien outil ou rapport n'est modifie.

Tests des nouveaux outils, sans Docker ni preuve reelle :

```text
.\.venv\Scripts\python.exe -I -B -m unittest discover -s qualification\p4_b1_consolidation_20261103\tests -v
```
