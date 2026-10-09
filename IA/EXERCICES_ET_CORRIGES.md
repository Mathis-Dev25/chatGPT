# Exercices et corrigés

Le réseau corrigé et l’interface sont fournis. Pour apprendre, résoudre chaque
question avant de consulter sa correction. Les expériences utilisent uniquement
le train et la validation ; conserver le test pour le bilan final.

## A — Compter les paramètres (3 minutes)

On imagine un réseau **64 → 16 → 10**, avec un biais par neurone caché et par sortie.
Combien de nombres doit-il apprendre ? Cet exercice est un calcul : la version
fournie reste fixée à 32 neurones cachés.

**Correction :**

```text
Première couche : 64 × 16 poids + 16 biais = 1 040
Deuxième couche : 16 × 10 poids + 10 biais =   170
Total                                     = 1 210
```

Le nombre d’images d’un lot ne change pas le nombre de paramètres. Les exemples
partagent les mêmes poids.

## B — Comparer deux taux d’apprentissage (8 minutes)

1. Dans l’interface, choisir 20 époques et un taux de 0,010.
2. Lancer l’apprentissage et noter la perte de train et l’exactitude de validation.
3. Choisir 20 époques et un taux de 0,100, puis relancer.
4. Comparer les courbes, pas uniquement leur dernière valeur.
5. Expliquer pourquoi il ne faut pas consulter le test pour départager ces essais.

Chaque lancement de l’interface repart de la même initialisation et du même ordre
des lots : la comparaison change ici seulement le taux. Le programme en ligne de
commande calcule automatiquement le test à la fin ; employer **l’interface** pour
cette expérience afin de laisser ce test fermé.

**Correction attendue :** la réponse s’appuie sur les valeurs effectivement
observées. Le taux contrôle la taille des mises à jour : un petit taux peut
apprendre lentement, un grand taux peut être instable. Aucun score précis n’est
imposé pour réussir l’exercice. Le choix des réglages appartient à la validation ;
le test mesure ensuite le résultat du choix fixé.

## C — Diagnostiquer un écart (4 minutes)

Scénario **fictif**, distinct des mesures réelles du cours :

```text
Train      : 99,8 % de bonnes réponses
Validation : 86 %, et ce score baisse au fil des époques
```

Que peut-il se passer ? Quelle mesure proposer avant de continuer ?

**Correction :** c’est un signe possible de surapprentissage. Le réseau progresse
sur ses exemples d’apprentissage, mais généralise moins bien sur la validation.
Surveiller la perte de validation, garder un point antérieur et envisager un arrêt
anticipé. On peut ensuite étudier la régularisation ou une plus petite architecture.
Une seule fluctuation n’établit pas le diagnostic : observer une tendance. Ne pas
chercher le meilleur réglage en comparant les scores du test.

## D — Retrouver les trois scores les plus élevés (8 minutes)

La fonction `predict_sample()` de l’application corrigée affiche déjà les trois
premiers choix. Recréer cette fonction dans la console avant de lire sa solution.

**Départ :** pour une image de forme `(1, 64)`, `predict_proba(image)` renvoie une
matrice de forme `(1, 10)`. Prendre sa première ligne, trouver les trois indices
associés aux plus grands scores et afficher leurs pourcentages.

**Correction complète**, à exécuter depuis `code` avec les dépendances installées :

```python
from pathlib import Path
import numpy as np
from model import Network, load_data

data = load_data(seed=42)
model = Network.load(Path("../support/modele-demo.npz"))
image = data["x_val"][0:1]
probas = model.predict_proba(image)[0]

top3 = np.argsort(probas)[-3:][::-1]
for chiffre in top3:
    print(f"{chiffre} : {100 * probas[chiffre]:.1f} %")
```

`argsort` classe les indices par score croissant ; `[-3:]` garde les trois derniers,
et `[::-1]` inverse leur ordre. Les dix scores totalisent environ 1 ; la somme des
trois affichés peut être inférieure à 1. La prédiction ne change aucun poids.
Les probabilités softmax ne sont pas des garanties de justesse.

## Bonus — Vérifier une mise à jour à la main

Un poids vaut 0,5, son gradient vaut 0,2 et le taux vaut 0,1.

```text
nouveau poids = 0,5 − 0,1 × 0,2 = 0,48
```

Avec un gradient de −0,2, le nouveau poids vaut 0,52. Le gradient fixe une direction
locale et le taux fixe la taille du pas ; aucun des deux ne garantit que tout
l’entraînement convergera correctement.
