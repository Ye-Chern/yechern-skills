"""Targeted synthetic recovery regressions; never touches user ledgers."""
import importlib.util
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('task_memory.py')
spec = importlib.util.spec_from_file_location('memory_reliability', SCRIPT)
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='durable-reliability-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve() / '原项目 with spaces'
        self.project.mkdir()
        self.root = self.project / 'memory'
        (self.project / 'contract.md').write_text('Goal: recover only. No tool execution.', encoding='utf8')
        (self.project / 'current.txt').write_text('current receipt', encoding='utf8')
        self.cli('init', project=self.project, contract=self.project / 'contract.md')

    def cli(self, command, code=0, **args):
        argv = [sys.executable, str(SCRIPT), command, '--root', str(self.root)]
        for key, value in args.items():
            if value is True:
                argv.append('--' + key.replace('_', '-'))
            elif value is not False and value is not None:
                argv.extend(['--' + key.replace('_', '-'), str(value)])
        result = subprocess.run(argv, capture_output=True, text=True, encoding='utf8')
        self.assertEqual(result.returncode, code, (argv, result.stdout, result.stderr))
        return result.stdout if code in {0, 2} else result.stderr

    def node(self, key, kind='evidence', status='accepted', deps=(), files=('current.txt',), **extra):
        return dict(id=key, kind=kind, status=status, title='entry ' + key, scope='synthetic fixture only',
                    rationale='needed by this recovery decision', depends_on=list(deps), files=list(files),
                    validation=dict(method='read receipt', result='receipt recorded', limits='not semantic proof'),
                    **extra)

    def put(self, node, revision=0, code=0, **args):
        path = self.project / 'put.json'
        path.write_text(json.dumps(node), encoding='utf8')
        return self.cli('put', code=code, file=path, expected_revision=revision, **args)

    def focus(self, ids, action='check current receipt', code=0, **args):
        path = self.project / 'focus.json'
        path.write_text(json.dumps(dict(ids=ids, next_action=action)), encoding='utf8')
        return self.cli('focus', code=code, file=path, **args)

    def events(self):
        with memory.connection(self.root) as con:
            return list(con.execute('SELECT seq,kind,payload FROM events ORDER BY seq'))

    def test_thousand_archived_nodes_do_not_fill_current_view(self):
        self.put(self.node('E'))
        self.put(self.node('C', 'claim', deps=['E'], files=[]))
        self.put(self.node('T', 'task', 'open', deps=['C'], files=[]))
        with memory.connection(self.root) as con:
            nodes, meta, _, _ = memory.replay(con)
            for i in range(1200):
                data = memory.validate_node(self.node(f'History{i:04d}', status='retracted', files=[]), nodes, meta, 0)
                memory.append(con, 'put', data)
                nodes[data['id']] = data
        self.focus(['T'])
        content = self.cli('resume')
        self.assertLess(len(content), 2000)
        self.assertNotIn('History0000', content)
        self.assertIn('1200', content)
        page = json.loads(self.cli('list', status='retracted', limit=17, offset=1190))
        self.assertEqual((page['total'], len(page['items']), page['next_offset']), (1200, 10, None))
        self.put(self.node('E', status='retracted'), revision=1)
        content = self.cli('resume')
        self.assertIn('E@2 [evidence/retracted]', content)
        self.assertIn('C@1 [claim/needs-review]', content)
        self.assertIn('T@1 [task/needs-review]', content)
        review = json.loads(self.cli('audit', code=2))['review']
        self.assertEqual(set(review), {'C', 'T'})

    def test_explicit_negative_reference_keeps_transitive_context(self):
        self.put(self.node('OldE', status='retracted'))
        self.put(self.node('OldC', 'claim', 'retracted', deps=['OldE'], files=[]))
        self.put(self.node('T', 'task', 'open', files=[], rejected_ids=['OldC']))
        self.focus(['T'])
        content = self.cli('resume')
        self.assertIn('HISTORICAL REFERENCE OldE', content)
        self.assertIn('HISTORICAL REFERENCE OldC', content)
        self.assertNotIn('Outside-focus risks', content)

    def test_legacy_invalid_negative_reference_is_visible_not_a_crash(self):
        data = self.node('T', 'task', 'open', files=[])
        data.update(revision=1, dep_revisions={}, rejected_ids=42)
        with memory.connection(self.root) as con:
            memory.append(con, 'put', data)
        self.focus(['T'])
        self.assertIn('invalid legacy rejected_ids', self.cli('resume'))

    def archive_fixture(self):
        (self.project / 'archive.txt').write_text('old source', encoding='utf8')
        self.put(self.node('E'))
        self.put(self.node('Old', status='retracted', files=['archive.txt']))
        target = Path(self.temp.name).resolve() / 'new project'
        target.mkdir()
        shutil.copy2(self.project / 'current.txt', target / 'current.txt')
        return target

    def test_explicit_archive_gap_retains_hash_record_and_cannot_revive(self):
        target = self.archive_fixture()
        self.cli('relocate', code=1, project=target)
        result = json.loads(self.cli('relocate', project=target, allow_missing_history=True))
        gap = result['missing_history'][0]
        self.assertEqual((gap['id'], gap['path']), ('Old', 'archive.txt'))
        self.assertEqual(gap['sha256'], memory.digest(self.project / 'archive.txt'))
        old = json.loads(self.cli('show', id='Old'))
        self.assertEqual(old['effective_status'], 'retracted')
        self.assertTrue(any('missing' in r for r in old['review_reasons']))
        self.assertEqual(json.loads(self.cli('audit'))['relocation_missing_history'], [gap])
        self.put(self.node('Old', files=['archive.txt']), revision=1, code=1)
        self.assertEqual(json.loads(self.cli('show', id='Old'))['node']['revision'], 1)
        event = json.loads(self.events()[-1][2])
        self.assertEqual(event['missing_history'], [gap])

    def test_archive_gap_cannot_skip_live_dependency_or_shared_current_file(self):
        target = self.archive_fixture()
        self.put(self.node('T', 'task', 'open', deps=['Old'], files=[]))
        self.cli('relocate', code=1, project=target, allow_missing_history=True)
        self.put(self.node('T', 'task', 'open', files=[]), revision=1)
        self.put(self.node('E', files=['archive.txt']), revision=1)
        self.cli('relocate', code=1, project=target, allow_missing_history=True)

    def test_archive_gap_does_not_permit_changed_history_or_path_escape(self):
        target = self.archive_fixture()
        (target / 'archive.txt').write_text('different', encoding='utf8')
        self.assertIn('mismatch', self.cli('relocate', code=1, project=target, allow_missing_history=True))
        data = self.node('Escape', status='retracted', files=[])
        data.update(revision=1, dep_revisions={}, files=[dict(path='../absent.txt', sha256='0' * 64)])
        with memory.connection(self.root) as con:
            memory.append(con, 'put', data)
        (target / 'archive.txt').write_text('old source', encoding='utf8')
        self.assertIn('escapes', self.cli('relocate', code=1, project=target, allow_missing_history=True))

    def test_archive_gap_never_exempts_permission_errors_or_directories(self):
        target = self.archive_fixture()
        inaccessible = target / 'archive.txt'
        inaccessible.write_text('old source', encoding='utf8')
        original_stat, original_is_file, original_exists = Path.stat, Path.is_file, Path.exists

        def denied_stat(path, *args, **kwargs):
            if path == inaccessible:
                raise PermissionError('simulated unreadable history')
            return original_stat(path, *args, **kwargs)

        # Simulate Python 3.14 query helpers suppressing OSError; stat must still reject it.
        def query_is_file(path, *args, **kwargs):
            return False if path == inaccessible else original_is_file(path, *args, **kwargs)

        def query_exists(path, *args, **kwargs):
            return False if path == inaccessible else original_exists(path, *args, **kwargs)

        before = self.events()
        argv = ['task_memory.py', 'relocate', '--root', str(self.root), '--project', str(target),
                '--allow-missing-history']
        with patch.object(Path, 'stat', denied_stat), patch.object(Path, 'is_file', query_is_file), \
                patch.object(Path, 'exists', query_exists), patch.object(sys, 'argv', argv), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(PermissionError):
            memory.main()
        self.assertEqual(self.events(), before)
        inaccessible.unlink()
        inaccessible.mkdir()
        self.assertIn('not a regular file', self.cli('relocate', code=1, project=target, allow_missing_history=True))
        self.assertEqual(self.events(), before)

    def test_strict_completion_is_opt_in_scoped_and_transitive(self):
        empty = self.node('Empty', 'task', 'done', files=[])
        empty.pop('validation')
        self.put(empty)
        self.cli('audit')
        self.assertEqual(json.loads(self.cli('show', id='Empty'))['completion_status'], 'claimed')
        self.put(self.node('Child', 'decision', deps=['Empty'], files=[]))
        review = json.loads(self.cli('audit', code=2, strict=True))['review']
        self.assertEqual(set(review), {'Empty', 'Child'})
        self.put(self.node('False', 'task', 'done', files=[], completion='verified'), code=1, strict=True)
        self.put(self.node('Empty', 'task', 'open', files=[]), revision=1)
        self.put(self.node('Child', 'decision', 'superseded', deps=['Empty'], files=[]), revision=1)
        poem = self.node('Creative', 'task', 'done', completion='verified')
        poem['validation'] = dict(method='review against user taste', result='accepted for this draft', limits='subjective scope only')
        self.put(poem, strict=True)
        self.cli('audit', strict=True)
        (self.project / 'current.txt').write_text('changed', encoding='utf8')
        self.assertIn('Creative', json.loads(self.cli('audit', code=2, strict=True))['review'])

    def test_unknown_execution_is_preserved_not_retried_or_completed(self):
        result = self.project / 'current.txt'
        original = result.read_bytes()
        node = self.node('Unknown', 'task', 'open', completion='unknown')
        node['validation']['method'] = 'DO NOT EXECUTE ANY COMMAND; inspect existing receipt'
        self.put(node)
        self.focus(['Unknown'], action='verify receipt before any retry')
        self.assertIn('completion: unknown', self.cli('resume'))
        node['status'] = 'done'
        self.put(node, revision=1, code=1)
        self.assertEqual(result.read_bytes(), original)
        self.assertEqual(json.loads(self.cli('show', id='Unknown'))['node']['status'], 'open')

    def test_budget_success_persists_failure_does_not_and_reads_do_not_append(self):
        self.put(self.node('T', 'task', 'open', files=[]))
        self.focus(['T'], chars=9000)
        self.cli('resume', chars=8000)
        count = len(self.events())
        self.cli('resume')
        self.cli('resume', chars=8000)
        self.assertEqual(len(self.events()), count)
        self.cli('resume', code=1, chars=10)
        self.assertEqual(len(self.events()), count)
        self.assertEqual(json.loads(self.events()[-1][2])['capsule_chars'], 8000)
        self.focus(['T'], action='new focus')
        self.assertEqual(json.loads(self.events()[-1][2])['capsule_chars'], 8000)

    def test_editable_round_trip_hash_capture_and_stale_writer_rejection(self):
        self.put(self.node('E'))
        data = json.loads(self.cli('show', id='E', editable=True))
        self.assertEqual(data['files'], ['current.txt'])
        self.assertNotIn('revision', data)
        self.assertNotIn('dep_revisions', data)
        path = self.project / 'editable.json'
        data['title'] = 'changed title'
        path.write_text(json.dumps(data), encoding='utf8')
        self.cli('put', file=path)
        self.assertIn('Revision conflict', self.cli('put', code=1, file=path))
        self.assertIn('conflict', self.cli('put', code=1, file=path, expected_revision=2))
        current = json.loads(self.cli('show', id='E'))['node']
        self.assertEqual((current['title'], current['revision']), ('changed title', 2))
        self.assertEqual(current['files'][0]['sha256'], memory.digest(self.project / 'current.txt'))

    def test_ledger_commit_survives_capsule_publication_failure(self):
        self.put(self.node('T', 'task', 'open', files=[]))
        self.focus(['T'], action='old action')
        previous = (self.root / 'CAPSULE.md').read_bytes()
        path = self.project / 'focus.json'
        path.write_text(json.dumps(dict(ids=['T'], next_action='new action')), encoding='utf8')
        argv = ['task_memory.py', 'focus', '--root', str(self.root), '--file', str(path)]
        with patch.object(sys, 'argv', argv), patch.object(memory, 'atomic_text', side_effect=OSError('simulated interruption')):
            with self.assertRaisesRegex(ValueError, 'committed/read.*publication failed'):
                memory.main()
        self.assertEqual((self.root / 'CAPSULE.md').read_bytes(), previous)
        self.assertEqual(json.loads(self.events()[-1][2])['next_action'], 'new action')
        count = len(self.events())
        self.assertIn('new action', self.cli('resume'))
        self.assertEqual(len(self.events()), count)

    def test_failed_ledger_append_does_not_publish_uncommitted_focus(self):
        self.put(self.node('T', 'task', 'open', files=[]))
        self.focus(['T'], action='committed action')
        before, view = self.events(), (self.root / 'CAPSULE.md').read_bytes()
        path = self.project / 'focus.json'
        path.write_text(json.dumps(dict(ids=['T'], next_action='uncommitted action')), encoding='utf8')
        argv = ['task_memory.py', 'focus', '--root', str(self.root), '--file', str(path)]
        with patch.object(sys, 'argv', argv), patch.object(memory, 'append', side_effect=OSError('simulated ledger failure')):
            with self.assertRaises(OSError):
                memory.main()
        self.assertEqual(self.events(), before)
        self.assertEqual((self.root / 'CAPSULE.md').read_bytes(), view)


if __name__ == '__main__':
    unittest.main(verbosity=2)
