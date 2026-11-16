---
type: Financial Concept
title: Rendement du dividende
description: Les dividendes des 12 derniers mois rapportés au cours, comment AlphaForge AI le calcule à partir du jeu de départ, et pourquoi ce n'est pas le rendement total.
tags: [notion, rendement, dividende, fiscalite]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:30:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: jeu-de-depart-dividendes
    title: "Jeu de départ AlphaForge AI : dividendes et fractionnements par date ex"
    resource: "starter:corporate_actions.csv (lignes dividend, montant par action en devise de cotation) et starter:prices_daily.csv (colonne close)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: starter-readme
    title: "Guide du jeu de départ AlphaForge AI"
    resource: "alphaforge_starter/README.md, section « Things to know before using the data » (adj_close, fractionnements déjà appliqués, CNQ.TO le 2022-08-22)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 6 (gain ou perte en capital plus revenus reçus égale rendement total)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: ftse-global-factor
    title: "FTSE Russell, FTSE Global Factor Index Series Ground Rules, v8.8 (juillet 2026)"
    resource: "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-factor-index-series-ground-rules.pdf, §5.8 (rendement du dividende sur 12 mois glissants)"
    retrieved_at: "2026-11-15T04:10:00Z"
  - id: convention-canada-eu
    title: "Convention fiscale entre le Canada et les États-Unis (1980, codification avec les protocoles jusqu'en 2007)"
    resource: "https://www.canada.ca/en/department-finance/programs/tax-policy/tax-treaties/country/united-states-america-convention-consolidated-1980-1983-1984-1995-1997-2007.html, article X, paragraphe 2 b) (15 % dans les autres cas) et article XXI, paragraphe 2 (régimes de retraite exonérés)"
    retrieved_at: "2026-11-15T04:05:00Z"
  - id: regles-canada
    title: "Paramètres canadiens d'AlphaForge AI : retenue à la source sur les dividendes américains"
    resource: "app/agents/src/alphaforge/finance/rules/canada_2026.yaml, section foreign_withholding (statut unverified)"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  aliases: [rendement du dividende, taux de dividende, dividende, dividendes, rendement en dividendes, ça verse un revenu]
  related: [rendement-total, celi-reer, risque-de-change, selection-par-regles, style-de-portefeuille]
---

# Rendement du dividende

Le rendement du dividende rapporte les dividendes versés par une action sur les 12 derniers mois à son cours du jour,
en pourcentage. Une action à 50 $ qui a versé 2 $ de dividendes sur un an a un rendement du dividende de 4 %. C'est
une mesure du revenu passé, pas du rendement total.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Certaines sociétés partagent une partie de leurs profits en argent avec leurs actionnaires. Le
  rendement du dividende dit combien elles ont versé sur un an, pour chaque 100 $ d'actions au prix d'aujourd'hui. »
- **Intermédiaire** : « Dividendes des 12 derniers mois divisés par le cours. Il ne dit rien de la variation du prix :
  un titre peut verser 5 % et perdre 20 % de sa valeur la même année. »
- **Avancé** : « Rendement courant sur 12 mois glissants, Σ dividendes par action (dates ex) / cours. Mesure rétrospective,
  sensible aux dividendes spéciaux, aux coupures et au dénominateur. »

## Ce qu'il faut retenir

- **Ce n'est pas le rendement total** : le rendement total additionne la variation du prix et les revenus reçus
  (atelier BNCD, diapositive 6; voir [Rendement total](rendement-total.md)). Avec 6 % de dividendes et un cours en
  baisse de 15 %, le rendement total est d'environ −9 %.
- **Un rendement élevé vient souvent d'un cours qui a baissé** : le dénominateur a diminué, ce qui peut signaler une
  difficulté de la société.
- **Un dividende peut être réduit ou suspendu** : la société n'a aucune obligation de le maintenir.
- **Le dividende ne crée pas de valeur à lui seul** : à la date ex, le cours baisse en général d'environ le montant
  versé.
- **Fiscalité dans un CELI** : la Convention Canada–États-Unis fixe à 15 % la retenue à la source sur les dividendes
  versés par une société américaine à un particulier canadien (article X, paragraphe 2 b). L'exonération de
  l'article XXI vise les régimes de retraite, comme le REER; selon la lecture courante, le CELI n'en profite pas, et
  la retenue y est perdue (voir [CELI, REER et CELIAPP](celi-reer.md)). AlphaForge AI marque encore cette lecture
  « non vérifiée ».

## Comment AlphaForge AI le calcule

AlphaForge AI calcule le rendement du dividende selon des règles fixes. Yan l'explique; les chiffres sont calculés,
jamais inventés.

- **Numérateur** : somme des dividendes du jeu de départ dont la date ex tombe dans les 12 mois qui précèdent la
  date de calcul, en montant par action et en devise de cotation. Ces montants sont déjà ajustés des
  fractionnements : NVDA y verse 0,004 $ US par trimestre en 2022, un montant ramené à l'échelle du fractionnement
  10 pour 1 de 2024.
- **Dénominateur** : le cours de clôture à la date, ajusté des fractionnements seulement, comme les dividendes. Le
  cours de clôture ajusté tient aussi compte des dividendes et fausserait le ratio.
- **Devise** : numérateur et dénominateur sont dans la même devise; aucune conversion n'est nécessaire.
- **Opérations spéciales** : les fractionnements ne sont pas des dividendes. Le « fractionnement » de 1,021 de CNQ.TO
  du 2022-08-22, probablement une distribution spéciale, n'entre donc pas dans le calcul (guide du jeu de départ).
- **Fenêtre** : dates ex dans les 365 jours qui précèdent la date de calcul, cette date comprise.
- **Usage** : c'est un des critères de la [sélection de titres par règles](selection-par-regles.md). Les styles
  défensif et dynamique favorisent un rendement du dividende plus élevé, et un intérêt déclaré pour les dividendes
  augmente son poids, sans lever aucun plafond. Comme chez FTSE Russell, qui emploie la même mesure sur 12 mois
  glissants (§5.8), un titre sans dividende reçoit le rang le plus bas sur ce critère (voir
  [Choix et score des titres selon le style](../methodologie/scoring-par-style.md)).

## Limites

- **Fenêtre de 12 mois** : un dividende spécial gonfle le chiffre; un versement annuel décalé d'une semaine peut
  sortir de la fenêtre.
- **Passé seulement** : le rendement mesuré ne dit rien des dividendes à venir.
- **Rachats d'actions** : une société qui redistribue par rachats plutôt que par dividendes paraît à tort sans revenu.
- **Actions seulement** : le choix des titres selon le style ne calcule pas de rendement de distribution pour les
  FNB.

## À ne pas confondre

- **Rendement total** : prix plus revenus, la seule mesure qui dit ce qu'un placement a rapporté.
- **Rendement d'une obligation** : il dépend du prix, des coupons et de l'échéance (voir
  [Obligations et taux](obligations-et-taux.md)).
- **Rendement sur le coût d'achat** : dividendes rapportés au prix payé jadis, qui flatte un titre détenu depuis
  longtemps.
- **Risque de change** : un dividende en dollars américains varie aussi en dollars canadiens (voir
  [Risque de change](risque-de-change.md)).
