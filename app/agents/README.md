# AlphaForge AI : agents Python (AgentCore Runtime)

Un seul code Python sert tous les runtimes AgentCore décrits dans `app/CONTRACTS.md`. La variable `AGENT_ROLE`
choisit le point d'entrée :

| `AGENT_ROLE` | Agents | Rôle |
| --- | --- | --- |
| `profile` | questionnaire déterministe, A1 `createProfile-Agent`, A2 `AnalyseExistingPortfolio-Agent` | Profil investisseur en cinq dimensions, portefeuille existant, complétude, traces, SSE. |
| `press` | A4 | Actualités datées (communiqués Newswire.ca et PR Newswire, GDELT) vers `staging/<run_id>/press/`. |
| `data` | A5 | Séries et cours datés (Banque du Canada Valet, FRED, Yahoo Finance) vers `staging/<run_id>/data/`. |
| `supervisor` | A6 | Contrôle ce qui est arrivé dans `staging/<run_id>/` et écrit les documents OKF sous `general/`. |
| `router` | A0 | Recherche par experts : choisit les sujets d'une question, puis rédige la synthèse finale (section 11). |
| `expert` | E1 à E7 | Expert de sujet : lance lui-même n chercheurs, une session AgentCore chacun, et met en attente leurs constats. |
| `researcher` | chercheur | Une mission par session : cherche dans les hôtes de ses paquets et consigne des constats par localisateur. |

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
    data/long/                   données longues 1926-2026 du moteur de backtest (catalogue versionné, parquets non)
    finance/backtest/            moteur de backtest mensuel (alphaforge.finance.backtest)
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
      http.py, fetchers.py       sources publiques sans clé, hôtes en liste blanche, User-Agent déclaré
      press.py, data.py          A4 et A5
      supervisor.py              A6 : contrôles du code, revue éditoriale, documents OKF, index général
      staging.py, service.py     éléments collectés, tâche asynchrone et marqueur _done.json
  tests/                         pytest, sans réseau ni AWS (modèle scripté pour la vraie boucle Strands)
app/knowledge/general/methodologie/   documents de méthodologie versionnés (poussés sous general/ par Terraform)
app/knowledge/general/notions/        notions financières (Financial Concept)
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

### Recherche par experts en local

Sans `ALPHAFORGE_RESEARCHER_NAME` ni `ALPHAFORGE_RESEARCHER_ARN`, un expert lance ses chercheurs dans des fils du même
processus, avec le même magasin : toute la chaîne tourne sur un poste.

```sh
AGENT_ROLE=expert ALPHAFORGE_STORE=local PORT=8084 uv run python main.py
curl -s 127.0.0.1:8084/invocations -H 'content-type: application/json' \
  -d '{"action":"research","run_id":"local-2","subject":"E2","mode":"sweep","depth":"quick"}'
# staging/local-2/experts/E2/_done.json, puis A6 :
curl -s 127.0.0.1:8083/invocations -H 'content-type: application/json' -d '{"action":"curate","run_id":"local-2"}'
```

Les paquets de sources, le registre des hôtes et les sujets sont dans `src/alphaforge/research/packs.py`; un hôte
nouveau n'entre dans un paquet qu'après la lecture humaine de sa licence (les hôtes proposés par les chercheurs
restent en quarantaine, `staging/<run_id>/supervisor/quarantine.json`).

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
les parquets et `raw/` de `alphaforge/data/long/` s'ils existent localement, retire `__pycache__` et `.pyc`, fixe les droits (644 fichiers, 755 dossiers et exécutables) et produit :

- `<out_dir>/agents.zip` : environ 32 Mo compressé, 70 Mo décompressé (limites vérifiées : 250 Mo et 750 Mo);
- `<out_dir>/knowledge/` : les fichiers `**/*.md` de `app/knowledge/general/`, à pousser sous `general/`.

