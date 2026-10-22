"""Testar, salvar e enviar o projeto para a mesma branch do GitHub."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import re
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from core.updater import PROJECT_DIR, get_git_status, run_git


def checked(*args, repo_path):
    result = run_git(*args, repo_path=repo_path, timeout=120)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def synchronize(repo_path=PROJECT_DIR, message=None, run_tests=True):
    repo_path = Path(repo_path).resolve()
    info = get_git_status(repo_path)
    if not info.get('success'):
        raise RuntimeError(info['message'])
    branch = info['branch']
    if info['behind']:
        if info['dirty'] or info['ahead']:
            raise RuntimeError('O GitHub tem mudancas novas e ha trabalho local. Integre as alteracoes antes de sincronizar.')
        checked('pull', '--ff-only', 'origin', branch, repo_path=repo_path)
    if run_tests:
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=repo_path)
        if result.returncode:
            raise RuntimeError('Testes falharam; nada foi commitado ou enviado.')
    checked('diff', '--check', repo_path=repo_path)
    checked('add', '-A', repo_path=repo_path)
    staged = checked('diff', '--cached', '--name-only', repo_path=repo_path)
    if staged:
        forbidden = re.compile(r'(^|/)(\.env($|\.(?!example$))|cookies?/|sessions?/|update_token\.txt$)|\.(pem|key|pfx)$', re.I)
        secret = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
        for name in staged.splitlines():
            if forbidden.search(name):
                raise RuntimeError(f'Arquivo sensivel no staging: {name}. Nada enviado.')
        additions = checked('diff', '--cached', '-U0', '--diff-filter=ACM', repo_path=repo_path)
        if secret.search('\n'.join(line for line in additions.splitlines() if line.startswith('+'))):
            raise RuntimeError('Possivel credencial nas alteracoes. Nada commitado ou enviado.')
        if not message:
            try:
                zone = ZoneInfo('America/Sao_Paulo')
            except ZoneInfoNotFoundError:
                zone = timezone(timedelta(hours=-3))
            timestamp = datetime.now(zone).strftime('%Y-%m-%d %H:%M')
            message = f'Salvamento do projeto (sincronizacao desktop) - {timestamp}'
        checked('commit', '-m', message, repo_path=repo_path)
    checked('push', 'origin', branch, repo_path=repo_path)
    final = get_git_status(repo_path)
    if not final.get('success') or final['ahead'] or final['behind'] or final['dirty']:
        raise RuntimeError('O repositorio mudou durante a sincronizacao; confira git status.')
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-m', '--message', help='Mensagem clara para o commit')
    args = parser.parse_args()
    try:
        info = synchronize(message=args.message)
        print(f"origin/{info['branch']} | behind 0 / ahead 0 | working tree limpa | PODE RODAR")
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'BLOQUEADO: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
