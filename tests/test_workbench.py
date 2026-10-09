"""Intégration Qt : vraies interactions, processus et persistance de session."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from nexus.app import CommandPalette, MainWindow
from nexus.editor import CodeWorkspace
from nexus.graph_lab import GraphLab
from nexus.theme import apply_theme


class QtCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.widgets = []
        self.callback_errors = []
        self.original_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.callback_errors.append(value)

    def tearDown(self):
        for widget in reversed(self.widgets):
            if hasattr(widget, "shutdown"):
                widget.shutdown()
            widget.close()
            widget.deleteLater()
        self.app.processEvents()
        sys.excepthook = self.original_hook
        self.temp.cleanup()
        self.assertEqual(self.callback_errors, [], "Une exception a été levée dans un callback Qt")

    def own(self, widget):
        self.widgets.append(widget)
        return widget

    def until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        self.fail("L’opération Qt n’a pas terminé dans le délai")


class EditorTests(QtCase):
    def test_execute_unicode_stdout_stderr_and_exit_code(self):
        editor = self.own(CodeWorkspace(self.root))
        editor.current_editor().setPlainText("import sys\nprint('résultat =', 6 * 7)\nprint('diagnostic', file=sys.stderr)\n")
        self.assertTrue(editor.run_current())
        self.until(lambda: editor.process is None)
        output = editor.output.toPlainText()
        self.assertIn("résultat = 42", output)
        self.assertIn("diagnostic", output)
        self.assertIn("code 0", output)
        self.assertIsNone(editor._run_temporary)

    def test_save_search_and_cancel_unsaved_close(self):
        path = self.root / "script.py"
        path.write_text("print('avant')\n", encoding="utf-8")
        editor = self.own(CodeWorkspace(self.root))
        self.assertTrue(editor.open_file(path))
        editor.current_editor().setPlainText("print('après')\n")
        editor.current_editor().document().setModified(True)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(editor.confirm_close())
        self.assertTrue(editor.save_current())
        self.assertEqual(path.read_text(encoding="utf-8"), "print('après')\n")
        editor.search_input.setText("après")
        self.assertTrue(editor.find_next())
        self.assertEqual(editor.current_editor().textCursor().selectedText(), "après")

    def test_stop_process_and_nonzero_exit(self):
        editor = self.own(CodeWorkspace(self.root))
        editor.current_editor().setPlainText("raise RuntimeError('échec voulu')")
        editor.run_current()
        self.until(lambda: editor.process is None)
        self.assertIn("code 1", editor.output.toPlainText())
        self.assertIn("échec voulu", editor.output.toPlainText())
        editor.current_editor().setPlainText("import time\nprint('démarré', flush=True)\ntime.sleep(30)")
        editor.run_current()
        self.until(lambda: "démarré" in editor.output.toPlainText())
        editor.stop_process()
        self.until(lambda: editor.process is None)


class GraphTests(QtCase):
    def test_roundtrip_invalid_import_and_cycle_traversal(self):
        graph = self.own(GraphLab())
        initial = graph.to_dict()
        graph.load_graph(copy.deepcopy(initial))
        self.assertEqual(graph.to_dict(), initial)
        invalid = copy.deepcopy(initial)
        invalid["edges"].append(["missing", "missing2"])
        with self.assertRaises(ValueError):
            graph.load_graph(invalid)
        self.assertEqual(graph.to_dict(), initial)
        ids = list(graph.nodes)
        graph.add_edge(ids[-1], ids[0])
        self.assertEqual(set(node_id for node_id, _ in graph.traversal()), set(ids))
        self.assertEqual(len(graph.traversal()), len(ids))
        graph.start_simulation()
        graph._timer.stop()
        for _ in range(len(ids) + 1):
            graph._simulation_step()
        self.assertTrue(all(node.state == "visited" for node in graph.nodes.values()))
        self.assertTrue(graph.run_button.isEnabled())

    def test_drag_updates_edges_and_delete_detaches(self):
        graph = self.own(GraphLab())
        edge = graph.edges[0]
        node = edge.source
        original = edge.path().pointAtPercent(0)
        node.setPos(node.pos() + QPointF(50, 70))
        self.assertNotEqual(original, edge.path().pointAtPercent(0))
        node_id = node.node_id
        node.setSelected(True)
        graph.delete_selected()
        self.assertNotIn(node_id, graph.nodes)
        self.assertTrue(all(e.source.node_id != node_id and e.target.node_id != node_id for e in graph.edges))
        graph.resize(1100, 700)
        graph.show()
        self.app.processEvents()
        self.assertFalse(graph.grab().isNull())


class WindowTests(QtCase):
    def test_navigation_palette_rendering_metrics_and_restore(self):
        state = self.root / "state"
        window = self.own(MainWindow(self.root, state, restore=False))
        window.show()
        self.app.processEvents()
        for index in range(5):
            QTest.mouseClick(window.nav_buttons[index], Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertEqual(window.stack.currentIndex(), index)
            self.assertFalse(window.grab().isNull())
        palette = self.own(CommandPalette([("Aller au code", lambda: window.navigate(1)), ("Voir les données", lambda: window.navigate(2))], window))
        palette.search.setText("données")
        self.assertEqual(palette.results.count(), 1)
        palette.execute()
        self.assertEqual(window.stack.currentIndex(), 2)
        before = window.dashboard.samples
        window.dashboard.collect()
        self.assertGreater(window.dashboard.samples, before)
        window.graph.add_node("Persistant")
        window.save_session()
        restored = self.own(MainWindow(self.root, state))
        self.assertEqual(restored.stack.currentIndex(), 2)
        self.assertTrue(any(n.label == "Persistant" for n in restored.graph.nodes.values()))
        self.assertEqual(restored.tasks.stats(), window.tasks.stats())


if __name__ == "__main__":
    unittest.main()
