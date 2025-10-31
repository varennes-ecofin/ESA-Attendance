"""
Course and student data management
"""

# Static course data from Master ESA
# Each course is associated with a year (M1 or M2)
# Format: {"course_code": {"name": "Course Name", "year": "M1" or "M2"}}

COURSES = {
    # M1 Courses
    "ESA1AN01": {"name": "Analyse des données qualitatives: ACM", "year": "M1"},
    "ESA1ST01": {"name": "Apprentissage statistique et classification", "year": "M1"},
    "ESA1FI01": {"name": "Assurance et techniques actuarielles", "year": "M1"},
    "ESA1FI02": {"name": "Économie bancaire et ALM", "year": "M1"},
    "ESA1EC01": {"name": "Économétrie des données de panel", "year": "M1"},
    "ESA1EC02": {"name": "Économétrie des variables qualitatives", "year": "M1"},
    "ESA1EC03": {"name": "Économétrie des variables qualitatives TD", "year": "M1"},
    "ESA1EN01": {"name": "English for Business and TOEIC", "year": "M1"},
    "ESA1FI03": {"name": "Finance quantitative", "year": "M1"},
    "ESA1PR01": {"name": "Langage macro sous SAS", "year": "M1"},
    "ESA1ST02": {"name": "Méthodes de prévision", "year": "M1"},
    "ESA1PR02": {"name": "Nouvelles technologies sous R", "year": "M1"},
    "ESA1PR03": {"name": "Programmation Python", "year": "M1"},
    "ESA1PR04": {"name": "Programmation Python avancée", "year": "M1"},
    "ESA1PR05": {"name": "Programmation R", "year": "M1"},
    "ESA1PR06": {"name": "Programmation SAS", "year": "M1"},
    "ESA1PJ01": {"name": "Projets (Semestre 7)", "year": "M1"},
    "ESA1PJ02": {"name": "Projets (Semestre 8)", "year": "M1"},
    "ESA1SE01": {"name": "Séminaire partenariat entreprise: Data Visualisation", "year": "M1"},
    "ESA1SE02": {"name": "Séminaire partenariat entreprise: Métiers de la Data Science", "year": "M1"},
    "ESA1ST03": {"name": "Séries temporelles multivariées", "year": "M1"},
    "ESA1ST04": {"name": "Séries temporelles multivariées TD", "year": "M1"},
    "ESA1ST05": {"name": "Séries temporelles univariées", "year": "M1"},
    "ESA1ST06": {"name": "Séries temporelles univariées TD", "year": "M1"},
    "ESA1ST07": {"name": "Statistique avancée et méthodes de simulation", "year": "M1"},
    "ESA1ST08": {"name": "Statistique avancée et méthodes de simulation TD", "year": "M1"},
    "ESA1ST09": {"name": "Statistique mathématique", "year": "M1"},
    "ESA1ST10": {"name": "Statistique mathématique TD", "year": "M1"},
    
    # M2 Courses
    "ESA2FI01": {"name": "Advanced Financial Econometrics", "year": "M2"},
    "ESA2AS01": {"name": "Assurance et techniques actuarielles 2", "year": "M2"},
    "ESA2BD01": {"name": "BDA: Machine learning interprétable", "year": "M2"},
    "ESA2BD02": {"name": "BDA: NLP with Python", "year": "M2"},
    "ESA2BD03": {"name": "BDA: Neural Networks", "year": "M2"},
    "ESA2BD04": {"name": "BDA: Penalized regressions", "year": "M2"},
    "ESA2BD05": {"name": "BDA: Support Vector Machine", "year": "M2"},
    "ESA2BD06": {"name": "BDA: Trees & aggregation methods", "year": "M2"},
    "ESA2CO01": {"name": "Communication orale", "year": "M2"},
    "ESA2DM01": {"name": "Data Mining", "year": "M2"},
    "ESA2EC01": {"name": "Économétrie semi et non-paramétrique", "year": "M2"},
    "ESA2FI02": {"name": "Finance Durable", "year": "M2"},
    "ESA2FI03": {"name": "Financial Fraud Detection", "year": "M2"},
    "ESA2PR01": {"name": "Gestion de bases de données sous SAS", "year": "M2"},
    "ESA2DM02": {"name": "Méthodes de Scoring", "year": "M2"},
    "ESA2PR02": {"name": "Mise en œuvre de la proc SQL sous SAS", "year": "M2"},
    "ESA2EC02": {"name": "Modèles de durée", "year": "M2"},
    "ESA2FI04": {"name": "Modélisation du risque de crédit", "year": "M2"},
    "ESA2PJ01": {"name": "Projets Entreprises", "year": "M2"},
    "ESA2RE01": {"name": "Réglementation prudentielle bancaire", "year": "M2"},
    "ESA2SE01": {"name": "Séminaire entreprise: outils de lutte contre la fraude financière", "year": "M2"},
    "ESA2SE02": {"name": "Séminaire partenariat SAS", "year": "M2"},
    "ESA2FI05": {"name": "Techniques de modélisation pour l'ALM", "year": "M2"},
}

