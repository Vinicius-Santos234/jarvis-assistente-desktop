"""
Aprendizado do Jarvis v0.4 - memoria persistente e novas capacidades.

O cerebro (cerebro.py) usa este modulo para:
- MEMORIA: fatos duraveis em memoria.json, injetados no prompt do Claude
  a cada pedido ("o caminho do jogo X e...", "a playlist de foco e...").
- PESQUISA: buscar na web (DuckDuckGo) e ler paginas quando nao sabe algo.
- PROGRAMAS: varrer o Menu Iniciar atras de um programa que nao abriu.
- ATALHOS: gravar comandos fixos novos no config.json ("quando eu disser
  X, faca Y") - instantaneos e sem custo de API nas proximas vezes.
- HABILIDADES: scripts Python pequenos escritos pelo proprio Jarvis,
  guardados em habilidades/ e executados SOMENTE depois que o usuario
  aprovar por voz ("Jarvis, aprovar habilidade").
"""

import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MEMORIA_PATH = BASE_DIR / "memoria.json"
HABILIDADES_DIR = BASE_DIR / "habilidades"
REGISTRO_PATH = HABILIDADES_DIR / "habilidades.json"

MAX_FATOS = 100  # acima disso, a memoria e podada (resumo ou corte)

# v0.6 - poda automatica com resumo: o cerebro pluga aqui uma funcao que
# recebe a lista de fatos antigos e devolve uma lista de strings resumidas
# (via Claude). Sem cerebro, a poda cai no corte simples dos mais antigos.
RESUMIDOR = None


def _normalizar(texto):
    """minusculas + sem acentos (copia local para nao importar assistente)."""
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# ---------- memoria ----------

def _carregar_memoria():
    try:
        with open(MEMORIA_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("fatos", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _salvar_memoria(fatos):
    with open(MEMORIA_PATH, "w", encoding="utf-8") as f:
        json.dump({"fatos": fatos}, f, ensure_ascii=False, indent=2)


def lembrar(fato):
    """Grava um fato duravel na memoria (deduplicado, com data)."""
    fato = str(fato).strip()
    if not fato:
        return "ERRO: fato vazio."
    fatos = _carregar_memoria()
    if any(_normalizar(f["fato"]) == _normalizar(fato) for f in fatos):
        return "Esse fato ja estava na memoria."
    fatos.append({"data": date.today().isoformat(), "fato": fato})
    if len(fatos) > MAX_FATOS:
        fatos = _podar(fatos)
    _salvar_memoria(fatos)
    return f"Memorizado: {fato}"


def _podar(fatos):
    """Poda a memoria cheia: resume a metade mais antiga em poucos fatos
    (via RESUMIDOR/Claude); sem resumidor ou em falha, corta os antigos."""
    if RESUMIDOR is None:
        return fatos[-MAX_FATOS:]
    metade = len(fatos) // 2
    antigos, recentes = fatos[:metade], fatos[metade:]
    try:
        resumidos = [str(r).strip() for r in RESUMIDOR(antigos) if str(r).strip()]
    except Exception as e:
        print(f"  [memoria] poda com resumo falhou ({e}); cortando os antigos.")
        return fatos[-MAX_FATOS:]
    if not resumidos:
        return fatos[-MAX_FATOS:]
    hoje = date.today().isoformat()
    novos = [{"data": hoje, "fato": f} for f in resumidos[:15]]
    print(f"  [memoria] poda: {len(antigos)} fatos antigos viraram "
          f"{len(novos)} resumidos.")
    return novos + recentes


def esquecer(trecho):
    """Remove da memoria todos os fatos que contem o trecho."""
    trecho_norm = _normalizar(trecho)
    fatos = _carregar_memoria()
    restantes = [f for f in fatos if trecho_norm not in _normalizar(f["fato"])]
    removidos = len(fatos) - len(restantes)
    if removidos:
        _salvar_memoria(restantes)
        return f"{removidos} fato(s) esquecido(s)."
    return "Nenhum fato na memoria contem esse trecho."


def memoria_para_prompt():
    """Bloco de texto com a memoria inteira, para o system prompt."""
    fatos = _carregar_memoria()
    if not fatos:
        return "(vazia por enquanto)"
    return "\n".join(f"- [{f['data']}] {f['fato']}" for f in fatos)


# ---------- pesquisa na web ----------

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
       "Accept-Language": "pt-BR,pt;q=0.9"}


def pesquisar_na_web(pergunta):
    """Busca na web e devolve os primeiros resultados em texto.

    Usa o RSS do Bing (estavel e feito para parsing); se vier vazio,
    tenta o HTML do DuckDuckGo (que as vezes serve captcha para bots).
    """
    resultados = _buscar_bing_rss(pergunta)
    if not resultados:
        resultados = _buscar_duckduckgo(pergunta)
    if not resultados:
        return "A busca nao devolveu resultados."
    return "Resultados da busca:\n" + "\n".join(resultados)


def _buscar_bing_rss(pergunta):
    url = ("https://www.bing.com/search?format=rss&setlang=pt-BR&q="
           + urllib.parse.quote(pergunta))
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    resultados = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)[:5]:
        titulo = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
        resumo = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
        resultados.append(
            f"- {html.unescape(titulo.group(1).strip()) if titulo else '?'}\n"
            f"  {html.unescape(link.group(1).strip()) if link else ''}\n"
            f"  {html.unescape(resumo.group(1).strip()) if resumo else ''}")
    return resultados


