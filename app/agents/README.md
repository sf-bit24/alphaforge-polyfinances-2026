# AlphaForge AI : agents Python (AgentCore Runtime)

Un seul code Python sert les quatre runtimes AgentCore décrits dans `app/CONTRACTS.md`. La variable `AGENT_ROLE`
choisit le point d'entrée :

| `AGENT_ROLE` | Agents | Rôle |
| --- | --- | --- |
| `profile` | questionnaire déterministe, A1 `createProfile-Agent`, A2 `AnalyseExistingPortfolio-Agent` | Profil investisseur en cinq dimensions, portefeuille existant, complétude, traces, SSE. |
| `press` | A4 | Actualités datées (Yahoo Finance RSS, Google News RSS, GDELT) vers `staging/<run_id>/press/`. |
| `data` | A5 | Séries et cours datés (Banque du Canada Valet, FRED, Yahoo Finance) vers `staging/<run_id>/data/`. |
| `supervisor` | A6 | Contrôle ce qui est arrivé dans `staging/<run_id>/` et écrit les documents OKF sous `general/`. |

Principes appliqués partout : le code calcule, le modèle explique, chaque nombre cite sa source. Le cadre est une
simulation : aucune transaction réelle, aucun conseil personnalisé. Les questions de base viennent d'un questionnaire
versionné, sans modèle; le risque effectif est `min(tolérance, capacité)`; l'horizon n'est jamais déduit de l'âge ni
de la tolérance.

## Arborescence

```text
app/agents/
  main.py                        point d'entrée : python main.py (BedrockAgentCoreApp, aiguillage sur AGENT_ROLE)
  pyproject.toml, uv.lock        projet uv, Python 3.13
  scripts/package.sh             zip de déploiement direct AgentCore (linux/arm64)
  src/alphaforge/
    config.py                    variables d'environnement (CONTRACTS.md §1)
    server.py                    application, /invocations (JSON ou SSE), /ping
    errors.py, clock.py, trace.py, okf.py
    agentkit.py                  modèle Bedrock (Strands), boucle d'agent, traces, garde-fou
    starter.py                   lecture du jeu de départ
    data/starter/                jeu de données de départ des organisateurs (copie, sans build_dataset.py)
    store/                       magasin OKF : s3 (bucket chiffré SSE-KMS) ou local (dossier)
    profile/
      questionnaire.yaml         questionnaire bilingue versionné, règles et pondérations (à relire par le volet finance)
      questionnaire.py, rules.py niveau de connaissances, tolérance, capacité, risque effectif, complétude
      state.py, views.py         base OKF du client (profil.md, journal.md, index.md, traces/)
      a1.py                      A1 : questions de suivi (3 au plus par tour), mises à jour validées du profil
      a2.py, portfolio.py        A2 : extraction des positions; le code résout tickers, prix, change, expositions
      kb.py                      kb.list / kb.get, recherche dans la Knowledge Base générale
      service.py                 toutes les actions de CONTRACTS.md §3
    collect/
      http.py, fetchers.py       sources publiques sans clé, hôtes en liste blanche, User-Agent générique
      press.py, data.py          A4 et A5
      supervisor.py              A6 : contrôles du code, revue éditoriale, documents OKF, index général
      staging.py, service.py     éléments collectés, tâche asynchrone et marqueur _done.json
  tests/                         pytest, sans réseau ni AWS (modèle scripté pour la vraie boucle Strands)
app/knowledge/general/methodologie/   documents de méthodologie versionnés (poussés sous general/ par Terraform)
app/knowledge/general/societes/       chiffres publiés d'ATD et de CSU, relevés à la main (poussés de même)
```

## Lancer en local

