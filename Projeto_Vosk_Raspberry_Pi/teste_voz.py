#!/usr/bin/env python3
"""Roberta: Enter inicia e conclui a fala; captura máxima de 15 segundos.

Dependências: vosk, sounddevice e numpy. FFmpeg só é necessário em --arquivo.
Coloque este script ao lado de vosk-model-small-pt-0.3.

    python3 roberta_otimizada.py
    python3 roberta_otimizada.py --duracao 15
    python3 roberta_otimizada.py --canal 2 --uma-vez
    python3 roberta_otimizada.py --arquivo gravacoes/1/audio.wav

Enter inicia uma fala. Durante a captura, outro Enter conclui a fala antes do limite.
A captura termina automaticamente em 15 segundos, mesmo em silêncio ou com ruído.
Entre as falas, digite 'sair' para encerrar. Ctrl+C também sai.
--continuo inicia capturas sem o Enter inicial.
A redução da espera depende da velocidade do reconhecimento na placa.
"""

import argparse
import json
import math
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import wave
from array import array
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

# As dependências são carregadas em main(), para --help funcionar sem instalá-las.
np = None
KaldiRecognizer = None

DURACAO = 15
TAXA_VOSK = 16000
PROJETO = Path(__file__).resolve().parent
MODELO = PROJETO / "vosk-model-small-pt-0.3"
GRAVACOES = PROJETO / "gravacoes"

# Cadastre as frases abaixo em minúsculas e sem acentos.
PERGUNTAS_HORA = {
    "que horas sao",
    "que horas sao agora",
    "que hora e",
    "que hora e agora",
    "que horas e",
    "qual e a hora",
    "qual a hora",
    "qual e o horario",
    "qual o horario",
    "qual o horario atual",
    "me fale a hora",
    "me fale a horas",
    "me fale as horas",
    "me fala a hora",
    "me fala a horas",
    "me fala as horas",
    "me diga a hora",
    "me diga as horas",
    "me diga que horas sao",
    "me diz a hora",
    "me diz as horas",
    "diga a hora",
    "diga as horas",
    "voce sabe que horas sao",
    "pode me dizer as horas",
    "pode me dizer que horas sao",
}

PERGUNTAS_DATA = {
    "que dia e hoje",
    "que dia e hoje mesmo",
    "qual e a data de hoje",
    "qual a data de hoje",
    "qual a data",
    "qual e a data",
    "me diga a data",
    "me fale a data",
    "hoje e que dia",
}

RESPOSTAS_FIXAS = {
    "ola": "Olá!",
    "oi": "Oi!",
    "tudo bem": "Olá, eu estou bem.",
    "como voce esta": "Olá, eu estou bem.",
    "como vai": "Olá, eu estou bem.",
    "bom dia": "Bom dia!",
    "boa tarde": "Boa tarde!",
    "boa noite": "Boa noite!",
    "qual e o seu nome": "Eu sou a Roberta.",
    "qual e seu nome": "Eu sou a Roberta.",
    "qual seu nome": "Eu sou a Roberta.",
    "como voce se chama": "Eu sou a Roberta.",
    "voce e a alexa": "Sou a Roberta. Meu escritório é um Raspberry Pi.",
    "voce e alexa": "Sou a Roberta. Meu escritório é um Raspberry Pi.",
    "conte uma piada": "Por que o computador foi ao médico? Porque pegou um vírus.",
    "me conte uma piada": "Por que o computador foi ao médico? Porque pegou um vírus.",
    "me conta uma piada": "Por que o computador foi ao médico? Porque pegou um vírus.",
    "obrigado": "De nada!",
    "obrigada": "De nada!",
    "tchau": "Até mais!",
}


def normalizar_comando(texto):
    decomposto = unicodedata.normalize("NFD", texto.casefold())
    sem_acentos = "".join(
        caractere for caractere in decomposto if not unicodedata.combining(caractere)
    )
    palavras = re.findall(r"[a-z0-9]+", sem_acentos)
    frase = " ".join(palavra for palavra in palavras if palavra != "roberta")
    frase = re.sub(r"^por favor | por favor$", "", frase)
    return re.sub(r"^(oi|ola) ", "", frase)


def responder(texto):
    comando = normalizar_comando(texto)

    if comando in PERGUNTAS_HORA:
        return f"Agora são {datetime.now():%H:%M}."

    if comando in PERGUNTAS_DATA:
        return f"Hoje é {datetime.now():%d/%m/%Y}."

    return RESPOSTAS_FIXAS.get(comando)


