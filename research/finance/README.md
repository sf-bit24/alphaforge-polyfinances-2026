# research/finance — volet finance AlphaForge AI (simulation seulement)

> **Organisation depuis l'intégration au squelette de `master` (2026-11-14)** : le code vit dans
> `app/agents/src/alphaforge/finance/` (paquet `alphaforge.finance` : `contracts`, `portfolio`, `llm`,
> `observability`, `rules`) et ses tests dans `app/agents/tests/finance/`. Ce dossier ne garde que les
> scripts de recherche (`feasibility_levels.py`, `demo_trace.py`, `bedrock_smoke.py`), les réponses LLM
> enregistrées (`llm_records/`) et `infra/provision.py`, en attendant son portage en Terraform.
> Les chemins ci-dessous qui commencent par `portfolio/`, `llm/` ou `observability/` sont relatifs à
> `app/agents/src/alphaforge/finance/`.
>
> ```sh
> cd app/agents && uv sync --group dev --group finance && uv run pytest tests/finance
> PYTHONPATH=app/agents/src uv run --project app/agents python research/finance/feasibility_levels.py <risk_levels.yaml> <expand.py>
> ```
> Les tests qui lisent l'engine de backtest (`research/backtest`, branche `feat/backtest-engine`) sont
> sautés tant qu'il est absent.

Travail de recherche du volet finance. Le moteur de backtest et la couche de données longue
(1926-2026) vivent à côté, dans `../backtest/`, et ce dossier ne les modifie pas.

| Élément | Rôle | État |
|---|---|---|
| `rules/canada_2026.yaml` | Paramètres canadiens (CELI, REER, FERR, CELIAPP, REEE/SCEE, REEI, RPC, RRQ, PSV, SRG, SADC, gains en capital, hypothèses FP Canada/IQPF 2026). Chaque entrée a sa source officielle, sa date de récupération et son statut | 46 entrées, 44 vérifiées. Non vérifiées : retenue US de 15 % et exemption REER/FERR |
| `bedrock_smoke.py` | Test d'accès à Claude sur Bedrock (client Mantle) avec sortie structurée Pydantic : extraction citée d'un texte fictif, sans aucun calcul | Opus 5.5 OK (us-east-1) |
| `portfolio/` | **F2** `optimize()` : allocation sous les limites d'un `PolicySpec` (CVaR ou CDaR en programmation linéaire, variance Ledoit-Wolf ; limites VOL, CVaR, CDaR et MDD ; prix de chaque contrainte ; diagnostic d'infaisabilité ; `project()`). **F3** : `risk_report` (contributions exactes à la volatilité et à la CVaR), `diversification_report` (N effectif, clusters), `lookthrough_report`, `stress_report`, `horizon_report`. **F4** : `check()` du Judge (`ConstraintCheck`, `Fact` et `TraceEvent`, aucun paramètre de dérogation), `framed_alternative()` | 19 tests verts |
| `llm/` | **Déterminisme des appels LLM.** `llm_call()` passe par `bedrock-runtime` Converse (sortie structurée native, effort), en mode `live`, `record` ou `replay`. La clé sha256 couvre modèle, prompt, guardrail, effort, messages, outils, schéma, versions, nœud et tour. Le stockage est en écriture unique : `FileStore`, ou `DynamoS3Store` (DynamoDB avec écriture conditionnelle et S3 versionné). `ReplayModel` est un `BedrockModel` de Strands rejouable, qui rend aussi `structured_output` rejouable | Vérifié en réel sur Opus, Sonnet et Haiku 5.5 (us-east-1), y compris un agent Strands avec outil |
| `observability/` | **Traçabilité.** `telemetry` : un TracerProvider OpenTelemetry partagé avec Strands (spans `gen_ai.*`), exporté en JSONL local, vers X-Ray (OTLP signé SigV4) et vers la console ; décorateur `traced_tool` (empreintes sha256 des entrées et sorties) ; `log_event` vers JSONL et CloudWatch `/alphaforge/app`, corrélé au `trace_id`. `verify` : contrôle d'entrée par Guardrail ; vérificateur numérique **déterministe** qui exige que chaque nombre d'une phrase vienne des faits **qu'elle cite** ; ancrage Guardrail sur les faits rédigés en phrases. `audit` : journal des décisions chaîné par hash (local, S3 Object Lock, DynamoDB), avec `verify_chain()` | 11 tests |
| `infra/` | `provision.py` idempotent (`--teardown` pour supprimer) : S3 versionné avec Object Lock, CloudWatch Logs, rôle IAM, **journalisation complète des invocations Bedrock**, DynamoDB avec PITR, **Guardrail versionné**, Transaction Search. `outputs.json` contient les noms et ARN, aucun secret | Provisionné le 2026-11-14 |
| `demo_trace.py` | Démo de bout en bout sous une seule trace : entrée, F2, F4, alternative, explication rejouable, vérifications, `Decision`, audit | Vérifiée en réel |
| `llm_records/` | Réponses enregistrées, rejouées à l'identique pendant la démo (`ALPHAFORGE_LLM_MODE=replay`) | |
| `tests/` | Tests F2-F4 sur les données réelles de l'engine, avec un mandat **générique** (aucun seuil tiré d'une fiche persona) | |
| `../../contracts/` | Contrats partagés `InvestorProfile` / `Decision` / `Fact` / `TraceEvent` (proposition v0.1) | 11 tests verts |

## Environnement

