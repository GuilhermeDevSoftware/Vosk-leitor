# Roberta — Assistente de voz com Vosk

A **Roberta** é uma assistente de voz em português brasileiro desenvolvida em Python e executada em uma **Raspberry Pi 3 Model B**. Ela recebe áudio de um microfone USB, transforma a fala em texto com o Vosk e apresenta respostas cadastradas no terminal.

O projeto foi desenvolvido na disciplina de **Sistemas Embarcados**, ministrada pelo **professor Dr. Breno Ortega**, no curso de **Engenharia de Computação da Unilins**.

Após a instalação das dependências e do modelo de reconhecimento, a captura, a transcrição e as respostas funcionam **localmente, sem conexão com a internet**. As respostas são exibidas por escrito.

## Integrantes

Integrantes em ordem alfabética:

| Nome | ID |
| --- | --- |
| Emilly Zagreti Valle de Oliveira | 317554 |
| Flavio Augusto Castilho Cucolo | 316199 |
| Gabriel Vinicius | 316809 |
| Guilherme Henrique Costa Silva | 317470 |
| Murilo Rodrigues de Farias | 317846 |

## Objetivo do projeto

Demonstrar o reconhecimento de voz local em uma plataforma embarcada, integrando captura de áudio, processamento de sinais e uma aplicação interativa. A proposta permite estudar a comunicação com um periférico USB, o uso de um modelo de reconhecimento de fala e a organização de tarefas em um dispositivo com recursos limitados.

A Roberta utiliza um modelo treinado para transcrever o áudio. Depois da transcrição, o programa compara a frase com comandos cadastrados e seleciona uma resposta. Frases sem correspondência são exibidas como transcrição, sem gerar uma resposta automática.

## Como funciona

1. O programa carrega o modelo de português `vosk-model-small-pt-0.3` e o mantém na memória durante a execução.
2. O usuário pressiona **Enter** para iniciar uma gravação e espera aparecer **“Pode falar!”**.
3. O microfone captura o áudio em blocos. Uma fila encaminha esses blocos para o Vosk, permitindo que o reconhecimento comece enquanto a pessoa ainda está falando.
4. A gravação termina quando o usuário pressiona **Enter novamente** ou quando alcança **15 segundos**. O silêncio e o ruído não controlam o encerramento da captura.
5. O programa finaliza o processamento pendente, exibe a transcrição e apresenta uma resposta quando identifica um comando cadastrado.
6. O áudio, a transcrição e os tempos de processamento são salvos em uma pasta numerada.
7. A Roberta aguarda um novo Enter. O usuário pode ler a resposta com calma antes da próxima gravação.

Na captura pelo microfone, o programa tenta usar 16 kHz. Se o dispositivo exigir outra frequência compatível, informa a frequência real ao Vosk, que faz a redução internamente. O reconhecedor recebe áudio mono; o WAV salvo preserva os canais e a frequência utilizados na captura.

O FFmpeg é utilizado no modo de transcrição de **arquivos WAV já gravados**, para selecionar o canal e converter o áudio para mono a 16 kHz.

## Materiais necessários

| Material | Finalidade |
| --- | --- |
| Raspberry Pi 3 Model B | Executar o programa e o reconhecimento de voz. |
| Cartão microSD com espaço para Raspberry Pi OS, dependências e gravações | Armazenar o sistema e os arquivos do projeto. |
| Fonte de alimentação micro USB adequada à Raspberry Pi 3 | Alimentar a placa e o microfone USB. |
| Microfone USB compatível com Linux | Captar a fala. |
| Monitor e cabo HDMI | Exibir o terminal e as respostas. |
| Teclado USB | Iniciar e concluir as gravações e executar os comandos. |
| Computador com leitor de cartão microSD | Preparar o cartão, caso o sistema ainda não esteja instalado. |
| Acesso à internet por Wi-Fi ou Ethernet | Baixar o projeto, as dependências e o modelo durante a instalação. |

Um mouse facilita a configuração inicial quando se utiliza o ambiente gráfico do Raspberry Pi OS. Para a interação com a Roberta pelo terminal, basta o teclado.

## 1. Preparar a Raspberry Pi

Se o Raspberry Pi OS já estiver instalado e conectado à internet, prossiga para a próxima seção.

