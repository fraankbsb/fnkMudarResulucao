"""Atualizacoes do checkout usado pelo aplicativo, sempre sem rebase automatico."""
import os
from pathlib import Path
import subprocess
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]


def run_git(*args, repo_path=None, timeout=25):
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return subprocess.run(['git', '-C', str(repo_path or PROJECT_DIR), *args],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        startupinfo=startupinfo, timeout=timeout)


def get_git_status(repo_path=None, fetch=True):
    try:
        if fetch:
            result = run_git('fetch', 'origin', repo_path=repo_path)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or 'Falha ao consultar o GitHub.')
        branch_result = run_git('branch', '--show-current', repo_path=repo_path)
        branch = branch_result.stdout.strip()
        if branch_result.returncode or not branch:
            raise RuntimeError('Repositorio sem branch ativa.')
        counts = run_git('rev-list', '--left-right', '--count', f'HEAD...origin/{branch}', repo_path=repo_path)
        if counts.returncode:
            raise RuntimeError(counts.stderr.strip())
        ahead, behind = map(int, counts.stdout.split())
        status = run_git('status', '--porcelain', repo_path=repo_path)
        if status.returncode:
            raise RuntimeError(status.stderr.strip())
        return dict(success=True, branch=branch, ahead=ahead, behind=behind,
                    dirty=bool(status.stdout), up_to_date=ahead == behind == 0 and not status.stdout,
                    message=status.stdout.strip())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        return dict(success=False, message=str(error))


def pull_updates(repo_path=None):
    info = get_git_status(repo_path)
    if not info.get('success'):
        return False, info['message']
    if info['dirty']:
        return False, 'Ha alteracoes locais. Salve e envie com sync.bat antes de atualizar.'
    if info['ahead']:
        return False, 'Ha commits locais. Envie com sync.bat antes de atualizar.'
    result = run_git('pull', '--ff-only', 'origin', info['branch'], repo_path=repo_path)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def restart_app():
    os.execl(sys.executable, sys.executable, *sys.argv)
