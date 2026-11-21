import { describe, expect, it } from "vitest";
import { normalizeSpaces } from "./text";

describe("normalizeSpaces", () => {
  it("remplace les espaces insécables (fines ou non) par une espace normale", () => {
    expect(normalizeSpaces("Real\u202FMadrid – 13\u00A0buts :\u2009ok")).toBe("Real Madrid – 13 buts : ok");
  });

  it("laisse le reste du texte intact", () => {
    expect(normalizeSpaces("Équipe ⚽ – 3 buts\n- liste")).toBe("Équipe ⚽ – 3 buts\n- liste");
  });
});
