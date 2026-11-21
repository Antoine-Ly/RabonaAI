import type { Session } from "@supabase/supabase-js";
import { useCallback, useEffect, useState } from "react";
import { supabase } from "../lib/supabase";

/** Session Supabase : connexion par e-mail et mot de passe, sans création de compte (accès sur invitation). */
export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(supabase !== null);

  useEffect(() => {
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);

  /** Renvoie un message d'erreur à afficher, ou `null` si la connexion a réussi. */
  const signIn = useCallback(async (email: string, password: string): Promise<string | null> => {
    if (!supabase) return "Supabase n'est pas configuré.";
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (!error) return null;
    if (error.status === 400) return "E-mail ou mot de passe incorrect.";
    return "Connexion impossible pour le moment. Réessaie dans un instant.";
  }, []);

  const signOut = useCallback(async () => {
    await supabase?.auth.signOut();
  }, []);

  /** Jeton à jour (rafraîchi par le client Supabase si besoin), pour l'en-tête Bearer. */
  const getToken = useCallback(async (): Promise<string | null> => {
    if (!supabase) return null;
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }, []);

  return { configured: supabase !== null, session, loading, signIn, signOut, getToken };
}
