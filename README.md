# fnkMudarResolucao - Conversor Universal de Proporcao e Resolucao

Aplicacao profissional de alto desempenho para conversao bidirecional e adaptacao de videos entre qualquer proporcao do mercado sem esticar, achatar ou cortar o conteudo essencial:

- **9:16 para 4:5** (Stories/Reels/TikTok -> Feed Instagram HD 1080x1350)
- **4:5 para 9:16** (Feed Instagram -> Stories/Reels Vertical Completo 1080x1920)
- **1:1 para 9:16 ou 4:5** (Quadrado para formatos verticais)
- **9:16 para 1:1** (Vertical para feed quadrado 1080x1080)
- **16:9 para 9:16 ou 4:5** (Horizontal para vertical e vice-versa)

---

## Modos de Preservacao da Originalidade

1. **Fundo Desfocado Dinamico (`blur` - Padrao Recomendado):**
   - O video original permanece em escala 100% no centro, integro e sem cortes.
   - O espaco excedente da nova proporcao (seja vertical ou lateral) e preenchido dinamicamente com o proprio video ampliado e suavizado com desfoque e ajuste de contraste, gerando a estetica oficial utilizada nas redes sociais.

2. **Barras Solidas (`pillarbox` / `letterbox`):**
   - Mantem o video original no centro com molduras limpas (preto, branco, cinza ou customizado).

3. **Preenchimento Total (`crop`):**
   - Centraliza o video e realiza o enquadramento preenchendo 100% da tela sem barras.

---

## Recursos e Integracoes

