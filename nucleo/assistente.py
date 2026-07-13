"""
Jarvis v0.5 - Palmas + voz + cerebro (Claude) + Whisper + memoria + arquivos.

v0.5: o cerebro mexe em arquivos por voz (listar, procurar, criar, ler,
mover, apagar para a Lixeira, analisar CSV) - restrito as pastas do
usuario; apagar/mover exigem "Confirma, senhor?". Em pedidos demorados,
avisa "Ainda trabalhando nisso, senhor" a cada aviso_processando_seg.

v0.4: o cerebro ganhou memoria persistente (memoria.json), pesquisa na
web, busca de programas no Menu Iniciar, atalhos aprendidos (viram
comando fixo no config) e habilidades (scripts que ele mesmo escreve,
executados SO depois do usuario dizer "Jarvis, aprovar habilidade").

Alem dos gatilhos da v0.2, pedidos livres ("Jarvis, toca Bohemian
Rhapsody no Spotify") vao para o Claude (cerebro.py), que interpreta,
executa as acoes e responde com fala gerada na hora (edge-tts).

v0.3.1: o Vosk pt-BR nao conhece palavras em ingles (github, spotify,
videogame...). Quando nenhum comando fixo casa com o texto do Vosk, a
frase e re-transcrita com o Whisper (multilingue, offline) a partir do
audio bufferizado - a ativacao ("Jarvis") continua 100% com o Vosk,
que e leve o bastante para escuta continua.

Fica ouvindo o microfone o tempo todo, com dois gatilhos:

1. DUAS PALMAS em sequencia -> abre os aplicativos e abas do navegador
   definidos no config.json e toca uma fala do Jarvis (igual a v0.1).

2. COMANDO DE VOZ -> diga a palavra de ativacao ("Jarvis") e um comando:
       "Jarvis, abra o navegador"
       "Jarvis"  ...  "abra os aplicativos"
   Os comandos e frases ficam na secao "voz" do config.json.

Reconhecimento de fala offline com Vosk (modelo pt-BR em modelo-vosk/).

Uso:
    python assistente.py

Pare com Ctrl+C, com o "Parar Jarvis.bat" ou dizendo "Jarvis, pode descansar".
"""

import json
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import webbrowser
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd

# Raiz do projeto (este arquivo vive em nucleo/)
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

# Trava de instancia unica: o bind desta porta local falha se outra
# instancia ja estiver rodando. O SO libera a porta sozinho quando o
# processo morre (sem risco de lock orfao apos crash/kill).
PORTA_TRAVA = 51739
_TRAVA = None


def travar_instancia_unica():
    """True se somos a unica instancia; False se o Jarvis ja esta rodando."""
    global _TRAVA
    import socket
    try:
        _TRAVA = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _TRAVA.bind(("127.0.0.1", PORTA_TRAVA))
        return True
    except OSError:
        return False

# 16 kHz mono: taxa exigida pelo modelo Vosk; serve bem para as palmas tambem.
SAMPLERATE = 16000
BLOCKSIZE = 2000  # ~0,125 s por bloco

ENCERRAR = threading.Event()


def carregar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg


def normalizar(texto):
    """minusculas + sem acentos + sem pontuacao, para casar frases faladas.

    A pontuacao vira espaco porque o Whisper transcreve com virgulas e
    pontos ("Jarvis, abra o GitHub.") e o Vosk nao.
    """
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def aplicar_correcoes(norm, correcoes):
    """Troca transcricoes conhecidamente erradas do Vosk pela palavra certa.

    `correcoes` ja deve vir com chaves e valores normalizados.
    """
    for errado, certo in correcoes.items():
        if errado and errado in norm:
            norm = norm.replace(errado, certo)
    return re.sub(r"\s+", " ", norm).strip()


# Sons de fim de palavra que o Vosk usa ao "ouvir" Jarvis: s, z, sse, ce...
_FINS_SIBILANTES = ("s", "z", "se", "ce", "ze")


def casar_ativacao(norm, palavras, limiar):
    """Procura a palavra de ativacao no texto normalizado.

    O modelo pt-BR nao conhece 'jarvis' e transcreve o que conhece:
    'james', 'ja disse', 'jardins', 'ja fiz'... Por isso, alem da lista
    exata `palavras`, aceita casamento APROXIMADO: janelas de 1-2 palavras
    que comecem com 'j', terminem com som de s/z e tenham similaridade
    >= `limiar` com 'jarvis' (difflib).

    Retorna o resto da frase depois da ativacao, ou None se nao achou.
    """
    from difflib import SequenceMatcher

    # 1) casamento exato com a lista do config
    for palavra in palavras:
        pos = norm.find(palavra)
        if pos >= 0:
            return norm[pos + len(palavra):].strip()

    # 2) casamento aproximado por janelas de 1-3 palavras
    tokens = norm.split()
    for i in range(len(tokens)):
        for tam in (3, 2, 1):  # janela maior primeiro ("ja vi se" antes de "ja")
            if i + tam > len(tokens):
                continue
            junto = "".join(tokens[i:i + tam])
            if not junto.startswith("j"):
                continue
            if not junto.endswith(_FINS_SIBILANTES):
                continue
            if SequenceMatcher(None, junto, "jarvis").ratio() >= limiar:
                return " ".join(tokens[i + tam:]).strip()
    return None


def _encontrar_chrome():
    """Tenta localizar o chrome.exe em locais comuns do Windows."""
    candidatos = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    return shutil.which("chrome")