1. No computador, baixe o [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Insira o cartão microSD no leitor. No Imager, selecione a **Raspberry Pi 3**, uma edição compatível do **Raspberry Pi OS** e o cartão de destino.
3. Configure o usuário, a senha e a rede Wi-Fi nas opções de personalização, quando disponíveis, e grave o sistema no cartão.
4. Com a Raspberry desligada, insira o cartão e conecte o monitor, o teclado e o microfone USB. Conecte a fonte para iniciar o sistema.
5. Conclua a configuração inicial. Se a rede não tiver sido configurada no Imager, conecte o Wi-Fi pela interface do sistema ou utilize um cabo Ethernet.
6. Abra o aplicativo **Terminal** da Raspberry Pi. Os comandos das próximas seções devem ser executados nele, um por vez.

## 2. Baixar e instalar o projeto

Os comandos abaixo criam a pasta `Vosk-leitor` dentro da pasta pessoal do usuário da Raspberry Pi.

### Instalar ferramentas do sistema

```bash
sudo apt update
sudo apt install -y git ffmpeg alsa-utils
```

O Git baixa o repositório, o FFmpeg permite transcrever WAVs existentes e o pacote `alsa-utils` fornece ferramentas para verificar os dispositivos de áudio.

### Baixar o repositório

```bash
cd ~
git clone https://github.com/GuilhermeDevSoftware/Vosk-leitor.git
cd ~/Vosk-leitor/Projeto_Vosk_Raspberry_Pi
```

### Executar o instalador e instalar o NumPy

```bash
bash instalar.sh
./ambiente/bin/python -m pip install numpy
```

O instalador prepara as dependências de áudio do sistema, cria o ambiente virtual `ambiente`, instala o Vosk e o `sounddevice` e baixa e extrai o modelo `vosk-model-small-pt-0.3`. O comando seguinte instala o NumPy, também necessário na versão atual do programa.

Mantenha a internet conectada até a conclusão. A instalação pode demorar alguns minutos, dependendo da conexão e do desempenho da placa.

### Conferir a instalação

Ainda na pasta `Projeto_Vosk_Raspberry_Pi`, execute:

```bash
./ambiente/bin/python -c "import vosk, sounddevice, numpy; print('Dependencias instaladas corretamente.')"
ls vosk-model-small-pt-0.3
```

O primeiro comando deve mostrar a confirmação sem erro de importação. O segundo deve listar o conteúdo da pasta do modelo, incluindo suas pastas de configuração e reconhecimento.

Todos os comandos Python deste guia usam `./ambiente/bin/python`, que já aponta para o ambiente virtual correto. Não é necessário ativá-lo com `source` para usar esses comandos.

## 3. Conferir o microfone

Conecte o microfone USB antes de iniciar o programa. Para verificar se o sistema reconhece uma entrada de áudio:

```bash
arecord -l
```

Em seguida, liste os dispositivos disponíveis para a Roberta:

```bash
./ambiente/bin/python teste_voz.py --listar-microfones
```

Identifique o nome e o índice do microfone USB. Para escolher um dispositivo manualmente, use o índice mostrado por **este último comando**. A numeração do `arecord` pode ser diferente.

Por exemplo, se o microfone tiver índice `3`:

```bash
./ambiente/bin/python teste_voz.py --dispositivo 3
```

Sem essa opção, o programa utiliza a entrada padrão do sistema ou procura uma entrada disponível.

## 4. Executar a Roberta

Na pasta do projeto, execute:

```bash
./ambiente/bin/python teste_voz.py
```

Aguarde o carregamento do modelo. Depois, siga esta sequência:

| Momento | Ação do usuário | Comportamento da Roberta |
| --- | --- | --- |
| Antes da gravação | Pressione Enter. | Abre o microfone e mostra “Pode falar!”. |
| Durante a gravação | Fale uma frase. | Captura e processa o áudio. |
| Ao concluir a fala | Pressione Enter novamente. | Encerra a captura e finaliza a transcrição. |
| Se não concluir manualmente | Aguarde o limite de 15 segundos. | Encerra a captura automaticamente. |
| Depois da resposta | Leia o resultado e pressione Enter quando quiser continuar. | Inicia outra gravação, mantendo o modelo carregado. |
| Para encerrar o programa | Digite `sair` e pressione Enter no intervalo entre as gravações. | Finaliza a execução. |

Também é possível encerrar com **Ctrl+C**. Use um terminal interativo para que o Enter durante a captura funcione.

Ao terminar uma gravação, pode existir uma espera adicional enquanto o Vosk processa os blocos restantes. Pressionar Enter conclui a captura do microfone; a resposta aparece após a finalização do reconhecimento.

### Executar novamente em outro dia

Não é necessário reinstalar as bibliotecas nem baixar o modelo a cada uso. Abra o Terminal e execute:

```bash
cd ~/Vosk-leitor/Projeto_Vosk_Raspberry_Pi
./ambiente/bin/python teste_voz.py
```

O caminho acima corresponde à instalação deste guia. Se o projeto estiver em outra pasta, utilize o caminho em que ele foi salvo.

## Exemplos de comandos de voz

| Frase dita | Resposta da Roberta |
| --- | --- |
| Olá, Roberta, tudo bem? | Olá, eu estou bem. |
| Que horas são? | Agora são 14:30. |
| Que dia é hoje? | Hoje é 20/11/2026. |
| Qual é o seu nome? | Eu sou a Roberta. |
| Você é a Alexa? | Sou a Roberta. Meu escritório é um Raspberry Pi. |
| Conte uma piada. | Por que o computador foi ao médico? Porque pegou um vírus. |
| Obrigado. | De nada! |
| Tchau. | Até mais! |

Os valores de data e hora da tabela são exemplos. A Roberta consulta o relógio do sistema da Raspberry Pi; por isso, a data, a hora e o fuso horário devem estar configurados corretamente.

O comando de voz “Tchau” gera a resposta cadastrada. Para fechar o programa, use `sair` pelo teclado entre as gravações ou Ctrl+C.

## Arquivos gerados

Cada captura que recebe áudio cria uma pasta numerada dentro de `gravacoes`. Por exemplo:

| Caminho | Conteúdo |
| --- | --- |
| `gravacoes/1/audio.wav` | Áudio da primeira captura. |
| `gravacoes/1/transcricao.txt` | Texto reconhecido nessa captura. |
| `gravacoes/1/tempos.json` | Tempos de processamento e informações da captura. |
| `gravacoes/2/audio.wav` | Áudio da segunda captura; as demais seguem a mesma organização. |

O arquivo `tempos.json` registra dados como a duração capturada, o tempo acumulado de reconhecimento, a espera após a captura e o motivo do encerramento: Enter ou limite de duração.

O reconhecimento ocorre durante a captura. Portanto, seu tempo acumulado não deve ser simplesmente somado ao tempo de gravação para calcular a espera percebida pelo usuário.

## Outras formas de execução

Execute os exemplos abaixo dentro de `Projeto_Vosk_Raspberry_Pi`.

### Transcrever um WAV salvo

```bash
./ambiente/bin/python teste_voz.py --arquivo gravacoes/1/audio.wav
```

Esse modo utiliza o FFmpeg e aceita um WAV PCM de 16 bits com um ou dois canais. Ele exibe a transcrição e a resposta correspondente, quando houver, e encerra. O resultado não sobrescreve o `transcricao.txt` já existente.

### Fazer apenas uma gravação

```bash
./ambiente/bin/python teste_voz.py --uma-vez
```

Pressione Enter para começar e outro Enter para concluir, ou aguarde os 15 segundos. Depois de mostrar o resultado, o programa encerra.

### Alterar o limite de gravação

```bash
./ambiente/bin/python teste_voz.py --duracao 10
```

Nesse exemplo, cada captura dura até 10 segundos. O encerramento antecipado por Enter continua disponível.

### Selecionar o canal do microfone

Se a seleção automática não captar a fala corretamente, teste um canal de cada vez:

```bash
./ambiente/bin/python teste_voz.py --canal 1
```

```bash
./ambiente/bin/python teste_voz.py --canal 2
```

Encerre uma execução antes de testar a outra. A opção `--canal 2` exige um dispositivo com pelo menos dois canais de entrada.

Para consultar todas as opções disponíveis:

```bash
./ambiente/bin/python teste_voz.py --help
```

## Cadastrar novas respostas

Abra o código:

```bash
nano teste_voz.py
```

Localize o dicionário `RESPOSTAS_FIXAS` e acrescente uma entrada, mantendo a vírgula entre os itens:

```python
"quem criou voce": "Fui desenvolvida pela turma de Sistemas Embarcados da Unilins.",
```

Escreva a frase de entrada em **minúsculas, sem acentos e sem pontuação**. O programa normaliza o texto reconhecido antes de procurar a resposta. O nome “Roberta” é removido durante essa comparação, portanto não precisa fazer parte da chave cadastrada.

Salve no Nano com **Ctrl+O**, pressione **Enter** e saia com **Ctrl+X**. Reinicie a Roberta para carregar as novas respostas.

As variações de perguntas sobre hora e data ficam, respectivamente, nos conjuntos `PERGUNTAS_HORA` e `PERGUNTAS_DATA`.

## Solução de problemas

### Aparece “No module named ...” ou “externally-managed-environment”

Dentro da pasta do projeto, instale as dependências usando o Python do ambiente virtual:

```bash
./ambiente/bin/python -m pip install vosk sounddevice numpy
```

Depois, execute o programa com `./ambiente/bin/python teste_voz.py`. O ambiente virtual separa as bibliotecas do projeto dos pacotes gerenciados pelo sistema operacional.

Se a pasta `ambiente` ainda não existir, volte à etapa de instalação e execute `bash instalar.sh` antes desse comando.

### O modelo de português não foi encontrado

Confira se a pasta `vosk-model-small-pt-0.3` está ao lado de `teste_voz.py`. Caso o download não tenha terminado, na pasta do projeto execute:

```bash
wget -O vosk-model-small-pt-0.3.zip https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip
unzip -o vosk-model-small-pt-0.3.zip
```

### O microfone não aparece ou a transcrição fica vazia

Confira a conexão USB, execute `arecord -l` e `--listar-microfones` e selecione o dispositivo correto com `--dispositivo`. Se necessário, teste `--canal 1` e `--canal 2`. Fale perto do microfone, com voz natural, e espere aparecer “Pode falar!” antes de começar.

### O Enter não conclui a gravação

Execute o programa no aplicativo Terminal da Raspberry Pi, com o teclado ligado. O encerramento antecipado depende de uma entrada de terminal interativa; consoles de algumas IDEs não fornecem essa entrada.

### O reconhecimento demora ou apresenta erros

A Raspberry Pi 3 possui recursos limitados, e a finalização pode levar mais tempo conforme o áudio e a carga do sistema. Comece com frases curtas, reduza os ruídos próximos e evite executar outros programas pesados durante a demonstração. Os tempos exibidos no terminal e salvos em `tempos.json` ajudam a observar esse comportamento.

A precisão depende do modelo, da pronúncia e da qualidade do áudio. Uma frase transcrita de forma diferente da chave cadastrada pode aparecer no terminal sem produzir a resposta esperada.

## Relação com Sistemas Embarcados

O projeto reúne a integração de um periférico de entrada, o processamento local em uma Raspberry Pi e a execução de tarefas concorrentes com uma fila de áudio. A captura e o reconhecimento trabalham de forma sobreposta, enquanto os resultados são armazenados para consulta.

O modelo permanece carregado entre as interações, evitando repetir o carregamento a cada frase. Essa organização reduz etapas repetidas, mas não distribui automaticamente o reconhecimento de uma mesma fala pelos quatro núcleos da placa. O desempenho deve ser avaliado no hardware utilizado.

## Arquivos principais do repositório

Este README deve ficar na **raiz do repositório**.

| Arquivo ou pasta | Função |
| --- | --- |
| [teste_voz.py](Projeto_Vosk_Raspberry_Pi/teste_voz.py) | Captura, transcrição, controle por Enter e respostas da Roberta. |
| [instalar.sh](Projeto_Vosk_Raspberry_Pi/instalar.sh) | Preparação do ambiente virtual, dependências iniciais e modelo de português. |
| `Projeto_Vosk_Raspberry_Pi/ambiente/` | Ambiente virtual criado na instalação. |
| `Projeto_Vosk_Raspberry_Pi/vosk-model-small-pt-0.3/` | Arquivos locais do modelo de reconhecimento. |
| `Projeto_Vosk_Raspberry_Pi/gravacoes/` | Áudios, transcrições e tempos das capturas. |

## Referências

- [Documentação do Vosk](https://alphacephei.com/vosk/).
- [Modelos oficiais do Vosk](https://alphacephei.com/vosk/models).
- [Preparação da Raspberry Pi](https://www.raspberrypi.com/documentation/computers/getting-started.html).
- [Python e ambientes virtuais no Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html).
- [Documentação do módulo venv do Python](https://docs.python.org/3/library/venv.html).
