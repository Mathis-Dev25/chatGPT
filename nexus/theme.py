"""Identité visuelle commune aux espaces de travail."""
from PySide6.QtGui import QColor, QFont, QPalette

BG = "#0b101b"
SURFACE = "#111827"
BORDER = "#253044"
TEXT = "#e6edf7"
MUTED = "#8190aa"
MINT = "#72e6bf"
PURPLE = "#a393f5"

STYLESHEET = """
QWidget { color: #e6edf7; font-family: 'Inter', 'Segoe UI', 'DejaVu Sans', sans-serif; font-size: 12px; }
QMainWindow, QDialog { background: #0b101b; }
QToolTip { background: #253044; color: #e6edf7; border: 1px solid #435572; padding: 6px; }
QLabel { background: transparent; }
QFrame#sidebar { background: #0e1522; border-right: 1px solid #253044; }
QFrame#topbar { border-bottom: 1px solid #253044; }
QFrame#card, QGroupBox { background: #111827; border: 1px solid #253044; border-radius: 12px; }
QGroupBox { margin-top: 12px; padding-top: 15px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QLabel#muted { color: #8190aa; }
QLabel#eyebrow { color: #8190aa; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel#heading { font-size: 27px; font-weight: 700; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; }
QPushButton, QToolButton { background: #192235; border: 1px solid #29364d; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover, QToolButton:hover { background: #25344b; border-color: #546684; }
QPushButton:pressed { background: #31405a; }
QPushButton:disabled { color: #57647c; border-color: #202c3f; background: #141d2c; }
QPushButton#primary, QPushButton[primary="true"] { background: #72e6bf; color: #102d25; font-weight: 700; border-color: #72e6bf; }
QPushButton#primary:hover, QPushButton[primary="true"]:hover { background: #a0f2d7; }
QPushButton#nav { text-align: left; background: transparent; color: #91a0b7; border: 0; padding: 12px 13px; font-size: 12px; }
QPushButton#nav:hover { color: #e6edf7; background: #172236; }
QPushButton#nav:checked { color: #72e6bf; background: #17342f; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox { background: #0d1422; border: 1px solid #29364d; border-radius: 6px; padding: 7px; selection-background-color: #355b68; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #72e6bf; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #172236; selection-background-color: #284339; }
QAbstractItemView { background: #0d1422; border: 1px solid #253044; border-radius: 6px; alternate-background-color: #121c2b; selection-background-color: #24423b; selection-color: #e6edf7; }
QTreeView::item, QListView::item { padding: 5px; }
QHeaderView::section { background: #192235; border: 0; border-right: 1px solid #29364d; border-bottom: 1px solid #29364d; padding: 8px; color: #a8b6ca; }
QTableView { gridline-color: #1f2b3d; }
QTabWidget::pane { border: 1px solid #253044; background: #111827; border-radius: 4px; }
QTabBar::tab { background: #111827; color: #8190aa; padding: 10px 18px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #72e6bf; border-bottom-color: #72e6bf; background: #172236; }
QSplitter::handle { background: #1a2639; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 0; }
QScrollBar::handle { background: #31405a; border-radius: 4px; min-height: 24px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMenu { background: #152033; border: 1px solid #33425a; padding: 5px; }
QMenu::item { padding: 7px 24px; }
QMenu::item:selected { background: #284339; }
QStatusBar { color: #8190aa; background: #0e1522; border-top: 1px solid #253044; font-size: 10px; }
QProgressBar { background: #263348; border: 0; border-radius: 3px; height: 5px; }
QProgressBar::chunk { background: #72e6bf; border-radius: 3px; }
QCheckBox { spacing: 8px; }
"""

def apply_theme(app):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, BG),
                        (QPalette.ColorRole.WindowText, TEXT),
                        (QPalette.ColorRole.Base, BG),
                        (QPalette.ColorRole.AlternateBase, SURFACE),
                        (QPalette.ColorRole.Text, TEXT),
                        (QPalette.ColorRole.Button, SURFACE),
                        (QPalette.ColorRole.ButtonText, TEXT),
                        (QPalette.ColorRole.Highlight, "#355b68"),
                        (QPalette.ColorRole.HighlightedText, TEXT)):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setFont(QFont("DejaVu Sans", 10))
    app.setStyleSheet(STYLESHEET)
