"""Tableau de bord : métriques réelles de la machine et tracés vectoriels."""
from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
import platform
import time

import psutil
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .theme import BORDER, MINT, MUTED, PURPLE, TEXT


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return frame, layout


class MetricCard(QFrame):
    def __init__(self, title, color=MINT, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)
        layout.addWidget(label(title, "eyebrow"))
        self.value = label("—")
        self.value.setStyleSheet("font-size: 29px; font-weight: 700;")
        layout.addWidget(self.value)
        self.detail = label("Collecte des mesures…", "muted")
        layout.addWidget(self.detail)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
        layout.addWidget(self.progress)

    def set_value(self, value, detail, percent):
        self.value.setText(value)
        self.detail.setText(detail)
        self.progress.setValue(round(max(0, min(percent, 100)) * 10))


class TelemetryChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cpu = deque(maxlen=120)
        self.ram = deque(maxlen=120)
        self.mode = "CPU + mémoire"
        self.setMinimumHeight(210)
        self.setMouseTracking(True)
        self.hover_x = None

    def append(self, cpu, ram):
        self.cpu.append(cpu)
        self.ram.append(ram)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = QRectF(36, 12, max(10, self.width() - 52), max(10, self.height() - 42))
        p.setFont(QFont("DejaVu Sans", 8))
        for value in (0, 25, 50, 75, 100):
            y = plot.bottom() - plot.height() * value / 100
            p.setPen(QPen(QColor("#202c3e"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, y - 7, 29, 14), Qt.AlignmentFlag.AlignRight, str(value))
        series = []
        if self.mode != "Mémoire":
            series.append((self.cpu, MINT))
        if self.mode != "CPU":
            series.append((self.ram, PURPLE))
        for values, color in series:
            if not values:
                continue
            points = [QPointF(plot.left() + i / max(1, len(values) - 1) * plot.width(),
                              plot.bottom() - value / 100 * plot.height())
                      for i, value in enumerate(values)]
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            fill = QPainterPath(path)
            fill.lineTo(points[-1].x(), plot.bottom())
            fill.lineTo(plot.left(), plot.bottom())
            fill.closeSubpath()
            gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
            shade = QColor(color)
            shade.setAlpha(38)
            gradient.setColorAt(0, shade)
            shade.setAlpha(0)
            gradient.setColorAt(1, shade)
            p.fillPath(fill, gradient)
            p.setPen(QPen(QColor(color), 2.2))
            p.drawPath(path)
            p.setBrush(QColor(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(points[-1], 3.5, 3.5)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(plot.left(), plot.bottom() + 10, 220, 20), "Historique de cette session")
        p.drawText(QRectF(plot.right() - 110, plot.bottom() + 10, 110, 20), Qt.AlignmentFlag.AlignRight, "Maintenant")
        if self.hover_x is not None and self.cpu:
            fraction = max(0, min(1, (self.hover_x - plot.left()) / plot.width()))
            index = round(fraction * (len(self.cpu) - 1))
            x = plot.left() + fraction * plot.width()
            p.setPen(QPen(QColor("#65748c"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            box = QRectF(max(plot.left(), min(x + 10, plot.right() - 168)), plot.top() + 8, 162, 44)
            p.setBrush(QColor("#1b293e"))
            p.setPen(QColor(BORDER))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(QColor(TEXT))
            p.drawText(box.adjusted(10, 4, -8, -4), f"CPU   {self.cpu[index]:.1f} %\nRAM   {self.ram[index]:.1f} %")
        p.end()

    def mouseMoveEvent(self, event):
        self.hover_x = event.position().x()
        self.update()

    def leaveEvent(self, event):
        self.hover_x = None
        self.update()


class Dashboard(QWidget):
    navigate = Signal(int)

    def __init__(self, workspace: Path, stats_provider, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.stats_provider = stats_provider
        self.started = time.monotonic()
        self.samples = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        banner = QFrame()
        banner.setObjectName("welcome")
        banner.setStyleSheet("QFrame#welcome { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #173930,stop:0.65 #14282e,stop:1 #1c2540); border: 1px solid #2d514c; border-radius: 12px; }")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(24, 21, 24, 21)
        welcome_text = QVBoxLayout()
        eyebrow = label("UN ESPACE. TOUTES VOS IDÉES.")
        eyebrow.setStyleSheet(f"color: {MINT}; font-size: 10px; letter-spacing: 2px;")
        welcome_text.addWidget(eyebrow)
        title = label("Créez. Explorez. Connectez.")
        title.setStyleSheet("font-size: 23px; font-weight: 700;")
        welcome_text.addWidget(title)
        subtitle = label("Votre atelier Python, des premières lignes aux données.")
        subtitle.setStyleSheet("color: #a2bdb8;")
        welcome_text.addWidget(subtitle)
        banner_layout.addLayout(welcome_text, 1)
        start_button = QPushButton("Ouvrir l’atelier   →")
        start_button.setObjectName("primary")
        start_button.clicked.connect(lambda: self.navigate.emit(1))
        banner_layout.addWidget(start_button)
        layout.addWidget(banner)

        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        self.cpu_card = MetricCard("PROCESSEUR")
        self.ram_card = MetricCard("MÉMOIRE", PURPLE)
        self.disk_card = MetricCard("STOCKAGE", "#73b8f1")
        self.tasks_card = MetricCard("PROJET", "#e9c27b")
        for metric in (self.cpu_card, self.ram_card, self.disk_card, self.tasks_card):
            metrics.addWidget(metric, 1)
        layout.addLayout(metrics)

        center = QHBoxLayout()
        center.setSpacing(18)
        telemetry, chart_layout = card()
        telemetry.setMinimumHeight(330)
        chart_heading = QHBoxLayout()
        chart_heading.addWidget(label("Activité de la machine", "cardTitle"))
        chart_heading.addStretch()
        self.mode = QComboBox()
        self.mode.addItems(["CPU + mémoire", "CPU", "Mémoire"])
        self.mode.currentTextChanged.connect(self._change_mode)
        chart_heading.addWidget(self.mode)
        chart_layout.addLayout(chart_heading)
        self.chart = TelemetryChart()
        chart_layout.addWidget(self.chart, 1)
        chart_footer = QHBoxLayout()
        legend = label("●  CPU       ●  Mémoire", "muted")
        chart_footer.addWidget(legend)
        chart_footer.addStretch()
        self.sampling = QLabel("Collecte · 1 s")
        self.sampling.setObjectName("muted")
        chart_footer.addWidget(self.sampling)
        self.pause = QPushButton("Pause")
        self.pause.setCheckable(True)
        self.pause.clicked.connect(self._toggle_pause)
        chart_footer.addWidget(self.pause)
        chart_layout.addLayout(chart_footer)
        center.addWidget(telemetry, 3)

        quick, quick_layout = card()
        quick.setMinimumHeight(330)
        quick_layout.setSpacing(6)
        quick_layout.addWidget(label("Vos outils", "cardTitle"))
        quick_layout.addWidget(label("Passez de l’idée au résultat.", "muted"))
        for index, title, detail in (
            (1, "01   Atelier de code", "Python · onglets · console"),
            (2, "02   Data lab", "CSV · statistiques · graphiques"),
            (3, "03   Flow lab", "Nœuds · connexions · parcours"),
            (4, "04   Tableau de projet", "Tâches · priorités · échéances"),
        ):
            button = QPushButton(title + "   ↗")
            button.setStyleSheet("text-align: left; padding: 7px;")
            button.setMinimumHeight(32)
            button.clicked.connect(lambda checked=False, i=index: self.navigate.emit(i))
            quick_layout.addWidget(button)
            hint = label(detail, "muted")
            hint.setStyleSheet("color: #8190aa; font-size: 10px; padding-left: 6px;")
            quick_layout.addWidget(hint)
        quick_layout.addStretch()
        center.addWidget(quick, 2)
        layout.addLayout(center, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(18)
        activity, activity_layout = card()
        activity_layout.addWidget(label("Journal de session", "cardTitle"))
        self.events = QListWidget()
        self.events.setMinimumHeight(95)
        self.events.setMaximumHeight(145)
        self.events.setStyleSheet("QListWidget { border: none; background: transparent; } QListWidget::item { padding: 5px 0; }")
        activity_layout.addWidget(self.events)
        bottom.addWidget(activity, 3)
        info, info_layout = card()
        info_layout.addWidget(label("ENVIRONNEMENT", "eyebrow"))
        self.system_label = label(f"{platform.system()}  /  Python {platform.python_version()}")
        info_layout.addWidget(self.system_label)
        workspace_label = label(workspace.name, "muted")
        workspace_label.setToolTip(str(workspace))
        info_layout.addWidget(workspace_label)
        self.session_label = label("Session ouverte", "muted")
        info_layout.addWidget(self.session_label)
        info_layout.addStretch()
        bottom.addWidget(info, 2)
        layout.addLayout(bottom)

        psutil.cpu_percent(interval=None)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.collect)
        self.timer.start()
        self.collect()
        self.add_activity("Nexus Studio est prêt. Bienvenue dans votre atelier.")

    def collect(self):
        cpu = psutil.cpu_percent(interval=None) if self.samples else 0.0
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage(str(self.workspace))
        stats = self.stats_provider()
        total = stats.get("total", sum(stats.get(s, 0) for s in ("todo", "doing", "done")))
        done = stats.get("done", 0)
        self.cpu_card.set_value(f"{cpu:.1f} %", f"{psutil.cpu_count() or 1} processeurs logiques", cpu)
        self.ram_card.set_value(f"{ram.percent:.1f} %", f"{ram.used / 2**30:.1f} / {ram.total / 2**30:.1f} Go", ram.percent)
        self.disk_card.set_value(f"{disk.percent:.1f} %", f"{disk.free / 2**30:.1f} Go disponibles", disk.percent)
        self.tasks_card.set_value(f"{done} / {total}", "tâches terminées", 100 * done / max(1, total))
        self.chart.append(cpu, ram.percent)
        self.samples += 1
        elapsed = int(time.monotonic() - self.started)
        self.session_label.setText(f"Session · {elapsed // 60:02d}:{elapsed % 60:02d}  /  {self.samples} mesures")

    def _change_mode(self, text):
        self.chart.mode = text
        self.chart.update()

    def _toggle_pause(self, checked):
        if checked:
            self.timer.stop()
        else:
            self.timer.start()
            self.collect()
        self.pause.setText("Reprendre" if checked else "Pause")
        self.sampling.setText("Collecte en pause" if checked else "Collecte · 1 s")

    def add_activity(self, message):
        item = QListWidgetItem(f"{datetime.now():%H:%M:%S}    {message}")
        item.setToolTip(message)
        self.events.insertItem(0, item)
        while self.events.count() > 100:
            self.events.takeItem(self.events.count() - 1)

    def shutdown(self):
        self.timer.stop()
