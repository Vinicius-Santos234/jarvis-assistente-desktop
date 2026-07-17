"""
Palavra de ativacao dedicada - v0.9 (openWakeWord).

A fragilidade do "Jarvis" (ouvido como "james", "ja vice", "jardins",
"chaves"...) vem de usar o Vosk para algo que ele nao foi feito. O
openWakeWord e um detector de wake word dedicado: open source (Apache
2.0), offline e SEM chave nenhuma - com o modelo pre-treinado embutido
"hey jarvis". (O plano original era o Porcupine, mas a Picovoice
encerrou o Free Tier em 30/06/2026 e ficou so para empresas.)

Ele responde a "ei Jarvis" / "hey Jarvis"; o casamento aproximado via
Vosk continua ativo como reserva, entao o "Jarvis" seco segue
funcionando por la. Ajuste fino em voz.wake_word.limiar no config.json
(score 0 a 1; MENOR = ativa mais facil).

CALIBRACAO (medida com TTS em 16/07/2026): o modelo foi treinado com
"hey jarvis" em INGLES - pronuncia nativa pontua ~1.0, mas a pronuncia
aportuguesada ("ei JAR-vis" das vozes pt-BR) pontua so ~0.12-0.23,
enquanto conversa normal fica abaixo de 0.01. Por isso o limiar padrao
e 0.1 (nao os 0.5 da documentacao) e o VAD interno fica ligado para
compensar: so audio com cara de fala chega a pontuar.

Esta camada e OPCIONAL e degrada sozinha: sem o pacote openwakeword ou
com qualquer erro, a ativacao volta a ser 100% via Vosk - nada quebra.
Quando ativa, tambem assume o barge-in ("Jarvis!" por cima da fala),
aposentando a gramatica minima de apelidos foneticos.

Instalacao: ja vem no requirements.txt (openwakeword + onnxruntime).
Na PRIMEIRA execucao baixa os modelos (~7 MB, uma unica vez - precisa
de internet); depois e tudo local.
"""

import numpy as np

MODELO = "hey_jarvis_v0.1"
FRAME = 1280  # 80 ms a 16 kHz - o quadro que o openWakeWord espera


class DetectorAtivacao:
    """Detecta 'hey jarvis' num stream PCM 16 kHz mono int16.

    O modelo processa quadros FIXOS de FRAME amostras; os blocos de
    tamanho arbitrario do assistente (2000) sao fatiados aqui e a sobra
    fica guardada para completar com o proximo bloco.
    """

    def __init__(self, limiar=0.1):
        from openwakeword.model import Model
        self.limiar = max(0.05, min(1.0, float(limiar)))

        def _criar():
            # vad_threshold: com limiar baixo (pronuncia pt-BR pontua
            # ~0.12-0.23), o VAD garante que so FALA pontue - ruido,
            # musica e batidas nem chegam ao classificador
            return Model(wakeword_models=[MODELO],
                         inference_framework="onnx",
                         vad_threshold=0.5)

        try:
            self._modelo = _criar()
        except Exception:
            # primeira execucao: os modelos ainda nao foram baixados
            import openwakeword.utils
            print("  [ativacao] baixando os modelos do openWakeWord "
                  "(~7 MB, so na primeira vez)...")
            openwakeword.utils.download_models(model_names=[MODELO])
            self._modelo = _criar()
        self._resto = b""

    def processar(self, dados):
        """Consome bytes PCM; True se a palavra de ativacao apareceu."""
        self._resto += dados
        achou = False
        while len(self._resto) >= FRAME * 2:  # int16 = 2 bytes/amostra
            quadro = np.frombuffer(self._resto[:FRAME * 2], dtype=np.int16)
            self._resto = self._resto[FRAME * 2:]
            notas = self._modelo.predict(quadro)
            if max(notas.values()) >= self.limiar:
                achou = True
        if achou:
            # o score fica alto por varios quadros apos a deteccao;
            # o reset evita disparo em cascata
            self._modelo.reset()
        return achou

    def resetar(self):
        """Descarta sobra e estado interno (usado ao limpar a captura)."""
        self._resto = b""
        try:
            self._modelo.reset()
        except Exception:
            pass
