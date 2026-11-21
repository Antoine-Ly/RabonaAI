import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

/** `null` si les variables publiques Supabase ne sont pas renseignées (`.env.local`). */
export const supabase = url && anonKey ? createClient(url, anonKey) : null;
