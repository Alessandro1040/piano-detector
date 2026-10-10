"""
Keyboard Grid — geometria dei tasti dentro il riquadro/quadrilatero della tastiera.

Stadio 2 / E3 della pipeline video -> MIDI.

MODELLO GEOMETRICO (formule esatte)
-----------------------------------
Si lavora in uno spazio canonico unitario (u, v):
    u in [0, 1]  asse della tastiera, dal tasto piu' grave al piu' acuto
    v in [0, 1]  profondita' del tasto, v=0 bordo superiore (lato dei neri),
                 v=1 bordo frontale (verso il suonatore)
Il quadrilatero della tastiera nel frame (TL, TR, BR, BL) e' il trasformato
del quadrato unitario tramite un'omografia (cv2.getPerspectiveTransform):
tutto cio' che segue e' calcolato in (u, v) e riportato nel frame con l'omografia.

  * n_b = numero di tasti bianchi; ogni bianco i occupa
        u in [i/n_b, (i+1)/n_b],  v in [0, 1].
  * Un nero di numero MIDI N ha il bianco sottostante (N-1) di indice i, quindi
    il confine fra i due bianchi adiacenti e' u_c = (i+1)/n_b. Il suo centro e'
        u_nero = u_c + offset[N % 12] / n_b
    con offset (in larghezze di tasto bianco) tratto dalla disposizione reale:
        C#: -0.10   D#: +0.10   F#: -0.12   G#: 0.00   A#: +0.12
    (C#/F# lievemente a sinistra, D#/A# a destra, G# centrato: sono
    approssimazioni di misure tipiche, errore < ~0.03 larghezze di bianco.)
  * Larghezza del nero = larghezza_neri / n_b (cioe' 0.60 larghezze di bianco).
  * Lunghezza del nero: occupa v in [0, altezza_bianchi]. NOTA: il brief la
    descriveva come "1 - altezza_bianchi", ma con il default 0.62 darebbe 0.38,
    fisicamente troppo corta (i neri reali sono ~0.62-0.65 dei bianchi). Qui
    `altezza_bianchi` e' quindi la frazione di profondita' coperta dai neri.

nota_a() ignora i punti fuori dalla tastiera e, in sovrapposizione, da' priorita'
al NERO (e' disegnato sopra le due porzioni di bianco adiacenti).

ASSUNZIONI DI ORIENTAMENTO: tasti gravi a sinistra, lato dei neri (retro della
tastiera) verso l'alto dell'immagine. Se il video e' capovolto la griglia va
girata a monte: controllare `prima_griglia.jpg`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

NOMI_NOTE = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NERI_PC = frozenset({1, 3, 6, 8, 10})
_OFFSET_NERI = {1: -0.10, 3: 0.10, 6: -0.12, 8: 0.0, 10: 0.12}

MIDI_MIN, MIDI_MAX = 21, 108          # A0 .. C8 (pianoforte a 88 tasti)
LARGHEZZA_BIANCO_CM = 2.2             # assunzione per stima_estensione
LUNGHEZZA_BIANCO_CM = 15.0            # assunzione per stima_estensione
_N_BIANCHI_88 = 52
_QUADRATO = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])


def nome_nota(n: int) -> str:
    """Notazione scientifica: MIDI 60 -> 'C4', 21 -> 'A0'."""
    return f"{NOMI_NOTE[n % 12]}{n // 12 - 1}"


def e_nero(n: int) -> bool:
    return (n % 12) in _NERI_PC


@dataclass
class Tasto:
    nota: int          # numero MIDI (A0 = 21, C8 = 108)
    nome: str          # "C4", "F#3", ...
    nero: bool
    poligono: list[tuple[float, float]]   # 4 vertici nel frame originale


class KeyboardGrid:
    """Griglia dei tasti costruita sul riquadro (o quadrilatero) della tastiera."""

    def __init__(self, prima_nota: int = 21, n_ottave: int = 7,
                 altezza_bianchi: float = 0.62, larghezza_neri: float = 0.60,
                 prospettiva: bool = True, ultima_nota: int | None = None) -> None:
        """
        prima_nota / n_ottave: estensione = da prima_nota a prima_nota + 12*n_ottave
            (inclusa), limitata a 21..108. `ultima_nota` (opzionale) la sostituisce.
        Gli estremi vengono portati su tasti bianchi (un nero non puo' stare al
        bordo): prima_nota nero -> scende di 1; ultima_nota nero -> sale di 1.
        Gli attributi `prima_nota` / `ultima_nota` riportano i valori effettivi.
        """
        if not 0.0 < altezza_bianchi <= 1.0:
            raise ValueError("altezza_bianchi deve essere in (0, 1]")
        if not 0.0 < larghezza_neri < 1.0:
            raise ValueError("larghezza_neri deve essere in (0, 1)")
        self.altezza_bianchi = float(altezza_bianchi)
        self.larghezza_neri = float(larghezza_neri)
        self.prospettiva = bool(prospettiva)

        prima = int(min(max(prima_nota, MIDI_MIN), MIDI_MAX))
        ultima = int(ultima_nota) if ultima_nota is not None \
            else prima + int(round(12 * n_ottave))
        ultima = int(min(max(ultima, MIDI_MIN), MIDI_MAX))
        if e_nero(prima):
            prima -= 1
        if e_nero(ultima):
            ultima += 1
        prima, ultima = max(prima, MIDI_MIN), min(ultima, MIDI_MAX)
        if ultima - prima < 2:
            raise ValueError(f"estensione troppo piccola: {prima}..{ultima}")
        self.prima_nota, self.ultima_nota = prima, ultima

        note = list(range(prima, ultima + 1))
        self._bianchi = [n for n in note if not e_nero(n)]
        self.n_bianchi = len(self._bianchi)
        indice = {n: i for i, n in enumerate(self._bianchi)}
        nb = self.n_bianchi
        self._neri: list[tuple[int, float, float]] = []   # (nota, u_centro, semi-larghezza)
        hw = self.larghezza_neri / (2.0 * nb)
        for n in note:
            if e_nero(n):
                uc = (indice[n - 1] + 1) / nb + _OFFSET_NERI[n % 12] / nb
                self._neri.append((n, uc, hw))
        self._note = note

        # poligoni nello spazio canonico (u, v) per ogni nota, ordinati come _note
        self._poligoni_unit: list[np.ndarray] = []
        neri = {n: (uc, h) for n, uc, h in self._neri}
        for n in note:
            if e_nero(n):
                uc, h = neri[n]
                p = [(uc - h, 0.0), (uc + h, 0.0), (uc + h, self.altezza_bianchi),
                     (uc - h, self.altezza_bianchi)]
            else:
                i = indice[n]
                p = [(i / nb, 0.0), ((i + 1) / nb, 0.0), ((i + 1) / nb, 1.0), (i / nb, 1.0)]
            self._poligoni_unit.append(np.float32(p))

        self._M: np.ndarray | None = None      # canonico -> frame
        self._Minv: np.ndarray | None = None   # frame -> canonico
        self._dim = (1.0, 1.0)                 # (larghezza, altezza) del quad in px
        self.info_stima: dict = {}

    # ------------------------------------------------------------------ API
    def costruisci(self, traccia: "Traccia", frame_shape: tuple[int, int]) -> list[Tasto]:
        """Costruisce i tasti sulla traccia; aggiorna lo stato usato da nota_a()."""
        h, w = frame_shape[:2]
        quad = self._quad_da_traccia(traccia)
        quad[:, 0] = np.clip(quad[:, 0], 0, max(0, w - 1))
        quad[:, 1] = np.clip(quad[:, 1], 0, max(0, h - 1))
        lw, lh = self._lati(quad)
        if lw < 2.0 or lh < 2.0:
            raise ValueError("riquadro della tastiera degenere")
        self._M = cv2.getPerspectiveTransform(_QUADRATO, quad)
        self._Minv = np.linalg.inv(self._M)
        self._dim = (lw, lh)

        tutti = np.concatenate(self._poligoni_unit).reshape(-1, 1, 2).astype(np.float32)
        nel_frame = cv2.perspectiveTransform(tutti, self._M).reshape(-1, 4, 2)
        return [Tasto(nota=n, nome=nome_nota(n), nero=e_nero(n),
                      poligono=[(float(x), float(y)) for x, y in nel_frame[i]])
                for i, n in enumerate(self._note)]

    def punto_raddrizzato(self, punto: tuple[float, float]) -> tuple[float, float]:
        """(x, y) del frame -> (u, v) canonici (u lungo la tastiera, v in profondita', 0-1 dentro i tasti)."""
        if self._Minv is None:
            raise RuntimeError("chiamare costruisci() prima di usare la griglia")
        x, y = float(punto[0]), float(punto[1])
        p = self._Minv @ np.array([x, y, 1.0])
        if abs(p[2]) < 1e-12:
            return float("nan"), float("nan")
        return float(p[0] / p[2]), float(p[1] / p[2])

    def nota_a(self, punto: tuple[float, float], margine_px: float = 0.0) -> int | None:
        """Nota MIDI sotto il punto (x, y) del frame, None se fuori dai tasti (entro il margine)."""
        u, v = self.punto_raddrizzato(punto)
        if not (math.isfinite(u) and math.isfinite(v)):
            return None
        lw, lh = self._dim
        mu, mv = margine_px / lw, margine_px / lh
        if u < -mu or u > 1 + mu or v < -mv or v > 1 + mv:
            return None
        u = min(max(u, 0.0), 1.0)
        v = min(max(v, 0.0), 1.0)

        # i neri hanno priorita': scelgo quello piu' vicino fra i candidati
        migliore, dist = None, 1e9
        for nota, uc, hw in self._neri:
            d = abs(u - uc)
            if d <= hw + mu and v <= self.altezza_bianchi + mv and d < dist:
                migliore, dist = nota, d
        if migliore is not None:
            return migliore
        i = min(int(u * self.n_bianchi), self.n_bianchi - 1)
        return self._bianchi[i]

    def frame_raddrizzato(self, frame: np.ndarray, traccia: "Traccia",
                          larghezza: int = 1200) -> tuple[np.ndarray, np.ndarray]:
        """Tastiera vista di fronte: -> (immagine raddrizzata, omografia 3x3 frame -> immagine)."""
        quad = self._quad_da_traccia(traccia)
        lw, lh = self._lati(quad)
        wd = max(1, int(larghezza))
        hd = max(1, int(round(wd * lh / lw)))
        dst = np.float32([[0, 0], [wd, 0], [wd, hd], [0, hd]])
        M = cv2.getPerspectiveTransform(quad, dst)
        return cv2.warpPerspective(frame, M, (wd, hd)), M

    def stima_estensione(self, traccia: "Traccia", larghezza_frame: int) -> tuple[int, int]:
        """
        Propone (prima_nota, ultima_nota) visibili. E' una STIMA, non una misura.

        Assunzioni (da verificare):
          1. il box copre la profondita' dei tasti bianchi (~15 cm) e la sua
             larghezza copre n tasti bianchi da ~2.2 cm, quindi
             n_bianchi = (larghezza_px / altezza_px) * (15.0 / 2.2) ~ 6.8 * w/h;
          2. la finestra visibile e' CENTRATA sul centro del pianoforte a 88
             tasti (fra E4 e F4).
        Errore atteso: n_bianchi +-15% (qualche tasto ai bordi); l'assunzione 2 e'
        quella pericolosa: se l'inquadratura non e' centrata, TUTTE le note sono
        trasposte (tipicamente di una o piu' ottave). Il numero di tasti e'
        affidabile, l'ottava assoluta NO: va fornita a mano (prima_nota).
        `larghezza_frame` serve solo a segnalare in `info_stima['taglio_frame']`
        che il box tocca i bordi (tastiera probabilmente tagliata: stima per difetto).
        """
        quad = self._quad_da_traccia(traccia)
        lw, lh = self._lati(quad)
        grezzo = (lw / lh) * (LUNGHEZZA_BIANCO_CM / LARGHEZZA_BIANCO_CM)
        n_b = int(min(max(round(grezzo), 7), _N_BIANCHI_88))
        primo = int(min(max(math.floor(26 - n_b / 2), 0), _N_BIANCHI_88 - n_b))
        bianchi_88 = [n for n in range(MIDI_MIN, MIDI_MAX + 1) if not e_nero(n)]
        prima, ultima = bianchi_88[primo], bianchi_88[primo + n_b - 1]
        self.info_stima = {
            "n_bianchi_grezzo": round(float(grezzo), 2),
            "n_bianchi": n_b,
            "prima_nota": prima,
            "ultima_nota": ultima,
            "taglio_frame": bool(larghezza_frame and
                                 (traccia.x1 <= 2 or traccia.x2 >= larghezza_frame - 2)),
        }
        return prima, ultima

    # -------------------------------------------------------------- interni
    def _quad_da_traccia(self, traccia) -> np.ndarray:
        quad = getattr(traccia, "quad", None)
        if self.prospettiva and quad is not None and len(quad) == 4:
            return np.float32(quad).reshape(4, 2).copy()
        return np.float32([[traccia.x1, traccia.y1], [traccia.x2, traccia.y1],
                           [traccia.x2, traccia.y2], [traccia.x1, traccia.y2]])

    @staticmethod
    def _lati(quad: np.ndarray) -> tuple[float, float]:
        """(larghezza, altezza) medie del quad in px."""
        larg = 0.5 * (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3]))
        alt = 0.5 * (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1]))
        return float(larg), float(alt)