def energia_do_canal(amostras):
    """Variância em ponto flutuante: remove DC sem estourar o inteiro de 16 bits."""
    dados = np.asarray(amostras, dtype=np.float32)
    return float(dados.var()) if dados.size else 0.0


def criar_pasta():
    GRAVACOES.mkdir(parents=True, exist_ok=True)
    numeros = (int(p.name) for p in GRAVACOES.iterdir() if p.is_dir() and p.name.isdecimal())
    numero = max(numeros, default=0) + 1
    while True:
        pasta = GRAVACOES / str(numero)
        try:
            pasta.mkdir()
            return pasta
        except FileExistsError:
            numero += 1


def escolher_microfone(sd, dispositivo=None):
    if dispositivo is not None:
        info = sd.query_devices(dispositivo, "input")
        return dispositivo, info
    dispositivos = sd.query_devices()
    padrao = sd.default.device[0]
    if padrao is not None and 0 <= padrao < len(dispositivos):
        info = dispositivos[padrao]
        if info["max_input_channels"] > 0:
            return padrao, info
    for indice, info in enumerate(dispositivos):
        if info["max_input_channels"] > 0:
            return indice, info
    raise RuntimeError("Nenhuma entrada de áudio encontrada. Rode arecord -l.")


def configurar_captura(sd, dispositivo, info, canal, taxa_forcada=None):
    """Tenta 16 kHz; se indisponível, informa ao Vosk a frequência real da captura.

    Mantém dois canais quando disponíveis, para não perder um microfone USB
    cujo sinal útil esteja somente no canal 2. Só um canal chega ao Vosk.
    """
    max_canais = min(2, int(info["max_input_channels"]))
    if max_canais < 1 or (canal == 2 and max_canais < 2):
        raise RuntimeError("O microfone selecionado não possui o canal solicitado.")
    taxas = [taxa_forcada] if taxa_forcada else [TAXA_VOSK, int(info["default_samplerate"])]
    candidatos_canais = [max_canais]
    if max_canais == 2 and canal != 2:
        candidatos_canais.append(1)
    erros = []
    for taxa in dict.fromkeys(taxas):
        if taxa < TAXA_VOSK:
            continue
        for canais in candidatos_canais:
            try:
                sd.check_input_settings(device=dispositivo, samplerate=taxa,
                                        channels=canais, dtype="int16")
                return taxa, canais
            except (ValueError, sd.PortAudioError) as erro:
                erros.append(str(erro))
    raise RuntimeError("Não foi possível configurar o microfone em 16 kHz ou mais. "
                       + " | ".join(erros))


def terminal_interativo():
    try:
        return sys.stdin.isatty()
    except (AttributeError, OSError, ValueError):
        return False


def limpar_entrada_pendente():
    """Não deixa um Enter antigo iniciar outra captura após o limite de tempo.

    Não cria threads de leitura bloqueadas: o mesmo terminal é usado tanto pelo
    input() entre as falas quanto pela verificação de Enter durante a captura.
    """
    if not terminal_interativo():
        return
    if sys.platform == "win32":
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
    else:
        import termios
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)


def enter_pressionado():
    """Consulta o teclado sem bloquear a captura nem deixar leitores pendurados."""
    if not terminal_interativo():
        return False
    if sys.platform == "win32":
        import msvcrt
        while msvcrt.kbhit():
            tecla = msvcrt.getwch()
            if tecla == "\x03":
                raise KeyboardInterrupt
            if tecla in {"\r", "\n"}:
                return True
        return False
    import select
    if select.select([sys.stdin], [], [], 0)[0]:
        import os
        # O terminal está em modo normal: a linha só fica pronta após Enter.
        # EOF (Ctrl+D) também conclui a captura, para não esperar o limite.
        # Lê diretamente do descritor para não deixar linhas extras no buffer
        # de texto do Python e iniciar a próxima gravação sem querer.
        os.read(sys.stdin.fileno(), 4096)
        return True
    return False


