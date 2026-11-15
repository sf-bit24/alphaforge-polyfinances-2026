# Décisions A : profil réglementaire (tolérance, capacité, réponses inférées, ancrage de la catégorie)

> **Simulation uniquement, personas fictifs.** Ce document ne constitue pas un conseil financier personnalisé et
> n'entraîne aucune transaction. Il ne constitue pas non plus une évaluation réglementaire de convenance : il dit
> comment le **prototype** doit traiter les réponses de profil pour rester fidèle aux règles publiques. Toutes les
> résolutions sont des **propositions** que l'équipe doit valider. La construction de portefeuille (plafond d'or,
> règle de sélection, duration, etc.) est traitée par un autre rapport et n'est pas tranchée ici.

Chemins relatifs à `research/backtest/` sauf mention. Calculs nouveaux : `analysis/decisions/A_reglementaire_calculs.py`,
trace `results/decisions/A_reglementaire_calculs.json` [ADC] (moteur `4d3e707a3271717d`, données `008f122d5da4f8f7`,
dernier mois 2026-10). Les autres chiffres viennent des traces citées par `reports/croisement-amira-mateo-robert.md`
([WC] `results/croisement_analysis/will_vs_cap.json`, [STR] `stress_anchor.json`, [BNC] `bnc.json`, [REC] `reconcile.json`).
Sources web consultées le 2026-11-14, numérotées [S1] à [S15] (liste à la fin). `engine/`, `data/` et les rapports
existants ne sont pas modifiés.

## Tableau récapitulatif

| décision | résolution proposée pour le prototype | confiance |
|---|---|---|
| **D1 Robert, Q10** | Ne plus traiter « 5 % » comme une réponse : c'est une inférence. Q10 passe en **manquant**. Le profil est **incomplet** tant que Q10 n'est pas posée. En attendant, résultat **provisoire** sous l'a priori prudent de `risk_levels_v0.2` (niveau N1), avec les deux branches visibles : 5 000 $ → encaisse et conflit signalé ; 15 000 $ → `eq20_gold10`. L'encaisse à 100 % n'est acceptée que si Robert **confirme** 0 ou 5 %. | moyenne |
| **D1 Robert, Q3** | Q3 porte sur le retrait du tiers du capital, pas sur la date de retraite : réponse **manquante**, à poser. La retraite crée des retraits réguliers, donc deux poches : les retraits des premières années en horizon court, le reste en horizon long. Pas d'AMF 1 pour tout le capital. | moyenne à élevée |
| **D3 Mateo, Q10 contre la bande [40 %, 80 %]** | Règle : la tolérance confirmée l'emporte sur l'objectif, qui ne peut jamais relever le risque (31-103CP). Si 15 % est confirmé, c'est la bande qui cède (plancher abaissé ou écart documenté), et le système montre l'objectif irréaliste et les autres leviers (épargner plus, horizon, objectif réel plus bas, poche « études » séparée). Avant cela, Q10 est posée. L'ère de mesure doit suivre l'ancrage D9. | élevée sur la règle, moyenne sur l'application |
| **D4 Amira** | Oui : par défaut, la limite vaut **0,30**. La réponse « plus de 30 % » vaut sa borne basse, ce qui concorde avec le profil AMF 4. La « capacité 0,40 » est un budget tiré des données, pas une réponse d'Amira. 0,40 n'est utilisable qu'après confirmation explicite d'un scénario de 40 000 $ sur 100 000 $ et levée du plafond Q5, ou avec une justification écrite. | moyenne |
| **D9 Ancrage de la catégorie** | Abandonner « 2022 seul ». Ancrer sur la **pire perte d'une histoire longue à plusieurs épisodes**, dans la devise de l'investisseur, où 2022 reste un épisode. Contrôler par le p90 de la baisse maximale à l'horizon. Afficher en plus, sans s'en servir d'ancre, l'étiquette ACVM (écart-type sur 10 ans) et la pire année civile (présentation Vanguard). Cela concorde avec la v0.2 et avec le §6.1 du croisement, et contredit `questionnaire-profil.md` l. 178. | moyenne à élevée |
| **D11 Questions en démo** | Poser explicitement **Q10 en dollars sur une durée donnée**, Q11, ainsi que Q3 et une question de capacité pour Robert, la tolérance du conjoint pour Mateo, et Q5 sous forme de quiz pour Amira. Le montant de la perte s'affiche dans la question ; l'effet sur le portefeuille s'affiche **après** la réponse, jamais avant. | élevée |
| **Transversal : inféré ou déclaré** | Chaque champ porte une provenance (confirmé, déclaré, pré-rempli, inféré, manquant, hypothèse prudente). Une valeur inférée ne lie jamais comme un fait. Statut INCOMPLET et a priori prudent de catégorie, jamais une valeur extrême. Confirmation avant tout résultat « final ». Une incohérence bloque jusqu'à ce qu'elle soit résolue. Les écarts sont documentés. | élevée sur les principes, faible sur les poids chiffrés |
| Ouvert : abattement selon le secteur d'emploi (Tyler) | Aucun texte public ne donne 0,5 ni 0,75 : le seuil de concentration relève de la firme, qui doit le documenter. Prendre 0,5 par défaut (même valeur que `familiarite.employer_ticker_cap_mult` de la v0.2), afficher 0,75 en sensibilité et le marquer comme convention d'équipe. | faible sur la valeur, élevée sur la nécessité de la documenter |

**Ce qui a été vérifié et ce qui ne l'a pas été.** L'avis « 31-368 (déc. 2025) » de `00-cadre.md` **existe** : avis conjoint
du personnel des ACVM et de l'OCRI, publié le 10 décembre 2025 [S3]. Il confirme « le plus bas des deux ». La phrase
« épargner plus, dépenser moins, retarder la retraite » ne vient pas de 31-368 : elle vient de l'Instruction générale 31-103CP [S1].
**Non vérifiés en ligne** dans cette session :
- le « bulletin OCRI (sept. 2026) » (ciro.ca répond par une vérification Cloudflare) ;
- la page AMF « Votre profil d'investisseur » et son barème Q3 à Q12 (lautorite.qc.ca répond 403 ou Cloudflare). Le barème utilisé reste celui que l'équipe a lu (`00-cadre.md`) ;
- FINRA 2111 et le rapport FINRA sur le conseil numérique, ainsi que sec.gov (403) ;
- Grable et Lytton (1999), non trouvé.

Les références de `questionnaire-profil.md` ont été « citées de mémoire » (son en-tête le dit) ; celles de ce rapport ont
toutes été relues en ligne, avec la date de consultation.

---

## D1. Robert : la tolérance Q10 « 5 % » et l'ambiguïté de Q3

### 1. La question en mots simples
Le questionnaire de l'AMF demande quelle baisse temporaire on peut supporter. Personne n'a posé la question à Robert :
l'équipe a déduit « 5 % » de l'étiquette officielle « Faible à modéré ». Or, avec la règle « on garde le plus prudent de
ce que la personne *veut* et de ce qu'elle *peut* supporter », ce 5 % ne laisse que de l'argent liquide. Le liquide ne
baisse pas en dollars, mais il perd du pouvoir d'achat avec l'inflation. Faut-il garder ce 5 %, poser la vraie question,
ou faire autrement ? Seconde question : Robert prend sa retraite dans 3 à 5 ans, mais il ne retirera pas tout son argent
d'un coup. Son « horizon » est-il court ou long ?

