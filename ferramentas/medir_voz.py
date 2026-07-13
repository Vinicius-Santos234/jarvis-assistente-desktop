"""
Medidor de nivel de VOZ do Jarvis.

Fale frases normais a distancia normal do notebook e observe a barra.
O que importa e o pico enquanto voce FALA:

    abaixo de 0.05  -> muito fraco: suba o volume do mic no Windows e use ganho_voz 5-6
    0.05 a 0.15     -> fraco: ganho_voz 3-4 resolve
    0.15 a 0.50     -> bom: ganho_voz 1-2
    acima de 0.80   -> forte demais (risco de distorcer): reduza o ganho_voz

O valor mostrado JA APLICA o ganho_voz atual do config.json, entao ajuste
o config, rode de novo e mire a faixa 0.2-0.6 falando a 1 metro.
Ctrl+C para sair.
"""

import json
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

# Raiz do projeto (este arquivo vive em ferramentas/)
BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLERATE = 16000
BLOCKSIZE = 2000

try:
    with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
        GANHO = float(json.load(f).get("microfone", {}).get("ganho_voz", 1.0))
except Exception:
    GANHO = 1.0

pico_bloco = 0.0


def callback(indata, frames, time_info, status):
    global pico_bloco
    p = float(np.max(np.abs(indata.astype(np.int32)))) / 32768.0
    pico_bloco = max(pico_bloco, min(1.0, p * GANHO))


def main():
    global pico_bloco
    print(__doc__)
    print(f"ganho_voz atual do config: {GANHO}\n")
    with sd.InputStream(channels=1, samplerate=SAMPLERATE, blocksize=BLOCKSIZE,
                        dtype="int16", callback=callback):
        try:
            while True:
                time.sleep(0.3)
                p = pico_bloco
                pico_bloco = 0.0
                barra = "#" * int(p * 50)
                nivel = ("MUITO FRACO" if p < 0.05 else
                         "fraco" if p < 0.15 else
                         "BOM" if p < 0.80 else "FORTE DEMAIS")
                print(f"  pico(c/ ganho)={p:.2f}  |{barra:<50s}| {nivel}")
        except KeyboardInterrupt:
            print("\nEncerrado.")


if __name__ == "__main__":
    main()
