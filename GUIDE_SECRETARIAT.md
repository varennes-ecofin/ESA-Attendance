# Guide du secrétariat — ESA Attendance

Ce document s'adresse aux personnes disposant du rôle **administrateur** dans
l'application d'appel du Master ESA. Il décrit les deux pages réservées à ce
rôle : la gestion du référentiel et celle de l'année universitaire.

Adresse de l'application : <https://esa-attendance.streamlit.app>

## Ce que fait l'application

Un enseignant ouvre une session d'appel et projette un QR code. Les étudiants le
scannent, choisissent leur nom dans la liste de leur promotion et confirment
leur présence. L'enseignant peut ensuite envoyer la feuille de présence par
courriel ou la télécharger.

Pour que cela fonctionne, l'application a besoin de deux listes à jour : les
**étudiants** de chaque promotion et les **cours** de la maquette. C'est le
rôle de l'administrateur de les tenir.

## Se connecter

Identifiant et mot de passe personnels. Quatre entrées apparaissent dans le
menu de gauche pour un administrateur : *Appel*, *Assiduité*, *Référentiel* et
*Année universitaire*. Les enseignants ne voient que les deux premières.

La connexion expire au bout de douze heures.

## Page « Référentiel »

### Onglet Étudiants

Le niveau se choisit avec le bouton **M1 / M2** en haut : toute opération ne
concerne que ce niveau, l'autre reste intact. C'est voulu — la liste des M2 est
connue en juillet, celle des M1 continue de bouger jusqu'en octobre.

**Importer une liste.** Déposez le fichier d'inscription tel que vous l'avez
reçu, en Excel ou en CSV. Il n'y a rien à préparer : le titre au-dessus de
l'en-tête, la colonne de numérotation et les colonnes d'adresses sont ignorés.
Seuls le nom et le prénom sont lus, et recomposés en « NOM Prénom ».

Une case permet de ne retenir que les étudiants dont l'inscription
administrative est confirmée. Décochée, tout le monde est importé et les
statuts inhabituels sont simplement signalés.

**Avant de confirmer, lisez l'aperçu.** Il indique combien d'étudiants sont
retenus, combien arrivent, combien sortent, et récapitule les statuts trouvés
dans le fichier. Les listes détaillées se déplient. Si ces chiffres ne
correspondent pas à ce que vous attendez, ne confirmez pas : c'est le signe
d'un fichier ou d'un niveau mal choisi. Tant que la case de confirmation n'est
pas cochée, rien n'est enregistré.

**Éditer la liste.** Pour les cas isolés : une inscription tardive, un abandon,
une faute d'orthographe. Le `+` en bas du tableau ajoute une ligne ; pour
retirer quelqu'un, sélectionnez la ligne et appuyez sur Suppr. Les
modifications en attente s'affichent nommément avant l'enregistrement.

Les identifiants sont attribués par l'application et ne se modifient pas.

### Onglet Cours

La maquette évolue peu : un ou deux cours ajoutés ou retirés d'une année sur
l'autre. L'onglet d'édition est donc présenté en premier.

**Ajouter un cours.** Le `+` en bas du tableau, puis le niveau, le domaine et
l'intitulé. Le code — `ESA1PR07` par exemple — est attribué à l'enregistrement.
Il n'y a jamais à le saisir.

**Retirer un cours.** Décochez la case **Actif** plutôt que de supprimer la
ligne. Le cours disparaît du menu des enseignants, mais les séances passées
restent lisibles dans les statistiques. La colonne *Séances* indique combien de
séances ont déjà été enregistrées sous ce code ; si elle n'est pas à zéro, la
suppression est refusée.

**Importer une maquette complète** remplace tout le catalogue. À réserver à la
mise en place d'une nouvelle année.

### Onglet Sauvegardes

Chaque enregistrement conserve automatiquement une copie horodatée de la
version précédente. En cas d'erreur d'import, sélectionnez la sauvegarde
voulue et restaurez : la liste actuelle est elle-même sauvegardée au passage,
la manœuvre est donc sans risque.

## Page « Année universitaire »

### Année active

C'est l'année à laquelle se rattachent les nouvelles séances d'appel et dont
les listes d'étudiants s'affichent. Elle ne change qu'une fois par an.

Importer des listes pour une année future ne bascule pas l'application : les
deux gestes sont séparés, ce qui permet de préparer la rentrée en août sans
perturber les cours en place.

### Archivage et purge

Les présences de l'année écoulée sont conservées jusqu'à ce qu'on décide de
les supprimer. La page se déroule en deux étapes, dans l'ordre :

1. **Exporter l'archive.** Un fichier CSV qui s'ouvre dans Excel. Ouvrez-le et
   vérifiez son contenu avant de continuer.
2. **Purger.** Il faut cocher une case et saisir l'année à la main. L'opération
   est **définitive** : une fois purgée, l'année n'est plus récupérable ailleurs
   que dans le fichier téléchargé.

L'année en cours n'apparaît jamais dans la liste des années purgeables.

### Entretien

Un bouton ferme les séances restées ouvertes depuis plus de douze heures. Une
séance oubliée continue d'accepter des émargements et n'entre dans aucune
statistique tant qu'elle n'est pas fermée.

## Le déroulé d'une année

| Quand | Quoi |
|---|---|
| Juillet | Référentiel → nouvelle année → importer le catalogue de cours, puis l'ajuster |
| Juillet | Référentiel → importer la liste M2 |
| Septembre | Référentiel → importer la liste M1, à réimporter autant que nécessaire |
| Septembre | Année universitaire → enregistrer la nouvelle année active |
| En cours d'année | Référentiel → éditer une liste pour un abandon ou une arrivée tardive |
| Après les jurys | Année universitaire → exporter l'archive, puis purger l'année écoulée |

## Bonnes pratiques

Lisez l'aperçu avant chaque confirmation : c'est le seul moment où une erreur
se voit sans conséquence. Téléchargez l'archive **et ouvrez-la** avant toute
purge. En cas de doute sur un import, restaurez la sauvegarde plutôt que de
réimporter à l'aveugle.

L'application ne conserve aucune adresse électronique d'étudiant : les colonnes
de courriel des fichiers d'inscription sont lues puis écartées.

## Ce que l'application ne fait pas

Supprimer une séance d'appel isolée, corriger une présence enregistrée à tort,
ou modifier un code de cours existant. Ces opérations demandent une
intervention technique — contactez le responsable de l'application.
