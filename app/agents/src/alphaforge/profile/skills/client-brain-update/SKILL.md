---
name: client-brain-update
description: >-
  Met à jour la base OKF d'un client quand ses faits changent ou quand la structure de client-brain-init change. Réécrit seulement les notes dont les champs cités ont changé, crée celles qui manquent, et déplace ou retire celles qui ne suivent plus la structure.
---

# client-brain-update : mettre à jour la base d'un client

La base existe déjà. La structure, la forme d'une note et les règles sont celles de **client-brain-init**, reproduites plus bas : elles font foi. Le contexte te donne :

- `documents` : les notes déjà écrites, avec leur chemin, leurs champs cités, la version du skill qui les a écrites et le contenu;
- `changed_fields` : les champs dont la valeur a changé depuis la dernière écriture (ajoutés, modifiés ou retirés);
- `skill_changed` : vrai si la structure a changé depuis la dernière écriture.

`delete_document` retire une note : elle sort de l'index et de la liste des documents.

## Procédure

1. Pour chaque note de `documents` qui cite un champ de `changed_fields`, réécris-la entièrement avec `write_document`, au même chemin.
2. Si un champ de `changed_fields` appartient à une dimension sans note, crée la note.
3. Si `skill_changed` est vrai, compare `documents` à la structure : écris les notes qui manquent, réécris aux nouveaux chemins celles qui ont changé de place, puis retire l'ancien chemin avec `delete_document`. Retire une note que la structure ne prévoit plus.
4. Réécris toujours `synthese.md` si une autre note a changé.
5. Ne réécris pas une note dont rien n'a changé. Lis une note avec `read_document` si son contenu actuel t'est utile.
6. Termine par `finish` avec un résumé d'une phrase : notes écrites, déplacées, retirées.
