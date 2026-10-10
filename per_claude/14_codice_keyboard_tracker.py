"""
Keyboard Tracker — segue il riquadro della tastiera fra i frame di un video.

Stadio 2 / E1 della pipeline video -> MIDI.

Strategia: la rete neurale (PianoDetector) gira solo sul 1° frame, poi
periodicamente (ogni `intervallo_redetect` frame) e, in modo forzato, quando il
tracking perde il bersaglio (somiglianza sotto soglia). Nei frame intermedi si
usa un tracker leggero:

  * tracker="template": template matching (cv2.matchTemplate, TM_CCOEFF_NORMED)
    in una finestra di ricerca attorno alla posizione precedente. Non dipende da
    il modulo legacy di OpenCV ne' da file di modello esterni.
  * tracker="mil": cv2.TrackerMIL_create() (presente in OpenCV 5). Se non e'
    disponibile si ripiega automaticamente su "template" con un warning.

Per la geometria dei tasti si usa la classe 'musical keyboard' (i tasti), con
'piano' (strumento intero) solo come ripiego: e' l'opposto di
PianoDetector.detect_piano(), che qui NON viene usato.

In piu' del contratto minimo, `Traccia` porta un campo opzionale `quad` (4
vertici TL,TR,BR,BL nel frame) stimato con una raffinazione prudente del box:
serve a KeyboardGrid per la prospettiva. Se la raffinazione non e' affidabile
vale None e la griglia usa il rettangolo.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:  # solo per i type hint: nessun import di ultralytics qui
    from piano_detector import PianoDetector

CLASSE_PREFERITA = "musical keyboard"

_SCALA_LAVORO = 0.5          # i frame sono ridotti a meta' per il template matching
_DIM_MIN = 16                # lato minimo (px) di un box valido
_RETRY_PERSO = 5             # ogni quanti frame ritentare la rilevazione se si e' persi
_AGG_TEMPLATE_OGNI = 5       # il template si aggiorna al massimo ogni N frame...
_SOGLIA_AGG_TEMPLATE = 0.75  # ...e solo se la somiglianza e' alta
_ALFA_TEMPLATE = 0.15        # peso del nuovo patch nell'EMA del template


@dataclass
class Traccia:
    """Riquadro della tastiera in un frame."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidenza: float          # confidenza "di tracciamento" 0-1
    origine: str               # "detector" | "tracker"
    frame: int
    quad: list[tuple[float, float]] | None = None  # TL, TR, BR, BL (opzionale)

    @property
    def larghezza(self) -> int:
        return self.x2 - self.x1

    @property
    def altezza(self) -> int:
        return self.y2 - self.y1


# ----------------------------------------------------------------- utilita'
def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    unione = area_a + area_b - inter
    return inter / unione if unione > 0 else 0.0


def _clamp_box(box, w: int, h: int):
    """Porta il box (float) dentro il frame mantenendo una dimensione minima."""
    x1, y1, x2, y2 = box
    x1 = min(max(0.0, x1), w - _DIM_MIN)
    y1 = min(max(0.0, y1), h - _DIM_MIN)
    x2 = min(max(x1 + _DIM_MIN, x2), float(w))
    y2 = min(max(y1 + _DIM_MIN, y2), float(h))
    return [x1, y1, x2, y2]


