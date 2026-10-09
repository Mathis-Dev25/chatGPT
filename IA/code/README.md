# Atelier : une IA qui apprend à reconnaître des chiffres

Ce programme accompagne le cours PowerPoint. Il construit un réseau de neurones
avec **NumPy**, puis l'entraîne sur de petites images de chiffres. **scikit-learn**
fournit uniquement les données et la séparation des exemples : il n'entraîne pas
le modèle. L'interface utilise **PySide6**.

## Installation

Utilisez **Python 3.11 ou 3.12**, de préférence en version 64 bits, et une session
graphique Windows, macOS ou Linux. Ouvrez un terminal dans ce dossier `code`.

Sous Windows :

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Sous macOS ou Linux :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

L'installation des bibliothèques nécessite Internet. Le jeu de données est déjà
inclus dans scikit-learn : l'application fonctionne ensuite sans téléchargement,
sans clé d'API et sans GPU. Une machine distante sans écran peut exécuter le modèle
en ligne de commande ; pour utiliser les boutons, ouvrez l'application sur votre
ordinateur ou dans une session de bureau distante.

## Découvrir l'interface

1. Conservez **60 époques** et un taux d'apprentissage de **0,100** pour reproduire
   le cours. Un lot contient 32 images. Chaque lancement réinitialise les poids.
2. Cliquez sur **Démarrer l'apprentissage**. Une époque correspond à un passage
   sur les images d'apprentissage. La perte orange devrait baisser ; le taux de
   réussite de validation vert devrait augmenter.
3. Attendez la fin, puis cliquez sur **Prédire**. Le réseau reconnaît une image
   de validation déjà fournie. **Autre image** change l'exemple ; le bouton ne permet
   pas de dessiner ni d'importer une image personnelle. L'exploration interactive
   utilise uniquement la validation ; le test reste réservé au bouton final.
4. Après avoir fixé tous les choix du modèle, cliquez sur **Évaluer le test final**.
   Ne choisissez pas les paramètres en fonction de ce score : utilisez la
   validation pendant vos essais.
5. **Sauvegarder le modèle** conserve les poids dans un fichier `.npz`.
   **Charger un modèle** les restaure. Le fichier contient les poids, pas les
   courbes ni l'historique. Le test affiché n'est interprétable que pour un modèle
   entraîné avec la même séparation des données, sans avoir utilisé ce test.

**Annuler** arrête le travail entre deux mini-lots. Le modèle partiel est abandonné.
Le calcul tourne dans un `QThread` pour garder la fenêtre réactive.

## Les fichiers à lire

| Fichier | Rôle |
| --- | --- |
| `model.py` | Données, calcul des sorties, gradients, entraînement et sauvegarde |
| `app.py` | Fenêtre, boutons, courbes, worker d'entraînement |
| `test_model.py` | Six tests portant sur les maths, l'apprentissage et les fichiers |
| `requirements.txt` | Versions des bibliothèques utilisées pour le cours |

Commencez par `load_data`, puis `Network.forward`, `loss_and_gradients` et
`train_epoch`. Les noms `w1` et `w2` désignent les poids ; `b1` et `b2` les biais.
Le réseau possède **2 410 paramètres** : 64 × 32 + 32 + 32 × 10 + 10.

## Données et résultats de référence

`load_digits()` contient **1 797 images de 8 × 8 pixels**, avec des intensités de
0 à 16. On divise par 16 pour obtenir des nombres entre 0 et 1. Cette borne est
connue à l'avance : aucune statistique n'est apprise sur la validation ou le test.

La séparation stratifiée conserve approximativement la proportion de chaque
chiffre : **1 078** images pour l'apprentissage, **359** pour la validation et
**360** pour le test. Le premier tirage utilise la graine 42, le second la graine
43. Les indices des trois groupes sont distincts. L'initialisation des poids et
l'ordre des mini-lots utilisent chacun un générateur NumPy de graine 42.

Exécution de référence, versions de `requirements.txt`, 60 époques, taux 0,1,
mini-lots de 32, réseau `64 → 32 → 10` :

| Mesure | Résultat observé |
| --- | --- |
| Perte d'apprentissage initiale | 2,4432 |
| Perte d'apprentissage finale | 0,0420 |
| Réussite d'apprentissage finale | 99,54 % |
| Réussite de validation finale | 95,26 % |
| Réussite du test final | 97,50 %, soit 351 / 360 |

Ces résultats concernent ce découpage, pas tous les chiffres possibles. Le test
peut obtenir un score légèrement supérieur à la validation par variation
d'échantillonnage. Une probabilité softmax élevée n'est pas une garantie de
justesse. Un autre environnement numérique peut introduire de petits écarts.

## Ligne de commande et vérifications

Remplacez `python` par le chemin du Python de votre environnement virtuel si
celui-ci n'est pas activé.

```bash
python model.py --epochs 60 --lr 0.1 --batch-size 32 --seed 42 --output metrics.json --save-model mon_reseau.npz
python -m unittest -v
```

Le script calcule les mesures de validation après chaque époque, puis utilise
le test **une seule fois à la fin** pour l'évaluation finale et sa matrice de
confusion. Dans cette matrice, les lignes sont les vraies classes et les colonnes
les prédictions. Les six tests vérifient la séparation des données, les gradients
par différences finies, la stabilité softmax, l'amélioration de l'apprentissage,
l'annulation et la sauvegarde/restauration avec refus des poids invalides.

L'interface refuse la prédiction pendant l'entraînement. La restauration utilise
`np.load(..., allow_pickle=False)` et vérifie les dimensions et les valeurs finies.
Utilisez uniquement des fichiers de modèle d'origine connue.

## Pourquoi le modèle apprend

Pour un mini-lot, `x` a la forme `(nombre_images, 64)`.

```python
z1 = x @ w1 + b1
hidden = np.maximum(0, z1)  # ReLU
logits = hidden @ w2 + b2
```

Softmax transforme les scores en probabilités dont la somme vaut 1. L'entropie
croisée mesure l'erreur par rapport à la vraie classe. La rétropropagation calcule
la dérivée de cette erreur par rapport à chaque poids. La descente de gradient
met ensuite chaque paramètre à jour :

```python
poids = poids - taux_apprentissage * gradient
```

Dans le code réel, le calcul utilise une version stable de log-softmax : on
soustrait le plus grand score avant l'exponentielle. Aucun appel à `fit()` ni
service distant ne cache les étapes du réseau.

## Pour aller plus loin

Comparez 10 et 60 époques, puis deux taux d'apprentissage sur **la validation**.
Notez les réglages avant d'observer le test. Essayez ensuite d'ajouter une matrice
de confusion à l'interface. L'import d'un dessin personnel demande aussi un
prétraitement cohérent : centrage, redimensionnement à 8 × 8 et même échelle
d'intensité. Ce projet n'est ni un chatbot ni un modèle de langage.

Sources : [jeu de données digits](https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_digits.html),
[NumPy](https://numpy.org/doc/stable/),
[Qt for Python](https://doc.qt.io/qtforpython-6/).