```sh
cd research/finance
uv venv --python 3.11 ~/.venvs/alphaforge-finance   # disque Linux : démarrage rapide
VIRTUAL_ENV=~/.venvs/alphaforge-finance uv pip install numpy pandas scipy pyarrow pyyaml cvxpy clarabel skfolio pydantic pytest boto3 "anthropic[bedrock]"
```

## F2-F4 : utilisation

```sh
PYTHONPATH=.:research/finance ~/.venvs/alphaforge-finance/bin/python -m pytest research/finance/tests contracts/tests -q
```

- Entrée : un `contracts.PolicySpec`, produit par F1 et hors de ce paquet. Les seuils viennent de F1 ;
  ce paquet n'en fixe aucun.
- Données : l'engine de `research/backtest`, importé en lecture seule (`portfolio/_engine.py`).
- `[!]` Pas de rendement attendu sans prior sourcé : `max_utility` exige `expected_returns`.
- `[!]` Le drawdown dans l'optimiseur est arithmétique, une approximation convexe. Le Judge vérifie
  le drawdown composé de l'engine, et c'est son contrôle qui fait foi.
- `[!]` QQQ, SPY, XIU.TO et ESGV n'ont pas de look-through dans l'engine : la limite le signale, et il
  faut une `exposure_override` sourcée.
- `[!]` Les stress 2008, 2000 et 1973 sont « non couverts » par les vrais tickers, qui commencent vers
  2011. Il reste à ajouter des proxys longs, étiquetés HYPOTHESE.

## Déterminisme

- Claude 5.x n'accepte ni `temperature` ni `seed`, et sa pensée est toujours active. **Seul le rejeu
  d'une réponse enregistrée reproduit une sortie au bit près.**
- Les chiffres, les poids et le verdict viennent du code (F2 à F4) : ils sont identiques en `live`.
  Seule la formulation varie, et elle est figée en `replay`.
- En `replay`, les outils se réexécutent. Si les données ou le code ont changé, la clé ne correspond
  plus et l'appel lève `ReplayMiss` : la dérive est détectée.
- Il faut passer par `bedrock-runtime`, pas par Mantle : seul `bedrock-runtime` est couvert par le
  model invocation logging, Prompt Management et les application inference profiles.
- Sortie structurée : le schéma est rendu strict automatiquement (`additionalProperties: false`, tous
  les champs obligatoires), sinon Bedrock renvoie une 400.

## Traçabilité : ce qui est journalisé, et où

| Quoi | Où | Comment le retrouver |
|---|---|---|
| Chaque prompt et chaque réponse Bedrock, complets | S3 `bedrock-invocations/` et CloudWatch `/alphaforge/bedrock/invocations` | filtrer `requestMetadata.alphaforge_node` (les sessions Claude Code du compte y apparaissent aussi) |
| Spans des agents, des modèles, des outils et des vérifications | `traces/*.jsonl` en local, X-Ray et `aws/spans` (Transaction Search) | `trace_id` |
| Événements applicatifs (vérifications, appels LLM, décisions) | `traces/app.jsonl` et CloudWatch `/alphaforge/app` | même `trace_id` |
| Réponses LLM rejouables | `llm_records/` (ou DynamoDB `alphaforge-llm-replay` + S3 `llm-replay/`) | clé sha256 |
| Décisions, chaînées par hash | `traces/journal/<profil>.jsonl`, S3 `decisions/` (Object Lock) et DynamoDB `alphaforge-decisions` | `decision_id`, `verify_chain()` |
| Lien entre une `Decision` et sa trace | `TraceEvent.otel_trace_id` / `otel_span_id` | — |

Constats du 2026-11-14 :
- Sur le Guardrail, les filtres de données personnelles exigent `inputEnabled` et `outputEnabled` explicites, sinon ils restent inactifs. Le NAS écrit avec espaces exige une expression régulière.
- L'ancrage juge mal un JSON brut (score 0,36 sur des chiffres exacts). Rédigés en phrases, les faits donnent 0,99 sur une explication exacte et 0,17 sur des chiffres inventés.
- La pertinence ne sert que d'indicateur.
- L'endpoint OTLP de X-Ray exige Transaction Search vers CloudWatch Logs.

## Bedrock

- Profils d'inférence listés dans le compte (us-east-1, `bedrock-runtime`) : `us.` et `global.`
  pour Claude Opus, Sonnet et Haiku 5.5, Fable 5.2 et Amazon Nova 2.
- Test du 2026-11-14 avec le client **Mantle** (`AnthropicBedrockMantle`) :
  - `anthropic.claude-opus-5-5` : **OK** (environ 9 s, sortie structurée valide) ;
  - `anthropic.claude-sonnet-5-5` et `anthropic.claude-haiku-5-5` : **404 « model does not exist »**
    sur Mantle.
  Les sous-agents passent donc soit par Opus 5.5 à effort `low`, soit par les profils `us.` via
  `bedrock-runtime` (à tester).
- `[!]` Le venv sur `/mnt/c` (disque Windows) démarre Python en environ 100 s. Pour travailler
  vite, créer le venv sur le disque Linux (par exemple `~/.venvs/alphaforge-finance`).
- Identifiants : `source ../../../../aws_login.sh` dans un sous-shell (identifiants temporaires,
  jamais commités).

## Règles

- **Profils = entrées seulement.** Le moteur ne reprend jamais les allocations, cibles ou « faits
  de marché » des fiches persona.
- Le LLM extrait, structure et explique ; il ne calcule jamais un poids ni un chiffre.
- Toute valeur `status: unverified` du YAML est affichée comme HYPOTHÈSE, jamais comme FAIT.
