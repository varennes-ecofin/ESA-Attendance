# ESA Attendance

Système d'appel par QR code pour le Master ESA (Économétrie et Statistique
Appliquée), Université d'Orléans. L'enseignant ouvre une session depuis son
tableau de bord, projette le QR code, et les étudiants émargent depuis leur
téléphone. La liste se remplit en direct et peut être envoyée au secrétariat.

Streamlit pour l'interface, Supabase (PostgreSQL) pour les données de présence,
fichiers CSV pour le référentiel des étudiants et des cours.

## Comment ça fonctionne

1. L'enseignant se connecte, choisit un cours et ouvre une session d'appel.
   Toute session qu'il aurait laissée ouverte est fermée au passage.
2. Le QR code pointe vers `?mode=student&session=<id>`, page publique sans
   authentification.
3. L'étudiant sélectionne son nom dans la liste de sa promotion et confirme.
   L'enregistrement passe par la fonction PostgreSQL `check_in()`, qui vérifie
   que la session est active et refuse les doublons côté serveur.
4. L'enseignant voit la liste se remplir, l'exporte en CSV ou l'envoie par mail,
   puis ferme la session.

## Arborescence

```
app.py                      point d'entrée, navigation par rôle
pyproject.toml              paquet esa-attendance (layout src/)
requirements.txt            dépendances pour Streamlit Cloud
sql/                        migrations à passer dans l'éditeur SQL Supabase
scripts/                    utilitaires hors application
src/esa_attendance/
├── config.py               secrets → objet Settings typé
├── auth.py                 hachage bcrypt, résolution des rôles
├── data/repository.py      accès Supabase : sessions, présences, statistiques
├── roster/                 référentiel CSV
│   ├── models.py           Student, Course, diff, codes de cours
│   ├── csv_io.py           lecture robuste, validation, sérialisation
│   ├── store.py            stockage local ou bucket Supabase
│   └── service.py          import, versionnement, année active
├── services/               analytique d'assiduité, envoi de courriel
└── ui/                     pages Streamlit
```

## Installation locale

Python 3.10 ou plus.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
streamlit run app.py
```

L'application doit être lancée **depuis la racine du projet** : le chemin du
référentiel local est relatif au répertoire courant.

`pip install -e .` est facultatif — `app.py` ajoute `src/` au chemin
d'import — mais recommandé en développement.

## Configuration

Tout se trouve dans `.streamlit/secrets.toml`, jamais versionné.

```toml
base_url = "https://esa-attendance.streamlit.app"   # ou http://localhost:8501

[supabase]
url         = "https://xxxxx.supabase.co"
key         = "…"   # clé anon, utilisée par la page étudiant
service_key = "…"   # clé service_role, utilisée par les pages authentifiées

[roster]
backend   = "supabase"    # "local" en développement
bucket    = "roster"      # bucket privé Supabase Storage
local_dir = "data/roster" # utilisé quand backend = "local"

[admins]
secretariat = "$2b$12$…"  # accès au référentiel et à l'année universitaire

[teachers]
gdt = "$2b$12$…"          # accès à l'appel et à l'assiduité

