"""使用临时目录验证，不触碰用户文件。运行 python -m unittest -v test_organizer"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test1 import build_plan, execute_plan, summarize


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content='data'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def test_preview_has_no_side_effects_and_nested_files_untouched(self):
        self.write('PHOTO.JPG')
        self.write('nested/song.mp3')
        plan = build_plan(self.root)
        self.assertEqual(summarize(plan)['preview'], 1)
        self.assertFalse((self.root / 'images').exists())
        execute_plan(plan)
        self.assertTrue((self.root / 'images/PHOTO.JPG').exists())
        self.assertTrue((self.root / 'nested/song.mp3').exists())

    def test_skip_conflict_preserves_both(self):
        self.write('a.pdf', 'new')
        self.write('documents/a.pdf', 'old')
        result = execute_plan(build_plan(self.root))
        self.assertEqual(summarize(result)['skip'], 1)
        self.assertEqual((self.root / 'a.pdf').read_text(), 'new')
        self.assertEqual((self.root / 'documents/a.pdf').read_text(), 'old')

    def test_compound_extension_rename(self):
        self.write('a.tar.gz')
        self.write('archives/a.tar.gz')
        self.write('archives/a (1).tar.gz')
        result = execute_plan(build_plan(self.root, 'rename'))
        self.assertEqual(summarize(result)['success'], 1)
        self.assertTrue((self.root / 'archives/a (2).tar.gz').exists())

    def test_preview_snapshot_and_changed_source(self):
        source = self.write('a.txt')
        plan = build_plan(self.root)
        source.write_text('changed content')
        self.write('later.pdf')
        result = execute_plan(plan)
        self.assertEqual(summarize(result)['skip'], 1)
        self.assertTrue(source.exists())
        self.assertTrue((self.root / 'later.pdf').exists())

    def test_new_target_after_preview_never_overwritten(self):
        source = self.write('a.txt')
        plan = build_plan(self.root)
        target = self.write('documents/a.txt', 'keep')
        result = execute_plan(plan)
        self.assertEqual(summarize(result)['skip'], 1)
        self.assertTrue(source.exists())
        self.assertEqual(target.read_text(), 'keep')

    def test_unknown_opt_in_and_blocked_category(self):
        self.write('README')
        self.write('a.pdf')
        self.write('documents')
        plan = build_plan(self.root)
        self.assertEqual(summarize(plan)['skip'], 3)
        result = execute_plan(build_plan(self.root, include_unknown=True))
        self.assertTrue((self.root / 'others/README').exists())
        self.assertTrue((self.root / 'a.pdf').exists())

    def test_protect_program_files(self):
        one = self.write('test1.py')
        two = self.write('gui_v2.py')
        with patch('test1.protected_files', return_value={one, two}):
            self.assertEqual(summarize(build_plan(self.root))['skip'], 2)

    def test_copy_failure_preserves_source_and_cleans_partial(self):
        source = self.write('a.txt')
        def fail(reader, writer):
            writer.write(b'partial')
            raise OSError('simulated full disk')
        with patch('test1.shutil.copyfileobj', side_effect=fail):
            result = execute_plan(build_plan(self.root))
        self.assertEqual(summarize(result)['fail'], 1)
        self.assertTrue(source.exists())
        self.assertFalse((self.root / 'documents/a.txt').exists())


if __name__ == '__main__':
    unittest.main()
