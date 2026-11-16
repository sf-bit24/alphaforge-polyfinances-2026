# OKF : comment nos bases sont rangées dans S3

La base générale et la base de chaque client sont des documents au format [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md), publié par Google Cloud : un fichier Markdown par concept, avec un en-tête YAML qui dit ce qu'il est, d'où il vient et quand le revoir. C'est aussi le format du Brain de l'équipe. Le détail du magasin est dans [`app/CONTRACTS.md`](../../app/CONTRACTS.md), section 5.

## Pourquoi ce format

1. **Lisible par tous.** L'investisseur, le jury, l'interface et les agents lisent le même fichier, sans base de données ni outil spécialisé.
2. **La provenance est dans le document.** `sources` et `generated` disent d'où vient chaque information et qui l'a écrite. Le superviseur rejette tout document sans source ni date.
3. **Le code lit des valeurs exactes.** Les chiffres sont dans `data`. La Knowledge Base ne sert qu'à retrouver un passage, jamais à fournir un nombre.
4. **Le chemin est l'identité.** Un dossier par type de document, une clé calculée par le code. IAM limite chaque rôle à ses préfixes : `profile` écrit `clients/`, le superviseur écrit `general/` mais jamais `general/methodologie/`.
5. **Indexable tel quel.** Bedrock Knowledge Bases lit les `.md` directement ; un fichier `.metadata.json` voisin permet de filtrer par type, ticker et date de publication.
6. **Versionné et exportable.** Le bucket est versionné, une base se copie sur un poste avec `aws s3 sync`, et la base de départ est versionnée dans git ([`app/knowledge/`](../../app/knowledge/)).

**Hors OKF** : les prix, le change et les données longues (parquets lus par le code), les scénarios, la collecte brute, les traces et les décisions complètes (`.json`).

## Les champs de l'en-tête

| Champ | Ce qu'il dit |
| --- | --- |
| `type` | Ce qu'est le document : `Investor Profile`, `News`, `Financial Concept`, `Portfolio Decision`, 16 types en tout. |
| `sources` | D'où vient chaque information, avec sa date de récupération. |
| `generated` | Qui l'a écrit et quand : le code, l'agent du profil (`agent:A1`), le superviseur (`agent:A6`). |
| `status`, `stale_after` | Brouillon (`draft`) ou stable, et la date où le revoir. |
| `sensitivity` | `client` sous `clients/`, `public` sous `general/`. |
| `data` | Les valeurs structurées que le code lit. Le corps Markdown, après l'en-tête, porte le texte. |

Un exemple réel, extrait de l'en-tête de [`general/notions/baisse-maximale.md`](../../app/knowledge/general/notions/baisse-maximale.md) (champs `description`, `tags`, `owners` et deux sources omis) :

```yaml
type: Financial Concept
title: Baisse maximale
status: draft
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: jeu-de-depart
    resource: "starter:prices_daily.csv (colonne adj_close)"
data:
  related: [volatilite, pire-rendement-12-mois, var-cvar, horizon, tolerance-et-capacite]
```

## Le bucket des bases

```text
alphaforge-sandbox-kb-<compte>/
├── general/                  base générale, commune, public
│   ├── methodologie/         méthode, versionnée dans git
│   ├── notions/              une notion financière par fichier
│   ├── societes/             fondamentaux, EDGAR, par le superviseur
│   ├── actualites/           presse datée, par le superviseur
│   ├── donnees/              séries et cours, par le superviseur
│   └── faits/ signaux/ depots/ recherches/   recherche par experts, par le superviseur
├── clients/<client_id>/      une base par investisseur
│   ├── profil.md             le profil et ses données
│   ├── portefeuille-existant.md
│   ├── journal.md            chaque réponse, sa provenance et sa date
│   ├── <notes>.md            notes de l'agent du profil
│   └── decisions/            résumé OKF de chaque décision simulée
└── staging/ archive/ runtime/ scenarios/   hors OKF
```

La base générale ne contient rien d'un client, et une base de client ne recopie pas la base générale. La Knowledge Base générale n'indexe que `general/` ; chaque client a sa propre Knowledge Base, construite à partir de `clients/<client_id>/`.

[Retour à l'architecture](README.md)
