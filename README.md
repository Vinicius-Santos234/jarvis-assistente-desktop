# Jarvis

Assistente de voz para desktop Windows, em português. Fica sempre ouvindo — o reconhecimento de fala é **100% offline** — e executa tarefas reais no computador por comando de voz.

> *"Jarvis, toca Bohemian Rhapsody no Spotify"* · *"cria uma lista de compras na área de trabalho"* · *"abaixa o volume e fecha o Chrome"* · *"quanto gastei hoje?"*

## Como funciona

Três camadas, da mais rápida para a mais inteligente:

1. **Duas palmas** 👏 — abre seus sites e aplicativos favoritos. A detecção usa análise espectral para não disparar com voz, música ou TV.
2. **Comandos fixos por voz** — offline, instantâneos e grátis (Vosk pt-BR): *"Jarvis, abra o navegador"*, *"pode descansar"*...
3. **Pedidos livres → IA** — o que não casar com um comando fixo vai para o Claude, que interpreta a intenção (mesmo com transcrição distorcida), executa uma de suas **28 ferramentas** e responde com voz gerada na hora.

Sem chave de API ou sem internet, nada quebra: as camadas offline continuam funcionando.

## O que ele faz

- **Música** — play direto no Spotify (pausar, pular, "que música é essa?") via Web API
- **Arquivos** — criar, ler, procurar, mover e apagar (sempre pela Lixeira); analisar CSV/Excel; ler PDF e Word; escrever em listas e planilhas
- **Computador** — volume do Windows, fechar programas, desligar/reiniciar/suspender
- **Web** — abrir sites, vídeos no YouTube, pesquisas no Google
- **Memória** — aprende fatos (*"lembra que..."*), atalhos novos por voz e até escreve scripts próprios (habilidades)
- **Conversa natural** — modo conversa emenda pedidos sem repetir "Jarvis"; dizer "Jarvis!" por cima da fala dele o interrompe na hora

**Travas de segurança:** ações destrutivas (apagar, mover, desligar, editar planilha) pedem *"Confirma, senhor?"* e só executam com o seu "sim". O acesso a arquivos é restrito às suas pastas de usuário. Habilidades novas só rodam depois de aprovadas por voz. Apagar nunca é definitivo — vai para a Lixeira.

## Instalação

1. **Python 3.10** em `C:\Python310` (os `.bat` usam esse caminho fixo) e as dependências:
   ```
   C:\Python310\python.exe -m pip install -r requirements.txt
   ```
2. **Modelo de voz** — baixe o modelo pt-BR do Vosk em [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models), extraia e renomeie a pasta para `modelo-vosk/` na raiz do projeto.
3. **Configuração** — copie `config.exemplo.json` para `config.json` e edite (sites, aplicativos, comandos). O arquivo é autodocumentado.
4. **Vozes** — gere os áudios das falas:
   ```
   C:\Python310\python.exe ferramentas\gerar_vozes.py
   ```
5. **Cérebro (opcional)** — defina a variável de ambiente `ANTHROPIC_API_KEY` para habilitar os pedidos livres via Claude. Opcionais também: `GROQ_API_KEY` (transcrição na nuvem, mais precisa) e Spotify Premium (play direto — Client ID no `config.json` + `Autorizar Spotify.bat`).
6. **Voz premium (opcional)** — defina `OPENAI_API_KEY` para o Jarvis falar com a voz `onyx` da OpenAI (grave, timbre de locutor; ~US$ 0,03 por minuto falado) e rode o `gerar_vozes.py` de novo para regravar as falas fixas. Sem a chave, ele fala com o edge-tts (grátis). Voz, modelo e estilo ficam na seção `tts` do `config.json`.

## Uso

| Ação | Como |
|------|------|
| Iniciar (segundo plano) | `Iniciar Jarvis.bat` |
| Iniciar com janela (para calibrar) | `Iniciar Jarvis (console).bat` |
| Parar | `Parar Jarvis.bat` ou *"Jarvis, pode descansar"* |
| Iniciar junto com o Windows | `Instalar Inicializacao.bat` (uma vez) |
| Calibrar palmas / microfone | `Medir Volume.bat` / `Medir Voz.bat` |

Se ele não responder ao "Jarvis" (ou ativar sozinho), abra o console, veja o que aparece em `[voz] ouvi:` e ajuste `voz.similaridade_ativacao` no `config.json`.

## Estrutura do projeto

```
Jarvis/
├── *.bat                → atalhos de uso diário (iniciar, parar, calibrar...)
├── config.json          → a SUA configuração (crie a partir do config.exemplo.json)
├── nucleo/              → o código do assistente
├── ferramentas/         → scripts de apoio (gerar vozes, calibrar, autorizar Spotify)
├── dados/               → memória, custos e tokens (criado em uso; fora do git)
├── modelo-vosk/         → modelo de fala pt-BR (baixado na instalação)
└── vozes/ respostas/    → áudios das falas (gerados na instalação)
```

## Custos e privacidade

- A escuta contínua e a palavra de ativação rodam **inteiramente no seu computador**. Com a transcrição na nuvem ativada, **só a frase do comando** é enviada (Groq, grátis no uso pessoal); sem ela, tudo fica local (Whisper).
- O cérebro usa a API do Claude, **paga por uso** (centavos por comando). A voz premium (OpenAI) também é paga por uso (~US$ 0,03/min falado) e cai sozinha para o edge-tts grátis se a chave faltar ou a API falhar. O Jarvis registra o gasto diário de tudo — pergunte *"Jarvis, quanto gastei hoje?"*.

## Roadmap

- [ ] Aproveitar o resto da frase ao interromper ("Jarvis, para **e toca outra**")
- [ ] Timers e lembretes por voz
- [ ] Luzes inteligentes (aguardando hardware compatível)
- [ ] **Versão 100% open source e sem custos** — substituir os serviços pagos (Claude, Groq) por modelos abertos rodando localmente, para que qualquer pessoa use o Jarvis completo de graça

## Licença

[MIT](LICENSE) — use, modifique e distribua livremente, mantendo o crédito.
