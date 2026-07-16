"""
Gera as falas fixas do JARVIS em portugues e salva como .wav nas pastas
'vozes/' (palmas) e 'respostas/' (comandos de voz).

v0.8: a voz vem da secao "tts" do config.json - OpenAI TTS (voz 'ash',
grave e estilo mordomo; requer OPENAI_API_KEY no ambiente) ou edge-tts
(gratis). Se a voz configurada MUDOU desde a ultima geracao, todas as
falas sao regravadas sozinhas (marcador .assinatura-voz em cada pasta).

Rode apos instalar ou ao trocar a voz (precisa de internet):
    C:\\Python310\\python.exe ferramentas\\gerar_vozes.py

Para mudar as frases, edite as listas abaixo e rode de novo.
"""

import json
import sys
from pathlib import Path

# Raiz do projeto (este arquivo vive em ferramentas/); o modulo da voz, em nucleo/
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "nucleo"))

import tts  # noqa: E402  (precisa do sys.path acima)

PASTA_VOZES = BASE_DIR / "vozes"
PASTA_RESPOSTAS = BASE_DIR / "respostas"

# Falas sorteadas ao bater duas palmas (pasta vozes/)
FRASES = [
    ("ola-senhor",          "Olá, senhor."),
    ("o-que-vamos-fazer",   "O que vamos fazer hoje, senhor?"),
    ("bem-vindo",           "Bem-vindo de volta, senhor."),
    ("as-suas-ordens",      "Às suas ordens, senhor."),
    ("ao-seu-dispor",       "Ao seu dispor, senhor."),
    ("como-posso-ajudar",   "Como posso ajudá-lo, senhor?"),
    ("sistemas-online",     "Todos os sistemas online e prontos, senhor."),
    ("iniciando-protocolos","Iniciando os protocolos, senhor."),
]

# Respostas dos comandos de voz da v0.2 (pasta respostas/)
RESPOSTAS = [
    ("pois-nao",            "Pois não, senhor?"),
    ("nao-entendi",         "Perdão, senhor, não entendi."),
    ("abrindo-navegador",   "Abrindo o navegador, senhor."),
    ("abrindo-aplicativos", "Abrindo seus aplicativos, senhor."),
    ("iniciando-tudo",      "Iniciando tudo, senhor. Bom trabalho."),
    ("abrindo-obsidian",    "Abrindo o Obsidian, senhor."),
    ("abrindo-editor",      "Abrindo o editor de código, senhor."),
    ("desligando",          "Como quiser, senhor. Vou descansar."),
    ("um-momento",          "Um momento, senhor..."),
    ("ainda-trabalhando",   "Ainda trabalhando nisso, senhor. Só mais um instante."),
    ("erro-cerebro",        "Perdão, senhor, não consegui acessar meu cérebro. Verifique a conexão e a chave da API."),
    ("por-nada",            "Por nada, senhor. Estarei por aqui."),
    ("atalho",              "Imediatamente, senhor."),
    ("cancelado",           "Cancelado, senhor."),
    ("feito",               "Feito, senhor."),
    ("acao-falhou",         "Perdão, senhor, a ação falhou."),
]


def carregar_config():
    try:
        with open(BASE_DIR / "config.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def gerar_lote(pasta, frases, t):
    pasta.mkdir(exist_ok=True)
    marcador = pasta / ".assinatura-voz"
    assin = tts.assinatura(t)
    try:
        voz_mudou = marcador.read_text(encoding="utf-8") != assin
    except OSError:
        voz_mudou = True  # primeira geracao (ou marcador apagado)
    if voz_mudou:
        print("  (voz nova ou alterada - regravando todas as falas)")

    erros = 0
    for nome, texto in frases:
        wav = pasta / f"{nome}.wav"
        if wav.exists() and not voz_mudou:
            print(f"  [ja existe] {wav.name}")
            continue
        try:
            # sem fallback: melhor um [erro] visivel do que gravar a
            # fala fixa com a voz errada em silencio
            tts.sintetizar(texto, t, wav, fallback=False)
            print(f"  [ok] {wav.name}  ->  \"{texto}\"")
        except Exception as e:
            erros += 1
            print(f"  [erro] {nome}: {e}")

    if erros == 0:
        marcador.write_text(assin, encoding="utf-8")
    return erros


def main():
    t = tts.config_tts(carregar_config())
    prov = t["provedor"]
    print(f"Voz configurada: {prov} ({t[prov]['voz']})")

    print(f"\nFalas das palmas ({len(FRASES)})...")
    erros = gerar_lote(PASTA_VOZES, FRASES, t)
    print(f"\nRespostas dos comandos ({len(RESPOSTAS)})...")
    erros += gerar_lote(PASTA_RESPOSTAS, RESPOSTAS, t)

    if erros:
        print(f"\n{erros} fala(s) falharam - corrija o problema e rode de novo.")
    else:
        print(f"\nPronto! Arquivos em: {PASTA_VOZES} e {PASTA_RESPOSTAS}")


if __name__ == "__main__":
    main()
