import { describe, expect, it } from "vitest";
import { formatDuration, nextUtcMidnight } from "./time";

describe("formatDuration", () => {
  it("formate secondes, minutes et heures", () => {
    expect(formatDuration(20)).toBe("20 s");
    expect(formatDuration(90)).toBe("2 min");
    expect(formatDuration(7200)).toBe("2 h");
    expect(formatDuration(15120)).toBe("4 h 12");
  });
});

describe("nextUtcMidnight", () => {
  it("renvoie le prochain minuit UTC, y compris en fin de mois", () => {
    expect(nextUtcMidnight(new Date("2026-11-30T23:59:59Z")).toISOString()).toBe("2026-12-01T00:00:00.000Z");
    expect(nextUtcMidnight(new Date("2026-11-20T00:00:00Z")).toISOString()).toBe("2026-11-21T00:00:00.000Z");
  });
});
