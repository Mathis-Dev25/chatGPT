"""Fenêtre principale, palette de commandes et sauvegarde de session."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QByteArray, QEvent, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPen, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from . import __version__
from .dashboard import Dashboard, label
from .data_lab import DataLab
from .editor import CodeWorkspace
from .graph_lab import GraphLab
from .tasks import TaskBoard
from .theme import MINT, apply_theme

PAGES = [
    ("Vue d’ensemble", "Votre espace, en mouvement.", "Une vue claire sur votre machine, vos outils et vos projets."),
    ("Atelier de code", "De l’idée à l’exécution.", "Éditez, enregistrez et exécutez vos scripts Python dans un même espace."),
    ("Data lab", "Laissez parler les données.", "Explorez vos fichiers CSV, filtrez les lignes et visualisez les tendances."),
    ("Flow lab", "Connectez vos idées.", "Composez un graphe et suivez son parcours, une étape après l’autre."),
    ("Tableau de projet", "Faites avancer l’essentiel.", "Organisez vos tâches, fixez vos priorités et gardez le cap."),
]


def atomic_json(path: Path, payload):
    """Écriture atomique : un échec ne détruit pas la session précédente."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".nexus-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def make_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(MINT))
    painter.drawRoundedRect(2, 2, 60, 60, 16, 16)
    painter.setPen(QPen(QColor("#12372d"), 5))
    painter.drawLine(20, 44, 20, 20)
    painter.drawLine(20, 20, 44, 44)
    painter.drawLine(44, 44, 44, 20)
    painter.end()
    return QIcon(pixmap)


