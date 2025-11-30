# maintenance.py
import os
from supabase import create_client

def ping_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("Erreur : Credentials manquants")
        return

    print("Tentative de connexion à Supabase...")
    supabase = create_client(url, key)
    
    # Simple lecture pour générer de l'activité API
    response = supabase.table("attendance_sessions").select("session_id").limit(1).execute()
    print(f"Ping réussi ! Données reçues : {len(response.data)} ligne(s)")

if __name__ == "__main__":
    ping_supabase()
