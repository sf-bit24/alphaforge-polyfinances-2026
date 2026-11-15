import { describe, expect, it } from "vitest";
import { pathOf, PIXELS, YAN_COLS, YAN_ROWS, YAN_VIEW } from "@/components/yan/pixels";

const at = (x: number, y: number) => PIXELS.find((pixel) => pixel.x === x && pixel.y === y)?.color;

describe("Yan in pixels", () => {
  it("fits its grid, and the grid fits the drawing box with room to hover", () => {
    expect(PIXELS.every((pixel) => pixel.x >= 0 && pixel.x < YAN_COLS && pixel.y >= 0 && pixel.y < YAN_ROWS)).toBe(true);
    expect(YAN_COLS).toBe(YAN_VIEW.size);
    expect(-YAN_VIEW.y + YAN_ROWS).toBeLessThan(YAN_VIEW.size);
  });

  it("has a symmetric body: arms, feet and eyes mirror each other", () => {
    const body = PIXELS.filter((pixel) => pixel.color !== "spark");
    expect(body.every((pixel) => at(YAN_COLS - 1 - pixel.x, pixel.y) === pixel.color)).toBe(true);
  });

  it("has two eyes of three cells, on the body", () => {
    const eyes = PIXELS.filter((pixel) => pixel.color === "eye");
    expect(eyes).toHaveLength(6);
    expect(new Set(eyes.map((eye) => eye.x))).toEqual(new Set([5, 10]));
  });

  it("merges each row into runs: the arms' row is one run across", () => {
    expect(pathOf(["body"])).toContain("M0 7h16v1h-16z");
    expect(pathOf(["eye"])).toBe("M5 4h1v1h-1zM10 4h1v1h-1zM5 5h1v1h-1zM10 5h1v1h-1zM5 6h1v1h-1zM10 6h1v1h-1z");
  });
});
