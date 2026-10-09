"""Éditeur Python multionglet avec exécution locale explicite.

Le terminal est une console de sortie : les scripts lancés ne disposent pas
d'une entrée interactive. Le code est exécuté avec les droits de l'application.
"""
from __future__ import annotations

import codecs
import keyword
import os
from pathlib import Path
import re
import sys
import tempfile

from PySide6.QtCore import QDir, QProcess, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QKeySequence, QPainter, QSyntaxHighlighter,
    QTextCharFormat, QTextCursor, QTextFormat,
)
from PySide6.QtWidgets import (
    QFileDialog, QFileSystemModel, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
    QTextEdit, QToolBar, QTreeView, QVBoxLayout, QWidget,
)


def _text_format(color: str, bold: bool = False) -> QTextCharFormat:
    result = QTextCharFormat()
    result.setForeground(QColor(color))
    if bold:
        result.setFontWeight(QFont.Weight.Bold)
    return result


class PythonHighlighter(QSyntaxHighlighter):
    """Coloration Python avec chaînes multilignes et commentaires."""

    NORMAL = 0
    SINGLE_TRIPLE = 1
    DOUBLE_TRIPLE = 2

    def __init__(self, document):
        super().__init__(document)
        self.keyword_format = _text_format("#c4a7ff", True)
        self.string_format = _text_format("#a3e6ad")
        self.comment_format = _text_format("#71839f")
        self.number_format = _text_format("#f4c77a")
        self.function_format = _text_format("#7dd3fc")
        self.builtin_format = _text_format("#72e6bf")
        self.comment_format.setFontItalic(True)
        keywords = keyword.kwlist + getattr(keyword, "softkwlist", [])
        self.rules = [
            (re.compile(r"\b(?:" + "|".join(keywords) + r")\b"), self.keyword_format),
            (re.compile(r"\b(?:print|len|range|str|int|float|dict|list|set|tuple|sum|min|max|open|enumerate|zip|super|sorted|isinstance|type)\b"), self.builtin_format),
            (re.compile(r"\b(?:0[xX][\da-fA-F_]+|0[bB][01_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)\b"), self.number_format),
            (re.compile(r"\b[A-Za-z_]\w*(?=\s*\()"), self.function_format),
            (re.compile(r"@[A-Za-z_]\w*(?:\.\w+)*"), self.function_format),
        ]

    def highlightBlock(self, text: str) -> None:
        for regex, style in self.rules:
            for match in regex.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), style)
        self.setCurrentBlockState(self.NORMAL)
        position = 0
        previous = self.previousBlockState()
        if previous in (self.SINGLE_TRIPLE, self.DOUBLE_TRIPLE):
            delimiter = "'''" if previous == self.SINGLE_TRIPLE else '"""'
            end = self._find_unescaped(text, delimiter, 0)
            if end < 0:
                self.setFormat(0, len(text), self.string_format)
                self.setCurrentBlockState(previous)
                return
            position = end + 3
            self.setFormat(0, position, self.string_format)
        while position < len(text):
            char = text[position]
            if char == "#":
                self.setFormat(position, len(text) - position, self.comment_format)
                break
            if char in ("'", '"'):
                triple = text.startswith(char * 3, position)
                delimiter = char * (3 if triple else 1)
                end = self._find_unescaped(text, delimiter, position + len(delimiter))
                if end < 0:
                    self.setFormat(position, len(text) - position, self.string_format)
                    if triple:
                        self.setCurrentBlockState(self.SINGLE_TRIPLE if char == "'" else self.DOUBLE_TRIPLE)
                    break
                end += len(delimiter)
                self.setFormat(position, end - position, self.string_format)
                position = end
            else:
                position += 1

    @staticmethod
    def _find_unescaped(text: str, delimiter: str, position: int) -> int:
        while True:
            found = text.find(delimiter, position)
            if found < 0:
                return -1
            slash = found - 1
            while slash >= 0 and text[slash] == "\\":
                slash -= 1
            if (found - 1 - slash) % 2 == 0:
                return found
            position = found + len(delimiter)


