import os
import subprocess
import sys

def get_git_status():
    try:
        cmd_fetch = ['git', 'fetch', 'origin']
        subprocess.run(cmd_fetch, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        
        cmd_status = ['git', 'status', '-uno']
        res = subprocess.run(cmd_status, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        output = res.stdout
        
        behind = 'behind' in output
        ahead = 'ahead' in output
        up_to_date = 'up to date' in output or 'Your branch is up to date' in output
        
        return {
            'success': True,
            'behind': behind,
            'ahead': ahead,
            'up_to_date': up_to_date,
            'message': output
        }
    except Exception as e:
        return {'success': False, 'message': str(e)}

def pull_updates():
    try:
        cmd = ['git', 'pull', '--rebase', 'origin', 'main']
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        if res.returncode != 0:
            # Tenta sem branch especifica caso esteja em master
            cmd = ['git', 'pull', 'origin']
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        
        return res.returncode == 0, res.stdout or res.stderr
    except Exception as e:
        return False, str(e)

def restart_app():
    python = sys.executable
    os.execl(python, python, *sys.argv)