import { ServerStatus } from "./components/ServerStatus";

export default function App() {
  return (
    <main className="page">
      <h1 className="page__title">RabonaAI</h1>
      <p className="page__lead">
        Un assistant football pour les classements, les résultats, les buteurs, l'histoire et la
        tactique.
      </p>
      <ServerStatus />
    </main>
  );
}
