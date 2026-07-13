"""
Transcricao de fala na NUVEM - v0.5.1 (Groq, Whisper large-v3).

O Whisper `small` local erra nomes proprios e ingles misturado; o
large-v3 servido pela Groq erra muito menos e responde em ~1 s. Esta
camada e OPCIONAL e degrada sozinha: sem chave, sem internet ou com a
API fora do ar, o assistente cai para o Whisper local (e depois para o
Vosk) - nada quebra.

Privacidade/custo: SO a frase do comando (depois do "Jarvis") e enviada;
a ativacao continua 100% offline no Vosk. No volume de uso pessoal, a
camada gratis da Groq cobre tudo.

Configurar (uma vez):
  1. Crie uma chave em https://console.groq.com/keys
  2. No SEU PowerShell:  setx GROQ_API_KEY "gsk_..."
  3. Reinicie o Jarvis (config.json -> voz -> stt_nuvem -> ativo: true)
"""

import io
import json
import os
import urllib.request
import uuid
import wave

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELO_PADRAO = "whisper-large-v3"
SAMPLERATE = 16000  # mesmo do stream do assistente


def chave():
    return os.environ.get("GROQ_API_KEY", "").strip()


def pcm_para_wav(audio_bytes, samplerate=SAMPLERATE):
    """Embrulha o PCM cru do buffer (16 kHz mono int16) num WAV valido."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(audio_bytes)
    return buf.getvalue()


def _post_multipart(url, campos, nome_arquivo, arquivo_bytes, headers, timeout):
    """POST multipart/form-data com a stdlib (sem dependencia nova)."""
    limite = "----jarvis-" + uuid.uuid4().hex
    corpo = io.BytesIO()
    for k, v in campos.items():
        corpo.write((f"--{limite}\r\nContent-Disposition: form-data; "
                     f'name="{k}"\r\n\r\n{v}\r\n').encode("utf-8"))
    corpo.write((f"--{limite}\r\nContent-Disposition: form-data; "
                 f'name="file"; filename="{nome_arquivo}"\r\n'
                 "Content-Type: audio/wav\r\n\r\n").encode("utf-8"))
    corpo.write(arquivo_bytes)
    corpo.write(f"\r\n--{limite}--\r\n".encode("utf-8"))

    req = urllib.request.Request(url, data=corpo.getvalue(), headers={
        **headers,
        "Content-Type": f"multipart/form-data; boundary={limite}",
        # o firewall da Groq devolve 403 para o UA padrao do urllib
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/0.5",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def transcrever(audio_bytes, vocabulario=None, modelo=MODELO_PADRAO,
                timeout=8.0):
    """Transcreve a frase na nuvem. Devolve o texto ou None (sem chave,
    audio vazio ou qualquer falha) - o chamador cai para o Whisper local."""
    k = chave()
    if not k or not audio_bytes:
        return None
    campos = {
        "model": modelo,
        "language": "pt",
        "response_format": "json",
        "temperature": "0",
    }
    if vocabulario:
        # mesma dica do Whisper local: nomes que o usuario costuma falar
        campos["prompt"] = "Jarvis, " + ", ".join(vocabulario)
    try:
        resposta = _post_multipart(
            URL, campos, "frase.wav", pcm_para_wav(audio_bytes),
            {"Authorization": f"Bearer {k}"}, timeout)
        texto = (resposta.get("text") or "").strip()
        return texto or None
    except Exception as e:
        print(f"  [nuvem] transcricao falhou ({e}); usando o Whisper local.")
        return None
