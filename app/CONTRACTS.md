# Contrats d'AlphaForge AI

Version 1, 2026-11-14. Source de vérité entre `app/agents` (Python, AgentCore), `app/web` (Next.js local) et `infrastructure/` (Terraform). Un champ ajouté doit être optionnel et décrit ici; un champ retiré demande une nouvelle version de ce fichier.

Périmètre de la version 1 : construire le profil (questions de base déterministes, relances A1, portefeuille existant analysé par A2) et alimenter la base générale (collecte A4, A5, A6 orchestrée par Step Functions). Le portefeuille guidé (A3, agents d'analyse, Judge) et le test psychométrique viendront plus tard. Il n'y a pas de choix de persona : chaque utilisateur construit son propre profil.

## 1. Runtimes AgentCore

Un seul zip de code (`app/agents`, Python 3.13, linux/arm64) alimente quatre runtimes, qui ne diffèrent que par `AGENT_ROLE` et par leur rôle IAM.

| Runtime AgentCore | `AGENT_ROLE` | Appelé par | Accès S3 (moindre privilège) |
| --- | --- | --- | --- |
| `alphaforge_sandbox_profile` | `profile` | serveur Next.js | lit `general/`, lit et écrit `clients/` |
| `alphaforge_sandbox_press` | `press` | Step Functions | lit et écrit `staging/<run_id>/press/` |
| `alphaforge_sandbox_data` | `data` | Step Functions | lit et écrit `staging/<run_id>/data/` |
| `alphaforge_sandbox_supervisor` | `supervisor` | Step Functions | lit `staging/` et `general/`; écrit `staging/<run_id>/supervisor/`, `general/actualites/`, `general/donnees/` et `general/index.md`, jamais `general/methodologie/` (géré par Terraform). L'ingestion de la Knowledge Base est lancée par Step Functions, pas par A6. |

Chaque rôle n'a `s3:ListBucket` que sous ses propres préfixes. Pour un objet absent, S3 répond donc 403 (`AccessDenied`) et non 404 : le magasin vérifie alors l'absence par `ListObjectsV2` sur la clé exacte, et ne conclut à un refus que si l'objet existe.

Variables d'environnement posées par Terraform sur chaque runtime :

| Variable | Exemple | Rôle |
| --- | --- | --- |
| `AGENT_ROLE` | `profile` | Choisit le point d'entrée. |
| `ALPHAFORGE_ENV` | `sandbox` | Environnement. |
| `ALPHAFORGE_RELEASE` | `1a2b3c4d` | SHA court du commit déployé, renvoyé dans chaque réponse. |
| `ALPHAFORGE_REGION` | `us-east-1` | Région des appels AWS. |
| `ALPHAFORGE_STORE` | `s3` | `s3` en AWS, `local` en développement. |
| `ALPHAFORGE_BUCKET` | `alphaforge-sandbox-kb-024848478575` | Bucket des bases OKF. |
| `ALPHAFORGE_LOCAL_DIR` | `.local-kb` | Racine du magasin `local` (développement seulement). |
| `ALPHAFORGE_MODEL_ID` | `us.anthropic.claude-opus-5-5` | Profil d'inférence Bedrock de tous les agents. |
| `ALPHAFORGE_KB_ID` | `ABCDEFGHIJ` | Knowledge Base de la base générale (vide en local). |
| `ALPHAFORGE_GUARDRAIL_ID` / `ALPHAFORGE_GUARDRAIL_VERSION` | `abc123` / `1` | Guardrail du cadre responsable, appliqué aux agents du runtime `profile` (vide en local). |

Transport : `POST /invocations`, corps JSON, réponse JSON (`application/json`), ou SSE (`text/event-stream`) quand la requête contient `"stream": true` (section 3.4). `GET /ping` est servi par `BedrockAgentCoreApp`.

Session AgentCore (`runtimeSessionId`) : le `client_id` (UUID v4, 36 caractères) pour `profile`; `<nom d'exécution Step Functions>-<rôle>`, complété à au moins 33 caractères, pour les collecteurs.

Développement local : `AGENT_ROLE=profile ALPHAFORGE_STORE=local uv run python main.py` dans `app/agents` sert les mêmes requêtes sur `http://127.0.0.1:8080/invocations`. Le serveur n'écoute que sur `127.0.0.1` : préférer cette adresse à `localhost`, que Node peut résoudre d'abord en IPv6.

## 2. Enveloppe commune

Toute requête est un objet JSON avec `action` (chaîne). Toute réponse non streamée est l'un de :

```json
{ "ok": true, "release": "1a2b3c4d", "...": "champs propres à l'action" }
{ "ok": false, "release": "1a2b3c4d", "error": { "code": "invalid_answer", "message": "texte lisible", "details": {} } }
```

Codes d'erreur : `bad_request`, `unknown_action`, `not_found`, `invalid_answer`, `conflict`, `model_error`, `guardrail_blocked`, `internal`.

Toutes les actions de tous les rôles acceptent `{"action": "health"}` et répondent `{"ok": true, "role": "profile", "release": "…", "env": "sandbox"}`.

## 3. Runtime `profile`

### 3.1 Étapes

```mermaid
stateDiagram-v2
    [*] --> base_questions
    base_questions --> existing_portfolio: "portefeuille existant = oui"
    base_questions --> followups: "portefeuille existant = non"
    existing_portfolio --> portfolio_review: "portfolio.submit"
    existing_portfolio --> followups: "portfolio.skip"
    portfolio_review --> followups: "portfolio.confirm"
    followups --> complete: "A1 juge le profil complet, ou l'investisseur s'arrête dès 70 %"
    complete --> followups: "followup.reply"
```

- `base_questions` : questions déterministes, sans modèle. D'abord le niveau de connaissances, puis les cinq dimensions du profil, puis « avez-vous un portefeuille existant ? ».
- `existing_portfolio` : l'investisseur fournit son portefeuille sous n'importe quelle forme (texte collé, CSV, tableur, PDF, image, JSON).
- `portfolio_review` : A2 propose des positions normalisées que l'investisseur corrige puis confirme.
- `followups` : A1 relance sur ce qui manque, sans s'écarter du sujet.
- `complete` : complétude d'au moins 70 %, et A1 n'a plus de relance utile, ou l'investisseur a choisi de s'arrêter.

### 3.2 Actions

| Action | Entrée (en plus de `action`) | Effet |
| --- | --- | --- |
| `session.start` | `locale` (`fr`, `en`), `client_id` facultatif | Crée la base du client si elle n'existe pas; renvoie la première question en attente. |
| `session.resume` | `client_id`, `locale` facultatif | Renvoie l'état courant, sans rien modifier. |
| `base.answer` | `client_id`, `question_id`, `value` | Valide la réponse, l'écrit dans la base du client, renvoie la question suivante ou l'étape suivante. |
| `portfolio.submit` | `client_id`, `text` facultatif, `files` facultatif : `[{ "name", "media_type", "data_base64" }]` | A2 extrait des positions; étape `portfolio_review`. Au moins `text` ou un fichier. 10 Mo au plus par fichier, 5 fichiers. |
| `portfolio.confirm` | `client_id`, `positions` (liste de `Position`, corrigée par l'investisseur) | Calcule les expositions par le code, écrit `portefeuille-existant.md`; étape `followups`. |
| `portfolio.skip` | `client_id` | Passe aux relances sans portefeuille. |
| `followup.reply` | `client_id`, `answers` facultatif : `[{ "question_id", "value" }]`, `message` facultatif, `stop` facultatif (booléen) | A1 enregistre, met le profil à jour, renvoie ses relances ou passe à `complete`. `stop: true` n'est accepté qu'à partir de 70 %. Sans `answers` ni `message` à l'arrivée en `followups`, A1 pose ses premières relances. |
| `settings.update` | `client_id`, `locale` facultatif, `knowledge_level` facultatif | Change la langue ou le niveau de connaissances (réglages). |
| `profile.get` | `client_id` | Comme `session.resume`, avec en plus `documents`. |
| `kb.list` | `prefix` (`general/` ou `clients/<client_id>/`) | `{ "items": [{ "key", "title", "type", "description", "updated_at" }] }` |
| `kb.get` | `key` | `{ "key", "content" }` : le document OKF complet (frontmatter et corps). Une clé `clients/` n'est servie qu'avec le `client_id` correspondant. |

Toutes les actions qui portent sur un client renvoient `ClientState` :

```json
{
  "ok": true,
  "release": "1a2b3c4d",
  "client_id": "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90",
  "locale": "fr",
  "stage": "base_questions",
  "message": null,
  "questions": [ "Question" ],
  "profile": "ProfileView",
  "completeness": "Completeness",
  "portfolio": null,
  "trace": [ "TraceStep" ]
}
```

- `questions` : les questions à afficher maintenant. En `base_questions`, exactement une. En `followups`, de zéro à trois, posées par A1. Vide en `existing_portfolio`, `portfolio_review` et `complete`.
- `message` : texte Markdown de l'agent (A1 ou A2) dans la langue de `locale`, adapté au niveau de connaissances. Il vaut `null` après une transition déterministe.
- `portfolio` : `PortfolioView` dès que A2 a proposé des positions, sinon `null`.
- `trace` : les étapes de cette requête seulement. L'historique complet est dans la base du client.

### 3.3 Types

`Question` (même forme pour les questions déterministes et celles d'A1) :

```json
{
  "id": "q_horizon",
  "source": "deterministic",
  "dimension": "horizon",
  "kind": "single_choice",
  "prompt": "Dans combien de temps aurez-vous besoin d'une part importante de cet argent ?",
  "help": "L'horizon ne se déduit ni de l'âge ni de la tolérance au risque.",
  "options": [ { "value": "lt3", "label": "Moins de 3 ans" }, { "value": "3to10", "label": "De 3 à 10 ans" }, { "value": "gt10", "label": "10 ans et plus" } ],
  "min": null,
  "max": null,
  "unit": null,
  "required": true,
  "field": "horizon.horizon_band"
}
```

- `source` : `deterministic` ou `a1`.
- `field` : champ du profil que la réponse renseigne, sous la même forme que `facts[].field` (`<dimension>.<nom>`), ou `null` (facultatif).
- `id` : `q_<nom>` pour une question de base (`questionnaire.yaml`), `a1_<tour>_<n>` pour une relance d'A1. Si A1 est indisponible, le code pose des questions de repli `fb_<tour>_<n>`, avec `source: deterministic`.
- `dimension` : `knowledge`, `objective`, `horizon`, `risk_tolerance`, `risk_capacity`, `constraints`, `preferences`, `context`.
- `kind` et type de `value` attendu : `single_choice` (chaîne parmi `options[].value`), `multi_choice` (liste de chaînes), `boolean` (booléen), `number` (nombre, borné par `min` et `max`), `money` (nombre, `unit` = devise, `CAD` par défaut), `percent` (nombre de 0 à 100), `scale` (entier de `min` à `max`), `text` (chaîne de 1 à 2 000 caractères).
- Les textes (`prompt`, `help`, `label`) sont déjà dans la langue de `locale`; l'interface n'en traduit aucun.

`Completeness` :

```json
{ "score": 0.62, "displayed": 0.62, "threshold": 0.7, "cap": 0.95, "ready": false, "missing": [ { "dimension": "risk_capacity", "field": "emergency_fund", "label": "Fonds d'urgence" } ] }
```

- `score` : part pondérée des champs requis connus, calculée par le code (de 0 à 1). `displayed` = `min(score, cap)`. `ready` = `score >= threshold`.

`ProfileView` :

```json
{
  "knowledge_level": "intermediate",
  "effective_risk": "medium",
  "dimensions": {
    "objective":      { "status": "known",   "summary": "Croissance à long terme", "fields": { "goal": "growth" } },
    "horizon":        { "status": "partial", "summary": "10 ans et plus", "fields": { "horizon_band": "gt10" } },
    "risk_tolerance": { "status": "known",   "summary": "Élevée", "fields": {} },
    "risk_capacity":  { "status": "missing", "summary": null, "fields": {} },
    "constraints":    { "status": "partial", "summary": "CELI", "fields": {} },
    "preferences":    { "status": "known",   "summary": "Exclut le tabac", "fields": {} },
    "context":        { "status": "partial", "summary": null, "fields": {} }
  },
  "risk": { "tolerance": "high", "capacity": "medium", "effective": "medium" },
  "facts": [ { "field": "horizon.horizon_band", "value": "gt10", "provenance": "base:q_horizon", "at": "2026-11-14T23:10:00Z" } ],
  "documents": [ { "key": "clients/8f0c…/profil.md", "title": "Profil investisseur" } ]
}
```

- `knowledge_level` : `beginner`, `intermediate`, `advanced` ou `null`; calculé par le code à partir des questions de niveau et de l'auto-évaluation.
- `effective_risk` : `low`, `low_medium`, `medium`, `medium_high`, `high` ou `null`; le minimum de la tolérance et de la capacité, calculé par le code. `risk` détaille les trois niveaux (facultatif).
- `status` : `known`, `partial`, `missing`. `provenance` : `base:<question_id>`, `a1:<numéro de tour>`, `a2:<numéro de tour>`, `settings`. Le numéro de tour est commun à A1 et A2 dans la session : un tour d'A1 qui suit A2 est `a1:2`.
- `documents` n'est rempli que par `profile.get`.

`Position` et `PortfolioView` :

```json
{
  "positions": [
    { "id": "p1", "raw": "100 RY.TO", "ticker": "RY.TO", "name": "Royal Bank of Canada", "asset_class": "equity", "sector": "Financials", "market": "TSX", "currency": "CAD", "quantity": 100, "market_value": null, "account_type": "tfsa", "price": 134.2, "price_date": "2026-11-12", "price_source": "starter:prices_daily.csv", "value_cad": 13420.0, "resolved": true, "notes": null }
  ],
  "unresolved": [ { "raw": "fonds maison XYZ", "reason": "titre introuvable", "position_id": "p2" } ],
  "fx": { "pair": "USDCAD", "rate": 1.4255, "date": "2026-11-12", "source": "starter:fx_usdcad_daily.csv" },
  "exposures": {
    "total_value_cad": 13420.0,
    "by_asset_class": { "equity": 1.0 },
    "by_currency": { "CAD": 1.0 },
    "by_market": { "TSX": 1.0 },
    "by_sector": { "Financials": 1.0 },
    "top_positions": [ { "id": "p1", "weight": 1.0 } ],
    "flags": [ "concentration_single_position", "home_bias_canada" ]
  },
  "status": "draft",
  "sources": [ { "id": "starter-prices", "title": "Jeu de départ, prices_daily.csv", "resource": "starter:prices_daily.csv", "retrieved_at": "2026-11-13" } ]
}
```

- `asset_class` : `equity`, `etf_equity`, `etf_bond`, `etf_commodity`, `bond`, `cash`, `crypto`, `fund`, `other`. `account_type` : `tfsa` (CELI), `rrsp` (REER), `resp` (REEE), `rrif` (FERR), `non_registered`, `unknown`, ou `null`.
- `ticker` peut être `null` : A2 garde en ligne ce qu'il n'a pas identifié, et l'investisseur peut confirmer une telle ligne. Une ligne ajoutée par l'investisseur demande un `ticker` ou une `market_value`.
- `flags` (seuils dans `portfolio.py`) : `concentration_single_position`, `concentration_sector`, `home_bias_canada`, `crypto_exposure_high`, `cash_heavy`, `few_holdings`, `unvalued_positions`. L'interface affiche le code brut d'un drapeau inconnu.
- Les expositions sont des parts de 0 à 1 de `total_value_cad`, calculées par le code (jamais par le modèle). La conversion USD/CAD utilise le dernier taux de `fx_usdcad_daily.csv`, cité dans `sources`.
- `status` : `draft` après `portfolio.submit`, `confirmed` après `portfolio.confirm`. `portefeuille-existant.md` est écrit dès `portfolio.submit`, avec le statut OKF `draft`, puis `stable` après `portfolio.confirm`.
- Un titre absent du jeu de départ est cherché sur Yahoo Finance (au plus 10 appels) : symbole américain, puis `.TO` si la devise est inconnue. L'URL est citée dans `sources`.

`TraceStep` :

```json
{ "id": "st_01", "at": "2026-11-14T23:10:00.120Z", "kind": "deterministic", "actor": "questionnaire", "title": "Question suivante choisie par les règles", "detail": "q_horizon après q_goal", "inputs": { "question_id": "q_goal" }, "outputs": { "next": "q_horizon" }, "sources": [], "duration_ms": 3 }
```

- `kind` : `deterministic`, `agent`, `model`, `tool`, `storage`, `guardrail`. `actor` : `questionnaire`, `completeness`, `A1`, `A2`, `A4`, `A5`, `A6`, `store`, `guardrail`. `A7`, `A8`, `polly` et `mediaconvert` sont réservés à la fonctionnalité vidéo tldoole, décrite dans sa propre section.
- `sources` : `[{ "id", "title", "resource", "published_at"?, "observed_at"?, "retrieved_at"? }]`.
- Une trace ne contient ni raisonnement interne du modèle ni secret : le titre et le détail décrivent l'action observable (outil appelé, entrées, résultat).

### 3.4 Streaming

Pour `portfolio.submit` et `followup.reply`, la requête peut contenir `"stream": true`. Le runtime répond alors en `text/event-stream`, un événement JSON par ligne `data:` :

```text
data: {"type": "trace", "step": { "...": "TraceStep" }}
data: {"type": "delta", "text": "morceau du message de l'agent"}
data: {"type": "result", "result": { "...": "ClientState" }}
data: {"type": "error", "error": { "code": "model_error", "message": "…" }}
```

- `delta` : un événement par message d'agent, qui porte le message entier, et non un événement par jeton. Opus 5.5 rend le texte placé entre deux appels d'outil comme un raisonnement masqué : le message passe donc par l'argument d'un outil `finish_turn`.
- Issues du modèle : `guardrail_intervened` donne `guardrail_blocked`; `content_filtered` et un refus donnent `model_error`.

Le flux se termine toujours par un seul `result` ou un seul `error`. Le `result` est identique à la réponse non streamée.

## 4. Runtimes de collecte

Les trois collecteurs acceptent leur tâche aussitôt, travaillent en arrière-plan dans leur session AgentCore (tâche asynchrone de `BedrockAgentCoreApp`, `/ping` à `HealthyBusy`), puis écrivent un marqueur que Step Functions sonde.

| Rôle | Requête | Réponse immédiate |
| --- | --- | --- |
| `press` (A4) | `{"action": "collect", "run_id", "since"?: "AAAA-MM-JJ", "tickers"?: ["RY.TO"]}` | `{"ok": true, "accepted": true, "run_id", "marker": "staging/<run_id>/press/_done.json"}`, avec `already_running: true` ou `already_done: true` si ce `run_id` est en cours ou déjà terminé |
| `data` (A5) | `{"action": "collect", "run_id", "since"?, "tickers"?}` | idem, `staging/<run_id>/data/_done.json` |
| `supervisor` (A6) | `{"action": "curate", "run_id"}` | idem, `staging/<run_id>/supervisor/_done.json` |

- `since` vaut par défaut sept jours avant la date du jour; `tickers` vaut par défaut l'univers du jeu de départ.
- Marqueur des collecteurs : `{"status": "ok" | "error", "role", "run_id", "items": 12, "keys": ["staging/<run_id>/press/<id>.json"], "error": null, "started_at", "finished_at"}`.
- Marqueur du superviseur : `{"status": "ok" | "error", "role": "supervisor", "run_id", "written": ["general/actualites/2026/11/<slug>.md"], "rejected": [{"key", "reason"}], "error": null, "started_at", "finished_at"}`.
- Les marqueurs portent aussi `warnings`, `release` et `trace` (les dernières étapes), facultatifs.
- Quand la revue éditoriale d'A6 est indisponible ou sans décision, A6 écrit quand même les données, dont le texte vient du code, mais retient les actualités en disant pourquoi. La collecte suivante les reproposera.
- Élément collecté (`staging/<run_id>/<role>/<id>.json`) : `{"id", "kind": "news" | "series" | "quote", "title", "url", "source", "published_at", "observed_at", "retrieved_at", "language", "tickers": [], "summary", "data": {}}`. `published_at` est la date de publication; `observed_at`, la date de référence d'une donnée (par exemple le mois d'un IPC). Pour une série, `published_at` est l'heure de récupération, une borne supérieure sûre (`data.published_at_basis = "retrieved_at_upper_bound"`). Pour une cotation, c'est l'heure du dernier cours donnée par Yahoo Finance (`regularMarketTime`).
- A6 rejette un élément sans source, sans date de publication, publié après sa date de récupération, ou en double d'un document existant, et dit pourquoi.

## 5. Magasin OKF (S3 ou local)

```text
general/index.md                            écrit par A6 seulement, absent avant la première collecte
general/methodologie/<slug>.md              seed versionné dans app/knowledge/general/, poussé par Terraform
general/actualites/<AAAA>/<MM>/<slug>.md    écrit par A6
general/donnees/<serie>/<slug>.md           écrit par A6
clients/<client_id>/index.md
clients/<client_id>/profil.md               profil et ses données structurées
clients/<client_id>/portefeuille-existant.md
clients/<client_id>/journal.md              chaque réponse, avec sa provenance et sa date
clients/<client_id>/traces/<horodatage>-<action>.json
staging/<run_id>/<role>/<id>.json
staging/<run_id>/<role>/_done.json
runtime/agents-<release>.zip                code des runtimes, poussé par Terraform
```

Chaque document `.md` est un document OKF : un frontmatter YAML puis un corps Markdown.

```yaml
type: Investor Profile            # Investor Profile, Existing Portfolio, Profile Journal, News, Data Series, Methodology, Index
title: Profil investisseur
description: Profil en cinq dimensions, niveau de connaissances et complétude.
tags: [profil-investisseur]
status: draft                     # draft ou stable
owners: [alphaforge-a1]
sensitivity: client               # client pour clients/, public pour general/
generated: { by: "agent:A1", at: "2026-11-14T23:10:00Z" }
stale_after: "2027-02-14T00:00:00Z"
sources:
  - { id: base-q_horizon, title: "Réponse à q_horizon", resource: "base:q_horizon", retrieved_at: "2026-11-14T23:10:00Z" }
data: {}                          # données structurées lues par le code (profil, positions, série…)
```

- `journal.md` porte ses entrées dans `data.entries[]`, en ajout seulement, une entrée par événement : `{at, kind, provenance, ...}`.
  - `kind` vaut `answer` (`field`, `value`, `question_id`?, `previous`?), `message` ou `stage` (`value`, `previous`, `note`).
  - Une entrée `message` garde le texte libre de l'investisseur (`followup.reply.message`) avec sa provenance `a1:<tour>`, `text` et `locale`. Elle n'est écrite qu'après un tour d'A1 réussi, donc jamais quand le garde-fou bloque.
  - Une requête écrit le journal au plus une fois.
- La base générale ne contient rien d'un client; une base de client ne recopie pas la base générale.
- Chaque document d'actualité ou de données garde sa date d'observation et sa date de publication.

## 6. Step Functions de collecte

Machine `alphaforge-sandbox-collecte`, déclenchée par EventBridge Scheduler et par l'interface. Entrée : `{"run_id"?: string, "since"?: "AAAA-MM-JJ", "tickers"?: [string]}`; `run_id` vaut par défaut le nom de l'exécution. `run_id` suit `^[A-Za-z0-9_-]{1,64}$`, car il entre dans les clés S3 et les identifiants de session. Un collecteur refuse tout autre `run_id` par `bad_request`, et l'interface laisse Step Functions nommer l'exécution, par un UUID.

```mermaid
flowchart LR
    S["Scheduler ou interface"] --> P{"Parallèle"}
    P --> A4["A4 : collect, puis sonde du marqueur"]
    P --> A5["A5 : collect, puis sonde du marqueur"]
    A4 --> A6["A6 : curate, puis sonde du marqueur"]
    A5 --> A6
    A6 --> I["Ingestion de la Knowledge Base, puis sonde du statut"]
    I --> F["Fin : documents écrits, rejetés, statut de l'ingestion"]
```

- La machine sonde chaque marqueur par `ListObjectsV2` (préfixe `staging/`), puis le lit. Délai de 1200 s par agent, sondage toutes les 15 s.
- A4 ou A5 en échec (appel refusé, marqueur absent dans le délai, ou `status: "error"`) terminent leur branche avec `status: "error"` sans arrêter la collecte. A6 lit les marqueurs présents et traite ce qui est arrivé : un marqueur absent ou en erreur n'empêche pas la curation.
- Un échec d'A6 ou de l'ingestion fait échouer l'exécution.

## 7. Interface locale

Le serveur Next.js appelle AWS avec les identifiants AWS du poste (chaîne par défaut), jamais depuis le navigateur. Variables de `app/web/.env.local` :

| Variable | Valeurs | Rôle |
| --- | --- | --- |
| `AGENT_MODE` | `mock`, `local`, `aws` | `mock` : simulateur en mémoire du contrat; `local` : `LOCAL_AGENT_URL`; `aws` : `InvokeAgentRuntime`. |
| `LOCAL_AGENT_URL` | `http://127.0.0.1:8080/invocations` | Runtime `profile` lancé en local. |
| `AWS_REGION` | `us-east-1` | Région. |
| `ALPHAFORGE_PREFIX` | `alphaforge_sandbox` | Préfixe des runtimes; l'ARN de `<préfixe>_profile` est trouvé par son nom (`ListAgentRuntimes`). |
| `ALPHAFORGE_STATE_MACHINE` | `alphaforge-sandbox-collecte` | Machine de collecte, trouvée par son nom (`ListStateMachines`). |

## 8. Volet finance (proposition, hors version 1)

Pour le portefeuille guidé (A3, agents d'analyse, Judge), à valider par l'équipe. Rien ne change pour les
runtimes de la version 1. Les schémas Pydantic sont dans `app/agents/src/alphaforge/finance/contracts/` :

| Contrat | Produit par | Lu par | Rôle |
| --- | --- | --- | --- |
| `InvestorProfile` (v0.1) | profil (A1, A2), via un adaptateur de la base OKF du client | compilateur F1 | la personne, sans aucun poids ni cible de performance |
| `PolicySpec` (v0.2-draft) | F1 (`risk_levels.yaml`) | F2 optimiseur, F3 analyses, F4 Judge | le mandat : limites nommées (`rule_id`, `derived_from`) |
| `Decision`, `Fact`, `TraceEvent`, `ConstraintCheck` (v0.1) | A3 et Judge | interface, explication, audit | tout nombre affiché est un `Fact` sourcé, relié à un `TraceEvent` ; un énoncé ne peut citer que des faits existants |

- Le contrôle des plafonds (`alphaforge.finance.portfolio.check`) est déterministe et sans paramètre de dérogation.
- Les appels LLM du volet finance passent par `alphaforge.finance.llm` (rejeu enregistré, clé sha256). Le Guardrail
  est toujours référencé par une version numérotée, jamais `DRAFT`.
- `TraceEvent.otel_trace_id` relie chaque étape à sa trace OpenTelemetry (X-Ray, JSONL local).

