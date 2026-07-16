"""
A VOZ do Jarvis - v0.8 (OpenAI TTS com fallback edge-tts).

O edge-tts (gratis) tem voz generica de leitor de noticia; o TTS da
OpenAI (gpt-4o-mini-tts) gera fala muito mais natural e com
personalidade - a voz 'ash' e grave e polida, estilo mordomo dos
filmes. Esta camada e OPCIONAL e degrada sozinha: sem OPENAI_API_KEY,
sem internet ou com a API fora do ar, a fala cai para o edge-tts -
nada quebra.

Custo (estimado): ~US$ 15 por 1 milhao de caracteres falados
(~US$ 0,015 por minuto). Cada sintese e registrada em dados/custos.json
junto com o cerebro - "Jarvis, quanto gastei hoje?" ja inclui a voz.

Configurar (uma vez):
  1. Crie uma chave em https://platform.openai.com/api-keys
  2. No SEU PowerShell:  setx OPENAI_API_KEY "sk-..."
  3. Reinicie o Jarvis (config.json -> tts -> provedor: "openai")
  4. Regrave as falas fixas: C:\\Python310\\python.exe ferramentas\\gerar_vozes.py
"""

import io
import json
import os
import struct
import subprocess
import urllib.request
import wave
from pathlib import Path

URL = "https://api.openai.com/v1/audio/speech"
MODELO_PADRAO = "tts-1-hd"
VOZ_PADRAO = "onyx"
INSTRUCOES_PADRAO = ("Fale portugues brasileiro nativo, sem nenhum sotaque "
                     "estrangeiro, com voz calma, grave e polida, num tom "
                     "formal e prestativo de mordomo.")
VOZ_EDGE_PADRAO = "pt-BR-AntonioNeural"

_avisou_sem_chave = False


def chave():
    return os.environ.get("OPENAI_API_KEY", "").strip()


def config_tts(cfg):
    """Normaliza a secao 'tts' do config.json num dict com todas as chaves.

    Aceita config antigo sem a secao: vira edge-tts com a voz de
    cerebro.voz, exatamente como era ate a v0.7. Pedir 'openai' sem
    OPENAI_API_KEY no ambiente tambem cai para o edge (com aviso unico).
    """
    global _avisou_sem_chave
    cfg = cfg or {}
    bruto = cfg.get("tts") or {}

    openai = {"modelo": MODELO_PADRAO, "voz": VOZ_PADRAO,
              "instrucoes": INSTRUCOES_PADRAO}
    openai.update(bruto.get("openai") or {})

    edge = {"voz": (cfg.get("cerebro") or {}).get("voz", VOZ_EDGE_PADRAO),
            "rate": "-5%"}
    edge.update(bruto.get("edge") or {})

    provedor = bruto.get("provedor", "edge")
    if provedor == "openai" and not chave():
        if not _avisou_sem_chave:
            print("  [tts] OPENAI_API_KEY nao definida; usando o edge-tts. "
                  "Veja como configurar em nucleo/tts.py.")
            _avisou_sem_chave = True
        provedor = "edge"

    return {"provedor": provedor, "openai": openai, "edge": edge}


def assinatura(t):
    """Identifica provedor + voz + estilo. Muda a assinatura -> muda o
    audio: e a chave do cache dinamico e o marcador que faz o
    gerar_vozes.py regravar as falas fixas."""
    if t["provedor"] == "openai":
        o = t["openai"]
        return f"openai|{o['modelo']}|{o['voz']}|{o['instrucoes']}"
    e = t["edge"]
    return f"edge|{e['voz']}|{e['rate']}"


def _openai_wav(texto, o, timeout=30.0):
    """Sintese na OpenAI; devolve os bytes do WAV (24 kHz mono)."""
    corpo = {
        "model": o["modelo"],
        "voice": o["voz"],
        "input": texto,
        "response_format": "wav",
    }
    if o.get("instrucoes") and not o["modelo"].startswith("tts-1"):
        # so o gpt-4o-mini-tts dirige o estilo; os tts-1 rejeitam o campo
        corpo["instructions"] = o["instrucoes"]
    req = urllib.request.Request(URL, data=json.dumps(corpo).encode("utf-8"),
                                 headers={
        "Authorization": f"Bearer {chave()}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _consertar_wav(resp.read())


def _consertar_wav(dados):
    """A OpenAI transmite o WAV em streaming, com tamanho 'infinito'
    (0xFFFFFFFF) no cabecalho. O winsound toca, mas o wave le uma duracao
    de ~24 horas - e o barge-in do falar() esperaria esse tempo todo pelo
    fim da fala. Reescreve o cabecalho com o tamanho real do audio."""
    f = dados.find(b"fmt ")
    d = dados.find(b"data")
    if f < 0 or d < 0:
        return dados
    canais, rate = struct.unpack_from("<HI", dados, f + 10)
    largura = struct.unpack_from("<H", dados, f + 22)[0] // 8
    pcm = dados[d + 8:]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(canais or 1)
        w.setsampwidth(largura or 2)
        w.setframerate(rate or 24000)
        w.writeframes(pcm)
    return buf.getvalue()


def _edge_wav(texto, e, caminho_wav):
    """Sintese no edge-tts (mp3) + conversao para wav com o ffmpeg."""
    import asyncio

    import edge_tts
    import imageio_ffmpeg

    mp3 = Path(caminho_wav).with_suffix(".mp3")

    async def _gerar():
        await edge_tts.Communicate(texto, e["voz"], rate=e["rate"]).save(str(mp3))

    asyncio.run(_gerar())
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(mp3),
         "-ar", "44100", "-ac", "2", str(caminho_wav)],
        check=True,
    )
    mp3.unlink(missing_ok=True)


def sintetizar(texto, t, caminho_wav, fallback=True):
    """Gera o WAV da fala em `caminho_wav`. Devolve o provedor usado
    ('openai' | 'edge').

    Com fallback=True (padrao, usado nas respostas ao vivo), falha da
    OpenAI cai para o edge-tts. Com False (usado pelo gerar_vozes.py),
    a excecao sobe - melhor um [erro] visivel do que gravar uma fala
    fixa com a voz errada em silencio.
    """
    caminho_wav = Path(caminho_wav)
    if t["provedor"] == "openai":
        try:
            if not chave():
                raise RuntimeError("OPENAI_API_KEY nao definida no ambiente")
            dados = _openai_wav(texto, t["openai"])
            caminho_wav.write_bytes(dados)
            try:
                import custos
                custos.registrar_tts(len(texto), t["openai"]["modelo"])
            except Exception:
                pass  # medidor de gastos nunca derruba a fala
            return "openai"
        except Exception as e:
            if not fallback:
                raise
            print(f"  [tts] OpenAI indisponivel ({e}); falando com edge-tts.")
    _edge_wav(texto, t["edge"], caminho_wav)
    return "edge"
