# AlphaForge AI : interface locale

Interface web d'AlphaForge AI (Datathon PolyFinances 2026), à lancer sur le poste. Elle suit les maquettes approuvées par l'équipe (`.impeccable/preview/` : `parcours.html`, `tableau-de-bord.html`, `details.html`) : fond blanc, rouge Banque Nationale `#E41C23` pour les actions, marine `#0B2341` pour le texte (approximations, aucun logo).

Simulation seulement : aucune transaction réelle, aucun conseil financier personnalisé.

Le contrat avec les runtimes Python et l'infrastructure est `app/CONTRACTS.md` : chaque réponse est validée par zod (`src/lib/contract/`) avant d'arriver à l'écran.

## Écrans

| Route | Écran |
| --- | --- |
| `/` | **Parcours du profil** : un personnage marche le long d'un chemin et s'arrête à un panneau par question de base (le runtime choisit la suivante, embranchements compris). Touches 1 à 9 pour répondre, « Pourquoi cette question ? » tiré de `help`. Un panneau à mallette accueille le portefeuille existant (A2 : texte collé ou fichiers, puis vérification des positions). La maison affiche la première version du profil et mène au tableau de bord. Boutons Trace et Profil : la trace complète et le profil détaillé (faits, provenance, documents OKF) s'ouvrent dans un panneau latéral. |
| `/dashboard` | **Tableau de bord** : tuiles d'indicateurs et assistant. L'assistant s'ouvre sur un paysage (personnage, volée d'oiseaux qui réagit au pointeur et à la saisie), puis devient la conversation avec A1 (`followup.reply`) : relances, questions structurées, arrêt dès 70 %. Chaque réponse porte ses sources et « Comment j'ai répondu », la trace de la requête. |
| `/details` | **Détails du portefeuille** : valeur, rendements quotidiens, retraite, volatilité, comparaison avec XIU.TO, répartition, gouvernance, stress test 2022, rendements mensuels, journal des décisions, les quatre questions de l'atelier BNCD, positions. |
| `/portfolio` | **Portefeuille simulé** : la `Decision` du runtime `portfolio` (CONTRACTS.md, section 12), affichée telle quelle pour un profil de démonstration FICTION (Amira, Mateo, Robert) ou, hors mode `mock`, pour son propre profil. Positions cœur et satellite, style et bande de part actions de l'étape 0, classement des titres individuels (momentum en sensibilité seulement), les quatre questions avec l'étiquette FAIT, HYPOTHÈSE ou FICTION de chaque énoncé et ses faits cliquables (valeur, source, étape de trace), contrefactuels, verdicts des lentilles, contrôles du Judge, trace. Bandeau permanent « Simulation éducative — aucun conseil, aucune transaction ». |
| `/knowledge` | Base de connaissances générale et collecte (A4, A5, A6). |
| `/settings` | Réglages (langue, niveau de connaissances, session ou compte connecté). |
| `/login` | Connexion (seulement en `AUTH_MODE=cognito`) : « Se connecter ou créer un compte », vers la connexion gérée de Cognito. |

`/profile` redirige vers `/`.

### Données d'exemple : mode `mock` seulement

Le tableau de bord, la page Détails et l'assistant ne sont pas branchés sur le moteur de portefeuille (A3, lentilles, Judge) : seule la page `/portfolio` affiche ses décisions. Décision de l'équipe du 2026-11-14 :

- en mode `mock`, les tuiles du tableau de bord, la page Détails et les réponses de l'assistant aux questions suggérées sur le portefeuille (le piège des 50 000 $, l'or, NVDA) reprennent l'exemple des maquettes, marqué « Valeurs d'exemple » et « Exemple simulé » (`src/lib/sample/`, série synthétique calibrée : volatilité 6,1 %, baisse 2022 de −9,8 %, 400 000 $);
- en modes `local` et `aws`, aucun chiffre inventé : les tuiles montrent ce que le code calcule (complétude, risque retenu, horizon, niveau, portefeuille existant valorisé par A2). La page Détails a deux tuiles : « Votre portefeuille simulé » décrit ce que le moteur construit à partir du profil (proposition sous ses limites, débat avec les quatre lentilles, contrôle du Judge, explication sourcée) et mène à `/portfolio`, profil « Mon profil »; « Votre portefeuille existant » montre les expositions du portefeuille confirmé, valorisé par A2, ou renvoie au profil s'il n'y en a pas.

### Animations