def abrir_abas(cfg):
    urls = cfg.get("abas_navegador", [])
    if not urls:
        return
    navegador = cfg.get("navegador", "chrome").lower()
    chrome = _encontrar_chrome() if navegador == "chrome" else None

    if chrome:
        try:
            subprocess.Popen([chrome] + list(urls))
            print(f"  [abas] Chrome aberto com {len(urls)} aba(s).")
            return
        except Exception as e:
            print(f"  [abas] Falha ao abrir Chrome direto ({e}); usando navegador padrao.")

    for url in urls:
        try:
            webbrowser.open_new_tab(url)
        except Exception as e:
            print(f"  [abas] Erro ao abrir {url}: {e}")
    print(f"  [abas] {len(urls)} aba(s) enviada(s) ao navegador padrao.")


def abrir_aplicativos(cfg):
    apps = cfg.get("aplicativos", [])
    for app in apps:
        abrir_alvo(app)


def abrir_alvo(alvo):
    """Abre um caminho de app/arquivo ou uma URL."""
    alvo = os.path.expandvars(str(alvo))
    if alvo.lower().startswith(("http://", "https://")):
        try:
            webbrowser.open_new_tab(alvo)
            print(f"  [abrir] URL: {alvo}")
        except Exception as e:
            print(f"  [abrir] Erro na URL {alvo}: {e}")
        return
    try:
        os.startfile(alvo)  # type: ignore[attr-defined]
        print(f"  [abrir] Aberto: {alvo}")
    except Exception:
        try:
            subprocess.Popen(alvo, shell=True)
            print(f"  [abrir] Aberto (shell): {alvo}")
        except Exception as e:
            print(f"  [abrir] Erro ao abrir {alvo}: {e}")


def _escolher_audio(cfg):
    """Sorteia um .wav de 'audio_pasta'; senao usa o arquivo unico em 'audio'."""
    pasta = cfg.get("audio_pasta")
    if pasta:
        p = Path(os.path.expandvars(str(pasta)))
        if not p.is_absolute():
            p = BASE_DIR / p
        if p.is_dir():
            wavs = sorted(p.glob("*.wav"))
            if wavs:
                return str(random.choice(wavs))
    return cfg.get("audio")


def tocar_audio(cfg):
    caminho = _escolher_audio(cfg)
    if not caminho:
        return
    caminho = os.path.expandvars(str(caminho))
    if not os.path.isfile(caminho):
        print(f"  [audio] Arquivo nao encontrado: {caminho}")
        return
    try:
        if caminho.lower().endswith(".wav"):
            import winsound
            winsound.PlaySound(caminho, winsound.SND_FILENAME | winsound.SND_ASYNC)
            print(f"  [audio] Tocando: {os.path.basename(caminho)}")
        else:
            os.startfile(caminho)  # type: ignore[attr-defined]
            print(f"  [audio] Enviado ao player padrao: {os.path.basename(caminho)}")
    except Exception as e:
        print(f"  [audio] Erro ao tocar: {e}")


def falar(caminho_wav, interromper=None):
    """Toca uma resposta do Jarvis de forma SINCRONA (espera terminar).

    Sincrono de proposito: enquanto ele fala, nao processamos o microfone,
    para o Jarvis nao 'se ouvir' e tentar reconhecer a propria voz.

    v0.7: se `interromper` (threading.Event) for passado, a fala pode ser
    CORTADA no meio - o evento e setado quando o usuario diz "Jarvis" por
    cima da fala (barge-in). Devolve True se foi interrompida.
    """
    if not caminho_wav:
        return False
    p = Path(os.path.expandvars(str(caminho_wav)))
    if not p.is_absolute():
        p = BASE_DIR / p
    if not p.is_file():
        print(f"  [voz] Resposta nao encontrada: {p}")
        return False
    try:
        import winsound
        if interromper is None:
            winsound.PlaySound(str(p), winsound.SND_FILENAME)
            return False
        import wave
        try:
            with wave.open(str(p), "rb") as w:
                duracao = w.getnframes() / float(w.getframerate() or 1)
        except Exception:
            duracao = 30.0
        interromper.clear()
        winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)
        fim = time.monotonic() + duracao + 0.15
        while time.monotonic() < fim:
            if interromper.wait(0.05):
                winsound.PlaySound(None, winsound.SND_PURGE)
                interromper.clear()
                return True
        return False
    except Exception as e:
        print(f"  [voz] Erro ao falar: {e}")
        return False


def falar_dinamico(texto, voz="pt-BR-AntonioNeural", interromper=None):
    """Gera a fala do texto na hora (edge-tts) e toca de forma sincrona.

    Usa cache em respostas/cache/ para nao gerar duas vezes a mesma frase.
    Levanta excecao se estiver sem internet - o chamador decide o fallback.
    Devolve True se a fala foi interrompida (ver falar()).
    """
    import asyncio
    import hashlib

    pasta = BASE_DIR / "respostas" / "cache"
    pasta.mkdir(parents=True, exist_ok=True)
    chave = hashlib.md5(f"{voz}|{texto}".encode("utf-8")).hexdigest()
    wav = pasta / f"{chave}.wav"

    if not wav.is_file():
        import edge_tts
        import imageio_ffmpeg

        mp3 = wav.with_suffix(".mp3")

        async def gerar():
            await edge_tts.Communicate(texto, voz, rate="-5%").save(str(mp3))

        asyncio.run(gerar())
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(mp3),
             "-ar", "44100", "-ac", "2", str(wav)],
            check=True,
        )
        mp3.unlink(missing_ok=True)

    return falar(wav, interromper)


def executar_acoes(cfg):
    """Dispara todas as acoes das duas palmas em paralelo."""
    print(">>> DUAS PALMAS DETECTADAS - executando acoes!")
    alvos = [abrir_abas, abrir_aplicativos, tocar_audio]
    threads = [threading.Thread(target=fn, args=(cfg,), daemon=True) for fn in alvos]
    for t in threads:
        t.start()