Le runtime démarre avec `python main.py` (point d'entrée `["main.py"]`, sans `opentelemetry-instrument`).

## Variables d'environnement

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `AGENT_ROLE` | `profile` | `profile`, `press`, `data`, `supervisor`, `router`, `expert` ou `researcher`. |
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
| `query1.finance.yahoo.com` | A5, A2 | Graphique quotidien d'un titre absent du jeu de départ. Le robots.txt de l'hôte interdit tout : exception assumée par l'équipe, faute d'alternative officielle gratuite. |
| `api.gdeltproject.org` | A4 | GDELT DOC 2.0, filtre `sourcelang:french` ou `english` (au plus une requête toutes les six secondes). |
| `www.newswire.ca` | A4 | Communiqués d'émetteurs (Cision/CNW), flux RSS général et services financiers. |
| `www.prnewswire.com` | A4 | Communiqués d'émetteurs (Cision), flux RSS des services financiers. |

Seuls ces hôtes sont joignables, en HTTPS, redirections comprises; les adresses sont construites par le code. Le
User-Agent déclare le robot, `AlphaForgeResearchBot/0.1 (+https://github.com/sf-bit24/alphaforge-polyfinances-2026)`,
sans renseignement personnel; FRED ne reçoit `curl/8.0` qu'en repli, une seule fois, s'il refuse ce User-Agent. Aucun
filtre n'est contourné : un 403, un 429 ou une coupure remonte comme erreur et l'agent passe à une autre source.
`feeds.finance.yahoo.com` et `news.google.com` ne sont plus lus, leur robots.txt interdisant les chemins utilisés
(vérifié le 2026-11-15). Des communiqués, A4 ne garde que les métadonnées (titre, lien, émetteur, dates, symboles) et
son propre résumé : l'extrait RSS sert au résumé puis est jeté.

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
| `finance/backtest/` | Moteur de backtest mensuel 1926-2026 (fenêtres, stratégies ex-ante, ORACLE, sélection robuste, walk-forward, traces) ; données longues dans `data/long/`. Voir ci-dessous. |
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

### Moteur de backtest (`finance/backtest/`)

`alphaforge.finance.backtest` simule des stratégies d'allocation sur des fenêtres historiques mensuelles (1926-2026)
et écrit une trace JSON par exécution (hash des données et du moteur, graine, période, résultats). Simulation
seulement. Il dépend du groupe `finance` (numpy, pandas, scipy, pyarrow), pas des dépendances de base. Les parquets de
`src/alphaforge/data/long/` ne sont pas versionnés (licences yfinance, Moody's, OCDE) : on les reconstruit avec le
groupe `backtest-data`. Détails : [`src/alphaforge/finance/backtest/README.md`](src/alphaforge/finance/backtest/README.md),
sources : [`src/alphaforge/data/long/SOURCES.md`](src/alphaforge/data/long/SOURCES.md). Les études par persona et leurs
rapports ne sont pas dans l'app (Brain `references/backtest/`, scripts archivés au commit `597d00b`).

```sh
uv run --group finance --group backtest-data python -I -m alphaforge.finance.backtest.build_data  # parquets dans data/long/
uv run --group finance python -I -m alphaforge.finance.backtest.run --profile example
uv run --group finance pytest tests/finance          # tests du moteur et du volet finance
```

Sans le groupe `finance` (CI), les tests du moteur sautent (`pytest.importorskip`) ; sans les parquets, ceux qui
lisent les données sautent aussi, avec la commande de reconstruction en raison.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `ALPHAFORGE_BT_DATA` | `src/alphaforge/data/long` | Données traitées du moteur (et `raw/` des téléchargements). |
| `ALPHAFORGE_STARTER_DIR` | `src/alphaforge/data/starter` | Jeu de départ lu par `build_data`. |
| `ALPHAFORGE_BT_PROFILES` | `finance/backtest/profiles` | Dossiers des profils YAML (séparés par `os.pathsep`). |
| `ALPHAFORGE_BT_RESULTS` | `./backtest-results` (répertoire courant, ignoré par git) | Traces des exécutions. |
