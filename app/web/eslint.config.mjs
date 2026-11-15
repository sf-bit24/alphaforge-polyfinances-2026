import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * Règles de code propre du projet : fonctions courtes et peu imbriquées, peu de paramètres,
 * pas de ternaire imbriqué, noms conformes aux conventions TypeScript et React.
 */
const cleanCode = {
  files: ["src/**/*.{ts,tsx}"],
  rules: {
    complexity: ["error", 15],
    "max-depth": ["error", 3],
    "max-lines-per-function": ["error", { max: 50, skipBlankLines: true, skipComments: true }],
    "max-params": ["error", 4],
    "max-lines": ["error", { max: 400, skipBlankLines: true, skipComments: true }],
    "no-nested-ternary": "error",
    "no-else-return": "error",
    "@typescript-eslint/naming-convention": [
      "error",
      { selector: "default", format: ["camelCase"], leadingUnderscore: "allow" },
      { selector: "import", format: ["camelCase", "PascalCase"] },
      { selector: "variable", format: ["camelCase", "PascalCase", "UPPER_CASE"], leadingUnderscore: "allow" },
      { selector: "function", format: ["camelCase", "PascalCase"] },
      { selector: "parameter", format: ["camelCase", "PascalCase"], leadingUnderscore: "allow" },
      { selector: "typeLike", format: ["PascalCase"] },
      { selector: "enumMember", format: ["PascalCase", "UPPER_CASE"] },
      // Le contrat avec les runtimes (CONTRACTS.md) est en snake_case : ses clés gardent leur forme,
      // y compris quand on les lit par déstructuration.
      { selector: ["objectLiteralProperty", "typeProperty", "objectLiteralMethod", "typeMethod"], format: null },
      { selector: "variable", modifiers: ["destructured"], format: null },
      { selector: "parameter", modifiers: ["destructured"], format: null },
    ],
  },
};

/** Tables de textes des deux langues : longues par nature. */
const dataModules = {
  files: ["src/lib/i18n/dictionary.ts", "src/lib/i18n/portfolio.ts", "src/lib/i18n/screens.ts"],
  rules: { "max-lines": "off" },
};

/**
 * Code arrivé sur master pendant le refactor de code propre (écran du portefeuille simulé, PR #52) :
 * pas encore mis aux règles. Retirer un dossier de la liste une fois refait.
 */
const pendingCleanup = {
  name: "alphaforge/pending-cleanup",
  files: ["src/components/portfolio/**"],
  rules: Object.fromEntries(Object.keys(cleanCode.rules).map((rule) => [rule, "off"])),
};

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  cleanCode,
  dataModules,
  pendingCleanup,
  globalIgnores([".next/**", "out/**", "build/**", "coverage/**", "next-env.d.ts"]),
]);

export default eslintConfig;
