"""Petit réseau de neurones NumPy : chiffres manuscrits, sans téléchargement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split


def load_data(seed: int = 42) -> dict:
    """Séparation stratifiée : 60 % apprentissage, 20 % validation, 20 % test."""
    digits = load_digits()
    x = digits.data.astype(np.float64) / 16.0  # Intensités connues : 0…16.
    y = digits.target.astype(np.int64)
    train, rest = train_test_split(
        np.arange(len(y)), test_size=0.4, stratify=y, random_state=seed
    )
    val, test = train_test_split(
        rest, test_size=0.5, stratify=y[rest], random_state=seed + 1
    )
    result = {}
    for name, indices in (("train", train), ("val", val), ("test", test)):
        result[f"x_{name}"] = x[indices]
        result[f"y_{name}"] = y[indices]
        result[f"indices_{name}"] = indices
    return result


class Network:
    """64 entrées → 32 neurones ReLU → 10 probabilités softmax."""

    def __init__(self, seed: int = 42):
        rng = np.random.default_rng(seed)
        self.w1 = rng.normal(0, np.sqrt(2 / 64), (64, 32))
        self.b1 = np.zeros(32)
        self.w2 = rng.normal(0, np.sqrt(2 / 32), (32, 10))
        self.b2 = np.zeros(10)

    def forward(self, x):
        z1 = x @ self.w1 + self.b1
        hidden = np.maximum(0, z1)
        logits = hidden @ self.w2 + self.b2
        shifted = logits - logits.max(axis=1, keepdims=True)
        log_probs = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
        return z1, hidden, log_probs

    def predict_proba(self, x):
        return np.exp(self.forward(x)[2])

    def loss_and_gradients(self, x, y):
        z1, hidden, log_probs = self.forward(x)
        loss = -log_probs[np.arange(len(y)), y].mean()
        dz2 = np.exp(log_probs)
        dz2[np.arange(len(y)), y] -= 1
        dz2 /= len(y)
        dw2, db2 = hidden.T @ dz2, dz2.sum(axis=0)
        dz1 = (dz2 @ self.w2.T) * (z1 > 0)
        dw1, db1 = x.T @ dz1, dz1.sum(axis=0)
        return float(loss), {"w1": dw1, "b1": db1, "w2": dw2, "b2": db2}

    def evaluate(self, x, y):
        log_probs = self.forward(x)[2]
        return {
            "loss": float(-log_probs[np.arange(len(y)), y].mean()),
            "accuracy": float((log_probs.argmax(axis=1) == y).mean()),
        }

    def train_epoch(self, x, y, lr, batch_size, rng, cancel=lambda: False):
        """Un passage sur le train ; False signifie une annulation entre lots."""
        order = rng.permutation(len(y))
        for start in range(0, len(y), batch_size):
            if cancel():
                return False
            indices = order[start:start + batch_size]
            _, gradients = self.loss_and_gradients(x[indices], y[indices])
            for name, gradient in gradients.items():
                setattr(self, name, getattr(self, name) - lr * gradient)
        return True

    def save(self, path):
        with open(path, "wb") as file:
            np.savez_compressed(file, version=np.array(1),
                                w1=self.w1, b1=self.b1, w2=self.w2, b2=self.b2)

    @classmethod
    def load(cls, path):
        """Refuse pickle, tailles incorrectes et valeurs non finies."""
        model = cls()
        with np.load(path, allow_pickle=False) as saved:
            if set(saved.files) != {"version", "w1", "b1", "w2", "b2"}:
                raise ValueError("Fichier de modèle incomplet ou incompatible.")
            if saved["version"].shape != () or saved["version"].item() != 1:
                raise ValueError("Version de modèle inconnue.")
            for name in ("w1", "b1", "w2", "b2"):
                value = saved[name]
                if (value.shape != getattr(model, name).shape
                        or value.dtype.kind != "f" or not np.isfinite(value).all()):
                    raise ValueError(f"Paramètre invalide : {name}")
                setattr(model, name, value.astype(np.float64))
        return model


def run_experiment(epochs=60, lr=0.1, batch_size=32, seed=42):
    data, model = load_data(seed), Network(seed)
    rng = np.random.default_rng(seed)
    initial = model.evaluate(data["x_train"], data["y_train"])
    history = []
    for epoch in range(1, epochs + 1):
        model.train_epoch(data["x_train"], data["y_train"], lr, batch_size, rng)
        train = model.evaluate(data["x_train"], data["y_train"])
        val = model.evaluate(data["x_val"], data["y_val"])
        history.append({"epoch": epoch, "train_loss": train["loss"],
                        "train_accuracy": train["accuracy"], "val_loss": val["loss"],
                        "val_accuracy": val["accuracy"]})
    # Le test n'intervient jamais dans les mises à jour ni le suivi par époque.
    test = model.evaluate(data["x_test"], data["y_test"])
    prediction = model.predict_proba(data["x_test"]).argmax(axis=1)
    matrix = np.zeros((10, 10), dtype=int)
    np.add.at(matrix, (data["y_test"], prediction), 1)
    report = {"seed": seed, "epochs": epochs, "learning_rate": lr,
              "batch_size": batch_size, "architecture": [64, 32, 10],
              "split_counts": {s: len(data[f"y_{s}"]) for s in ("train", "val", "test")},
              "initial_train": initial, "history": history, "test": test,
              "confusion_matrix": matrix.tolist()}
    return model, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--output", type=Path, default=Path("metrics.json"))
    parser.add_argument("--save-model", type=Path)
    args = parser.parse_args()
    if args.epochs < 1 or not np.isfinite(args.lr) or args.lr <= 0 or args.batch_size < 1:
        parser.error("epochs et batch-size doivent être positifs ; lr doit être positif et fini.")
    network, report = run_experiment(args.epochs, args.lr, args.batch_size, args.seed)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.save_model:
        network.save(args.save_model)
    print(json.dumps({k: v for k, v in report.items() if k not in ("history", "confusion_matrix")},
                     indent=2))
