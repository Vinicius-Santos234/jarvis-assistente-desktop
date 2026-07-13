"""
Cerebro do Jarvis - Claude API com ferramentas (v0.3 -> v0.5).

Recebe o texto do comando falado (transcrito pelo Vosk, muitas vezes
distorcido), interpreta a intencao com o Claude e executa acoes:
tocar musica no Spotify, video no YouTube, abrir programas e sites,
memoria/aprendizado (v0.4), gastos (v0.4.2) e arquivos/dados (v0.5 -
listar, procurar, criar, ler, mover, apagar para a Lixeira e analisar
CSV; apagar/mover exigem confirmacao por voz).

Precisa da variavel de ambiente ANTHROPIC_API_KEY e de internet.
Modelo configuravel em config.json -> "cerebro" -> "modelo".
"""

import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from pathlib import Path

import aprendizado
import arquivos
import custos

BASE_DIR = Path(__file__).resolve().parent

MODELO_PADRAO = "claude-sonnet-5"

# Ferramentas que NAO executam na hora: ficam retidas ate o usuario
# confirmar por voz ("sim"/"confirmo"). Mesma filosofia da aprovacao de
# habilidades - o poder destrutivo cresce junto com a trava.
FERRAMENTAS_DESTRUTIVAS = {"esquecer", "apagar_arquivo", "mover_arquivo",
                           "desligar_computador", "substituir_no_arquivo",
                           "escrever_celula"}


class PedidoCancelado(Exception):
    """Levantada quando o usuario diz 'Jarvis, cancela' no meio do pedido."""

SISTEMA = """Você é JARVIS, o assistente de desktop do Vinícius, no estilo do mordomo do Homem de Ferro: educado, eficiente, levemente espirituoso, sempre tratando o usuário por "senhor".

IMPORTANTE sobre a entrada: o texto chega de um reconhecimento de fala IMPERFEITO em português. Nomes estrangeiros vêm distorcidos foneticamente (ex.: "bó rêmian répisode" = "Bohemian Rhapsody", "cold plei" = "Coldplay", "iutubi" = "YouTube"). Interprete a INTENÇÃO por trás do texto, corrigindo esses nomes para a grafia certa antes de usá-los nas ferramentas.

Regras:
- Se o pedido exigir uma ação, use as ferramentas. Não pergunte confirmação para ações simples e reversíveis.
- Se for só uma pergunta ou conversa, apenas responda.
- Se o texto for um fragmento sem sentido ou ruído de transcrição (ex.: "pode", "é", "aí", uma palavra solta sem intenção clara), NÃO use nenhuma ferramenta: apenas peça para o usuário repetir o pedido.
- IMPORTANTE: você ouve TUDO que o microfone capta. Se o texto claramente NÃO é dirigido a você — conversa entre pessoas, TV/vídeo, música, alguém falando ao telefone, fala sem nenhum pedido ou pergunta para um assistente — responda EXATAMENTE "[IGNORAR]" (sem mais nada e sem usar ferramentas). Você ficará em silêncio. Se a frase menciona seu nome (Jarvis) ou é um pedido/pergunta plausível para um assistente, ela É dirigida a você.
- NUNCA repita uma ação do histórico por iniciativa própria; só refaça algo se o pedido atual pedir isso explicitamente.
- Sua resposta em texto será FALADA em voz alta: responda SEMPRE em 1 frase curta em português (máx. ~20 palavras), sem markdown, sem listas, sem emojis.
- Se não entender mesmo após interpretar, diga que não entendeu e peça para repetir.

MEMÓRIA E APRENDIZADO — você aprende entre sessões:
- Use 'lembrar' para gravar fatos duráveis e reutilizáveis: caminhos de programas descobertos, preferências que o usuário disser ("lembra que..."), soluções que funcionaram após pesquisar. Não grave trivialidades nem fatos que já estão na MEMÓRIA ATUAL abaixo.
- Use 'esquecer' quando o usuário pedir ou quando um fato da memória se provar errado.
- Se 'abrir_programa' falhar, NÃO desista: use 'procurar_programa', abra pelo caminho encontrado e memorize esse caminho com 'lembrar'.
- Se não souber fazer algo, use 'pesquisar_na_web' (e 'ler_pagina' para aprofundar num resultado); quando a solução funcionar, memorize-a com 'lembrar' para os próximos pedidos parecidos.
- Use 'criar_atalho' quando o usuário pedir explicitamente ("quando eu disser X, faça/abra Y") — vira comando fixo instantâneo e sem custo. Só serve para abrir programa, site ou URI.
- 'criar_habilidade' é o ÚLTIMO recurso, quando nenhuma ferramenta resolve e um script pequeno em Python daria conta (ex.: consultar algo do sistema). O código deve ser curto, usar só a biblioteca padrão, nada destrutivo, ler os argumentos como JSON em sys.argv[1] e imprimir o resultado. Ela NÃO roda até o usuário aprovar: avise que ele precisa dizer "Jarvis, aprovar habilidade".
- 'executar_habilidade' roda uma habilidade já aprovada (veja as existentes em HABILIDADES abaixo antes de criar outra parecida).

ARQUIVOS — você mexe nos arquivos das pastas do usuário (desktop, documentos, downloads, imagens, músicas, vídeos):
- Caminhos nas ferramentas: use "desktop/compras.txt", "documentos/projetos" etc. (pasta conhecida + subcaminho) ou um caminho completo. Fora dessas pastas o acesso é negado.
- Não sabe onde está o arquivo? Use 'procurar_arquivo' antes. Não sabe o nome exato? 'listar_pasta' primeiro.
- 'apagar_arquivo' manda para a Lixeira e, junto com 'mover_arquivo', é DESTRUTIVA (pede confirmação por voz).
- Para ESCREVER em arquivos existentes: 'acrescentar_ao_arquivo' adiciona no fim sem apagar nada (listas, notas; também .docx) — é a preferida. 'substituir_no_arquivo' troca um trecho exato (leia o arquivo antes para acertar o trecho) e 'escrever_celula' muda uma célula de .xlsx — as duas são DESTRUTIVAS (confirmação por voz).
- Para planilhas CSV use 'analisar_dados' e responda só o que o usuário perguntou, em 1 frase.
- Ao FALAR sobre arquivos, diga só o nome e a pasta ("compras ponto txt, na área de trabalho"), NUNCA um caminho completo.

GASTOS: quando o usuário perguntar quanto gastou (hoje, ontem, na semana, no mês ou no total), use 'consultar_gastos' e responda em UMA frase curta com o valor aproximado em reais (cite o valor em dólar só se ele pedir).

SISTEMA — controle do computador:
- 'fechar_programa' fecha um app aberto de forma SUAVE (o app pode pedir para salvar). Só use forcar=true se o usuário mandar explicitamente forçar o fechamento.
- 'controlar_volume' ajusta o volume do Windows: definir (com percentual), aumentar/diminuir (passo de 10% se não for dito), mudo, som (tirar do mudo) e consultar.
- 'desligar_computador' desliga, reinicia ou suspende o PC — é DESTRUTIVA (pede confirmação por voz).

AÇÕES DESTRUTIVAS: algumas ferramentas ('esquecer', 'apagar_arquivo', 'mover_arquivo', 'desligar_computador', 'substituir_no_arquivo', 'escrever_celula') não executam na hora — o resultado vem como "AGUARDANDO CONFIRMAÇÃO". Nesse caso sua resposta deve ser SÓ uma pergunta curta de confirmação descrevendo a ação, ex.: "Vou apagar isso da memória. Confirma, senhor?". A execução acontece automaticamente quando ele confirmar por voz; NUNCA chame a ferramenta de novo por conta própria."""