class GanhoAdaptativo:
    """Ganho automatico (AGC) do audio do reconhecimento de voz (v0.6).

    O ganho fixo alto (ex.: 15x) fazia a fala SATURAR (clipping) sempre
    que havia barulho de fundo - o audio distorcido confundia o Vosk e o
    Whisper. Aqui o ganho se adapta: sobe devagar ate o teto (ganho_voz)
    quando o som esta baixo e despenca na hora quando o sinal amplificado
    estoura. Desligue com microfone.agc: false (volta ao ganho fixo).
    """

    def __init__(self, ganho_max, alvo=0.6):
        self.ganho_max = max(1.0, float(ganho_max))
        self.alvo = float(alvo)
        self.envelope = 0.05  # pico recente do sinal cru; decai em ~10 s
        self.ganho = min(4.0, self.ganho_max)

    def aplicar(self, indata):
        """Recebe o bloco int16 cru e devolve os bytes amplificados."""
        pico = float(np.max(np.abs(indata.astype(np.int32)))) / 32768.0
        # o envelope segue o pico na subida e decai devagar: o ganho nao
        # dispara nas pausas curtas entre as palavras
        self.envelope = max(pico, self.envelope * 0.97, 1e-3)
        desejado = min(self.ganho_max, max(1.0, self.alvo / self.envelope))
        if desejado < self.ganho:
            self.ganho = desejado  # desce na hora (anti-clipping)
        else:
            self.ganho += 0.08 * (desejado - self.ganho)  # sobe suave
        amp = np.clip(indata.astype(np.float32) * self.ganho, -32768, 32767)
        return amp.astype(np.int16).tobytes()


class DetectorPalmas:
    def __init__(self, cfg):
        d = cfg.get("deteccao", {})
        self.limite = float(d.get("limite_volume", 0.35))
        self.min_gap = float(d.get("intervalo_min_seg", 0.15))
        self.max_gap = float(d.get("intervalo_max_seg", 1.2))
        self.cooldown = float(d.get("cooldown_seg", 5.0))
        self.pausa = float(d.get("pausa_entre_palmas_seg", 0.25))
        # v0.6 - analise espectral: reduz falsos positivos (voz, musica,
        # batidas na mesa) exigindo o perfil de uma palma de verdade
        self.espectral = bool(d.get("analise_espectral", True))
        self.min_agudos = float(d.get("min_agudos", 0.25))
        self.min_crista = float(d.get("min_crista", 3.0))

        self.cfg = cfg
        self.ultima_palma = 0.0
        self.penultima_palma = 0.0
        self.ultimo_disparo = 0.0
        self.lock = threading.Lock()

    def _parece_palma(self, bloco):
        """Palma = transiente IMPULSIVO de BANDA LARGA.

        Voz, musica e TV concentram a energia nos graves (< 1,5 kHz) e
        tem envelope continuo; a palma espalha energia ate os agudos e
        dura poucos milissegundos. Dois testes no bloco do pico:
        - agudos: fracao da energia acima de 2 kHz (palma: alta);
        - crista: pico/RMS (impulso: alto; som continuo: baixo).
        """
        x = np.asarray(bloco).reshape(-1).astype(np.float32)
        if x.size == 0:
            return True
        pico = float(np.max(np.abs(x)))
        rms = float(np.sqrt(np.mean(x * x))) + 1e-9
        crista = pico / rms
        espectro = np.abs(np.fft.rfft(x)) ** 2
        freqs = np.fft.rfftfreq(x.size, 1.0 / SAMPLERATE)
        total = float(espectro.sum()) + 1e-9
        agudos = float(espectro[freqs >= 2000.0].sum()) / total
        if agudos >= self.min_agudos and crista >= self.min_crista:
            return True
        print(f"[palma] pico ignorado (agudos={agudos:.2f} "
              f"crista={crista:.1f}) - nao tem cara de palma")
        return False

    def processar_pico(self, pico, bloco=None):
        agora = time.monotonic()
        if pico < self.limite:
            return
        if self.espectral and bloco is not None and not self._parece_palma(bloco):
            return

        with self.lock:
            if agora - self.ultima_palma < self.pausa:
                return
            if agora - self.ultimo_disparo < self.cooldown:
                self.ultima_palma = agora
                return

            self.penultima_palma = self.ultima_palma
            self.ultima_palma = agora
            gap = self.ultima_palma - self.penultima_palma

            print(f"[palma] pico={pico:.2f}  intervalo={gap:.2f}s")

            if self.min_gap <= gap <= self.max_gap:
                self.ultimo_disparo = agora
                self.ultima_palma = 0.0
                self.penultima_palma = 0.0
                try:
                    cfg_atual = carregar_config()
                except Exception as e:
                    print(f"  [config] Erro ao reler ({e}); usando o anterior.")
                    cfg_atual = self.cfg
                executar_acoes(cfg_atual)


# Palavras que confirmam/negam uma acao destrutiva retida (estado CONFIRMACAO)
PALAVRAS_SIM = {"sim", "confirmo", "confirma", "confirmado", "pode", "claro",
                "isso", "afirmativo"}
PALAVRAS_NAO = {"nao", "negativo"}
# Palavras que abortam um pedido em andamento (estado PROCESSANDO)
PALAVRAS_CANCELAR = {"cancela", "cancelar", "cancele", "pare", "para"}

# v0.7 - barge-in: o modelo pt-BR nao conhece 'jarvis'; quando alguem diz
# "Jarvis" por cima da fala, a gramatica limitada do reconhecedor de
# interrupcao decodifica como um destes apelidos foneticos (validado com
# TTS: "Jarvis!" vira "chaves"; a fala normal do Jarvis vira so [unk]).
BARGE_ALVOS = {"james", "jarbas", "jazz", "chaves", "java", "davis"}


