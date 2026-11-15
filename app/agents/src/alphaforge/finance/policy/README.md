# policy_compiler — F1 : InvestorProfile -> PolicySpec

Compilateur **déterministe** du profil investisseur en mandat `PolicySpec 0.2.0-draft`, selon
`app/agents/src/alphaforge/finance/policy/risk_levels.yaml` v0.2.0, qui reste le moteur de référence. Simulation seulement, jamais un conseil.

Il porte en code de bibliothèque la logique de `app/agents/scripts/calibration/review/expand.py` (`emit`) et de
`persona_v02.py`. Les scripts de revue ne sont pas importés.

## API

```python
from alphaforge.finance.policy import compile_profile, CompileResult, SpecificRequest, QuestionnaireScores

res = compile_profile(
    profile,
    as_of,
    request=None,
    yaml_path=None,
    universe=None,
    asset_classes=None,
    emphasis_path=None,
    questionnaire=None,
)
res.policy  # PolicySpec validé ; None si decision_kind ∈ {"incomplet", "protection"}
res.limits  # les Limit, toujours présentes, même quand policy est None
res.level, res.level_from_R, res.R, res.capacity, res.tolerance, res.l_star, res.e_cap, res.horizon_years
res.decision_kind  # None | "position_attente" (INCOMPLETE, mandat plafonné) | "incomplet" | "protection"
res.emphasis  # {"timeline","risk","diversity","constraints"} -> poids, somme 1 (emphasis.yaml)
res.emphasis_rules  # ids des règles d'emphase déclenchées
res.trace  # [{rule, inputs, output, yaml_path}] pour chaque nombre dérivé
res.missing_defaults  # valeurs prudentes appliquées (aussi dans PolicySpec.missing_defaults)
res.buckets  # seaux prudents par objectif, réserve de retraits, poche liquide
res.request  # RequestView : sandbox_max, single_name_max, crypto_max, applicable_max, outside_policy
res.policy_with_request()  # PolicySpec + sat.sandbox, pour optimiser « avec la demande »
res.near_cutoff  # R à moins de levels.hysteresis d'une coupure (information pour le re-profilage)
```

F1 n'approuve **jamais** une `SpecificRequest(ticker, amount_cad | weight, kind="buy")`. Il expose les
plafonds qui la visent (bac à sable, titre individuel, crypto, exclusions). `res.policy` ne contient pas
`sat.sandbox`, ce qui permet au graphe d'optimiser avec et sans la demande. Le Judge tranche ensuite.

## Chaîne de calcul (risk_levels.yaml v0.2)

1. **Statut.** Un statut `INCOMPLETE` vient du profil, d'un champ `must_have` manquant ou d'un
   `confidence < status.completeness_min`. Si `investable_wealth` manque, le résultat est `incomplet` et
   aucun mandat n'est émis. Sinon, c'est une `position_attente` : niveau au plus N2, sans titres
   individuels, crypto ni bac à sable. Un statut `PROTECTION` donne N0 et `protection`, sans mandat.
2. **Horizon du seau risque.** C'est le T minimal des objectifs qui ne relèvent pas d'une règle
   `buckets.rules`. Un retrait récurrent qui commence dans 5 ans ou moins crée une réserve N1 de
   `withdrawal_reserve_years` et repousse T d'autant.