### 2. Options
- (a) Garder 5 % : encaisse seule, et l'incohérence avec l'objectif est signalée.
- (b) Remesurer : poser Q10. Si la réponse est 15 %, la capacité 0,23 redevient la limite.
- (c) Deux poches : liquidités pour les premières années de retraite, et le reste sous la capacité.
- Pour Q3 : lecture littérale (horizon < 5 ans → AMF 1) ou lecture « retrait du tiers étalé au-delà de 5 ans » (AMF 4).

### 3. Preuves

| source | date | URL | citation | ce que ça prouve |
|---|---|---|---|---|
| [S1] ACVM, Instruction générale 31-103CP, art. 13.2 | consolidation du 2022-06-06 | osc.ca (voir [S1]) | « The risk profile for a client should reflect the lower of (a) the client's willingness to accept risk and (b) the client's ability to endure potential financial loss. » | La règle du minimum existe, mais elle s'applique à une tolérance et une capacité **mesurées**. |
| [S1] idem | idem | idem | Le processus doit inclure : « appropriately interpreting client responses to questions and not attributing inappropriate weight to certain answers » et « identifying clients that are more suited to placing their money in cash deposits or guaranteed products because they are unwilling or unable to accept the risk of loss of capital. » | L'encaisse à 100 % est un résultat **légitime**, mais seulement pour qui est *réellement* peu disposé ou peu capable. Donner tout le poids à une réponse qui n'a jamais été donnée, c'est le contraire. |
| [S1] idem, « Resolving conflicts » | idem | idem | « The questions at the source of this conflict should be revisited with the client. » | Reposer Q10 n'est pas une manipulation : c'est ce qu'il faut faire quand objectif et tolérance se contredisent. |
| [S1] idem | idem | idem | « We stress that KYC information must not be made to correspond or match with a security, account or portfolio or otherwise be manipulated to lead to a pre-determined outcome. » | On ne choisit pas la réponse de Robert pour obtenir un « beau » portefeuille. La réponse de démo doit être annoncée comme **scénarisée**, et l'autre branche doit rester visible. |
| [S2] ACVM, Règlement 31-103, art. 13.2(3.1) | consolidation du 2023-09-13 | osc.ca (voir [S2]) | « Within a reasonable time after receiving the information, a registrant must take reasonable steps to have a client confirm the accuracy of the information collected under subsection (2). » | Un profil n'est pas final sans confirmation. |
| [S3] ACVM et OCRI, avis 31-368 | 2025-12-10 | osc.ca (voir [S3]) | « Clients should provide specific input on both their risk tolerance and risk capacity. » | Une tolérance déduite d'une étiquette ne remplit pas cette exigence. |
| [S6] FSA (R.-U.), FG11/05 « Assessing suitability », note 4 | 2011-03 | fca.org.uk (voir [S6]) | Pour les clients orientés vers les dépôts en espèces : « Recognising the risks that inflation can erode the value of capital. » | L'encaisse a un risque, le pouvoir d'achat, qu'il faut expliquer. |
| [S13] SEC, Investor.gov, guide de répartition d'actifs | non datée | investor.gov (voir [S13]) | « The principal concern for investors investing in cash equivalents is inflation risk. » | Même constat aux États-Unis. |
| [S1] 31-103CP, liquidité et horizon | 2022-06-06 | idem | Le conseiller doit évaluer « whether, once the need materializes, the money will be withdrawn on a regular basis, such as once a month or once a year. » ; et il « has the responsibility to assess its feasibility and reasonableness relative to the client's liquidity needs, age, investment objectives… ». | L'horizon se juge sur le rythme réel des retraits, pas seulement sur la date de la retraite. Cela appuie la lecture non littérale de Q3. |
| [S8] Vanguard, « Asset allocation models » | données au 2025-12-31 | investor.vanguard.com (voir [S8]) | « When you're in retirement, you'll need some money for daily expenses, but other assets won't be touched for years. » | Pratique de l'industrie : un retraité a deux horizons, d'où deux poches. |
| [S14] Énoncé officiel, p. 7 | 2026 | PDF local | Robert : « Profil de risque Faible à modéré », « Horizon de placement 3 à 5 ans » ; il veut « Préserver son capital tout en maintenant un potentiel de croissance ». | Seuls faits officiels : une **fourchette** (faible à modéré, soit AMF 2 à 3, donc Q10 entre 5 % et 15 %) et un objectif de croissance. Le chiffre 5 % n'est pas un fait. |