class CommandPalette(QDialog):
    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self.commands = commands
        self.setWindowTitle("Palette de commandes")
        self.resize(580, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(label("QUE VOULEZ-VOUS FAIRE ?", "eyebrow"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher une page ou une action…")
        self.search.setMinimumHeight(44)
        self.search.textChanged.connect(self.filter_commands)
        self.search.returnPressed.connect(self.execute)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.itemActivated.connect(self.execute)
        layout.addWidget(self.results, 1)
        layout.addWidget(label("Entrée pour ouvrir · Échap pour fermer", "muted"))
        self.filter_commands("")

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.results.count():
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                self.results.setCurrentRow((self.results.currentRow() + step) % self.results.count())
                return True
        return super().eventFilter(watched, event)

    def filter_commands(self, query):
        self.results.clear()
        for index, (name, callback) in enumerate(self.commands):
            if query.casefold() in name.casefold():
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def execute(self, *_args):
        item = self.results.currentItem()
        if item:
            callback = self.commands[item.data(Qt.ItemDataRole.UserRole)][1]
            self.accept()
            callback()


class MainWindow(QMainWindow):
    def __init__(self, workspace: Path, state_dir: Path, restore=True):
        super().__init__()
        self.workspace = workspace.resolve()
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.setWindowTitle("Nexus Studio — Atelier Python")
        self.setWindowIcon(make_icon())
        self.resize(1460, 1040)
        self.setMinimumSize(1100, 740)
        self._closed = False
        self._startup_messages = []
        self.tasks = TaskBoard(self.state_dir / "tasks.sqlite3")
        self.editor = CodeWorkspace(workspace)
        self.data_lab = DataLab()
        self.graph = GraphLab()
        self.dashboard = Dashboard(workspace, self.tasks.stats)
        self.dashboard.navigate.connect(self.navigate)
        self._build_ui()
        self._connect_actions()
        self._restore(restore)
        for message in self._startup_messages:
            self.record_activity(message)
        example = workspace / "examples" / "welcome.py"
        if example.is_file():
            self.editor.open_file(example)
            self.editor._close_tab(0)
        self.statusBar().showMessage("Prêt  ·  Espace de travail local")
        self.statusBar().addPermanentWidget(label("PYTHON   /   PYSIDE6     •     v" + __version__))

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 27, 18, 22)
        side.setSpacing(8)
        brand_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(make_icon().pixmap(36, 36))
        brand_row.addWidget(logo)
        brand_text = QVBoxLayout()
        brand = label("NEXUS")
        brand.setStyleSheet("font-size: 22px; font-weight: 800; letter-spacing: 3px;")
        brand_text.addWidget(brand)
        brand_text.addWidget(label("S T U D I O", "eyebrow"))
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        side.addLayout(brand_row)
        side.addSpacing(36)
        side.addWidget(label("ESPACE DE TRAVAIL", "eyebrow"))
        side.addSpacing(10)
        self.nav_buttons = []
        symbols = ["◈", "⌘", "▥", "◇", "☷"]
        for index, (name, _, _) in enumerate(PAGES):
            button = QPushButton(f"{symbols[index]}     {name}")
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setMinimumHeight(46)
            button.setToolTip(f"{name}  ·  Ctrl+{index + 1}")
            button.clicked.connect(lambda checked=False, i=index: self.navigate(i))
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch()
        tip = QFrame()
        tip.setObjectName("card")
        tip_layout = QVBoxLayout(tip)
        tip_layout.setContentsMargins(13, 15, 13, 15)
        tip_layout.addWidget(label("UN RACCOURCI, UNE IDÉE", "eyebrow"))
        hint = label("Tous vos outils\nà portée de clavier.")
        hint.setStyleSheet("color: #aebbd0; line-height: 1.5;")
        tip_layout.addWidget(hint)
        command = QPushButton("⌘   Ctrl + K")
        command.clicked.connect(self.show_palette)
        tip_layout.addWidget(command)
        side.addWidget(tip)
        side.addSpacing(14)
        local = label("●   ESPACE LOCAL")
        local.setStyleSheet(f"color: {MINT}; font-size: 10px; letter-spacing: 1px;")
        side.addWidget(local)
        about = QPushButton("À propos et raccourcis")
        about.setFlat(True)
        about.clicked.connect(self.show_about)
        side.addWidget(about)
        root.addWidget(sidebar)

        body = QVBoxLayout()
        body.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(30, 14, 30, 14)
        self.breadcrumb = label("NEXUS   /   Vue d’ensemble", "muted")
        top.addWidget(self.breadcrumb)
        top.addStretch()
        search = QPushButton("Rechercher une commande…     Ctrl K")
        search.setStyleSheet("color: #8190aa; text-align: left; min-width: 265px;")
        search.clicked.connect(self.show_palette)
        top.addWidget(search)
        body.addWidget(topbar)

        heading = QWidget()
        heading_layout = QVBoxLayout(heading)
        heading_layout.setContentsMargins(30, 26, 30, 22)
        eyebrow_row = QHBoxLayout()
        eyebrow_row.addWidget(label("VOTRE ATELIER NUMÉRIQUE", "eyebrow"))
        eyebrow_row.addStretch()
        eyebrow_row.addWidget(label(datetime.now().strftime("%d / %m / %Y"), "muted"))
        heading_layout.addLayout(eyebrow_row)
        self.heading = label(PAGES[0][1], "heading")
        heading_layout.addWidget(self.heading)
        self.subtitle = label(PAGES[0][2], "muted")
        heading_layout.addWidget(self.subtitle)
        body.addWidget(heading)
        self.stack = QStackedWidget()
        self.stack.setContentsMargins(30, 0, 30, 24)
        # Scroll the overview at small sizes without compressing the charts.
        overview_scroll = QScrollArea()
        overview_scroll.setWidgetResizable(True)
        overview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        overview_scroll.setWidget(self.dashboard)
        self.dashboard.setMinimumHeight(780)
        for page in (overview_scroll, self.editor, self.data_lab, self.graph, self.tasks):
            self.stack.addWidget(page)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(central)
        self.navigate(0)

    def _connect_actions(self):
        for page in (self.editor, self.data_lab, self.graph, self.tasks):
            page.activity.connect(self.record_activity)
        for index in range(len(PAGES)):
            action = QAction(self)
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(lambda checked=False, i=index: self.navigate(i))
            self.addAction(action)
        palette = QAction(self)
        palette.setShortcut(QKeySequence("Ctrl+K"))
        palette.triggered.connect(self.show_palette)
        self.addAction(palette)
        quit_action = QAction(self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

    def navigate(self, index):
        if not 0 <= index < len(PAGES):
            return
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(index == i)
        name, title, subtitle = PAGES[index]
        self.breadcrumb.setText("NEXUS   /   " + name)
        self.heading.setText(title)
        self.subtitle.setText(subtitle)

    def record_activity(self, message):
        self.dashboard.add_activity(message)
        self.statusBar().showMessage(message, 6000)

    def show_palette(self):
        commands = [("Ouvrir · " + page[0], lambda i=i: self.navigate(i)) for i, page in enumerate(PAGES)]
        commands += [
            ("Python · nouveau document", lambda: (self.navigate(1), self.editor.new_file())),
            ("Python · ouvrir un fichier", lambda: (self.navigate(1), self.editor.open_file())),
            ("Données · importer un CSV", lambda: (self.navigate(2), self.data_lab._choose_import())),
            ("Projet · nouvelle tâche", lambda: (self.navigate(4), self.tasks.add_task())),
            ("À propos · aide et raccourcis", self.show_about),
        ]
        dialog = CommandPalette(commands, self)
        dialog.exec()

    def show_about(self):
        QMessageBox.information(self, "Nexus Studio", f"Nexus Studio {__version__}\n\nUn atelier Python local avec PySide6.\n\nCtrl+1…5 : changer d’espace\nCtrl+K : palette de commandes\nDans l’éditeur : Ctrl+N / O / S / F\nF5 : exécuter · Maj+F5 : arrêter\n\nLe Flow lab visualise un parcours de graphe.\nL’éditeur exécute du vrai Python sur votre machine.\n\nDonnées locales :\n{self.state_dir}")

    def _restore(self, restore):
        if not restore:
            return
        graph_file = self.state_dir / "graph.json"
        settings_file = self.state_dir / "session.json"
        if graph_file.exists():
            try:
                if graph_file.stat().st_size > 2_000_000:
                    raise ValueError("graphe trop volumineux")
                self.graph.load_graph(json.loads(graph_file.read_text(encoding="utf-8")))
            except (OSError, ValueError, RecursionError) as error:
                self._startup_messages.append(f"Graphe précédent non restauré : {error}")
        if settings_file.exists():
            try:
                if settings_file.stat().st_size > 100_000:
                    raise ValueError("session trop volumineuse")
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
                geometry = settings.get("geometry", "")
                if isinstance(geometry, str):
                    self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
                index = settings.get("page", 0)
                if type(index) is int:
                    self.navigate(index)
            except (OSError, ValueError, AttributeError, RecursionError) as error:
                self._startup_messages.append(f"Session précédente non restaurée : {error}")

    def save_session(self):
        atomic_json(self.state_dir / "graph.json", self.graph.to_dict())
        atomic_json(self.state_dir / "session.json", {
            "version": 1,
            "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            "page": self.stack.currentIndex(),
        })

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self.dashboard.shutdown()
        self.graph.shutdown()
        self.editor.shutdown()
        self.tasks.shutdown()

    def closeEvent(self, event):
        if self._closed:
            event.accept()
            return
        if not self.editor.confirm_close():
            event.ignore()
            return
        try:
            self.save_session()
        except (OSError, ValueError) as error:
            answer = QMessageBox.warning(self, "Sauvegarde de session impossible", f"{error}\n\nQuitter sans enregistrer le graphe et la disposition ?", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self.shutdown()
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Nexus Studio — atelier graphique Python")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Dossier affiché dans l’explorateur")
    parser.add_argument("--state-dir", type=Path, help="Dossier des tâches, du graphe et de la session")
    parser.add_argument("--smoke-test", action="store_true", help="Démarrer puis fermer automatiquement après 2 secondes")
    parser.add_argument("--screenshot", type=Path, help="Enregistrer la fenêtre pendant --smoke-test")
    options = parser.parse_args(argv)
    if options.screenshot and not options.smoke_test:
        parser.error("--screenshot nécessite --smoke-test")
    if not options.workspace.is_dir():
        parser.error("le dossier --workspace doit exister")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("NexusStudio")
    app.setOrganizationName("Nexus")
    apply_theme(app)
    state_dir = options.state_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    window = MainWindow(options.workspace, state_dir, restore=not options.smoke_test)
    window.show()
    errors = []
    if options.smoke_test:
        def finish():
            try:
                if options.screenshot:
                    options.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    if not window.grab().save(str(options.screenshot)):
                        raise OSError("Impossible d’enregistrer la capture")
                window.save_session()
                print("Nexus Studio : démarrage, rendu et sauvegarde vérifiés.")
            except Exception as error:
                errors.append(error)
                print(str(error), file=sys.stderr)
            finally:
                window.shutdown()
                window.close()
                app.quit()
        QTimer.singleShot(2200, finish)
    result = app.exec()
    window.shutdown()
    return 1 if errors else result
