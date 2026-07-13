"""
Supervisor do Jarvis - v0.4.2.

Mantem o assistente sempre vivo: inicia o assistente.py e, se ele morrer
por erro (crash, thread de voz morta, falha de audio), reinicia sozinho.
Um assistente de verdade precisa estar sempre la - sem isto, se o
processo cair, so se percebe falando com o vazio.

Regras:
- Saida com codigo 0 = encerramento intencional ("Jarvis, pode descansar"
  ou outra instancia ja rodando) -> o supervisor tambem encerra.
- Qualquer outro codigo = falha -> espera alguns segundos e reinicia.
- Se cair 5 vezes seguidas em menos de 1 minuto cada, desiste (algo
  esta realmente quebrado; reiniciar em loop so esquentaria o PC).

Uso: e o alvo do "Iniciar Jarvis.bat" e do atalho de inicializacao do
Windows ("Instalar Inicializacao.bat"). O "Parar Jarvis.bat" mata o
supervisor E o assistente.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSISTENTE = BASE_DIR / "assistente.py"

# Trava de instancia unica do SUPERVISOR (o assistente tem a dele na 51739)
PORTA_TRAVA = 51740
_TRAVA = None

ESPERA_REINICIO_SEG = 3.0
CRASH_RAPIDO_SEG = 60.0
MAX_CRASHES_SEGUIDOS = 5


def travar_instancia_unica():
    global _TRAVA
    try:
        _TRAVA = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _TRAVA.bind(("127.0.0.1", PORTA_TRAVA))
        return True
    except OSError:
        return False


def supervisionar(comando, espera_seg=ESPERA_REINICIO_SEG,
                  crash_rapido_seg=CRASH_RAPIDO_SEG,
                  max_seguidos=MAX_CRASHES_SEGUIDOS):
    """Roda `comando` em loop ate ele sair com codigo 0 ou falhar demais.

    Devolve o motivo da parada: 'normal' ou 'desistiu'.
    """
    crashes_seguidos = 0
    while True:
        inicio = time.monotonic()
        try:
            codigo = subprocess.run(comando, cwd=str(BASE_DIR)).returncode
        except Exception as e:
            print(f"[supervisor] Erro ao iniciar o Jarvis: {e}")
            codigo = -1

        if codigo == 0:
            print("[supervisor] Jarvis encerrou normalmente. Ate mais.")
            return "normal"

        duracao = time.monotonic() - inicio
        if duracao < crash_rapido_seg:
            crashes_seguidos += 1
        else:
            crashes_seguidos = 1  # rodou um bom tempo antes de cair
        print(f"[supervisor] Jarvis caiu (codigo {codigo}, apos {duracao:.0f}s) "
              f"- queda {crashes_seguidos}/{max_seguidos}.")

        if crashes_seguidos >= max_seguidos:
            print("[supervisor] Muitas quedas seguidas; desistindo. "
                  "Rode o 'Iniciar Jarvis (console).bat' para ver o erro.")
            return "desistiu"

        time.sleep(espera_seg)
        print("[supervisor] Reiniciando o Jarvis...")


def main():
    if not travar_instancia_unica():
        print("[supervisor] Ja ha um supervisor rodando; saindo.")
        sys.exit(0)
    # sys.executable garante o mesmo interpretador (pythonw = invisivel)
    supervisionar([sys.executable, str(ASSISTENTE)])


if __name__ == "__main__":
    main()
