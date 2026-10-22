# fnkMudarResolucao - Conversor 9:16 para 4:5

Aplicacao completa de alto desempenho para conversao de videos verticais (9:16, formato Reels/Stories/TikTok) para o formato vertical padrao de feed do Instagram e Facebook (4:5, 1080x1350), mantendo a originalidade do conteudo sem distorcer proporcoes ou achatar elementos visuais.

---

## Modos de Preservacao da Originalidade

1. **Fundo Desfocado Dinamico (lur - Recomendado):**
   - O video original 9:16 e mantido em escala 100% no centro, sem nenhum corte.
   - O espaco lateral restante do quadro 4:5 e preenchido com o proprio video ampliado, desfocado suavemente com boxblur e leve ajuste de contraste. Padrao utilizado pelas maiores agencias e criadores para feed do Instagram.

2. **Barras Laterais Solidas (pillarbox):**
   - Mantem o video 100% original no centro com bordas laterais limpas (preto solido, branco ou customizado).

3. **Preenchimento Total (crop):**
   - Centraliza o video e realiza o recorte suave do topo e base para ocupar integralmente a tela 4:5 sem bordas laterais.

---

## Estrutura do Projeto

- core/converter.py: Motor de processamento via FFmpeg com extracao de metadados via FFprobe, codificacao x264 de alta fidelidade visual (CRF ajustavel) e streaming de progresso em tempo real.
- core/preview.py: Gerador de miniaturas instantaneas para pre-visualizacao do resultado antes de converter.
- gui/app.py: Interface grafica moderna desktop (CustomTkinter) com suporte a fila de arquivos, pre-visualizacao ao vivo, controle de desfoque, cores e barra de progresso.
- cli/main.py: Utilitario completo de linha de comando para conversao de arquivos individuais ou pastas inteiras em lote.
- main.py: Ponto de entrada unificado da aplicacao.
- 	ests/: Suite de testes automatizados com geracao de video sintetico.

---

## Como Usar

### 1. Interface Grafica (Modo Visual)

Execute no terminal:

`ash
python main.py
`

Recursos da interface:
- Selecao de multiplos videos com lista de fila;
- Alternancia de modos (Fundo Desfocado, Barras Solidas, Corte Total);
- Slider de intensidade do desfoque (10 a 80);
- Seletor de resolucao alvo (1080x1350 Instagram HD, 864x1080, 1440x1800 2K);
- Pre-visualizacao 4:5 em tempo real do frame selecionado;
- Barra de progresso com porcentagem e botao de cancelamento seguro;
- Botao direto para abrir a pasta de saida.

---

### 2. Linha de Comando (CLI para automacao ou lote)

Converter um video com fundo desfocado:

`ash
python main.py --cli -i seu_video.mp4 -o video_convertido.mp4 -m blur
`

Processar uma pasta inteira de videos em lote:

`ash
python main.py --cli -i C:\meus_videos -m blur --blur-strength 40
`

Parametros disponiveis na CLI:
- -i, --input: Arquivo ou diretorio de entrada (obrigatorio).
- -o, --output: Arquivo ou diretorio de destino (opcional).
- -m, --mode: Modo de composicao (lur, pillarbox, crop).
- --width: Largura em pixels (padrao: 1080).
- --height: Altura em pixels (padrao: 1350).
- --blur-strength: Intensidade do desfoque no modo blur (padrao: 35).
- --bg-color: Cor das barras no modo pillarbox (padrao: black).
- --crf: Fator de qualidade do codec (padrao: 18, qualidade visual sem perdas perceptíveis).
- --preset: Velocidade de processamento do FFmpeg (padrao: fast).

---

## Dependencias Instaladas

- Python 3.11+
- FFmpeg e FFprobe no PATH do sistema
- customtkinter
- Pillow