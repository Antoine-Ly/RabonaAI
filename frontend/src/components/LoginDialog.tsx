import { type SubmitEvent, useState } from "react";
import { EyeIcon, EyeOffIcon } from "./icons";
import { LogoMark, Wordmark } from "./Logo";
import { ServerStatus } from "./ServerStatus";

interface Props {
  onSignIn: (email: string, password: string) => Promise<string | null>;
}

/** Fenêtre de connexion : e-mail et mot de passe seulement, les comptes se créent par invitation. */
export function LoginDialog({ onSignIn }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const message = await onSignIn(email.trim(), password);
    setError(message);
    setPending(false);
  }

  return (
    <div className="login-layer">
      <div className="login-pitch-clip" aria-hidden="true">
        <div className="login-pitch" />
      </div>
      <form className="login-card" onSubmit={handleSubmit} aria-labelledby="login-title">
        <header className="login-card__head">
          <LogoMark size={96} />
          <h1 id="login-title" className="login-card__title">
            <Wordmark />
          </h1>
          <p className="login-card__lead">L'assistant football. Accès sur invitation.</p>
        </header>

        <div className="field">
          <label htmlFor="login-email">E-mail</label>
          <input
            id="login-email"
            className="input"
            type="email"
            autoComplete="username"
            inputMode="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="login-password">Mot de passe</label>
          <div className="input-wrap">
            <input
              id="login-password"
              className="input"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              className="input-wrap__toggle"
              aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((v) => !v)}
            >
              {showPassword ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </div>
        </div>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="button button--primary" disabled={pending}>
          {pending ? "Connexion…" : "Se connecter"}
        </button>
        <ServerStatus />
      </form>
    </div>
  );
}
