"""
Gera as falas do JARVIS em portugues com voz neural (edge-tts) e
converte para .wav dentro da pasta 'vozes/'.

Rode uma vez (precisa de internet):
    python gerar_vozes.py

Para mudar as frases ou a voz, edite as listas abaixo e rode de novo.
Vozes masculinas em portugues disponiveis no edge-tts:
    pt-BR-AntonioNeural  (Brasil)   <- padrao
    pt-BR-FabioNeural    (Brasil)
    pt-PT-DuarteNeural   (Portugal, mais formal/mordomo)
"""

import asyncio
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg

VOZ = "pt-BR-AntonioNeural"
BASE_DIR = Path(__file__).resolve().parent
PASTA_VOZES = BASE_DIR / "vozes"
PASTA_RESPOSTAS = BASE_DIR / "respostas"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

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


async def gerar_mp3(texto, caminho_mp3):
    comunicador = edge_tts.Communicate(texto, VOZ, rate="-5%")
    await comunicador.save(str(caminho_mp3))


def mp3_para_wav(caminho_mp3, caminho_wav):
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", str(caminho_mp3),
         "-ar", "44100", "-ac", "2", str(caminho_wav)],
        check=True,
    )
    caminho_mp3.unlink(missing_ok=True)  # remove o mp3 temporario


async def gerar_lote(pasta, frases, pular_existentes=True):
    pasta.mkdir(exist_ok=True)
    for nome, texto in frases:
        mp3 = pasta / f"{nome}.mp3"
        wav = pasta / f"{nome}.wav"
        if pular_existentes and wav.exists():
            print(f"  [ja existe] {wav.name}")
            continue
        try:
            await gerar_mp3(texto, mp3)
            mp3_para_wav(mp3, wav)
            print(f"  [ok] {wav.name}  ->  \"{texto}\"")
        except Exception as e:
            print(f"  [erro] {nome}: {e}")


async def main():
    print(f"Falas das palmas ({len(FRASES)}) com a voz '{VOZ}'...")
    await gerar_lote(PASTA_VOZES, FRASES)
    print(f"\nRespostas dos comandos ({len(RESPOSTAS)})...")
    await gerar_lote(PASTA_RESPOSTAS, RESPOSTAS)
    print(f"\nPronto! Arquivos em: {PASTA_VOZES} e {PASTA_RESPOSTAS}")


if __name__ == "__main__":
    asyncio.run(main())
