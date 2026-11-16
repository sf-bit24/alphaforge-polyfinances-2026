---
type: Financial Concept
title: Baisse maximale
description: La pire chute d'un sommet à un creux, comment AlphaForge AI la calcule, ses limites et comment l'expliquer à chaque niveau.
tags: [notion, risque, baisse-maximale, drawdown]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 8 (le risque ne se résume pas à « ça peut baisser »)"
  - id: atelier-aws
    title: "Atelier du Datathon PolyFinances 2026 : aide-mémoire, pièges classiques des données financières"
    resource: "Atelier AWS du Datathon PolyFinances 2026, section 3 (rendement sans risque, rendement passé, adj_close)"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : prix quotidiens ajustés"
    resource: "starter:prices_daily.csv (colonne adj_close)"
data:
  aliases: [baisse maximale, drawdown, perte maximale, pire baisse, creux]
  related: [volatilite, pire-rendement-12-mois, var-cvar, horizon, tolerance-et-capacite]
---

# Baisse maximale

La baisse maximale (*maximum drawdown*) est la plus forte chute de valeur entre un sommet et le creux qui le suit, sur une
période donnée. Elle s'exprime en pourcentage du sommet. Elle répond à la question : « Dans le pire moment de cette
période, combien aurais-je perdu sur papier? »

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Imaginez que vous avez acheté au plus haut. La baisse maximale, c'est ce que vous auriez perdu, sur
  papier, au pire moment avant que ça remonte. »
- **Intermédiaire** : « La plus forte chute d'un sommet à un creux sur la période, en pourcentage. On la lit avec le
  temps de récupération : combien de mois avant de retrouver le sommet. »
- **Avancé** : « Maximum de 1 − Vₜ / max₍ₛ≤ₜ₎ Vₛ sur la fenêtre, sur une valeur composée à partir de prix ajustés. Mesure de
  risque de trajectoire, sensible à la fréquence d'observation et à la fenêtre retenue. »

## Ce qu'il faut retenir

- Une baisse demande une hausse plus grande pour être effacée : −20 % demande +25 %, −50 % demande +100 %. La formule
  est 1 / (1 − baisse) − 1.
- La profondeur ne suffit pas : le temps de récupération compte autant. Une baisse de 30 % effacée en six mois ne se vit
  pas comme une baisse de 30 % qui dure cinq ans.
- Une perte sur papier ne devient réelle que si l'on vend au creux. C'est pourquoi la baisse maximale se compare à la
  tolérance et à la capacité de risque de l'investisseur, et à son horizon (voir
  [Tolérance, capacité et risque effectif](../methodologie/tolerance-capacite-risque-effectif.md) et
  [Horizon de placement](../methodologie/horizon-de-placement.md)).
- Un rendement seul ne dit rien : il se lit avec la volatilité et la baisse maximale (aide-mémoire du Datathon, section 3).

## Comment AlphaForge AI la calcule

AlphaForge AI calcule la baisse maximale selon des règles fixes. Yan l'explique; les chiffres sont calculés, jamais
inventés. Deux calculs existent, sur la même définition.

| Où | Données | Résultat |
| --- | --- | --- |
| Risque d'un portefeuille (simulateur, vérification finale) | Rendements mensuels d'un portefeuille rééquilibré chaque mois vers ses poids | Perte positive (0,25 = 25 %) et nombre de mois de récupération |

- La vérification finale traite la baisse maximale comme un plafond bloquant : elle refuse une proposition qui le
  dépasse. AlphaForge AI propose alors la plus proche qui respecte votre mandat. Le plafond dépend du niveau de risque
  de votre profil (N0 à N5).
- Elle la mesure sur un long historique mensuel, en dollars canadiens, où chaque actif est raccordé à un proxy d'historique
  (indice ou industrie) pour inclure des crises comme 1973-1974, 2000-2002 et 2008. Un actif sans proxy, comme le
  bitcoin, est exclu de la série et sa part ajoute une perte prudente de 90 % de son poids.
- Le simulateur utilise une approximation arithmétique (CDaR), en général plus prudente. La vérification finale porte
  sur la baisse composée.

## Limites

- **Passé seulement** : la baisse maximale décrit une période passée et ne prédit pas la prochaine baisse. Une baisse
  plus forte reste possible.
- **Fenêtre** : elle dépend de la période choisie. Une fenêtre sans crise donne un chiffre rassurant et trompeur.
- **Fréquence** : sur des données mensuelles, une chute survenue et effacée à l'intérieur d'un mois n'apparaît pas; la
  baisse mensuelle est donc souvent plus faible que la baisse quotidienne du même actif. Pour en tenir compte, la perte
  de planification comparée à la perte que l'investisseur dit accepter ajoute 4 points à la baisse mensuelle
  (un choix encore ouvert).
- **Devise** : la baisse d'un actif américain n'est pas la même en dollars américains et en dollars canadiens.
- **Prix ajustés** : sur des prix bruts, un fractionnement d'actions ressemblerait à une baisse. Le calcul utilise
  les prix de clôture ajustés (aide-mémoire du Datathon, section 3).

## À ne pas confondre

- **Volatilité** : l'ampleur moyenne des variations, à la hausse comme à la baisse. La baisse maximale ne regarde que
  le pire épisode de baisse.
- **Pire rendement sur 12 mois** : la pire année glissante, d'une date fixe à une date fixe un an plus tard, et non d'un
  sommet à un creux.
- **Perte réalisée** : ce que l'investisseur perd vraiment en vendant. La baisse maximale est une perte sur papier.
