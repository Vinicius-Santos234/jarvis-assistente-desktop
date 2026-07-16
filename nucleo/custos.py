"""
Medidor de gasto da API - Jarvis v0.4.2.

Cada resposta da API devolve quantos tokens foram usados (usage). Este
modulo acumula esses numeros por dia em custos.json e calcula o custo
em dolares pela tabela de precos do modelo, permitindo perguntar:
"Jarvis, quanto gastei hoje?" (ferramenta consultar_gastos do cerebro).

Precos por 1 milhao de tokens (USD). Cache do prompt: escrita custa
1,25x o preco de entrada (TTL 5 min) e leitura custa 0,1x.
"""

import json
from datetime import date, timedelta
from pathlib import Path

# Raiz do projeto (este arquivo vive em nucleo/); runtime fica em dados/
BASE_DIR = Path(__file__).resolve().parent.parent
CUSTOS_PATH = BASE_DIR / "dados" / "custos.json"
CONFIG_PATH = BASE_DIR / "config.json"

CAMBIO_BRL_PADRAO = 5.5  # so para dar uma nocao em reais; ajuste no config

# Fim do preco de lancamento do Sonnet 5 ($2/$10); depois vale $3/$15.
_FIM_PRECO_LANCAMENTO_SONNET5 = date(2026, 8, 31)

# v0.8 - voz (OpenAI TTS), USD por 1M de caracteres: tts-1-hd custa 30;
# tts-1 e gpt-4o-mini-tts (~US$ 0,015/min, cobrado por token de audio -
# por caractere e uma estimativa boa em portugues) custam ~15.
PRECO_TTS_USD_1M_CHARS = 15.0
PRECO_TTS_HD_USD_1M_CHARS = 30.0


def _precos(modelo, quando=None):
    """(preco_entrada, preco_saida) em USD por 1M de tokens."""
    quando = quando or date.today()
    m = (modelo or "").lower()
    if "sonnet-5" in m:
        if quando <= _FIM_PRECO_LANCAMENTO_SONNET5:
            return 2.0, 10.0
        return 3.0, 15.0
    if "haiku" in m:
        return 1.0, 5.0
    if "opus" in m:
        return 5.0, 25.0
    return 3.0, 15.0  # desconhecido: assume preco de Sonnet


def _carregar():
    try:
        with open(CUSTOS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"dias": {}}


def _salvar(dados):
    with open(CUSTOS_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def _cambio_brl():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return float(json.load(f).get("cerebro", {}).get(
                "cambio_brl", CAMBIO_BRL_PADRAO))
    except Exception:
        return CAMBIO_BRL_PADRAO


def registrar(modelo, usage):
    """Acumula o uso de UMA resposta da API no dia de hoje.

    `usage` e o objeto da resposta (ou qualquer coisa com os atributos
    input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens). Devolve o custo desta chamada em USD.
    """
    entrada = getattr(usage, "input_tokens", 0) or 0
    saida = getattr(usage, "output_tokens", 0) or 0
    cache_esc = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_lei = getattr(usage, "cache_read_input_tokens", 0) or 0

    p_in, p_out = _precos(modelo)
    custo = (entrada * p_in
             + cache_esc * p_in * 1.25
             + cache_lei * p_in * 0.10
             + saida * p_out) / 1_000_000

    dados = _carregar()
    dia = dados.setdefault("dias", {}).setdefault(date.today().isoformat(), {
        "chamadas": 0, "entrada": 0, "saida": 0,
        "cache_escrita": 0, "cache_leitura": 0, "custo_usd": 0.0,
    })
    dia["chamadas"] += 1
    dia["entrada"] += entrada
    dia["saida"] += saida
    dia["cache_escrita"] += cache_esc
    dia["cache_leitura"] += cache_lei
    dia["custo_usd"] = round(dia["custo_usd"] + custo, 6)
    _salvar(dados)
    return custo


def registrar_tts(caracteres, modelo=""):
    """Acumula UMA sintese de voz (OpenAI TTS) no dia de hoje.

    Recebe o tamanho do texto falado; o custo e estimado por caractere,
    conforme o modelo. Devolve o custo estimado em USD.
    """
    preco = PRECO_TTS_HD_USD_1M_CHARS if "hd" in (modelo or "").lower() \
        else PRECO_TTS_USD_1M_CHARS
    custo = caracteres * preco / 1_000_000
    dados = _carregar()
    dia = dados.setdefault("dias", {}).setdefault(date.today().isoformat(), {
        "chamadas": 0, "entrada": 0, "saida": 0,
        "cache_escrita": 0, "cache_leitura": 0, "custo_usd": 0.0,
    })
    dia["tts_falas"] = dia.get("tts_falas", 0) + 1
    dia["tts_caracteres"] = dia.get("tts_caracteres", 0) + caracteres
    dia["custo_usd"] = round(dia.get("custo_usd", 0.0) + custo, 6)
    _salvar(dados)
    return custo


def _dias_do_periodo(periodo):
    """Lista de datas ISO que compoem o periodo pedido."""
    hoje = date.today()
    if periodo == "hoje":
        return [hoje.isoformat()]
    if periodo == "ontem":
        return [(hoje - timedelta(days=1)).isoformat()]
    if periodo == "semana":  # ultimos 7 dias, incluindo hoje
        return [(hoje - timedelta(days=i)).isoformat() for i in range(7)]
    if periodo == "mes":  # mes corrente
        return [date(hoje.year, hoje.month, d).isoformat()
                for d in range(1, hoje.day + 1)]
    return None  # total: todos os dias registrados


def resumo(periodo="hoje"):
    """Texto com o gasto do periodo, para o cerebro responder em voz alta."""
    dados = _carregar().get("dias", {})
    dias = _dias_do_periodo(periodo)
    if dias is None:
        dias = sorted(dados.keys())

    chamadas = entrada = saida = falas = 0
    custo = 0.0
    for d in dias:
        reg = dados.get(d)
        if not reg:
            continue
        chamadas += reg.get("chamadas", 0)
        entrada += reg.get("entrada", 0) + reg.get("cache_escrita", 0) \
            + reg.get("cache_leitura", 0)
        saida += reg.get("saida", 0)
        falas += reg.get("tts_falas", 0)
        custo += reg.get("custo_usd", 0.0)

    if chamadas == 0 and falas == 0:
        return f"Nenhum gasto registrado no periodo '{periodo}'."

    reais = custo * _cambio_brl()
    texto = (f"Gasto no periodo '{periodo}': US$ {custo:.4f} "
             f"(aproximadamente R$ {reais:.2f}) em {chamadas} chamada(s) a API. "
             f"Tokens: {entrada} de entrada (incluindo cache), {saida} de saida.")
    if falas:
        texto += f" Inclui {falas} fala(s) geradas pela voz OpenAI."
    return texto
