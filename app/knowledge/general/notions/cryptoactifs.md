---
type: Financial Concept
title: Cryptoactifs
description: Ce qu'est un cryptoactif, pourquoi AlphaForge AI en limite fortement la place, ses limites et comment l'expliquer à chaque niveau.
tags: [notion, instrument, cryptoactifs, risque]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 4 (familles de placements) et 5 (ce qu'on achète vraiment : volatilité, liquidité, garde, technologie)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, exemples d'actifs (BTC-USD, ETH-USD, p. 10), familles de données (p. 11), jeu de départ (p. 12) et Encadrement responsable (p. 17)"
  - id: regles-canada
    title: "Paramètres canadiens d'AlphaForge AI : protection SADC"
    resource: "app/agents/src/alphaforge/finance/rules/canada_2026.yaml, cdic.insured_categories (vérifié, 2026, https://www.cdic.ca/your-coverage/whats-covered/)"
  - id: risk-levels
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, sections satellites.crypto, knowledge, status et loss_bounds"
data:
  catalog_id: cryptoactifs
  aliases: [cryptoactif, crypto, bitcoin, btc, ether, eth, jeton, blockchain]
  related: [volatilite, baisse-maximale, concentration, var-cvar, fnb]
---

# Cryptoactifs

Un cryptoactif est un actif numérique inscrit sur une chaîne de blocs (*blockchain*). Les droits et les usages qu'il
donne varient d'un jeton à l'autre (atelier BNCD, diapositive 4). Le jeu de départ en contient deux : Bitcoin
(`BTC-USD`) et Ether (`ETH-USD`), cotés en dollars américains (énoncé, p. 10 et 12).

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « C'est une monnaie ou un jeton numérique. Son prix peut monter ou baisser très fort, très vite. Ce
  n'est pas un compte d'épargne : rien ne garantit la valeur. »
- **Intermédiaire** : « Un actif numérique sans revenus ni flux de trésorerie à analyser comme une action. Son rendement
  vient surtout de la variation de son prix; ses baisses passées sont bien plus profondes que celles d'un indice. »
- **Avancé** : « Actif à queue épaisse, sans historique long pour raccorder une série de crise. Le risque se gère par
  une borne de perte explicite et un poids plafonné, pas par une volatilité estimée sur quelques années. »

## Ce qu'il faut retenir

- La valeur peut varier très fortement, à la hausse comme à la baisse : c'est un risque de marché avant tout (voir
  [Volatilité](volatilite.md) et [Baisse maximale](baisse-maximale.md)).
- Il faut aussi comprendre la liquidité, la garde (où et par qui les jetons sont conservés) et le risque technologique
  (atelier BNCD, diapositive 5).
- Les cryptoactifs, y compris les jetons à valeur stable, ne sont pas couverts par la SADC, pas plus que les actions,
  les obligations ou les FNB (`canada_2026.yaml`, catégories assurées par la SADC, vérifié en 2026).
- Une petite part peut déjà peser lourd dans le risque d'un portefeuille : il faut regarder le poids et la perte
  possible ensemble.

## Comment AlphaForge AI l'utilise

- **Constat sur un portefeuille existant** : le code signale `crypto_exposure_high` quand les cryptoactifs dépassent
  10 % de la valeur évaluée (`profile/portfolio.py`; seuil à relire par le volet finance).
- **Plafond du mandat** : la limite `alloc.crypto` dépend du niveau de risque, de la préférence pour la crypto et du
  niveau de connaissances. Elle est nulle sous le niveau N4, réduite de moitié pour un débutant, qui n'y accède que par
  un FNB, et nulle quand le profil est incomplet ou en protection (`risk_levels.yaml`, sections `satellites.crypto`,
  `knowledge` et `status`).
- **Borne de perte** : Bitcoin et Ether n'ont pas d'historique long; ils sont exclus de la série raccordée et le code
  ajoute une perte supposée de 90 % de leur poids à la CVaR sur 12 mois et à la baisse maximale vérifiées par le Judge
  (`loss_bounds`). C'est une hypothèse prudente, affichée comme telle.
- Une vidéo tldoole peut être proposée quand un débutant dit s'intéresser aux cryptoactifs.

## Limites

- **Historique court** : quelques cycles seulement; les chiffres passés disent peu de la prochaine crise.
- **Devise** : les cotations sont en dollars américains; le résultat en dollars canadiens dépend aussi du change.
- **Simulation** : AlphaForge AI ne recommande aucun cryptoactif et n'exécute aucune transaction (énoncé, p. 17).

## À ne pas confondre

- **Cryptoactif et FNB de cryptoactifs** : le FNB se négocie en bourse et règle la garde, mais garde le risque de prix
  du jeton (voir [FNB](fnb.md)).
- **Jeton à valeur stable et dépôt bancaire** : un jeton arrimé au dollar n'est ni un dépôt ni une garantie SADC.
- **Rendement passé et potentiel** : une forte hausse passée ne dit pas que la suivante viendra.
