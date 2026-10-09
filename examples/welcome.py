"""Un premier script à exécuter avec F5 dans Nexus Studio."""
from dataclasses import dataclass
from math import sqrt
from statistics import mean


@dataclass(frozen=True)
class Mission:
    nom: str
    progression: int


missions = [
    Mission("Explorer les données", 100),
    Mission("Connecter les idées", 75),
    Mission("Construire la suite", 40),
]

print("Bienvenue dans Nexus Studio !\n")
for mission in missions:
    barre = "█" * (mission.progression // 5)
    print(f"{mission.nom:25} {barre:20} {mission.progression:3}%")

print(f"\nProgression moyenne : {mean(m.progression for m in missions):.1f}%")
print(f"Racine carrée de 2 : {sqrt(2):.8f}")
print("\nModifiez ce script, puis appuyez sur F5 pour le relancer.")
