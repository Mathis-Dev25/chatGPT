"""Vérifications utiles : python -m unittest -v."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from model import Network, load_data, run_experiment


class ModelTests(unittest.TestCase):
    def test_split_is_disjoint_reproducible_and_scaled(self):
        a, b = load_data(), load_data()
        sets = [set(a[f"indices_{s}"]) for s in ("train", "val", "test")]
        self.assertEqual(len(set.union(*sets)), 1797)
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        for name in ("train", "val", "test"):
            np.testing.assert_array_equal(a[f"indices_{name}"], b[f"indices_{name}"])
            self.assertGreaterEqual(a[f"x_{name}"].min(), 0)
            self.assertLessEqual(a[f"x_{name}"].max(), 1)
            self.assertEqual(set(a[f"y_{name}"]), set(range(10)))

    def test_gradient_matches_finite_differences(self):
        model = Network(4)
        rng = np.random.default_rng(8)
        x, y = rng.normal(size=(5, 64)), np.array([0, 3, 5, 7, 9])
        _, gradients = model.loss_and_gradients(x, y)
        epsilon = 1e-6
        for name in ("w1", "b1", "w2", "b2"):
            parameter = getattr(model, name)
            for flat_index in rng.choice(parameter.size, min(8, parameter.size), replace=False):
                index = np.unravel_index(flat_index, parameter.shape)
                original = parameter[index]
                parameter[index] = original + epsilon
                plus = model.evaluate(x, y)["loss"]
                parameter[index] = original - epsilon
                minus = model.evaluate(x, y)["loss"]
                parameter[index] = original
                numerical = (plus - minus) / (2 * epsilon)
                self.assertAlmostEqual(numerical, gradients[name][index], places=6)

    def test_softmax_is_stable_and_normalized(self):
        model = Network()
        model.b2 = np.linspace(-10000, 10000, 10)
        x = np.ones((4, 64))
        p = model.predict_proba(x)
        self.assertTrue(np.isfinite(p).all())
        np.testing.assert_allclose(p.sum(axis=1), 1)
        self.assertTrue(np.isfinite(model.evaluate(x, np.zeros(4, dtype=int))["loss"]))

    def test_training_improves_and_generalizes(self):
        _, report = run_experiment(epochs=20)
        self.assertLess(report["history"][-1]["train_loss"], report["initial_train"]["loss"] / 5)
        self.assertGreater(report["history"][-1]["val_accuracy"], 0.9)
        self.assertGreater(report["test"]["accuracy"], 0.9)
        self.assertEqual(sum(map(sum, report["confusion_matrix"])), 360)

    def test_cancel_does_not_update_weights(self):
        model = Network()
        original = model.w1.copy()
        complete = model.train_epoch(np.ones((3, 64)), np.array([1, 2, 3]),
                                     0.1, 2, np.random.default_rng(42), lambda: True)
        self.assertFalse(complete)
        np.testing.assert_array_equal(model.w1, original)

    def test_save_load_and_reject_invalid_model(self):
        model, x = Network(), np.ones((2, 64))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.npz"
            model.save(path)
            restored = Network.load(path)
            np.testing.assert_array_equal(model.predict_proba(x), restored.predict_proba(x))
            model.w1[0, 0] = np.nan
            model.save(path)
            with self.assertRaises(ValueError):
                Network.load(path)
            np.savez(path, version=np.array(1), w1=np.zeros((1, 1)),
                     b1=np.zeros(32), w2=np.zeros((32, 10)), b2=np.zeros(10))
            with self.assertRaises(ValueError):
                Network.load(path)


if __name__ == "__main__":
    unittest.main()
