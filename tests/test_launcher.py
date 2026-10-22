import os
import subprocess
import sys
import unittest


@unittest.skipUnless(os.name=='nt' or os.environ.get('DISPLAY'),'Janela requer ambiente grafico')
class LauncherTests(unittest.TestCase):
    def test_entry_window_version_offline_update_and_open(self):
        # Interpretador separado evita compartilhar o ciclo de vida do Tk do editor.
        code = """
import time
from unittest.mock import patch
from launcher import LauncherWindow
from core.updater import local_version
with patch('launcher.get_git_status',return_value={'success':True,'behind':1,'ahead':0,'dirty':False}), patch('launcher.pull_updates',return_value=(True,'Atualizado')) as update:
    app=LauncherWindow()
    app.withdraw()
    deadline=time.monotonic()+5
    while app.info is None and time.monotonic()<deadline:
        app.update();time.sleep(0.01)
    assert app.info is not None
    assert local_version() in app.version_label.cget('text')
    assert app.btn_update.cget('text')=='Baixar atualizacao'
    app._show_status({'success':False})
    assert app.btn_enter.cget('state')=='normal'
    assert 'versao local' in app.status.cget('text')
    app._show_status({'success':True,'behind':1,'dirty':True})
    assert app.btn_update.cget('state')=='disabled'
    app._show_status({'success':True,'behind':1,'ahead':0,'dirty':False})
    app.btn_update.invoke()
    assert app.btn_enter.cget('state')=='disabled'
    deadline=time.monotonic()+5
    while app.btn_enter.cget('state')=='disabled' and time.monotonic()<deadline:
        app.update();time.sleep(0.01)
    assert update.called
    assert 'concluida' in app.status.cget('text')
    with patch('launcher.subprocess.Popen') as launch:
        app.btn_enter.invoke()
        assert launch.call_args.args[0][-1]=='--app'
"""
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