- **Sincronizacao Git Bidirecional:** Botao "Sincronizar GitHub" no topo da interface: executa os testes, salva alteracoes em commit e envia para a mesma branch. Baixa atualizacoes com fast-forward quando nao ha trabalho local pendente.
- **Launcher Integrado:** Atalho oficial na Area de Trabalho abre a tela de entrada, consulta o GitHub e oferece a atualizacao antes de iniciar o editor.
- **Pre-Visualizacao em Tempo Real:** Exibicao dinamica na interface grafica do resultado adaptado proporcionalmente a cada formato selecionado antes de renderizar.
- **Edicao integrada:** Remocao de segundos do inicio e do fim, velocidade de 0.25x a 4x, espelhamento horizontal e nitidez de 0 a 2.
- **Detector de Cor de Fundo / Template Inteligente (Metodo Fusex):** Identificacao automatica da cor de fundo de cada video (analisando bordas laterais, card de frases superior e rodape). Se o video possui template/card branco, aplica molduras brancas (#ffffff); se possui template preto, aplica molduras pretas (#000000), garantindo fusao estetica perfeita com cada video individual no lote.
- **Selecao em Lote por Arquivos ou Pasta Inteira:** Permite adicionar multiplos videos de uma so vez ou carregar uma pasta inteira com um clique (varredura recursiva de arquivos compativeis .mp4, .mov, .mkv, .webm, .avi, .m4v), alimentando a fila de processamento instantaneamente.
- **Processamento em Lote Blindado:** Execucao resiliente com nomes temporarios isolados sem locks de sistema no Windows, suporte a faixas amplas de velocidade (0.05x a 10x) e tolerancia inteligente a variacoes de duracao entre os arquivos da fila sem interromper o lote.
- **Capa de abertura com Higienizacao Forense:** Conversao e enquadramento automatico para 1080x1920 (9:16) perfeitamente encaixada ao selecionar imagem, com duracao configuravel, nos modos preencher, inteira (com barras) ou esticar. Realiza limpeza forense profunda eliminando metadados EXIF, GPS, camera, software de edicao e carimbos de tempo, tornando a imagem 100% esterilizada. O tempo e ajustado ao quadro mais proximo, com no minimo um quadro. A capa fica silenciosa e o audio acompanha o inicio do corpo do video.
- **Previa maior com som:** Clique no video ou use a tecla Espaco para Play/Pause. O icone central e pequeno, sem fundo, e desaparece apos 600 ms sem movimento do mouse, inclusive quando pausado. O botao **Ampliar previa** ocupa o painel da janela; Escape ou **Restaurar painel** retorna aos controles. O audio toca por padrao; **Sem som** silencia a previa. O video e sincronizado pelo relogio do dispositivo de som. A saida usa o Windows, sem dependencias novas, com ate 200 ms de audio em buffer. A decodificacao do video continua ate 30 fps, no maximo 960x720 e fila de seis quadros; cortes, velocidade e silencio da capa valem tambem para o audio.
- **Enquadramento por resolucao:** A previa preserva exatamente a proporcao escolhida (4:5, 9:16, 1:1, 16:9 ou 4:3), adapta-se ao espaco da janela e identifica as dimensoes reais da saida. Trocar ajustes ou proporcao substitui a previa anterior.
- **Percentuais visiveis:** Desfoque de 0 a 100% corresponde a 0 a 80; nitidez de 0 a 100% corresponde a 0 a 2; velocidade 100% e normal. O CRF mostra o valor numerico e sua posicao percentual na escala (100% corresponde a CRF 0; 0% a CRF 51). Esse percentual e uma referencia do controle, nao uma medida de qualidade do arquivo. A linha de tempo tambem mostra o percentual reproduzido.
- **Limpeza de metadados:** Secao propria, ativada por padrao na conversao. Remove titulo, autor, comentarios, datas, localizacao e capitulos, mantendo dados tecnicos de reproducao e orientacao. O botao **Limpar metadados da fila (sem converter)** cria copias com sufixo `_metadados_limpos` mantendo a extensao, a resolucao e os fluxos de video/audio sem recodificar. O original e preservado.
- **Configuracoes salvas:** Aplique os tres presets incluidos ou salve e importe configuracoes em JSON. Caminhos de capas sao locais ao computador.
- **Audio:** Copia direta sem perdas quando nao ha cortes, capa ou mudanca de velocidade e o perfil para celular esta desligado. Com essas edicoes, o audio e sincronizado e recodificado em AAC a 192 kb/s. Videos sem audio tambem sao aceitos.
- **Saida MP4:** A interface gera H.264 em MP4 e acrescenta um numero quando o nome de destino ja existe. Cancelamentos e falhas descartam o arquivo temporario e preservam uma saida preexistente.

---

## Como Usar

### Instalacao

Requer Python 3.10 ou superior e `ffmpeg` / `ffprobe` disponiveis no PATH.

```powershell
python -m pip install -r requirements.txt
```

### 1. Interface Grafica (Desktop)

Basta abrir pelo atalho **fnkMudarResolucao** na Area de Trabalho ou executar no terminal:

```bash
python main.py
```

1. Selecione os videos desejados.
2. Escolha a proporcao de destino (ex: `4:5 Feed Instagram`, `9:16 Stories/Reels`, `1:1 Quadrado`).
3. Escolha o modo de composicao (recomendado: `Fundo Desfocado Dinamico`).
4. Em **Edicao do Video**, informe os segundos a remover do inicio e do fim, a velocidade, o espelhamento e a nitidez. Os ajustes se aplicam a todos os videos da fila; os cortes precisam deixar algum trecho em cada video.
5. Se desejar, escolha uma imagem de capa e ajuste sua duracao e seu enquadramento. A capa e adicionada antes do trecho editado e nao recebe espelhamento ou nitidez.
6. Confira o resultado na previa a direita e clique em **INICIAR CONVERSAO DE PROPORCAO**. Ajustes alterados durante uma conversao valem para a proxima execucao.

---

### 2. Linha de Comando (CLI para automacao ou lote)

Converter de 9:16 para 4:5:
```bash
python main.py --cli -i "video_origem.mp4" -t 4:5 -m blur
```

Converter de 4:5 para 9:16:
```bash
python main.py --cli -i "video_feed.mp4" -t 9:16 -m blur
```

Converter uma pasta inteira de videos em lote para 9:16:
```bash
python main.py --cli -i "C:\pasta_de_videos" -t 9:16 -m blur
```


Converter com edicao e capa:

```powershell
python main.py --cli -i "video.mp4" -o "resultado.mp4" -t 4:5 --corte-inicio 1 --corte-fim 0.5 --velocidade 1.25 --espelhar --sharpen-strength 0.8 --capa "capa.jpg" --capa-segundos 0.25 --capa-ajuste preencher
```

A CLI gera MP4 por padrao e tambem aceita saida explicita `.mov` ou `.mkv`.
Um caminho de saida informado com `-o` e substituido somente apos a conversao terminar com sucesso.

### Verificacao

Os testes geram videos sinteticos em uma pasta temporaria e verificam resolucao, audio, duracao, capa, espelhamento, previa, cancelamento e preservacao de arquivos existentes:

```powershell
python -m unittest discover -s tests -v
```


### Desktop e GitHub

Este checkout e a mesma versao usada pelo atalho do Desktop. Para criar ou corrigir o atalho nesta maquina ou em outra pasta clonada:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_desktop.ps1
```

O atalho abre `launcher.py`: uma tela de entrada com a versao de `VERSION`, consulta ao GitHub e os botoes **Entrar na ferramenta** e **Atualizar app**. O segundo baixa atualizacoes apenas com a pasta limpa e sem commits locais pendentes. Sem internet, a tela permite entrar na versao local. A atualizacao da entrada apenas baixa codigo; o botao **Sincronizar GitHub** dentro do editor continua sendo o fluxo de desenvolvimento que testa, commita e envia. `python main.py` tambem abre a entrada; `python main.py --app` abre diretamente o editor.

O repositorio e [fraankbsb/fnkMudarResulucao](https://github.com/fraankbsb/fnkMudarResulucao), branch `main` (a grafia do repositorio e essa).
As regras em `AGENTS.md` e `CLAUDE.md` determinam que as alteracoes feitas pelos agentes sejam testadas, commitadas e enviadas ao GitHub antes de concluir cada pedido.
Para edicoes manuais, use o botao **Sincronizar GitHub**, abra `sync.bat`, ou execute:

```powershell
python sync.py -m "Descricao da alteracao"
```

O sincronizador testa antes de commitar e enviar. Se houver alteracoes locais e mudancas novas no GitHub, ele para para permitir integracao sem descartar trabalho. Nao existe vigilancia continua de cada salvamento do editor; a sincronizacao acontece ao concluir o trabalho do agente ou ao acionar esse comando/botao.


Para usar tambem no computador de mesa, com Git, Python e FFmpeg instalados:

```powershell
git clone https://github.com/fraankbsb/fnkMudarResulucao.git
cd fnkMudarResulucao
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\setup_desktop.ps1
```

O caminho de instalacao pode ser diferente em cada computador. O atalho e criado no Desktop do usuario atual e aponta para a pasta clonada naquela maquina. Para receber atualizacoes, abra novamente pelo atalho e clique em **Atualizar app**; para desenvolver nos dois PCs, sincronize antes de trocar de computador.


### Limpar metadados pela CLI

Limpar sem alterar resolucao, enquadramento ou compressao:

```powershell
python main.py --cli -i "video.mp4" --somente-limpar-metadados
```

Tambem aceita uma pasta inteira. Na conversao normal, a limpeza ja vem ativada; para preservar os metadados de origem, use `--manter-metadados` ou desmarque a opcao na interface.

A previa usa uma versao reduzida dos mesmos filtros de enquadramento da exportacao; o desfoque acompanha proporcionalmente a escala da previa. A exportacao conserva a resolucao selecionada. Os testes cobrem as cinco proporcoes, a reproducao continua, pausa/retomada, fila limitada, capas, cortes, espelho, limpeza de campos pessoais e preservacao dos fluxos na limpeza sem recodificacao.


### Padrao de limpeza e identidade por video

A limpeza segue o comportamento descrito no [Metadata2Go](https://www.metadata2go.com/pt/excluir-metadados): remover dados pessoais e de aparelho preservando o conteudo audiovisual. A implementacao e local e independente; nao acessa o site durante o processamento. Detalhes da referencia e da verificacao estao em [docs/metadata-cleaning.md](docs/metadata-cleaning.md).

Na interface, **Gerar identificador unico por video** vem ativado: grava um UUID v4 novo em `content_identifier` a cada arquivo produzido. O formato para celular tambem vem ativado na conversao: MP4, H.264/yuv420p, audio AAC e inicio rapido. Isso nao inventa modelo, fabricante, serial, GPS ou data de captura e nao comprova uma origem em celular. Limpar sem converter preserva os codecs e a resolucao do original, acrescentando apenas o UUID quando selecionado.

Na CLI, essas duas opcoes sao explicitas:

```powershell
python main.py --cli -i "video.mp4" --perfil-celular --identidade-unica
python main.py --cli -i "video.mp4" --somente-limpar-metadados --identidade-unica
```