### 4. Nos données
- Sous la capacité 0,23 : `eq20_gold10`, p10 réel +1,53 %/an, P(perte de pouvoir d'achat sur 4 ans) 6,5 %, pire baisse
  0,097 sur 46 fenêtres roulantes en CAD 1977+ [WC → `robert.robert_cad|rolling|capacite_0.23.robust`].
- Sous 0,05 : 1 stratégie éligible sur 19 (`cash_100`), p10 −0,98 %, P(perte réelle sur 4 ans) **30,4 %**
  [WC → `robert_cad|rolling|volonte_0.05`]. La lecture littérale de Q3 (AMF 1) donne exactement le même résultat.
- Même avec une lecture « sur 12 mois », 5 % ne laisse pas passer `eq20_gold10` : sa pire perte sur 12 mois vaut 8,05 %
  et sa pire année civile 6,16 % (2022), en CAD 1977+ [ADC → `q10_dollars`]. Avec 15 %, il passe sous toutes les lectures.
- En dollars, pour un montant fictif de 100 000 $ : Q10 = 5 % → 5 000 $ ; 15 % → 15 000 $ ; pire baisse historique de
  `eq20_gold10` ≈ 9 700 $ [ADC].
- **Incohérence interne à l'équipe** : `00-cadre.md` lit Q10 de façon *ordinale* (5 % → AMF 2 → BNC Conservateur, environ 30 %
  d'actions, pire épisode 15,3 % [STR]). Le croisement la lit de façon *cardinale* (5 % = baisse maximale permise → encaisse).
  Les deux lectures ne peuvent pas coexister. La v0.2 (`risk_levels_v0.2.yaml`) traite une tolérance manquante avec un
  `conservative_prior: 25`. Sur l'échelle R de 0 à 100 (coupures 15/30/45/60/75), cela donne **N1 « Prudent »** : 10 à 25 % d'actions, mdd 0,14.
  La v0.2 prévoit aussi le statut `INCOMPLETE` (niveau ≤ N2, aucun titre individuel, aucune crypto).

### 5. Résolution proposée pour le prototype
1. **Statut de Q10 : manquant, pas « 5 % (I) ».** C'est un écart assumé avec le croisement (§3), qui applique ce 5 % comme
   une volonté. Robert reste **INCOMPLET** (statut v0.2) jusqu'à la réponse. Le résultat affiché est marqué « provisoire ».
2. **Défaut provisoire** : l'a priori prudent de la v0.2 (N1), pas une limite cardinale de 5 %. Une valeur jamais donnée
   ne peut pas imposer le résultat le plus extrême, l'encaisse à 100 % (31-103CP : pas de « inappropriate weight »).
3. **En démo, poser Q10** en dollars, sur une durée précise et avec la même mesure que le moteur (baisse du sommet au creux). Par exemple :
   « Sur 100 000 $, quelle baisse temporaire pourriez-vous traverser sans changer votre plan : 0 $, 5 000 $, 15 000 $,
   30 000 $, plus ? ». La réponse est une **entrée fictive scénarisée** par l'équipe, affichée comme telle.
4. **Les deux branches restent visibles** dans « ce qui changerait la réponse » :
   - **5 000 $ confirmé** : encaisse et signal « objectif contre tolérance ». Texte à afficher : *« Avec une baisse acceptable de
     5 000 $, seule l'encaisse respecte votre limite dans nos simulations. Elle protège les dollars, mais pas le pouvoir
     d'achat : dans 30 % des périodes de 4 ans depuis 1977, elle a perdu face à l'inflation. Votre objectif de croissance
     n'est donc pas atteignable à ce niveau de risque. Les leviers possibles sont de travailler un peu plus longtemps,
     d'épargner davantage ou de prévoir des dépenses de retraite plus basses. Voulez-vous revoir votre réponse ? »*
     Le risque n'est jamais relevé en silence.
   - **15 000 $** : la capacité 0,23 redevient la limite, et `eq20_gold10` apparaît (pire baisse ≈ 9 700 $).
5. **Q3** : la poser telle quelle (« Dans combien d'années prévoyez-vous retirer au moins le tiers de ce montant ? »).
   En l'absence de réponse, on applique la découpe de `questionnaire-profil.md` (« la poche retraite est découpée ») et de
   la v0.2 (`withdrawal_reserve_years: 3`) : les retraits des premières années vont dans une poche courte, le reste prend
   l'horizon allongé. C'est l'option (c), qui rend Q3 littéral inutile.
- **Ce qui ferait changer** : Robert confirme 0 ou 5 % (alors (a) est la bonne réponse, et elle s'explique) ; il annonce un
  retrait important d'ici 5 ans (alors cette part va en poche courte) ; ou l'équipe adopte partout la lecture ordinale
  de l'AMF.
- **Qui valide** : l'équipe (réponse scénarisée de Robert, lecture cardinale ou ordinale) ; le compilateur F1 (a priori v0.2).
  Le jury verra les deux branches.

---

## D3. Mateo : Q10 « 15 % » contre la bande d'actions [40 %, 80 %]

### 1. La question en mots simples
Pour viser son objectif (ne pas perdre de pouvoir d'achat en 10 ans), l'analyse donne à Mateo 40 à 80 % d'actions. Mais
s'il ne supporte qu'une baisse de 15 %, même 40 % d'actions a dépassé cette limite dans environ une période sur trois de
l'histoire américaine longue. Quand l'objectif demande plus de risque que la personne n'en accepte, que disent les règles ?

### 2. Options
- (a) Garder 15 % et la règle inter-ères (`min_variance_60`).
- (b) Garder 15 % mais ne juger que l'ère CAD.
- (c) Abaisser le plancher de la bande.
- (d) Remesurer Q10.

### 3. Preuves

| source | date | URL | citation | ce que ça prouve |
|---|---|---|---|---|
| [S1] 31-103CP, « Resolving conflicts » | 2022-06-06 | osc.ca | « Registrants should not override the risk a client is willing and able to accept on the basis that the client's expectations for returns cannot otherwise be met given the risk profile associated with their KYC responses. » | L'objectif ne peut jamais relever le risque. Une bande d'actions tirée de l'objectif doit céder devant une tolérance confirmée. |
| [S1] idem | idem | idem | « If a client's goals or return objectives cannot be achieved without taking greater risk than they are able or willing to accept, alternatives should be clearly explained such as saving more, spending less or retiring later. » | Les leviers à afficher. Pour Mateo : épargner plus, allonger l'horizon si la date n'est pas rigide, ou accepter un objectif réel plus bas. |
| [S1] idem | idem | idem | « …the registrant should explain to the client that their need or expectation for a higher return cannot realistically be met, and as a result, the higher risk portfolio is unsuitable. » | Le prototype doit le *dire*, pas seulement le calculer. |
| [S6] FSA FG11/05, § 4.9 et 4.10 | 2011-03 | fca.org.uk | Mauvaise pratique : « a firm inappropriately overriding the risk it had established a customer was willing and able to take because the customer's needs could not be met » ; alternatives : « saving more, spending less, retiring later or taking more risk ». | Même règle au R.-U. Nuance : le R.-U. cite aussi « prendre plus de risque », mais *choisi par le client après discussion* ; le texte canadien ne le cite pas. |
| [S3] avis 31-368 | 2025-12-10 | osc.ca | « …a client's overall risk profile should reflect the lower of the two. If a registrant determines otherwise, the rationale should be clearly documented. » | Garder un plancher de 40 % qui viole 15 % n'est défendable qu'avec une justification écrite et visible. |
| [S3] idem | idem | idem | « …some firms collected risk tolerance, annual income and investment time horizon on only a combined basis for spouses and thus did not have adequate KYC information… » | Mateo est en couple : la tolérance du conjoint est une information manquante, pas un détail. |
| [S7] ESMA, lignes directrices sur la convenance MiFID II | 2022-09-23 | esma.europa.eu | Pour un groupe : « the firm should adopt the most prudent approach by taking into account… the most conservative investment objectives. » | Pratique européenne pour un ménage : le plus prudent des deux. La v0.2 fait de même (`household.min_tolerance`). |
| [S5] Règlement 81-102, annexe F, item 2(2)(b) | consolidation du 2025-07-16 | osc.ca | L'écart-type se calcule dans « the same currency in which the series or class is offered. » | Précédent réglementaire : mesurer le risque dans la devise de l'investisseur. Cela appuie l'ère CAD comme référence, l'ère USD longue servant de stress affiché. |

### 4. Nos données
- Sous la capacité 0,20 : `risk_parity_iv36`, pire p10 −0,15 % (CAD 3,81 %). Sous 0,15 : `min_variance_60`, pire p10 −0,42 %
  (CAD 2,06 %), 2 stratégies éligibles [WC → `mateo.capacite_0.20`, `volonte_0.15`].
- Le plancher `static_eq40` dépasse 0,15 dans **0 %** des fenêtres CAD, 28,6 % des fenêtres USD 1975+ et 37,4 % des fenêtres USD 1926+
  [WC → `mateo.volonte_0.15.breach_by_era`]. La tension dépend donc de l'ère choisie.
- BNC sous 0,15 : Pondéré [BNC]. Avec l'ancrage D9 : Prudent sur le pire épisode (limite 0,1498), Pondéré sur le p90 de la baisse
  maximale à 10 ans [STR → `CAD_bands.mateo_volonte`].
- Sous la v0.2 (enveloppe de 3 histoires, `daily_buffer` 0,04), `L_plan` vaut 0,178 en N1 et 0,13 en N0. Une limite confirmée de 0,15
  placerait donc la part d'actions maximale **entre 10 et 25 %**, bien sous la bande [40 %, 80 %]. Ce n'est pas recalculé ici
  (c'est l'affaire de F1 et du rapport de construction). Conséquence : sous la v0.2, l'inférence « modéré → 15 % » est encore plus
  déterminante que dans le croisement.

### 5. Résolution proposée pour le prototype
1. **Poser Q10** (comme pour D1), et poser la question de tolérance au **conjoint** (ou la marquer manquante). Le profil du ménage prend
   le minimum (v0.2, ESMA).
2. **Si 15 % est confirmé, la tolérance l'emporte** : la bande [40 %, 80 %] est une cible tirée de l'objectif, pas une contrainte qui
   prime. Deux sorties conformes :
   - option (c) : abaisser le plancher jusqu'à respecter 15 % sur l'ère de référence retenue en D9 ;
   - option (b) : garder la bande en jugeant sur l'ère CAD, mais **documenter et afficher** le dépassement en USD long.
   L'option (a) n'est acceptable que si elle respecte 15 % sur l'ère de référence.
3. **Message à afficher** en cas de conflit : *« Avec une baisse acceptable de 15 000 $ sur 100 000 $, le niveau d'actions que
   demande votre objectif a dépassé cette limite dans environ une période de 10 ans sur trois de l'histoire américaine
   longue. Nous ne relevons pas le risque pour atteindre l'objectif. Les options sont d'épargner davantage, de décaler
   l'échéance si elle n'est pas fixe, de viser un objectif réel plus bas, ou de séparer une poche "études" à court terme
   d'une poche à long terme. »*
4. Même ère de mesure que l'ancrage D9 : ne pas juger Mateo en CAD et la catégorie en enveloppe longue.
- **Ce qui ferait changer** : Mateo (et son conjoint) répondent 30 % (alors la capacité 0,20 s'applique : `risk_parity_iv36`, BNC
  Équilibré) ; la date des études n'est pas rigide ; le choix de l'ère en D9.
- **Qui valide** : l'équipe (ère, plancher) ; F1 pour la traduction en limite.

---

## D4. Amira : le profil AMF 4 implique-t-il une perte tolérée de 30 % ?

### 1. La question en mots simples
Amira dit accepter « plus de 30 % » de baisse, et l'analyse lui calcule une capacité de 40 %. Mais l'AMF la classe au profil 4
« Croissance », et non au profil 5, parce que ses connaissances sont intermédiaires. Le profil 4 correspond, dans le barème, à
une baisse tolérable de 30 %. Faut-il appliquer 30 % ou 40 % ? À 0,4 point près, cela change la stratégie retenue.

### 2. Options
- (a) Non : la limite reste 0,40, et `Mom_etf_top3` est retenu.
- (b) Oui : la limite est 0,30 ; `Mom_etf_top3` sort pour 0,4 pt, et il faut revoir la règle de sélection.

### 3. Preuves

| source | date | URL | citation | ce que ça prouve |
|---|---|---|---|---|
| [S3] avis 31-368 | 2025-12-10 | osc.ca | Lacune relevée : « Some registrants assessed risk capacity by looking solely at a client's personal and financial circumstances without obtaining any client input specifically on their risk capacity. » | La « capacité 0,40 » d'Amira est pire encore : elle ne vient ni d'elle ni de sa situation (inconnue), mais du p90 de la baisse maximale d'une politique de référence (`reports/amira.md` §3.1). C'est un budget du modèle, pas une capacité au sens du règlement. |
| [S1] 31-103CP, connaissances | 2022-06-06 | osc.ca | « Registrants should always make further inquiries if the information provided by a client appears to be inconsistent with their apparent level of investment knowledge. For example, a client may indicate that they have limited investment knowledge and experience, while also indicating a willingness to accept a high level of risk. » | Le cas d'Amira (connaissances intermédiaires, tolérance élevée) appelle une **question**, pas un relèvement automatique. Le plafond Q5 de l'AMF en est la version mécanique. |
| [S7] ESMA 2022, § 46 | 2022-09-23 | esma.europa.eu | « …instead of asking whether a client feels comfortable with taking risk, the firm should ask what level of loss over a given time period the client would be willing to accept… » | Pour aller au-delà de 30 %, il faut demander explicitement « 40 % sur telle durée ». « Plus de 30 % » ne veut pas dire 40 %. |
| [S9] Wealthfront, livre blanc de méthodologie | 2026-03-09 | research.wealthfront.com | « Our overall Risk Score combines subjective and objective risk tolerance, with a heavier weighting to whichever component is more risk averse. » | L'industrie penche vers la composante la plus prudente, pas vers la plus audacieuse. |
| [S14] Énoncé officiel, p. 5 | 2026 | PDF local | « Il doit tenir compte de son profil offensif sans interpréter « risque élevé » comme « tout est acceptable ». » | 0,30 reste offensif (bande Croissance, environ 80 % d'actions, ci-dessous). Cela répond au test sans le dénaturer. |
| Équipe, `questionnaire-profil.md` l. 173 (brain a65a0b3) | 2026-11-15 | git show | « La tranche ouverte « 30 % ou plus » vaut 30 %. » | Règle déjà proposée par l'équipe : la borne basse d'une tranche. |

### 4. Nos données
- Avec l'ancrage D9 (pire épisode CAD 1977+) : Croissance 29,9 % ≤ 0,30 donne la **bande Croissance** ; Actions 39,7 % ≤ 0,40 donne la
  bande Actions [STR → `CAD`, `CAD_bands.amira_*`]. Avec 0,30, Amira reste donc « Croissance », ce qui concorde avec AMF 4 et BNC Croissance.
- `Mom_etf_top3` : pire baisse 0,304 contre 0,30. Les données mensuelles sous-estiment les creux (SPY 2021-2026 : 0,2225 en quotidien,
  0,1867 en mensuel [REC]). Un écart de 0,4 pt n'est donc **pas significatif** dans un sens comme dans l'autre. La règle de sélection ne
  doit pas dépendre de cet écart (point pour le rapport de construction).
- Le croisement note que sous 0,30 le minimax ne garde que `RP_invvol_36m` (16 à 36 % d'actions) [WC]. C'est un artefact de la règle
  de sélection, pas du profil : la *catégorie* reste Croissance.

### 5. Résolution proposée pour le prototype
1. **Limite par défaut : 0,30**, catégorie Croissance (AMF 4). Raisons : la borne basse de la tranche « plus de 30 % », la concordance
   avec le profil AMF 4, et une capacité qui n'est pas mesurée.
2. **0,40 n'est accessible qu'à deux conditions** : (i) Amira confirme un scénario explicite (« une baisse de 40 000 $ sur 100 000 $
   pendant environ deux ans, vous restez investie ? ») ; (ii) le plafond Q5 est levé par un **quiz** de connaissances (ESMA
   [S7] : pas d'auto-évaluation), ou l'écart est justifié par écrit (31-368).
3. Afficher la capacité comme « **estimée par le modèle** (horizon de 15 ans), non déclarée ».
4. Texte à afficher : *« Vous acceptez plus de 30 % de baisse. Nous retenons 30 % (30 000 $ sur 100 000 $) tant que vous n'avez pas
   confirmé un scénario plus dur et vos connaissances. C'est ce qui sépare "risque élevé" de "tout est permis". »*
- **Ce qui ferait changer** : la confirmation d'un scénario à 40 % et un quiz Q5 réussi (bande Actions possible) ; une règle de
  sélection insensible aux effets de seuil.
- **Qui valide** : l'équipe ; le volet construction pour la règle de sélection.

---

## D9. Ancrage de la catégorie de risque : stress 2022 ou histoire longue ?

### 1. La question en mots simples
Pour ranger un portefeuille dans « Prudent », « Équilibré » ou « Actions », le questionnaire de l'équipe compare sa perte de
2022 à la perte acceptable. Mais en 2022, actions et obligations ont baissé ensemble. Tous les portefeuilles ont donc perdu à peu
près autant (de 10,6 % à 11,9 %), et la règle ne les sépare plus. Que font les régulateurs et l'industrie ?

### 2. Options
- (a) Stress 2022 seul (brain, `questionnaire-profil.md` l. 169 et 178).
- (b) Pire épisode CAD 1977+ (croisement §6.1).
- (c) p90 de la baisse maximale à l'horizon de la poche.
- (d) Enveloppe USD 1926+ avec 1929-32.
- (v0.2) Enveloppe historique longue sur 3 familles, avec 2022 en simple contrôle (`judge_extra_checks.stress.y2022`).

### 3. Preuves

| source | date | URL | citation | ce que ça prouve |
|---|---|---|---|---|
| [S5] Règlement 81-102, annexe F, items 1 et 2 | consolidation du 2025-07-16 | osc.ca | « A mutual fund must calculate its standard deviation for the most recent 10 years » ; bornes : « 0 to less than 6 Low … 20 or greater High ». | Le régulateur canadien classe le risque des OPC et des FNB sur **10 ans de rendements mensuels**, pas sur un épisode. |
| [S5] idem, commentaire de l'item 1 | idem | idem | Si la méthode donne un niveau trop bas, « …when a mutual fund employs investment strategies that produce an atypical or non-normal distribution of performance results… », les fonds sont invités à relever le niveau. | La volatilité seule ne suffit pas pour une stratégie à queue épaisse, comme le momentum d'Amira (ci-dessous). |
| [S1] 31-103CP, art. 13.3 | 2022-06-06 | osc.ca | « …using the risk rating of a security as the only input in determining its suitability for a client is not in itself sufficient… » | L'étiquette de l'annexe F décrit un produit ; elle ne peut pas être à elle seule l'ancre qui relie un client à une catégorie. |
| [S6] FSA FG11/05, § 4.15 | 2011-03 | fca.org.uk | « We are concerned that, where firms solely use volatility as a proxy for risk and ignore other risks, this can result in investment selections that… may not be suitable… » | Un seul indicateur, que ce soit la volatilité ou un seul stress, ne suffit pas. |
| [S8] Vanguard, « Range of calendar year returns (1928–2025) » | données au 2025-12-31 | investor.vanguard.com (graphique SVG) | Pire année civile : 100 % actions −43,3 %, 60/40 −26,9 %, 40/60 −18,7 %, 20/80 −14,1 %, 100 % obligations −12,9 %. | Un grand robot-conseiller et gestionnaire présente le risque de chaque mélange par la **pire perte sur près d'un siècle**, pas par une seule année. L'écart entre 20/80 et 100 % actions y vaut 29 points. |
| [S10] Betterment, « Portfolio strategy » | 2026-06-15 | betterment.com | « The "risk" element of this statement represents volatility and the related drawdown potential of the portfolio… » | L'industrie pense le risque en volatilité *et* en baisse potentielle. |
| [S14] Énoncé officiel, p. 17 | 2026 | PDF local | « Les équipes doivent distinguer faits, hypothèses et scénarios fictifs et présenter les incertitudes importantes de façon compréhensible. » | Afficher plusieurs mesures, en disant laquelle décide, sert l'explicabilité exigée. |

### 4. Nos données
Méthode de l'annexe F appliquée à nos séries longues (mêmes séries que [STR], rendements mensuels, écart-type sur 120 mois avec ddof = 1,
annualisé par √12) [ADC → `comparison_bnc`, `appendix_f`] :

| BNC (proxys, CAD 1977+) | écart-type 10 ans au 2026-09 | catégorie ACVM | max. sur fenêtres de 10 ans (catégorie) | perte 2022 | pire année civile | pire épisode |
|---|---|---|---|---|---|---|
| Prudent 80/6/14 | 5,35 % | Faible | 9,19 % (Faible à moyen) | 10,59 % | 10,59 % (2022) | 14,98 % (2022) |
| Conservateur 70/9/21 | 5,65 % | Faible | 9,40 % (Faible à moyen) | 10,78 % | 10,78 % (2022) | 15,31 % (2022) |
| Pondéré 55/13,5/31,5 | 6,62 % | Faible à moyen | 10,33 % (Faible à moyen) | 11,04 % | 11,04 % (2022) | 15,79 % (2022) |
| Équilibré 40/18/42 | 8,00 % | Faible à moyen | 11,79 % (Moyen) | 11,29 % | 11,29 % (2022) | 19,11 % (2000-02) |
| Croissance 20/24/56 | 10,18 % | Faible à moyen | 14,17 % (Moyen) | 11,59 % | 17,86 % (2008) | 29,88 % (2000-02) |
| Actions 0/30/70 | 12,58 % | Moyen | 16,80 % (Moyen à élevé) | 11,86 % | 25,34 % (2008) | 39,67 % (2000-02) |
| **écart Prudent → Actions** | **7,2 pt** | 3 catégories | 7,6 pt | **1,3 pt** | 14,8 pt | **24,7 pt** |

Lecture :
- 2022 seul ne sépare pas les portefeuilles : 1,3 pt d'écart.
- La pire année civile, mesure de type Vanguard, sépare le haut de l'échelle, mais pas les 4 BNC les plus prudents, dont la pire année *est* 2022.
- Le pire épisode sépare toute l'échelle. 2022 y reste l'épisode qui lie pour Prudent, Conservateur et Pondéré.
- L'annexe F range 6 BNC dans 3 catégories seulement. Réserve : `CA_GOV_10Y` est construit sur des taux moyens mensuels, ce qui sous-estime la volatilité obligataire.
- **Limite de l'écart-type** : le momentum d'Amira (`Mom_etf_top3`) obtient 9,02 % (« Faible à moyen »), la même étiquette que Pondéré,
  alors que sa pire perte vaut 28,5 % (1987) et sa pire année 25,1 % [ADC, STR]. C'est exactement le cas « non normal » que prévoit le commentaire
  de l'annexe F.
- `eq20_gold10` (Robert) : 4,22 %, catégorie Faible. `risk_parity_iv36` (Mateo) : 5,42 %, catégorie Faible.
- En USD 1926+ : écart 2022 de 2,8 pt, pire épisode de 65,2 pt (1929-32 lie dès Conservateur) [ADC → `comparison_bnc.USD`].

### 5. Résolution proposée pour le prototype
1. **Ancre** : la pire perte (du sommet au creux) sur une **histoire longue à plusieurs épisodes**, dans la devise de l'investisseur, où
   **2022 reste un épisode** (il lie pour les bandes basses). **Contrôle** : le p90 de la baisse maximale à l'horizon de la poche.
   Cela concorde avec la v0.2 (enveloppe longue, 2022 en contrôle au Judge) et avec la proposition du croisement §6.1. Cela **contredit
   explicitement** `questionnaire-profil.md` l. 169 et 178, que la PR brain#2 marque déjà « A confirmer ». Les preuves
   ne tranchent pas entre l'enveloppe à 3 familles de la v0.2 et le jeu d'épisodes CAD 1977+ du croisement. Ce choix relève de F1 et du
   volet construction. 1929-32 reste **informatif** (`stress_informational` de la v0.2).
2. **Afficher sans en faire l'ancre**, dans le panneau d'explication : l'étiquette « écart-type sur 10 ans, méthode ACVM » (de Faible à
   Élevé) et la pire année civile. Ce sont des repères familiers aux régulateurs et à l'industrie. Quand l'étiquette sous-estime le
   risque, on le dit : *« Volatilité "faible à moyenne", mais pire perte historique de 28 % : la volatilité ne voit pas tout. »*
3. Texte d'explication : *« Votre catégorie est la plus élevée dont la pire perte passée (1977-2026, en dollars canadiens, sur 7
   épisodes dont 2022) reste sous votre perte acceptable. 2022 seul ne suffit pas : cette année-là, presque tous les portefeuilles
   ont perdu environ 11 %. »*
- **Ce qui ferait changer** : un régime d'inflation où actions et obligations restent corrélées (1970-1999 : 97,5 à 100 % des fenêtres de
  36 mois positives [H22 du croisement]). La 2022 serait alors un régime durable, ce qui plaide encore pour l'histoire longue.
- **Qui valide** : l'équipe (mise à jour de `questionnaire-profil.md`) et F1 (adaptateur du questionnaire).

---

## D11. Démo : quelles questions poser explicitement au lieu d'inférer ?

### 1. La question en mots simples
Dans nos 6 fiches, toutes les réponses sur la tolérance sont devinées à partir de récits, et elles décident du portefeuille dans 4
poches sur 9. Faut-il les poser à l'écran pendant la démo ? Lesquelles, et comment, sans orienter la réponse ?

### 2. Options
- (a) Garder les inférences et les afficher comme hypothèses.
- (b) Poser Q10 et Q11 (avec l'accord de l'auteur de l'analyse réglementaire, transmis par la coordination).
- (c) Poser (b) et en plus les questions qui changent le résultat de chaque persona.

### 3. Preuves

| source | date | URL | citation | ce que ça prouve |
|---|---|---|---|---|
| [S4] ACVM, avis 31-342 (conseil en ligne) | 2015-09-24 | osc.ca | Un questionnaire en ligne bien conçu va « prevent a client or prospective client from progressing further until all questions have been answered » et « test for inconsistencies in the answers (for example, answers that indicate both low risk tolerance and a maximum growth objective), and will not let the client… complete the questionnaire until the conflict is resolved ». | Pour un robot-conseiller canadien : pas de profil sans réponses, et une incohérence bloque. |
| [S1] 31-103CP | 2022-06-06 | osc.ca | « Clients should not be influenced by a representative as to the way they respond to questions related to their risk tolerance or risk capacity. » | Montrer l'effet sur le portefeuille *avant* la réponse orienterait le choix. Le montant de la perte peut figurer dans la question ; le résultat, seulement après. |
| [S1] idem | idem | idem | « KYC questions and client communications should be in plain language and supported with explanations of what each question or item relates to… » | Le « pourquoi je vous demande ça » de `questionnaire-profil.md` est conforme. |
| [S7] ESMA 2022, § 46 | 2022-09-23 | esma.europa.eu | « Self-assessment should be counterbalanced by objective criteria. » ; montrer des exemples « by means of graphs or through positive and negative scenarios which are based on reasonable assumptions ». | Q10 en dollars sur une durée, et Q5 en quiz plutôt qu'en auto-évaluation. |
| [S11] Klement, CFA Institute Research Foundation | 2015-04-01 | rpc.cfainstitute.org | « The current standard process of risk profiling through questionnaires is highly unreliable and typically explains less than 15% of the variation in risky assets between investors… » | Même posée, une réponse reste incertaine : il faut afficher sa sensibilité. |
| [S12] Guiso, Sapienza, Zingales, NBER WP 19284 (JFE 2018) | 2013-08 | nber.org | « We find that both a qualitative and a quantitative measure of risk aversion increases substantially after the crisis. » | La tolérance est datée : la reposer à la révision, et ne pas la déduire d'une période calme. |

### 4. Nos données
Toutes les volontés sont inférées ; elles l'emportent sur la capacité dans 4 poches sur 9 (croisement §8). Effet quand elles gagnent :
- Robert : actions de 20 % à 0 % ;
- Mateo : −1,75 pt de p10 en CAD ;
- p35 B : actions de 60 % à environ 35-40 %.

Montants pour 100 000 $ fictifs [ADC → `q10_dollars.options`] : 0 / 5 000 / 15 000 / 30 000 / 30 000 $ (borne basse de « plus de 30 % »).

### 5. Résolution proposée pour le prototype
L'option (c), dans un ordre fixe, une question à la fois :

| persona | questions à poser (texte à adapter) | pourquoi |
|---|---|---|
| Robert | **Q10 en dollars** ; **Q3** (« quand retirerez-vous au moins le tiers ? ») ; **capacité** : « Une baisse de 15 000 $ juste avant votre retraite changerait-elle votre date de départ ou votre train de vie ? » (définition FCA de la capacité [S6]) ; Q11 | Ces réponses décident entre encaisse et `eq20_gold10` (D1) ; 31-368 exige un apport du client sur la capacité. |
| Mateo | **Q10 en dollars** ; **tolérance du conjoint** ; **date des études** fixe ou souple ; Q11 ; Q8 | D3 : la bande cède-t-elle ? Le ménage prend le minimum. |
| Amira | **Q10 avec un scénario à 40 000 $** ; **Q5 en quiz** ; Q11 (« acheter plus » ou « conserver ») ; fonds d'urgence (Q7) | D4 : 0,30 ou 0,40, AMF 4 ou 5. |

Règles d'affichage :
- le montant de la perte figure dans la question ;
- l'effet sur le portefeuille (stratégie, p10, catégorie) s'affiche **après** la réponse, avec un bouton « revoir ma réponse » si un conflit
  apparaît (31-103CP : « revisited ») ;
- chaque réponse scénarisée de la démo est marquée « réponse fictive scénarisée ».
- **Ce qui ferait changer** : un temps de démo trop court. On garderait alors au minimum Q10 pour Robert et Mateo, et on afficherait les autres
  comme « hypothèse prudente, à confirmer ».
- **Qui valide** : l'équipe (script de démo).

---

## Transversal : comment traiter une réponse INFÉRÉE et une réponse DÉCLARÉE

### 1. La question en mots simples
Quand une information vient d'une déduction et non de la bouche de la personne, quel poids lui donner ? Faut-il la faire confirmer ?
Que faire en attendant ?

### 2. Options
- (a) Confiance chiffrée et moyenne pondérée.
- (b) Une valeur inférée lie comme une réponse.
- (c) Une valeur inférée ne lie jamais : question obligatoire, et en attendant un statut incomplet avec une hypothèse prudente affichée.

### 3. Preuves (en plus de celles des sections précédentes)

| source | date | URL | citation | ce que ça prouve |
|---|---|---|---|---|
| [S3] avis 31-368 | 2025-12-10 | osc.ca | « Any inconsistencies should be discussed with the client, and the resolution should be documented. » ; lacune : « No confirmation of risk profile by client ». | Il faut une confirmation et une trace de la résolution. |
| [S3] idem | idem | idem | Il faut éviter « …where a client with a high risk capacity and low risk tolerance is determined to have a high risk profile. » | La pondération ne doit pas faire remonter le profil au-dessus du minimum. |
| [S7] ESMA 2022, ligne directrice 4 | 2022-09-23 | esma.europa.eu | « Firms should take reasonable steps and have appropriate tools to ensure that the information collected about their clients is reliable and consistent, without unduly relying on clients' self-assessment. » | La fiabilité se vérifie ; elle ne se suppose pas. |
| [S7] idem, § 12 | idem | idem | « Without this information, firms cannot provide investment advice and portfolio management services to clients. » | Sans information, pas de résultat « final ». |
| [S9] Wealthfront | 2026-03-09 | research.wealthfront.com | « The less consistent the answers, the exponentially less risk-tolerant you are likely to be. » | L'incohérence fait baisser le score ; elle ne se moyenne pas. |
| [S6] FSA FG11/05, § 3.19 | 2011-03 | fca.org.uk | Une réponse neutre lue comme un vrai milieu : « …scoring it as reflecting a mid-range attitude to risk without further discussion with the customer, a flawed risk profile can result. » | Une valeur par défaut au milieu d'une fourchette (« faible à modéré ») ne vaut pas une réponse. |

### 4. Nos données et ce que font déjà nos documents
- `questionnaire-profil.md` donne une confiance de **provenance** : 0,9 si confirmé, 0,8 si déclaré, 0,6 si pré-rempli par un persona,
  au plus 0,5 si déduit, 0,3 à 0,4 pour une hypothèse prudente. Il précise : « Une valeur déduite n'entre dans aucun plafond avant d'avoir été confirmée (RV-04) ».
- La v0.2 donne une confiance de **fiabilité de mesure** (`default_confidence: declared 0.5, tested 0.8`), un `conservative_prior: 25`
  (soit N1) et un statut `INCOMPLETE` (niveau ≤ N2, aucun titre, aucune crypto).
- **Les deux échelles portent le même nom mais ne mesurent pas la même chose** (0,8 contre 0,5 pour « déclaré »). Le contrat
  `InvestorProfile.Score.confidence` ne dit pas laquelle il porte.
- Les trois « capacités dérivées » (Robert 0,23, Mateo 0,20, Amira 0,40) viennent de statistiques de portefeuilles, pas des clients.

### 5. Résolution proposée pour le prototype
1. **Deux champs distincts** : `provenance` ∈ {confirmé, déclaré, pré-rempli persona, inféré, manquant, hypothèse prudente} et
   `fiabilite` (la mesure psychométrique de la v0.2). À valider par l'équipe de développement : c'est une évolution du contrat.
2. **Une valeur inférée ne lie jamais comme un fait.** Elle déclenche d'abord une question. Faute de réponse, elle est remplacée par une
   **hypothèse prudente affichée**, et le profil passe au statut INCOMPLET (plafonds de la v0.2). L'hypothèse prudente est un **a priori de
   catégorie** (N1), pas la valeur la plus extrême d'une fourchette : cela évite le « inappropriate weight ».
3. **Le minimum se prend entre valeurs mesurées.** Une capacité tirée des données est étiquetée « estimée par le modèle ». Pour une poche
   à décaissement, une question de capacité est posée (31-368).
4. **Une incohérence bloque** la proposition finale jusqu'à ce que la personne la résolve (31-342). Le système ne tranche jamais vers
   plus de risque. La résolution est journalisée (31-368).
5. **Confirmation finale** : un écran récapitule le profil (tolérance, capacité, minimum retenu, provenances) avant tout résultat dit
   final (13.2(3.1)).
6. **Datation** : chaque réponse de tolérance porte une date et se repose à la révision (Guiso et al.). La part d'incertitude est affichée
   (Klement).
- **Ce qui ferait changer** : un test pilote qui calibrerait les poids. Ces poids restent des conventions d'équipe.
- **Qui valide** : l'équipe ; l'équipe de développement pour le contrat ; F1 pour l'adaptateur.

---

## Question ouverte transmise : abattement selon le secteur d'emploi (Tyler, revenu lié à l'énergie)

- **Preuves** : 31-103CP [S1] range « employment status and occupation » dans la situation personnelle à connaître. Sur la concentration,
  il prévoit : « we expect registrants to determine appropriate concentration and liquidity thresholds for their clients and to have
  processes in place to calculate, monitor and manage concentration in a client's account. » L'avis 31-368 [S3] cite comme bonne pratique
  des seuils « applied more conservatively to certain types of investors such as investors with lower risk tolerance and seniors. »
  **Aucune source consultée ne donne de coefficient** (ni 0,5 ni 0,75) : le seuil est laissé à la firme, qui doit le documenter.
- **Résolution proposée** : traiter l'abattement comme un **paramètre documenté**, par défaut **0,5**. C'est la valeur la plus prudente des
  deux, et c'est déjà celle de `familiarite.employer_ticker_cap_mult: 0.5` dans la v0.2. On l'affiche « convention d'équipe », avec 0,75 en
  sensibilité dans le panneau « ce qui changerait la réponse ». Ne pas le présenter comme une règle réglementaire.
- **Confiance** : faible sur la valeur, élevée sur l'obligation de la documenter. **Valide** : le volet finance de l'équipe.

---

## Limites
- Les textes canadiens sont lus dans des **consolidations non officielles de la CVMO** (OSC), en anglais : 31-103CP au 2022-06-06,
  Règlement 31-103 au 2023-09-13, Règlement 81-102 au 2025-07-16. La version officielle en français (LégisQuébec, Règlement 31-103, « à jour
  au 4 juillet 2026 ») renvoie au site de l'AMF, qui était inaccessible. Les citations sont en anglais, telles quelles.
- Le texte du Règlement 31-103 a été extrait d'un PDF : quelques mots manquent. Pour 13.3(2.1), on cite plutôt le résumé de l'avis 31-368 [S3],
  dont le texte est complet.
- Le barème AMF (Q3, Q10, plafond le plus bas) **n'a pas pu être relu** (403 ou Cloudflare). Les résolutions D1 et D4 en dépendent : si la
  formulation de Q10 précise une durée (par exemple « en un an »), la lecture cardinale doit suivre cette durée.
- Les chiffres de marché viennent de proxys mensuels (volatilité obligataire sous-estimée, creux intra-mois manqués) et de fenêtres qui se
  chevauchent (voir les limites du croisement, §10).
- Les pratiques européennes (ESMA), britanniques (FSA) et américaines (Vanguard, Wealthfront, Betterment, SEC) sont **comparatives** ; elles
  ne s'imposent pas au Canada.

## Les quatre questions
- **Quelles données ?** Les textes réglementaires et les pages de l'industrie [S1] à [S15], consultés le 2026-11-14. Les traces du croisement
  ([WC], [STR], [BNC], [REC]). Le nouveau calcul de l'annexe F et la vue en dollars ([ADC]), sur `data/processed`.
- **Pourquoi ce choix ?** La règle du minimum ne vaut que pour des valeurs mesurées. Les textes demandent de poser les questions, de résoudre
  les incohérences avec la personne, de ne jamais relever le risque pour atteindre un objectif, et de documenter les écarts.
- **Quelles limites ?** Celles de la section précédente, plus des personas fictifs dont les réponses de démo sont scénarisées par l'équipe.
- **Qu'est-ce qui changerait la réponse ?** Les vraies réponses à Q10, Q3 et Q5 ; la formulation exacte du barème AMF ; le choix de l'ère de
  mesure en D9.

## Reproduire
```bash
cd research/backtest
.venv/bin/python -I -W ignore analysis/decisions/A_reglementaire_calculs.py   # -> results/decisions/A_reglementaire_calculs.json
```
Le script réutilise `analysis/croisement/stress_anchor.series()`, sans le modifier, et lit `results/croisement_analysis/{stress_anchor,will_vs_cap,stress_mateo_series}.json`.

## Sources (toutes consultées le 2026-11-14)

| # | titre | organisme | date de publication | URL |
|---|---|---|---|---|
| S1 | Companion Policy 31-103CP Registration Requirements, Exemptions and Ongoing Registrant Obligations, consolidation non officielle (art. 13.2 « Client's risk profile », « Resolving conflicts… », « Client's investment time horizon » ; art. 13.3) | ACVM / CVMO | consolidation du 2022-06-06 | https://www.osc.ca/en/securities-law/instruments-rules-policies/3/31-103/unofficial-consolidation-companion-policy-31-103cp-registration-requirements-exemptions-and-1 (PDF : https://www.osc.ca/sites/default/files/2022-11/cp_20220606_31-103_unofficial-consolidation.pdf) |
| S2 | National Instrument 31-103, consolidation non officielle (art. 13.2(3.1), 13.3(2.1)) | ACVM / CVMO | consolidation du 2023-09-13 | https://www.osc.ca/en/securities-law/instruments-rules-policies/3/31-103/unofficial-consolidation-national-instrument-31-103-registration-requirements-exemptions-and-3 (PDF : https://www.osc.ca/sites/default/files/2023-12/ni_20230913_31-103_unofficial-consolidation.pdf) |
| S3 | Joint CSA/CIRO Staff Notice 31-368 Client Focused Reforms: Review of Registrants' Know Your Client, Know Your Product and Suitability Determination Practices and Additional Guidance | ACVM et OCRI | 2025-12-10 | https://www.osc.ca/en/securities-law/instruments-rules-policies/3/31-368/joint-csaciro-staff-notice-31-368-client-focused-reforms-review-registrants-know-your-client-know (PDF : https://www.osc.ca/sites/default/files/2025-12/csa-ciro_20251210_31-368_client-focused-reforms.pdf) |
| S4 | CSA Staff Notice 31-342 Guidance for Portfolio Managers Regarding Online Advice | ACVM | 2015-09-24 | https://www.osc.ca/en/securities-law/instruments-rules-policies/3/31-342/csa-staff-notice-31-342-guidance-portfolio-managers-regarding-online-advice |
| S5 | National Instrument 81-102 Investment Funds, Appendix F « Investment Risk Classification Methodology », consolidation non officielle | ACVM / CVMO | consolidation du 2025-07-16 | https://www.osc.ca/en/securities-law/instruments-rules-policies/8/81-102-81-102cp/unofficial-consolidation-national-instrument-81-102-investment-funds-4 (PDF : https://www.osc.ca/sites/default/files/2026-02/ni_20250716_81-102_unofficial-consolidation.pdf) |
| S6 | Finalised guidance FG11/05 « Assessing suitability: Establishing the risk a customer is willing and able to take and making a suitable investment selection » | Financial Services Authority (aujourd'hui FCA), R.-U. | 2011-03 | https://www.fca.org.uk/publication/finalised-guidance/fsa-fg11-05.pdf |
| S7 | ESMA35-43-3172 Guidelines on certain aspects of the MiFID II suitability requirements | ESMA (UE) | 2022-09-23 (PDF mis en ligne le 2023-04-03) | https://www.esma.europa.eu/sites/default/files/2023-04/ESMA35-43-3172_Guidelines_on_certain_aspects_of_the_MiFID_II_suitability_requirements.pdf |
| S8 | « Investment portfolios: Asset allocation models » et graphique « Range of calendar year returns (1928–2025) » | Vanguard | données au 2025-12-31 | https://investor.vanguard.com/investor-resources-education/education/model-portfolio-allocation (graphique : https://investor.vanguard.com/content/dam/retail/digital/en/data-viz/vanguard-range-of-calendar-year-returns-2026.svg) |
| S9 | Wealthfront Investment Methodology White Paper (« Determining Risk Tolerance ») | Wealthfront | 2026-03-09 | https://research.wealthfront.com/whitepapers/investment-methodology/ |
| S10 | Betterment Portfolio Strategy | Betterment | 2026-06-15 | https://www.betterment.com/resources/betterment-portfolio-strategy |
| S11 | Klement, J., « Investor Risk Profiling: An Overview » (Research Foundation Brief) | CFA Institute Research Foundation | 2015-04-01 | https://rpc.cfainstitute.org/research/foundation/2015/investor-risk-profiling-an-overview |
| S12 | Guiso, L., Sapienza, P., Zingales, L., « Time Varying Risk Aversion », NBER WP 19284 (publié au Journal of Financial Economics, 2018) | NBER | 2013-08 | https://www.nber.org/papers/w19284 |
| S13 | « Beginners' Guide to Asset Allocation, Diversification, and Rebalancing » | SEC, Investor.gov | non datée sur la page | https://www.investor.gov/additional-resources/general-resources/publications-research/info-sheets/beginners-guide-asset |
| S14 | Datathon, cas officiel 2026 (FR), p. 5 à 7 (personas) et p. 17 (encadrement responsable) | PolyFinances | 2026 | `source/Datathon2026/Datathon2026/Datathon - Case Officiel 2026 FR.pdf` (local) |
| S15 | Règlement 31-103 (V-1.1, r. 10), version officielle en français, « À jour au 4 juillet 2026 » (texte renvoyé vers le site de l'AMF, non lu) | LégisQuébec / AMF | consultée le 2026-11-14 | https://www.legisquebec.gouv.qc.ca/fr/document/rc/V-1.1,%20r.%2010 |

**Tentées sans succès** (403 ou vérification Cloudflare) : AMF, « Votre profil d'investisseur » (lautorite.qc.ca) ; OCRI, notes
d'orientation GN-3400-21-004 et bulletin « sept. 2026 » (ciro.ca) ; FINRA, règle 2111 et « Report on Digital Investment Advice » (finra.org) ;
SEC (sec.gov) ; site des ACVM (securities-administrators.ca). Ces sources ne sont citées nulle part comme vérifiées.