[email]
sender          = "…"
password        = "…"     # mot de passe d'application Gmail
smtp_server     = "smtp.gmail.com"
smtp_port       = 587
recipient_email = ["secretariat@univ-orleans.fr"]
```

Pour produire une empreinte de mot de passe :

```powershell
python -m esa_attendance.auth 'le mot de passe'
```

Les anciennes empreintes SHA-256 restent acceptées pour la transition, mais
l'application signale qu'elles doivent être regénérées.

**Après toute modification des secrets, redémarrer le serveur** : les valeurs
sont mises en cache au premier import et un simple rechargement de page ne les
relit pas.

## Le référentiel

Les étudiants et les cours vivent dans des CSV, pas en base. Le stockage est
interchangeable : un dossier local en développement, un bucket privé Supabase
Storage en production — le système de fichiers de Streamlit Cloud étant
éphémère, un fichier téléversé et écrit sur disque y disparaîtrait au premier
redémarrage.

```
manifest.json                         année active
2026-2027/students.csv                academic_year, level, student_id, name
2026-2027/courses.csv                 code, name, level, active
2026-2027/backups/students-….csv      sauvegarde horodatée à chaque écriture
```

Aucune adresse électronique n'est conservée : l'application n'écrit jamais aux
étudiants.

### Étudiants

L'import se fait **par niveau**, depuis le fichier d'inscription de la
scolarité tel quel — l'en-tête est localisé même sous une ligne de titre, les
colonnes de courriel sont ignorées, nom et prénom sont recomposés en
« NOM Prénom ». M2 est connu tôt, M1 bouge jusqu'en octobre : remplacer une
promotion ne touche pas l'autre.

Un aperçu montre les arrivées, les sorties et les statuts d'inscription avant
toute écriture. L'onglet d'édition gère les exceptions : inscription tardive,
abandon, correction d'orthographe.

Les identifiants sont attribués automatiquement (`m1_007`) et réattribués aux
étudiants déjà présents, repérés par leur nom : un réimport en cours d'année ne
renumérote personne et n'orpheline aucune présence.

### Cours

Le code d'un cours (`ESA1PR03`) est la clé qui relie les séances au catalogue.
Il n'est donc jamais modifiable, et le code d'un cours supprimé n'est jamais
réattribué. Retirer un cours de la maquette se fait en le **désactivant** : il
quitte le menu des enseignants et reste lisible dans l'historique. L'interface
refuse la suppression d'un code auquel des séances font référence.

Un cours nouveau reçoit son code à partir du niveau et du domaine choisis
(`ESA` + chiffre du niveau + deux lettres + numéro d'ordre).

## Base de données

Deux tables, `attendance_sessions` et `attendance_records`, chacune portant une
colonne `academic_year` remplie par déclencheur. Les migrations sont dans
`sql/`, à passer dans l'éditeur SQL Supabase, dans l'ordre :

| Fichier | Rôle |
|---|---|
| `000_preflight.sql` | inspection en lecture seule, à passer d'abord |
| `001_rollover_and_hardening.sql` | colonnes d'année, nettoyage, vues d'agrégation, `check_in()`, `purge_academic_year()` |
| `002_rls_lockdown.sql` | verrouillage RLS — **casse l'ancien chemin d'émargement**, à passer une fois la v2 déployée |

### Sécurité

Le rôle `anon`, porté par la page publique, ne peut ni lire ni écrire dans
`attendance_records` : seule la fonction `check_in()`, exécutée avec les droits
du définisseur, y insère. Il ne voit des sessions que celles qui sont actives.
Le rôle `service_role`, utilisé par les pages authentifiées, contourne RLS.

Conséquence pratique : un ancien QR code ne permet plus rien une fois la
session fermée.

## Déploiement sur Streamlit Cloud

Fichier principal `app.py`. Les secrets se collent dans les réglages de
l'application, au format ci-dessus, avec `base_url` pointant sur l'URL du
déploiement et `backend = "supabase"`.

Streamlit Cloud installe depuis `requirements.txt` sans exécuter
`pip install .` : `app.py` ajoute `src/` au chemin d'import pour que le layout
`src/` fonctionne quand même.

## Procédure de rentrée

1. **Référentiel** → nouvelle année → importer le catalogue de cours de l'année
   précédente, puis l'ajuster dans l'onglet d'édition.
2. **Référentiel** → importer la liste M2, puis la liste M1 dès qu'elle est
   stabilisée.
3. **Année universitaire** → enregistrer la nouvelle année active.
4. **Année universitaire** → exporter l'archive CSV de l'année écoulée, la
   vérifier, puis la purger.

L'année active est enregistrée dans le manifeste. Tant qu'elle ne l'est pas,
elle est déduite de la date du jour et bascule seule au 1er septembre :
l'interface le signale.

## Scripts

| Script | Usage |
|---|---|
| `scripts/sync_roster.py` | copie le référentiel entre le disque local et le bucket, dans les deux sens |
| `scripts/export_legacy_roster.py` | convertit l'ancien `utils/courses.py` en CSV (migration v1 → v2, sans objet ensuite) |

## Limites connues

- Un étudiant sélectionne son nom dans une liste : rien ne l'empêche d'émarger
  pour un camarade. Le QR code, affiché en séance et valable le temps de la
  session, est la seule barrière.
- La réservation des codes de cours ne porte que sur le catalogue de l'année
  éditée. Conserver plusieurs années en base supposerait de l'étendre à
  l'union des catalogues.
- Les treize domaines de codes sont figés dans `roster/models.py` ; une famille
  nouvelle demande une ligne de code.
- `services/analytics.py` compte au dénominateur toutes les séances fermées des
  cours retenus : un cours optionnel doit être exclu explicitement de la
  sélection.

## Licence

MIT.