def _buscar_duckduckgo(pergunta):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(pergunta)
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=10) as resp:
            pagina = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    resultados = []
    blocos = re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'class="result__snippet"[^>]*>(.*?)</a>',
        pagina, re.DOTALL)
    for link, titulo, resumo in blocos[:5]:
        m = re.search(r"uddg=([^&]+)", link)
        if m:
            link = urllib.parse.unquote(m.group(1))
        titulo = html.unescape(re.sub(r"<[^>]+>", "", titulo)).strip()
        resumo = html.unescape(re.sub(r"<[^>]+>", "", resumo)).strip()
        resultados.append(f"- {titulo}\n  {link}\n  {resumo}")
    return resultados


def ler_pagina(url):
    """Baixa uma pagina e devolve o texto principal (sem HTML), truncado."""
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=10) as resp:
            pagina = resp.read(1_000_000).decode("utf-8", errors="ignore")
    except Exception as e:
        return f"ERRO ao ler a pagina: {e}"
    pagina = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", pagina)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", pagina))
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) > 4000:
        texto = texto[:4000] + " [...pagina truncada]"
    return texto or "A pagina nao tem texto legivel."


# ---------- procurar programas no Windows ----------

def procurar_programa(nome):
    """Varre os atalhos do Menu Iniciar atras de um programa pelo nome.

    Devolve os melhores candidatos (nome + caminho do .lnk) - o caminho
    pode ser passado direto ao abrir_programa (os.startfile abre .lnk).
    """
    from difflib import SequenceMatcher

    pastas = [
        Path(os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")),
        Path(os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs")),
    ]
    alvo = _normalizar(nome)
    candidatos = []
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for lnk in pasta.rglob("*.lnk"):
            stem = _normalizar(lnk.stem)
            nota = SequenceMatcher(None, alvo, stem).ratio()
            if alvo in stem:
                nota = max(nota, 0.9)
            if nota >= 0.55:
                candidatos.append((nota, lnk.stem, str(lnk)))
    if not candidatos:
        return (f"Nenhum programa parecido com '{nome}' no Menu Iniciar. "
                "Tente pesquisar na web como abri-lo.")
    candidatos.sort(reverse=True)
    linhas = [f"- {n} -> {c}" for _, n, c in candidatos[:5]]
    return ("Programas encontrados (use o caminho no abrir_programa e "
            "memorize com lembrar):\n" + "\n".join(linhas))


# ---------- atalhos aprendidos (comandos fixos novos) ----------

def criar_atalho(frases, alvo, caminho_config=None):
    """Acrescenta um comando fixo em config.json -> voz.comandos.

    So para abrir coisas (programa, site, URI tipo spotify:). O comando
    passa a valer imediatamente (o assistente rele os comandos a cada
    frase) e continua depois de reiniciar.
    """
    caminho = Path(caminho_config) if caminho_config else BASE_DIR / "config.json"
    frases = [str(f).strip() for f in frases if str(f).strip()]
    if not frases:
        return "ERRO: informe ao menos uma frase para o atalho."
    if not str(alvo).strip():
        return "ERRO: informe o alvo (caminho, URL ou URI)."

    with open(caminho, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    comandos = cfg.setdefault("voz", {}).setdefault("comandos", [])

    ja_usadas = {_normalizar(fr) for c in comandos for fr in c.get("frases", [])}
    repetidas = [fr for fr in frases if _normalizar(fr) in ja_usadas]
    if repetidas:
        return f"ERRO: a frase '{repetidas[0]}' ja pertence a outro comando."

    comandos.append({
        "frases": frases,
        "acao": "abrir",
        "alvo": str(alvo),
        "resposta": "respostas/atalho.wav",
        "aprendido_em": date.today().isoformat(),
    })
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return (f"Atalho criado: dizer {frases} abre '{alvo}'. Ja esta valendo, "
            "sem custo de API nas proximas vezes.")


# ---------- habilidades (auto-extensao, com aprovacao por voz) ----------

def _carregar_registro():
    try:
        with open(REGISTRO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _salvar_registro(reg):
    HABILIDADES_DIR.mkdir(exist_ok=True)
    with open(REGISTRO_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def criar_habilidade(nome, descricao, codigo):
    """Salva um script Python novo em habilidades/, PENDENTE de aprovacao.

    O script recebe os argumentos como JSON em sys.argv[1] e imprime o
    resultado. Ele NAO roda ate o usuario dizer "Jarvis, aprovar
    habilidade" (quem aprova e o assistente.py, nunca o cerebro).
    """
    slug = re.sub(r"[^a-z0-9_]+", "-", _normalizar(nome)).strip("-")
    if not slug:
        return "ERRO: nome invalido para a habilidade."
    if not str(codigo).strip():
        return "ERRO: codigo vazio."
    HABILIDADES_DIR.mkdir(exist_ok=True)
    (HABILIDADES_DIR / f"{slug}.py").write_text(str(codigo), encoding="utf-8")
    reg = _carregar_registro()
    reg[slug] = {
        "descricao": str(descricao),
        "aprovada": False,
        "criada": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _salvar_registro(reg)
    return (f"Habilidade '{slug}' criada, aguardando aprovacao. Avise o "
            "usuario para conferir habilidades/{0}.py e dizer 'Jarvis, "
            "aprovar habilidade' para ativa-la.".format(slug))


def aprovar_ultima_habilidade():
    """Aprova a habilidade pendente mais recente (chamado pelo comando de
    voz 'aprovar habilidade' no assistente.py - decisao fica com o usuario)."""
    reg = _carregar_registro()
    pendentes = sorted(
        (dados["criada"], nome) for nome, dados in reg.items()
        if not dados.get("aprovada"))
    if not pendentes:
        return None
    nome = pendentes[-1][1]
    reg[nome]["aprovada"] = True
    _salvar_registro(reg)
    return nome


def listar_habilidades():
    reg = _carregar_registro()
    if not reg:
        return "Nenhuma habilidade criada ainda."
    linhas = []
    for nome, dados in sorted(reg.items()):
        estado = "aprovada" if dados.get("aprovada") else "PENDENTE de aprovacao"
        linhas.append(f"- {nome} ({estado}): {dados.get('descricao', '')}")
    return "\n".join(linhas)


def executar_habilidade(nome, argumentos=None):
    """Roda uma habilidade APROVADA em um processo separado (timeout 30 s)."""
    slug = re.sub(r"[^a-z0-9_]+", "-", _normalizar(nome)).strip("-")
    reg = _carregar_registro()
    if slug not in reg:
        return f"ERRO: habilidade '{slug}' nao existe. Existentes:\n{listar_habilidades()}"
    if not reg[slug].get("aprovada"):
        return (f"ERRO: a habilidade '{slug}' ainda nao foi aprovada. Peca ao "
                "usuario para dizer 'Jarvis, aprovar habilidade'.")
    caminho = HABILIDADES_DIR / f"{slug}.py"
    if not caminho.is_file():
        return f"ERRO: arquivo da habilidade '{slug}' sumiu."
    try:
        proc = subprocess.run(
            [sys.executable, str(caminho), json.dumps(argumentos or {}, ensure_ascii=False)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, cwd=str(BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        return f"ERRO: a habilidade '{slug}' demorou mais de 30 s e foi cancelada."
    saida = (proc.stdout or "").strip()
    erro = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return f"ERRO na habilidade '{slug}':\n{erro or saida}"
    return saida or "(a habilidade rodou sem imprimir nada)"