La marche, la volée d'oiseaux et l'entrée des graphiques font partie de la maquette : elles jouent même si le système demande de réduire les animations (Windows avec les effets d'animation désactivés le signale). « Passer la marche » saute la marche en cours.

Yan, l'assistant, est le petit robot rouge en pixels de la vidéo de démonstration (`src/components/yan/`) et suit la même règle. Sur l'accueil, il naît du carré rouge de la marque : ses pixels traversent la page et se rassemblent à droite du titre. Il vole ensuite vers l'avatar de chaque carte du parcours, puis vers l'en-tête de l'assistant du tableau de bord. À chaque arrivée, il se pose en s'écrasant. Il flotte au-dessus de son ombre et cligne des yeux. Il plisse les yeux de joie (« ^ ^ ») à l'accueil et quand le profil est prêt, et regarde autour de lui pendant qu'A1 prépare sa réponse.

### Tailles d'écran

Vérifiées à 1920 × 1080, 1440 × 900, 1280 × 720, 1024 × 768 et 390 × 844 :

- sur téléphone (moins de 760 px), le parcours devient une bande en bas de l'écran où le personnage marche, sous les cartes; la barre du haut passe en icônes;
- sous 1280 px, les onglets passent sur une deuxième ligne que l'on fait défiler;
- sur un écran bas (portable), les cartes du parcours se resserrent et leur bouton principal reste visible en bas de la carte;
- le tableau de bord tient sur un écran à partir de 1100 px de large et 805 px de haut; plus bas, la page défile un peu plutôt que de couper les tuiles.

Le rouge est réservé aux actions principales, à la marque et à la progression; les sélections, liens, focus et icônes sont en marine, comme dans les maquettes.

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

### Portefeuille simulé (`/portfolio`)

L'interface ne calcule rien : chaque nombre est la valeur d'un `Fact` du moteur, un poids de `positions[]` ou une limite du Judge, mis en forme par `src/lib/portfolio/format.ts`, port exact de `fmt` (`finance/debate/facts.py`) : « 12,3 % », « 31 300 $ », arrondi au pair comme Python. Un test vérifie que chaque nombre écrit par le moteur dans une explication est la valeur ainsi formatée d'un fait qu'elle cite.

- `mock` : les réponses de `build` sont de vraies décisions du moteur (mode `rules`), enregistrées dans `src/lib/fixtures/portfolio-<persona>.json`. Aucun chiffre n'y est écrit à la main. Pour les régénérer : `cd app/agents && ALPHAFORGE_BT_DATA=<données longues> uv run --group finance python scripts/finance/export_web_fixtures.py`.
- `local` : `LOCAL_PORTFOLIO_URL` (runtime `portfolio` lancé avec `AGENT_ROLE=portfolio PORT=8081 ALPHAFORGE_STORE=local uv run --group finance python main.py`).
- `aws` : `InvokeAgentRuntime` sur `${ALPHAFORGE_PREFIX}_portfolio` (déployé seulement avec `portfolio_enabled = true`), `runtimeSessionId = client_id`, ou une session stable par profil de démonstration.

Le moteur se choisit hors `mock` : règles (déterministe, rapide) ou lentilles LLM (Bedrock, plusieurs minutes). Pour Robert, l'interface envoie sa demande (`request` : 50 000 $ dans TSLA), que le Judge refuse et encadre.

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
| Bedrock AgentCore | `bedrock-agentcore:ListAgentRuntimes`, `bedrock-agentcore:InvokeAgentRuntime` (runtimes `profile` et, pour `/portfolio`, `portfolio`) |
| Step Functions | `states:ListStateMachines`, `states:StartExecution`, `states:ListExecutions`, `states:DescribeExecution` |

## Connexion (`AUTH_MODE`)

Par défaut (`AUTH_MODE=off`), il n'y a pas de connexion : le navigateur garde son `client_id` dans le `localStorage`, comme avant, dans les trois modes.

Avec `AUTH_MODE=cognito` (déploiement AWS, `infrastructure/infra/auth.tf`), chaque investisseur se crée un compte sur la connexion gérée d'Amazon Cognito (courriel vérifié par un code). Un compte = un `client_id` = une base `clients/<client_id>/` (CONTRACTS.md, section 7.1) :

- toute page demande une session (sinon `/login`), toute route `/api/*` aussi (sinon 401), sauf `/api/auth/*`, `/api/health` et `/api/ping`;
- le serveur tire le `client_id` de la session, jamais du corps : un autre `client_id` ou une clé `clients/` d'un autre compte donne 403. Les profils de démonstration FICTION de `/portfolio` restent ouverts à tout compte connecté;
- seuls les membres du groupe Cognito `admin` lancent une collecte (`POST /api/collect`); tout compte connecté voit les exécutions;
- la session est un cookie `httpOnly`, `SameSite=Lax`, `Secure` hors `http://localhost`, chiffré et authentifié (AES-256-GCM, `node:crypto`). Aucun jeton n'est lisible par le JavaScript du navigateur. Elle dure ce que dure l'ID token (8 h par défaut, `auth_session_hours`), puis l'investisseur se reconnecte;
- au chargement, l'interface lit `/api/auth/me` et prend le `client_id` du compte; l'historique local (traces, conversation) reste rangé par `client_id`. Le menu de compte (en haut à droite) donne le courriel et « Se déconnecter », qui efface aussi la session locale de ce client. Les profils anonymes d'avant ne sont pas migrés.

Pour tester la connexion avec `next dev` après un déploiement (le client Cognito accepte déjà `http://localhost:3000`), prendre les outputs `auth_issuer`, `auth_client_id` et `auth_domain` du workspace HCP Terraform :

```bash
AUTH_MODE=cognito APP_URL=http://localhost:3000 AUTH_SESSION_SECRET=$(openssl rand -hex 32) \
  COGNITO_ISSUER=... COGNITO_CLIENT_ID=... COGNITO_DOMAIN=... npm run dev
```

## Variables d'environnement

À placer dans `app/web/.env.local` (voir `.env.example`). Aucune n'est exposée au navigateur.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `AGENT_MODE` | `mock` | `mock`, `local` ou `aws`. |
| `LOCAL_AGENT_URL` | `http://127.0.0.1:8080/invocations` | Runtime `profile` local (mode `local`). |
| `LOCAL_PORTFOLIO_URL` | `http://127.0.0.1:8081/invocations` | Runtime `portfolio` local (mode `local`, page `/portfolio`). |
| `AWS_REGION` | `us-east-1` | Région des runtimes et de la machine de collecte. |
| `ALPHAFORGE_PREFIX` | `alphaforge_sandbox` | Préfixe des runtimes AgentCore. |
| `ALPHAFORGE_STATE_MACHINE` | `alphaforge-sandbox-collecte` | Nom de la machine Step Functions de collecte. |
| `AWS_PROFILE` | aucun | Profil AWS facultatif, lu par la chaîne par défaut du SDK. |
| `AUTH_MODE` | `off` | `off` (sans connexion) ou `cognito` (connexion obligatoire). Les variables suivantes ne servent qu'en `cognito`, où elles sont toutes requises. |
| `COGNITO_ISSUER` | aucun | `https://cognito-idp.<région>.amazonaws.com/<user pool>` (output `auth_issuer`). |
| `COGNITO_CLIENT_ID` | aucun | Client d'application public, sans secret (output `auth_client_id`). |
| `COGNITO_DOMAIN` | aucun | Domaine de la connexion gérée, `https://<préfixe>.auth.<région>.amazoncognito.com` (output `auth_domain`). |
| `APP_URL` | aucun | Origine publique de l'interface : le domaine CloudFront, ou `http://localhost:3000`. Sert aux URL de retour et au drapeau `Secure` du cookie. |
| `AUTH_SESSION_SECRET` | aucun | Clé du cookie de session, 32 caractères au moins (Terraform : `random_password`). |

## Passerelle (route handlers du serveur)

| Route | Rôle |
| --- | --- |
| `POST /api/agent` | Une action du contrat (`session.start`, `base.answer`, `portfolio.submit`, `followup.reply`, `kb.list`, etc.). Validée par zod, puis transmise au mode choisi. Avec `"stream": true`, `portfolio.submit` et `followup.reply` répondent en `text/event-stream`. |
| `POST /api/portfolio` | L'action `build` du runtime `portfolio` : `{ "client_id"? , "persona"?: "amira" \| "mateo" \| "robert", "as_of"?, "strategy"?, "style_preference"?, "request"?, "mode"?, "locale"? }`, `client_id` ou `persona` requis. JSON seulement; au-delà de 20 s (mode `llm`), la réponse part en 200 tout de suite et envoie un espace toutes les 15 s jusqu'à l'enveloppe, car CloudFront coupe une réponse muette après 60 s (`src/lib/server/heartbeat.ts`); la `Decision` est validée par zod dans le navigateur (`src/lib/contract/portfolio.ts`). |
| `GET /api/health` | Mode courant, santé du runtime et, en mode `aws`, runtime résolu. |
| `GET /api/collect` | Collectes récentes, avec le statut de chaque collecteur (`collected.press`, `collected.data`). `?execution_arn=` donne le détail d'une exécution de la machine configurée. |
| `POST /api/collect` | Lance une collecte : `{ "since"?: "AAAA-MM-JJ", "tickers"?: ["RY.TO"] }`. Groupe `admin` exigé en `AUTH_MODE=cognito`. |
| `GET /api/auth/login?next=/chemin` | Commence une connexion (code, PKCE, `state`, `nonce`, `lang` selon la langue de l'interface), puis la connexion gérée de Cognito. |
| `GET /api/auth/callback` | Retour de Cognito : échange du code, vérification de l'ID token (signature par le JWKS, `iss`, `aud`, `exp`, `token_use`, `nonce`), cookie de session. |
| `POST /api/auth/logout` | Efface la session, puis `/logout` de Cognito. Refusé (403) si l'en-tête `Origin` diffère de `APP_URL`. |
| `GET /api/auth/me` | `{ "mode": "off" \| "cognito", "user": { "email", "client_id", "groups", "admin", "expires_at" } \| null }`; 401 en `cognito` sans session. |

Limites appliquées par le serveur : 5 fichiers de 10 Mo au plus par `portfolio.submit`, base64 vérifié, clés `clients/` servies seulement avec le `client_id` correspondant, aucune clé hors `general/` et `clients/<client_id>/`.

## Structure

```text
src/
  app/                  / (parcours), (app)/ : dashboard, details, portfolio, knowledge, settings, sous la navigation; routes /api
  components/journey/   parcours : scène et personnage, cartes de question, portefeuille existant, synthèse
  components/dashboard/ tableau de bord : tuiles, assistant, scène d'accueil et volée d'oiseaux
  components/details/   détails du portefeuille et graphiques
  components/           aussi : profil (champs de réponse, revue A2, panneau), trace, base de connaissances, réglages, composants communs
  lib/contract/         schémas zod du contrat et des requêtes, lecture des sorties de collecte
  lib/server/           passerelle : configuration, modes local et aws, erreurs, SSE
  lib/server/auth/      connexion Cognito : OIDC, cookie chiffré, garde (client_id de la session), routes /api/auth
  proxy.ts              garde de Next.js 16 (ex-middleware) : /login ou 401 sans session en AUTH_MODE=cognito
  lib/mock/             simulateur du contrat (mode mock)
  lib/sample/           portefeuille et réponses d'exemple des maquettes (mode mock seulement)
  lib/fixtures/         réponses de `build` produites par le moteur (mode mock de /portfolio)
  lib/portfolio/        formats du moteur, lecture des faits d'une Decision, scénarios de démonstration
  components/portfolio/ portefeuille simulé : décision, faits cliquables, panneau des sources
  lib/journey/          chemin du parcours (panneaux, maison, reprise d'une session)
  lib/client/           appels à la passerelle, session (localStorage), état de l'interface
  lib/i18n/             dictionnaire typé FR (par défaut) et EN; screens.ts pour les écrans des maquettes, portfolio.ts pour le portefeuille simulé, okf-types.ts pour les libellés des types OKF
  lib/sse.ts            parseur SSE (fragments, CR/LF, une ligne JSON par événement)
tests/                  tests Vitest (contrat, simulateur, passerelle, SSE, parcours, données d'exemple, portefeuille simulé, textes)
```

Les styles des trois écrans des maquettes sont des modules CSS (`*.module.css`) portés des maquettes; le portefeuille simulé reprend ceux de Détails avec les siens, et Yan, le robot de l'assistant, a le sien. Les autres composants utilisent Tailwind avec les jetons de `globals.css`.

## Limites connues

- Pas de mode sombre.
- Le parcours n'offre pas de retour à une question de base déjà répondue : le contrat n'a pas d'action pour la modifier.
- Les réponses de l'assistant sur le portefeuille sont des exemples écrits d'avance (mode `mock`) : l'assistant n'est pas branché sur le moteur du volet finance, que seule la page `/portfolio` affiche.
- Le mode `mock` garde tout en mémoire; un redémarrage efface les sessions et les collectes simulées.
- En mode `mock`, A2 ne lit que le texte et les fichiers texte (CSV, TXT, JSON); en mode `aws`, A2 lit aussi les PDF et les images avec le modèle.
- La collecte n'est disponible qu'en modes `mock` et `aws`.
- En `AUTH_MODE=cognito`, le lien direct de l'ALB (`web_alb_url`, HTTP) ne garde pas de session : le cookie est `Secure` et Cognito n'accepte un retour en HTTP que sur `localhost`. Un build du portefeuille de plus de 60 s (limite de CloudFront) n'a donc plus de voie de secours.
- La session ne suit pas en direct les changements du compte : un ajout au groupe `admin` vaut à la connexion suivante.