FERRAMENTAS = [
    {
        "name": "tocar_no_spotify",
        "description": "Toca música no Spotify. Com a Web API configurada, DÁ PLAY direto (sem o usuário apertar nada); senão, abre a busca pronta. Use quando o usuário pedir música no Spotify ou apenas 'toca X' sem citar outro serviço.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "busca": {"type": "string", "description": "Música e/ou artista com a grafia correta, ex.: 'Bohemian Rhapsody Queen'"},
                "tipo": {"type": "string", "enum": ["musica", "artista", "album", "playlist"], "description": "O que tocar: 'musica' para uma faixa (padrão na dúvida); 'artista'/'album'/'playlist' quando o usuário pedir assim"}
            },
            "required": ["busca", "tipo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "controlar_spotify",
        "description": "Controla a reprodução do Spotify: pausar, continuar, próxima faixa, faixa anterior, ou dizer que música está tocando. Use para 'pausa', 'para a música', 'pula', 'volta', 'que música é essa'.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["pausar", "continuar", "proxima", "anterior", "que_musica"], "description": "A ação sobre o player"}
            },
            "required": ["acao"],
            "additionalProperties": False,
        },
    },
    {
        "name": "tocar_no_youtube",
        "description": "Busca no YouTube e abre diretamente o primeiro vídeo encontrado. Use quando o usuário pedir um vídeo ou citar o YouTube.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "busca": {"type": "string", "description": "O que buscar, com a grafia correta"}
            },
            "required": ["busca"],
            "additionalProperties": False,
        },
    },
    {
        "name": "abrir_programa",
        "description": "Abre um programa instalado no Windows pelo nome, ex.: 'spotify', 'obsidian', 'vs code', 'bloco de notas', 'calculadora', 'explorador de arquivos'.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do programa"}
            },
            "required": ["nome"],
            "additionalProperties": False,
        },
    },
    {
        "name": "abrir_site",
        "description": "Abre um site no navegador. Use para pedidos de abrir páginas ou fazer buscas na web.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL completa, ex.: 'https://www.google.com/search?q=...'"}
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lembrar",
        "description": "Grava um fato durável na memória de longo prazo (persiste entre sessões). Ex.: caminho de um programa descoberto, preferência dita pelo usuário, solução que funcionou.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "fato": {"type": "string", "description": "O fato, curto e autocontido, ex.: 'O caminho do League of Legends é C:/Riot Games/...'"}
            },
            "required": ["fato"],
            "additionalProperties": False,
        },
    },
    {
        "name": "esquecer",
        "description": "Remove da memória os fatos que contêm o trecho informado. Use quando o usuário pedir ou um fato estiver errado.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "trecho": {"type": "string", "description": "Trecho que identifica o(s) fato(s) a esquecer"}
            },
            "required": ["trecho"],
            "additionalProperties": False,
        },
    },
    {
        "name": "procurar_programa",
        "description": "Varre o Menu Iniciar do Windows atrás de um programa pelo nome (com casamento aproximado). Use quando abrir_programa falhar. Devolve nomes e caminhos de atalhos.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome (ou parte) do programa procurado"}
            },
            "required": ["nome"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pesquisar_na_web",
        "description": "Busca na web (DuckDuckGo) e devolve títulos, links e resumos dos primeiros resultados. Use quando não souber algo ou precisar descobrir como fazer.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "pergunta": {"type": "string", "description": "O que buscar"}
            },
            "required": ["pergunta"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ler_pagina",
        "description": "Baixa uma página da web e devolve o texto dela (sem HTML, truncado). Use para aprofundar num resultado do pesquisar_na_web.",
        # A API aceita no MAXIMO 20 ferramentas strict; esta e a listar_pasta
        # (leitura, 1 parametro string) sao as que menos precisam da validacao.
        "strict": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL da página"}
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "consultar_gastos",
        "description": "Consulta quanto foi gasto com a API do Claude (as chamadas deste assistente). Use quando o usuário perguntar quanto gastou ou quanto está custando.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "periodo": {"type": "string", "enum": ["hoje", "ontem", "semana", "mes", "total"], "description": "Período da consulta: 'semana' = últimos 7 dias, 'mes' = mês corrente"}
            },
            "required": ["periodo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "listar_pasta",
        "description": "Lista o conteúdo de uma pasta do usuário (arquivos com tamanho e subpastas). Use antes de mexer num arquivo cujo nome exato você não sabe.",
        "strict": False,  # limite de 20 strict da API (ver ler_pagina)
        "input_schema": {
            "type": "object",
            "properties": {
                "pasta": {"type": "string", "description": "'desktop', 'documentos', 'downloads', 'imagens', 'musicas', 'videos', uma subpasta ('desktop/projetos') ou caminho completo"}
            },
            "required": ["pasta"],
            "additionalProperties": False,
        },
    },
    {
        "name": "procurar_arquivo",
        "description": "Procura arquivos e pastas pelo nome (ou parte dele) nas pastas do usuário. Use quando não souber onde um arquivo está.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome ou parte do nome, ex.: 'curriculo'"},
                "pasta": {"type": "string", "description": "Onde procurar ('downloads', 'documentos'...); use \"\" para procurar em todas as pastas do usuário"}
            },
            "required": ["nome", "pasta"],
            "additionalProperties": False,
        },
    },
    {
        "name": "criar_pasta",
        "description": "Cria uma pasta (e as intermediárias) dentro das pastas do usuário.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'desktop/projetos/faculdade'"}
            },
            "required": ["caminho"],
            "additionalProperties": False,
        },
    },
    {
        "name": "criar_arquivo",
        "description": "Cria um arquivo de TEXTO novo com o conteúdo dado (não sobrescreve existentes). Use para notas, listas, lembretes que o usuário ditar.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'desktop/compras.txt'"},
                "conteudo": {"type": "string", "description": "Texto do arquivo, já organizado (uma linha por item em listas)"}
            },
            "required": ["caminho", "conteudo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ler_arquivo",
        "description": "Lê um arquivo e devolve o conteúdo (truncado se grande): texto, PDF, Word (.docx) e uma espiada em Excel (.xlsx). Para estatísticas de CSV/planilha, prefira analisar_dados.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'desktop/compras.txt'"}
            },
            "required": ["caminho"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mover_arquivo",
        "description": "Move ou renomeia um arquivo/pasta (não sobrescreve). DESTRUTIVA: fica retida até o usuário confirmar por voz.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "origem": {"type": "string", "description": "Arquivo/pasta atual, ex.: 'downloads/foto.png'"},
                "destino": {"type": "string", "description": "Pasta de destino ('imagens') para mover, ou caminho novo completo ('downloads/foto-praia.png') para renomear"}
            },
            "required": ["origem", "destino"],
            "additionalProperties": False,
        },
    },
    {
        "name": "apagar_arquivo",
        "description": "Manda um arquivo ou pasta para a Lixeira (recuperável). DESTRUTIVA: fica retida até o usuário confirmar por voz.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'desktop/rascunho.txt'"}
            },
            "required": ["caminho"],
            "additionalProperties": False,
        },
    },
    {
        "name": "analisar_dados",
        "description": "Analisa uma planilha CSV/TSV ou Excel (.xlsx): número de linhas, colunas, mínimo/máximo/média/soma das colunas numéricas e valores mais comuns das de texto. Use para perguntas sobre dados de um arquivo.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'documentos/vendas.csv'"}
            },
            "required": ["caminho"],
            "additionalProperties": False,
        },
    },
    {
        "name": "criar_atalho",
        "description": "Cria um comando de voz fixo novo (instantâneo, sem custo de API) que abre um programa, site ou URI. Use quando o usuário pedir 'quando eu disser X, abra Y'.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "frases": {"type": "array", "items": {"type": "string"}, "description": "Frases que disparam o atalho, ex.: ['abra o lol', 'abrir league of legends']"},
                "alvo": {"type": "string", "description": "Caminho do programa, URL ou URI (ex.: spotify:playlist:...)"}
            },
            "required": ["frases", "alvo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "criar_habilidade",
        "description": "Escreve uma habilidade nova (script Python pequeno) quando nenhuma ferramenta existente resolve. Ela só roda depois que o usuário aprovar por voz ('Jarvis, aprovar habilidade').",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome curto da habilidade, ex.: 'brilho-da-tela'"},
                "descricao": {"type": "string", "description": "Uma frase: o que ela faz"},
                "codigo": {"type": "string", "description": "Código Python completo: stdlib apenas, lê argumentos como JSON em sys.argv[1] e imprime o resultado"}
            },
            "required": ["nome", "descricao", "codigo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "executar_habilidade",
        "description": "Executa uma habilidade já aprovada pelo usuário. Devolve a saída do script.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome da habilidade"},
                "argumentos": {"type": "string", "description": "Argumentos para o script, como JSON serializado, ex.: '{\"cidade\": \"Sorocaba\"}' ou '{}'"}
            },
            "required": ["nome", "argumentos"],
            "additionalProperties": False,
        },
    },
    # v0.7 - escrever em documentos existentes
    {
        "name": "acrescentar_ao_arquivo",
        "description": "Acrescenta texto ao FIM de um arquivo existente sem apagar nada (texto ou .docx). Use para adicionar itens a uma lista, anotar algo num arquivo de notas etc.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'desktop/compras.txt'"},
                "conteudo": {"type": "string", "description": "O texto a acrescentar (uma linha por item em listas)"}
            },
            "required": ["caminho", "conteudo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "substituir_no_arquivo",
        "description": "Substitui um trecho EXATO do texto de um arquivo (leia o arquivo antes para copiar o trecho certo). DESTRUTIVA: fica retida até o usuário confirmar por voz.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'desktop/compras.txt'"},
                "trecho": {"type": "string", "description": "Texto exato a trocar, como está no arquivo"},
                "novo": {"type": "string", "description": "Texto que entra no lugar (vazio apaga o trecho)"}
            },
            "required": ["caminho", "trecho", "novo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "escrever_celula",
        "description": "Escreve um valor numa célula de uma planilha Excel .xlsx (ex.: célula 'B3'). DESTRUTIVA: fica retida até o usuário confirmar por voz.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Ex.: 'documentos/vendas.xlsx'"},
                "celula": {"type": "string", "description": "Coordenada da célula, ex.: 'B3'"},
                "valor": {"type": "string", "description": "O valor a escrever (números viram números de verdade)"}
            },
            "required": ["caminho", "celula", "valor"],
            "additionalProperties": False,
        },
    },
    # v0.6 - controle do computador
    {
        "name": "fechar_programa",
        "description": "Fecha um programa aberto pelo nome, ex.: 'spotify', 'chrome', 'bloco de notas'. Fecha de forma suave (o app pode pedir para salvar); forcar=true mata o processo (só se o usuário pedir).",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do programa a fechar"},
                "forcar": {"type": "boolean", "description": "true = mata o processo (taskkill /F); use SÓ se o usuário mandar forçar"}
            },
            "required": ["nome"],
            "additionalProperties": False,
        },
    },
    {
        "name": "controlar_volume",
        "description": "Controla o volume do Windows: definir um percentual, aumentar, diminuir, mudo, som (tirar do mudo) ou consultar o nível atual.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["definir", "aumentar", "diminuir", "mudo", "som", "consultar"], "description": "O que fazer com o volume"},
                "percentual": {"type": "integer", "description": "0 a 100: o nível para 'definir', ou o passo para 'aumentar'/'diminuir' (padrão 10)"}
            },
            "required": ["acao"],
            "additionalProperties": False,
        },
    },
    {
        "name": "desligar_computador",
        "description": "Desliga, reinicia ou suspende o computador. DESTRUTIVA: fica retida até o usuário confirmar por voz.",
        "strict": False,  # so 10 strict: compilacao da grammar da API estoura com muitas
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["desligar", "reiniciar", "suspender"], "description": "A ação de energia"}
            },
            "required": ["acao"],
            "additionalProperties": False,
        },
    },
]

