# Les trois cas d'utilisation

AlphaForge AI sert à trois choses : créer son profil d'investisseur, construire un portefeuille simulé, et tenir la base de connaissances à jour par la veille web. Chaque cas a son diagramme AWS. Les exemples viennent de l'application déployée, relevés le 15 novembre 2026. Simulation seulement : aucune transaction réelle, aucun conseil.

## 1. Créer son profil d'investisseur

| | |
| --- | --- |
| Qui | L'investisseur, connecté par Amazon Cognito |
| But | Un profil complet en cinq dimensions (objectif, horizon, risque, contraintes, préférences), avec le niveau de connaissances |
| Où | Page Profil, route `POST /api/agent` |
| Agents | Runtime `profile` : questionnaire (code, sans modèle), A1 `createProfile-Agent`, A2 `AnalyseExistingPortfolio-Agent` |
| Résultat | `profil.md` et ses notes dans `clients/<client_id>/`, et la Knowledge Base du client |

Déroulement :

1. L'investisseur crée un compte (code de vérification par courriel) ou se connecte. Un compte = un `client_id` = une base `clients/<client_id>/`.
2. `session.start` crée sa base dans S3 et sa propre Knowledge Base, puis le code choisit la première question.
3. Le questionnaire de base, sans modèle : niveau de connaissances et mini-quiz, objectif, horizon, tolérance et capacité de risque, contraintes, préférences, mise en situation. Le code valide et écrit chaque réponse.
4. Facultatif : il dépose son portefeuille actuel (texte, CSV, tableur, PDF, image ou JSON ; 5 fichiers de 10 Mo au plus). A2 en extrait les positions, le code les valorise. Il confirme, ou il passe l'étape.
5. A1 pose au plus trois questions par tour, seulement sur ce qui manque. Il cherche dans la Knowledge Base générale et dans celle du client. Le code calcule la complétude.
6. Dès 70 % de complétude, l'investisseur peut s'arrêter. A1 écrit alors le profil et ses notes.

Ce qui peut arriver :

- Un message hors cadre : le Guardrail Bedrock le bloque (`guardrail_blocked`) et invite à reformuler.
- A1 indisponible : le code pose ses questions de repli.
- Le quota de 100 Knowledge Bases par compte est atteint : le questionnaire continue sans recherche dans la base du client.
- Une requête pour un autre `client_id` que celui de la session : refusée (403).

Exemple réel (profil fictif `5edbd889…`) : `session.start` crée la base et choisit la première question en 0,2 s. Quand l'investisseur répond aux trois questions d'A1, le tour d'A1 (Claude Opus 5.5) dure 12,8 s et la complétude atteint 80 % pour un seuil de 70 %. Un message volontairement hors cadre est bloqué par le Guardrail en 0,35 s.

Diagramme : [création du profil](img/alphaforge-flux-profil.png).

## 2. Construire un portefeuille simulé

| | |
| --- | --- |
| Qui | L'investisseur, une fois son profil complet |
| But | Un portefeuille simulé qui respecte les limites de son profil, avec son explication ; ou la réponse à une demande précise, par exemple « 50 000 $ dans TSLA » |
| Où | Page Portefeuille simulé, route `POST /api/portfolio`, mode règles ou mode Lentilles LLM |
| Agents | Runtime `portfolio` : étape 0, optimiseur, A3 l'avocat, quatre lentilles, Judge |
| Résultat | Une décision approuvée, ou refusée avec une alternative encadrée, écrite dans `clients/<client_id>/decisions/` |

Déroulement :

1. L'investisseur lance la construction, avec ou sans demande précise.
2. Le code lit `profil.md` et le traduit en mandat : chaque limite garde le nom de la règle du profil d'où elle vient.
3. L'étape 0 choisit le style (défensif, dynamique ou offensif) et les titres admissibles, avec les exclusions ESG de la base générale.
4. L'optimiseur cvxpy calcule les poids sous ces limites. Aucun poids ne vient d'un modèle.
5. Tour 1 : A3 plaide pour le portefeuille ; quatre lentilles (horizon, risque, diversification, contraintes) le jugent en parallèle, sans voir le plaidoyer. Leurs amendements ne peuvent que resserrer une limite. Tour 2 : les lentilles voient le plaidoyer et A3 répond ; le code tranche. En mode règles, des règles fixes remplacent le modèle.
6. Le Judge contrôle chaque limite, sans dérogation possible. Avec une demande précise, il compare le portefeuille avec et sans la demande.
7. Le code écrit l'explication à partir de faits sourcés, le modèle la reformule, et chaque phrase est vérifiée. Le Guardrail contrôle ensuite l'ancrage dans les faits (seuil 0,75).
8. La décision est écrite dans S3, chaînée par hachage dans DynamoDB et copiée sous Object Lock. Elle tient dans une seule trace X-Ray.

