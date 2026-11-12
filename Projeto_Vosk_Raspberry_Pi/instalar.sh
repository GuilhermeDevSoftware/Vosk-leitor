#!/bin/bash
set -e

MODEL="vosk-model-small-pt-0.3"
ZIP="${MODEL}.zip"
URL="https://alphacephei.com/vosk/models/${ZIP}"

echo "1/4 - Instalando dependências do sistema..."
sudo apt update
sudo apt install -y python3-venv python3-pip libportaudio2 libasound2 wget unzip

echo "2/4 - Criando ambiente Python..."
python3 -m venv ambiente

echo "3/4 - Instalando bibliotecas Python..."
./ambiente/bin/python -m pip install --upgrade pip
./ambiente/bin/python -m pip install vosk sounddevice

echo "4/4 - Baixando modelo de português brasileiro..."
if [ ! -d "$MODEL" ]; then
    wget -O "$ZIP" "$URL"
    unzip -o "$ZIP"
    rm -f "$ZIP"
fi

echo
echo "Instalação concluída!"
echo "Para iniciar o teste, execute:"
echo "./ambiente/bin/python teste_voz.py"
