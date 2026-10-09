"""Run with QT_QPA_PLATFORM=offscreen python -m unittest tests.test_data_lab."""

import csv
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from nexus.data_lab import DataLab, numeric_value


class DataLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.lab = DataLab()

    def tearDown(self):
        self.lab.close()
        self.lab.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def test_filtered_numeric_sort_export_preserves_values(self):
        source = self.root / "data.csv"
        source.write_text("\ufeffVille;Valeur;Note\nParis;10,5;a\nLyon;100;b\nParis;2,5;c\n", encoding="utf-8")
        self.assertEqual(self.lab.load_csv(source), 3)
        self.lab.filter_input.setText("Paris")
        self.lab.proxy.sort(1, Qt.SortOrder.AscendingOrder)
        self.lab._refresh_analysis()
        self.assertEqual(self.lab.metrics["mean"].text(), "6,50")
        self.assertEqual(self.lab.metrics["rows"].text(), "2")
        target = self.root / "export.csv"
        self.assertEqual(self.lab.export_csv(target), 2)
        with target.open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.reader(handle))
        self.assertEqual(records, [["Ville", "Valeur", "Note"], ["Paris", "2,5", "c"], ["Paris", "10,5", "a"]])

    def test_invalid_csv_does_not_replace_dataset(self):
        source = self.root / "invalid.csv"
        source.write_text('A,B\n1,"unterminated\n', encoding="utf-8")
        original_rows = list(self.lab.view_model.rows)
        with self.assertRaises(ValueError):
            self.lab.load_csv(source)
        self.assertEqual(self.lab.view_model.rows, original_rows)

    def test_blank_and_duplicate_headers_and_missing_cells(self):
        source = self.root / "headers.csv"
        source.write_text("A;A;\n1;2;3\n4;5\n", encoding="utf-8")
        self.lab.load_csv(source)
        self.assertEqual(self.lab.view_model.headers, ["A", "A (2)", "Colonne 3"])
        self.assertEqual(self.lab.view_model.rows[-1], ("4", "5", ""))

    def test_nonfinite_numbers_are_excluded(self):
        for text in ("nan", "inf", "-inf", "1e400", "", "texte"):
            self.assertIsNone(numeric_value(text))
        self.assertEqual(numeric_value("1\u202f234,5"), 1234.5)

    def test_chart_renders_all_modes_and_empty_filter(self):
        self.lab.resize(1100, 800)
        self.lab.show()
        for mode in ("Dispersion", "Courbe", "Histogramme"):
            self.lab.chart_type.setCurrentText(mode)
            self.lab._refresh_analysis()
            self.app.processEvents()
            self.assertFalse(self.lab.grab().isNull())
        self.lab.filter_input.setText("aucune ligne ne correspond")
        self.lab._refresh_analysis()
        self.assertEqual(self.lab.metrics["rows"].text(), "0")
        self.assertEqual(self.lab.metrics["mean"].text(), "—")
        self.assertFalse(self.lab.grab().isNull())


if __name__ == "__main__":
    unittest.main()
