# Cas d'utilisation 2 : construire un portefeuille simulé

Simulation seulement : aucune transaction réelle, aucun conseil. Les exemples viennent de l'application déployée, relevés le 15 novembre 2026.

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

Diagramme : [création du portefeuille](../architecture/assets/alphaforge-flux-portefeuille.png).

[Retour aux cas d'utilisation](README.md)
