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

- **Sincronizacao Git Bidirecional:** Botao "Atualizar App (Git Sync)" no topo da interface que verifica em segundo plano atualizacoes no GitHub e reinicia a aplicacao atualizada com um clique.
- **Launcher Integrado:** Atalho oficial na Area de Trabalho que realiza sync automatico antes de abrir a aplicacao.
- **Pre-Visualizacao em Tempo Real:** Exibicao dinamica na interface grafica do resultado adaptado proporcionalmente a cada formato selecionado antes de renderizar.
- **Preservacao de Audio Sem Perdas:** Utiliza copia direta de audio (`-c:a copy`) para velocidade maxima e integridade acustica.

---

## Como Usar

### 1. Interface Grafica (Desktop)

Basta abrir pelo atalho **fnkMudarResolucao** na Area de Trabalho ou executar no terminal:

```bash
python main.py
```

1. Selecione os videos desejados.
2. Escolha a proporcao de destino (ex: `4:5 Feed Instagram`, `9:16 Stories/Reels`, `1:1 Quadrado`).
3. Escolha o modo de composicao (recomendado: `Fundo Desfocado Dinamico`).
4. Veja o resultado no preview a direita e clique em **INICIAR CONVERSAO DE PROPORCAO**.

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
