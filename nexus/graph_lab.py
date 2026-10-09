"""Laboratoire de graphes interactif, entièrement local et sans moteur externe."""
from __future__ import annotations

from collections import deque
import json
import math
from pathlib import Path
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen, QPolygonF,
    QShortcut,
)
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QFrame, QGraphicsItem,
    QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

BG = QColor("#0b101b")
SURFACE = QColor("#111827")
BORDER = QColor("#253044")
TEXT = QColor("#e6edf7")
MUTED = QColor("#8190aa")
ACCENT = QColor("#72e6bf")
PURPLE = QColor("#a393f5")


class GraphNode(QGraphicsObject):
    """Une carte déplaçable dont les liens suivent les changements de position."""

    WIDTH = 184
    HEIGHT = 88

    def __init__(self, node_id: str, label: str, kind: str = "OPÉRATION"):
        super().__init__()
        self.node_id = node_id
        self.label = label
        self.kind = kind
        self.edges: list[GraphEdge] = []
        self.state = "idle"
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(label)

    def boundingRect(self):
        return QRectF(-7, -3, self.WIDTH + 14, self.HEIGHT + 6)

    def input_point(self):
        return self.mapToScene(QPointF(0, self.HEIGHT / 2))

    def output_point(self):
        return self.mapToScene(QPointF(self.WIDTH, self.HEIGHT / 2))

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = self.state == "active"
        color = ACCENT if active or self.state == "visited" else PURPLE
        edge = ACCENT if self.isSelected() or active else BORDER
        painter.setPen(QPen(edge, 2 if self.isSelected() or active else 1))
        painter.setBrush(QColor("#172b2c") if active else SURFACE)
        painter.drawRoundedRect(QRectF(0, 0, self.WIDTH, self.HEIGHT), 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(14, 14, 4, 12), 2, 2)
        painter.setPen(MUTED)
        painter.setFont(QFont("Sans Serif", 8, QFont.Weight.DemiBold))
        painter.drawText(QRectF(25, 11, self.WIDTH - 36, 19), Qt.AlignmentFlag.AlignVCenter, self.kind)
        painter.setPen(TEXT)
        painter.setFont(QFont("Sans Serif", 10, QFont.Weight.DemiBold))
        label = painter.fontMetrics().elidedText(self.label, Qt.TextElideMode.ElideRight, self.WIDTH - 30)
        painter.drawText(QRectF(15, 33, self.WIDTH - 30, 24), Qt.AlignmentFlag.AlignVCenter, label)
        painter.setPen(ACCENT if self.state != "idle" else MUTED)
        painter.setFont(QFont("Sans Serif", 8))
        caption = {"active": "● En cours", "visited": "✓ Parcouru", "idle": "Prêt à connecter"}[self.state]
        painter.drawText(QRectF(15, 59, self.WIDTH - 30, 18), Qt.AlignmentFlag.AlignVCenter, caption)
        for x in (0, self.WIDTH):
            painter.setBrush(color)
            painter.setPen(QPen(BG, 2))
            painter.drawEllipse(QPointF(x, self.HEIGHT / 2), 5, 5)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_path()
        return super().itemChange(change, value)

    def set_state(self, state: str):
        self.state = state
        self.update()


class GraphEdge(QGraphicsPathItem):
    def __init__(self, source: GraphNode, target: GraphNode):
        super().__init__()
        self.source = source
        self.target = target
        self.active = False
        self.setZValue(-1)
        self.setPen(QPen(QColor("#51617d"), 2))
        self.source.edges.append(self)
        self.target.edges.append(self)
        self.update_path()

    def update_path(self):
        start, end = self.source.output_point(), self.target.input_point()
        bend = max(65, abs(end.x() - start.x()) * .45)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(bend, 0), end - QPointF(bend, 0), end)
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        color = ACCENT if self.active else QColor("#51617d")
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 2.8 if self.active else 1.7))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())
        tip = self.path().pointAtPercent(.96)
        prev = self.path().pointAtPercent(.92)
        angle = math.atan2(tip.y() - prev.y(), tip.x() - prev.x())
        left = tip - QPointF(math.cos(angle - .55) * 11, math.sin(angle - .55) * 11)
        right = tip - QPointF(math.cos(angle + .55) * 11, math.sin(angle + .55) * 11)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([tip, left, right]))

    def detach(self):
        self.source.edges.remove(self)
        self.target.edges.remove(self)


