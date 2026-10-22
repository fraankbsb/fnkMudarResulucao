# fnkMudarResolucao

## Regras permanentes do usuario
- Responder em portugues.
- GitHub e a fonte da verdade: https://github.com/fraankbsb/fnkMudarResulucao, branch `main`.
- Antes de editar, fazer `git fetch origin`, conferir branch, behind/ahead e `git status --short`.
- Integrar atualizacoes remotas sem perder trabalho local. Usar fast-forward quando possivel. Nunca forcar push, fazer reset destrutivo ou descartar alteracoes do usuario.
- Depois de qualquer mudanca neste projeto: executar os testes, fazer commit com mensagem clara em portugues e `git push origin main`, na mesma branch. O trabalho so esta concluido depois do push confirmado.
- A autorizacao de commit e push e permanente para as mudancas pedidas neste projeto; nao pedir novamente a cada atualizacao.
- Incrementar a versao em `VERSION` a cada nova atualizacao publicada (patch por padrao). A tela de entrada mostra esse numero.
- Registrar mudancas relevantes no README e manter o atalho do Desktop abrindo a pasta atual do projeto, sem uma segunda copia desatualizada.
- Nunca incluir senhas, tokens, cookies, ambientes virtuais ou videos pessoais no GitHub. Respeitar `.gitignore`.
- Antes de executar lotes de producao, exigir checkout atualizado e limpo. Testes de desenvolvimento podem rodar durante a edicao para validar o commit.
- Ao concluir, informar: repo/branch, behind/ahead, working tree, acao feita e veredito PODE RODAR ou BLOQUEADO com o motivo.

## Execucao e validacao
- Interface: `python main.py`; Desktop: `launcher.py`, com atalho criado por `setup_desktop.ps1`.
- CLI: `python main.py --cli --help`.
- Testes: `python -m unittest discover -s tests -v` e `git diff --check`.
- Sincronizacao manual: `python sync.py -m "Descricao clara da mudanca"` ou `sync.bat`.
- O launcher mostra a tela de entrada e consulta o GitHub. O botao Atualizar app baixa somente com checkout limpo, sem commits locais, usando `pull --ff-only`. Ele nao commita codigo em andamento. `main.py --app` abre o editor diretamente para testes.
- Priorizar Python padrao e FFmpeg; uma conversao de cada vez. Nao instalar dependencias extras sem necessidade.
