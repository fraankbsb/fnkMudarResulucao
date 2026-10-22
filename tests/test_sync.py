import subprocess
import tempfile
import unittest
from pathlib import Path

from core.updater import get_git_status, pull_updates
from launcher import sync_repository
from sync import synchronize


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fnk sync acentos_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / 'remote.git'
        self.work = self.root / 'projeto local'
        self.git(self.root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.git(self.root, 'clone', str(self.remote), str(self.work))
        self.identify(self.work)
        (self.work / 'README.md').write_text('initial\n', encoding='utf-8')
        self.git(self.work, 'add', '.')
        self.git(self.work, 'commit', '-m', 'Inicial')
        self.git(self.work, 'push', '-u', 'origin', 'main')

    @staticmethod
    def git(repo, *args):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', check=True)
        return result.stdout.strip()

    def identify(self, repo):
        self.git(repo, 'config', 'user.name', 'Teste local')
        self.git(repo, 'config', 'user.email', 'teste@example.invalid')

    def advance_remote(self):
        other = self.root / 'outra copia'
        self.git(self.root, 'clone', str(self.remote), str(other))
        self.identify(other)
        (other / 'remote.txt').write_text('atualizacao remota', encoding='utf-8')
        self.git(other, 'add', '.')
        self.git(other, 'commit', '-m', 'Atualizacao remota')
        self.git(other, 'push', 'origin', 'main')

    def test_manual_edits_are_committed_and_pushed(self):
        (self.work / 'README.md').write_text('alterado localmente\n', encoding='utf-8')
        info = synchronize(self.work, run_tests=False)
        self.assertEqual((info['ahead'], info['behind'], info['dirty']), (0, 0, False))
        self.assertIn('Salvamento do projeto', self.git(self.work, 'log', '-1', '--format=%s'))
        self.assertEqual(self.git(self.work, 'rev-parse', 'HEAD'),
                         self.git(self.remote, 'rev-parse', 'main'))

    def test_clean_checkout_updates_by_fast_forward(self):
        self.advance_remote()
        self.assertEqual(get_git_status(self.work)['behind'], 1)
        ok, message = pull_updates(self.work)
        self.assertTrue(ok, message)
        self.assertTrue((self.work / 'remote.txt').exists())
        self.assertTrue(get_git_status(self.work)['up_to_date'])

    def test_remote_changes_do_not_overwrite_local_work(self):
        self.advance_remote()
        path = self.work / 'README.md'
        path.write_text('trabalho em andamento', encoding='utf-8')
        head = self.git(self.work, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(RuntimeError, 'Integre'):
            synchronize(self.work, run_tests=False)
        ok, _ = pull_updates(self.work)
        self.assertFalse(ok)
        self.assertEqual(head, self.git(self.work, 'rev-parse', 'HEAD'))
        self.assertEqual(path.read_text(encoding='utf-8'), 'trabalho em andamento')

    def test_launcher_preserves_uncommitted_edits(self):
        (self.work / 'README.md').write_text('edicao nao concluida', encoding='utf-8')
        head = self.git(self.work, 'rev-parse', 'HEAD')
        ok, _ = sync_repository(self.work)
        self.assertFalse(ok)
        self.assertEqual(head, self.git(self.work, 'rev-parse', 'HEAD'))
        self.assertTrue(get_git_status(self.work)['dirty'])

    def test_network_failure_is_reported(self):
        self.git(self.work, 'remote', 'set-url', 'origin', str(self.root / 'missing.git'))
        info = get_git_status(self.work)
        self.assertFalse(info['success'])
        self.assertTrue(info['message'])

    def test_credentials_prevent_commit_and_push(self):
        head = self.git(self.work, 'rev-parse', 'HEAD')
        (self.work / 'credential.txt').write_text('ghp_' + 'a' * 30, encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'credencial'):
            synchronize(self.work, message='Nao enviar', run_tests=False)
        self.assertEqual(head, self.git(self.work, 'rev-parse', 'HEAD'))
        self.assertEqual(head, self.git(self.remote, 'rev-parse', 'main'))