def _grigio(frame: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return cv2.resize(g, None, fx=_SCALA_LAVORO, fy=_SCALA_LAVORO,
                      interpolation=cv2.INTER_AREA)


def _ordina_quad(pts: np.ndarray):
    """Ordina 4 punti come TL, TR, BR, BL. None se degenerati."""
    s = pts.sum(axis=1)
    d = pts[:, 1] - pts[:, 0]
    idx = [int(np.argmin(s)), int(np.argmin(d)), int(np.argmax(s)), int(np.argmax(d))]
    if len(set(idx)) != 4:
        return None
    return pts[idx]


def _raffina_quad(frame: np.ndarray, box) -> list[tuple[float, float]] | None:
    """
    Stima prudente dei 4 vertici della tastiera dentro il box del detector.

    Soglia Otsu sul ritaglio, chiusura morfologica (riempie i tasti neri),
    contorno piu' grande -> poligono a 4 lati. Il risultato e' accettato solo se
    e' vicino al box (ogni vertice entro il 15% della larghezza e il 20%
    dell'altezza dal corrispondente angolo del box) e copre almeno il 60% della
    sua area: serve solo a correggere una prospettiva lieve, mai a inventare una
    forma. In ogni altro caso ritorna None (e la griglia usa il rettangolo).
    """
    H, W = frame.shape[:2]
    x1, y1 = max(0, int(round(box[0]))), max(0, int(round(box[1])))
    x2, y2 = min(W, int(round(box[2]))), min(H, int(round(box[3])))
    bw, bh = x2 - x1, y2 - y1
    if bw < _DIM_MIN * 4 or bh < _DIM_MIN * 2:
        return None
    roi = frame[y1:y2, x1:x2]
    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    g = cv2.GaussianBlur(g, (5, 5), 0)
    _, bin_ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = max(5, int(0.05 * min(bw, bh))) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    area_box = float(bw * bh)

    candidato, miglior_score = None, 0.0
    for img in (bin_, 255 - bin_):
        chiuso = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)
        contorni, _ = cv2.findContours(chiuso, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contorni:
            continue
        c = max(contorni, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < 0.35 * area_box:
            continue
        hull = cv2.convexHull(c)
        area_hull = cv2.contourArea(hull)
        if area_hull <= 0:
            continue
        score = (area / area_box) * (area / area_hull)
        if score <= miglior_score:
            continue
        pts = None
        peri = cv2.arcLength(hull, True)
        for f in (0.01, 0.02, 0.03, 0.05, 0.08):
            approx = cv2.approxPolyDP(hull, f * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                break
        if pts is None:
            try:
                pts = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)
            except (AttributeError, cv2.error):
                continue
        ordinati = _ordina_quad(pts)
        if ordinati is not None:
            candidato, miglior_score = ordinati, score

    if candidato is None:
        return None
    candidato = candidato + np.float32([x1, y1])
    angoli = np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
    scarto = np.abs(candidato - angoli)
    if (scarto[:, 0] > 0.15 * bw).any() or (scarto[:, 1] > 0.20 * bh).any():
        return None
    if not cv2.isContourConvex(candidato.reshape(-1, 1, 2)):
        return None
    if cv2.contourArea(candidato.reshape(-1, 1, 2)) < 0.60 * area_box:
        return None
    return [(float(x), float(y)) for x, y in candidato]


# ------------------------------------------------------------------ tracker
class KeyboardTracker:
    """Segue la tastiera: detector periodico + tracker leggero fra una rilevazione e l'altra."""

    def __init__(self, detector: "PianoDetector", conf: float = 0.15,
                 tracker: str = "template", intervallo_redetect: int = 30,
                 soglia_somiglianza: float = 0.55, ema: float = 0.35,
                 raffina_quad: bool = True) -> None:
        if tracker not in ("template", "mil"):
            raise ValueError(f"tracker sconosciuto: {tracker!r} (usa 'template' o 'mil')")
        self.detector = detector
        self.conf = float(conf)
        self.tracker_tipo = tracker
        self.intervallo = max(1, int(intervallo_redetect))
        self.soglia = float(soglia_somiglianza)
        self.ema = float(min(max(ema, 0.0), 0.95))   # 0 = nessuno smoothing
        self.raffina_quad = bool(raffina_quad)
        self.reset()

    # ------------------------------------------------------------------ API
    def reset(self) -> None:
        """Dimentica lo stato: il prossimo init()/update() rilevera' da zero."""
        self._box = None          # box grezzo [x1,y1,x2,y2] (float), usato per il tracking
        self._box_out = None      # box smussato con EMA, quello restituito
        self._quad_rel = None     # vertici in coordinate relative al box (0-1)
        self._template = None     # patch in grigio a scala di lavoro
        self._mil = None
        self._ultimo_det = -10 ** 9
        self._ultimo_agg = -10 ** 9
        self._ultima_sim = 0.0
        self.ultima_classe = None  # classe del detector usata all'ultima adozione

    def init(self, frame: np.ndarray, frame_idx: int = 0) -> Traccia | None:
        """Rileva la tastiera con la rete neurale e inizializza il tracker."""
        self.reset()
        self._ultimo_det = frame_idx
        det = self._rileva(frame)
        if det is None:
            return None
        return self._adotta(frame, _grigio(frame), [det.x1, det.y1, det.x2, det.y2],
                            frame_idx, det.confidenza)

    def update(self, frame: np.ndarray, frame_idx: int) -> Traccia | None:
        """Aggiorna la traccia sul frame; None se la tastiera non si trova (mai box inventati)."""
        if self._box is None:
            if frame_idx - self._ultimo_det >= _RETRY_PERSO:
                return self.init(frame, frame_idx)
            return None

        gray = _grigio(frame)
        box_new, sim = self._segui(frame, gray)
        self._ultima_sim = sim
        ok = box_new is not None and sim >= self.soglia
        scaduto = (frame_idx - self._ultimo_det) >= self.intervallo
        riprova = (frame_idx - self._ultimo_det) >= _RETRY_PERSO

        if scaduto or (not ok and riprova):
            self._ultimo_det = frame_idx
            det = self._rileva(frame)
            if det is not None:
                box_det = [float(det.x1), float(det.y1), float(det.x2), float(det.y2)]
                if not ok:  # forzata: il tracker ha perso il bersaglio
                    return self._adotta(frame, gray, box_det, frame_idx, det.confidenza)
                iou = _iou(box_new, box_det)
                if iou >= 0.5:  # concordi: media, per correggere scala/deriva senza salti
                    misto = [0.5 * a + 0.5 * b for a, b in zip(box_new, box_det)]
                    return self._adotta(frame, gray, misto, frame_idx, det.confidenza,
                                        mantieni_out=True)
                if sim < self.soglia + 0.15:  # discordi e tracker incerto: ci si fida della rete
                    return self._adotta(frame, gray, box_det, frame_idx, det.confidenza)
                # discordi ma tracker solido: il box del detector e' un outlier, si ignora

        if not ok:
            return None   # perso e nessuna rilevazione: nessun box inventato

        self._box = box_new
        h, w = frame.shape[:2]
        self._box = _clamp_box(self._box, w, h)
        self._aggiorna_template(gray, sim, frame_idx)
        if self._box_out is None or self.ema <= 0:
            self._box_out = list(self._box)
        else:
            self._box_out = [self.ema * o + (1.0 - self.ema) * n
                             for o, n in zip(self._box_out, self._box)]
        return self._costruisci_traccia(frame_idx, "tracker", sim, (h, w))

    # ------------------------------------------------------------- interni
    def _rileva(self, frame: np.ndarray):
        """Migliore rilevazione per la GEOMETRIA dei tasti: 'musical keyboard' > 'piano'."""
        dets = [d for d in self.detector.detect_all(frame) if d.confidenza >= self.conf]
        if not dets:
            return None
        tastiere = [d for d in dets if d.classe == CLASSE_PREFERITA]
        scelta = tastiere[0] if tastiere else dets[0]   # liste gia' ordinate per confidenza
        self.ultima_classe = scelta.classe
        return scelta

    def _adotta(self, frame, gray, box, frame_idx, conf, mantieni_out: bool = False) -> Traccia | None:
        """Imposta box, template, quad e tracker MIL a partire da un box (float)."""
        h, w = frame.shape[:2]
        box = _clamp_box(box, w, h)
        s = _SCALA_LAVORO
        tx1, ty1 = int(round(box[0] * s)), int(round(box[1] * s))
        tx2, ty2 = int(round(box[2] * s)), int(round(box[3] * s))
        patch = gray[ty1:ty2, tx1:tx2]
        if patch.shape[0] < 8 or patch.shape[1] < 8:
            return None
        self._template = patch.copy()
        self._box = list(box)
        if self._box_out is None or not mantieni_out:
            self._box_out = list(box)
        else:
            self._box_out = [self.ema * o + (1.0 - self.ema) * n
                             for o, n in zip(self._box_out, box)]
        self._ultimo_agg = frame_idx

        quad = _raffina_quad(frame, box) if self.raffina_quad else None
        bw, bh = box[2] - box[0], box[3] - box[1]
        if quad is None:
            self._quad_rel = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        else:
            self._quad_rel = [((x - box[0]) / bw, (y - box[1]) / bh) for x, y in quad]

        if self.tracker_tipo == "mil":
            self._avvia_mil(frame, box)
        return self._costruisci_traccia(frame_idx, "detector", conf, (h, w),
                                        con_quad=quad is not None)

    def _avvia_mil(self, frame, box) -> None:
        try:
            self._mil = cv2.TrackerMIL_create()
            self._mil.init(frame, (int(box[0]), int(box[1]),
                                   int(box[2] - box[0]), int(box[3] - box[1])))
        except (AttributeError, cv2.error) as e:
            warnings.warn(f"TrackerMIL non disponibile ({e}): ripiego sul template matching.")
            self._mil = None
            self.tracker_tipo = "template"

    def _segui(self, frame, gray):
        """Un passo di tracking -> (box [x1,y1,x2,y2] | None, somiglianza 0-1)."""
        if self.tracker_tipo == "mil" and self._mil is not None:
            try:
                ok, bb = self._mil.update(frame)
            except cv2.error:
                return None, 0.0
            if not ok:
                return None, 0.0
            x, y, bw, bh = [float(v) for v in bb]
            box = [x, y, x + bw, y + bh]
            return box, self._somiglianza_in_box(gray, box)
        return self._segui_template(frame, gray)

    def _segui_template(self, frame, gray):
        s = _SCALA_LAVORO
        th, tw = self._template.shape[:2]
        H, W = frame.shape[:2]
        x1, y1, x2, y2 = self._box
        bw, bh = x2 - x1, y2 - y1
        r = max(40.0, 0.25 * bh)                       # raggio di ricerca (px frame)
        gx1 = int(math.floor(max(0.0, x1 - r) * s))
        gy1 = int(math.floor(max(0.0, y1 - r) * s))
        gx2 = int(math.ceil(min(float(W), x2 + r) * s))
        gy2 = int(math.ceil(min(float(H), y2 + r) * s))
        regione = gray[gy1:gy2, gx1:gx2]
        if regione.shape[0] < th or regione.shape[1] < tw:
            return None, 0.0
        res = cv2.matchTemplate(regione, self._template, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if not np.isfinite(maxv):
            return None, 0.0
        nx1 = (gx1 + maxloc[0]) / s
        ny1 = (gy1 + maxloc[1]) / s
        return [nx1, ny1, nx1 + bw, ny1 + bh], float(max(0.0, min(1.0, maxv)))

    def _somiglianza_in_box(self, gray, box) -> float:
        """Somiglianza fra il template e il contenuto di `box` (usata col tracker MIL)."""
        s = _SCALA_LAVORO
        th, tw = self._template.shape[:2]
        x1, y1, x2, y2 = [int(round(v * s)) for v in box]
        x1, y1 = max(0, x1), max(0, y1)
        patch = gray[y1:y2, x1:x2]
        if patch.shape[0] < 8 or patch.shape[1] < 8:
            return 0.0
        patch = cv2.resize(patch, (tw, th), interpolation=cv2.INTER_AREA)
        v = float(cv2.matchTemplate(patch, self._template, cv2.TM_CCOEFF_NORMED)[0, 0])
        return float(max(0.0, min(1.0, v))) if np.isfinite(v) else 0.0

    def _aggiorna_template(self, gray, sim: float, frame_idx: int) -> None:
        """EMA del template: raro e solo con somiglianza alta, per non inseguire il drift."""
        if sim < _SOGLIA_AGG_TEMPLATE or frame_idx - self._ultimo_agg < _AGG_TEMPLATE_OGNI:
            return
        s = _SCALA_LAVORO
        th, tw = self._template.shape[:2]
        x1, y1 = int(round(self._box[0] * s)), int(round(self._box[1] * s))
        patch = gray[y1:y1 + th, x1:x1 + tw]
        if patch.shape != self._template.shape:
            return
        self._template = cv2.addWeighted(self._template, 1.0 - _ALFA_TEMPLATE,
                                         patch, _ALFA_TEMPLATE, 0.0)
        self._ultimo_agg = frame_idx

    def _costruisci_traccia(self, frame_idx, origine, conf, shape, con_quad: bool = True) -> Traccia:
        h, w = shape
        x1, y1, x2, y2 = _clamp_box(self._box_out, w, h)
        quad = None
        if self._quad_rel is not None and con_quad is not False and self._quad_e_reale():
            bw, bh = x2 - x1, y2 - y1
            quad = [(x1 + u * bw, y1 + v * bh) for u, v in self._quad_rel]
        return Traccia(int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)),
                       float(min(max(conf, 0.0), 1.0)), origine, int(frame_idx), quad)

    def _quad_e_reale(self) -> bool:
        """True se il quad relativo non e' il semplice rettangolo (altrimenti e' inutile)."""
        rett = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        return any(abs(a - c) > 1e-6 or abs(b - d) > 1e-6
                   for (a, b), (c, d) in zip(self._quad_rel, rett))