class OuvinteVoz(threading.Thread):
    """Consome o audio numa fila e reconhece fala com Vosk.

    Estados:
      OCIOSO      - espera alguem dizer a palavra de ativacao ("Jarvis").
                    Se o comando vier na mesma frase, executa direto.
      COMANDO     - depois do "Pois nao?", espera a frase de comando por
                    alguns segundos; executa ou responde "nao entendi".
      PROCESSANDO - o cerebro esta trabalhando numa thread separada; o mic
                    continua aberto SO para ouvir "Jarvis, cancela".
      CONFIRMACAO - uma acao destrutiva esta retida esperando "sim"/"nao";
                    silencio ou outro assunto cancelam a acao.
    """

    def __init__(self, cfg, fila):
        super().__init__(daemon=True)
        from vosk import Model, KaldiRecognizer, SetLogLevel

        SetLogLevel(-1)
        v = cfg.get("voz", {})
        pasta_modelo = BASE_DIR / v.get("modelo", "modelo-vosk")
        if not pasta_modelo.is_dir():
            raise FileNotFoundError(f"Modelo Vosk nao encontrado em {pasta_modelo}")

        print("  Carregando modelo de voz (alguns segundos)...")
        self.modelo = Model(str(pasta_modelo))
        self.rec = KaldiRecognizer(self.modelo, SAMPLERATE)

        self.cfg = cfg
        self.fila = fila
        self.ativacao = [normalizar(p) for p in v.get("palavras_ativacao", ["jarvis"])]
        self.similaridade = float(v.get("similaridade_ativacao", 0.5))
        self.timeout_comando = float(v.get("timeout_comando_seg", 8.0))
        self.modo_conversa = bool(v.get("modo_conversa", True))
        self.janela_conversa = float(v.get("janela_conversa_seg", 12.0))
        self.respostas = v.get("respostas", {})
        self.comandos = v.get("comandos", [])
        self.correcoes = {normalizar(k): normalizar(val)
                          for k, val in v.get("correcoes", {}).items()}
        self.vocabulario = cfg.get("vocabulario", [])

        self.timeout_confirmacao = float(v.get("timeout_confirmacao_seg", 10.0))
        self.palavras_cancelar = {normalizar(p) for p in v.get(
            "palavras_cancelar", [])} or set(PALAVRAS_CANCELAR)
        # v0.5 - aviso intermediario: pesquisas longas passam de 20-30 s em
        # silencio apos o unico "Um momento"; sem isto parece travamento.
        self.aviso_processando = float(v.get("aviso_processando_seg", 15.0))

        # v0.7 - interromper a fala: enquanto o Jarvis fala, o mic alimenta
        # um SEGUNDO reconhecedor (gramatica minuscula: so a ativacao) - se
        # ouvir "Jarvis" por cima, corta o audio e abre a escuta.
        self.interromper_fala_evt = threading.Event()
        self.fila_barge = queue.Queue(maxsize=40)
        self.barge_ativo = bool(v.get("interromper_fala", True))
        if self.barge_ativo:
            try:
                gram = sorted(BARGE_ALVOS) + ["[unk]"]
                self.rec_barge = KaldiRecognizer(self.modelo, SAMPLERATE,
                                                 json.dumps(gram))
                threading.Thread(target=self._escutar_barge,
                                 daemon=True).start()
            except Exception as e:
                print(f"  [voz] Interrupcao de fala indisponivel ({e}).")
                self.barge_ativo = False

        self.estado = "OCIOSO"
        self.prazo_comando = 0.0
        self.prazo_processando = 0.0
        self.falando = threading.Event()  # gate: ignora mic enquanto o Jarvis fala
        self.cancelar_pedido = threading.Event()  # "Jarvis, cancela"
        # o cerebro agora responde numa thread separada; este lock protege o
        # KaldiRecognizer (Reset x AcceptWaveform de threads diferentes)
        self.rec_lock = threading.Lock()

        # v0.5.1 - transcricao na nuvem (Groq, Whisper large-v3): mais
        # precisa que o local; cai para o Whisper local sem chave/internet.
        n = v.get("stt_nuvem", {})
        self.nuvem_ativa = bool(n.get("ativo", False))
        self.nuvem_modelo = n.get("modelo", "whisper-large-v3")
        if self.nuvem_ativa:
            import stt_nuvem
            if not stt_nuvem.chave():
                print("  [nuvem] GROQ_API_KEY nao definida; "
                      "usando so o Whisper local.")
                self.nuvem_ativa = False

        # v0.3.1 - Whisper re-transcreve a frase quando o Vosk nao resolve
        # (palavras em ingles). Buffer guarda o audio da frase atual;
        # 280 blocos de ~0,125 s = ~35 s, mais que qualquer frase.
        self.buffer_frase = deque(maxlen=280)
        self.whisper = None
        w = v.get("whisper", {})
        if w.get("ativo", False):
            try:
                from faster_whisper import WhisperModel
                nome = w.get("modelo", "small")
                print(f"  Carregando Whisper '{nome}' (alguns segundos)...")
                self.whisper = WhisperModel(nome, device="cpu", compute_type="int8")
            except Exception as e:
                print(f"  [whisper] Desativado ({e}); usando so o Vosk.")

        # v0.3 - cerebro (Claude). Opcional: sem SDK/chave, o Jarvis segue na v0.2.
        self.cerebro = None
        self.voz_tts = cfg.get("cerebro", {}).get("voz", "pt-BR-AntonioNeural")
        if cfg.get("cerebro", {}).get("ativo", False):
            try:
                from cerebro import Cerebro
                self.cerebro = Cerebro(cfg)
                self.cerebro.cancelar = self.cancelar_pedido
                print(f"  Cerebro ativo: {self.cerebro.modelo}")
            except Exception as e:
                print(f"  [cerebro] Desativado: {e}")

    # ---------- reconhecimento ----------

    def run(self):
        while not ENCERRAR.is_set():
            try:
                dados = self.fila.get(timeout=0.2)
            except queue.Empty:
                self._checar_timeout()
                continue

            try:
                self.buffer_frase.append(dados)
                with self.rec_lock:
                    fechou = self.rec.AcceptWaveform(dados)
                    resultado = self.rec.Result() if fechou else ""
                if fechou:
                    texto = json.loads(resultado).get("text", "").strip()
                    audio = b"".join(self.buffer_frase)
                    self.buffer_frase.clear()
                    if texto:
                        self._tratar_frase(texto, audio)
                self._checar_timeout()
            except Exception:
                # nunca deixa a thread de voz morrer em silencio
                import traceback
                print("[voz] ERRO na thread de voz:")
                traceback.print_exc()

    def _checar_timeout(self):
        agora = time.monotonic()
        if self.estado == "COMANDO" and agora > self.prazo_comando:
            print("  [voz] Nenhum comando ouvido; voltando a espera.")
            self.estado = "OCIOSO"
        elif self.estado == "CONFIRMACAO" and agora > self.prazo_comando:
            # silencio cancela a acao destrutiva (padrao seguro)
            print("  [voz] Sem confirmacao; acao cancelada.")
            if self.cerebro is not None:
                self.cerebro.cancelar_pendente()
            self.estado = "OCIOSO"
        elif self.estado == "PROCESSANDO" and agora > self.prazo_processando:
            # rede de seguranca: se o cerebro travar, o Jarvis nao fica surdo
            print("  [voz] Processamento demorou demais; abortando o pedido.")
            self.cancelar_pedido.set()
            self.estado = "OCIOSO"

    def _tratar_frase(self, texto, audio=b""):
        norm = aplicar_correcoes(normalizar(texto), self.correcoes)
        print(f'[voz] ouvi ({self.estado}): "{texto}"')

        if self.estado == "PROCESSANDO":
            # o cerebro esta trabalhando: a unica coisa que importa e "cancela"
            if set(norm.split()) & self.palavras_cancelar:
                print("  [voz] Cancelamento pedido pelo senhor.")
                self.cancelar_pedido.set()
            return

        if self.estado == "CONFIRMACAO":
            tokens = set(norm.split())
            if tokens & PALAVRAS_SIM:
                self.estado = "OCIOSO"
                self._executar_confirmada()
                return
            if tokens & PALAVRAS_NAO or tokens & self.palavras_cancelar:
                self.estado = "OCIOSO"
                if self.cerebro is not None:
                    self.cerebro.cancelar_pendente()
                self._falar_resposta("cancelado")
                self._abrir_conversa()
                return
            # mudou de assunto: cancela a pendencia e trata como comando normal
            if self.cerebro is not None:
                self.cerebro.cancelar_pendente()
            self.estado = "COMANDO"

        if self.estado == "COMANDO":
            self.estado = "OCIOSO"
            acao, melhor = self._casar_ou_transcrever(norm, texto, audio)
            if acao is not None:
                if acao not in ("sair", "fim"):
                    self._abrir_conversa()
                return
            if self.cerebro is not None:
                # processa em outra thread; quem reabre a conversa (ou pede
                # confirmacao) e o proprio worker ao terminar.
                self._consultar_cerebro(melhor)
                return
            self._falar_resposta("nao_entendi")
            self._abrir_conversa()
            return

        # OCIOSO: procura a palavra de ativacao (exata ou aproximada)
        resto = casar_ativacao(norm, self.ativacao, self.similaridade)
        print(f"  [debug] ativacao={'SIM' if resto is not None else 'nao'}"
              f"{f' resto={resto!r}' if resto else ''}")
        if resto is None:
            return
        if resto:
            # O texto do Whisper inclui o "Jarvis" do inicio - nao tem
            # problema: comandos casam por trecho contido e o Claude
            # entende ser chamado pelo nome.
            acao, melhor = self._casar_ou_transcrever(resto, resto, audio)
            if acao is not None:
                if acao not in ("sair", "fim"):
                    self._abrir_conversa()
                return  # comando fixo veio na mesma frase
            if self.cerebro is not None:
                self._consultar_cerebro(melhor)  # pedido livre na mesma frase
                return
        self._falar_resposta("ativacao")
        self.estado = "COMANDO"
        self.prazo_comando = time.monotonic() + self.timeout_comando
        print(f"  [voz] Aguardando comando ({self.timeout_comando:.0f}s)...")

    def _casar_ou_transcrever(self, norm, texto, audio):
        """Tenta o comando fixo com o texto do Vosk (caminho instantaneo);
        se nao casar, re-transcreve a frase com o Whisper e tenta de novo.

        Devolve (acao, texto): a acao do comando fixo executado (None se
        nenhum casou) e o melhor texto disponivel para mandar ao cerebro.
        """
        acao = self._executar_se_comando(norm)
        if acao is not None:
            return acao, texto
        wtexto = self._transcrever_frase(audio)
        if wtexto:
            wnorm = aplicar_correcoes(normalizar(wtexto), self.correcoes)
            return self._executar_se_comando(wnorm), wtexto
        return None, texto

    def _transcrever_frase(self, audio):
        """Melhor transcricao disponivel da frase bufferizada:
        nuvem (Groq large-v3) -> Whisper local -> None (fica o Vosk)."""
        if self.nuvem_ativa and audio:
            import stt_nuvem
            texto = stt_nuvem.transcrever(audio, self.vocabulario,
                                          self.nuvem_modelo)
            if texto:
                print(f'  [nuvem] ouvi: "{texto}"')
                return texto
        return self._transcrever_whisper(audio)

    def _transcrever_whisper(self, audio_bytes):
        """Re-transcreve a frase bufferizada com o Whisper (entende ingles).

        Devolve o texto ou None (whisper inativo, audio vazio ou falha) -
        o chamador segue com o texto do Vosk.
        """
        if self.whisper is None or not audio_bytes:
            return None
        try:
            amostras = (np.frombuffer(audio_bytes, dtype=np.int16)
                        .astype(np.float32) / 32768.0)
            dica = None
            if self.vocabulario:
                dica = "Jarvis, " + ", ".join(self.vocabulario)
            segmentos, _ = self.whisper.transcribe(
                amostras,
                language="pt",
                beam_size=3,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=dica,
            )
            wtexto = " ".join(s.text.strip() for s in segmentos).strip()
            if wtexto:
                print(f'  [whisper] ouvi: "{wtexto}"')
            return wtexto or None
        except Exception as e:
            print(f"  [whisper] Falha ao transcrever ({e}).")
            return None

    def _executar_se_comando(self, norm):
        """Executa o comando fixo que casar e devolve a acao; None se nenhum."""
        try:
            # v0.4: rele os comandos do config a cada frase - atalhos criados
            # pelo cerebro (criar_atalho) passam a valer sem reiniciar.
            self.comandos = carregar_config().get("voz", {}).get(
                "comandos", self.comandos)
        except Exception:
            pass
        for cmd in self.comandos:
            for frase in cmd.get("frases", []):
                if normalizar(frase) in norm:
                    self._executar_comando(cmd)
                    return cmd.get("acao", "")
        return None

    def _abrir_conversa(self):
        """Reabre a janela de comando apos uma resposta (modo conversa):
        da para emendar o proximo pedido sem repetir 'Jarvis'."""
        if not self.modo_conversa or ENCERRAR.is_set():
            self.estado = "OCIOSO"
            return
        self.estado = "COMANDO"
        self.prazo_comando = time.monotonic() + self.janela_conversa
        print(f"  [voz] Conversa aberta ({self.janela_conversa:.0f}s) - "
              f"pode pedir mais; diga 'obrigado' para encerrar.")

    # ---------- acoes ----------

    def _executar_comando(self, cmd):
        acao = cmd.get("acao", "")
        print(f"  [voz] Comando reconhecido: acao={acao}")
        try:
            cfg = carregar_config()
        except Exception:
            cfg = self.cfg

        self._falar_arquivo(cmd.get("resposta"))

        if acao == "abas":
            threading.Thread(target=abrir_abas, args=(cfg,), daemon=True).start()
        elif acao == "apps":
            threading.Thread(target=abrir_aplicativos, args=(cfg,), daemon=True).start()
        elif acao == "tudo":
            executar_acoes(cfg)
        elif acao == "abrir":
            alvo = cmd.get("alvo")
            if alvo:
                threading.Thread(target=abrir_alvo, args=(alvo,), daemon=True).start()
        elif acao == "fim":
            pass  # so agradece; a janela de conversa nao reabre
        elif acao == "aprovar_habilidade":
            self._aprovar_habilidade()
        elif acao == "sair":
            print("  [voz] Encerrando o Jarvis a pedido do senhor.")
            ENCERRAR.set()
        else:
            print(f"  [voz] Acao desconhecida no config: {acao!r}")

    # ---------- habilidades (v0.4) ----------

    def _aprovar_habilidade(self):
        """Aprova a ultima habilidade pendente criada pelo cerebro.

        A aprovacao e SEMPRE por voz do usuario (este comando fixo) - o
        cerebro cria o script, mas nunca o executa sem passar por aqui.
        """
        try:
            import aprendizado
            nome = aprendizado.aprovar_ultima_habilidade()
        except Exception as e:
            print(f"  [voz] Erro ao aprovar habilidade: {e}")
            nome = None
        if nome:
            print(f"  [voz] Habilidade aprovada: {nome}")
            self._falar_texto(f"Habilidade {nome.replace('-', ' ')} aprovada, senhor.")
        else:
            print("  [voz] Nenhuma habilidade pendente.")
            self._falar_texto("Nao ha habilidade pendente de aprovacao, senhor.")

    def _falar_texto(self, texto):
        """Fala um texto gerado na hora, com o mesmo anti-eco das respostas fixas."""
        self.falando.set()
        cortada = False
        try:
            cortada = falar_dinamico(texto, self.voz_tts,
                                     self._evento_corte(texto))
        except Exception as e:
            print(f'  [voz] TTS indisponivel ({e}): "{texto}"')
        finally:
            self._descartar_captura()
        if cortada:
            self._pos_corte()

    def _descartar_captura(self):
        """Descarta o que o mic captou enquanto o Jarvis falava, para ele
        nao reconhecer a propria voz. Chamado tambem da thread do cerebro,
        por isso o lock em volta do recognizer."""
        try:
            while True:
                self.fila.get_nowait()
        except queue.Empty:
            pass
        try:
            while True:
                self.fila_barge.get_nowait()
        except queue.Empty:
            pass
        self.buffer_frase.clear()
        with self.rec_lock:
            self.rec.Reset()
        self.falando.clear()

    # ---------- interromper a fala (v0.7) ----------

    def _escutar_barge(self):
        """Escuta 'Jarvis' ENQUANTO o proprio Jarvis fala.

        Roda numa thread propria com um reconhecedor de gramatica
        minuscula (BARGE_ALVOS + [unk]): tudo que nao parecer a palavra
        de ativacao vira [unk] e e ignorado - por isso o eco da propria
        voz do Jarvis no microfone nao dispara nada.
        """
        while not ENCERRAR.is_set():
            try:
                dados = self.fila_barge.get(timeout=0.3)
            except queue.Empty:
                continue
            if not self.falando.is_set():
                continue  # sobra de audio de depois da fala: descarta
            try:
                if self.rec_barge.AcceptWaveform(dados):
                    texto = json.loads(self.rec_barge.Result()).get("text", "")
                else:
                    texto = json.loads(
                        self.rec_barge.PartialResult()).get("partial", "")
                if set(texto.split()) & BARGE_ALVOS:
                    print("  [voz] 'Jarvis' por cima da fala - cortando.")
                    self.interromper_fala_evt.set()
                    self.rec_barge.Reset()
            except Exception:
                pass  # barge-in nunca derruba nada

    def _evento_corte(self, texto=None):
        """Evento de interrupcao para uma fala, ou None se nao se aplica.

        Se o PROPRIO texto falado contiver uma palavra-alvo (ex.: 'as
        chaves estao na gaveta', 'playlist de jazz'), o barge-in e
        desligado NESTA fala - senao o eco cortaria a resposta no meio.
        """
        if not self.barge_ativo:
            return None
        if texto and set(normalizar(texto).split()) & BARGE_ALVOS:
            return None
        return self.interromper_fala_evt

    def _pos_corte(self):
        """Fala cortada com 'Jarvis': abre a escuta na hora."""
        if ENCERRAR.is_set():
            return
        self.estado = "COMANDO"
        self.prazo_comando = time.monotonic() + self.timeout_comando
        print(f"  [voz] Fala interrompida; ouvindo "
              f"({self.timeout_comando:.0f}s)...")

    # ---------- cerebro (v0.3) ----------

    def _consultar_cerebro(self, texto):
        """Dispara o pedido ao Claude numa thread separada (nao bloqueia).

        Enquanto o cerebro trabalha (estado PROCESSANDO), o mic continua
        aberto SO para ouvir "Jarvis, cancela". Quem fala a resposta e
        decide o proximo estado (conversa aberta, confirmacao pendente ou
        ocioso) e o worker _trabalhar_cerebro.
        """
        self.estado = "PROCESSANDO"
        self.prazo_processando = time.monotonic() + 120.0
        self.cancelar_pedido.clear()
        threading.Thread(target=self._trabalhar_cerebro, args=(texto,),
                         daemon=True).start()

    def _tocar_async(self, caminho):
        """Toca um wav curto SEM bloquear e sem fechar o mic (avisos de
        espera enquanto o cerebro trabalha - o mic segue aberto para o
        'Jarvis, cancela')."""
        if not caminho:
            return
        p = Path(os.path.expandvars(str(caminho)))
        if not p.is_absolute():
            p = BASE_DIR / p
        if not p.is_file():
            return
        try:
            import winsound
            winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass

    def _avisar_demora(self, terminou):
        """Enquanto o cerebro nao responde, toca 'Ainda trabalhando nisso,
        senhor' a cada aviso_processando_seg - o silencio de uma pesquisa
        longa nao pode parecer a 'falsa surdez' de novo."""
        if self.aviso_processando <= 0:
            return
        while not terminou.wait(self.aviso_processando):
            if ENCERRAR.is_set() or self.cancelar_pedido.is_set():
                return
            print("  [voz] Pedido demorado; avisando que segue em andamento.")
            self._tocar_async(self.respostas.get("ainda_trabalhando"))

    def _trabalhar_cerebro(self, texto):
        from cerebro import PedidoCancelado

        try:
            # "Um momento, senhor..." em paralelo, enquanto o Claude pensa
            self._tocar_async(self.respostas.get("um_momento"))
            terminou = threading.Event()
            threading.Thread(target=self._avisar_demora, args=(terminou,),
                             daemon=True).start()

            try:
                resposta = self.cerebro.processar(texto)
            except PedidoCancelado:
                print("  [cerebro] pedido cancelado pelo senhor.")
                self.estado = "OCIOSO"
                self._falar_resposta("cancelado")
                return
            finally:
                terminou.set()
            if self.cancelar_pedido.is_set():
                # cancelou depois que a resposta ficou pronta: nao fala nada
                print("  [cerebro] pedido cancelado (resposta descartada).")
                self.estado = "OCIOSO"
                self._falar_resposta("cancelado")
                return
            if resposta.strip() == "[IGNORAR]":
                print("  [cerebro] fala ambiente - ignorada em silencio.")
                self.estado = "OCIOSO"
                return
            print(f'  [cerebro] resposta: "{resposta}"')
            self._falar_texto(resposta)

            # acao destrutiva retida? espera o "sim"/"nao" do usuario
            if getattr(self.cerebro, "acao_pendente", None):
                self.estado = "CONFIRMACAO"
                self.prazo_comando = time.monotonic() + self.timeout_confirmacao
                print(f"  [voz] Aguardando confirmacao "
                      f"({self.timeout_confirmacao:.0f}s)... diga sim ou nao.")
            else:
                self._abrir_conversa()
        except Exception as e:
            print(f"  [cerebro] Erro: {e}")
            self.estado = "OCIOSO"
            self._falar_resposta("erro_cerebro")

    def _executar_confirmada(self):
        """Executa a acao destrutiva que o usuario acabou de confirmar."""
        saida = None
        try:
            saida = self.cerebro.executar_pendente()
        except Exception as e:
            print(f"  [voz] Erro ao executar acao confirmada: {e}")
        if saida is not None and not str(saida).startswith("ERRO"):
            self._falar_resposta("feito")
        else:
            self._falar_resposta("acao_falhou")
        self._abrir_conversa()

    # ---------- fala ----------

    def _falar_resposta(self, chave):
        self._falar_arquivo(self.respostas.get(chave))

    def _falar_arquivo(self, caminho):
        if not caminho:
            return
        self.falando.set()
        cortada = False
        try:
            cortada = falar(caminho, self._evento_corte())
        finally:
            self._descartar_captura()
        if cortada:
            self._pos_corte()


