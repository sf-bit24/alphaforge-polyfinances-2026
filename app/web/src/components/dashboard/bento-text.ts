/**
 * Texts of the profile tiles chosen from the ProfileView, as plain functions so they are tested
 * without a DOM (tests/issue-79-horizon-tile.test.ts).
 */

/** The runtime and the mock join the facts of a dimension's summary with « · » (`dimension_summary`, views.py). */
const SUMMARY_SEPARATOR = " · ";

export interface HorizonTileText {
  /** The tile's figure: the first fact of the summary, the horizon band (« De 3 à 10 ans »). */
  figure: string;
  /** The other facts, under the label (« Années avant le premier retrait important : … · Par étapes, … »). */
  details: string | null;
}

/**
 * The horizon tile splits the dimension's summary: once A1 refines the horizon (ranges, #75) the whole
 * summary runs to seven lines, too long for a figure, and the tile hid its label and the objective.
 * Nothing is dropped or rewritten: the facts keep their order and their words.
 */
export function horizonTileText(summary: string | null | undefined): HorizonTileText {
  if (!summary) return { figure: "—", details: null };
  const [figure = summary, ...rest] = summary.split(SUMMARY_SEPARATOR);
  return { figure, details: rest.length > 0 ? rest.join(SUMMARY_SEPARATOR) : null };
}