Prérequis : [uv](https://docs.astral.sh/uv/) (il installe Python 3.13 au besoin). Les actions déterministes
(questionnaire, `profile.get`, `kb.*`, `settings.update`) n'appellent ni modèle ni AWS. A1, A2, A4, A5 et A6 appellent
Bedrock (`us-east-1`) avec les identifiants AWS de la session courante; une session ouverte par `aws login` demande
`botocore[crt]`, déjà dans les dépendances de développement.

```sh
cd app/agents
uv sync
AGENT_ROLE=profile ALPHAFORGE_STORE=local uv run python main.py      # http://127.0.0.1:8080
```

En local, le serveur écoute sur `127.0.0.1` (variable `ALPHAFORGE_HOST` pour changer) et le magasin est le dossier
`.local-kb/` (ignoré par git). Au démarrage, les documents de `app/knowledge/general/` absents du magasin local y sont
copiés, comme Terraform le fait dans S3.

```sh
curl -s 127.0.0.1:8080/ping
curl -s 127.0.0.1:8080/invocations -H 'content-type: application/json' -d '{"action":"health"}'
curl -s 127.0.0.1:8080/invocations -H 'content-type: application/json' -d '{"action":"session.start","locale":"fr"}'
# Flux SSE (événements trace, delta puis un seul result ou error) :
curl -sN 127.0.0.1:8080/invocations -H 'content-type: application/json' \
  -d '{"action":"followup.reply","client_id":"<client_id>","message":"Je veux acheter un condo dans 6 ans.","stream":true}'
```

Plusieurs rôles en même temps : un port par rôle avec `PORT`, et le même magasin local.

```sh
AGENT_ROLE=press      ALPHAFORGE_STORE=local PORT=8081 uv run python main.py
AGENT_ROLE=data       ALPHAFORGE_STORE=local PORT=8082 uv run python main.py
AGENT_ROLE=supervisor ALPHAFORGE_STORE=local PORT=8083 uv run python main.py

curl -s 127.0.0.1:8081/invocations -H 'content-type: application/json' \
  -d '{"action":"collect","run_id":"local-1","tickers":["RY.TO","XIU.TO","AAPL"]}'
curl -s 127.0.0.1:8082/invocations -H 'content-type: application/json' -d '{"action":"collect","run_id":"local-1"}'
# Quand staging/local-1/press/_done.json et staging/local-1/data/_done.json existent :
curl -s 127.0.0.1:8083/invocations -H 'content-type: application/json' -d '{"action":"curate","run_id":"local-1"}'
```

Les collecteurs acceptent tout de suite (`accepted: true`), travaillent en tâche asynchrone AgentCore (`/ping` répond
`HealthyBusy` pendant ce temps) et écrivent leur marqueur `_done.json`, même en cas d'erreur (`status: "error"`).
A6 écrit son marqueur avec `status: "ok"` même si A4 ou A5 a échoué ou n'a rien produit; seule une panne
d'A6 lui-même donne `status: "error"`. `run_id` doit
respecter `^[A-Za-z0-9_-]{1,64}$`. Une collecte est bornée : 30 actualités, 6 recherches, quelques minutes au plus.

## Tests et qualité

```sh
uv run pytest            # aucun appel réseau ni AWS
uv run ruff check
uv run ruff format --check
```

## Paquet de déploiement

```sh
sh scripts/package.sh <out_dir>        # par exemple infrastructure/infra/build/
```

Le script exporte les dépendances verrouillées (`uv export --frozen --no-dev`), les installe en roues
`aarch64-manylinux2014` pour Python 3.13 (`--only-binary=:all:`; il échoue si une roue manque, sans changer de
plateforme), place `main.py` et le paquet `alphaforge` (YAML et jeu de départ compris) à la racine du zip, retire
`__pycache__` et `.pyc`, fixe les droits (644 fichiers, 755 dossiers et exécutables) et produit :

- `<out_dir>/agents.zip` : environ 32 Mo compressé, 70 Mo décompressé (limites vérifiées : 250 Mo et 750 Mo);
- `<out_dir>/knowledge/` : les fichiers `**/*.md` de `app/knowledge/general/`, à pousser sous `general/`.

Le runtime démarre avec `python main.py` (point d'entrée `["main.py"]`, sans `opentelemetry-instrument`).

## Variables d'environnement

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `AGENT_ROLE` | `profile` | `profile`, `press`, `data` ou `supervisor`. |
| `ALPHAFORGE_ENV` | `local` | Environnement, renvoyé par `health`. |
| `ALPHAFORGE_RELEASE` | `dev` | SHA court du commit, renvoyé dans chaque réponse. |
| `ALPHAFORGE_REGION` | `AWS_REGION`, sinon `us-east-1` | Région des appels AWS. |
| `ALPHAFORGE_STORE` | `local` | `s3` en AWS, `local` en développement. |
| `ALPHAFORGE_BUCKET` | — | Bucket des bases OKF (obligatoire avec `s3`; chiffrement SSE-KMS par défaut du bucket). |
| `ALPHAFORGE_LOCAL_DIR` | `.local-kb` | Racine du magasin local. |
| `ALPHAFORGE_MODEL_ID` | `us.anthropic.claude-opus-5-5` | Profil d'inférence Bedrock de tous les agents. |
| `ALPHAFORGE_KB_ID` | — | Knowledge Base générale pour la recherche d'A1 (sans elle, la recherche ne renvoie rien). |
| `ALPHAFORGE_GUARDRAIL_ID` / `ALPHAFORGE_GUARDRAIL_VERSION` | — | Guardrail Bedrock appliqué à A1 et A2. |
| `PORT` | `8080` | Port HTTP. |
| `ALPHAFORGE_HOST` | `127.0.0.1` en local, `0.0.0.0` avec `s3` | Adresse d'écoute. |
| `ALPHAFORGE_LOG_LEVEL` | `INFO` | Niveau des journaux. |

## Modèle

Claude Opus 5.5 sur Bedrock (API Converse en flux, via Strands `BedrockModel`). La réflexion est toujours active :
aucun paramètre `thinking`, `temperature`, `top_p` ou `top_k` n'est envoyé. L'effort passe par
`output_config.effort` : `low` pour A1, A4 et A5, `medium` pour A2 et A6. A1 et A2 sont sans état : le contexte compact
du client est reconstruit à chaque tour, et leurs outils n'écrivent que des champs connus, typés et validés, avec la
provenance `a1:<tour>` ou `a2:<tour>`.

## Sources publiques (sans clé)

| Hôte | Utilisé par | Contenu |
| --- | --- | --- |
| `www.bankofcanada.ca` | A5 | API Valet (taux directeur, rendements, IPC, USD/CAD). |
| `fred.stlouisfed.org` | A5 | `fredgraph.csv` (taux, rendements, IPC, chômage aux États-Unis). |
| `query1.finance.yahoo.com` | A5, A2 | Graphique quotidien d'un titre absent du jeu de départ. |
| `feeds.finance.yahoo.com` | A4 | Titres d'actualité par symbole (RSS). |
| `news.google.com` | A4 | Recherche Google News (RSS). |
| `api.gdeltproject.org` | A4 | GDELT DOC 2.0 (au plus une requête toutes les six secondes). |

Seuls ces hôtes sont joignables, en HTTPS, redirections comprises; les adresses sont construites par le code. Le
User-Agent est générique et ne contient aucun renseignement personnel.

## Volet finance (`alphaforge.finance`, simulation seulement)

Construction et contrôle du portefeuille à partir d'un `PolicySpec` (sortie de F1, hors de ce paquet). Contrat :
`app/CONTRACTS.md` §9. Aucun seuil n'est fixé ici et aucune donnée des fiches persona n'est reprise.

| Module | Rôle |
| --- | --- |
| `finance/contracts/` | `InvestorProfile`, `PolicySpec`, `Decision`, `Fact`, `TraceEvent` (Pydantic). |
| `finance/portfolio/` | **F2** `optimize()` (cvxpy : CVaR, CDaR, variance Ledoit-Wolf ; prix duaux des contraintes ; diagnostic d'infaisabilité). **F3** contributions au risque d'Euler, clusters, look-through, stress, horizon. **F4** `check()` du Judge, déterministe, et `framed_alternative()`. |
| `finance/llm/` | `llm_call()` via `bedrock-runtime` Converse (sortie structurée native) en mode `live`, `record` ou `replay` ; clé sha256 canonique ; `FileStore` ou `DynamoS3Store` en écriture unique ; `ReplayModel` pour Strands. |
| `finance/observability/` | Spans OpenTelemetry GenAI (JSONL, X-Ray OTLP), `log_event` vers CloudWatch, vérificateur numérique par phrase, ancrage Guardrail, journal des décisions chaîné par hash (`verify_chain`). |
| `finance/rules/canada_2026.yaml` | Paramètres canadiens 2026, chacun avec sa source officielle et son statut. |
| `scripts/finance/` | `demo_trace.py` (démo de bout en bout sous une trace), `feasibility_levels.py` (faisabilité de la table de risque de F1), `bedrock_smoke.py`. |
| `tests/finance/` | Tests F2-F4 sur un mandat générique ; `fixtures/llm_records/` contient les réponses LLM rejouées. |

```sh
cd app/agents
uv sync --group dev --group finance && uv run pytest tests/finance
ALPHAFORGE_LLM_MODE=replay uv run --group finance python scripts/finance/demo_trace.py
```

Déterminisme : Claude 5.x n'accepte ni `temperature` ni `seed`. Les chiffres, poids et verdicts viennent du code ;
seule la formulation du LLM varie, et elle est figée en `replay`. Si le prompt, le Guardrail, les données ou le code
changent, la clé ne correspond plus et l'appel lève `ReplayMiss` : la dérive est détectée.

Ressources AWS de traçabilité (Terraform, `infrastructure/infra/traceability.tf`), lues dans l'environnement :

| Variable | Output Terraform | Contenu |
| --- | --- | --- |
| `ALPHAFORGE_GUARDRAIL_ID` / `_VERSION` | `guardrail_id` / `guardrail_version` | Guardrail `cadre` (sujets interdits, données personnelles, NAS, ancrage 0,75). |
| `ALPHAFORGE_TRACE_BUCKET` | `trace_bucket` | Object Lock : journal complet des invocations Bedrock, blobs du rejeu, `decisions/`. |
| `ALPHAFORGE_REPLAY_TABLE` | `llm_replay_table` | Index DynamoDB du rejeu LLM. |
| `ALPHAFORGE_DECISIONS_TABLE` | `decisions_table` | Tête de chaîne et maillons du journal des décisions. |
| `ALPHAFORGE_OTLP_XRAY=1` | — | Exporte les spans vers X-Ray (Transaction Search, indexation 100 %). |