def main():
    if not travar_instancia_unica():
        print("O Jarvis JA ESTA RODANDO (em outra janela ou em segundo plano).")
        print('Duas instancias ouvem uma a outra e conversam sozinhas.')
        print('Use o "Parar Jarvis.bat" antes de iniciar de novo.')
        sys.exit(0)

    if not CONFIG_PATH.exists():
        print(f"config.json nao encontrado em {CONFIG_PATH}")
        sys.exit(1)

    cfg = carregar_config()
    detector = DetectorPalmas(cfg)

    voz_cfg = cfg.get("voz", {})
    voz_ativa = bool(voz_cfg.get("ativa", True))
    # ganho digital aplicado SO ao audio do reconhecimento de voz
    # (as palmas continuam medindo o sinal cru, ja calibrado).
    # v0.6: com agc (padrao), ganho_voz vira o TETO e o ganho se adapta
    # sozinho - o fixo saturava a fala quando havia barulho de fundo.
    mic_cfg = cfg.get("microfone", {})
    ganho = float(mic_cfg.get("ganho_voz", 1.0))
    agc = GanhoAdaptativo(ganho) if bool(mic_cfg.get("agc", True)) else None
    fila = queue.Queue(maxsize=200)

    ouvinte = None
    if voz_ativa:
        try:
            ouvinte = OuvinteVoz(cfg, fila)
        except Exception as e:
            print(f"  [voz] Reconhecimento de voz desativado: {e}")

    def callback(indata, frames, time_info, status):
        if ouvinte is not None and ouvinte.falando.is_set():
            # Jarvis esta falando: o reconhecimento normal fica fechado
            # (anti-eco), mas o barge-in escuta um "Jarvis" por cima
            if ouvinte.barge_ativo:
                try:
                    ouvinte.fila_barge.put_nowait(indata.tobytes())
                except queue.Full:
                    pass
            return
        pico = float(np.max(np.abs(indata.astype(np.int32)))) / 32768.0
        detector.processar_pico(pico, indata)
        if ouvinte is not None:
            if agc is not None:
                dados = agc.aplicar(indata)
            elif ganho != 1.0:
                amp = np.clip(indata.astype(np.int32) * ganho, -32768, 32767)
                dados = amp.astype(np.int16).tobytes()
            else:
                dados = indata.tobytes()
            try:
                fila.put_nowait(dados)
            except queue.Full:
                pass  # reconhecimento atrasado: descarta o bloco

    print("=" * 55)
    print("  JARVIS v0.5 - voz + cerebro + memoria + arquivos")
    print("=" * 55)
    print(f"  Limite de volume : {detector.limite}")
    print(f"  Intervalo palmas : {detector.min_gap}s a {detector.max_gap}s")
    print(f"  Cooldown         : {detector.cooldown}s")
    print(f"  Filtro espectral : {'ativo' if detector.espectral else 'inativo'}"
          " (palmas)")
    print(f"  Ganho do mic     : "
          f"{f'adaptativo (ate {ganho:g}x)' if agc is not None else f'fixo {ganho:g}x'}")
    print(f"  Abas             : {len(cfg.get('abas_navegador', []))}")
    print(f"  Apps             : {len(cfg.get('aplicativos', []))}")
    if voz_ativa and ouvinte is not None:
        print(f"  Ativacao por voz : {', '.join(voz_cfg.get('palavras_ativacao', ['jarvis']))}")
        print(f"  Comandos de voz  : {len(voz_cfg.get('comandos', []))}")
        whisper_st = "ativo" if ouvinte.whisper is not None else "inativo"
        print(f"  Whisper (ingles) : {whisper_st}")
        print(f"  Nuvem (Groq)     : {'ativa' if ouvinte.nuvem_ativa else 'inativa'}")
        print(f"  Interromper fala : "
              f"{'ativo (diga Jarvis por cima)' if ouvinte.barge_ativo else 'inativo'}")
    print("-" * 55)
    print('  Ouvindo... bata DUAS palmas ou diga "Jarvis". (Ctrl+C sai)')
    print("=" * 55)

    if ouvinte is not None:
        ouvinte.start()

    try:
        with sd.InputStream(
            channels=1,
            samplerate=SAMPLERATE,
            blocksize=BLOCKSIZE,
            dtype="int16",
            callback=callback,
        ):
            while not ENCERRAR.is_set():
                time.sleep(0.1)
                # watchdog: se a thread de voz morrer, sai com codigo != 0
                # para o supervisor.py reiniciar o Jarvis inteiro
                if ouvinte is not None and not ouvinte.is_alive():
                    print("[watchdog] Thread de voz morreu; reiniciando pelo supervisor.")
                    sys.exit(2)
        print("Encerrado. Ate mais, senhor!")
    except KeyboardInterrupt:
        print("\nEncerrado. Ate mais!")
    except Exception as e:
        print(f"\nErro no fluxo de audio: {e}")
        print("Verifique se o microfone esta conectado e habilitado.")
        sys.exit(1)


if __name__ == "__main__":
    main()
