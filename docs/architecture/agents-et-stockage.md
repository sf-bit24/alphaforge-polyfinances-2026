# Agents déployés et stockage

Relevé sur le compte AWS du Datathon (us-east-1) le 15 novembre 2026, release `1f026dbf`. Simulation seulement.

## Les agents, en clair

La documentation nomme chaque agent par son nom. L'application, elle, l'affiche par son code dans la trace de chaque requête (colonne « Code dans la trace »). « Modèle » veut dire Claude Opus 5.5 sur Bedrock ; « code » veut dire du Python déterministe, sans modèle.

| Agent | Code dans la trace | Ce qu'il fait | Moteur | Runtime |
| --- | --- | --- | --- | --- |
| Les questions de base | `questionnaire` | Pose les questions fixes du profil et valide chaque réponse. | code | `profile` |
| L'agent du profil | A1 | Ne demande que ce qui manque pour compléter le profil, au plus trois questions par tour, puis l'écrit. | modèle | `profile` |
| L'agent du portefeuille existant | A2 | Lit un relevé (PDF, tableur, image, texte) et en extrait les positions ; le code les valorise. | modèle | `profile` |
| Le calcul du portefeuille (étape 0 et optimiseur) | `s0.*`, `s0b.*`, `s2.optimize` | Traduit le profil en limites, choisit le style et les titres, puis calcule les poids (cvxpy). | code | `portfolio` |
| L'avocat | `a3.advocate` | Défend le portefeuille construit, puis répond aux critiques au second tour. | modèle | `portfolio` |
| Les quatre lentilles critiques | `lens.*` | Horizon, risque, diversification, contraintes : contestent le portefeuille, et ne peuvent que resserrer une limite. | modèle | `portfolio` |
| Le Judge | `judge` | Contrôle chaque limite du profil, sans dérogation ; refuse une demande qui dépasse une limite bloquante et propose une version encadrée. | code | `portfolio` |
| L'agent de la presse | A4 | Collecte les communiqués et les actualités, datés et sourcés. | modèle | `press` |
| L'agent des données | A5 | Collecte les séries économiques et les cours ; les fondamentaux SEC EDGAR viennent du code. | modèle | `data` |
| Le superviseur | A6 | Relit tout ce qui est collecté, rejette ce qui n'a ni source ni date ou fait double emploi, et écrit la base générale. | modèle | `supervisor` |
| Le routeur | A0 | Choisit les sujets d'une question de recherche, puis rédige la synthèse. | modèle | `router` |
| Les experts de sujet | E1 à E7 | Un expert par sujet : consulte la base générale et lance ses chercheurs. | modèle | `expert` |
| Les chercheurs | `researcher` | Une mission chacun : lisent les sites publics de leur liste, en respectant `robots.txt`. | modèle | `researcher` |

## Les 8 runtimes AgentCore

| Runtime | Agents | Ce qu'il fait | Appelé par |
| --- | --- | --- | --- |
| `alphaforge_sandbox_profile` | questions de base (code), agent du profil, agent du portefeuille existant | Construit le profil de l'investisseur : questions de base sans modèle, relances de l'agent du profil sur ce qui manque, lecture d'un portefeuille existant. Crée la Knowledge Base du client. | l'interface web (`/api/agent`) |
| `alphaforge_sandbox_portfolio` | étape 0, optimiseur, avocat, quatre lentilles, Judge | Construit le portefeuille simulé : le code calcule les poids, l'avocat et les lentilles en débattent, le Judge contrôle chaque limite du profil. | l'interface web (`/api/portfolio`), la machine d'évolution |
| `alphaforge_sandbox_press` | agent de la presse | Collecte les actualités datées (Newswire.ca, PR Newswire, GDELT) dans `staging/`. | la machine de collecte |
| `alphaforge_sandbox_data` | agent des données | Collecte les séries et les cours datés (Banque du Canada, FRED, Yahoo Finance) dans `staging/`. | la machine de collecte |
| `alphaforge_sandbox_supervisor` | superviseur | Relit ce qui arrive dans `staging/`, rejette tout document sans source ou sans date, et écrit la base générale (`general/`). | les machines de collecte et de recherche |
| `alphaforge_sandbox_router` | routeur | Choisit les sujets d'une question de recherche, puis rédige la synthèse finale. | la machine de recherche |
| `alphaforge_sandbox_expert` | experts de sujet | Expert d'un sujet : lance ses chercheurs et met leurs constats en attente. | la machine de recherche |
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
