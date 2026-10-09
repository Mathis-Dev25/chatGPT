"""CSV exploration with numeric sorting, live statistics and painter-based charts.

Imports are deliberately limited to 16 MiB, 25,000 records and 80 columns to
keep this single-process desktop workspace responsive. No optional libraries
or network access are required.
"""

from __future__ import annotations

import csv
import math
import random
import statistics
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QPointF, QRectF, QSize, QSortFilterProxyModel,
    Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSizePolicy, QSplitter, QTableView,
    QToolTip, QVBoxLayout, QWidget,
)


MAX_IMPORT_BYTES = 16 * 1024 * 1024
MAX_IMPORT_ROWS = 25_000
MAX_IMPORT_COLUMNS = 80
MAX_CHART_POINTS = 1_200


def numeric_value(value: str) -> float | None:
    """Parse finite numeric cells, accepting French decimal separators."""
    text = str(value).strip().replace("\u00a0", "").replace("\u202f", "")
    if not text:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def format_number(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1e9 or (value != 0 and abs(value) < 0.001):
        return f"{value:.3g}".replace(".", ",")
    return f"{value:,.2f}".replace(",", "\u202f").replace(".", ",")


class CsvTableModel(QAbstractTableModel):
    """Keep exact CSV cell text so exports do not lose numeric precision."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers: list[str] = []
        self.rows: list[tuple[str, ...]] = []

    def replace(self, headers: list[str], rows: list[tuple[str, ...]]) -> None:
        self.beginResetModel()
        self.headers = headers
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return value
        if role == Qt.ItemDataRole.TextAlignmentRole:
            horizontal = Qt.AlignmentFlag.AlignRight if numeric_value(value) is not None else Qt.AlignmentFlag.AlignLeft
            return horizontal | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return str(section + 1)


class NumericSortProxy(QSortFilterProxyModel):
    """Sort numeric cells numerically, with text and missing cells afterward."""

    def lessThan(self, left, right):
        left_text = str(left.data() or "")
        right_text = str(right.data() or "")
        left_number = numeric_value(left_text)
        right_number = numeric_value(right_text)
        left_key = (0, left_number) if left_number is not None else (1, left_text.casefold())
        right_key = (0, right_number) if right_number is not None else (1, right_text.casefold())
        return left_key < right_key


class DataChart(QWidget):
    """Interactive vector chart, capped rendering and exact histogram counts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._points: list[tuple[float, float, str]] = []
        self._values: list[float] = []
        self._mode = "Dispersion"
        self._x_name = "Index"
        self._y_name = "Valeur"
        self._total = 0
        self._hit_points: list[tuple[QPointF, str]] = []
        self._hit_bars: list[tuple[QRectF, str]] = []
        self._hover: QPointF | None = None

    def sizeHint(self):
        return QSize(510, 340)

    def set_series(self, points, values, mode, x_name, y_name):
        self._mode = mode
        self._x_name = x_name
        self._y_name = y_name
        self._total = len(points)
        if mode == "Courbe":
            points = sorted(points, key=lambda item: item[0])
        if len(points) > MAX_CHART_POINTS:
            stride = (len(points) - 1) / (MAX_CHART_POINTS - 1)
            points = [points[round(index * stride)] for index in range(MAX_CHART_POINTS)]
        self._points = points
        self._values = values
        self._hover = None
        self._hit_points.clear()
        self._hit_bars.clear()
        self.update()

    @staticmethod
    def _bounds(values):
        low, high = min(values), max(values)
        if low == high:
            pad = abs(low) * 0.05 or 1.0
            return low - pad, high + pad
        return low, high

    @staticmethod
    def _ratio(value, low, high):
        # Scaling first prevents overflow for valid but very large CSV values.
        scale = max(abs(low), abs(high), 1.0)
        lo, hi = low / scale, high / scale
        return (value / scale - lo) / (hi - lo) if hi != lo else 0.5

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#253044"), 1))
        painter.setBrush(QColor("#111827"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        painter.setFont(QFont("Sans Serif", 10, QFont.Weight.DemiBold))
        painter.setPen(QColor("#e6edf7"))
        title = f"Distribution · {self._y_name}" if self._mode == "Histogramme" else f"{self._y_name} × {self._x_name}"
        painter.drawText(QRectF(18, 12, self.width() - 36, 26), Qt.AlignmentFlag.AlignLeft, title)
        self._hit_points.clear()
        self._hit_bars.clear()
        has_data = bool(self._values) if self._mode == "Histogramme" else bool(self._points)
        if not has_data:
            painter.setPen(QColor("#8190aa"))
            painter.setFont(QFont("Sans Serif", 10))
            painter.drawText(self.rect().adjusted(24, 40, -24, -24), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             "Aucune donnée numérique pour cette sélection.\nModifiez les colonnes ou le filtre.")
            return
        plot = QRectF(70, 58, max(80, self.width() - 94), max(80, self.height() - 111))
        if self._mode == "Histogramme":
            self._draw_histogram(painter, plot)
        else:
            self._draw_points(painter, plot)
        if self._hover is not None:
            painter.setPen(QPen(QColor("#e6edf7"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(self._hover.x(), plot.top()), QPointF(self._hover.x(), plot.bottom()))
            painter.drawLine(QPointF(plot.left(), self._hover.y()), QPointF(plot.right(), self._hover.y()))
        painter.setFont(QFont("Sans Serif", 8))
        painter.setPen(QColor("#8190aa"))
        caption = f"{len(self._values):,} valeurs · survolez une barre" if self._mode == "Histogramme" else f"{len(self._points):,} / {self._total:,} points · survolez pour explorer"
        painter.drawText(QRectF(18, self.height() - 26, self.width() - 36, 18), Qt.AlignmentFlag.AlignLeft, caption.replace(",", " "))

    def _axes(self, painter, plot, xmin, xmax, ymin, ymax):
        painter.setFont(QFont("Sans Serif", 8))
        for index in range(5):
            fraction = index / 4
            y = plot.bottom() - fraction * plot.height()
            painter.setPen(QPen(QColor("#253044"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#8190aa"))
            value = ymin * (1 - fraction) + ymax * fraction
            painter.drawText(QRectF(2, y - 9, plot.left() - 10, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, format_number(value))
        for index in range(3):
            fraction = index / 2
            x = plot.left() + fraction * plot.width()
            value = xmin * (1 - fraction) + xmax * fraction
            painter.drawText(QRectF(x - 52, plot.bottom() + 9, 104, 18), Qt.AlignmentFlag.AlignCenter, format_number(value))

    def _draw_points(self, painter, plot):
        xs = [point[0] for point in self._points]
        ys = [point[1] for point in self._points]
        xmin, xmax = self._bounds(xs)
        ymin, ymax = self._bounds(ys)
        self._axes(painter, plot, xmin, xmax, ymin, ymax)
        coordinates = [QPointF(plot.left() + self._ratio(x, xmin, xmax) * plot.width(),
                              plot.bottom() - self._ratio(y, ymin, ymax) * plot.height()) for x, y, _ in self._points]
        painter.save()
        painter.setClipRect(plot.adjusted(-3, -3, 3, 3))
        if self._mode == "Courbe":
            path = QPainterPath()
            path.moveTo(coordinates[0])
            for point in coordinates[1:]:
                path.lineTo(point)
            painter.setPen(QPen(QColor("#72e6bf"), 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        for index, coordinate in enumerate(coordinates):
            color = QColor("#72e6bf" if index % 3 else "#a393f5")
            color.setAlpha(170 if len(coordinates) > 300 else 220)
            painter.setBrush(color)
            painter.drawEllipse(coordinate, 2.7, 2.7)
            x, y, label = self._points[index]
            self._hit_points.append((coordinate, f"{label}\n{self._x_name} : {format_number(x)}\n{self._y_name} : {format_number(y)}"))
        painter.restore()

    def _draw_histogram(self, painter, plot):
        low, high = self._bounds(self._values)
        count = min(16, max(1, math.ceil(math.sqrt(len(self._values)))))
        bins = [0] * count
        for value in self._values:
            index = min(count - 1, max(0, int(self._ratio(value, low, high) * count)))
            bins[index] += 1
        max_count = max(bins)
        self._axes(painter, plot, low, high, 0, max_count)
        width = plot.width() / count
        for index, amount in enumerate(bins):
            height = amount / max_count * plot.height()
            bar = QRectF(plot.left() + index * width + 2, plot.bottom() - height, max(1, width - 4), height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#72e6bf" if index % 2 == 0 else "#a393f5"))
            painter.drawRoundedRect(bar, 3, 3)
            start_fraction, end_fraction = index / count, (index + 1) / count
            start = low * (1 - start_fraction) + high * start_fraction
            end = low * (1 - end_fraction) + high * end_fraction
            self._hit_bars.append((bar, f"{format_number(start)} → {format_number(end)}\n{amount} valeurs"))

    def mouseMoveEvent(self, event):
        position = event.position()
        self._hover = None
        tooltip = None
        if self._mode == "Histogramme":
            for rect, text in self._hit_bars:
                if rect.contains(position):
                    tooltip = text
                    break
        elif self._hit_points:
            point, text = min(self._hit_points, key=lambda entry: (entry[0].x() - position.x()) ** 2 + (entry[0].y() - position.y()) ** 2)
            if (point.x() - position.x()) ** 2 + (point.y() - position.y()) ** 2 <= 225:
                tooltip = text
                self._hover = point
        if tooltip:
            QToolTip.showText(event.globalPosition().toPoint(), tooltip, self)
        else:
            QToolTip.hideText()
        self.update()

    def leaveEvent(self, event):
        self._hover = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)


class DataLab(QWidget):
    """Public helpers: load_csv(path), export_csv(path), demo_data()."""

    activity = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view_model = CsvTableModel(self)
        self.proxy = NumericSortProxy(self)
        self.proxy.setSourceModel(self.view_model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self._source_name = "Données de démonstration"
        self._truncated = False
        self._numeric_columns: list[int] = []
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self._refresh_analysis)
        self._build_ui()
        self.demo_data()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        toolbar = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Rechercher dans toutes les colonnes…")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setMinimumWidth(180)
        self.filter_input.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter_input, 1)
        import_button = QPushButton("Importer CSV")
        import_button.setObjectName("primaryButton")
        import_button.clicked.connect(self._choose_import)
        export_button = QPushButton("Exporter la vue")
        export_button.clicked.connect(self._choose_export)
        demo_button = QPushButton("Démo")
        demo_button.clicked.connect(self.demo_data)
        for button in (import_button, export_button, demo_button):
            toolbar.addWidget(button)
        root.addLayout(toolbar)

        self.source_label = QLabel()
        self.source_label.setObjectName("mutedLabel")
        self.source_label.setWordWrap(True)
        root.addWidget(self.source_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.table = QTableView()
        self.table.setObjectName("dataTable")
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(35)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(120)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._refresh_timer.start())
        self.table.setMinimumWidth(260)
        splitter.addWidget(self.table)

        analysis = QWidget()
        right = QVBoxLayout(analysis)
        right.setContentsMargins(8, 0, 0, 0)
        right.setSpacing(12)
        controls = QGridLayout()
        self.chart_type = QComboBox()
        self.chart_type.addItems(["Dispersion", "Courbe", "Histogramme"])
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        controls.addWidget(QLabel("VISUALISATION"), 0, 0, 1, 2)
        controls.addWidget(self.chart_type, 1, 0, 1, 2)
        controls.addWidget(QLabel("Axe horizontal"), 2, 0)
        controls.addWidget(QLabel("Mesure analysée"), 2, 1)
        controls.addWidget(self.x_combo, 3, 0)
        controls.addWidget(self.y_combo, 3, 1)
        for combo in (self.chart_type, self.x_combo, self.y_combo):
            combo.setMinimumWidth(110)
            combo.currentIndexChanged.connect(lambda *_: self._refresh_timer.start())
        right.addLayout(controls)
        self.chart = DataChart()
        right.addWidget(self.chart, 1)

        metrics = QGridLayout()
        metrics.setSpacing(8)
        self.metrics: dict[str, QLabel] = {}
        for index, (key, name) in enumerate([
            ("rows", "LIGNES VISIBLES"), ("count", "VALEURS NUMÉRIQUES"),
            ("mean", "MOYENNE"), ("std", "ÉCART-TYPE"),
            ("min", "MINIMUM"), ("max", "MAXIMUM"),
        ]):
            card = QFrame()
            card.setObjectName("statCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(13, 10, 13, 10)
            label = QLabel(name)
            label.setObjectName("mutedLabel")
            label.setStyleSheet("font-size: 10px; letter-spacing: 0.7px; color: #8190aa;")
            value = QLabel("—")
            value.setStyleSheet("font-size: 20px; font-weight: 600; color: #e6edf7;")
            layout.addWidget(label)
            layout.addWidget(value)
            self.metrics[key] = value
            metrics.addWidget(card, index // 2, index % 2)
        right.addLayout(metrics)
        splitter.addWidget(analysis)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([580, 470])
        root.addWidget(splitter, 1)
        self.status_label = QLabel()
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

    def _apply_filter(self, text):
        self.proxy.setFilterFixedString(text)
        self._refresh_timer.start()

    def _set_dataset(self, headers, rows, name, truncated=False):
        self._refresh_timer.stop()
        self._source_name = name
        self._truncated = truncated
        self.filter_input.clear()
        self.proxy.setFilterFixedString("")
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.view_model.replace(headers, rows)
        self._numeric_columns = [column for column in range(len(headers))
                                 if any(numeric_value(row[column]) is not None for row in rows)]
        self.x_combo.blockSignals(True)
        self.y_combo.blockSignals(True)
        self.x_combo.clear()
        self.y_combo.clear()
        self.x_combo.addItem("Ordre des lignes", -1)
        for column in self._numeric_columns:
            self.x_combo.addItem(headers[column], column)
            self.y_combo.addItem(headers[column], column)
        if not self._numeric_columns:
            self.y_combo.addItem("Aucune mesure", -1)
        if len(self._numeric_columns) >= 2:
            self.x_combo.setCurrentIndex(1)
            self.y_combo.setCurrentIndex(1)
        self.x_combo.blockSignals(False)
        self.y_combo.blockSignals(False)
        self.source_label.setText(f"{name}   ·   {len(rows):,} lignes   ·   {len(headers)} colonnes".replace(",", " "))
        self._refresh_analysis()

    def demo_data(self):
        """Create deterministic, correlated business data for immediate exploration."""
        rng = random.Random(42)
        rows = []
        start = date(2026, 1, 1)
        regions = ["Paris", "Lyon", "Bordeaux", "Lille"]
        for index in range(240):
            visitors = round(850 + index * 3.1 + 180 * math.sin(index / 12) + rng.gauss(0, 95))
            conversion = max(1.2, min(8.5, 4.5 + math.sin(index / 19) + rng.gauss(0, 0.6)))
            orders = round(visitors * conversion / 100)
            revenue = orders * rng.uniform(52, 84)
            rows.append(((start + timedelta(days=index)).isoformat(), regions[index % len(regions)],
                         str(visitors), str(orders), f"{revenue:.2f}", f"{conversion:.2f}",
                         "Organique" if index % 3 else "Campagne"))
        self._set_dataset(["Date", "Ville", "Visiteurs", "Commandes", "Revenu (€)", "Conversion (%)", "Canal"],
                          rows, "Exploration commerciale · démo reproductible")
        self.y_combo.setCurrentIndex(2)
        self._refresh_analysis()
        self.activity.emit("Laboratoire : 240 observations de démonstration chargées.")

    def load_csv(self, path: str | Path) -> int:
        """Load UTF-8 CSV atomically; raise ValueError/OSError on invalid input.

        Files beyond the row limit load a clearly labeled preview. Invalid
        input leaves the previous dataset intact.
        """
        path = Path(path)
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise ValueError("Fichier trop volumineux : la limite est de 16 Mio. Exportez un sous-ensemble avant l'import.")
        rows: list[tuple[str, ...]] = []
        truncated = False
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                sample = handle.read(65_536)
                if not sample.strip():
                    raise ValueError("Ce fichier CSV est vide.")
                handle.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    # A truncated sample or single-column CSV may not sniff.
                    first_line = sample.splitlines()[0]
                    delimiter = max(",;\t|", key=first_line.count)
                    dialect = csv.excel()
                    dialect.delimiter = delimiter
                reader = csv.reader(handle, dialect, strict=True)
                raw_headers = next(reader, [])
                if not raw_headers:
                    raise ValueError("La première ligne doit contenir les noms des colonnes.")
                if len(raw_headers) > MAX_IMPORT_COLUMNS:
                    raise ValueError(f"La limite est de {MAX_IMPORT_COLUMNS} colonnes par fichier.")
                headers = []
                seen = set()
                for index, header in enumerate(raw_headers):
                    base = header.strip() or f"Colonne {index + 1}"
                    candidate, suffix = base, 2
                    while candidate in seen:
                        candidate = f"{base} ({suffix})"
                        suffix += 1
                    headers.append(candidate)
                    seen.add(candidate)
                for row in reader:
                    if not row or not any(cell.strip() for cell in row):
                        continue
                    if len(rows) >= MAX_IMPORT_ROWS:
                        truncated = True
                        break
                    if len(row) > len(headers):
                        raise ValueError(f"Ligne {reader.line_num} : {len(row)} cellules pour {len(headers)} colonnes. Vérifiez le séparateur et les guillemets.")
                    rows.append(tuple(row + [""] * (len(headers) - len(row))))
        except UnicodeError as error:
            raise ValueError("Encodage non pris en charge : enregistrez le CSV en UTF-8 (avec ou sans BOM).") from error
        except csv.Error as error:
            raise ValueError(f"Le CSV est mal formé : {error}") from error
        self._set_dataset(headers, rows, path.name, truncated)
        self.activity.emit(f"Laboratoire : {len(rows)} lignes importées depuis {path.name}.")
        return len(rows)

    def export_csv(self, path: str | Path) -> int:
        """Export the visible rows in their current sort order, including headers."""
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.view_model.headers)
            for row in range(self.proxy.rowCount()):
                source = self.proxy.mapToSource(self.proxy.index(row, 0)).row()
                writer.writerow(self.view_model.rows[source])
        count = self.proxy.rowCount()
        self.activity.emit(f"Laboratoire : {count} lignes exportées vers {Path(path).name}.")
        return count

    def _choose_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importer un jeu de données UTF-8", "", "Données CSV (*.csv *.tsv);;Tous les fichiers (*)")
        if not path:
            return
        try:
            self.load_csv(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Import impossible", str(error))

    def _choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter les lignes visibles", "nexus-export.csv", "Données CSV (*.csv)")
        if not path:
            return
        try:
            count = self.export_csv(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Export impossible", str(error))
            return
        self.status_label.setText(f"Export terminé : {count} lignes enregistrées dans {Path(path).name}.")

    def _refresh_analysis(self):
        count = self.proxy.rowCount()
        y_column = self.y_combo.currentData()
        x_column = self.x_combo.currentData()
        y_column = y_column if isinstance(y_column, int) else -1
        x_column = x_column if isinstance(x_column, int) else -1
        mode = self.chart_type.currentText()
        self.x_combo.setEnabled(mode != "Histogramme")
        values: list[float] = []
        points: list[tuple[float, float, str]] = []
        if y_column >= 0:
            for visible_row in range(count):
                source = self.proxy.mapToSource(self.proxy.index(visible_row, 0)).row()
                record = self.view_model.rows[source]
                y = numeric_value(record[y_column])
                if y is None:
                    continue
                values.append(y)
                x = numeric_value(record[x_column]) if x_column >= 0 else float(visible_row + 1)
                if x is not None:
                    points.append((x, y, f"Ligne {source + 1} · {record[0][:80]}"))
        self.metrics["rows"].setText(f"{count:,}".replace(",", " "))
        self.metrics["count"].setText(f"{len(values):,}".replace(",", " "))
        if values:
            # Normalize before aggregation to prevent overflow near float limits.
            scale = max(abs(value) for value in values) or 1.0
            normalized = [value / scale for value in values]
            mean = statistics.fmean(normalized) * scale
            deviation = statistics.pstdev(normalized) * scale
            statistics_values = {"mean": mean, "std": deviation, "min": min(values), "max": max(values)}
        else:
            statistics_values = dict.fromkeys(("mean", "std", "min", "max"))
        for key, value in statistics_values.items():
            self.metrics[key].setText(format_number(value))
        x_name = self.view_model.headers[x_column] if x_column >= 0 else "Ordre des lignes"
        y_name = self.view_model.headers[y_column] if y_column >= 0 else "Valeur"
        self.chart.set_series(points, values, mode, x_name, y_name)
        suffix = " · aperçu limité à 25 000 lignes à l'import" if self._truncated else ""
        self.status_label.setText(f"{count:,} / {len(self.view_model.rows):,} lignes · {len(values):,} valeurs numériques pour « {y_name} » · écart-type de population{suffix}".replace(",", " "))