class TranscricaoEmFluxo:
    """Um único consumidor usa o reconhecedor; a captura só entrega blocos mono.

    A fila comporta a captura inteira, mas possui limite de memória. Nenhum bloco
    é descartado para esconder lentidão. O Vosk continua sequencial para uma fala.
    """

    def __init__(self, modelo, taxa, max_blocos):
        self.modelo = modelo
        self.taxa = taxa
        self.fila = queue.Queue(maxsize=max_blocos)
        self.parar = threading.Event()
        self.erro = None
        self.texto = ""
        self.tempo_processamento = 0.0
        self.bytes_processados = 0
        self.pico_fila = 0
        self.thread = threading.Thread(target=self._executar, daemon=True)
        self.thread.start()

    def _executar(self):
        try:
            inicio = time.monotonic()
            reconhecedor = KaldiRecognizer(self.modelo, self.taxa)
            self.tempo_processamento += time.monotonic() - inicio
            trechos = []
            while not self.parar.is_set():
                try:
                    bloco = self.fila.get(timeout=0.1)
                except queue.Empty:
                    continue
                if bloco is None:
                    inicio = time.monotonic()
                    final = json.loads(reconhecedor.FinalResult()).get("text", "").strip()
                    self.tempo_processamento += time.monotonic() - inicio
                    if final:
                        trechos.append(final)
                    self.texto = " ".join(trechos)
                    return
                inicio = time.monotonic()
                if reconhecedor.AcceptWaveform(bloco):
                    trecho = json.loads(reconhecedor.Result()).get("text", "").strip()
                    if trecho:
                        trechos.append(trecho)
                self.tempo_processamento += time.monotonic() - inicio
                self.bytes_processados += len(bloco)
        except Exception as erro:
            self.erro = erro

    def enviar(self, bloco):
        if self.erro is not None:
            raise RuntimeError(f"Falha no reconhecimento: {self.erro}") from self.erro
        try:
            self.fila.put_nowait(bloco)
        except queue.Full as erro:
            raise RuntimeError("A fila de áudio ficou cheia; a captura foi interrompida.") from erro
        self.pico_fila = max(self.pico_fila, self.fila.qsize())

    def finalizar(self):
        self.enviar(None)
        while self.thread.is_alive():
            self.thread.join(timeout=0.1)
        if self.erro is not None:
            raise RuntimeError(f"Falha no reconhecimento: {self.erro}") from self.erro
        return self.texto

    def cancelar(self):
        self.parar.set()
        self.thread.join(timeout=0.2)


