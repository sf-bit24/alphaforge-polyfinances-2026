# Agents déployés et stockage

Relevé sur le compte AWS du Datathon (us-east-1) le 15 novembre 2026, release `1f026dbf`. Simulation seulement.

## Les agents et leurs runtimes AgentCore

13 rôles, dont 10 qui appellent le modèle et 3 en code, déployés dans 8 runtimes AgentCore. Un runtime peut porter plusieurs rôles. « Modèle » veut dire Claude Opus 5.5 sur Bedrock ; « code » veut dire du Python déterministe, sans modèle.

| Runtime | Agent | Ce qu'il fait | Moteur | Appelé par |
| --- | --- | --- | --- | --- |
| `alphaforge_sandbox_profile` | Les questions de base | Pose les questions fixes du profil et valide chaque réponse. | code | l'interface web (`/api/agent`) |
| | L'agent du profil | Ne demande que ce qui manque pour compléter le profil, au plus trois questions par tour, puis l'écrit. Crée la Knowledge Base du client. | modèle | |
| | L'agent du portefeuille existant | Lit un relevé (PDF, tableur, image, texte) et en extrait les positions ; le code les valorise. | modèle | |
| `alphaforge_sandbox_portfolio` | Le calcul du portefeuille (étape 0 et optimiseur) | Traduit le profil en limites, choisit le style et les titres, puis calcule les poids (cvxpy). | code | l'interface web (`/api/portfolio`), la machine d'évolution |
| | L'avocat | Défend le portefeuille construit, puis répond aux critiques au second tour. | modèle | |
| | Les quatre lentilles critiques | Horizon, risque, diversification, contraintes : contestent le portefeuille, et ne peuvent que resserrer une limite. | modèle | |
| | Le Judge | Contrôle chaque limite du profil, sans dérogation ; refuse une demande qui dépasse une limite bloquante et propose une version encadrée. | code | |
| `alphaforge_sandbox_press` | L'agent de la presse | Collecte les actualités datées (Newswire.ca, PR Newswire, GDELT) dans `staging/`. | modèle | la machine de collecte |
| `alphaforge_sandbox_data` | L'agent des données | Collecte les séries et les cours datés (Banque du Canada, FRED, Yahoo Finance) dans `staging/` ; les fondamentaux SEC EDGAR viennent du code. | modèle | la machine de collecte |
| `alphaforge_sandbox_supervisor` | Le superviseur | Relit ce qui arrive dans `staging/`, rejette tout document sans source ou sans date, et écrit la base générale (`general/`). | modèle | les machines de collecte et de recherche |
| `alphaforge_sandbox_router` | Le routeur | Choisit les sujets d'une question de recherche, puis rédige la synthèse finale. | modèle | la machine de recherche |
| `alphaforge_sandbox_expert` | Les experts de sujet | Un expert par sujet : consulte la base générale, lance ses chercheurs et met leurs constats en attente. | modèle | la machine de recherche |
| `alphaforge_sandbox_researcher` | Les chercheurs | Une mission par session : cherchent dans les sites publics de leur liste, en respectant `robots.txt`, et consignent leurs constats. | modèle | le runtime `expert` |

Points communs :

- Un seul code, choisi par la variable `AGENT_ROLE`. Le zip `runtime/agents-<commit>.zip` sert à sept runtimes ; `portfolio` a son propre zip (`agents-portfolio-<commit>.zip`), qui ajoute les bibliothèques de calcul (cvxpy, numpy, pandas). Python 3.13.
- Chaque runtime a son rôle IAM : `alphaforge-sandbox-agentcore-<rôle>` (par exemple `alphaforge-sandbox-agentcore-profile`).
- Tous les agents utilisent Claude Opus 5.5 sur Bedrock (`us.anthropic.claude-opus-5-5`). Le Guardrail Bedrock (`rcsdbnz8u48w`, version 3) s'applique à `profile` et à `portfolio`. En mode règles, `portfolio` n'appelle aucun modèle.
- Les machines Step Functions : `collecte` (lancée par EventBridge Scheduler toutes les 6 h, ou par un compte admin), `recherche`, `evolution` et `scenarios`.

## Buckets S3

| Bucket | Contenu | Protection |
| --- | --- | --- |
| `alphaforge-sandbox-kb-024848478575` | Les bases OKF. `general/` : la base générale, seule source de la Knowledge Base générale. `clients/` : une base par investisseur, avec ses décisions. `staging/` : collecte brute, effacée après 14 jours. `runtime/` : le zip du code des runtimes, un par commit. `scenarios/` : entrées et sorties du job des scénarios. | Versionné, chiffré par la clé KMS du projet. |
| `alphaforge-sandbox-traces-024848478575` | Le journal complet des appels Bedrock (`bedrock-invocations/`) et une copie de chaque maillon de la chaîne d'audit (`decisions/<profil>/`). | Versionné, Object Lock (mode GOVERNANCE, 3 jours) : une preuve ne se réécrit pas. |

## Buckets S3 Vectors (index des Knowledge Bases)

| Bucket de vecteurs | Contenu |
| --- | --- |
| `alphaforge-sandbox-vectors` | L'index `general` de la Knowledge Base générale (`alphaforge-sandbox-general`, `1JN7STFRBD`). Embeddings Titan Text V2, 1024 dimensions. |
| `alphaforge-sandbox-client-vectors` | Un index `client-<id>` par investisseur, pour sa propre Knowledge Base (`alphaforge-sandbox-client-<id>`). Chiffré par une clé KMS dédiée. Un compte AWS accepte au plus 100 Knowledge Bases. |

## Autres stockages

| Ressource | Contenu |
| --- | --- |
| DynamoDB `alphaforge-sandbox-decisions` | La chaîne d'audit : chaque décision est liée à la précédente par un hachage (58 éléments au relevé). |
| DynamoDB `alphaforge-sandbox-llm-replay` | L'index du rejeu des appels LLM (clé sha256), vide : les runtimes déployés gardent leurs enregistrements dans leur session. |
| DynamoDB `alphaforge-decisions`, `alphaforge-llm-replay` | Anciennes tables créées par un script boto3 avant Terraform, plus utilisées (4 éléments et 0). |
| ECR `alphaforge-web` | L'image de l'interface Next.js, déployée sur ECS Fargate. |

Voir aussi : le [diagramme de la plateforme](diagrams/alphaforge-plateforme-aws.png), [`app/agents/README.md`](../../app/agents/README.md) et [`infrastructure/README.md`](../../infrastructure/README.md).
