# Cours : créer une IA qui apprend en Python

Un **PowerPoint de 32 diapositives en français**, pour un atelier d’environ deux heures,
accompagné d’une application de bureau, du code commenté et d’exercices corrigés.
Niveau : débutant en Python, à condition de connaître les variables, les fonctions
et les boucles. Les détails de rétropropagation sont une partie facultative.

## Commencer

1. Ouvrir `livrables/Cours_IA_Python_Reseau_Neurones.pptx` dans PowerPoint ou LibreOffice Impress.
2. Consulter les **notes du présentateur**, sous chaque diapositive : elles contiennent
   les explications détaillées et les conseils de manipulation.
3. Utiliser le PDF du même nom pour une lecture sans logiciel de présentation.
4. Lire `code/README.md` pour installer et lancer l’application.

Dans un terminal ouvert dans le dossier `code`, sous Windows :

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Sous Linux ou macOS :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Python **3.12** est la version utilisée pour la vérification. Une session graphique
est nécessaire pour afficher les boutons. L’installation nécessite Internet ;
le jeu de données est ensuite disponible localement, sans clé API ni GPU.

## Ce que l’on construit

Le réseau est codé avec **NumPy**, étape par étape, sans appel à un entraînement
prédéfini de scikit-learn : 64 pixels → 32 neurones ReLU → 10 sorties softmax.
scikit-learn fournit les images et la séparation des ensembles. PySide6 fournit
la fenêtre et les signaux du worker d’entraînement.

La démonstration interactive utilise des **images de validation**. Le test reste
réservé au bouton d’évaluation finale, après le choix des réglages. L’application
ne propose pas de zone de dessin ni d’import de photos personnelles.

## Contenu

| Chemin | Contenu |
| --- | --- |
| `livrables/*.pptx` | Cours éditable, avec notes pédagogiques |
| `livrables/*.pdf` | Version de lecture, mêmes 32 diapositives |
| `code/model.py` | Données, réseau, gradients et boucle d’apprentissage |
| `code/app.py` | Petite interface graphique complète |
| `code/test_model.py` | Six tests automatiques |
| `EXERCICES_ET_CORRIGES.md` | Manipulations détaillées et corrections |
| `support/metrics.json` | Mesures réellement obtenues à chaque époque |
| `support/modele-demo.npz` | Poids de l’expérience de référence, chargeables dans l’interface |
| `support/interface.png` | Capture réelle de l’application après apprentissage |
| `support/generate_course.py` | Source de génération du PowerPoint |

## Résultats et validation

Expérience de référence : graine 42, 60 époques, lots de 32, taux d’apprentissage
0,1, réseau 64 → 32 → 10. Répartition : 1 078 images d’apprentissage,
359 de validation et 360 de test.

- Exactitude finale d’apprentissage : **99,54 %**.
- Exactitude finale de validation : **95,26 %**.
- Exactitude finale de test : **97,50 %**, soit **351 / 360** bonnes réponses.

Ces valeurs décrivent une expérience, pas une garantie sur d’autres images.
Le code a été vérifié sous Linux/Python 3.12. Les six tests réussissent.
L’interface a été exécutée hors écran pour vérifier l’apprentissage, la prédiction,
l’évaluation finale, l’annulation et la fermeture pendant le calcul. Le rendu des
32 diapositives a été contrôlé par export PDF. Les commandes Windows/macOS sont
fournies ; ces systèmes n’ont pas été exécutés dans cet environnement.

Depuis `code`, lancer les tests avec le Python installé dans votre environnement :

```bash
python -m unittest -v
```

Pour régénérer le PowerPoint, installer `support/requirements-generation.txt` dans
un environnement séparé et lancer `python support/generate_course.py` depuis la
racine du dossier. Les figures et le PowerPoint seront recalculés à partir de
`support/metrics.json` et de la capture existante. L’export PDF utilise un logiciel
de présentation (par exemple LibreOffice) et est fourni prêt à lire.