Ce qui peut arriver :

- La demande dépasse une limite bloquante : refus encadré. La réponse montre chaque limite dépassée et propose la version la plus proche qui les respecte.
- Même sans actions, la perte possible dépasse ce que l'investisseur accepte de perdre : statut protection, le portefeuille le plus prudent du mandat.
- Un nombre de la reformulation n'est pas un fait cité : le texte du code reste à la place.
- En mode LLM, un build dure environ 2 minutes. Le serveur envoie un espace toutes les 15 s, pour que CloudFront ne coupe pas une réponse muette après 60 s.

Exemples réels :

- Robert (fictif, 59 ans) demande 50 000 $ dans TSLA, en mode règles. Réponse en 18,1 s : refus encadré, quatre violations bloquantes (actifs de croissance 10,28 % pour 10 %, TSLA 5,56 % pour 0 %, titres individuels 5,56 % pour 0 %, CDaR 3,26 % pour 1,5 %). Alternative : ZST.TO 81,5 %, AGG 9,5 %, GLD 4 %, XIU.TO 3,8 %, SPY 1,2 %, qui passe ses 28 contrôles.
- Amira (fictive), en mode Lentilles LLM : 111,9 s. Les lentilles signalent des points sans changer les poids, et les positions finales sont les mêmes qu'en mode règles : le modèle commente, le code fixe les poids. Ancrage : 22 énoncés vérifiés, score minimal 0,76.

Diagramme : [création du portefeuille](img/alphaforge-flux-portefeuille.png).

## 3. Mettre à jour la base de connaissances par la veille web

| | |
| --- | --- |
| Qui | EventBridge Scheduler toutes les 6 h, ou un membre du groupe `admin` par le bouton de l'interface |
| But | Une base générale à jour, faite de documents datés et sourcés, indexée dans la Knowledge Base |
| Où | Machine Step Functions `alphaforge-sandbox-collecte` ; route `POST /api/collect` pour le bouton |
| Agents | A4 presse, A5 données, A6 superviseur ; pour une question de recherche : A0, les experts E1 à E7 et leurs chercheurs |
| Résultat | De nouveaux documents sous `general/`, indexés dans la Knowledge Base générale |

Déroulement de la collecte :

1. Le Scheduler, ou un admin, lance la machine de collecte.
2. A4 et A5 travaillent en parallèle. A4 lit les communiqués (PR Newswire, Newswire.ca) et les actualités GDELT. A5 lit les fondamentaux SEC EDGAR, la Banque du Canada, FRED et Yahoo Finance. Chacun écrit des éléments datés dans `staging/<run_id>/`.
3. A6 relit tout. Il rejette, en disant pourquoi, un élément sans source, sans date, publié après sa récupération ou en double. Il écrit le reste dans `general/`.
4. La machine lance l'ingestion de la Knowledge Base, qui n'indexe que `general/`.
5. A1 et les experts retrouvent ensuite les nouveaux documents par la recherche de la Knowledge Base.

La recherche par experts, pour une question précise : A0 choisit d'un à quatre sujets. Chaque expert lance ses chercheurs (24 au plus par exécution), qui ne lisent que les sites de leur liste, respectent `robots.txt` et s'arrêtent sur un refus d'accès. A0 rédige la synthèse ; A6 vérifie chaque valeur contre la page archivée, puis la même ingestion suit.

Ce qui peut arriver :

- Un échec d'A4 ou d'A5 n'arrête pas la collecte ; un échec d'A6 l'arrête.
- Une source limite le débit (GDELT répond 429) : la collecte continue et signale l'avertissement.

Exemple réel (exécution `376cb392…`, 1 min 44 s) : A4 rapporte 12 éléments et A5 en rapporte 59. A6 écrit 5 documents et en rejette 48, par exemple « doublon d'un document existant (même adresse) ». L'ingestion analyse 201 documents, en indexe 5 nouveaux et 2 modifiés, sans aucun échec.

Diagramme : [veille web et base générale](img/alphaforge-flux-veille-web.png).
