# Le langage de l'interface

Les clients d'AlphaForge AI sont des clients de la Banque Nationale. Ils ne connaissent rien à la technologie et n'ont pas à la connaître. Tout ce que l'écran affiche s'adresse à eux : textes, titres d'onglets, infobulles (`title`), `aria-label`, `placeholder`, messages d'erreur, textes écrits par les agents (questions, messages, étapes).

## La règle

Aucun mot technique à l'écran. Le client voit ce que le service fait pour lui, jamais comment il est construit.

Ne jamais afficher :

- un nom de service ou de fournisseur : AWS, AgentCore, Bedrock, Knowledge Base (le terme anglais), Guardrails, Cognito, Step Functions, Lambda, DynamoDB, S3, CloudWatch, X-Ray, OpenSearch, Next.js;
- un terme d'ingénierie : runtime, passerelle, gateway, API, endpoint, serveur, session, token, client_id, index, ingestion, réindexer, JSON, YAML, Markdown, CSV comme jargon, fichier `.md`, modèle, LLM, prompt, mode `mock`, `local` ou `aws`, fixture, version, release, environnement, déploiement, machine, exécution;
- un identifiant : UUID, ARN, numéro de décision, identifiant de règle (`strat.floor.TSLA[TSLA]:min`), chemin de fichier (`general/index.md`), nom de fichier de configuration (`strategy.yaml@0.1.0`), compte ou groupe technique (`alphaforge-a6`, `mock:simulateur`);
- un journal : données d'entrée et de sortie brutes, durées en millisecondes, codes d'erreur, piles d'appels, liens vers une console;
- un nom interne d'agent : A1, A2, A3, A4, A5, A6, « le Judge », « les lentilles », « l'étape 0 », « le moteur », « le code ».

Les écrans de l'équipe (lancer une collecte, état du service, versions) restent permis, mais seulement dans la vue équipe : `useOperator()` (`src/lib/client/account.tsx`), un compte connecté du groupe `admin`. Un client ne les voit jamais, et un navigateur sans connexion non plus.

## Le vocabulaire

| Interne | À l'écran (FR) | À l'écran (EN) |
| --- | --- | --- |
| A1, l'assistant, le modèle qui rédige | Yan, votre assistant | Yan, your assistant |
| A2 (lecture du portefeuille existant) | Yan lit votre portefeuille | Yan reads your portfolio |
| A3, le moteur, le volet finance | le simulateur | the simulator |
| le Judge, les contrôles du Judge | la vérification finale, les vérifications | the final check, the checks |
| les lentilles, le débat des lentilles | les quatre points de vue | the four viewpoints |
| l'étape 0, le style | le style du portefeuille | the portfolio style |
| A4, A5, A6, la collecte | notre veille : actualités et données, vérifiées (source et date) avant d'être ajoutées | our watch: news and data, checked (source and date) before they are added |
| Knowledge Base, index, réindexation | la base de connaissances, mise à jour | the knowledge base, updated |
| votre Knowledge Base personnelle | vos documents personnels | your personal documents |
| trace d'exécution | les étapes suivies, comment Yan a procédé | the steps taken, how Yan worked |
| session, client_id | votre profil sur cet appareil, votre compte | your profile on this device, your account |
| le code calcule, déterministe | calculé selon des règles fixes | computed with fixed rules |
| le modèle rédige | Yan rédige les phrases; les chiffres sont calculés, jamais inventés | Yan writes the sentences; the figures are computed, never made up |
| garde-fous, Guardrails | vérification des faits | fact check |
| runtime injoignable, erreur interne | le service ne répond pas pour l'instant : réessayez dans un instant | the service is not answering right now: try again in a moment |
| fichiers CSV, JSON, tableur | relevé, tableur, PDF ou photo | statement, spreadsheet, PDF or photo |

Les mots de la finance restent quand ils servent le client (FNB, actions, obligations, volatilité, rendement, les étiquettes FAIT, HYPOTHÈSE, FICTION). Le niveau de connaissances du profil règle déjà leur précision.

## Comment écrire

- Parler au client : « vous », « votre profil ». Phrases courtes, un seul message par phrase.
- Dire ce qui se passe pour lui, puis ce qu'il peut faire : « Nous n'avons pas pu lire ce fichier. Essayez une photo plus nette ou collez le texte. »
- Une erreur ne montre jamais de code ni de cause technique. Elle dit quoi faire.
- Une explication reste : le client a le droit de savoir pourquoi. On garde les étapes, les sources et les vérifications, dites simplement, sans les données brutes.
- Une source s'affiche par son titre et sa date, jamais par son chemin ou sa clé. Un lien web reste cliquable.
- Les deux langues changent ensemble : chaque texte français a son anglais.

## Le garde-fou

`tests/client-language.test.ts` parcourt les dictionnaires et échoue si un mot de la liste ci-dessus revient. Ajoutez-y un mot quand vous en trouvez un nouveau.
