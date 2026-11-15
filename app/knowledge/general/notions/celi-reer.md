---
type: Financial Concept
title: CELI, REER et CELIAPP
description: Ce que sont les comptes enregistrés CELI, REER et CELIAPP, leurs plafonds vérifiés de 2026 et comment les expliquer à chaque niveau, sans recommandation.
tags: [notion, comptes-enregistres, celi, reer, celiapp, fiscalite]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: canada-celi
    title: "Gouvernement du Canada, Compte d'épargne libre d'impôt (CELI)"
    resource: "https://www.canada.ca/fr/agence-revenu/services/impot/particuliers/sujets/compte-epargne-libre-impot.html"
  - id: canada-reer
    title: "Gouvernement du Canada, REER et régimes connexes"
    resource: "https://www.canada.ca/fr/agence-revenu/services/impot/particuliers/sujets/reer-regimes-connexes.html"
  - id: arc-plafonds
    title: "ARC, plafonds CELI, REER et autres (MP, DB, RRSP, DPSP, ALDA, TFSA limits, YMPE and the YAMPE)"
    resource: "https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html, lu le 2026-11-14 (canada_2026.yaml, tfsa.annual_dollar_limit, tfsa.cumulative_room_since_2009, rrsp.dollar_limit)"
  - id: arc-t4040
    title: "ARC, guide T4040 : REER et autres régimes enregistrés pour la retraite (année d'imposition 2025)"
    resource: "https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/t4040/rrsps-other-registered-plans-retirement.html (canada_2026.yaml, rrsp.earned_income_rate)"
  - id: arc-reer-71
    title: "ARC, options du REER à 71 ans"
    resource: "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/rrsp-options-when-you-turn-71.html (canada_2026.yaml, rrsp.conversion_deadline)"
  - id: arc-celi-ouverture
    title: "ARC, ouvrir un CELI"
    resource: "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/opening.html (canada_2026.yaml, tfsa.eligibility_age)"
  - id: arc-celiapp
    title: "ARC, cotiser à votre CELIAPP"
    resource: "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/contributing-your-fhsa.html (canada_2026.yaml, fhsa.annual_limit, fhsa.lifetime_limit, fhsa.carry_forward_max)"
  - id: sadc
    title: "SADC, ce qui est couvert"
    resource: "https://www.cdic.ca/your-coverage/whats-covered/ (canada_2026.yaml, cdic.insured_categories, vérifié, 2026)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, Encadrement responsable (p. 17)"
data:
  aliases: [celi, reer, celiapp, tfsa, rrsp, fhsa, compte enregistré, abri fiscal]
  related: [fnb, interets-composes, horizon, frais]
---

# CELI, REER et CELIAPP

Le CELI (compte d'épargne libre d'impôt), le REER (régime enregistré d'épargne-retraite) et le CELIAPP (compte
d'épargne libre d'impôt pour l'achat d'une première propriété) sont des **comptes enregistrés** : des enveloppes
fiscales prévues par la loi. Ce sont des comptes, pas des placements : on peut y détenir des FNB, des actions ou des CPG
(voir [FNB](fnb.md)).

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Un CELI ou un REER est une boîte où l'on met ses placements. La boîte ne rapporte rien en soi; elle
  change la façon dont l'impôt s'applique à ce qu'il y a dedans. »
- **Intermédiaire** : « CELI : pas de déduction à la cotisation, mais revenus et retraits non imposables. REER :
  cotisations déductibles, retraits imposés. Chaque compte a des droits de cotisation limités et personnels. »
- **Avancé** : « Le choix dépend notamment du taux d'imposition à la cotisation et au retrait, des droits inutilisés et
  de l'objectif; AlphaForge AI ne fait pas ce calcul et ne tranche pas. »

## Ce qu'il faut retenir

- **CELI** : les revenus de placement et les retraits ne sont pas imposables; les cotisations ne sont pas déductibles
  (canada.ca). Ouverture dès 18 ans. Plafond annuel de 7 000 $ en 2026; 111 000 $ de droits cumulés depuis 2009 pour
  une personne admissible chaque année et n'ayant jamais cotisé (somme des plafonds annuels de l'ARC).
- **REER** : les cotisations sont déductibles du revenu imposable; les retraits sont imposés (canada.ca). Droits de
  18 % du revenu gagné de l'année précédente, jusqu'à 33 810 $ en 2026. Le REER doit être converti au plus tard le
  31 décembre de l'année des 71 ans.
- **CELIAPP** : plafond de 8 000 $ par année et de 40 000 $ à vie, avec au plus 8 000 $ de droits inutilisés reportés
  (2026). Les droits commencent à l'ouverture du premier CELIAPP.
- Les droits de cotisation sont propres à chaque personne. Pour le CELIAPP, une cotisation excédentaire est imposée à
  1 % par mois (ARC, 2026).

## Comment AlphaForge AI l'utilise

- Le questionnaire demande dans quels types de comptes l'argent sera placé (CELI, REER, REEE, FERR, non enregistré,
  ou « je ne sais pas »); A2 relève aussi le type de compte des lignes d'un portefeuille existant.
- Les plafonds sont versionnés avec leur source dans `finance/rules/canada_2026.yaml`; seules les valeurs marquées
  vérifiées peuvent être citées. Le moteur ne calcule pas encore l'impôt ni les droits de cotisation d'un investisseur.

## Limites

- Les plafonds changent chaque année : les valeurs ci-dessus valent pour 2026 et doivent être revérifiées.
- Les droits réels d'une personne dépendent de son historique (cotisations, retraits, facteur d'équivalence); seul
  l'avis de cotisation ou le dossier de l'ARC les donne.
- AlphaForge AI ne recommande aucun compte : simulation seulement, sans conseil fiscal ni financier personnalisé
  (énoncé, p. 17).

## À ne pas confondre

- **Compte et placement** : le CELI n'est pas un produit d'épargne à taux fixe; son risque est celui de ce qu'il
  contient.
- **CELI et compte d'épargne** : un CELI peut contenir des actions qui baissent.
- **Protection SADC** : elle couvre certains dépôts détenus dans un CELI ou un REER, pas les actions ni les FNB.
