# Cas d'utilisation

AlphaForge AI sert à trois choses. Chaque cas a sa page : qui, but, agents, déroulement, ce qui peut arriver, un exemple réel et le lien vers son diagramme AWS.

| Cas | Qui | Résultat |
| --- | --- | --- |
| [1. Créer son profil d'investisseur](profil.md) | L'investisseur, connecté par Cognito | Son profil complet dans `clients/<client_id>/`, et sa propre Knowledge Base |
| [2. Construire un portefeuille simulé](portefeuille.md) | L'investisseur au profil complet | Une décision approuvée, ou refusée avec une alternative encadrée, expliquée chiffre par chiffre |
| [3. Mettre à jour la base de connaissances par la veille web](veille-web.md) | EventBridge Scheduler toutes les 6 h, ou un compte admin | De nouveaux documents datés et sourcés sous `general/`, indexés dans la Knowledge Base générale |

L'architecture AWS, les diagrammes et la liste des agents et des buckets sont dans [`docs/architecture/`](../architecture/README.md).

Simulation seulement : aucune transaction réelle, aucun conseil.
