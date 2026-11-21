import { FauxChat } from "./components/FauxChat";
import { LoginDialog } from "./components/LoginDialog";
import { useSession } from "./hooks/useSession";
import { ChatPage } from "./pages/ChatPage";

export default function App() {
  const { configured, session, loading, signIn, signOut, getToken } = useSession();

  if (!configured) {
    return (
      <main className="splash">
        <h1>Configuration manquante</h1>
        <p>
          Renseigne <code>VITE_SUPABASE_URL</code> et <code>VITE_SUPABASE_ANON_KEY</code> dans{" "}
          <code>frontend/.env.local</code>, puis relance <code>npm run dev</code>.
        </p>
      </main>
    );
  }
  if (loading) return <main className="splash" aria-busy="true" aria-label="Chargement" />;
  if (!session) {
    return (
      <>
        <FauxChat />
        <LoginDialog onSignIn={signIn} />
      </>
    );
  }
  return <ChatPage email={session.user.email ?? ""} getToken={getToken} onSignOut={() => void signOut()} />;
}