3. **Capacité.** `C = 100·Π max(c_k, 0.05)^a_k` sur H, A, E, D, I et L, puis les plafonds durs : coussin
   de moins d'un mois, dette à coût élevé, besoin sous-financé. Le résultat est enfin `min(C,
   capacity_assessed)` : la capacité évaluée ne peut que baisser C.
4. **Tolérance.** On part de la formule PhD1 : moyenne pondérée par la confiance, désaccord, rétrécissement
   vers l'a priori de 25, composure. La règle du ménage prend ensuite le min des membres. Les biais ne
   font que resserrer.
5. **Score R.** `R = min(T, C) − pénalités de drapeaux`. Le niveau est le min de niveau(R),
   `horizon_cap(T)`, du plafond des seaux et du plafond du statut.
6. **Règle des dollars.** `l* = min(L_plan(e_max), l_declared, l_cap)`. `e_cap` est le e maximal de la
   grille de 5 % tel que `ENV_mdd(e) + daily_buffer ≤ l*`. Le niveau final est celui dont la bande
   contient `e_cap`.
7. **Budgets.** On prend les valeurs du niveau si `e_cap = e_max`, sinon `arrondi_sup(ENV(e_cap))`
   (`budgets_when_capped`).
8. **Satellites, composition, limites.** Une limite par entrée de `limits_template`. `risk.cdar_m` est
   ajoutée si le profil a une aversion aux pertes ou une composure inférieure à 40. Un biais de
   familiarité ajoute `bias.familiarite.employer`. Les exclusions viennent des contraintes légales
   bloquantes et des filtres de valeurs (`exclu`, ou `zone_grise` non tranchée).
9. **Autres champs du mandat.** `history_proxies`, `exposure_overrides`, `loss_bounds` et
   `policy_defaults` sont copiés du YAML et restreints à l'univers, qui est le starter (31 tickers réels).

**L'enveloppe ENV(e)** vient de `envelope_v02.yaml`. Ce fichier est généré par
`envelope.build_from_calibration(app/agents/tests/finance/fixtures/calibration)`, avec la même définition que `v02.py` et le
sha256 des CSV. Un test le régénère et le compare, et vérifie qu'il reproduit les budgets et les `L_plan`
de chaque niveau du YAML.

## Traçabilité

- `Limit.source` vaut `risk_levels.yaml@0.2.0#<chemin>`, par exemple `#levels.N3.cvar_m`,
  `#satellites.single_name ; #knowledge.debutant.single_name_cap`, ou
  `#levels.budgets_when_capped ; envelope_v02.yaml#equity_pct.35.cvar95_m`.
- `Limit.derived_from` indique le champ du profil ou la règle dont la limite découle.
- Chaque entrée de `res.trace` contient `{rule, inputs, output, yaml_path}`, par exemple `capacity.E`,
  `dollar_rule.l_star`, `dollar_rule.e_cap`, `limit.risk.cvar_m` ou `emphasis.risk.debts`. Le graphe peut
  en faire des `Fact` et des `TraceEvent`.
- Déterminisme : mêmes entrées, même JSON. `policy_id` contient le sha256 des entrées. `created_utc` vaut
  `as_of` à minuit UTC.

## Garanties testées (`tests/`, 54 tests, environ 6 s)

| Test | Ce qu'il vérifie |
|---|---|
| `test_personas.py` | Amira N4 (C 98,7, T 71,5, crypto 2 %). Mateo N2 (e_cap 35 %, budgets ENV(35) = persona_v02). Robert N0 (l* 0,133, e_cap 10 %, bac à sable 0, demande hors mandat). `example_N3` du YAML reproduit. Effet de la marge quotidienne (sans elle : Mateo seul N3, Robert N1). Validation, sources, déterminisme |
| `test_monotonicity.py` | Dégrader une entrée ne relève jamais le niveau ni un plafond de risque : horizon, perte déclarée, coussin, dette, connaissances, capacité évaluée, composure, drapeaux, membres du ménage. Les 4 biais ne font que resserrer. Règle du min du ménage. La capacité évaluée ne fait que baisser |
| `test_status_emphasis.py` | Cas INCOMPLETE, incomplet et PROTECTION (statut, ou règle des dollars quand l* < 0,1299). Seaux, emphase normalisée, exclusions, enveloppe |
| `test_adapter.py` | Questionnaire : agrégation par min par défaut, un seul chemin par fait, poche liquide, pas de double réserve, monotonie |
| `test_integration_optimizer.py` | `portfolio.optimizer.optimize(policy, as_of=2026-09-30)` rend `optimal` pour Amira et Robert, environ 1 s chacun. Le test n'est donc pas marqué `slow` |

