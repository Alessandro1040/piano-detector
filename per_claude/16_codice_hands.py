"""
Hands — landmark delle mani con MediaPipe Tasks (HandLandmarker, modalita' VIDEO).

Stadio 2 / E2 della pipeline video -> MIDI.

Usa SOLO l'API Tasks (mediapipe.tasks.python.vision.HandLandmarker): l'API
vecchia API a soluzioni non esiste piu' in mediapipe 1.x. L'import di mediapipe e'
pigro (dentro HandTracker.__init__): importare questo modulo non richiede
mediapipe, quindi il resto della pipeline gira anche con --senza-mani.

I landmark lavorano sul frame INTERO (non sul crop) e sono restituiti in pixel
del frame passato.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

PUNTE = (4, 8, 12, 16, 20)   # pollice, indice, medio, anulare, mignolo
URL_MODELLO = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
               "hand_landmarker/float16/1/hand_landmarker.task")


@dataclass
class Mano:
    punte: dict[int, tuple[float, float]]   # {4: (x,y), 8: (...), 12, 16, 20}
    tutte: list[tuple[float, float]]        # 21 landmark (x,y) in pixel
    mano: str                               # "Left" | "Right"
    confidenza: float


class HandTracker:
    """Rileva fino a `max_mani` mani per frame, con etichette stabili fra i frame."""

    def __init__(self, modello: str = "weights/hand_landmarker.task",
                 max_mani: int = 2, soglia: float = 0.3) -> None:
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as e:
            raise ImportError(
                "mediapipe non e' installato. Installa con:\n"
                "    python3 -m pip install mediapipe\n"
                f"e scarica il modello delle mani:\n    {URL_MODELLO}\n"
                "salvandolo come weights/hand_landmarker.task (7.5 MB). "
                "Senza mani usa l'opzione --senza-mani."
            ) from e

        if not Path(modello).is_file():
            raise FileNotFoundError(
                f"Modello delle mani non trovato: {modello}\n"
                f"Scaricalo da:\n    {URL_MODELLO}\n"
                "e salvalo come weights/hand_landmarker.task (nessun download automatico)."
            )

        self._mp = mp
        self.max_mani = int(max_mani)
        self.soglia = float(soglia)
        opzioni = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(modello)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=self.max_mani,
            min_hand_detection_confidence=self.soglia,
            min_hand_presence_confidence=self.soglia,
            min_tracking_confidence=self.soglia,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(opzioni)
        self._ultimo_ts = -1
        self._ultima_x: dict[str, float] = {}   # ultima x media per etichetta

    # ------------------------------------------------------------------ API
    def processa(self, frame: np.ndarray, timestamp_ms: int) -> list[Mano]:
        """Mani nel frame BGR. `timestamp_ms` deve crescere (se no viene forzato a +1)."""
        h, w = frame.shape[:2]
        ts = int(timestamp_ms)
        if ts <= self._ultimo_ts:
            ts = self._ultimo_ts + 1
        self._ultimo_ts = ts

        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        immagine = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        risultato = self._landmarker.detect_for_video(immagine, ts)

        mani: list[Mano] = []
        for landmarks, handedness in zip(risultato.hand_landmarks, risultato.handedness):
            if not landmarks or not handedness:
                continue
            conf = float(handedness[0].score or 0.0)
            if conf < self.soglia:
                continue
            tutte = [(float(p.x) * w, float(p.y) * h) for p in landmarks]   # normalizzati -> pixel
            if len(tutte) < 21:
                continue
            mani.append(Mano(punte={i: tutte[i] for i in PUNTE}, tutte=tutte,
                             mano=str(handedness[0].category_name or "Right"),
                             confidenza=conf))
        return self._etichetta_stabile(mani, w)

    def chiudi(self) -> None:
        """Libera le risorse di MediaPipe (idempotente)."""
        if getattr(self, "_landmarker", None) is not None:
            self._landmarker.close()
            self._landmarker = None

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, *exc) -> None:
        self.chiudi()

    # -------------------------------------------------------------- interni
    def _etichetta_stabile(self, mani: list[Mano], larghezza: int) -> list[Mano]:
        """
        Etichette "Left"/"Right" e ordine stabili fra i frame.

        L'handedness di MediaPipe assume immagini speculari (selfie) e su un video
        normale puo' risultare invertita: non e' affidabile da sola. Si ordina per
        x media: con 2 mani la sinistra nell'immagine e' "Left" (vista dal
        suonatore o dall'alto). Con 1 mano si assegna l'etichetta la cui ultima
        posizione e' piu' vicina; senza storia, si decide dalla meta' del frame.
        """
        if not mani:
            return []
        xs = [float(np.mean([p[0] for p in m.tutte])) for m in mani]
        ordine = sorted(range(len(mani)), key=lambda i: xs[i])
        mani = [mani[i] for i in ordine]
        xs = [xs[i] for i in ordine]

        if len(mani) >= 2:
            etichette = ["Left"] + ["Right"] * (len(mani) - 1)
        else:
            x = xs[0]
            if self._ultima_x:
                etichette = [min(self._ultima_x, key=lambda k: abs(self._ultima_x[k] - x))]
            else:
                etichette = ["Left" if x < larghezza / 2.0 else "Right"]
        for m, e, x in zip(mani, etichette, xs):
            m.mano = e
            self._ultima_x[e] = x
        return mani
