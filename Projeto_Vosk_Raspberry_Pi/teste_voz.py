#!/usr/bin/env python3
"""Grava 15 segundos e transcreve a fala em português com Vosk."""

import argparse
import json
import sys
import wave
from pathlib import Path

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel


DURACAO = 15
PROJETO = Path(__file__).resolve().parent
MODELO = PROJETO / "vosk-model-small-pt-0.3"
GRAVACOES = PROJETO / "gravacoes"


def escolher_microfone():
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


def gravar(dispositivo, taxa, canais):
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


def transcrever(blocos, modelo, taxa, canais, canal):
    reconhecedor = KaldiRecognizer(modelo, taxa)
    trechos = []

    for bloco in blocos:
        if canais == 2:
            amostras = memoryview(bloco).cast("h")
            bloco = amostras[canal - 1::2].tobytes()

        if reconhecedor.AcceptWaveform(bloco):
            texto = json.loads(reconhecedor.Result())["text"].strip()
            if texto:
                trechos.append(texto)

    texto_final = json.loads(reconhecedor.FinalResult())["text"].strip()
    if texto_final:
        trechos.append(texto_final)
    return " ".join(trechos)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canal", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()

    try:
        dispositivo, info = escolher_microfone()
        taxa = int(info["default_samplerate"])
        canais = min(2, info["max_input_channels"])
        if args.canal > canais:
            raise RuntimeError("O microfone selecionado tem apenas um canal.")

        SetLogLevel(-1)
        print("Carregando o modelo de português...", flush=True)
        modelo = Model(str(MODELO))
        print(f"Microfone: {info['name']} | Canal para o Vosk: {args.canal}")

        blocos = gravar(dispositivo, taxa, canais)
        print("Gravação concluída. Transcrevendo...", flush=True)

        pasta = criar_pasta()
        with wave.open(str(pasta / "audio.wav"), "wb") as wav:
            wav.setparams((canais, 2, taxa, 0, "NONE", "not compressed"))
            wav.writeframes(b"".join(blocos))
        print(f"Áudio salvo em {pasta / 'audio.wav'}", flush=True)

        texto = transcrever(blocos, modelo, taxa, canais, args.canal)
        (pasta / "transcricao.txt").write_text(
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