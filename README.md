# Jarvis v0.7 🖐️👏👏 + 🎙️ + 🧠💾 + 📁 + 🖥️ "Jarvis, abaixa o volume e fecha o Spotify"

## Interromper e editar (v0.7) ✋📝
- **"Jarvis!" por cima da fala** — se ele estiver falando demais, diga **"Jarvis"** por cima que ele **cala na hora** e abre a escuta para o próximo pedido. Desligar: `voz.interromper_fala: false`. (Truque: um segundo reconhecedor com vocabulário mínimo escuta durante a fala; o eco da voz dele não dispara nada.)
- **Escrever em documentos existentes**:
  - *"adiciona ovos na lista de compras"* → **`acrescentar_ao_arquivo`** (acrescenta no fim, nunca apaga nada; funciona em texto e **.docx**).
  - *"troca leite por leite desnatado na lista"* → **`substituir_no_arquivo`** (trecho exato; **pede confirmação**).
  - *"põe 500 na célula B2 da planilha vendas"* → **`escrever_celula`** (.xlsx; números viram números de verdade; **pede confirmação**).

## Controle do computador (v0.6) 🖥️
O Jarvis agora controla a própria máquina:

- **Fechar programas** — *"Jarvis, fecha o Spotify"*, *"fecha o Chrome"*. O fechamento é **suave** (o app pode perguntar se quer salvar); ele só **força** se você mandar explicitamente (*"força o fechamento"*).
- **Volume do Windows** — *"põe o volume em 30"*, *"aumenta o som"*, *"abaixa um pouco"*, *"mudo"*, *"tira do mudo"*, *"em quanto tá o volume?"*.
- **Desligar / reiniciar / suspender** — *"Jarvis, desliga o computador"*. É ação **destrutiva**: ele pergunta *"Confirma, senhor?"* e só executa com o seu **"sim"** (e espera 5 s para terminar de falar).
- Ele **nunca fecha** processos do sistema nem a si mesmo.

## Ouvindo melhor com barulho de fundo (v0.6) 🔊
- **Ganho adaptativo (AGC)** — o ganho fixo do microfone (15x) fazia a fala **saturar** quando havia barulho de fundo, e o áudio distorcido confundia o reconhecimento. Agora o ganho se adapta sozinho: sobe quando está silencioso, despenca na hora quando o som estoura. `microfone.agc: false` volta ao fixo.
- **Palmas com análise espectral** — um pico de volume só conta como palma se tiver **cara de palma** (transiente curto com energia nos agudos); voz, música e TV são rejeitadas. Calibre com o **`Medir Volume.bat`** (mostra `agudos` e `crista` de cada pico) e ajuste `deteccao.min_agudos` / `min_crista`.
- **Poda automática da memória** — quando `memoria.json` passa de 100 fatos, os antigos são **resumidos** pelo Claude (não mais descartados).
- **xlsx / pdf / docx** — *"o que diz o contrato ponto pdf?"*, *"na planilha vendas ponto xlsx, qual produto vendeu mais?"* — além do CSV, ele lê PDF, Word e Excel.
- **Spotify sem resposta falsa** — quando a rede falhava no meio do comando, a música tocava mas o Jarvis respondia como se tivesse falhado; agora ele **confere o player** antes de declarar erro.

Seu assistente de desktop. Sempre ouvindo, em três camadas:

- **Duas palmas** → abre aplicativos, abas do Chrome e ele responde falando.
- **Comandos fixos por voz** (offline, grátis, instantâneos) → *"Jarvis, abra o navegador"*, *"abra tudo"*, *"pode descansar"*...
- **🧠 Pedidos livres → Claude (v0.3)** → o que não for comando fixo vai para a IA, que interpreta, executa e responde com voz gerada na hora:
  - *"Jarvis, toca Bohemian Rhapsody no Spotify"* → abre o Spotify já na música
  - *"Jarvis, põe um vídeo de lofi no YouTube"* → abre direto o primeiro vídeo
  - *"Jarvis, abre a calculadora"*, *"pesquisa X no Google"*, ou só conversar

O reconhecimento de fala é **offline** (Vosk, pt-BR). O cérebro (Claude) precisa de **internet + `ANTHROPIC_API_KEY`** — sem eles, o Jarvis segue funcionando no modo v0.2.

## Arquivos e dados por voz (v0.5) 📁
O Jarvis agora mexe nos seus arquivos:

