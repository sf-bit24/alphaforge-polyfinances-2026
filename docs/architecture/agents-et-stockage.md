# Agents déployés et stockage

Relevé sur le compte AWS du Datathon (us-east-1) le 15 novembre 2026, release `1f026dbf`. Simulation seulement.

## Les agents, en clair

Les diagrammes et les étapes nomment les agents par leur code. « Modèle » veut dire Claude Opus 5.5 sur Bedrock ; « code » veut dire du Python déterministe, sans modèle.

| Code | Qui c'est | Ce qu'il fait | Moteur | Runtime |
| --- | --- | --- | --- | --- |
| Questionnaire | Les questions de base | Pose les questions fixes du profil et valide chaque réponse. | code | `profile` |
| A1 | L'agent du profil | Ne demande que ce qui manque pour compléter le profil, au plus trois questions par tour, puis l'écrit. | modèle | `profile` |
| A2 | L'agent du portefeuille existant | Lit un relevé (PDF, tableur, image, texte) et en extrait les positions ; le code les valorise. | modèle | `profile` |
| Étape 0 et optimiseur | Le calcul du portefeuille | Traduit le profil en limites, choisit le style et les titres, puis calcule les poids (cvxpy). | code | `portfolio` |
| A3 | L'avocat | Défend le portefeuille construit, puis répond aux critiques au second tour. | modèle | `portfolio` |
| Lentilles | Les quatre critiques | Horizon, risque, diversification, contraintes : contestent le portefeuille, et ne peuvent que resserrer une limite. | modèle | `portfolio` |
| Judge | Le juge | Contrôle chaque limite du profil, sans dérogation ; refuse une demande qui dépasse une limite bloquante et propose une version encadrée. | code | `portfolio` |
| A4 | L'agent de la presse | Collecte les communiqués et les actualités, datés et sourcés. | modèle | `press` |
| A5 | L'agent des données | Collecte les séries économiques et les cours ; les fondamentaux SEC EDGAR viennent du code. | modèle | `data` |
| A6 | Le superviseur | Relit tout ce qui est collecté, rejette ce qui n'a ni source ni date ou fait double emploi, et écrit la base générale. | modèle | `supervisor` |
| A0 | Le routeur | Choisit les sujets d'une question de recherche, puis rédige la synthèse. | modèle | `router` |
| E1 à E7 | Les experts de sujet | Un expert par sujet : consulte la base générale et lance ses chercheurs. | modèle | `expert` |
| Chercheurs | Les chercheurs | Une mission chacun : lisent les sites publics de leur liste, en respectant `robots.txt`. | modèle | `researcher` |

## Les 8 runtimes AgentCore

| Runtime | Agents | Ce qu'il fait | Appelé par |
| --- | --- | --- | --- |
| `alphaforge_sandbox_profile` | questionnaire (code), A1 `createProfile-Agent`, A2 `AnalyseExistingPortfolio-Agent` | Construit le profil de l'investisseur : questions de base sans modèle, relances d'A1 sur ce qui manque, lecture d'un portefeuille existant par A2. Crée la Knowledge Base du client. | l'interface web (`/api/agent`) |
| `alphaforge_sandbox_portfolio` | étape 0, A3, quatre lentilles, Judge | Construit le portefeuille simulé : le code calcule les poids, A3 et les lentilles en débattent, le Judge contrôle chaque limite du profil. | l'interface web (`/api/portfolio`), la machine d'évolution |
| `alphaforge_sandbox_press` | A4 | Collecte les actualités datées (Newswire.ca, PR Newswire, GDELT) dans `staging/`. | la machine de collecte |
| `alphaforge_sandbox_data` | A5 | Collecte les séries et les cours datés (Banque du Canada, FRED, Yahoo Finance) dans `staging/`. | la machine de collecte |
| `alphaforge_sandbox_supervisor` | A6 | Relit ce qui arrive dans `staging/`, rejette tout document sans source ou sans date, et écrit la base générale (`general/`). | les machines de collecte et de recherche |
| `alphaforge_sandbox_router` | A0 | Choisit les sujets d'une question de recherche, puis rédige la synthèse finale. | la machine de recherche |
| `alphaforge_sandbox_expert` | E1 à E7 | Expert d'un sujet : lance ses chercheurs et met leurs constats en attente. | la machine de recherche |
| `alphaforge_sandbox_researcher` | chercheur | Une mission par session : cherche dans les sites de son paquet et consigne ses constats. | le runtime `expert` |

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