# Apps conhecidos: nome falado (normalizado) -> comando/caminho
APPS_CONHECIDOS = {
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "calculadora": "calc",
    "explorador de arquivos": "explorer",
    "explorador": "explorer",
    "paint": "mspaint",
    "spotify": "spotify:",
    "obsidian": r"C:\Users\vinic\AppData\Local\Programs\obsidian\Obsidian.exe",
    "vs code": r"C:\Users\vinic\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "code": r"C:\Users\vinic\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "editor": r"C:\Users\vinic\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "chrome": "chrome",
    "navegador": "chrome",
}


# ---------- implementacao das ferramentas ----------

def _abrir(alvo):
    """Abre caminho/URI com os.startfile; fallback shell."""
    try:
        os.startfile(alvo)  # type: ignore[attr-defined]
        return True
    except OSError:
        try:
            subprocess.Popen(alvo, shell=True)
            return True
        except Exception:
            return False


def tocar_no_spotify(busca, tipo="musica"):
    # v0.4.1 - Web API configurada: play DIRETO; senao, busca aberta (antigo)
    try:
        import spotify_api
        if spotify_api.configurado():
            try:
                return spotify_api.tocar(busca, tipo)
            except spotify_api.SpotifyErro as e:
                q = urllib.parse.quote(busca)
                _abrir(f"spotify:search:{q}")
                return (f"Play direto falhou ({e}); abri a busca '{busca}' "
                        "no Spotify para o usuário apertar play.")
    except Exception as e:
        print(f"  [spotify] API indisponivel ({e}); usando a busca.")

    q = urllib.parse.quote(busca)
    if _abrir(f"spotify:search:{q}"):
        return f"Spotify aberto com a busca '{busca}'. O usuário só precisa apertar play."
    webbrowser.open_new_tab(f"https://open.spotify.com/search/{q}")
    return f"Spotify não instalado; abri a busca '{busca}' no Spotify Web."


