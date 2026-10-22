import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.converter import convert_video

def main():
    parser = argparse.ArgumentParser(
        description='fnkMudarResolucao CLI - Conversor Universal de Proporcao (4:5, 9:16, 1:1, 16:9) preservando o conteudo'
    )
    parser.add_argument('-i', '--input', required=True, help='Caminho do video ou diretorio de entrada')
    parser.add_argument('-o', '--output', help='Caminho do video ou diretorio de saida')
    parser.add_argument('-m', '--mode', choices=['blur', 'pillarbox', 'crop'], default='blur',
                        help='Modo: blur (fundo desfocado inteligente), pillarbox (barras), crop (preenchimento)')
    parser.add_argument('-t', '--target', choices=['4:5', '9:16', '1:1', '16:9', '4:3'], default='4:5',
                        help='Proporcao alvo predefinida (padrao: 4:5)')
    parser.add_argument('--width', type=int, help='Largura personalizada em pixels (sobrescreve --target)')
    parser.add_argument('--height', type=int, help='Altura personalizada em pixels (sobrescreve --target)')
    parser.add_argument('--blur-strength', type=int, default=35, help='Intensidade do desfoque no modo blur (padrao: 35)')
    parser.add_argument('--bg-color', default='black', help='Cor das barras laterais no modo pillarbox (padrao: black)')
    parser.add_argument('--crf', type=int, default=18, help='Qualidade CRF do x264 (0-51, menor = melhor, padrao: 18)')
    parser.add_argument('--preset', default='fast', choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow'],
                        help='Preset de velocidade de compressao (padrao: fast)')

    parser.add_argument('--sharpen-strength', type=float, default=0, help='Nitidez de 0 a 2')
    parser.add_argument('--corte-inicio', type=float, default=0, help='Segundos removidos do inicio')
    parser.add_argument('--corte-fim', type=float, default=0, help='Segundos removidos do fim')
    parser.add_argument('--velocidade', type=float, default=1, help='Velocidade de 0.25 a 4x')
    parser.add_argument('--espelhar', action='store_true', help='Espelhar horizontalmente')
    parser.add_argument('--capa', help='Imagem de capa de abertura')
    parser.add_argument('--capa-segundos', type=float, default=0.1, help='Duracao da capa')
    parser.add_argument('--capa-ajuste', choices=['preencher', 'inteira', 'esticar'], default='preencher')
    args = parser.parse_args()
    if (args.width is None) != (args.height is None):
        parser.error('Informe --width e --height juntos.')
    edits = dict(sharpen_strength=args.sharpen_strength, corte_inicio=args.corte_inicio,
                 corte_fim=args.corte_fim, velocidade=args.velocidade, espelhar=args.espelhar,
                 capa_path=args.capa, capa_segundos=args.capa_segundos, capa_ajuste=args.capa_ajuste)

    # Define a resolução alvo
    if args.width and args.height:
        target_res = (args.width, args.height)
    else:
        target_map = {
            '4:5': (1080, 1350),
            '9:16': (1080, 1920),
            '1:1': (1080, 1080),
            '16:9': (1920, 1080),
            '4:3': (1440, 1080)
        }
        target_res = target_map.get(args.target, (1080, 1350))

    input_path = os.path.abspath(args.input)
    if os.path.isdir(input_path):
        files = []
        for ext in ('*.mp4', '*.mov', '*.mkv', '*.webm'):
            files.extend(glob.glob(os.path.join(input_path, ext)))
        if not files:
            print(f'[AVISO] Nenhum video compativel encontrado em: {input_path}')
            return
        out_dir = os.path.abspath(args.output) if args.output else os.path.join(input_path, f'convertidos_{target_res[0]}x{target_res[1]}')
        os.makedirs(out_dir, exist_ok=True)
        print(f'[LOTE] Processando {len(files)} video(s) para {target_res[0]}x{target_res[1]}...')
        failures = 0
        for idx, f in enumerate(files, 1):
            name, ext = os.path.splitext(os.path.basename(f))
            dest = os.path.join(out_dir, f'{name}_{target_res[0]}x{target_res[1]}.mp4')
            print(f'\n[{idx}/{len(files)}] Convertendo: {os.path.basename(f)} -> {os.path.basename(dest)}')
            try:
                def progress(p, text):
                    bar_len = 30
                    filled = int(bar_len * p)
                    bar = '=' * filled + '-' * (bar_len - filled)
                    print(f'\rProgresso: [{bar}] {text}', end='', flush=True)
                convert_video(
                    input_path=f,
                    output_path=dest,
                    mode=args.mode,
                    target_resolution=target_res,
                    blur_strength=args.blur_strength,
                    bg_color=args.bg_color,
                    crf=args.crf,
                    preset=args.preset,
                    progress_callback=progress,
                    **edits
                )
                print('\n[CONCLUIDO COM SUCESSO]')
            except Exception as e:
                failures += 1
                print(f'\n[ERRO]: {e}')
        if failures:
            sys.exit(1)
    else:
        if not os.path.isfile(input_path):
            print(f'[ERRO] Arquivo de entrada nao encontrado: {input_path}')
            sys.exit(1)
        if args.output:
            out_file = os.path.abspath(args.output)
        else:
            base, ext = os.path.splitext(input_path)
            out_file = f'{base}_{target_res[0]}x{target_res[1]}.mp4'

        print(f'[INICIO] Processando video: {input_path}')
        print(f'         Modo: {args.mode} | Resolucao alvo: {target_res[0]}x{target_res[1]} ({args.target})')
        print(f'         Saida: {out_file}')

        def progress(p, text):
            bar_len = 35
            filled = int(bar_len * p)
            bar = '=' * filled + '-' * (bar_len - filled)
            print(f'\rProgresso: [{bar}] {text}', end='', flush=True)

        start = time.time()
        try:
            convert_video(
                input_path=input_path,
                output_path=out_file,
                mode=args.mode,
                target_resolution=target_res,
                blur_strength=args.blur_strength,
                bg_color=args.bg_color,
                crf=args.crf,
                preset=args.preset,
                progress_callback=progress,
                **edits
            )
            elapsed = time.time() - start
            print(f'\n[CONCLUIDO] Video gerado em {elapsed:.2f} segundos: {out_file}')
        except Exception as e:
            print(f'\n[ERRO AO CONVERTER]: {e}')
            sys.exit(1)

if __name__ == '__main__':
    main()
