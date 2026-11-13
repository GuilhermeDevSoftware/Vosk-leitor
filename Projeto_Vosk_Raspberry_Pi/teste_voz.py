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