def controlar_spotify(acao):
    try:
        import spotify_api
        if not spotify_api.configurado():
            return ("ERRO: a Web API do Spotify não está configurada - o usuário "
                    "precisa colar o client_id no config.json e rodar o "
                    "'Autorizar Spotify.bat'.")
        return spotify_api.controlar(acao)
    except Exception as e:
        return f"ERRO no controle do Spotify: {e}"


def _primeiro_video_youtube(busca):
    """Busca no YouTube e devolve o id do primeiro vídeo (scrape leve)."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(busca)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=8) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    m = re.search(r'"videoId":"([\w-]{11})"', html)
    return m.group(1) if m else None


def tocar_no_youtube(busca):
    try:
        vid = _primeiro_video_youtube(busca)
    except Exception:
        vid = None
    if vid:
        webbrowser.open_new_tab(f"https://www.youtube.com/watch?v={vid}")
        return f"Abri o primeiro vídeo do YouTube para '{busca}'."
    webbrowser.open_new_tab(
        "https://www.youtube.com/results?search_query=" + urllib.parse.quote(busca))
    return f"Não achei um vídeo direto; abri os resultados da busca '{busca}' no YouTube."


def abrir_programa(nome):
    chave = nome.lower().strip()
    alvo = APPS_CONHECIDOS.get(chave, nome)
    if _abrir(alvo):
        return f"Programa '{nome}' aberto."
    return f"ERRO: não consegui abrir '{nome}'. Programa não encontrado."


def abrir_site(url):
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    try:
        webbrowser.open_new_tab(url)
        return f"Site {url} aberto no navegador."
    except Exception as e:
        return f"ERRO ao abrir o site: {e}"


# ---------- controle do computador (v0.6) ----------

# Processos que o Jarvis NUNCA fecha: o sistema, o shell e ele mesmo
PROCESSOS_PROTEGIDOS = {
    "python.exe", "pythonw.exe", "explorer.exe", "svchost.exe", "csrss.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "smss.exe", "dwm.exe",
    "wininit.exe", "taskhostw.exe", "system", "system idle process",
    "conhost.exe", "cmd.exe",
}

# Nome falado -> executavel (complementa o casamento aproximado)
APPS_FECHAR = {
    "spotify": "Spotify.exe",
    "chrome": "chrome.exe",
    "navegador": "chrome.exe",
    "google chrome": "chrome.exe",
    "obsidian": "Obsidian.exe",
    "vs code": "Code.exe",
    "code": "Code.exe",
    "editor": "Code.exe",
    "bloco de notas": "Notepad.exe",
    "notepad": "Notepad.exe",
    "calculadora": "CalculatorApp.exe",
    "paint": "mspaint.exe",
    "discord": "Discord.exe",
    "steam": "steam.exe",
}


def _processos_rodando():
    """Nomes de .exe em execucao (tasklist), sem repeticao."""
    import csv as _csv
    import io as _io
    proc = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=15)
    nomes = set()
    for linha in _csv.reader(_io.StringIO(proc.stdout or "")):
        if linha and linha[0].strip():
            nomes.add(linha[0].strip())
    return sorted(nomes)


def fechar_programa(nome, forcar=False):
    """Fecha um programa pelo nome falado.

    Suave por padrao (taskkill sem /F envia WM_CLOSE: o app pode
    perguntar se quer salvar). forcar=True mata o processo - o prompt
    manda o Claude so usar quando o usuario pedir explicitamente.
    """
    from difflib import SequenceMatcher

    falado = str(nome).lower().strip()
    exe = APPS_FECHAR.get(falado)
    if exe is None:
        try:
            rodando = _processos_rodando()
        except Exception as e:
            return f"ERRO ao listar os processos: {e}"
        alvo = re.sub(r"[^a-z0-9]", "", falado)
        if not alvo:
            return "ERRO: nome de programa vazio."
        melhores = []
        for n in rodando:
            stem = re.sub(r"[^a-z0-9]", "", n.lower().rsplit(".", 1)[0])
            nota = SequenceMatcher(None, alvo, stem).ratio()
            if alvo in stem or stem in alvo:
                nota = max(nota, 0.9)
            if nota >= 0.75:
                melhores.append((nota, n))
        if not melhores:
            return (f"ERRO: nenhum programa aberto parecido com '{nome}'. "
                    "Talvez ele ja esteja fechado.")
        melhores.sort(reverse=True)
        exe = melhores[0][1]

    if exe.lower() in PROCESSOS_PROTEGIDOS:
        return (f"ERRO: '{exe}' e um processo do sistema (ou o proprio "
                "Jarvis); nao vou fechar.")

    cmd = ["taskkill", "/IM", exe] + (["/F"] if forcar else [])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=15)
    except Exception as e:
        return f"ERRO ao fechar '{exe}': {e}"
    if proc.returncode == 0:
        return f"Programa '{exe}' fechado."
    saida = (proc.stderr or proc.stdout or "").strip()[:200]
    if proc.returncode == 128 or "não encontrado" in saida.lower() \
            or "not found" in saida.lower():
        return f"O programa '{exe}' nao esta aberto."
    if not forcar:
        return (f"ERRO: '{exe}' nao aceitou fechar de forma suave. "
                "Se o usuario quiser forcar (pode perder trabalho nao "
                "salvo), chame de novo com forcar=true.")
    return f"ERRO ao fechar '{exe}': {saida}"


def _endpoint_volume():
    """IAudioEndpointVolume do dispositivo de som padrao (pycaw)."""
    import comtypes
    from pycaw.pycaw import AudioUtilities

    try:
        comtypes.CoInitialize()  # a thread do cerebro nao tem COM iniciado
    except OSError:
        pass  # ja iniciado nesta thread
    return AudioUtilities.GetSpeakers().EndpointVolume


def controlar_volume(acao, percentual=None):
    """Volume mestre do Windows: definir/aumentar/diminuir/mudo/som/consultar."""
    try:
        vol = _endpoint_volume()
        atual = round(vol.GetMasterVolumeLevelScalar() * 100)
    except Exception as e:
        return f"ERRO: controle de volume indisponivel ({e})."
    try:
        passo = max(1, min(100, int(percentual))) if percentual is not None else 10
    except (TypeError, ValueError):
        passo = 10

    if acao == "consultar":
        mudo = " (no mudo)" if vol.GetMute() else ""
        return f"O volume esta em {atual}%{mudo}."
    if acao == "mudo":
        vol.SetMute(1, None)
        return "Som no mudo."
    if acao == "som":
        vol.SetMute(0, None)
        return f"Mudo desativado; volume em {atual}%."
    if acao == "definir":
        if percentual is None:
            return "ERRO: informe o percentual (0 a 100)."
        novo = max(0, min(100, int(percentual)))
    elif acao == "aumentar":
        novo = min(100, atual + passo)
    elif acao == "diminuir":
        novo = max(0, atual - passo)
    else:
        return f"ERRO: acao de volume desconhecida '{acao}'."
    try:
        vol.SetMasterVolumeLevelScalar(novo / 100.0, None)
        vol.SetMute(0, None)  # ajustar o volume tira do mudo
    except Exception as e:
        return f"ERRO ao ajustar o volume: {e}"
    return f"Volume em {novo}%."


def desligar_computador(acao):
    """Desliga/reinicia/suspende. So roda apos o 'Confirma, senhor?' -> 'sim'
    (esta em FERRAMENTAS_DESTRUTIVAS); os 5 s dao tempo da fala terminar."""
    comandos = {
        "desligar": ["shutdown", "/s", "/t", "5"],
        "reiniciar": ["shutdown", "/r", "/t", "5"],
        "suspender": ["rundll32", "powrprof.dll,SetSuspendState", "0,1,0"],
    }
    if acao not in comandos:
        return f"ERRO: acao de energia desconhecida '{acao}'."
    try:
        subprocess.Popen(comandos[acao])
    except Exception as e:
        return f"ERRO ao {acao}: {e}"
    frases = {"desligar": "Desligando o computador em cinco segundos.",
              "reiniciar": "Reiniciando o computador em cinco segundos.",
              "suspender": "Suspendendo o computador."}
    return frases[acao]


def executar_ferramenta(nome, entrada):
    try:
        if nome == "tocar_no_spotify":
            return executar_ferramenta.tocar_no_spotify(
                entrada["busca"], entrada.get("tipo", "musica"))
        if nome == "controlar_spotify":
            return executar_ferramenta.controlar_spotify(entrada["acao"])
        if nome == "tocar_no_youtube":
            return executar_ferramenta.tocar_no_youtube(entrada["busca"])
        if nome == "abrir_programa":
            return executar_ferramenta.abrir_programa(entrada["nome"])
        if nome == "abrir_site":
            return executar_ferramenta.abrir_site(entrada["url"])
        # v0.4 - memoria e aprendizado
        if nome == "lembrar":
            return aprendizado.lembrar(entrada["fato"])
        if nome == "esquecer":
            return aprendizado.esquecer(entrada["trecho"])
        if nome == "procurar_programa":
            return aprendizado.procurar_programa(entrada["nome"])
        if nome == "pesquisar_na_web":
            return aprendizado.pesquisar_na_web(entrada["pergunta"])
        if nome == "ler_pagina":
            return aprendizado.ler_pagina(entrada["url"])
        if nome == "consultar_gastos":
            return custos.resumo(entrada.get("periodo", "hoje"))
        # v0.5 - arquivos e dados
        if nome == "listar_pasta":
            return arquivos.listar_pasta(entrada["pasta"])
        if nome == "procurar_arquivo":
            return arquivos.procurar_arquivo(entrada["nome"], entrada.get("pasta", ""))
        if nome == "criar_pasta":
            return arquivos.criar_pasta(entrada["caminho"])
        if nome == "criar_arquivo":
            return arquivos.criar_arquivo(entrada["caminho"], entrada["conteudo"])
        if nome == "ler_arquivo":
            return arquivos.ler_arquivo(entrada["caminho"])
        if nome == "mover_arquivo":
            return arquivos.mover_arquivo(entrada["origem"], entrada["destino"])
        if nome == "apagar_arquivo":
            return arquivos.apagar_arquivo(entrada["caminho"])
        if nome == "analisar_dados":
            return arquivos.analisar_dados(entrada["caminho"])
        # v0.7 - escrever em documentos existentes
        if nome == "acrescentar_ao_arquivo":
            return arquivos.acrescentar_ao_arquivo(
                entrada["caminho"], entrada["conteudo"])
        if nome == "substituir_no_arquivo":
            return arquivos.substituir_no_arquivo(
                entrada["caminho"], entrada["trecho"], entrada.get("novo", ""))
        if nome == "escrever_celula":
            return arquivos.escrever_celula(
                entrada["caminho"], entrada["celula"], entrada["valor"])
        if nome == "criar_atalho":
            return aprendizado.criar_atalho(entrada["frases"], entrada["alvo"])
        if nome == "criar_habilidade":
            return aprendizado.criar_habilidade(
                entrada["nome"], entrada["descricao"], entrada["codigo"])
        if nome == "executar_habilidade":
            try:
                argumentos = json.loads(entrada.get("argumentos") or "{}")
            except json.JSONDecodeError:
                argumentos = {}
            return aprendizado.executar_habilidade(entrada["nome"], argumentos)
        # v0.6 - controle do computador
        if nome == "fechar_programa":
            return executar_ferramenta.fechar_programa(
                entrada["nome"], bool(entrada.get("forcar", False)))
        if nome == "controlar_volume":
            return executar_ferramenta.controlar_volume(
                entrada["acao"], entrada.get("percentual"))
        if nome == "desligar_computador":
            return executar_ferramenta.desligar_computador(entrada["acao"])
        return f"ERRO: ferramenta desconhecida '{nome}'."
    except Exception as e:
        return f"ERRO ao executar {nome}: {e}"


# Indirecao para os testes trocarem as implementacoes sem abrir nada de verdade
executar_ferramenta.tocar_no_spotify = tocar_no_spotify
executar_ferramenta.controlar_spotify = controlar_spotify
executar_ferramenta.tocar_no_youtube = tocar_no_youtube
executar_ferramenta.abrir_programa = abrir_programa
executar_ferramenta.abrir_site = abrir_site
executar_ferramenta.fechar_programa = fechar_programa
executar_ferramenta.controlar_volume = controlar_volume
executar_ferramenta.desligar_computador = desligar_computador


# ---------- o cerebro ----------

class Cerebro:
    """Loop agentico: envia o comando ao Claude, executa as ferramentas
    pedidas e devolve a frase final para ser falada."""

    MAX_RODADAS = 4

    def __init__(self, cfg):
        import anthropic  # import tardio: v0.2 funciona sem o SDK

        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise RuntimeError("variavel de ambiente ANTHROPIC_API_KEY nao definida")

        c = cfg.get("cerebro", {})
        self.modelo = c.get("modelo", MODELO_PADRAO)
        self.max_historico = int(c.get("max_historico", 6))
        self.cliente = anthropic.Anthropic()  # le ANTHROPIC_API_KEY do ambiente
        self.historico = deque(maxlen=self.max_historico)  # pares (user, assistant)
        # (nome, input) de uma ferramenta destrutiva aguardando o "sim" do
        # usuario; quem confirma/cancela e o assistente.py, por voz.
        self.acao_pendente = None
        # threading.Event fornecido pelo assistente: quando setado, o pedido
        # em andamento e abortado ("Jarvis, cancela").
        self.cancelar = None

        # Glossario do usuario: da ao Claude um alvo concreto para corrigir
        # nomes que o reconhecimento de fala distorce ("guite rabe" -> GitHub).
        self.sistema = SISTEMA
        vocab = cfg.get("vocabulario", [])
        if vocab:
            self.sistema += (
                "\n\nPalavras e nomes que o usuário costuma dizer — se a "
                "transcrição parecer foneticamente com uma delas, assuma que "
                "é ela: " + ", ".join(vocab) + "."
            )

        # v0.6 - poda automatica: quando a memoria estoura o limite, o
        # aprendizado chama este resumidor para condensar os fatos antigos
        # em vez de simplesmente descarta-los.
        aprendizado.RESUMIDOR = self._resumir_memoria

    def _resumir_memoria(self, fatos):
        """Condensa uma lista de fatos antigos em poucos fatos curtos."""
        linhas = "\n".join(f"- [{f['data']}] {f['fato']}" for f in fatos)
        resp = self.cliente.messages.create(
            model=self.modelo,
            max_tokens=600,
            system=("Você condensa a memória de longo prazo de um assistente "
                    "pessoal. Resuma os fatos abaixo em NO MÁXIMO 12 fatos "
                    "curtos e autocontidos, preservando caminhos de "
                    "programas/arquivos, nomes próprios e preferências do "
                    "usuário; descarte duplicados e obsoletos. Responda SÓ "
                    "com os fatos, um por linha, começando com '- '."),
            messages=[{"role": "user", "content": linhas}],
        )
        try:
            custos.registrar(self.modelo, resp.usage)
        except Exception:
            pass
        texto = "\n".join(b.text for b in resp.content if b.type == "text")
        return [l.strip()[2:].strip() for l in texto.splitlines()
                if l.strip().startswith("- ")]

    def _checar_cancelamento(self):
        if self.cancelar is not None and self.cancelar.is_set():
            raise PedidoCancelado()

    def executar_pendente(self):
        """Executa a acao destrutiva retida, apos o 'sim' do usuario.

        Devolve a saida da ferramenta, ou None se nao havia pendencia.
        """
        if not self.acao_pendente:
            return None
        nome, entrada = self.acao_pendente
        self.acao_pendente = None
        saida = executar_ferramenta(nome, entrada)
        print(f"  [cerebro] acao confirmada: {nome} -> {saida}")
        # registra no historico para o contexto das proximas frases
        self.historico.append(("sim, confirmo",
                               f"(confirmado; executei {nome}: {saida})"))
        return saida

    def cancelar_pendente(self):
        """Descarta a acao destrutiva retida (usuario negou ou mudou de assunto)."""
        if self.acao_pendente:
            print(f"  [cerebro] acao cancelada: {self.acao_pendente[0]}")
            self.historico.append(("nao", "(acao cancelada a pedido do senhor)"))
        self.acao_pendente = None

    def _chamar_api(self, sistema, mensagens):
        """Uma chamada ao Claude, com retentativa no timeout de compilacao.

        Na 1a chamada apos as ferramentas mudarem, o servidor compila a
        'grammar' dos schemas strict e pode devolver 400 'Grammar
        compilation timed out' - a compilacao continua por la, entao
        repetir em alguns segundos resolve.
        """
        import anthropic

        for tentativa in (1, 2, 3):
            try:
                return self.cliente.messages.create(
                    model=self.modelo,
                    max_tokens=1024,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "low"},  # comandos simples: rapido e barato
                    system=[{
                        "type": "text",
                        "text": sistema,
                        "cache_control": {"type": "ephemeral"},  # cacheia tools+sistema
                    }],
                    tools=FERRAMENTAS,
                    messages=mensagens,
                )
            except anthropic.BadRequestError as e:
                if "Grammar compilation" not in str(e) or tentativa == 3:
                    raise
                print("  [cerebro] servidor ainda compilando os schemas; "
                      f"tentando de novo ({tentativa}/2)...")
                self._checar_cancelamento()
                time.sleep(3.0 * tentativa)

    def processar(self, texto):
        """Devolve a resposta em texto do Jarvis (ja executando as acoes)."""
        # um pedido novo descarta qualquer confirmacao que ficou para tras
        self.acao_pendente = None
        # A memoria e as habilidades mudam em runtime, entao o bloco e
        # remontado a cada pedido. So invalida o prompt cache quando o
        # conteudo de fato muda.
        sistema = (
            self.sistema
            + "\n\nMEMÓRIA ATUAL (fatos que você aprendeu antes):\n"
            + aprendizado.memoria_para_prompt()
            + "\n\nHABILIDADES:\n"
            + aprendizado.listar_habilidades()
        )

        mensagens = []
        for usuario, resposta in self.historico:
            mensagens.append({"role": "user", "content": usuario})
            mensagens.append({"role": "assistant", "content": resposta})
        mensagens.append({"role": "user", "content": texto})

        resposta_final = ""
        for _ in range(self.MAX_RODADAS):
            self._checar_cancelamento()
            resp = self._chamar_api(sistema, mensagens)

            try:
                custos.registrar(self.modelo, resp.usage)
            except Exception as e:
                print(f"  [custos] falha ao registrar uso ({e}).")

            usos = [b for b in resp.content if b.type == "tool_use"]
            textos = [b.text for b in resp.content if b.type == "text"]
            if textos:
                resposta_final = " ".join(textos).strip()

            if resp.stop_reason != "tool_use":
                break

            mensagens.append({"role": "assistant", "content": resp.content})
            resultados = []
            for uso in usos:
                self._checar_cancelamento()
                print(f"  [cerebro] ferramenta: {uso.name}({json.dumps(uso.input, ensure_ascii=False)})")
                if uso.name in FERRAMENTAS_DESTRUTIVAS:
                    # nao executa: retem a acao e pede confirmacao por voz
                    self.acao_pendente = (uso.name, dict(uso.input))
                    saida = ("AGUARDANDO CONFIRMAÇÃO: a ação NÃO foi executada. "
                             "Pergunte ao usuário em uma frase curta se confirma "
                             "(ex.: 'Confirma, senhor?') e não faça mais nada. "
                             "Ela será executada automaticamente quando ele "
                             "confirmar por voz.")
                else:
                    saida = executar_ferramenta(uso.name, uso.input)
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": uso.id,
                    "content": saida,
                })
            mensagens.append({"role": "user", "content": resultados})

        if not resposta_final:
            resposta_final = "Feito, senhor."
        if "[IGNORAR]" in resposta_final:
            # fala ambiente: nao entra no historico (nao polui o contexto)
            return "[IGNORAR]"
        self.historico.append((texto, resposta_final))
        return resposta_final