class GraphScene(QGraphicsScene):
    def drawBackground(self, painter, rect):
        painter.fillRect(rect, BG)
        painter.setPen(QPen(QColor("#1c2638"), 1))
        step = 28
        left = math.floor(rect.left() / step) * step
        top = math.floor(rect.top() / step) * step
        # At minimum zoom, points can otherwise become needlessly expensive.
        if rect.width() / step * rect.height() / step < 18000:
            points = []
            for x in range(int(left), int(rect.right()) + step, step):
                for y in range(int(top), int(rect.bottom()) + step, step):
                    points.append(QPointF(x, y))
            if points:
                painter.drawPoints(points)


class GraphView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumSize(300, 300)
        self.setBackgroundBrush(BG)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        next_scale = self.transform().m11() * factor
        if .18 <= next_scale <= 3:
            self.scale(factor, factor)
        event.accept()

    def fit_graph(self):
        items = self.scene().itemsBoundingRect()
        if items.isEmpty():
            self.resetTransform()
            return
        area = items.adjusted(-75, -75, 75, 75)
        self.scene().setSceneRect(area.adjusted(-350, -350, 350, 350))
        self.fitInView(area, Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.25:
            self.resetTransform()
            self.scale(1.25, 1.25)
            self.centerOn(items.center())


class GraphLab(QWidget):
    """Éditeur de graphe dirigé avec sérialisation et parcours pédagogique animé.

    Le parcours visite chaque nœud une fois, même en présence de cycles. Il ne
    lance aucun code utilisateur : les cartes sont des étapes de visualisation.
    """

    activity = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._sequence: deque[tuple[str, str | None]] = deque()
        self._active_node: str | None = None
        self._visited_count = 0
        self._timer = QTimer(self)
        self._timer.setInterval(550)
        self._timer.timeout.connect(self._simulation_step)
        self._build_ui()
        self.demo_graph()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        toolbar = QHBoxLayout()
        for caption, callback, primary in (
            ("＋ Nœud", lambda: self.add_node(), True),
            ("Cadrer", self.fit_graph, False),
            ("Démo", self.demo_graph, False),
            ("Importer", self._import_graph, False),
            ("Exporter", self._export_graph, False),
        ):
            button = QPushButton(caption)
            if primary:
                button.setProperty("primary", True)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addStretch()
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #8190aa;")
        toolbar.addWidget(self.count_label)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.scene = GraphScene(self)
        self.view = GraphView(self.scene)
        self.scene.selectionChanged.connect(self._selection_changed)
        splitter.addWidget(self.view)
        sidebar = QWidget()
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(330)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 5, 5, 5)
        side.setSpacing(12)
        heading = QLabel("INSPECTEUR")
        heading.setStyleSheet("color: #a393f5; font-weight: 700; letter-spacing: 2px;")
        side.addWidget(heading)
        self.selection_label = QLabel("Sélectionnez une carte")
        self.selection_label.setWordWrap(True)
        side.addWidget(self.selection_label)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(80)
        self.name_edit.setPlaceholderText("Nom du nœud")
        self.name_edit.editingFinished.connect(self._rename_selected)
        side.addWidget(self.name_edit)
        self.delete_button = QPushButton("Supprimer le nœud")
        self.delete_button.clicked.connect(self.delete_selected)
        side.addWidget(self.delete_button)
        side.addSpacing(8)
        connection_label = QLabel("NOUVELLE CONNEXION")
        connection_label.setStyleSheet("color: #a393f5; font-weight: 700;")
        side.addWidget(connection_label)
        form = QFormLayout()
        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        form.addRow("Depuis", self.source_combo)
        form.addRow("Vers", self.target_combo)
        side.addLayout(form)
        connect_button = QPushButton("Relier les étapes →")
        connect_button.clicked.connect(self._connect_selected)
        side.addWidget(connect_button)
        side.addSpacing(8)
        self.run_button = QPushButton("▶ Animer le parcours")
        self.run_button.setProperty("primary", True)
        self.run_button.clicked.connect(self.start_simulation)
        side.addWidget(self.run_button)
        self.stop_button = QPushButton("■ Arrêter / effacer")
        self.stop_button.clicked.connect(self.clear_simulation)
        side.addWidget(self.stop_button)
        self.simulation_label = QLabel("Parcours local · aucun code exécuté")
        self.simulation_label.setStyleSheet("color: #8190aa; font-size: 11px;")
        self.simulation_label.setWordWrap(True)
        side.addWidget(self.simulation_label)
        side.addStretch()
        help_label = QLabel("Glissez une carte pour la déplacer.\nMolette : zoom · fond : déplacement\nSuppr : retirer la carte sélectionnée")
        help_label.setStyleSheet("color: #8190aa; font-size: 11px;")
        help_label.setWordWrap(True)
        side.addWidget(help_label)
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([950, 260])
        layout.addWidget(splitter, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(250)
        self.log.setMaximumHeight(105)
        self.log.setPlaceholderText("Les événements du parcours apparaîtront ici.")
        layout.addWidget(self.log)
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.view)
        self.delete_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.delete_shortcut.activated.connect(self.delete_selected)

    def _record(self, message):
        self.log.appendPlainText(message)
        self.activity.emit(message)

    def _refresh_controls(self):
        old_source = self.source_combo.currentData()
        old_target = self.target_combo.currentData()
        self.source_combo.clear()
        self.target_combo.clear()
        for node_id, node in self.nodes.items():
            self.source_combo.addItem(node.label, node_id)
            self.target_combo.addItem(node.label, node_id)
        for combo, old in ((self.source_combo, old_source), (self.target_combo, old_target)):
            index = combo.findData(old)
            if index >= 0:
                combo.setCurrentIndex(index)
        if old_target is None and self.target_combo.count() > 1:
            self.target_combo.setCurrentIndex(1)
        self.count_label.setText(f"{len(self.nodes)} nœuds  /  {len(self.edges)} liens")
        self._selection_changed()

    def _selected_node(self):
        return next((item for item in self.scene.selectedItems() if isinstance(item, GraphNode)), None)

    def _selection_changed(self):
        node = self._selected_node()
        self.name_edit.setEnabled(node is not None)
        self.delete_button.setEnabled(node is not None)
        self.name_edit.setText(node.label if node else "")
        if node:
            incoming = sum(edge.target is node for edge in self.edges)
            outgoing = sum(edge.source is node for edge in self.edges)
            self.selection_label.setText(f"{incoming} entrée(s) · {outgoing} sortie(s)")
        else:
            self.selection_label.setText("Sélectionnez une carte")

    def _rename_selected(self):
        node = self._selected_node()
        if not node:
            return
        label = self.name_edit.text().strip()
        if not label:
            self.name_edit.setText(node.label)
            return
        if node.label == label:
            return
        node.label = label
        node.setToolTip(label)
        node.update()
        self._refresh_controls()
        self._record(f"Nœud renommé : {label}")

    def add_node(self, label="Nouveau nœud"):
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80:
            raise ValueError("Le nom doit contenir de 1 à 80 caractères.")
        if len(self.nodes) >= 300:
            self._record("Limite atteinte : 300 nœuds par graphe.")
            return None
        self.clear_simulation(erase_log=False)
        node_id = uuid.uuid4().hex[:12]
        node = GraphNode(node_id, label.strip())
        self.nodes[node_id] = node
        self.scene.addItem(node)
        center = self.view.mapToScene(self.view.viewport().rect().center())
        offset = (len(self.nodes) % 5) * 25
        node.setPos(center - QPointF(node.WIDTH / 2 - offset, node.HEIGHT / 2 - offset))
        self.scene.clearSelection()
        node.setSelected(True)
        self._refresh_controls()
        self._record(f"Nœud ajouté : {node.label}")
        return node_id

    def add_edge(self, source, target):
        if source not in self.nodes or target not in self.nodes or source == target:
            return False
        if len(self.edges) >= 3000:
            return False
        if any(edge.source.node_id == source and edge.target.node_id == target for edge in self.edges):
            return False
        self.clear_simulation(erase_log=False)
        edge = GraphEdge(self.nodes[source], self.nodes[target])
        self.scene.addItem(edge)
        self.edges.append(edge)
        self._refresh_controls()
        return True

    def _connect_selected(self):
        source, target = self.source_combo.currentData(), self.target_combo.currentData()
        if self.add_edge(source, target):
            self._record(f"Connexion : {self.nodes[source].label} → {self.nodes[target].label}")
        else:
            self._record("Connexion refusée : choisissez deux nœuds distincts sans lien existant (3 000 liens maximum).")

    def delete_selected(self):
        selected = [node for node in self.scene.selectedItems() if isinstance(node, GraphNode)]
        if not selected:
            return
        self.clear_simulation(erase_log=False)
        for node in selected:
            for edge in list(node.edges):
                edge.detach()
                self.edges.remove(edge)
                self.scene.removeItem(edge)
            self.scene.removeItem(node)
            del self.nodes[node.node_id]
        self._refresh_controls()
        self._record(f"{len(selected)} nœud(s) supprimé(s), connexions associées retirées.")

    def fit_graph(self):
        self.view.fit_graph()

    def demo_graph(self):
        self.load_graph({
            "version": 1,
            "nodes": [
                {"id": "input", "label": "Flux entrant", "kind": "SOURCE", "x": 0, "y": 110},
                {"id": "validate", "label": "Valider les données", "kind": "CONTRÔLE", "x": 255, "y": 110},
                {"id": "transform", "label": "Transformer", "kind": "OPÉRATION", "x": 510, "y": 0},
                {"id": "filter", "label": "Filtrer les anomalies", "kind": "OPÉRATION", "x": 510, "y": 220},
                {"id": "merge", "label": "Fusionner", "kind": "AGRÉGATION", "x": 765, "y": 110},
                {"id": "store", "label": "Archiver le résultat", "kind": "SORTIE", "x": 1020, "y": 0},
                {"id": "notify", "label": "Publier le rapport", "kind": "SORTIE", "x": 1020, "y": 220},
            ],
            "edges": [["input", "validate"], ["validate", "transform"], ["validate", "filter"],
                      ["transform", "merge"], ["filter", "merge"], ["merge", "store"], ["merge", "notify"]],
        })
        self._record("Graphe de démonstration chargé. Déplacez les cartes ou animez le parcours.")

    def to_dict(self):
        return {
            "version": 1,
            "nodes": [
                {"id": node_id, "label": node.label, "kind": node.kind,
                 "x": round(node.pos().x(), 3), "y": round(node.pos().y(), 3)}
                for node_id, node in self.nodes.items()
            ],
            "edges": [[edge.source.node_id, edge.target.node_id] for edge in self.edges],
        }

    @staticmethod
    def _validate_graph(data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("Format de graphe inconnu : version 1 attendue.")
        nodes, edges = data.get("nodes"), data.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ValueError("Le graphe doit contenir les listes nodes et edges.")
        if len(nodes) > 300 or len(edges) > 3000:
            raise ValueError("Limite dépassée : 300 nœuds et 3 000 liens maximum.")
        ids = set()
        normalized_nodes = []
        for node in nodes:
            if not isinstance(node, dict):
                raise ValueError("Chaque nœud doit être un objet JSON.")
            node_id, label, kind = node.get("id"), node.get("label"), node.get("kind", "OPÉRATION")
            if not isinstance(node_id, str) or not node_id or len(node_id) > 128 or node_id in ids:
                raise ValueError("Les identifiants doivent être uniques et non vides (128 caractères maximum).")
            if not isinstance(label, str) or not label.strip() or len(label) > 80:
                raise ValueError("Chaque nom doit contenir de 1 à 80 caractères.")
            if not isinstance(kind, str) or not kind.strip() or len(kind) > 30:
                raise ValueError("Chaque type doit contenir de 1 à 30 caractères.")
            coordinates = []
            for axis in ("x", "y"):
                value = node.get(axis, 0)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Les positions doivent être numériques.")
                # Bound before conversion so arbitrary-size JSON integers stay safe.
                if not -100000 <= value <= 100000 or not math.isfinite(value):
                    raise ValueError("Position de nœud hors limites.")
                coordinates.append(float(value))
            ids.add(node_id)
            normalized_nodes.append((node_id, label.strip(), kind.strip(), *coordinates))
        seen_edges = set()
        normalized_edges = []
        for edge in edges:
            if not isinstance(edge, (list, tuple)) or len(edge) != 2 or not all(isinstance(part, str) for part in edge):
                raise ValueError("Chaque lien doit contenir deux identifiants.")
            source, target = edge
            if source not in ids or target not in ids or source == target:
                raise ValueError("Un lien référence un nœud absent ou relie un nœud à lui-même.")
            if (source, target) in seen_edges:
                raise ValueError("Un lien est présent plusieurs fois.")
            seen_edges.add((source, target))
            normalized_edges.append((source, target))
        return normalized_nodes, normalized_edges

    def load_graph(self, data):
        """Valide entièrement avant de remplacer la scène ; l'échec préserve le graphe."""
        nodes, edges = self._validate_graph(data)
        self.clear_simulation(erase_log=False)
        self.scene.blockSignals(True)
        try:
            self.nodes.clear()
            self.edges.clear()
            self.scene.clear()
            for node_id, label, kind, x, y in nodes:
                node = GraphNode(node_id, label, kind)
                self.nodes[node_id] = node
                self.scene.addItem(node)
                node.setPos(x, y)
            for source, target in edges:
                edge = GraphEdge(self.nodes[source], self.nodes[target])
                self.edges.append(edge)
                self.scene.addItem(edge)
        finally:
            self.scene.blockSignals(False)
        self._refresh_controls()
        self.fit_graph()

    def _export_graph(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Exporter le graphe", "graphe-nexus.json", "Graphe JSON (*.json)")
        if not filename:
            return
        try:
            Path(filename).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Export impossible", str(exc))
            return
        self._record(f"Graphe exporté : {Path(filename).name}")

    def _import_graph(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Importer un graphe", "", "Graphe JSON (*.json)")
        if not filename:
            return
        try:
            path = Path(filename)
            if path.stat().st_size > 2_000_000:
                raise ValueError("Le fichier dépasse 2 Mo.")
            self.load_graph(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            QMessageBox.warning(self, "Graphe invalide", str(exc))
            return
        self._record(f"Graphe importé : {Path(filename).name}")

    def traversal(self):
        """Retourne un parcours en largeur couvrant aussi cycles et composantes isolées."""
        adjacency = {node_id: [] for node_id in self.nodes}
        incoming = {node_id: 0 for node_id in self.nodes}
        for edge in self.edges:
            source, target = edge.source.node_id, edge.target.node_id
            adjacency[source].append(target)
            incoming[target] += 1
        roots = [node_id for node_id in self.nodes if incoming[node_id] == 0]
        visited = set()
        result = []
        for root in roots + list(self.nodes):
            if root in visited:
                continue
            queue = deque([(root, None)])
            visited.add(root)
            while queue:
                node_id, parent = queue.popleft()
                result.append((node_id, parent))
                for target in adjacency[node_id]:
                    if target not in visited:
                        visited.add(target)
                        queue.append((target, node_id))
        return result

    def start_simulation(self):
        self.clear_simulation(erase_log=False)
        if not self.nodes:
            self._record("Ajoutez un nœud avant de démarrer le parcours.")
            return
        self._sequence = deque(self.traversal())
        self._visited_count = 0
        self.run_button.setEnabled(False)
        self._record("Parcours en largeur démarré ; chaque nœud sera visité une seule fois.")
        self._timer.start()
        self._simulation_step()

    def _simulation_step(self):
        if self._active_node in self.nodes:
            self.nodes[self._active_node].set_state("visited")
        if not self._sequence:
            self._timer.stop()
            self._active_node = None
            self.run_button.setEnabled(True)
            self.simulation_label.setText(f"Terminé · {self._visited_count} nœuds visités")
            self._record(f"Parcours terminé : {self._visited_count} nœuds visités, cycles gérés sans répétition.")
            return
        node_id, parent = self._sequence.popleft()
        self._active_node = node_id
        self.nodes[node_id].set_state("active")
        self._visited_count += 1
        if parent is not None:
            for edge in self.edges:
                if edge.source.node_id == parent and edge.target.node_id == node_id:
                    edge.active = True
                    edge.update()
        self.simulation_label.setText(f"Progression · {self._visited_count} / {len(self.nodes)}")
        self._record(f"{self._visited_count:02d}  →  {self.nodes[node_id].label}")

    def clear_simulation(self, erase_log=True):
        self._timer.stop()
        self._sequence.clear()
        self._active_node = None
        self._visited_count = 0
        for node in self.nodes.values():
            node.set_state("idle")
        for edge in self.edges:
            edge.active = False
            edge.update()
        self.run_button.setEnabled(True)
        self.simulation_label.setText("Parcours local · aucun code exécuté")
        if erase_log:
            self.log.clear()

    def shutdown(self):
        self._timer.stop()
        self._sequence.clear()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_initial_fit_done", False):
            self._initial_fit_done = True
            QTimer.singleShot(0, self.fit_graph)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