- *"Jarvis, cria um arquivo compras ponto txt na área de trabalho com pão, leite e ovos"*
- *"o que está escrito no arquivo compras?"* / *"lista o que tem na pasta downloads"* / *"procura o meu currículo"*
- *"move a foto da praia dos downloads para imagens"* / *"apaga o rascunho do desktop"*
- *"na planilha vendas ponto csv, qual produto vendeu mais?"* (análise de CSV: totais, médias, valores mais comuns)

**Travas de segurança:**
- Ele só acessa **as suas pastas** (Área de Trabalho, Documentos, Downloads, Imagens, Músicas, Vídeos). Para liberar outra, adicione o caminho em `config.json` → `arquivos.pastas_extras`.
- **Apagar vai para a Lixeira** (dá para recuperar), nunca é definitivo.
- **Apagar e mover pedem confirmação**: ele pergunta *"Confirma, senhor?"* e só executa se você disser **"sim"/"confirmo"**; "não" ou silêncio cancelam.

E em pedidos demorados (pesquisas na web etc.), ele avisa *"Ainda trabalhando nisso, senhor"* a cada 15 s (`voz.aviso_processando_seg`) — silêncio não é mais travamento.

## Confiabilidade e controle (v0.4.2) 🛡️
- **"Jarvis, cancela"** — aborta um pedido no meio do processamento (também: "pare").
- **"Jarvis, quanto gastei hoje?"** — ele acompanha o custo da API por dia (`dados/custos.json`) e responde em reais (câmbio em `cerebro.cambio_brl`). Períodos: hoje, ontem, semana, mês, total.
- **Supervisor** — o `Iniciar Jarvis.bat` sobe um supervisor que **reinicia o Jarvis sozinho se ele cair**.
- **Iniciar com o Windows** — rode **`Instalar Inicializacao.bat`** uma vez (desfaz com o `Remover Inicializacao.bat`).

## Memória e aprendizado (v0.4) 💾
O Jarvis agora **aprende e lembra entre sessões**:

- **Memória** (`dados/memoria.json`) — *"Jarvis, lembra que minha playlist de foco é X"*. Ele também memoriza sozinho o que descobre (caminhos de programas, soluções). Tudo entra no prompt do Claude a cada pedido. *"Jarvis, esquece isso"* remove.
- **Aprende com falhas** — se não conseguir abrir um programa, ele **varre o Menu Iniciar** atrás do executável e memoriza o caminho. Se não souber algo, **pesquisa na web** (Bing/DuckDuckGo) e pode ler páginas.
- **Atalhos aprendidos** — *"Jarvis, quando eu disser 'abra o lol', abre o League of Legends"* → vira comando fixo no `config.json` (instantâneo, sem custo de API) e já vale sem reiniciar.
- **Habilidades (auto-extensão)** — quando nenhuma ferramenta resolve, ele pode **escrever um script Python** novo em `dados/habilidades/`. ⚠️ **Nada roda sem sua aprovação**: confira o arquivo e diga *"Jarvis, aprovar habilidade"*. Sem isso, o script fica bloqueado.

## Spotify de verdade (v0.4.1) 🎵
Com a Web API configurada, *"Jarvis, toca Bohemian Rhapsody"* **dá play direto** (nada de apertar botão), e funcionam por voz: **pausar, continuar, pular, voltar e "que música é essa"**. Pedidos de artista/álbum/playlist também tocam direto.

