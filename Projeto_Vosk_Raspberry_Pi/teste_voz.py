#!/usr/bin/env python3
"""
Teste de reconhecimento de voz com Vosk em português brasileiro.
Captura áudio do microfone e mostra a transcrição no terminal.
"""

import json
import queue
import sys
import sounddevice as sd
from vosk import Model, KaldiRecognizer

MODEL_PATH = "vosk-model-small-pt-0.3"
audio_queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Aviso do áudio: {status}", file=sys.stderr)
    audio_queue.put(bytes(indata))


def escolher_microfone():
    dispositivos = sd.query_devices()
    entrada_padrao = sd.default.device[0]

    if entrada_padrao is not None and entrada_padrao >= 0:
        info = sd.query_devices(entrada_padrao, "input")
        if info["max_input_channels"] > 0:
            return entrada_padrao, info

    for numero, info in enumerate(dispositivos):
        if info["max_input_channels"] > 0:
            return numero, info

    raise RuntimeError(
        "Nenhum microfone de entrada foi encontrado. "
        "Verifique se o microfone USB está conectado."
    )


def main():
    print("Carregando modelo de português brasileiro...")
    try:
        model = Model(MODEL_PATH)
    except Exception as erro:
        print(f"Não foi possível carregar o modelo: {erro}")
        print("Execute primeiro o instalador ou confira a pasta do modelo.")
        sys.exit(1)

    try:
        device_id, device_info = escolher_microfone()
    except Exception as erro:
        print(erro)
        sys.exit(1)

    sample_rate = int(device_info["default_samplerate"])
    recognizer = KaldiRecognizer(model, sample_rate)

    print(f"Microfone: {device_info['name']}")
    print(f"Taxa de amostragem: {sample_rate} Hz")
    print("\nAssistente iniciada!")
    print("Fale em português. Pressione CTRL+C para encerrar.\n")

    try:
        with sd.RawInputStream(
            device=device_id,
            samplerate=sample_rate,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=audio_callback,
        ):
            while True:
                data = audio_queue.get()

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        print("Você falou:", text)
                else:
                    partial = json.loads(recognizer.PartialResult())
                    partial_text = partial.get("partial", "").strip()
                    # A transcrição parcial não é exibida para evitar repetição.

    except KeyboardInterrupt:
        print("\nTeste encerrado.")
    except Exception as erro:
        print(f"\nErro durante a captura de áudio: {erro}")
        print("Confira o microfone USB e a lista de dispositivos de áudio.")
        sys.exit(1)


if __name__ == "__main__":
    main()
