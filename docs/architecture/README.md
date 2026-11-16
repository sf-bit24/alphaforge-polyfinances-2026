# Architecture AWS

L'architecture d'AlphaForge AI sur AWS (sandbox us-east-1), établie d'après le code de `master` du 15 novembre 2026. Simulation seulement : aucune transaction réelle.

| Document | Contenu |
| --- | --- |
| [Document d'architecture AWS (PDF)](alphaforge-architecture-aws.pdf) | Le document remis au jury : les agents et leurs runtimes, la structure OKF des bases, le débat et le Judge, la plateforme, le rôle et la justification de chaque service, les trois cas d'utilisation étape par étape, les agents et le stockage, la sécurité, la traçabilité et le déploiement. |
| [`diagrams/`](diagrams/README.md) | Les quatre diagrammes, avec leur source draw.io : la plateforme, puis un diagramme par cas d'utilisation. |
| [Agents déployés et stockage](agents-et-stockage.md) | Les 8 runtimes AgentCore, les buckets S3 et S3 Vectors, DynamoDB et ECR. |
| [Le débat, le Judge et la traçabilité](debat-et-judge.md) | Comment les quatre lentilles et le Judge construisent et contrôlent un portefeuille, comment chaque chiffre se trace, et ce qui est lu dans les bases OKF. |
| [OKF](okf.md) | Ce qu'est l'Open Knowledge Format et pourquoi nos bases dans S3 l'utilisent : champs d'un document, arborescence du bucket. |

Les cas d'utilisation, du point de vue de l'investisseur, sont dans [`docs/use-cases/`](../use-cases/README.md).

![Plateforme AlphaForge AI sur AWS](diagrams/alphaforge-plateforme-aws.png)
