cd ~/projeto && cat > teste_voz.py <<'PY'
#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

MODELO = Path(__file__).resolve().parent / "vosk-model-small-pt-0.3"


def escolher_microfone():
    dispositivos = sd.query_devices()
    padrao = sd.default.device[0]

    if padrao is not None and 0 <= padrao < len(dispositivos):
        if dispositivos[padrao]["max_input_channels"] > 0:
            return padrao, dispositivos[padrao]

    for indice, info in enumerate(dispositivos):
        if info["max_input_channels"] > 0:
            return indice, info

    raise RuntimeError("Nenhuma entrada de áudio encontrada. Rode arecord -l.")


def main():
    parser = argparse.ArgumentParser(description="Transcreve a voz em português.")
    parser.add_argument("--canal", type=int, choices=(1, 2), default=1,
                        help="Canal do microfone a transcrever (padrão: 1).")
    args = parser.parse_args()

    try:
        dispositivo, info = escolher_microfone()
        canais = min(2, info["max_input_channels"])
        if args.canal > canais:
            raise RuntimeError("O microfone selecionado tem apenas um canal.")

        taxa = int(info["default_samplerate"])
        amostras_por_bloco = taxa // 10

        SetLogLevel(-1)
        print("Carregando o modelo de português...", flush=True)
        modelo = Model(str(MODELO))
        reconhecedor = KaldiRecognizer(modelo, taxa)
        parcial_anterior = ""

        with sd.RawInputStream(
            device=dispositivo,
            samplerate=taxa,
            channels=canais,
            dtype="int16",
        ) as entrada:
            print(f"Microfone: {info['name']}", flush=True)
            print(f"Taxa: {taxa} Hz | Canal: {args.canal} de {canais}", flush=True)
            print("Fale uma frase e faça uma pausa. Ctrl+C encerra.", flush=True)

            while True:
                bloco, houve_perda = entrada.read(amostras_por_bloco)
                if houve_perda:
                    print("Aviso: perda de amostras de áudio.", file=sys.stderr)

                audio = bytes(bloco)
                if canais == 2:
                    amostras = memoryview(audio).cast("h")
                    audio = amostras[args.canal - 1::2].tobytes()

                if reconhecedor.AcceptWaveform(audio):
                    texto = json.loads(reconhecedor.Result()).get("text", "")
                    if texto:
                        print("Você falou:", texto, flush=True)
                    parcial_anterior = ""
                else:
                    parcial = json.loads(reconhecedor.PartialResult()).get("partial", "")
                    if parcial and parcial != parcial_anterior:
                        print("Parcial:", parcial, flush=True)
                    parcial_anterior = parcial

    except KeyboardInterrupt:
        print("\nTeste encerrado.")
    except Exception as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
PY