"""
Log em arquivo do Jarvis - v0.9.

Todo diagnostico ([voz] ouvi:, ferramentas, erros) sai em print, mas o
uso normal e em segundo plano via pythonw - sem console, sys.stdout e
None e os prints somem. Este modulo espelha stdout/stderr para
dados/<nome>.log com horario por linha e rotacao simples (1 MB,
2 backups), sem mudar nenhum print do codigo.

Uso (primeira coisa no main):
    import registro
    registro.iniciar("jarvis")

O assistente ("jarvis") e o supervisor ("supervisor") usam arquivos
separados: sao processos diferentes, e dois processos no mesmo arquivo
embaralhariam linhas e brigariam na rotacao.
"""

import os
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PASTA = BASE_DIR / "dados"
TAMANHO_MAX = 1_000_000  # ~1 MB por arquivo
BACKUPS = 2  # jarvis.log + .1 + .2

_ativado = False


class _ArquivoLog:
    """Escreve linhas com horario num arquivo, com rotacao propria."""

    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self.lock = threading.Lock()
        self._f = None

    def _abrir(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.caminho, "a", encoding="utf-8", errors="replace")

    def _rotacionar(self):
        """jarvis.log -> jarvis.log.1 -> jarvis.log.2 (o mais velho cai)."""
        self._f.close()
        self._f = None
        try:
            Path(f"{self.caminho}.{BACKUPS}").unlink(missing_ok=True)
            for i in range(BACKUPS - 1, 0, -1):
                p = Path(f"{self.caminho}.{i}")
                if p.exists():
                    p.rename(f"{self.caminho}.{i + 1}")
            self.caminho.rename(f"{self.caminho}.1")
        except OSError:
            pass  # arquivo preso? segue escrevendo no atual mesmo

    def escrever(self, linha):
        with self.lock:
            try:
                if self._f is None:
                    self._abrir()
                if self._f.tell() > TAMANHO_MAX:
                    self._rotacionar()
                    self._abrir()
                self._f.write(time.strftime("%d/%m %H:%M:%S  ") + linha + "\n")
                self._f.flush()  # crash nao pode engolir a ultima pista
            except Exception:
                pass  # o log NUNCA derruba o Jarvis


class _Tee:
    """Substitui sys.stdout/sys.stderr: repassa ao console (se houver)
    e manda cada linha completa ao arquivo de log."""

    def __init__(self, log, original, prefixo=""):
        self.log = log
        self.original = original  # None sob pythonw (sem console)
        self.prefixo = prefixo
        self.encoding = getattr(original, "encoding", None) or "utf-8"
        self._parcial = ""
        self._lock = threading.Lock()

    def write(self, texto):
        texto = str(texto)
        if self.original is not None:
            try:
                self.original.write(texto)
            except Exception:
                pass
        with self._lock:
            self._parcial += texto
            while "\n" in self._parcial:
                linha, self._parcial = self._parcial.split("\n", 1)
                if linha.strip():
                    self.log.escrever(self.prefixo + linha.rstrip())
        return len(texto)

    def flush(self):
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def iniciar(nome="jarvis"):
    """Ativa o espelhamento de stdout/stderr para dados/<nome>.log.

    Devolve o caminho do log; chamadas repetidas nao empilham tees.
    """
    global _ativado
    caminho = PASTA / f"{nome}.log"
    if _ativado:
        return caminho
    _ativado = True
    log = _ArquivoLog(caminho)
    log.escrever(f"===== sessao iniciada (pid {os.getpid()}) =====")
    sys.stdout = _Tee(log, sys.stdout)
    sys.stderr = _Tee(log, sys.stderr, prefixo="[err] ")
    return caminho
