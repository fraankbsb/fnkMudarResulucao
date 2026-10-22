# Recria o atalho para esta pasta do projeto, sem compilar outra copia.
$ErrorActionPreference = 'Stop'
$taskProject = $PSScriptRoot
$taskPython = (Get-Command python.exe -ErrorAction Stop).Source
$taskPythonw = Join-Path (Split-Path -Parent $taskPython) 'pythonw.exe'
if (Test-Path -LiteralPath $taskPythonw) { $taskPython = $taskPythonw }
$taskDesktop = [Environment]::GetFolderPath('Desktop')
$taskShell = New-Object -ComObject WScript.Shell
$taskLinkPath = Join-Path $taskDesktop 'fnkMudarResolucao.lnk'
$taskLink = $taskShell.CreateShortcut($taskLinkPath)
$taskLink.TargetPath = $taskPython
$taskLink.Arguments = '"' + (Join-Path $taskProject 'launcher.py') + '"'
$taskLink.WorkingDirectory = $taskProject
$taskLink.IconLocation = (Join-Path $taskProject 'assets\app_icon.ico') + ',0'
$taskLink.Description = 'fnkMudarResolucao - versao desta pasta, sincronizada com o GitHub'
$taskLink.WindowStyle = 7
$taskLink.Save()
Write-Output "Atalho criado: $taskLinkPath"