**Hystérésis.** `levels.hysteresis` (3) ne sert qu'au re-profilage : un niveau déjà attribué ne change
que si R franchit la coupure de plus de 3 points. F1 compile sans état. Il signale seulement
`near_cutoff`, et c'est à l'appelant qui connaît le niveau précédent d'appliquer la règle.

## Emphase (`emphasis.yaml` v0.1.0)

Chaque lentille part d'un poids de base de 1. Les règles déclenchées ajoutent leur bonus, puis on
normalise. Ce sont des hypothèses de présentation : elles orientent l'explication et ne changent aucune
limite.

| Lentille | Règles (signal) |
|---|---|
| timeline | Objectif à moins de 5 ans, retrait récurrent, besoin à 5 ans ou moins |
| risk | Tolérance supérieure à la capacité (calculée ou drapeau), perte maximale déclarée, dettes, coussin insuffisant, biais émotionnel (FOMO, aversion) |
| diversity | ESG requis, filtres de valeurs, préférences thématiques, position d'au moins 10 % de W |
| constraints | Contraintes légales, titres de l'employeur, règles de l'utilisateur, demande hors mandat |

## Adaptateur du questionnaire (brain `product/questionnaire-profil.md`, a65a0b3, « A confirmer »)

`compile_profile(..., questionnaire=QuestionnaireScores(...))` traduit les sorties du questionnaire en
champs que F1 consomme déjà. La configuration est dans `questionnaire_adapter.yaml`. La règle du brain
« un même fait ne baisse pas les limites par deux chemins » est respectée ainsi :

| Sortie du questionnaire | Champ consommé par F1 | Pour éviter le double comptage |
|---|---|---|
| SF-00 M moins la poche liquide (OB-03, OB-06 < 3 ans, CT-09, SF-16 en zone de séquence) | `investable_wealth` = M_risque, et `buckets` reçoit `poche_liquide` (N0) | Les `covered_goal_ids` sortent de T et de q. Avec `sequence_reserve_years`, F1 n'ajoute pas sa propre réserve |
| L = min(L_cap, L_tol), en $ sur M_risque (SF-04, TR-03, TR-04, TR-19 ; SF-19) | `max_acceptable_loss_cad`, qui donne l_declared = L / M_risque dans l* | `max_acceptable_loss_pct` est retiré, car TR-03 est déjà dans L |
| Sous-scores de tolérance : déclarée (TR-01/03/05/06/10), scénarios (TR-02/18/19), révélée (TR-08/09), test (TR-12/13/14/16) | `tolerance_declared` (0–100), avec la confiance du brain (0,6 si un seul sous-score) | `tolerance_tested` est retiré, car le test est déjà dans l'agrégat |
| Score de capacité, 0–1, plafonds du brain inclus | `capacity_assessed` (×100), puis F1 prend min(C_faits, C_q) | Un min, jamais un cumul de pénalités |
| Complétude | `confidence`, puis le seuil `status.completeness_min` de 0,70 | — |

**Agrégation de la tolérance** (`tolerance.aggregation`) :
- `min` est la valeur par défaut : c'est le sous-score le plus bas qui compte. C'est un choix de
  conception aligné sur le questionnaire de l'AMF (« le plafond le plus bas l'emporte »), pas une
  obligation.
- `mean_minus_half_range` reprend la règle du brain : moyenne pondérée 0,3, 0,3, 0,2 et 0,2,
  renormalisée, moins 0,5 × (max − min). Elle reste défendable si elle est documentée.

Dans les deux cas, le risque effectif est `min(tolérance, capacité)`, comme l'exige 31-103CP.

