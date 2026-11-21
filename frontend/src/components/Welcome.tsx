import { LogoMark, Wordmark } from "./Logo";

const SUGGESTIONS = [
  "Où en est la Ligue 1 au classement ?",
  "Quels sont les prochains matchs de Premier League ?",
  "Qui sont les meilleurs buteurs de Liga ?",
  "Qui a gagné la Coupe du monde 2018 ?",
  "Explique-moi la règle du hors-jeu.",
];

interface Props {
  disabled: boolean;
  onPick: (text: string) => void;
}

export function Welcome({ disabled, onPick }: Props) {
  return (
    <div className="welcome">
      <LogoMark size={120} />
      <h1 className="welcome__title">
        <Wordmark />
      </h1>
      <p className="welcome__lead">Classements, résultats, buteurs, histoire et tactique.</p>
      <ul className="suggestions">
        {SUGGESTIONS.map((text) => (
          <li key={text}>
            <button type="button" className="chip" disabled={disabled} onClick={() => onPick(text)}>
              {text}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