# Student data organized by year
# NOTE: Email field can be left empty ("") for privacy on public repositories
STUDENTS_BY_YEAR = {
    "M1": [
        {"id": "m1_001", "name": "AGONGNON Médéssé", "email": ""},
        {"id": "m1_002", "name": "BARRY Kadidiatou", "email": ""},
        {"id": "m1_003", "name": "BAUDOUIN Olivier", "email": ""},
        {"id": "m1_004", "name": "BEN YAGHLANE Aymen", "email": ""},
        {"id": "m1_005", "name": "BORDAIS Inès", "email": ""},
        {"id": "m1_006", "name": "CHATONNET Marius", "email": ""},
        {"id": "m1_007", "name": "CHEVRIER Léane", "email": ""},
        {"id": "m1_008", "name": "DABGO Jean Franck Sivere", "email": ""},
        {"id": "m1_009", "name": "DIALLO Fatoumata", "email": ""},
        {"id": "m1_010", "name": "DIALLO Mamadou Cherif", "email": ""},
        {"id": "m1_011", "name": "DOFFOU Eve Roxane", "email": ""},
        {"id": "m1_012", "name": "DONICI Cristian", "email": ""},
        {"id": "m1_013", "name": "DOSSOU Marie Claudine", "email": ""},
        {"id": "m1_014", "name": "GRASSI Carla", "email": ""},
        {"id": "m1_015", "name": "GUENIN Jarod", "email": ""},
        {"id": "m1_016", "name": "HOUENOU MIGAN Kponnou Martinien", "email": ""},
        {"id": "m1_017", "name": "KPONTON Emilie Lydie", "email": ""},
        {"id": "m1_018", "name": "MOHAMED ABDERRAHMANE Sidi", "email": ""},
        {"id": "m1_019", "name": "MOTIA Yassir", "email": ""},
        {"id": "m1_020", "name": "NAIT AKLI Abdellah", "email": ""},
        {"id": "m1_021", "name": "NGOMA-BANKADILA Roskane-Prestige", "email": ""},
        {"id": "m1_022", "name": "NKOUSSOL NSANGOU Petronie", "email": ""},
        {"id": "m1_023", "name": "NTETE NLANDU MATONDO Nephthali", "email": ""},
        {"id": "m1_024", "name": "ORY Gwezheneg", "email": ""},
        {"id": "m1_025", "name": "PEREIRA Tony", "email": ""},
        {"id": "m1_026", "name": "RUEL Quentin", "email": ""},
        {"id": "m1_027", "name": "SOUGOUMA Issa Haki", "email": ""},
        {"id": "m1_028", "name": "WGALE Loïc", "email": ""},
        {"id": "m1_029", "name": "ZARHOUNI JAURES Sabiha", "email": ""},
        {"id": "m1_030", "name": "ZETU Fabian", "email": ""},
    ],
    "M2": [
        {"id": "m2_001", "name": "ABOUBAKAR Ali Ibrahim", "email": ""},
        {"id": "m2_002", "name": "AGBANDJALA Akbar", "email": ""},
        {"id": "m2_003", "name": "AGBANGLA Brunille", "email": ""},
        {"id": "m2_004", "name": "AGOSSOU Arielle", "email": ""},
        {"id": "m2_005", "name": "BAZEMO Brigitte", "email": ""},
        {"id": "m2_006", "name": "CHABACH Younès", "email": ""},
        {"id": "m2_007", "name": "CHABOSSOU Annabelle Serena", "email": ""},
        {"id": "m2_008", "name": "CHIGBLO Gedeon", "email": ""},
        {"id": "m2_009", "name": "DAN BAKY Janna", "email": ""},
        {"id": "m2_010", "name": "DAOUIRI Nada", "email": ""},
        {"id": "m2_011", "name": "DIALLO Ousmane Djounnou", "email": ""},
        {"id": "m2_012", "name": "DUPRE Salomé", "email": ""},
        {"id": "m2_013", "name": "EL BOUZIDI Marwane", "email": ""},
        {"id": "m2_014", "name": "HAFIDI Nawal", "email": ""},
        {"id": "m2_015", "name": "HANI Laura", "email": ""},
        {"id": "m2_016", "name": "HOUNKANRIN Alex Romaric", "email": ""},
        {"id": "m2_017", "name": "KAKOU Siékoua", "email": ""},
        {"id": "m2_018", "name": "KARAPETYAN Marieta Hranti", "email": ""},
        {"id": "m2_019", "name": "KONAN Ahou", "email": ""},
        {"id": "m2_020", "name": "LACROIX Ewan", "email": ""},
        {"id": "m2_021", "name": "NAJDOVA Léa Aleksandra", "email": ""},
        {"id": "m2_022", "name": "NOEL Julien", "email": ""},
        {"id": "m2_023", "name": "NOUNI Atman Azzedine", "email": ""},
        {"id": "m2_024", "name": "PINHEIRO Mateo", "email": ""},
        {"id": "m2_025", "name": "RAKOTO Niiva", "email": ""},
        {"id": "m2_026", "name": "REGENT Alexandre", "email": ""},
        {"id": "m2_027", "name": "ROMAIN Canelle", "email": ""},
        {"id": "m2_028", "name": "SAID ABDALLAH Azir", "email": ""},
        {"id": "m2_029", "name": "TOGODO AZON Marlyse Sylovia", "email": ""},
    ],
}