D'autres champs du profil, remplis par l'agent de profil, sont consommés directement :
- SF-01 → `income.variability`, et une rente donne le statut de retraité ;
- SF-02 → `emergency_fund_months` ;
- SF-07 et SF-08 → `debts` (solde, taux) ;
- SF-10 → `pensions` ;
- SF-21 → `monthly_expenses` ;
- OB-01, OB-02, OB-06 et OB-11 → `goals` (priorité, `horizon_years`, `recurring_withdrawal`) ;
- CN → `knowledge_level` ;
- CB-01 et CB-04 → `biases[FOMO]`, et CB-06 à CB-17 → `biases` ;
- PR-01 → `preferences.esg_required` ;
- PR-13, souhait crypto supérieur à 0 → `preferences.tilts` contient « crypto » ;
- CT-03, CT-15, CT-16 et PR-04 → `preferences.value_filters[].per_ticker` ;
- titres de l'employeur → `employer_equity` ;
- contraintes → `legal_constraints`, `user_rules` et `consistency_flags`.

**Divergence : le stress 2022 ne sert pas à choisir le niveau.** Le brain retient « la bande la plus
élevée dont la perte au stress 2022 tient dans L / M_risque ». F1 ne le fait pas. Sur l'historique long,
2022 ne sépare pas les catégories. Les proxys XBB, XIU et SPY en CAD des portefeuilles BNI ont perdu
−11,2 % (défensif 70/9/21), −10,9 % (équilibré 40/18/42) et −10,7 % (actions 0/30/70), avec une
corrélation XBB–SPY de +0,68. La source est `/mnt/c/Users/User/Desktop/ecole/hackoton/analyse/relation-profils-actifs/quant/resultats.md`.
F1 choisit donc le niveau par la règle des dollars sur ENV_mdd, l'enveloppe longue (familles 1946, 1971 et 1977 à
2026. `STRESS_2022` n'est qu'un contrôle du Judge (`risk.stress_2022`).

## Écarts au YAML (et pourquoi)

1. **Seuil de PROTECTION.** Le texte `dollar_rule.protection` dit « L_plan(0) = 0,144 > l* ». F1 suit le
   code de la revue (`persona_v02.run`) : PROTECTION s'il n'existe aucun e tel que L_plan(e) ≤ l*,
   c'est-à-dire si l* < L_plan(10) = 0,1299, le minimum de la courbe. Avec le texte du YAML, Robert
   (l* = 0,133) serait en PROTECTION, alors que la revue conclut à N0.
2. **Garde de monotonie sur `budgets_when_capped`.** `min(arrondi_sup(ENV(e_cap)), budget du niveau)`.
   ENV n'est pas monotone sous 10 % d'actions : les obligations seules ont une perte plus forte que le
   mélange demi-cash (CVaR12m 3,8 % à e = 0 contre 2,5 % à e = 10). Sans cette garde, le cas
   PROTECTION (e_cap = 0) relevait les plafonds, ce que le test de monotonie a détecté. Dans tous les
   autres cas, la garde n'a aucun effet.
3. **Biais de surconfiance.** T = min(T sans biais, T avec biais). Les poids du YAML (w_tested 3)
   relèvent T quand le test est plus haut que la déclaration. Le min garantit que les biais ne font que
   resserrer.
4. **Membre du ménage.** Son `Score` est traité comme une tolérance déclarée seule : confiance, retour
   vers 25, et −5 faute de composure. Pour le conjoint de Mateo, on obtient T = 32, alors que la revue
   (« ménage = min ») prenait le min de chaque entrée et obtenait 44,4. Le niveau reste N2.
5. **Thème tech.** On arrondit au plancher de 0,25 % sur e_cap, comme `expand.py` et `example_N3`.
   `persona_v02` arrondissait à 0,5 % : Amira obtient 0,4075 au lieu de 0,405.
6. **Crypto pour un débutant.** `crypto_vehicle: etf_only` et le starter ne contient aucun FNB crypto :
   le plafond crypto vaut donc 0, et `crypto_mult` n'a pas d'effet.