**Configurar (uma vez, precisa de conta Premium):**
1. Crie um app em [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → *Create app* → em **Redirect URIs** cole `http://127.0.0.1:8917/callback` → marque **Web API**.
2. Copie o **Client ID** do app e cole em `config.json` → `"spotify"` → `"client_id"`.
3. Rode **`Autorizar Spotify.bat`** — o navegador abre, você autoriza, pronto (o token fica em `dados/spotify_token.json` e se renova sozinho).

Sem configurar, nada quebra: o Jarvis abre a busca como antes. Se o Spotify estiver fechado, ele abre o app e espera antes de dar play.

## Transcrição na nuvem (v0.5.1) ☁️
Para entender **qualquer palavra** com precisão máxima, o Jarvis pode transcrever as frases na nuvem (**Groq**, Whisper large-v3 — o irmão gigante do Whisper local): erra muito menos em nomes próprios e inglês, responde em ~1 s e é **grátis no volume de uso pessoal**.

**Configurar (uma vez):**
1. Crie uma chave em [console.groq.com/keys](https://console.groq.com/keys) (conta gratuita).
2. No **seu** PowerShell: `setx GROQ_API_KEY "gsk_..."`
3. Reinicie o Jarvis — o console mostra `Nuvem (Groq): ativa`.

Privacidade: **só a frase do comando** vai para a nuvem (a escuta contínua e a ativação "Jarvis" continuam 100% offline). Sem chave ou sem internet, ele cai sozinho para o Whisper local — nada quebra. Desligar: `voz.stt_nuvem.ativo: false`.

## Palavras em inglês (v0.3.1) 🌎
O Vosk pt-BR não conhece palavras em inglês — "github" virava *"jeito rubi"*. Agora, quando nenhum comando fixo casa, a frase é **re-transcrita com o Whisper** (offline, multilíngue), que entende GitHub, Spotify, videogame etc. A ativação ("Jarvis") continua com o Vosk, e comandos em português seguem instantâneos.

- **`voz.whisper.ativo`** — `false` desliga (volta ao Vosk puro). **`modelo`**: `tiny` | `base` | `small` (atual; ~1–2 s por frase).
- **`vocabulario`** — as palavras que você costuma falar. Entram como dica para o Whisper **e** como glossário para o Claude corrigir nomes distorcidos. **Adicione as suas!**
- **`voz.correcoes`** — fallback sem Whisper: mapeia a transcrição errada do Vosk para a palavra certa (ex.: `"jeito rubi": "github"`).

## O cérebro (config.json → "cerebro")
- **`ativo`** — `false` desliga a IA (volta ao v0.2 puro).
- **`modelo`** — `claude-sonnet-5` (atual) | `claude-haiku-4-5` (mais rápido/barato) | `claude-opus-4-8` (mais capaz).
- A IA entende transcrições distorcidas ("bó rêmian répisode") e corrige sozinha.
- Custo: paga por uso (~centavos por comando). O histórico curto (6 trocas) permite emendas: *"toca outra do mesmo artista"*.

## Comandos de voz disponíveis (config.json → "voz" → "comandos")
| Diga... | Ação |
|---------|------|
| "abra o navegador" | Abre as abas do `config.json` no Chrome |
| "abra os aplicativos" | Abre os programas do `config.json` |
| "abra tudo" / "bom dia" / "modo trabalho" | Tudo de uma vez (igual às palmas) |
| "abra o Obsidian" | Abre o Obsidian |
| "abra o editor" / "vs code" | Abre o VS Code |
| "aprovar habilidade" | Aprova a última habilidade criada pelo cérebro (v0.4) |
| "pode descansar" / "encerrar" / "boa noite" | Desliga o Jarvis (ele se despede) |

> Atalhos que você ensinar (*"quando eu disser X..."*) aparecem aqui embaixo no `config.json` automaticamente.

## Estrutura de pastas
```
Jarvis/
├── *.bat                → atalhos de uso diário (iniciar, parar, calibrar...)
├── config.json          → a SUA configuração (crie a partir do config.exemplo.json)
├── nucleo/              → o código do Jarvis
├── ferramentas/         → scripts de apoio (gerar vozes, calibrar, autorizar Spotify)
├── dados/               → o que o Jarvis aprende e gasta (criado em uso; fora do git)
├── modelo-vosk/         → modelo de fala pt-BR (baixar na instalação)
├── vozes/  respostas/   → áudios das falas (gerados pelo gerar_vozes.py)
```

## Arquivos
- **`nucleo/assistente.py`** — o programa principal (palmas + voz + integração do cérebro).
- **`nucleo/cerebro.py`** — a IA (Claude + 28 ferramentas: Spotify, YouTube, programas, sites, memória, pesquisa, atalhos, habilidades, gastos, arquivos, edição de documentos, volume, fechar apps e desligar).
- **`nucleo/aprendizado.py`** — **(v0.4)** memória, pesquisa web, atalhos e habilidades.
- **`nucleo/arquivos.py`** — **(v0.5)** listar, procurar, criar, ler, mover, apagar (Lixeira) e analisar CSV, restrito às suas pastas.
- **`nucleo/custos.py`** / **`dados/custos.json`** — **(v0.4.2)** registro do gasto diário com a API.
- **`nucleo/supervisor.py`** — **(v0.4.2)** mantém o Jarvis vivo (reinicia se cair).
- **`nucleo/spotify_api.py`** — **(v0.4.1)** play direto e controles via Web API (token em `dados/spotify_token.json`).
- **`dados/memoria.json`** — **(v0.4)** o que o Jarvis aprendeu (criado no primeiro uso; pode editar à mão).
- **`dados/habilidades/`** — **(v0.4)** scripts que o Jarvis escreveu; `habilidades.json` marca o que está aprovado.
- **`config.json`** — o que abrir, frases dos comandos, palavras de ativação, sensibilidade, modelo da IA.
- **`ferramentas/gerar_vozes.py`** — gera as falas do Jarvis (`vozes/` e `respostas/`) com edge-tts. Rode de novo se editar as frases.
- **`ferramentas/medir_volume.py`** — calibra a sensibilidade das palmas.
- **`modelo-vosk/`** — modelo de reconhecimento de fala pt-BR (não mexer). O modelo do Whisper baixa sozinho na primeira vez (fica no cache do usuário).
- **`Iniciar Jarvis.bat`** — inicia em **segundo plano** (sem janela).
- **`Iniciar Jarvis (console).bat`** — inicia **com janela**, para calibrar (mostra o que ele ouve).
- **`Parar Jarvis.bat`** — encerra o Jarvis que roda em segundo plano.

> Os `.bat` usam o Python 3.10 fixo em `C:\Python310` (onde estão as dependências).

## Instalação (primeira vez)
1. **Python 3.10** em `C:\Python310` (os `.bat` usam esse caminho fixo) e as dependências:
   ```
   C:\Python310\python.exe -m pip install -r requirements.txt
   ```
2. **Modelo de voz (Vosk pt-BR)** — baixe o modelo pt-BR em [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models), extraia e renomeie a pasta para **`modelo-vosk/`** na raiz do projeto.
3. **Configuração** — copie `config.exemplo.json` para **`config.json`** e edite (sites, aplicativos, comandos).
4. **Vozes do Jarvis** — gere os áudios das falas (`vozes/` e `respostas/`):
   ```
   C:\Python310\python.exe ferramentas\gerar_vozes.py
   ```
5. **Cérebro (opcional)** — defina a variável de ambiente `ANTHROPIC_API_KEY` para os pedidos livres via Claude. Groq (`GROQ_API_KEY`, transcrição na nuvem) e Spotify são opcionais — veja as seções acima.

## Como usar
1. Clique duas vezes em **`Iniciar Jarvis.bat`** (nada aparece — ele fica ouvindo em segundo plano).
2. Bata **duas palmas** ou diga **"Jarvis, abra tudo"**.
3. Para parar: **`Parar Jarvis.bat`** ou diga **"Jarvis, pode descansar"**.

## Calibrando a voz 🎙️
O modelo entende "Jarvis" como outras coisas (*"james"*, *"já disse"*, *"jardins"*, *"já fiz"*...). Por isso a ativação usa **casamento aproximado**: qualquer trecho que comece com "j", termine em som de s/z e pareça com "jarvis" ativa o assistente.

Se ainda assim ele não responder (ou ativar sozinho demais):

1. Abra o **`Iniciar Jarvis (console).bat`**.
2. Diga "Jarvis" e veja o que aparece em `[voz] ouvi: "..."`.
3. Ajuste em `config.json` → `voz`:
   - **`similaridade_ativacao`** (0 a 1, padrão 0.5) — **diminua** se não responde; **aumente** se ativa sozinho.
   - Ou acrescente a grafia exata em **`palavras_ativacao`** (sempre funciona, ignora a similaridade).

O mesmo vale para os comandos: as `frases` casam por trecho contido no que foi ouvido (acentos são ignorados).

## Calibrando as palmas 👏
Se não detectar ou disparar sozinho, rode **`Medir Volume.bat`**, bata palmas e veja o `pico`. Ajuste no `config.json`:
- **`limite_volume`** — aumente se dispara sozinho; diminua se não detecta (atual: 0.40).
- **`intervalo_min_seg` / `intervalo_max_seg`** — janela entre as duas palmas.
- **`cooldown_seg`** — espera após disparar.

## Personalizando (config.json)
- **`abas_navegador`** — sites para abrir no Chrome.
- **`aplicativos`** — programas a abrir (caminho completo).
- **`audio_pasta`** — pasta de falas sorteadas nas palmas (`vozes/`).
- **`voz.comandos`** — cada comando tem `frases` (o que você diz), `acao` (`abas` | `apps` | `tudo` | `abrir` | `sair`), `alvo` (para `abrir`) e `resposta` (o .wav que ele fala).

## Próximos passos (rumo ao Jarvis completo)
- Controlar luzes inteligentes (a lightbar atual é USB "burra", sem protocolo — precisaria de uma smart plug/lâmpada Wi-Fi; com uma Tuya/Govee/Hue em mãos, a integração entra aqui).
- Depois de interromper com "Jarvis!", aproveitar o resto da frase como o próprio pedido (hoje ele corta e abre a escuta).
- Timers e lembretes por voz ("Jarvis, me lembra em 20 minutos").