# Try to load private student data from local file (not committed to GitHub)
# This allows you to keep emails private while committing names publicly
try:
    import os
    import json
    
    private_data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'students_private.json')
    if os.path.exists(private_data_path):
        with open(private_data_path, 'r', encoding='utf-8') as f:
            PRIVATE_STUDENTS = json.load(f)
            # Merge private data (with emails) into public data
            # Expected format: {"M1": [...], "M2": [...]}
            for year, students in PRIVATE_STUDENTS.items():
                if year in STUDENTS_BY_YEAR:
                    STUDENTS_BY_YEAR[year] = students
                else:
                    STUDENTS_BY_YEAR[year] = students
except Exception:
    # If loading fails, just use the public data above
    pass

def get_courses() -> dict:
    """
    Get all available courses
    
    Returns:
        Dictionary with course codes as keys and full course info (name + year) as values
        Format: {"ESA101": "Mathématiques Financières (M1)", ...}
    """
    return {code: f"{info['name']} ({info['year']})" for code, info in COURSES.items()}

def get_students(course_code: str) -> list:
    """
    Get list of students for a specific course based on its year
    
    Args:
        course_code: Code of the course (e.g., "ESA101")
        
    Returns:
        List of student dictionaries with id, name, and email
        Returns students from the year associated with the course (M1 or M2)
    """
    # Get the year associated with this course
    if course_code not in COURSES:
        # If course not found, return empty list
        return []
    
    year = COURSES[course_code]["year"]
    
    # Return students from that year
    return STUDENTS_BY_YEAR.get(year, [])

def add_student(year: str, student_id: str, name: str, email: str = "") -> bool:
    """
    Add a new student to a year (M1 or M2)
    
    Args:
        year: Year of the student ("M1" or "M2")
        student_id: Unique student identifier
        name: Student name
        email: Student email (optional, defaults to empty string)
        
    Returns:
        Success status
    """
    if year not in STUDENTS_BY_YEAR:
        STUDENTS_BY_YEAR[year] = []
    
    student = {
        "id": student_id,
        "name": name,
        "email": email
    }
    
    STUDENTS_BY_YEAR[year].append(student)
    return True

def import_students_from_csv(year: str, csv_path: str) -> bool:
    """
    Import students from a CSV file for a specific year
    Expected format: id,name,email
    
    Args:
        year: Year of the students ("M1" or "M2")
        csv_path: Path to CSV file
        
    Returns:
        Success status
    """
    try:
        import pandas as pd
        
        df = pd.read_csv(csv_path)
        
        if year not in STUDENTS_BY_YEAR:
            STUDENTS_BY_YEAR[year] = []
        
        for _, row in df.iterrows():
            student = {
                "id": str(row['id']),
                "name": row['name'],
                "email": row.get('email', "")  # Default to empty string if no email
            }
            STUDENTS_BY_YEAR[year].append(student)
        
        return True
        
    except Exception as e:
        print(f"Error importing students: {e}")
        return False