7. **Seaux.** Interprétation : un objectif couvert par `buckets.rules` est rapporté dans `res.buckets`
   et sort du T du seau risque. Le mandat entier n'en prend le plafond que si tous les objectifs sont des
   seaux. Un `besoin_underfunded` est un besoin à 5 ans ou moins dont le montant dépasse W. Une dette
   est à coût élevé dès que son taux atteint `high_cost_rate`. Une hypothèque, reconnue à son libellé,
   est exclue de la dette de L.
8. **Bac à sable.** `sat.sandbox` n'est pas dans `res.policy`. Il est dans `res.request.limits` et
   `policy_with_request()`.
9. **Déduction crypto de `risk.cvar_m`.** `cvar_m − 0,55·w_crypto` peut monter d'environ 0,1 point quand
   l* baisse sans changer e_cap, car w_crypto baisse. Le budget total `cvar_m + 0,55·w_crypto`, lui, ne
   monte jamais. C'est ce budget que teste la monotonie.
10. **Constantes absentes du YAML sous forme de clé.** `mu_recovery = 0,04` (texte de
    `dollar_rule.l_cap`) est tracé comme tel.
11. **Valeurs prudentes manquantes.** Variabilité du revenu absente : exigence de coussin de 12 mois.
    Coussin absent : 0, donc plafond C ≤ 30. Connaissances absentes : `debutant`. Composure absente :
    −5. Dépenses absentes : bac à sable nul. Toutes figurent dans `missing_defaults`.
12. **`esg_required` n'est pas appliqué.** L'univers n'a pas de données ESG. Seuls les filtres
    `per_ticker` excluent.

## Questions ouvertes

1. La marge quotidienne de 4 points (`dollar_rule.daily_buffer`) fait passer Mateo de N3 à N2 et Robert
   de N1 à N0. C'est la décision humaine n°1 de la revue.
2. Les coupures de R et l'a priori de 25 sont ordinaux et non calibrés. Faut-il garder la formule PhD1
   ou passer à la composite du brain ? Les deux échelles de capacité (géométrique 0–100 contre moyenne
   0–1 plafonnée à 0,4 ou 0,5) ne sont pas encore réconciliées.
3. La règle 9 du brain (plafond = min(bande, souhait PR-13 ou PR-23, valeur tirée de L)) : les souhaits
   de plafond de l'utilisateur ne sont pas encore des champs d'`InvestorProfile`.
4. Un L non confirmé (SF-19) s'applique quand même, car il ne peut que resserrer. C'est noté dans
   `missing_defaults`. Le brain (RV-04) l'exclurait jusqu'à confirmation.
5. Plafond par secteur d'emploi (SF-12, abattement de 0,5 ou 0,75, 25 à 30 % par secteur) : seul le
   titre de l'employeur est plafonné, et seulement avec un biais de familiarité.
6. L'optimiseur garde lookback 597, mais avec les tickers réels sa fenêtre effective est 2018-10 →
   2026-09, limitée par ESGV. Le Judge rattrape sur les proxys longs.

## Références réglementaires

Vérifiées dans `/mnt/c/Users/User/Desktop/ecole/hackoton/analyse/relation-profils-actifs/00-cadre.md` :
- Règlement 31-103, art. 13.2(2)(c) : les six éléments de la connaissance du client (KYC).
- 31-103CP : le profil de risque reflète **le plus bas** de la volonté (tolérance) et de la capacité,
  d'où `R = min(T, C)`.
- Avis conjoint ACVM/OCRI 31-368 (2025-12-10) : règle d'agrégation documentée, questions distinctes pour
  la tolérance et la capacité, pondération qui empêche une capacité faible de produire un profil élevé,
  et résolution documentée des incohérences.
- Bulletin KYC de l'OCRI (septembre 2026).
- Questionnaire officiel de l'AMF : « le plafond le plus bas l'emporte ». C'est la justification du choix
  `aggregation: min`, un choix de conception et non une obligation.

## Lancer les tests

```bash
cd app/agents && uv sync --group dev --group finance && uv run pytest tests/finance/policy -q
```
