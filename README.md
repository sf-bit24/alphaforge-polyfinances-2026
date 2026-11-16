# AlphaForge AI

Aide à la décision d'investissement agentique et explicable, construite par l'équipe larpathon pour le Datathon PolyFinances 2026 (Banque Nationale et AWS). L'investisseur construit son profil avec un agent qui ne demande que ce qui manque. Le code bâtit ensuite un portefeuille simulé sous les limites de ce profil. Des agents critiques en débattent, un Judge déterministe contrôle chaque plafond, et chaque chiffre de l'explication cite sa source.

> **Simulation seulement** : aucune transaction réelle, aucun conseil financier personnalisé.

[Application déployée](https://d2gsaqmfxygugx.cloudfront.net) (jusqu'au 16 novembre 2026, 13 h 59) · [Remise](docs/remise/README.md) : [one-pager](docs/remise/alphaforge-one-pager.pdf), [architecture AWS](docs/remise/alphaforge-architecture-aws.pdf), [documentation technique](docs/remise/alphaforge-documentation-technique.pdf) · [Cas d'utilisation](docs/use-cases/README.md)

## Démo vidéo

https://github.com/user-attachments/assets/b2629c28-754f-4717-b255-53ac79fe743f

*2 min 19 s, en français, sous-titres incrustés.* Robert, 59 ans (FICTION), demande 50 000 $ dans l'action TSLA : son profil, l'optimisation sous ses limites, quatre lentilles critiques, le Judge, puis le refus encadré et expliqué.

## Architecture

![Plateforme AlphaForge AI sur AWS](docs/architecture/diagrams/alphaforge-plateforme-aws.png)

Les trois flux de bout en bout (profil, portefeuille, veille web) sont dans [`docs/architecture/diagrams/`](docs/architecture/diagrams/README.md). L'infrastructure est décrite dans [`infrastructure/README.md`](infrastructure/README.md).

## Démarrer en local

Prérequis : [uv](https://docs.astral.sh/uv/) et Node.js 20.9 ou plus (24 recommandé). Les modes `local` et `aws` demandent aussi des identifiants AWS (`us-east-1`).

```sh
./scripts/init.sh   # dépendances (uv, npm) et .env créé depuis .env.example
./scripts/run.sh    # http://localhost:3000
```

| Script | Rôle |
| --- | --- |
| `./scripts/run.sh mock` | Interface seule, simulateur du contrat, sans AWS (défaut) |
| `./scripts/run.sh local` | Runtimes `profile` et `portfolio` sur le poste (modèles Bedrock réels), puis l'interface |
| `./scripts/run.sh aws` | Interface branchée sur les runtimes déployés |
| `./scripts/init.sh --data` | Reconstruit aussi les données longues du moteur, requises pour `/portfolio` en mode `local` |
| `./scripts/test.sh [agents\|web]` | Les contrôles de la CI : ruff, pytest, lint, typecheck, tests et build |
| `./scripts/export-okf.sh` | Copie les bases OKF du bucket vers `./export/` avant la fermeture du compte AWS |

Les scripts appellent `uv` et `npm`. Les commandes directes et les variables sont dans [`app/agents/README.md`](app/agents/README.md) et [`app/web/README.md`](app/web/README.md).

## Dépôt

```text
app/agents/       runtimes Python (Strands Agents, Bedrock AgentCore)
app/web/          interface Next.js
app/knowledge/    base générale de départ (OKF)
app/CONTRACTS.md  contrat entre l'interface, les runtimes et l'infrastructure
infrastructure/   Terraform (HCP Terraform -> AWS) ; un push sur master déploie
scripts/          scripts du poste de développement
```

<sub>Crédits de la démo vidéo : voix de synthèse Microsoft (fr-CA-SylvieNeural, via edge-tts) ; batterie « MuldjordKit » de Lars Muldjord (drumgizmo.org), version FreePats, sous licence [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ; échantillons CC0 : Karoryfer Samples, Versilian Community Sample Library (Versilian Studios) ; polices Inter et JetBrains Mono (SIL OFL 1.1) ; icônes Lucide (ISC) ; mascotte « Braise » originale.</sub>
