# AlphaForge AI : interface locale

Interface web d'AlphaForge AI (Datathon PolyFinances 2026), à lancer sur le poste. Elle construit le profil d'investisseur (questions de base, portefeuille existant analysé par A2, relances d'A1), affiche la complétude, les documents OKF du client et la trace de chaque requête, puis permet de lire et d'alimenter la base générale (collecte A4, A5, A6 par Step Functions).

Simulation seulement : aucune transaction réelle, aucun conseil financier personnalisé.

Le contrat avec les runtimes Python et l'infrastructure est `app/CONTRACTS.md` : chaque réponse est validée par zod (`src/lib/contract/`) avant d'arriver à l'écran.

## Prérequis

- Node.js 20.9 ou plus récent (Node 24 recommandé, comme en CI).
- npm.
- Pour le mode `local` : [uv](https://docs.astral.sh/uv/) et le runtime Python de `app/agents`.
- Pour le mode `aws` : des identifiants AWS valides sur le poste (profil, `aws sso login` ou variables d'environnement).

## Installation et commandes

```bash
cd app/web
npm ci
cp .env.example .env.local   # puis adapter AGENT_MODE et les autres variables
npm run dev                  # http://localhost:3000
```

| Commande | Rôle |
| --- | --- |
| `npm run dev` | Serveur de développement (Turbopack). |
| `npm run build` | Build de production. |
| `npm run start` | Sert le build de production. |
| `npm run lint` | ESLint (configuration plate, règles Next.js et TypeScript). |
| `npm run typecheck` | `tsc --noEmit`, TypeScript strict. |
| `npm test` | Vitest : schémas zod contre les exemples du contrat, simulateur, passerelle, parseur SSE. |

Le port se change avec `PORT=3100 npm run dev`.

## Les trois modes (`AGENT_MODE`)

### `mock` (par défaut)

Simulateur en mémoire du contrat, sans aucun appel réseau : questions de base avec leurs embranchements, A2 (texte collé et fichiers texte ou CSV; les PDF, images et tableurs sont signalés comme non lus), relances d'A1 adaptées au niveau de connaissances, garde-fous, complétude, documents OKF, traces, streaming SSE et collectes Step Functions simulées (environ 9 s). Les données disparaissent au redémarrage du serveur.

```bash
AGENT_MODE=mock npm run dev
```

### `local`

Le serveur Next.js transmet chaque requête au runtime `profile` lancé sur le poste :

```bash
# terminal 1
cd app/agents
AGENT_ROLE=profile ALPHAFORGE_STORE=local uv run python main.py

# terminal 2
cd app/web
AGENT_MODE=local LOCAL_AGENT_URL=http://127.0.0.1:8080/invocations npm run dev
```

Le runtime n'écoute que sur `127.0.0.1` : gardez cette adresse plutôt que `localhost`, que Node peut résoudre d'abord en IPv6 (`::1`). La collecte de la base générale n'existe pas dans ce mode (elle passe par Step Functions) : la page Base de connaissances le signale.

### `aws`

Le serveur Next.js appelle Bedrock AgentCore et Step Functions avec les identifiants AWS du poste (chaîne par défaut du SDK). Rien n'est envoyé au navigateur : les appels AWS ne partent que des route handlers du serveur.

```bash
aws sso login --profile <profil>      # ou tout autre moyen d'obtenir des identifiants
AWS_PROFILE=<profil> AGENT_MODE=aws npm run dev
```

- Runtime `profile` : son ARN est trouvé par son nom `${ALPHAFORGE_PREFIX}_profile` (`ListAgentRuntimes`), puis appelé par `InvokeAgentRuntime` avec le qualificatif `DEFAULT` et `runtimeSessionId = client_id`. Les appels sans client (`health`, `kb.*` sur `general/`) utilisent une session technique propre au serveur.
- Collecte : la machine est trouvée par son nom `ALPHAFORGE_STATE_MACHINE` (`ListStateMachines`). L'interface lance `StartExecution` sans nom ni `run_id` : Step Functions nomme l'exécution par un UUID, qui devient le `run_id`.

Permissions IAM nécessaires pour l'identité du poste :

| Service | Actions |
| --- | --- |
| Bedrock AgentCore | `bedrock-agentcore:ListAgentRuntimes`, `bedrock-agentcore:InvokeAgentRuntime` |
| Step Functions | `states:ListStateMachines`, `states:StartExecution`, `states:ListExecutions`, `states:DescribeExecution` |

## Variables d'environnement

À placer dans `app/web/.env.local` (voir `.env.example`). Aucune n'est exposée au navigateur.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `AGENT_MODE` | `mock` | `mock`, `local` ou `aws`. |
| `LOCAL_AGENT_URL` | `http://127.0.0.1:8080/invocations` | Runtime `profile` local (mode `local`). |
| `AWS_REGION` | `us-east-1` | Région des runtimes et de la machine de collecte. |
| `ALPHAFORGE_PREFIX` | `alphaforge_sandbox` | Préfixe des runtimes AgentCore. |
| `ALPHAFORGE_STATE_MACHINE` | `alphaforge-sandbox-collecte` | Nom de la machine Step Functions de collecte. |
| `AWS_PROFILE` | aucun | Profil AWS facultatif, lu par la chaîne par défaut du SDK. |

## Passerelle (route handlers du serveur)

| Route | Rôle |
| --- | --- |
| `POST /api/agent` | Une action du contrat (`session.start`, `base.answer`, `portfolio.submit`, `followup.reply`, `kb.list`, etc.). Validée par zod, puis transmise au mode choisi. Avec `"stream": true`, `portfolio.submit` et `followup.reply` répondent en `text/event-stream`. |
| `GET /api/health` | Mode courant, santé du runtime et, en mode `aws`, runtime résolu. |
| `GET /api/collect` | Collectes récentes, avec le statut de chaque collecteur (`collected.press`, `collected.data`). `?execution_arn=` donne le détail d'une exécution de la machine configurée. |
| `POST /api/collect` | Lance une collecte : `{ "since"?: "AAAA-MM-JJ", "tickers"?: ["RY.TO"] }`. |

Limites appliquées par le serveur : 5 fichiers de 10 Mo au plus par `portfolio.submit`, base64 vérifié, clés `clients/` servies seulement avec le `client_id` correspondant, aucune clé hors `general/` et `clients/<client_id>/`.

## Structure

```text
src/
  app/                  pages (accueil, profil, base de connaissances, réglages) et routes /api
  components/           interface : profil, trace, base de connaissances, réglages, composants communs
  lib/contract/         schémas zod du contrat et des requêtes, lecture des sorties de collecte
  lib/server/           passerelle : configuration, modes local et aws, erreurs, SSE
  lib/mock/             simulateur du contrat (mode mock)
  lib/client/           appels à la passerelle, session (localStorage), état de l'interface
  lib/i18n/             dictionnaire typé FR (par défaut) et EN
  lib/sse.ts            parseur SSE (fragments, CR/LF, une ligne JSON par événement)
tests/                  tests Vitest
```

## Limites connues

- Pas de mode sombre.
- Le mode `mock` garde tout en mémoire; un redémarrage efface les sessions et les collectes simulées.
- En mode `mock`, A2 ne lit que le texte et les fichiers texte (CSV, TXT, JSON); en mode `aws`, A2 lit aussi les PDF et les images avec le modèle.
- La collecte n'est disponible qu'en modes `mock` et `aws`.
