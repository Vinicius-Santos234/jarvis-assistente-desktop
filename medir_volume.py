"""
Medidor de volume - ajuda a calibrar o 'limite_volume' do config.json.

Rode este script e bata palma algumas vezes. Anote o pico das palmas
e o nivel do som ambiente. Escolha um 'limite_volume' que fique
ENTRE os dois (mais perto do valor das palmas).

v0.6: mostra tambem as metricas do filtro espectral das palmas
(deteccao.min_agudos / min_crista no config.json):
- agudos: fracao da energia acima de 2 kHz (palma de verdade: alta);
- crista: pico/RMS do bloco (impulso: alto; voz/musica: baixo).
Se as SUAS palmas aparecerem com agudos/crista abaixo dos limites do
config, diminua 'min_agudos' ou 'min_crista'.

    python medir_volume.py

Pare com Ctrl+C.
"""
import time
import numpy as np
import sounddevice as sd

# 16 kHz e blocos de ~0,125 s: as MESMAS condicoes do assistente.py,
# para as metricas medidas aqui valerem la.
SAMPLERATE = 16000
BLOCKSIZE = 2000


def callback(indata, frames, time_info, status):
    x = indata.reshape(-1)
    pico = float(np.max(np.abs(x)))
    if pico < 0.05:
        return  # silencio: nao polui a tela
    rms = float(np.sqrt(np.mean(x * x))) + 1e-9
    crista = pico / rms
    espectro = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(x.size, 1.0 / SAMPLERATE)
    agudos = float(espectro[freqs >= 2000.0].sum()) / (float(espectro.sum()) + 1e-9)
    barras = int(pico * 50)
    marca = " <== PALMA?" if pico > 0.3 else ""
    print(f"pico={pico:5.2f}  agudos={agudos:4.2f}  crista={crista:4.1f} |"
          + "#" * barras + marca)


print("Medindo volume do microfone. Bata palmas! (Ctrl+C para sair)")
try:
    with sd.InputStream(channels=1, samplerate=SAMPLERATE,
                        blocksize=BLOCKSIZE, dtype="float32",
                        callback=callback):
        while True:
            time.sleep(0.1)
except KeyboardInterrupt:
    print("\nEncerrado.")