class LineNumberArea(QWidget):
    def __init__(self, editor: "PythonEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_line_numbers(event)


class PythonEditor(QPlainTextEdit):
    """Éditeur à numéros de ligne et indentation Python."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.display_name = "sans_titre.py"
        self.line_numbers = LineNumberArea(self)
        self.highlighter = PythonHighlighter(self.document())
        font = QFont("DejaVu Sans Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet("QPlainTextEdit { font-family: 'DejaVu Sans Mono', 'Consolas', monospace; font-size: 13px; }")
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setPlaceholderText("Écrivez votre code Python ici…")
        self.blockCountChanged.connect(self.update_line_number_width)
        self.updateRequest.connect(self.update_line_numbers)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_width()
        self.highlight_current_line()

    def line_number_width(self) -> int:
        return 22 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount())))

    def update_line_number_width(self, *_args) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def update_line_numbers(self, rect, dy: int) -> None:
        if dy:
            self.line_numbers.scroll(0, dy)
        else:
            self.line_numbers.update(0, rect.y(), self.line_numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents = self.contentsRect()
        self.line_numbers.setGeometry(QRect(contents.left(), contents.top(), self.line_number_width(), contents.height()))

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self.line_numbers)
        painter.fillRect(event.rect(), QColor("#0b101b"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#72e6bf" if number == current else "#61718a"))
                painter.drawText(0, top, self.line_numbers.width() - 10, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    def highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#162235"))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
        self.line_numbers.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Tab and not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.indent_selection(False)
            return
        if event.key() == Qt.Key.Key_Backtab:
            self.indent_selection(True)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.textCursor().hasSelection():
            cursor = self.textCursor()
            prefix = cursor.block().text()[:cursor.positionInBlock()]
            indent = re.match(r"[ \t]*", prefix).group(0)
            if prefix.rstrip().endswith(":"):
                indent += "    "
            cursor.beginEditBlock()
            cursor.insertText("\n" + indent)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return
        super().keyPressEvent(event)

    def indent_selection(self, remove: bool) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection() and not remove:
            cursor.insertText(" " * (4 - cursor.positionInBlock() % 4))
            return
        start = self.document().findBlock(cursor.selectionStart())
        finish_position = cursor.selectionEnd()
        if cursor.hasSelection() and finish_position > cursor.selectionStart():
            finish_position -= 1
        end = self.document().findBlock(finish_position)
        work = QTextCursor(start)
        work.beginEditBlock()
        current = start
        while current.isValid():
            is_last = current == end
            work.setPosition(current.position())
            if remove:
                text = current.text()
                amount = 1 if text.startswith("\t") else min(4, len(text) - len(text.lstrip(" ")))
                if amount:
                    work.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, amount)
                    work.removeSelectedText()
            else:
                work.insertText("    ")
            if is_last:
                break
            current = current.next()
        work.endEditBlock()


class CodeWorkspace(QWidget):
    """Panneau intégrable. Aucun script n'est exécuté sans action utilisateur."""

    activity = Signal(str)

    def __init__(self, workspace: Path, parent=None):
        super().__init__(parent)
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._new_counter = 0
        self.process: QProcess | None = None
        self._run_temporary: tempfile.TemporaryDirectory | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._shutting_down = False
        self._build_ui()
        self.new_file()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._add_action(toolbar, "Nouveau", self.new_file, QKeySequence.StandardKey.New)
        self._add_action(toolbar, "Ouvrir", self.open_file, QKeySequence.StandardKey.Open)
        self.save_action = self._add_action(toolbar, "Enregistrer", self.save_current, QKeySequence.StandardKey.Save)
        self._add_action(toolbar, "Enregistrer sous", self.save_as, QKeySequence.StandardKey.SaveAs)
        toolbar.addSeparator()
        self.run_action = self._add_action(toolbar, "Exécuter · F5", self.run_current, QKeySequence("F5"))
        self.stop_action = self._add_action(toolbar, "Arrêter", self.stop_process, QKeySequence("Shift+F5"))
        self.stop_action.setEnabled(False)
        toolbar.addSeparator()
        self._add_action(toolbar, "Rechercher", self.show_search, QKeySequence.StandardKey.Find)
        layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("EXPLORATEUR")
        title.setObjectName("eyebrow")
        side_layout.addWidget(title)
        self.file_model = QFileSystemModel(self)
        self.file_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.file_model.setRootPath(str(self.workspace))
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        self.file_tree.setRootIndex(self.file_model.index(str(self.workspace)))
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setAnimated(True)
        self.file_tree.setIndentation(14)
        for column in range(1, 4):
            self.file_tree.hideColumn(column)
        self.file_tree.doubleClicked.connect(self._tree_open)
        side_layout.addWidget(self.file_tree)
        root_label = QLabel(self.workspace.name)
        root_label.setToolTip(str(self.workspace))
        root_label.setObjectName("muted")
        side_layout.addWidget(root_label)
        splitter.addWidget(sidebar)

        content = QSplitter(Qt.Orientation.Vertical)
        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(6)
        self.search_bar = QWidget()
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher dans le document…")
        self.search_input.returnPressed.connect(self.find_next)
        search_layout.addWidget(self.search_input)
        search_next = QPushButton("Suivant")
        search_next.clicked.connect(self.find_next)
        search_layout.addWidget(search_next)
        search_close = QPushButton("Fermer")
        search_close.clicked.connect(self.search_bar.hide)
        search_layout.addWidget(search_close)
        editor_layout.addWidget(self.search_bar)
        self.search_bar.hide()
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._update_position)
        editor_layout.addWidget(self.tabs)
        self.position_label = QLabel()
        self.position_label.setObjectName("muted")
        editor_layout.addWidget(self.position_label)
        content.addWidget(editor_panel)

        output_panel = QWidget()
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        output_header = QHBoxLayout()
        output_header.addWidget(QLabel("CONSOLE PYTHON"))
        self.process_status = QLabel("Prête")
        self.process_status.setObjectName("muted")
        output_header.addWidget(self.process_status)
        output_header.addStretch()
        clear_output = QPushButton("Effacer")
        clear_output.clicked.connect(lambda: self.output.clear())
        output_header.addWidget(clear_output)
        output_layout.addLayout(output_header)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("DejaVu Sans Mono", 10))
        self.output.setStyleSheet("QPlainTextEdit { font-family: 'DejaVu Sans Mono', 'Consolas', monospace; font-size: 12px; }")
        self.output.setMaximumBlockCount(3000)
        self.output.setPlaceholderText("F5 pour lancer le document avec Python. Sortie standard et erreurs apparaîtront ici. Les scripts avec input() ne sont pas interactifs.")
        output_layout.addWidget(self.output)
        content.addWidget(output_panel)
        content.setSizes([560, 200])
        content.setStretchFactor(0, 4)
        content.setStretchFactor(1, 1)
        splitter.addWidget(content)
        splitter.setSizes([210, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

    def _add_action(self, toolbar, title, callback, shortcut=None) -> QAction:
        action = QAction(title, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda _checked=False: callback())
        self.addAction(action)
        toolbar.addAction(action)
        return action

    def current_editor(self) -> PythonEditor | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, PythonEditor) else None

    def new_file(self) -> PythonEditor:
        self._new_counter += 1
        editor = PythonEditor()
        editor.display_name = f"sans_titre_{self._new_counter}.py"
        self._add_editor(editor)
        return editor

    def _add_editor(self, editor: PythonEditor) -> None:
        index = self.tabs.addTab(editor, editor.display_name)
        editor.document().modificationChanged.connect(lambda _modified, e=editor: self._update_tab_title(e))
        editor.cursorPositionChanged.connect(self._update_position)
        self.tabs.setCurrentIndex(index)
        editor.setFocus()
        self._update_tab_title(editor)

    def open_file(self, path=None) -> bool:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un document", str(self.workspace), "Python (*.py *.pyw);;Textes (*.txt *.md *.json *.toml *.yaml *.yml *.csv);;Tous les fichiers (*)")
            if not path:
                return False
        path = Path(path).expanduser().resolve()
        for index in range(self.tabs.count()):
            if self.tabs.widget(index).path == path:
                self.tabs.setCurrentIndex(index)
                return True
        try:
            if path.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("Ce fichier dépasse la limite de 5 Mo de l'éditeur.")
            data = path.read_text(encoding="utf-8-sig")
            if "\x00" in data:
                raise ValueError("Ce fichier semble binaire et ne peut pas être édité comme texte.")
        except (OSError, UnicodeError, ValueError) as error:
            self._error("Ouverture impossible", str(error))
            return False
        editor = PythonEditor()
        editor.path = path
        editor.display_name = path.name
        editor.setPlainText(data)
        editor.document().setModified(False)
        self._add_editor(editor)
        self.activity.emit(f"Document ouvert : {path.name}")
        return True

    def _tree_open(self, index) -> None:
        path = Path(self.file_model.filePath(index))
        if path.is_file():
            self.open_file(path)

    def save_current(self) -> bool:
        editor = self.current_editor()
        return self._save_editor(editor) if editor else False

    def save_as(self) -> bool:
        editor = self.current_editor()
        return self._save_editor(editor, save_as=True) if editor else False

    def _save_editor(self, editor: PythonEditor, save_as: bool = False) -> bool:
        path = editor.path
        if path is None or save_as:
            suggested = path or self.workspace / editor.display_name
            selected, _ = QFileDialog.getSaveFileName(self, "Enregistrer le document", str(suggested), "Python (*.py);;Tous les fichiers (*)")
            if not selected:
                return False
            path = Path(selected).expanduser().resolve()
        for index in range(self.tabs.count()):
            other = self.tabs.widget(index)
            if other is not editor and other.path == path:
                self._error("Document déjà ouvert", "Ce chemin appartient à un autre onglet. Fermez cet onglet avant d'écraser son fichier.")
                return False
        temporary_path = None
        try:
            # Écriture atomique dans le même dossier, avec préservation des permissions.
            existing_mode = path.stat().st_mode & 0o777 if path.exists() else None
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
                temporary_path = Path(handle.name)
                handle.write(editor.toPlainText())
                handle.flush()
                os.fsync(handle.fileno())
            if existing_mode is not None:
                temporary_path.chmod(existing_mode)
            os.replace(temporary_path, path)
        except OSError as error:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            self._error("Enregistrement impossible", str(error))
            return False
        editor.path = path
        editor.display_name = path.name
        editor.document().setModified(False)
        self._update_tab_title(editor)
        self.activity.emit(f"Document enregistré : {path.name}")
        return True

    def _update_tab_title(self, editor: PythonEditor) -> None:
        index = self.tabs.indexOf(editor)
        if index >= 0:
            suffix = " *" if editor.document().isModified() else ""
            self.tabs.setTabText(index, editor.display_name + suffix)
            self.tabs.setTabToolTip(index, str(editor.path) if editor.path else "Document non enregistré")
        self._update_position()

    def _update_position(self, *_args) -> None:
        editor = self.current_editor()
        if editor is None:
            self.position_label.setText("Aucun document")
            return
        cursor = editor.textCursor()
        self.position_label.setText(f"Ligne {cursor.blockNumber() + 1} : {cursor.positionInBlock() + 1}     •     {editor.blockCount()} lignes     •     UTF-8     •     Python {sys.version_info.major}.{sys.version_info.minor}")

    def _confirm_editor(self, editor: PythonEditor) -> bool:
        if not editor.document().isModified():
            return True
        answer = QMessageBox.question(self, "Modifications non enregistrées", f"Enregistrer les modifications de {editor.display_name} ?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save_editor(editor)
        return True

    def _close_tab(self, index: int) -> bool:
        editor = self.tabs.widget(index)
        if not isinstance(editor, PythonEditor) or not self._confirm_editor(editor):
            return False
        self.tabs.removeTab(index)
        editor.deleteLater()
        if not self.tabs.count() and not self._shutting_down:
            self.new_file()
        return True

    def confirm_close(self) -> bool:
        for index in range(self.tabs.count()):
            if not self._confirm_editor(self.tabs.widget(index)):
                self.tabs.setCurrentIndex(index)
                return False
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            answer = QMessageBox.question(self, "Script en cours", "Un script Python est encore en cours. Fermer l'application et arrêter ce script ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            return answer == QMessageBox.StandardButton.Yes
        return True

    def show_search(self) -> None:
        self.search_bar.show()
        editor = self.current_editor()
        if editor and editor.textCursor().hasSelection():
            self.search_input.setText(editor.textCursor().selectedText())
        self.search_input.setFocus()
        self.search_input.selectAll()

    def find_next(self) -> bool:
        editor = self.current_editor()
        text = self.search_input.text()
        if editor is None or not text:
            return False
        initial = editor.textCursor()
        found = editor.find(text)
        if not found:
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            editor.setTextCursor(cursor)
            found = editor.find(text)
        if not found:
            editor.setTextCursor(initial)
        self.search_input.setToolTip("" if found else "Aucun résultat")
        self.search_input.setStyleSheet("" if found else "border: 1px solid #f1a579;")
        return found

    def run_current(self) -> bool:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            return False
        editor = self.current_editor()
        if editor is None:
            return False
        path = editor.path
        if path is not None and path.suffix.lower() not in (".py", ".pyw"):
            self._error("Fichier non Python", "L'exécution est réservée aux documents .py et .pyw.")
            return False
        if path is not None and editor.document().isModified() and not self._save_editor(editor):
            return False
        try:
            if path is None:
                self._run_temporary = tempfile.TemporaryDirectory(prefix="nexus-python-")
                path = Path(self._run_temporary.name) / editor.display_name
                path.write_text(editor.toPlainText(), encoding="utf-8")
        except OSError as error:
            self._clean_temporary()
            self._error("Exécution impossible", str(error))
            return False
        self.output.clear()
        self._append_output(f"$ Python {editor.display_name}\nDossier : {self.workspace}\n{'─' * 48}\n")
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        process = QProcess(self)
        self.process = process
        process.setProgram(sys.executable)
        process.setArguments(["-u", "-X", "utf8", str(path)])
        process.setWorkingDirectory(str(self.workspace))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.started.connect(lambda: process.closeWriteChannel())
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)
        self.run_action.setEnabled(False)
        self.stop_action.setEnabled(True)
        self.process_status.setText("Exécution en cours")
        self.activity.emit(f"Exécution Python : {editor.display_name}")
        process.start()
        return True

    def _append_output(self, text: str) -> None:
        # Bound output even when a script prints a very long line without '\n'.
        text = text[-500_000:]
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        excess = self.output.document().characterCount() - 500_000
        if excess > 0:
            trim = QTextCursor(self.output.document())
            trim.setPosition(0)
            trim.setPosition(excess, QTextCursor.MoveMode.KeepAnchor)
            trim.removeSelectedText()
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _read_output(self) -> None:
        if self.process:
            data = bytes(self.process.readAllStandardOutput())
            if data:
                self._append_output(self._decoder.decode(data))

    def _process_finished(self, exit_code: int, exit_status) -> None:
        self._read_output()
        tail = self._decoder.decode(b"", final=True)
        if tail:
            self._append_output(tail)
        if exit_status == QProcess.ExitStatus.CrashExit:
            status = "Processus interrompu"
        else:
            status = f"Terminé · code {exit_code}"
        self._append_output(f"\n{'─' * 48}\n{status}\n")
        self.process_status.setText(status)
        self.activity.emit(f"Python : {status.lower()}")
        self._release_process()

    def _process_error(self, error) -> None:
        if self.process:
            self._append_output(f"\nErreur du processus : {self.process.errorString()}\n")
        if error == QProcess.ProcessError.FailedToStart:
            self.process_status.setText("Échec du démarrage")
            self.activity.emit("Python : échec du démarrage")
            self._release_process()

    def _release_process(self) -> None:
        self.run_action.setEnabled(True)
        self.stop_action.setEnabled(False)
        self._clean_temporary()
        if self.process:
            self.process.deleteLater()
            self.process = None

    def _clean_temporary(self) -> None:
        if self._run_temporary is not None:
            try:
                self._run_temporary.cleanup()
            except OSError:
                pass
            self._run_temporary = None

    def stop_process(self) -> None:
        process = self.process
        if process and process.state() != QProcess.ProcessState.NotRunning:
            self.process_status.setText("Arrêt demandé…")
            process.terminate()
            QTimer.singleShot(1800, lambda p=process: self._kill_if_current(p))

    def _kill_if_current(self, process: QProcess) -> None:
        if self.process is process and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def shutdown(self) -> None:
        self._shutting_down = True
        process = self.process
        if process and process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            if not process.waitForFinished(1000):
                process.kill()
                process.waitForFinished(1000)
        self._clean_temporary()

    def _error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)
        self.activity.emit(f"{title} : {message}")
