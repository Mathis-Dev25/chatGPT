"""Interface pédagogique : entraîner un petit réseau puis reconnaître un chiffre."""
from __future__ import annotations

import sys
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QProgressBar,
    QFileDialog, QMessageBox,
)
from model import Network, load_data


class TrainingThread(QThread):
    progress = Signal(int, float, float)
    result = Signal(object, object, bool)
    error = Signal(str)

    def __init__(self, data, epochs, lr, parent=None):
        super().__init__(parent)
        self.data, self.epochs, self.lr = data, epochs, lr

    def run(self):
        try:
            model, rng, history = Network(42), np.random.default_rng(42), []
            for epoch in range(1, self.epochs + 1):
                completed = model.train_epoch(
                    self.data["x_train"], self.data["y_train"], self.lr, 32, rng,
                    self.isInterruptionRequested,
                )
                if not completed or self.isInterruptionRequested():
                    self.result.emit(None, history, True)
                    return
                train = model.evaluate(self.data["x_train"], self.data["y_train"])
                val = model.evaluate(self.data["x_val"], self.data["y_val"])
                history.append((train["loss"], val["accuracy"]))
                self.progress.emit(epoch, train["loss"], val["accuracy"])
            self.result.emit(model, history, False)
        except Exception as exc:
            self.error.emit(str(exc))


class LearningChart(QWidget):
    def __init__(self):
        super().__init__()
        self.points = []
        self.setMinimumSize(470, 240)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(55, 30, self.width() - 115, self.height() - 78)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setFont(QFont("Sans Serif", 9))
        max_loss = max(1.0, max((p[0] for p in self.points), default=2.5) * 1.1)
        for i in range(5):
            y = area.bottom() - i * area.height() / 4
            painter.setPen(QPen(QColor("#e5eaf1"), 1))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(QColor("#475569"))
            painter.drawText(QRectF(0, y - 9, 47, 18), Qt.AlignRight, f"{max_loss * i / 4:.1f}")
            painter.drawText(QRectF(area.right() + 8, y - 9, 50, 18), f"{i * 25} %")
        painter.drawText(8, 17, "Perte")
        painter.drawText(self.width() - 110, 17, "Réussite validation")
        painter.drawText(QRectF(0, self.height() - 25, self.width(), 20), Qt.AlignCenter,
                         f"Époques terminées : {len(self.points)}")
        if not self.points:
            painter.drawText(area, Qt.AlignCenter, "Les courbes apparaîtront pendant l’apprentissage.")
        for column, color, scale in ((0, "#f97316", max_loss), (1, "#0d9488", 1)):
            painter.setPen(QPen(QColor(color), 2.8))
            coords = [QPointF(area.left() + n * area.width() / max(1, len(self.points) - 1),
                              area.bottom() - p[column] / scale * area.height())
                      for n, p in enumerate(self.points)]
            for a, b in zip(coords, coords[1:]):
                painter.drawLine(a, b)
            if len(coords) == 1:
                painter.drawEllipse(coords[0], 3, 3)


