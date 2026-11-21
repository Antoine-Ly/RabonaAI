import markUrl from "../assets/rabonaai-mark.png";

/** Symbole seul (décoratif : le nom est toujours écrit à côté ou dans le titre de la page). */
export function LogoMark({ size }: { size: number }) {
  return <img className="logo-mark" src={markUrl} alt="" width={size} style={{ width: size, height: "auto" }} />;
}

export function Wordmark() {
  return (
    <span className="wordmark">
      Rabona<span className="wordmark__ai">AI</span>
    </span>
  );
}
