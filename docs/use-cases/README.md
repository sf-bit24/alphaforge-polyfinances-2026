# Cas d'utilisation

AlphaForge AI sert à trois choses. Chaque cas a sa page : qui, but, agents, déroulement, ce qui peut arriver, un exemple réel et le lien vers son diagramme AWS.

| Cas d'utilisation | Qui | Résultat |
| --- | --- | --- |
| [UC01 : Créer son profil d'investisseur](uc01.md) | L'investisseur, connecté par Cognito | Son profil complet dans `clients/<client_id>/`, et sa propre Knowledge Base |
| [UC02 : Construire un portefeuille simulé](uc02.md) | L'investisseur au profil complet | Une décision approuvée, ou refusée avec une alternative encadrée, expliquée chiffre par chiffre |
| [UC03 : Mettre à jour la base de connaissances par la veille web](uc03.md) | EventBridge Scheduler toutes les 6 h, ou un compte admin | De nouveaux documents datés et sourcés sous `general/`, indexés dans la Knowledge Base générale |

L'architecture AWS, les diagrammes et la liste des agents et des buckets sont dans [`docs/architecture/`](../architecture/README.md).

Simulation seulement : aucune transaction réelle, aucun conseil.