class DigitView(QWidget):
    def __init__(self):
        super().__init__()
        self.values = np.zeros((8, 8))
        self.setFixedSize(176, 176)

    def paintEvent(self, event):
        painter = QPainter(self)
        side = self.width() / 8
        for row in range(8):
            for col in range(8):
                gray = int(self.values[row, col] * 255)
                painter.fillRect(QRectF(col * side, row * side, side, side),
                                 QColor(gray, gray, gray))


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mon premier réseau de neurones — Atelier Python")
        self.resize(1140, 800)
        self.data, self.model, self.worker = load_data(42), None, None
        self.sample_rng = np.random.default_rng(2026)
        self.sample_index = 0
        self.history = []
        self.setStyleSheet("""
            QWidget {font-family: 'DejaVu Sans'; font-size: 13px; color: #172b4d; background: #f4f7fb;}
            QGroupBox {font-weight: bold; background: white; border: 1px solid #dbe3ee;
                       border-radius: 12px; margin-top: 18px; padding: 16px;}
            QGroupBox::title {subcontrol-origin: margin; left: 15px; padding: 0 6px;}
            QLabel {background: transparent;}
            QPushButton {background: #e9eff7; border: 0; padding: 11px 14px; border-radius: 7px;}
            QPushButton:hover {background: #d6e2f2;}
            QPushButton:disabled {background: #edf1f6; color: #94a3b8;}
            QPushButton#primary {background: #0f766e; color: white; font-weight: bold;}
            QPushButton#primary:disabled {background: #9bbebc;}
            QSpinBox, QDoubleSpinBox {background: white; padding: 7px; border: 1px solid #cbd5e1;}
            QProgressBar {border: 0; border-radius: 4px; background: #e2e8f0; text-align: center;}
            QProgressBar::chunk {background: #2dd4bf; border-radius: 4px;}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel("Une IA qui apprend à lire les chiffres")
        title.setStyleSheet("font-size: 26px; font-weight: bold; color: #102a43;")
        layout.addWidget(title)
        layout.addWidget(QLabel("64 pixels → 32 neurones ReLU → 10 classes  •  Données locales  •  Graine 42"))
        top = QHBoxLayout()
        layout.addLayout(top, 1)
        controls = QGroupBox("1. Entraîner")
        controls.setMaximumWidth(335)
        control_layout = QVBoxLayout(controls)
        description = QLabel("1 078 images : apprentissage\n359 images : validation\n360 images : test réservé à la fin")
        control_layout.addWidget(description)
        form = QGridLayout()
        self.epochs = QSpinBox()
        self.epochs.setRange(1, 500)
        self.epochs.setValue(60)
        self.lr = QDoubleSpinBox()
        self.lr.setRange(0.001, 0.5)
        self.lr.setDecimals(3)
        self.lr.setSingleStep(0.01)
        self.lr.setValue(0.1)
        form.addWidget(QLabel("Époques"), 0, 0)
        form.addWidget(self.epochs, 0, 1)
        form.addWidget(QLabel("Taux d’apprentissage"), 1, 0)
        form.addWidget(self.lr, 1, 1)
        control_layout.addLayout(form)
        self.start = QPushButton("Démarrer l’apprentissage")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.start_training)
        self.stop = QPushButton("Annuler")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.cancel_training)
        control_layout.addWidget(self.start)
        control_layout.addWidget(self.stop)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        control_layout.addWidget(self.progress)
        self.metrics = QLabel("Prêt à apprendre.\nUn lot contient 32 images.")
        self.metrics.setWordWrap(True)
        control_layout.addWidget(self.metrics)
        control_layout.addStretch()
        top.addWidget(controls)
        curves = QGroupBox("2. Observer l’apprentissage")
        curves_layout = QVBoxLayout(curves)
        curves_layout.addWidget(QLabel("🟠 Perte sur l’apprentissage     •     Réussite validation en vert"))
        self.chart = LearningChart()
        curves_layout.addWidget(self.chart, 1)
        top.addWidget(curves, 1)

        bottom = QGroupBox("3. Prédire sur une image de validation")
        bottom_layout = QHBoxLayout(bottom)
        self.digit = DigitView()
        bottom_layout.addWidget(self.digit)
        prediction_layout = QVBoxLayout()
        self.sample_label = QLabel()
        self.prediction = QLabel("Entraînez le réseau, puis cliquez sur « Prédire ».")
        self.prediction.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.prediction.setWordWrap(True)
        prediction_layout.addWidget(self.sample_label)
        prediction_layout.addWidget(self.prediction)
        self.probabilities = QLabel("Le score softmax est une estimation, pas une certitude.")
        self.probabilities.setWordWrap(True)
        prediction_layout.addWidget(self.probabilities)
        buttons = QHBoxLayout()
        self.next_sample = QPushButton("Autre image")
        self.next_sample.clicked.connect(self.show_sample)
        self.predict = QPushButton("Prédire")
        self.predict.setObjectName("primary")
        self.predict.clicked.connect(self.predict_sample)
        self.test = QPushButton("Évaluer le test final")
        self.test.clicked.connect(self.evaluate_test)
        for button in (self.next_sample, self.predict, self.test):
            buttons.addWidget(button)
        prediction_layout.addLayout(buttons)
        bottom_layout.addLayout(prediction_layout, 1)
        layout.addWidget(bottom)
        footer = QHBoxLayout()
        self.save = QPushButton("Sauvegarder le modèle")
        self.save.clicked.connect(self.save_model)
        self.load = QPushButton("Charger un modèle")
        self.load.clicked.connect(self.load_model)
        footer.addWidget(self.save)
        footer.addWidget(self.load)
        footer.addStretch()
        layout.addLayout(footer)
        self.status = QLabel("Explorez les images de validation. Le test est réservé à l’évaluation finale.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.set_busy(False)
        self.show_sample()

    def set_busy(self, busy):
        for widget in (self.start, self.epochs, self.lr, self.load):
            widget.setEnabled(not busy)
        self.stop.setEnabled(busy)
        for widget in (self.predict, self.test, self.save):
            widget.setEnabled(not busy and self.model is not None)

    def start_training(self):
        self.model = None
        self.history = []
        self.chart.points = []
        self.chart.update()
        self.prediction.setText("Apprentissage en cours…")
        self.progress.setRange(0, self.epochs.value())
        self.progress.setValue(0)
        self.status.setText("Seuls les exemples d’apprentissage modifient les poids.")
        self.set_busy(True)
        self.worker = TrainingThread(self.data, self.epochs.value(), self.lr.value(), self)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.on_result)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread_finished)
        self.worker.start()

    def cancel_training(self):
        if self.worker:
            self.worker.requestInterruption()
            self.stop.setEnabled(False)
            self.status.setText("Annulation au prochain lot…")

    def on_progress(self, epoch, loss, accuracy):
        self.progress.setValue(epoch)
        self.chart.points.append((loss, accuracy))
        self.chart.update()
        self.metrics.setText(f"Époque {epoch}/{self.epochs.value()}\nPerte : {loss:.4f}\nValidation : {accuracy:.1%}")

    def on_result(self, model, history, cancelled):
        self.model, self.history = model, history
        self.prediction.setText("Entraînement annulé." if cancelled else "Modèle prêt : cliquez sur « Prédire ».")
        self.status.setText("Annulé. Relancez un entraînement." if cancelled else
                            "Terminé. Explorez la validation ; évaluez le test une fois les choix du modèle fixés.")

    def on_error(self, message):
        self.model = None
        self.status.setText("Échec de l’apprentissage.")
        QMessageBox.warning(self, "Erreur", message)

    def thread_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)

    def show_sample(self):
        self.sample_index = int(self.sample_rng.integers(len(self.data["y_val"])))
        self.digit.values = self.data["x_val"][self.sample_index].reshape(8, 8)
        self.digit.update()
        label = self.data["y_val"][self.sample_index]
        self.sample_label.setText(f"Image de validation n° {self.sample_index + 1}  •  Vraie classe : {label}")
        self.prediction.setText("Cliquez sur « Prédire » après l’apprentissage.")
        self.probabilities.setText("Le score softmax est une estimation, pas une certitude.")

    def predict_sample(self):
        if self.model is None or self.worker is not None:
            return
        x = self.data["x_val"][self.sample_index:self.sample_index + 1]
        p = self.model.predict_proba(x)[0]
        self.prediction.setText(f"Chiffre prédit : {p.argmax()}  •  Score : {p.max():.1%}")
        top = np.argsort(p)[-3:][::-1]
        self.probabilities.setText("Trois premiers scores : " + "  |  ".join(f"{i} : {p[i]:.1%}" for i in top))

    def evaluate_test(self):
        if self.model is None or self.worker is not None:
            return
        result = self.model.evaluate(self.data["x_test"], self.data["y_test"])
        self.status.setText(f"Test final : {result['accuracy']:.2%} sur 360 images, perte {result['loss']:.4f}. "
                            "Ce résultat ne sert pas à régler les paramètres.")

    def save_model(self):
        path, _ = QFileDialog.getSaveFileName(self, "Sauvegarder", "mon_reseau.npz", "Modèle NumPy (*.npz)")
        if path and self.model is not None:
            try:
                self.model.save(path)
                self.status.setText("Modèle sauvegardé : " + path)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Sauvegarde impossible", str(exc))

    def load_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Charger", "", "Modèle NumPy (*.npz)")
        if path:
            try:
                self.model = Network.load(path)
                self.chart.points = []
                self.chart.update()
                self.metrics.setText("Modèle chargé.\nHistorique non sauvegardé.")
                self.prediction.setText("Modèle chargé : cliquez sur « Prédire ».")
                self.status.setText("Test interprétable seulement si ce modèle respecte le découpage fourni (graine 42).")
                self.set_busy(False)
            except (OSError, ValueError, KeyError) as exc:
                QMessageBox.warning(self, "Modèle invalide", str(exc))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())