def capturar_e_transcrever(sd, modelo, dispositivo, taxa, canais, args):
    tamanho_bloco = max(1, round(taxa * 0.1))
    limite_quadros = max(1, round(taxa * args.duracao))
    max_blocos = math.ceil(limite_quadros / tamanho_bloco) + 3
    GRAVACOES.mkdir(parents=True, exist_ok=True)
    capturados = 0
    houve_perda = False
    fim_manual = False
    canais_usados = set()
    fluxo = TranscricaoEmFluxo(modelo, taxa, max_blocos)

    try:
        with TemporaryDirectory(dir=GRAVACOES) as pasta_temporaria:
            temporario = Path(pasta_temporaria) / "audio.wav"
            with wave.open(str(temporario), "wb") as wav:
                wav.setparams((canais, 2, taxa, 0, "NONE", "not compressed"))
                with sd.RawInputStream(device=dispositivo, samplerate=taxa, channels=canais,
                                       dtype="int16", blocksize=tamanho_bloco) as entrada:
                    print(f"\nPode falar! Até {args.duracao:g} segundos. "
                          "Pressione Enter para concluir a fala antes. Ctrl+C sai.", flush=True)
                    if not terminal_interativo():
                        print("Sem teclado interativo: a captura seguirá até o limite de tempo.", flush=True)
                    inicio_captura = time.monotonic()
                    while capturados < limite_quadros:
                        if fluxo.erro is not None:
                            raise RuntimeError(f"Falha no reconhecimento: {fluxo.erro}") from fluxo.erro
                        if enter_pressionado():
                            fim_manual = True
                            break
                        quadros = min(tamanho_bloco, limite_quadros - capturados)
                        bloco, perda = entrada.read(quadros)
                        bruto = bytes(bloco)
                        wav.writeframesraw(bruto)
                        houve_perda = houve_perda or perda
                        capturados += quadros

                        dados = np.frombuffer(bruto, dtype=np.int16).reshape(-1, canais)
                        if args.canal is not None:
                            candidato = args.canal - 1
                        elif canais == 1:
                            candidato = 0
                        else:
                            # Usa o canal mais forte em cada bloco. Todo o áudio é
                            # enviado ao Vosk, inclusive voz baixa e pausas; não há
                            # limiar de ruído nem detecção automática de silêncio.
                            energias = dados.astype(np.float32).var(axis=0)
                            candidato = int(energias.argmax())
                        canais_usados.add(candidato + 1)
                        mono = dados[:, candidato].astype("<i2", copy=False).tobytes()
                        fluxo.enviar(mono)
                    fim_captura = time.monotonic()

            motivo = "Enter" if fim_manual else "limite de duração"
            if capturados:
                arquivo = criar_pasta() / "audio.wav"
                temporario.replace(arquivo)
                print(f"Fala concluída por {motivo}; finalizando a transcrição...", flush=True)
            texto = fluxo.finalizar()
            finalizado = time.monotonic()

        if houve_perda:
            print("Aviso: houve perda de amostras no microfone; a transcrição pode conter falhas.",
                  file=sys.stderr, flush=True)
        if not capturados:
            print("Captura encerrada antes de receber áudio.", flush=True)
            return ""

        tempos = {
            "captura_s": round(fim_captura - inicio_captura, 4),
            "audio_capturado_s": round(capturados / taxa, 4),
            "audio_enviado_vosk_s": round(fluxo.bytes_processados / (2 * taxa), 4),
            "reconhecimento_acumulado_s": round(fluxo.tempo_processamento, 4),
            "espera_apos_captura_s": round(finalizado - fim_captura, 4),
            "taxa_hz": taxa,
            "canal": args.canal or (1 if canais == 1 else "automático por bloco"),
            "canais_utilizados": sorted(canais_usados),
            "pico_fila_blocos": fluxo.pico_fila,
            "perda_amostras": houve_perda,
            "motivo_fim": motivo,
        }
        arquivo.with_name("transcricao.txt").write_text(texto + "\n" if texto else "", encoding="utf-8")
        arquivo.with_name("tempos.json").write_text(
            json.dumps(tempos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Áudio salvo em {arquivo}", flush=True)
        print(f"Captura: {tempos['captura_s']:.2f} s | "
              f"Reconhecimento acumulado: {tempos['reconhecimento_acumulado_s']:.2f} s | "
              f"Espera após captura: {tempos['espera_apos_captura_s']:.2f} s", flush=True)
        return texto
    finally:
        fluxo.cancelar()


def canais_para_transcrever(arquivo, canal):
    with wave.open(str(arquivo), "rb") as wav:
        canais = wav.getnchannels()
        if canais not in (1, 2) or wav.getsampwidth() != 2:
            raise RuntimeError("Use um WAV PCM de 16 bits com um ou dois canais.")
        if canal == 2 and canais == 1:
            raise RuntimeError("O áudio tem apenas um canal.")
        if canal is not None:
            return [canal]
        if canais == 1:
            return [1]
        amostras = array("h", wav.readframes(wav.getnframes()))

    energia_1 = energia_do_canal(amostras[0::2])
    energia_2 = energia_do_canal(amostras[1::2])
    return [2, 1] if energia_2 > energia_1 else [1, 2]


def preparar_audio(arquivo, canal):
    resultado = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(arquivo),
            "-af", f"pan=mono|c0=c{canal - 1}", "-ar", str(TAXA_VOSK),
            "-f", "s16le", "pipe:1",
        ],
        capture_output=True,
    )
    if resultado.returncode != 0:
        detalhe = resultado.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Falha ao converter o áudio com FFmpeg. {detalhe}")
    return resultado.stdout


def reconhecer(audio, modelo):
    reconhecedor = KaldiRecognizer(modelo, TAXA_VOSK)
    trechos = []

    for inicio in range(0, len(audio), 4000):
        bloco = audio[inicio:inicio + 4000]
        if reconhecedor.AcceptWaveform(bloco):
            texto = json.loads(reconhecedor.Result())["text"].strip()
            if texto:
                trechos.append(texto)

    texto_final = json.loads(reconhecedor.FinalResult())["text"].strip()
    if texto_final:
        trechos.append(texto_final)
    return " ".join(trechos)


def transcrever(arquivo, modelo, canal):
    for tentativa in canais_para_transcrever(arquivo, canal):
        print(f"Canal para o Vosk: {tentativa}", flush=True)
        texto = reconhecer(preparar_audio(arquivo, tentativa), modelo)
        if texto:
            return texto
    return ""


