"""
Lembretes e timers por voz - v0.9.

"Jarvis, me lembra em 20 minutos de tirar o bolo", "me acorda as 15h".
O cerebro converte o tempo falado (em_segundos OU horario "HH:MM") e
chama criar(); a thread vigia deste modulo observa dados/lembretes.json
e, na hora certa, fala a mensagem pela voz do Jarvis (callback FALAR,
plugado pelo assistente).

Persistente de proposito: lembretes sobrevivem a reinicios (crash +
supervisor, "pode descansar" + boot seguinte). Se a hora passou com o
Jarvis desligado, ele dispara no proximo boot avisando o atraso.
"""

import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARQUIVO = BASE_DIR / "dados" / "lembretes.json"

MAX_LEMBRETES = 50
MAX_SEGUNDOS = 7 * 24 * 3600  # ate 7 dias no futuro

_lock = threading.RLock()
_mudou = threading.Event()  # acorda a vigia quando a lista muda
_vigia_iniciada = False

# Plugado pelo assistente: funcao que fala um texto em voz alta.
# None = sem voz (os disparos ficam so no log).
FALAR = None


# ---------- persistencia ----------

def _carregar():
    """Lista de lembretes validos; entradas corrompidas sao descartadas."""
    try:
        with open(ARQUIVO, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(dados, list):
        return []
    validos = []
    for item in dados:
        try:
            datetime.fromisoformat(item["quando"])
            str(item["mensagem"])
            validos.append(item)
        except (KeyError, TypeError, ValueError):
            continue  # lixo no json nao pode travar os demais
    return validos


def _salvar(lembretes):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(lembretes, f, ensure_ascii=False, indent=2)


def _quando(lembrete):
    return datetime.fromisoformat(lembrete["quando"])


def _formatar(dt, agora=None):
    """'hoje às 15:00', 'amanhã às 08:00' ou '20/07 às 15:00'."""
    agora = agora or datetime.now()
    hora = dt.strftime("%H:%M")
    if dt.date() == agora.date():
        return f"hoje às {hora}"
    if dt.date() == (agora + timedelta(days=1)).date():
        return f"amanhã às {hora}"
    return f"{dt.strftime('%d/%m')} às {hora}"


# ---------- ferramentas do cerebro ----------

def criar(mensagem, em_segundos=None, horario=None):
    """Agenda um lembrete. Devolve a frase de confirmacao (ou ERRO...)."""
    mensagem = str(mensagem or "").strip()
    if not mensagem:
        return "ERRO: lembrete sem mensagem."
    agora = datetime.now()

    if em_segundos is not None:
        try:
            seg = int(em_segundos)
        except (TypeError, ValueError):
            return "ERRO: em_segundos deve ser um inteiro (segundos)."
        if not 5 <= seg <= MAX_SEGUNDOS:
            return "ERRO: o prazo deve ficar entre 5 segundos e 7 dias."
        quando = agora + timedelta(seconds=seg)
    elif horario:
        m = re.fullmatch(r"(\d{1,2})(?:[:h.](\d{1,2}))?h?",
                         str(horario).strip().lower())
        if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
            return f"ERRO: horário inválido '{horario}' (use HH:MM, 24h)."
        quando = agora.replace(hour=int(m.group(1)),
                               minute=int(m.group(2) or 0),
                               second=0, microsecond=0)
        if quando <= agora:
            quando += timedelta(days=1)  # ja passou hoje: proxima e amanha
    else:
        return "ERRO: informe em_segundos ou horario."

    with _lock:
        pendentes_ = _carregar()
        if len(pendentes_) >= MAX_LEMBRETES:
            return (f"ERRO: já há {MAX_LEMBRETES} lembretes pendentes; "
                    "cancele algum antes.")
        pendentes_.append({
            "id": uuid.uuid4().hex[:6],
            "mensagem": mensagem,
            "quando": quando.isoformat(timespec="seconds"),
            "criado": agora.isoformat(timespec="seconds"),
        })
        pendentes_.sort(key=lambda l: l["quando"])
        _salvar(pendentes_)
    _mudou.set()
    return f"Lembrete criado para {_formatar(quando, agora)}: {mensagem}"


def listar():
    pendentes_ = _carregar()
    if not pendentes_:
        return "Nenhum lembrete pendente."
    agora = datetime.now()
    linhas = [f"- {_formatar(_quando(l), agora)}: {l['mensagem']}"
              for l in sorted(pendentes_, key=lambda l: l["quando"])]
    return f"{len(pendentes_)} lembrete(s) pendente(s):\n" + "\n".join(linhas)


def cancelar(trecho):
    """Remove os lembretes cuja mensagem contem o trecho ('todos' = tudo)."""
    alvo = str(trecho or "").strip().lower()
    if not alvo:
        return "ERRO: informe um trecho da mensagem do lembrete."
    with _lock:
        pendentes_ = _carregar()
        if alvo in ("todos", "todas", "tudo"):
            removidos, restantes = pendentes_, []
        else:
            removidos = [l for l in pendentes_
                         if alvo in l["mensagem"].lower()]
            restantes = [l for l in pendentes_ if l not in removidos]
        if not removidos:
            return f"Nenhum lembrete pendente contém '{trecho}'."
        _salvar(restantes)
    _mudou.set()
    frases = "; ".join(l["mensagem"] for l in removidos)
    return f"{len(removidos)} lembrete(s) cancelado(s): {frases}"


def pendentes():
    """Quantos lembretes aguardam (para o banner do boot)."""
    return len(_carregar())


# ---------- a vigia ----------

def _disparar(lembrete, agora):
    msg = lembrete["mensagem"]
    atraso = (agora - _quando(lembrete)).total_seconds()
    if atraso > 120:
        # a hora passou com o Jarvis desligado (ou mudo): avisa o atraso
        fala = (f"Senhor, um lembrete atrasado, era para "
                f"{_formatar(_quando(lembrete), agora)}: {msg}")
    else:
        fala = f"Senhor, lembrete: {msg}"
    print(f"  [lembrete] disparando: {msg}")
    try:
        if FALAR is not None:
            FALAR(fala)
    except Exception as e:
        print(f"  [lembrete] falha ao falar ({e}): {msg}")


def _vigiar():
    while True:
        _mudou.clear()
        with _lock:
            pendentes_ = _carregar()
            agora = datetime.now()
            vencidos = [l for l in pendentes_ if _quando(l) <= agora]
            if vencidos:
                _salvar([l for l in pendentes_ if l not in vencidos])
        if vencidos:
            for lembrete in vencidos:
                _disparar(lembrete, agora)  # fora do lock: a fala demora
            continue
        if pendentes_:
            falta = min((_quando(l) - agora).total_seconds()
                        for l in pendentes_)
            espera = max(0.2, min(falta, 30.0))
        else:
            espera = 30.0  # teto: mudancas externas no json sao notadas
        _mudou.wait(espera)


def iniciar(falar=None):
    """Pluga o callback de fala e liga a thread vigia (uma so vez)."""
    global FALAR, _vigia_iniciada
    if falar is not None:
        FALAR = falar
    with _lock:
        if _vigia_iniciada:
            return
        _vigia_iniciada = True
    threading.Thread(target=_vigiar, daemon=True, name="lembretes").start()
