#!/usr/bin/env python3
"""Roberta encerra a escuta após 3 s de silêncio e transcreve com Vosk."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import wave
from array import array
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from vosk import KaldiRecognizer, Model, SetLogLevel


DURACAO = 15
SEGUNDOS_SILENCIO = 3
LIMIAR_SILENCIO = 120  # Nível RMS em PCM de 16 bits, após descontar o nível DC.
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


def escolher_microfone(sd):
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


def gravar(sd, dispositivo, taxa, canais, wav, canal=None):
    restante = taxa * DURACAO
    quadros_por_bloco = max(1, taxa // 10)
    limite_silencio = taxa * SEGUNDOS_SILENCIO
    quadros_em_silencio = 0
    energia_minima = LIMIAR_SILENCIO ** 2
    indices_canais = range(canais) if canal is None else (canal - 1,)
    houve_perda = False

    with sd.RawInputStream(
        device=dispositivo, samplerate=taxa, channels=canais, dtype="int16"
    ) as entrada:
        print(
            f"Pode falar! Até {DURACAO} s de gravação. "
            f"A escuta encerra após {SEGUNDOS_SILENCIO} s de silêncio.",
            flush=True,
        )
        while restante and quadros_em_silencio < limite_silencio:
            quadros = min(restante, quadros_por_bloco, limite_silencio - quadros_em_silencio)
            bloco, perda = entrada.read(quadros)
            wav.writeframesraw(bloco)
            houve_perda = houve_perda or perda
            restante -= quadros

            amostras = memoryview(bloco).cast("h")
            som_detectado = any(
                energia_do_canal(amostras[indice::canais]) >= energia_minima
                for indice in indices_canais
            )
            if som_detectado or perda:
                quadros_em_silencio = 0
            else:
                quadros_em_silencio += quadros

    if houve_perda:
        print("Aviso: houve perda de amostras durante a captura.", file=sys.stderr)


def criar_pasta():
    numeros = (int(item.name) for item in GRAVACOES.iterdir() if item.name.isdecimal())
    numero = max(numeros, default=0) + 1
    while True:
        pasta = GRAVACOES / str(numero)
        try:
            pasta.mkdir()
            return pasta
        except FileExistsError:
            numero += 1


def gravar_e_salvar(canal):
    import sounddevice as sd

    dispositivo, info = escolher_microfone(sd)
    taxa = int(info["default_samplerate"])
    canais = min(2, info["max_input_channels"])
    if canal == 2 and canais == 1:
        raise RuntimeError("O microfone selecionado tem apenas um canal.")

    print(f"Microfone: {info['name']} | {taxa} Hz", flush=True)
    GRAVACOES.mkdir(exist_ok=True)
    # Numera a gravação após fechar um WAV completo.
    with TemporaryDirectory(dir=GRAVACOES) as pasta_temporaria:
        temporario = Path(pasta_temporaria) / "audio.wav"
        with wave.open(str(temporario), "wb") as wav:
            wav.setparams((canais, 2, taxa, 0, "NONE", "not compressed"))
            gravar(sd, dispositivo, taxa, canais, wav, canal=canal)

        arquivo = criar_pasta() / "audio.wav"
        temporario.replace(arquivo)

    print(f"Gravação concluída. Áudio salvo em {arquivo}", flush=True)
    return arquivo


def energia_do_canal(amostras):
    if not amostras:
        return 0
    media = sum(amostras) / len(amostras)
    # A variância mede o sinal sem contar o deslocamento DC como volume.
    return sum(valor * valor for valor in amostras) / len(amostras) - media**2


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canal", type=int, choices=(1, 2),
        help="força o canal indicado. Por padrão, a seleção é automática",
    )
    parser.add_argument("--arquivo", type=Path, help="mostra a transcrição de um WAV já gravado")
    args = parser.parse_args()

    try:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("Instale o FFmpeg com sudo apt install ffmpeg.")

        SetLogLevel(-1)
        print("Carregando o modelo de português...", flush=True)
        modelo = Model(str(MODELO))

        arquivo = args.arquivo or gravar_e_salvar(args.canal)
        print("Transcrevendo...", flush=True)
        texto = transcrever(arquivo, modelo, args.canal)
        if args.arquivo is None:
            arquivo.with_name("transcricao.txt").write_text(
                texto + "\n" if texto else "", encoding="utf-8"
            )
        print(f"Você falou: {texto}" if texto else "Nenhuma fala reconhecida.")
        resposta = responder(texto)
        if resposta is not None:
            print(f"Roberta: {resposta}")
        return 0

    except KeyboardInterrupt:
        print("\nExecução interrompida.")
        return 130
    except Exception as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
