"""Storage checks: persistence, strict validation and safe updates."""
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from nexus.tasks import TaskStore


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "nested" / "tasks.sqlite3"
        self.store = TaskStore(self.path, seed=False)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_edits_and_deletions_survive_restart(self):
        task_id = self.store.add_task("  Concevoir le projet  ", "Premier croquis", priority="high")
        self.store.update_task(task_id, status="doing", description="Croquis terminé", due_date="2030-01-15")
        self.store.close()
        self.store = TaskStore(self.path)
        tasks = self.store.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Concevoir le projet")
        self.assertEqual(tasks[0]["description"], "Croquis terminé")
        self.assertEqual(tasks[0]["status"], "doing")
        self.assertEqual(tasks[0]["due_date"], "2030-01-15")
        self.store.delete_task(task_id)
        self.store.close()
        self.store = TaskStore(self.path)
        self.assertEqual(self.store.list_tasks(), [])

    def test_invalid_updates_are_atomic(self):
        task_id = self.store.add_task("Original", status="todo")
        invalid_fields = [
            dict(title=" "), dict(title="x" * 181), dict(status="missing"),
            dict(priority="critical"), dict(due_date="2026-02-30"),
            dict(due_date="20261009"), dict(created_at="tomorrow"),
            dict(description=None), dict(description="x" * 20001),
        ]
        before = self.store.list_tasks()[0]
        for fields in invalid_fields:
            with self.subTest(fields=tuple(fields)):
                with self.assertRaises(ValueError):
                    self.store.update_task(task_id, **({"title": "Changed"} | fields))
                self.assertEqual(self.store.list_tasks()[0], before)
        self.store.update_task(task_id, status="done")
        self.assertEqual(self.store.counts()["done"], 1)

    def test_counts_include_overdue_but_exclude_completed(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.store.add_task("En attente", due_date=yesterday)
        self.store.add_task("En cours", status="doing")
        self.store.add_task("Terminée", status="done", due_date=yesterday)
        self.assertEqual(self.store.counts(), dict(todo=1, doing=1, done=1, total=3, overdue=1))

    def test_missing_ids_do_not_change_other_tasks(self):
        task_id = self.store.add_task("Conservée")
        with self.assertRaises(KeyError):
            self.store.update_task(task_id + 1, title="Introuvable")
        with self.assertRaises(KeyError):
            self.store.delete_task(task_id + 1)
        with self.assertRaises(ValueError):
            self.store.delete_task(True)
        self.assertEqual(self.store.list_tasks()[0]["title"], "Conservée")

    def test_seed_happens_only_on_initial_creation(self):
        self.store.close()
        seeded_path = Path(self.temp.name) / "demo.sqlite3"
        self.store = TaskStore(seeded_path)
        self.assertEqual(self.store.counts()["total"], 4)
        for task in self.store.list_tasks():
            self.store.delete_task(task["id"])
        self.store.close()
        self.store = TaskStore(seeded_path)
        self.assertEqual(self.store.counts()["total"], 0)

    def test_text_is_stored_literally(self):
        title = "<script> & '); DROP TABLE tasks; --"
        self.store.add_task(title, description="éè中文\nDeuxième ligne")
        self.assertEqual(self.store.list_tasks()[0]["title"], title)
        self.assertEqual(self.store.counts()["total"], 1)


if __name__ == "__main__":
    unittest.main()
