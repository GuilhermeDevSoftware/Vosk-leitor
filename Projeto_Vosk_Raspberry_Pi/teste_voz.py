#!/usr/bin/env python3
"""Grava 15 segundos e transcreve a fala em português com Vosk."""

import argparse
import json
import shutil
import subprocess
import sys
import wave
from array import array
from pathlib import Path

from vosk import KaldiRecognizer, Model, SetLogLevel


DURACAO = 15
TAXA_VOSK = 16000
PROJETO = Path(__file__).resolve().parent
MODELO = PROJETO / "vosk-model-small-pt-0.3"
GRAVACOES = PROJETO / "gravacoes"


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


def gravar(sd, dispositivo, taxa, canais):
    blocos = []
    restante = taxa * DURACAO
    houve_perda = False

    with sd.RawInputStream(
        device=dispositivo, samplerate=taxa, channels=canais, dtype="int16"
    ) as entrada:
        print(f"Gravando por {DURACAO} segundos. Pode falar!", flush=True)
        while restante:
            quadros = min(restante, taxa // 5)
            bloco, perda = entrada.read(quadros)
            blocos.append(bytes(bloco))
            houve_perda = houve_perda or perda
            restante -= quadros

    if houve_perda:
        print("Aviso: houve perda de amostras durante a captura.", file=sys.stderr)
    return blocos


def criar_pasta():
    GRAVACOES.mkdir(exist_ok=True)
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
    blocos = gravar(sd, dispositivo, taxa, canais)
    arquivo = criar_pasta() / "audio.wav"
    with wave.open(str(arquivo), "wb") as wav:
        wav.setparams((canais, 2, taxa, 0, "NONE", "not compressed"))
        wav.writeframes(b"".join(blocos))
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
        return 0

    except KeyboardInterrupt:
        print("\nExecução interrompida.")
        return 130
    except Exception as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
