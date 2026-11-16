# Le débat, le Judge et la traçabilité du portefeuille

Comment le runtime `portfolio` construit, conteste, contrôle et prouve un portefeuille simulé. Le modèle peut contester et expliquer ; seul le code fixe un poids, et seul le Judge décide. Simulation seulement. Le détail est dans [UC02](../use-cases/uc02.md) et dans le [diagramme du portefeuille](diagrams/alphaforge-flux-portefeuille.png).

```text
Profil OKF ─▶ Mandat ─▶ Optimiseur ─▶ Débat (2 tours) ─▶ Fusion ─▶ Judge ─▶ Explication ancrée ─▶ Décision
  code         code       code          modèle            code      code      modèle + contrôle     OKF, audit, X-Ray
```

## Le débat des quatre lentilles

- Quatre lentilles jugent le portefeuille calculé : horizon, risque (tolérance et capacité), diversité et préférences (ESG compris), contraintes. Chacune a ses outils de preuves : épisodes de stress, distribution par horizon, expositions, preuves ESG, fondamentaux, dépôts.
- Au tour 1, elles ne voient pas le plaidoyer de l'avocat, contre l'effet d'ancrage. Au tour 2, elles le voient et l'avocat répond ; une objection n'est jamais levée par l'argumentation. Le code tranche, réoptimise seulement si le mandat a changé, et jamais une troisième fois.
- Une lentille propose au plus trois amendements, pris dans une liste fermée : resserrer une limite, plafonner un groupe, exclure un titre, exiger un minimum, changer de mesure du risque, signaler. Un amendement doit citer un fait existant. La fusion rejette tout relâchement, tout fait inconnu, toute borne sous 0,6 fois l'originale et tout mandat infaisable.

## Le Judge : rôle et impact

- Du code déterministe, sans paramètre de dérogation : insister ne change rien (test : trois exécutions identiques). Il contrôle chaque limite du mandat sur les poids finaux.
- Chaque contrôle dit la règle, son origine dans le profil, la limite, la valeur, si elle est saturée ou violée, bloquante ou indicative, et son coût (prix dual). Le verdict est l'un de : proposition, refus encadré, position d'attente, incomplet, protection.
- Avec une demande précise, il compare le portefeuille avec et sans elle. Robert (fictif) veut 50 000 $ dans TSLA : quatre violations bloquantes, donc un refus encadré ; l'alternative passe ses 28 contrôles, dont 6 saturés. Pour Amira (fictive) en mode LLM, les lentilles n'ont fait que signaler : les poids sont ceux du mode règles.

## Traçabilité et évaluations

- Chaque nombre est un fait sourcé (`fact_id`, source, date, étape de trace) ; les 28 contrôles du Judge sont 28 faits. Chaque étape est un événement de trace, par exemple `dec-demo-robert-v1-1145a799:t022:judge:check:demande`.
- L'explication répond aux quatre questions : quelles données, pourquoi ce choix, quelles limites, ce qui changerait la réponse. Les contrefactuels sont recalculés par l'optimiseur. Une phrase dont un nombre n'est pas un fait cité est rejetée, puis `ApplyGuardrail` note l'ancrage de chaque énoncé (seuil 0,75).
- La décision est chaînée par hachage dans DynamoDB, copiée sous Object Lock et tient dans une seule trace X-Ray (`portfolio.build`). Le rejeu des appels du modèle, par clé sha256, fait voir toute dérive.

## Le lien avec les bases OKF

| Document | Ce que le portefeuille en fait |
| --- | --- |
| `clients/<id>/profil.md` | Le mandat : limites, préférences, exclusions. Chaque limite garde la règle du profil d'où elle vient. |
| `clients/<id>/portefeuille-existant.md` | Les positions détenues, seulement si la vue est confirmée par l'investisseur. |
| `general/faits/` (ESG) | Des preuves datées qui peuvent appuyer une exclusion. |
| `general/societes/` | Les fondamentaux publiés (EDGAR), lus par l'outil `fundamentals_evidence`. |
| `general/depots/`, `general/actualites/` | Signalés aux lentilles, jamais transformés en limite. |
| `general/methodologie/` | La référence de l'ancrage de l'explication, avec les faits cités. |
| **`clients/<id>/decisions/<id>.md`** | **Écrit** : le résumé OKF de la décision (le `.json` complet est à côté), ingéré dans la Knowledge Base du client. |

Voir aussi : [OKF](okf.md), [les agents et leurs runtimes](agents-et-stockage.md).

[Retour à l'architecture](README.md)
