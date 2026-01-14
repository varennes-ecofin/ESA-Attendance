# maintenance.py
import os
from datetime import datetime
from supabase import create_client

def ping_supabase():
    # On récupère les secrets. 
    # IMPORTANT : On essaie de récupérer la SERVICE_KEY pour avoir les droits d'écriture
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("❌ Erreur : Credentials manquants (URL ou KEY)")
        # On ne raise pas d'erreur pour ne pas faire échouer le workflow GitHub violemment,
        # mais on log l'erreur.
        exit(1)

    print(f"Connexion à Supabase... (URL: {url[:15]}...)")
    supabase = create_client(url, key)
    
    # 1. Définition des données fictives
    course_code = "ESA_MAINTENANCE"
    teacher_username = "system_bot"
    # Création d'un ID unique basé sur l'heure pour éviter les doublons
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    session_id = f"PING_{timestamp}"
    student_id = "bot_student"
    student_name = "System KeepAlive Bot"

    try:
        # 2. Création de la session (WRITE operation 1)
        print(f"Création de la session de maintenance : {session_id}")
        session_data = {
            "session_id": session_id,
            "course_code": course_code,
            "teacher_username": teacher_username,
            "status": "closed", # On la crée directement fermée pour ne pas gêner
            "started_at": datetime.now().isoformat(),
            "ended_at": datetime.now().isoformat()
        }
        
        res_session = supabase.table("attendance_sessions").insert(session_data).execute()
        
        if not res_session.data:
            print("⚠️ Avertissement : La session semble ne pas avoir été créée (pas de data retournée).")
        else:
            print("✅ Session créée avec succès.")

        # 3. Insertion d'une présence (WRITE operation 2)
        print("Insertion d'une présence fictive...")
        attendance_data = {
            "session_id": session_id,
            "student_id": student_id,
            "student_name": student_name,
            "checked_in_at": datetime.now().isoformat()
        }
        
        res_att = supabase.table("attendance_records").insert(attendance_data).execute()
        
        if res_att.data:
            print("✅ Présence enregistrée. Activité d'écriture confirmée.")
        else:
            print("⚠️ Présence non confirmée.")

        # 4. Nettoyage (Optionnel - Tu peux laisser commenter si tu veux garder les logs en base)
        # Pour Supabase, l'activité a déjà eu lieu (Insert). On peut supprimer pour garder la base propre.
        # print("Nettoyage des données de test...")
        # supabase.table("attendance_records").delete().eq("session_id", session_id).execute()
        # supabase.table("attendance_sessions").delete().eq("session_id", session_id).execute()
        # print("✅ Nettoyage terminé.")

    except Exception as e:
        print(f"❌ Erreur critique lors du ping : {str(e)}")
        # C'est ici qu'on verra si c'est une erreur de droits (RLS) ou autre
        exit(1)

if __name__ == "__main__":
    ping_supabase()
