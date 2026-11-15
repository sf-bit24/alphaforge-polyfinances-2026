# Proposition : mesure de contrôle `PROB_LOSS` (pour F1 et F4)

Proposition du volet E (intégration de l'outil `scenario_risk`), 2026-11-14. Statut : **à valider par les
propriétaires de F1 (compilateur de mandat) et de F4 (Judge)**. Aucun fichier de F1 ou F4 n'est modifié ici.
Simulation seulement, jamais un conseil.

Référence lue (lecture seule) : `origin/feat/finance-integration`, `app/agents/src/alphaforge/finance/`
(`contracts/policy.py`, `portfolio/compile.py`, `portfolio/judge.py`). La spécification suit la forme de
`CVAR12M` : même `Limit`, même `ConstraintCheck`, mêmes noms de champs.

## 1. Définition

> `PROB_LOSS` : P(perte cumulée du portefeuille à l'horizon H > L) ≤ α

- **L** (perte, fraction du montant investi) et **H** (horizon, années) décrivent l'événement;
- **α** (probabilité maximale tolérée) est la borne `Limit.max`;
- la probabilité est lue dans la **table de scénarios précalculée** (outil `scenario_risk`,
  `app/agents/src/alphaforge/scenarios/tool.py`), avec son IC à 90 %, son `model_id` et son `data_sha256`.

**Aucune valeur de α, L ou H n'est fixée par ce document** : ce sont des entrées de F1, dérivées du profil
(perte tolérée déclarée, horizon du projet, capacité de perte) et validées par l'équipe.

Mesure de **contrôle seulement** (comme `CVAR12M` et `STRESS_2022`) : l'optimiseur F2 ne l'utilise pas.

## 2. Changements proposés au contrat `policy.py` (tous optionnels, rétrocompatibles)

```python
RiskMeasure = Literal["CVAR", "CDAR", "VOL", "MDD", "CVAR12M", "STRESS_2022", "PROB_LOSS"]
# PROB_LOSS : contrôle seulement (Judge). P(perte cumulée à l'horizon > L) lue dans la table de scénarios
# précalculée (outil scenario_risk), IC 90 % ; la limite porte sur la borne haute ci_hi (prudence).
CONTROL_ONLY_MEASURES = frozenset({"CVAR12M", "STRESS_2022", "PROB_LOSS"})


class Selector(_Strict):
    ...
    measure: RiskMeasure | None = None
    loss_level: float | None = Field(default=None, gt=0, le=1)  # PROB_LOSS : L, fraction du montant
    horizon_years: int | None = Field(default=None, ge=1)       # PROB_LOSS : H, années


class ScenarioBlock(_Strict):
    """Bloc de la table de scénarios qui représente un actif de l'engine (ex. XIU.TO -> CA_EQ)."""
    block: Literal["CA_EQ", "US_MKT", "BONDS", "CASH", "GOLD", "CRYPTO"]
    source: str                                   # justification du rapprochement
    status: Literal["HYPOTHESE"] = "HYPOTHESE"


class PolicySpec(_Strict):
    ...
    scenario_blocks: dict[str, ScenarioBlock] = Field(default_factory=dict)  # requis si une limite PROB_LOSS
    scenario_family: Literal["CAD77", "CAD71", "USD1926"] = "CAD77"          # cohérente avec currency
    scenario_model_id: str | None = None          # None : modèle par défaut du manifeste de la table
    scenario_run_id: str | None = None            # None : scenarios/latest.json ; sinon run figé (rejeu)
```

Validation ajoutée à `Limit._bounds` : si `selector.measure == "PROB_LOSS"`, `loss_level` et `horizon_years`
sont requis et `0 < max < 1`; sinon ils doivent être absents. Validation ajoutée à `PolicySpec._coherence` :
une limite `PROB_LOSS` exige que chaque actif de `universe` hors `excluded` ait une entrée `scenario_blocks`
(ou un `history_proxies[a].proxy` qui soit déjà un bloc : `US_MKT`, `CA_EQ`…), et `scenario_family` en CAD si
`currency == "CAD"`.

`compile.py` n'a rien à changer d'autre : `RiskRow(rule_id, measure, hi=limit.max, limit)` porte déjà α, et
`limit.selector` porte L et H.

## 3. Évaluation par le Judge (`judge.check`, branche `rr.measure == "PROB_LOSS"`)

1. **Poids par bloc** : `w_bloc = Σ_a w_a` pour les actifs `a` rattachés au bloc (`scenario_blocks`, sinon le
   proxy déclaré). Le rattachement est une **HYPOTHESE** (un FNB n'est pas l'indice du bloc).
2. **Appel de l'outil** (déterministe, sans LLM), une seule instance par processus pour garder le cache :

   ```python
   from alphaforge.scenarios.tool import compute_scenario_risk
   from alphaforge.scenarios.tool_table import ScenarioTableLoader

   table = ScenarioTableLoader(store, run_id=policy.scenario_run_id).load()
   res = compute_scenario_risk(
       table, weights=w_blocs, horizon_years=sel.horizon_years,
       loss_threshold_cad=sel.loss_level, amount_cad=1.0,       # L en fraction : montant unitaire
       family=policy.scenario_family, model_id=policy.scenario_model_id,
   )
   ```
3. **Valeur comparée à α : la borne haute `ci_hi` de l'IC à 90 %** (prudence, suggestion retenue). La valeur
   centrale et la borne basse sont citées dans l'explication, mais seule `ci_hi` décide :

   | Situation | `violated` | Lecture |
   | --- | --- | --- |
   | `ci_hi ≤ α` | non | même la borne prudente respecte α |
   | `value ≤ α < ci_hi` | **oui** | l'IC chevauche α : on ne peut pas exclure le dépassement |
   | `value > α` | oui | dépassement au centre de l'IC |
   | outil en refus (hors grille, table absente, sha invalide) | **oui** | non vérifiable = refus prudent (comme `STRESS_2022` sans 2022) |

   `active = abs(ci_hi - α) <= TOL`. La règle de l'outil garde ce sens prudent partout :
   - **seuil** : L est arrondi **vers le bas** au palier `p_loss_gt_XX` disponible, donc P lue ≥ P(perte > L);
     si L est sous le plus petit palier, la probabilité lue est un minorant : l'outil le signale
     (`threshold.is_lower_bound`) et le Judge doit alors traiter le contrôle comme **non vérifiable** (violé);
   - **horizon** hors grille : l'outil renvoie l'horizon inférieur et l'horizon supérieur (`upper_horizon`);
     le Judge prend `max(ci_hi_inférieur, ci_hi_supérieur)`, sans interpoler;
   - **mélange** : grille la plus proche en distance L1, refus au-delà de 0,10 (`MAX_L1_DISTANCE`, à valider);
     la distance est un `Fact` cité dans la description.
4. **Désaccord entre modèles** : la décision porte sur `scenario_model_id` (ou le modèle par défaut). Si un autre
   modèle de la table donne `ci_hi > α`, le Judge ajoute un **avertissement non bloquant** (`warnings`) qui le
   nomme. Variante plus stricte, au choix de F1 : décider sur le maximum des `ci_hi` de tous les modèles.
5. **Fact et ConstraintCheck**, avec l'aide `add(...)` existante, sans nouveau champ :

   ```python
   add(f"{rr.rule_id}:max",
       rr.limit.description_fr or f"P(perte > {L:.0%} sur {H} ans), borne haute IC 90 %",
       rr.limit.derived_from, rr.hi,
       ci_hi if res["status"] == "ok" else -1.0,          # -1 = non vérifiable, comme STRESS_2022
       "probabilité (fraction)", violated, active, rr.limit.blocking,
       proc,                                              # voir ci-dessous
       "HYPOTHESE")                                       # modèle + rattachement des actifs aux blocs
   facts.extend(Fact.model_validate(f) for f in res["facts"])   # value, ci_lo, ci_hi, distance L1, autres modèles
   ```

   `proc` (champ `Source.processing`) : `scenario_risk <model_id>, famille <family>, mix <mix_id> (L1 <d>),
   horizon <H_utilisé> ans, palier <bucket_metric>, run <run_id>, table sha256 <sha>, code <code_sha>,
   ajusté jusqu'à <fitted_through>`. Le `TraceEvent` de l'outil (`res["trace_event"]`) devient un enfant de la
   trace du Judge (`parent_id = trace_id` du Judge) : la conclusion se retrace jusqu'au fichier de la table et au
   code qui l'a produit.

   Les `Fact` de l'outil sont déjà au format `contracts/decision.py` (mêmes clés, `extra="forbid"`), avec des
   identifiants stables (`scn.<model>.<famille>.<mix>.<H>y.<base>.<métrique>[.ci_lo|.ci_hi]`).

## 4. Ce que `PROB_LOSS` ajoute à `STRESS_2022`, `MDD` et `CVAR12M`

| Mesure | Question | Données | Incertitude affichée |
| --- | --- | --- | --- |
| `STRESS_2022` | Combien ce portefeuille réel a-t-il perdu en 2022 ? | un épisode, tickers réels (FAIT) | aucune : un seul chemin |
| `MDD` (historique long) | Pire baisse sur le chemin historique observé | une trajectoire, proxys (HYPOTHESE) | aucune : un seul chemin |
| `CVAR12M` | Perte moyenne des 5 % pires années glissantes | historique long, fenêtres chevauchantes | aucune (bootstrap en recherche) |
| `PROB_LOSS` | À quelle fréquence perd-on plus de L à l'horizon H du projet ? | distribution de trajectoires simulées (modèle) | IC à 90 % + écart entre modèles |

- Les trois premières décrivent **ce qui s'est passé**; `PROB_LOSS` décrit **la fréquence** d'un événement à
  l'horizon de l'investisseur, ce que demandent les profils à horizon court (Robert, 3–5 ans).
- Elles se complètent : `STRESS_2022` reste le test concret, explicable en une phrase; `PROB_LOSS` dit si 2022
  était un cas rare ou fréquent pour ce mélange. Garder les deux : un modèle peut sous-estimer un épisode réel,
  et un épisode réel ne dit rien de sa fréquence.
- `PROB_LOSS` porte sur la perte **à l'horizon**, pas en cours de route : une chute de 30 % suivie d'une reprise
  n'y apparaît pas. Pour la tolérance émotionnelle à la baisse, une mesure sœur `PROB_MDD` (même forme, métrique
  `p_mdd_gt_XX` de la table) est possible; non proposée ici tant que F1 n'en a pas besoin.

## 5. Ce que F1 doit fournir

- α, L, H par profil (et `derived_from`, par exemple `profile.loss_tolerance` / `profile.horizon`);
- `scenario_blocks` pour chaque actif de l'univers (source datée, `HYPOTHESE`);
- `scenario_family` cohérente avec la devise du mandat; `scenario_run_id` figé pour la démonstration.

## 6. Limites connues

- Le Judge dépend d'une table précalculée : si elle manque, `PROB_LOSS` est violée (refus prudent). Le Judge
  doit donc l'activer seulement quand la table est publiée (`scenarios/latest.json`).
- Une grille de mélanges (pas de 5 %) et d'horizons discrets : contrôle approximatif, rendu prudent par les
  arrondis ci-dessus, jamais extrapolé.
- La validation hors échantillon des modèles (volet C) doit être publiée dans le manifeste (`models[].validation`)
  pour être citée; sans elle, l'outil le dit dans les limites de l'explication.
