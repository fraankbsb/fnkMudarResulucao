# Limpeza local: referencia Metadata2Go

Referencia consultada em 22/10/2026: https://www.metadata2go.com/pt/excluir-metadados

O pedido e implementar o padrao no aplicativo, sem API ou envio de videos pessoais.
A pagina descreve retirar dados EXIF/GPS/autor, dispositivo, codificador e datas,
preservando imagem e som. Nem todo campo oculto de todo formato pode ser detectado.

## Analise pratica

Foi gerado um MP4 sintetico de um segundo, cor azul e audio silencioso, contendo
titulo, autor, comentario, data de criacao, GPS de teste, fabricante e modelo ficticios.
Esse arquivo de teste foi enviado ao site e o trabalho concluiu, oferecendo um MP4
para download (5,7 KB). O corpo desse download nao ficou disponivel para analise
local na sessao do navegador; nao se afirma igualdade byte a byte com o algoritmo
interno do servico, que nao foi obtido ou copiado.

A implementacao independente usa FFmpeg: desativa copia de metadados globais e dos
fluxos, remove capitulos/timecode e campos de software do conteiner. A limpeza
isolada copia os fluxos de video e audio sem recodificacao. Os testes validam que
os marcadores pessoais/de aparelho desapareceram e os hashes dos pacotes de video
e audio permaneceram iguais. Dados tecnicos necessarios a reproducao e orientacao
permanecem. Isso cobre os formatos de video aceitos pelo aplicativo, nao as funcoes
de PDF, imagens ou documentos oferecidas pelo site.

## Identidade unica e formato para celular

O UUID v4 em `content_identifier` e uma identidade desta copia de saida. Duas
execucoes geram UUIDs diferentes, inclusive ao limpar o mesmo original. O UUID
nao e um numero de serie de aparelho, nem uma promessa de conteudo visual diferente.
O perfil para celular produz MP4/H.264/yuv420p/AAC com faststart e marca tecnica mp42.
Nao sao inventados fabricante, modelo, data de captura, localizacao ou serial.
Os testes verificam o UUID, os codecs, a limpeza e o perfil do conteiner.