def mostrar_resposta(texto):
    print(f"Você falou: {texto}" if texto else "Nenhuma fala reconhecida.", flush=True)
    resposta = responder(texto)
    if resposta is not None:
        print(f"Roberta: {resposta}", flush=True)


def positivo(valor):
    numero = float(valor)
    if not math.isfinite(numero) or numero <= 0:
        raise argparse.ArgumentTypeError("Use um número finito maior que zero.")
    return numero


def dispositivo_ou_nome(valor):
    try:
        return int(valor)
    except ValueError:
        return valor


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--canal", type=int, choices=(1, 2), help="força o canal; padrão: seleção automática")
    parser.add_argument("--arquivo", type=Path, help="transcreve um WAV salvo e encerra (usa FFmpeg)")
    parser.add_argument("--modelo", type=Path, default=MODELO, help="pasta do modelo Vosk")
    parser.add_argument("--dispositivo", type=dispositivo_ou_nome, help="índice ou nome do microfone")
    parser.add_argument("--listar-microfones", action="store_true", help="lista dispositivos e encerra")
    parser.add_argument("--uma-vez", action="store_true", help="faz apenas uma captura e encerra")
    parser.add_argument("--continuo", action="store_true", help="inicia capturas sem esperar Enter")
    parser.add_argument("--duracao", type=positivo, default=DURACAO,
                        help="limite total de cada captura em segundos (padrão: 15)")
    parser.add_argument("--taxa", type=int, help="força a frequência de captura, em Hz (mínimo: 16000)")
    args = parser.parse_args()
    if args.taxa is not None and args.taxa < TAXA_VOSK:
        parser.error("--taxa deve ser pelo menos 16000 Hz para este modelo.")

    try:
        # Importa sounddevice somente no modo de microfone.
        if args.listar_microfones or args.arquivo is None:
            import sounddevice as sd
            if args.listar_microfones:
                print(sd.query_devices())
                return 0
        global np, KaldiRecognizer
        import numpy as np
        from vosk import KaldiRecognizer, Model, SetLogLevel

        if not args.modelo.is_dir():
            raise RuntimeError(f"Modelo não encontrado: {args.modelo}. "
                               "Coloque a pasta ao lado do script ou informe --modelo.")
        if args.arquivo is not None and shutil.which("ffmpeg") is None:
            raise RuntimeError("Para --arquivo, instale o FFmpeg: sudo apt install ffmpeg")
        SetLogLevel(-1)
        print("Carregando o modelo de português (uma vez nesta execução)...", flush=True)
        inicio = time.monotonic()
        modelo = Model(str(args.modelo))
        print(f"Modelo pronto em {time.monotonic() - inicio:.2f} s.", flush=True)

        if args.arquivo is not None:
            inicio = time.monotonic()
            texto = transcrever(args.arquivo, modelo, args.canal)
            mostrar_resposta(texto)
            print(f"Conversão e reconhecimento do arquivo: {time.monotonic() - inicio:.2f} s")
            return 0

        dispositivo, info = escolher_microfone(sd, args.dispositivo)
        taxa, canais = configurar_captura(sd, dispositivo, info, args.canal, args.taxa)
        print(f"Microfone: {info['name']} | {taxa} Hz | {canais} canal(is)", flush=True)
        if taxa != TAXA_VOSK:
            print("O microfone usa a frequência acima; o Vosk fará a redução internamente.", flush=True)
        print("\nA Roberta está pronta. O modelo continuará carregado entre as falas.", flush=True)
        while True:
            if not args.continuo:
                limpar_entrada_pendente()
                escolha = input("\nLeia a resposta com calma. Enter para iniciar a fala "
                                "ou 'sair': ").strip().casefold()
                if escolha in {"sair", "q", "exit"}:
                    print("Roberta encerrada.")
                    return 0
                if escolha:
                    print("Pressione apenas Enter para iniciar uma fala.", flush=True)
                    continue
            texto = capturar_e_transcrever(sd, modelo, dispositivo, taxa, canais, args)
            if texto is not None:
                mostrar_resposta(texto)
            if args.uma_vez:
                return 0
    except KeyboardInterrupt:
        print("\nRoberta encerrada.")
        return 130
    except EOFError:
        print("\nEntrada do terminal encerrada. Roberta encerrada.")
        return 0
    except ImportError as erro:
        print(f"Dependência ausente: {erro}. No ambiente Python da Roberta, instale:\n"
              "python3 -m pip install vosk sounddevice numpy", file=sys.stderr)
        return 1
    except Exception as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
