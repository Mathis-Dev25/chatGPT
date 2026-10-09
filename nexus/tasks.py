"""A persistent, searchable Kanban workspace and its validated SQLite store."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

STATUSES = {"todo": "À faire", "doing": "En cours", "done": "Terminé"}
PRIORITIES = {"low": "Basse", "normal": "Normale", "high": "Haute", "urgent": "Urgente"}
PRIORITY_COLORS = {"low": "#8190aa", "normal": "#72e6bf", "high": "#f4c779", "urgent": "#fb8ca8"}
STATUS_COLORS = {"todo": "#a393f5", "doing": "#f4c779", "done": "#72e6bf"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class TaskStore:
    """Small transaction-safe task repository; all public writes are validated.

    Set ``seed=False`` for an empty workspace. Demo tasks are only created when
    the tasks table is first initialized; deleting every task never reseeds it.
    """

    def __init__(self, database_path: Path | str, *, seed: bool = True):
        if str(database_path) != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(database_path), timeout=10)
        self.connection.row_factory = sqlite3.Row
        self._closed = False
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        fresh = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).fetchone() is None
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK (status IN ('todo','doing','done')),
                    priority TEXT NOT NULL CHECK (priority IN ('low','normal','high','urgent')),
                    due_date TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            self.connection.execute("CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status)")
            if fresh and seed:
                samples = [
                    ("Dessiner le prochain chapitre", "Définir trois objectifs concrets pour votre espace de travail. Ouvrez cette carte pour la personnaliser.", "todo", "high", ""),
                    ("Explorer le laboratoire", "Essayez les visualisations et ajustez les paramètres pour observer les résultats en direct.", "todo", "normal", ""),
                    ("Organiser les idées", "Rassemblez vos notes, puis transformez les idées les plus utiles en actions.", "doing", "normal", ""),
                    ("Créer mon espace personnel", "Votre tableau est enregistré automatiquement sur cet ordinateur. Les cartes de démonstration peuvent être modifiées ou supprimées.", "done", "low", ""),
                ]
                stamp = _now()
                self.connection.executemany(
                    "INSERT INTO tasks(title,description,status,priority,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    [(*sample, stamp, stamp) for sample in samples],
                )

    @staticmethod
    def _validate(fields: dict[str, Any]) -> dict[str, str]:
        allowed = {"title", "description", "status", "priority", "due_date"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Champs inconnus : {', '.join(sorted(unknown))}")
        validated: dict[str, str] = {}
        for key, value in fields.items():
            if not isinstance(value, str):
                raise ValueError(f"Le champ {key} doit être du texte.")
            if key == "title":
                value = value.strip()
                if not value or len(value) > 180:
                    raise ValueError("Le titre doit contenir entre 1 et 180 caractères.")
            elif key == "description" and len(value) > 20000:
                raise ValueError("La description est limitée à 20 000 caractères.")
            elif key == "status" and value not in STATUSES:
                raise ValueError("Statut de tâche inconnu.")
            elif key == "priority" and value not in PRIORITIES:
                raise ValueError("Priorité de tâche inconnue.")
            elif key == "due_date" and value:
                try:
                    parsed = date.fromisoformat(value)
                except ValueError as error:
                    raise ValueError("La date doit être au format AAAA-MM-JJ.") from error
                if value != parsed.isoformat():
                    raise ValueError("La date doit être au format AAAA-MM-JJ.")
            validated[key] = value
        return validated

    @staticmethod
    def _validate_id(task_id: int) -> None:
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
            raise ValueError("Identifiant de tâche invalide.")

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("""
            SELECT * FROM tasks
            ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                     CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date, id DESC
        """).fetchall()
        return [dict(row) for row in rows]

    def add_task(self, title: str, description: str = "", status: str = "todo",
                 priority: str = "normal", due_date: str = "") -> int:
        data = self._validate(dict(title=title, description=description, status=status,
                                   priority=priority, due_date=due_date))
        stamp = _now()
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO tasks(title,description,status,priority,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (data["title"], data["description"], data["status"], data["priority"], data["due_date"], stamp, stamp),
            )
        return int(cursor.lastrowid)

    def update_task(self, task_id: int, **fields: str) -> None:
        self._validate_id(task_id)
        data = self._validate(fields)
        if not data:
            return
        data["updated_at"] = _now()
        assignments = ", ".join(f"{name}=?" for name in data)
        with self.connection:
            cursor = self.connection.execute(
                f"UPDATE tasks SET {assignments} WHERE id=?", (*data.values(), task_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Tâche {task_id} introuvable.")

    def delete_task(self, task_id: int) -> None:
        self._validate_id(task_id)
        with self.connection:
            cursor = self.connection.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            if cursor.rowcount != 1:
                raise KeyError(f"Tâche {task_id} introuvable.")

    def counts(self) -> dict[str, int]:
        result = {status: 0 for status in STATUSES}
        result.update({row["status"]: row["amount"] for row in self.connection.execute(
            "SELECT status, COUNT(*) AS amount FROM tasks GROUP BY status"
        )})
        result["total"] = sum(result.values())
        result["overdue"] = self.connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE due_date <> '' AND due_date < ? AND status <> 'done'",
            (date.today().isoformat(),),
        ).fetchone()[0]
        return result

    def close(self) -> None:
        if not self._closed:
            self.connection.close()
            self._closed = True


class TaskDialog(QDialog):
    """Accessible editor for a new or existing task."""

    def __init__(self, task: dict[str, Any] | None = None, parent: QWidget | None = None,
                 initial_status: str = "todo"):
        super().__init__(parent)
        task = task or {}
        self.setWindowTitle("Modifier la tâche" if task else "Nouvelle tâche")
        self.setMinimumWidth(510)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        heading = QLabel(self.windowTitle())
        heading.setStyleSheet("font-size: 23px; font-weight: 700; color: #e6edf7;")
        layout.addWidget(heading)
        hint = QLabel("Une intention claire, une prochaine action.")
        hint.setStyleSheet("color: #8190aa;")
        layout.addWidget(hint)
        layout.addWidget(QLabel("Titre"))
        self.title = QLineEdit(task.get("title", ""))
        self.title.setMaxLength(180)
        self.title.setPlaceholderText("Quel est votre prochain objectif ?")
        self.title.setMinimumHeight(40)
        layout.addWidget(self.title)
        layout.addWidget(QLabel("Description"))
        self.description = QTextEdit()
        self.description.setAcceptRichText(False)
        self.description.setPlaceholderText("Contexte, idées et étapes à suivre…")
        self.description.setPlainText(task.get("description", ""))
        self.description.setMinimumHeight(130)
        layout.addWidget(self.description)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.addWidget(QLabel("Statut"), 0, 0)
        grid.addWidget(QLabel("Priorité"), 0, 1)
        self.status = QComboBox()
        self.priority = QComboBox()
        for key, label in STATUSES.items():
            self.status.addItem(label, key)
        for key, label in PRIORITIES.items():
            self.priority.addItem(label, key)
        self.status.setCurrentIndex(self.status.findData(task.get("status", initial_status)))
        self.priority.setCurrentIndex(self.priority.findData(task.get("priority", "normal")))
        grid.addWidget(self.status, 1, 0)
        grid.addWidget(self.priority, 1, 1)
        layout.addLayout(grid)
        row = QHBoxLayout()
        self.has_due = QCheckBox("Définir une échéance")
        self.has_due.setChecked(bool(task.get("due_date")))
        self.due = QDateEdit()
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("dd MMM yyyy")
        self.due.setDate(QDate.fromString(task["due_date"], "yyyy-MM-dd") if task.get("due_date") else QDate.currentDate())
        self.due.setEnabled(self.has_due.isChecked())
        self.has_due.toggled.connect(self.due.setEnabled)
        row.addWidget(self.has_due)
        row.addStretch()
        row.addWidget(self.due)
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #fb8ca8;")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.title.setFocus()

    def fields(self) -> dict[str, str]:
        return dict(title=self.title.text(), description=self.description.toPlainText(),
                    status=self.status.currentData(), priority=self.priority.currentData(),
                    due_date=self.due.date().toString("yyyy-MM-dd") if self.has_due.isChecked() else "")

    def _accept(self) -> None:
        try:
            TaskStore._validate(self.fields())
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.accept()


class TaskCard(QFrame):
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    status_requested = Signal(int, str)

    def __init__(self, task: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("taskCard")
        self.setStyleSheet("QFrame#taskCard { background: #111827; border: 1px solid #253044; border-radius: 12px; } QFrame#taskCard:hover { border-color: #425371; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(11)
        top = QHBoxLayout()
        priority = QLabel("●  " + PRIORITIES[task["priority"]])
        priority.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {PRIORITY_COLORS[task['priority']]}; background: transparent; border: none;")
        top.addWidget(priority)
        top.addStretch()
        menu_button = QPushButton("•••")
        menu_button.setToolTip("Actions de la tâche")
        menu_button.setFixedSize(28, 24)
        menu_button.setStyleSheet("QPushButton { background: transparent; color: #8190aa; border: none; } QPushButton:hover { color: #e6edf7; }")
        menu = QMenu(menu_button)
        menu.addAction("Modifier", lambda: self.edit_requested.emit(task["id"]))
        menu.addSeparator()
        menu.addAction("Supprimer", lambda: self.delete_requested.emit(task["id"]))
        menu_button.setMenu(menu)
        top.addWidget(menu_button)
        layout.addLayout(top)
        title = QLabel(task["title"])
        title.setWordWrap(True)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setStyleSheet("font-size: 14px; font-weight: 650; color: #e6edf7; background: transparent; border: none;")
        layout.addWidget(title)
        if task["description"]:
            compact = " ".join(task["description"].split())
            description = QLabel(compact[:125] + ("…" if len(compact) > 125 else ""))
            description.setWordWrap(True)
            description.setTextFormat(Qt.TextFormat.PlainText)
            description.setStyleSheet("font-size: 12px; color: #8190aa; background: transparent; border: none;")
            layout.addWidget(description)
        meta = QHBoxLayout()
        identifier = QLabel(f"NX-{task['id']:03d}")
        identifier.setStyleSheet("font-size: 10px; color: #667690; background: transparent; border: none;")
        meta.addWidget(identifier)
        meta.addStretch()
        if task["due_date"]:
            parsed = date.fromisoformat(task["due_date"])
            overdue = parsed < date.today() and task["status"] != "done"
            due = QLabel(("En retard · " if overdue else "") + parsed.strftime("%d/%m"))
            due.setToolTip("Échéance : " + parsed.strftime("%d/%m/%Y"))
            due.setStyleSheet(f"font-size: 10px; color: {'#fb8ca8' if overdue else '#8190aa'}; background: transparent; border: none;")
            meta.addWidget(due)
        layout.addLayout(meta)
        status = QComboBox()
        status.setToolTip("Déplacer cette tâche")
        status.setAccessibleName("Statut de la tâche " + task["title"])
        for key, label in STATUSES.items():
            status.addItem(label, key)
        status.setCurrentIndex(status.findData(task["status"]))
        status.setMinimumHeight(29)
        status.setStyleSheet("QComboBox { font-size: 11px; padding: 4px 9px; background: #172033; color: #b9c6db; border: 1px solid #253044; border-radius: 6px; }")
        status.currentIndexChanged.connect(lambda _: self.status_requested.emit(task["id"], status.currentData()))
        layout.addWidget(status)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # The task ID is present in the card's status action closure; callers
            # set a property so double-click remains independent from that UI.
            task_id = self.property("taskId")
            if task_id is not None:
                self.edit_requested.emit(task_id)
        super().mouseDoubleClickEvent(event)


class TaskBoard(QWidget):
    changed = Signal()
    activity = Signal(str)

    def __init__(self, database_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = TaskStore(database_path)
        self._tasks: dict[int, dict[str, Any]] = {}
        self._columns: dict[str, tuple[QLabel, QVBoxLayout]] = {}
        self._closed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher une tâche…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(40)
        self.search.setMaximumWidth(390)
        self.search.setAccessibleName("Rechercher dans les tâches")
        self.search.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItem("Toutes les priorités", "")
        for key, label in PRIORITIES.items():
            self.filter.addItem(label, key)
        self.filter.setMinimumHeight(40)
        self.filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.filter)
        toolbar.addStretch()
        self.summary = QLabel()
        self.summary.setStyleSheet("color: #8190aa; font-size: 12px;")
        toolbar.addWidget(self.summary)
        add_button = QPushButton("+  Nouvelle tâche")
        add_button.setObjectName("primaryButton")
        add_button.setMinimumHeight(40)
        add_button.setStyleSheet("QPushButton { background: #72e6bf; color: #0b101b; padding: 10px 16px; border: none; border-radius: 8px; font-weight: 700; } QPushButton:hover { background: #96efd2; }")
        add_button.clicked.connect(lambda: self.add_task())
        toolbar.addWidget(add_button)
        layout.addLayout(toolbar)
        columns = QHBoxLayout()
        columns.setSpacing(18)
        for status, name in STATUSES.items():
            panel = QFrame()
            panel.setObjectName("kanbanColumn")
            panel.setStyleSheet("QFrame#kanbanColumn { background: #0e1421; border: 1px solid #1c2639; border-radius: 12px; }")
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(12, 16, 12, 12)
            panel_layout.setSpacing(14)
            heading_row = QHBoxLayout()
            heading = QLabel("●  " + name.upper())
            heading.setStyleSheet(f"color: {STATUS_COLORS[status]}; font-size: 11px; font-weight: 750; letter-spacing: 1px;")
            heading_row.addWidget(heading)
            heading_row.addStretch()
            counter = QLabel("0")
            counter.setStyleSheet("color: #8190aa; background: #1b2538; border-radius: 8px; padding: 3px 8px; font-size: 11px;")
            heading_row.addWidget(counter)
            panel_layout.addLayout(heading_row)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            contents = QWidget()
            contents.setStyleSheet("background: transparent;")
            cards = QVBoxLayout(contents)
            cards.setContentsMargins(0, 0, 3, 0)
            cards.setSpacing(12)
            cards.setAlignment(Qt.AlignmentFlag.AlignTop)
            scroll.setWidget(contents)
            panel_layout.addWidget(scroll, 1)
            add_here = QPushButton("+  Ajouter une tâche")
            add_here.setMinimumHeight(35)
            add_here.setStyleSheet("QPushButton { border: 1px dashed #2b3850; border-radius: 7px; color: #8190aa; background: transparent; font-size: 12px; } QPushButton:hover { color: #72e6bf; border-color: #72e6bf; }")
            add_here.clicked.connect(lambda checked=False, key=status: self.add_task(key))
            panel_layout.addWidget(add_here)
            self._columns[status] = (counter, cards)
            columns.addWidget(panel, 1)
        layout.addLayout(columns, 1)
        footer = QLabel("DOUBLE-CLIC POUR MODIFIER  ·  CHANGEZ LE STATUT POUR DÉPLACER UNE CARTE  ·  ENREGISTREMENT AUTOMATIQUE")
        footer.setWordWrap(True)
        footer.setStyleSheet("font-size: 9px; color: #63738e; letter-spacing: 0.8px;")
        layout.addWidget(footer)
        self.refresh()

    def refresh(self, *_args) -> None:
        if self._closed:
            return
        tasks = self.store.list_tasks()
        self._tasks = {task["id"]: task for task in tasks}
        query = self.search.text().strip().casefold()
        priority = self.filter.currentData()
        filtered = [task for task in tasks if (not query or query in (task["title"] + " " + task["description"]).casefold()) and (not priority or task["priority"] == priority)]
        counts = self.store.counts()
        self.summary.setText(f"{counts['done']}/{counts['total']} terminées")
        for status, (counter, cards) in self._columns.items():
            while cards.count():
                item = cards.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            selected = [task for task in filtered if task["status"] == status]
            counter.setText(str(len(selected)))
            for task in selected:
                card = TaskCard(task)
                card.setProperty("taskId", task["id"])
                card.edit_requested.connect(self.edit_task)
                card.delete_requested.connect(self.delete_task)
                card.status_requested.connect(self.move_task)
                cards.addWidget(card)
            if not selected:
                empty = QLabel("Aucun résultat" if query or priority else "Un peu d'espace\npour la suite.")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setWordWrap(True)
                empty.setMinimumHeight(135)
                empty.setStyleSheet("color: #53647e; font-size: 12px; line-height: 1.5;")
                cards.addWidget(empty)

    def _commit(self, operation, message: str) -> bool:
        try:
            operation()
        except (ValueError, KeyError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Enregistrement impossible", str(error))
            self.refresh()
            return False
        self.refresh()
        self.changed.emit()
        self.activity.emit(message)
        return True

    def add_task(self, status: str = "todo") -> None:
        dialog = TaskDialog(parent=self, initial_status=status)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            fields = dialog.fields()
            self._commit(lambda: self.store.add_task(**fields), "Tâche créée : " + fields["title"].strip())

    def edit_task(self, task_id: int) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            self.refresh()
            return
        dialog = TaskDialog(task, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._commit(lambda: self.store.update_task(task_id, **dialog.fields()), "Tâche mise à jour : " + dialog.fields()["title"].strip())

    def delete_task(self, task_id: int) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        prompt = QMessageBox(self)
        prompt.setIcon(QMessageBox.Icon.Question)
        prompt.setWindowTitle("Supprimer la tâche")
        prompt.setText("Supprimer cette tâche définitivement ?")
        prompt.setInformativeText(task["title"])
        prompt.setTextFormat(Qt.TextFormat.PlainText)
        delete_button = prompt.addButton("Supprimer", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = prompt.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        prompt.setDefaultButton(cancel_button)
        prompt.exec()
        if prompt.clickedButton() == delete_button:
            self._commit(lambda: self.store.delete_task(task_id), "Tâche supprimée : " + task["title"])

    def move_task(self, task_id: int, status: str) -> None:
        task = self._tasks.get(task_id)
        if task is None or task["status"] == status:
            return
        self._commit(lambda: self.store.update_task(task_id, status=status), f"{task['title']} → {STATUSES.get(status, status)}")

    def stats(self) -> dict[str, int]:
        return self.store.counts() if not self._closed else {"todo": 0, "doing": 0, "done": 0, "total": 0, "overdue": 0}

    def shutdown(self) -> None:
        if not self._closed:
            self._closed = True
            self.store.close()
