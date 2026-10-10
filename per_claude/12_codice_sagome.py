"""
Sagome — "dove guardare", per nota e per frame, misurato sul singolo video.

Motore "calibrato", fase 1-3 (BRIEF_CLAUDE_2_SAGOME.md).

Una SAGOMA e' un rettangolo: l'area del frame dove si decide se *quella* nota e'
premuta *in quel* frame. Nessun modello da addestrare: geometria misurata.

COME SI MISURA
--------------
1. regione_tastiera(): quadrilatero della tastiera per frame (YOLO + tracker gia'
   in keyboard_tracker.py, oppure i 4 angoli dati a mano).
2. riquadri_per_frame(): ogni frame viene raddrizzato (omografia) in una striscia
   canonica. Sulla striscia, con la MEDIANA di molti frame (le mani si muovono, i
   tasti no), si misura:
     * la banda dei tasti neri (righe con piu' alternanza scuro/chiaro);
     * i centri dei neri -> larghezza del tasto bianco `w` (spaziature w / 2w);
     * l'estensione reale della tastiera (colonne "tasto" chiare nella fascia frontale);
     * la FASE dei neri (schema 2-3 = spaziature 1,2,1,1,2) -> quale nota e' ogni tasto.
   Poi per OGNI frame un piccolo scarto orizzontale (correlazione del profilo dei
   neri col modello, entro +-0.3 w) corregge la deriva: un frame con confidenza
   bassa riusa l'ultimo scarto buono (e abbassa la confidenza); non inventa nulla.
3. Un tasto e' `visibile` solo se sta per intero dentro la tastiera misurata.
   Le note non inquadrate non hanno riquadri e non compaiono in `visibili`.

OTTAVA (D3): lo schema dei neri dice la nota entro l'ottava (fase), NON l'ottava.
Si calcolano tutte le posizioni compatibili con 21..108 (e con nota_min/nota_max).
Se resta una sola -> `scelta`. Se restano piu' candidate -> `scelta` = None, si
elencano le candidate e si dichiara l'ipotesi usata (`ipotesi_usata`, `ambigua`).
La fase e' verificata su 4 segmenti del video (`segmenti_concordi`).

ASSUNZIONI (da verificare sul video reale):
  * il quadrilatero arriva fino al bordo frontale dei tasti (v=1);
  * le mani non coprono gli stessi tasti per tutto il video (mediana temporale);
  * tasti neri piu' scuri dei bianchi.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from keyboard_grid import MIDI_MAX, MIDI_MIN, _OFFSET_NERI, e_nero, nome_nota

QUI = Path(__file__).resolve().parent
_SCHEMA_NERI = (1, 2, 1, 1, 2)          # spaziature (in bianchi) C#-D#, D#-F#, F#-G#, G#-A#, A#-C#
_PC_NERI = (1, 3, 6, 8, 10)
_N_STIMA = 60                           # frame campionati per la stima globale
_SOGLIA_NCC = 0.35                      # sotto: il frame non corregge lo scarto (confidenza bassa)
_BIANCHI_88 = [n for n in range(MIDI_MIN, MIDI_MAX + 1) if not e_nero(n)]


# ------------------------------------------------------------------ dati
@dataclass(slots=True)
class RiquadroNota:
    nota: int
    nome: str
    nero: bool
    frame: int
    t: float
    x1: int
    y1: int
    x2: int
    y2: int
    visibile: bool
    confidenza: float


@dataclass
class SagomeVideo:
    video: str
    fps: float
    n_frame: int
    quad: list
    riquadri: dict
    visibili: list
    ottava: dict


# ------------------------------------------------------------- utilita'
def _apri(video):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"impossibile aprire il video: {video}")
    return cap


def _fps(cap) -> float:
    f = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    return f if math.isfinite(f) and f > 0 else 30.0


def _lati(q: np.ndarray) -> tuple[float, float]:
    lw = 0.5 * (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3]))
    lh = 0.5 * (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1]))
    return float(lw), float(lh)


def _dim_canonica(q: np.ndarray) -> tuple[int, int]:
    lw, lh = _lati(q)
    wc = int(min(max(round(lw), 400), 2400))
    hc = int(min(max(round(wc * lh / max(lw, 1.0)), 60), 900))
    return wc, hc


def _omografia(q: np.ndarray, wc: int, hc: int) -> np.ndarray:
    dst = np.float32([[0, 0], [wc, 0], [wc, hc], [0, hc]])
    return cv2.getPerspectiveTransform(np.float32(q).reshape(4, 2), dst)


def _grigio_canonico(frame, q, wc, hc) -> np.ndarray:
    M = _omografia(q, wc, hc)
    return cv2.cvtColor(cv2.warpPerspective(frame, M, (wc, hc)), cv2.COLOR_BGR2GRAY)


# ---------------------------------------------------------- 1. regione
def regione_tastiera(video, *, quad=None, ogni_frame: bool = True,
                     max_secondi: float | None = None) -> list:
    """
    Quadrilatero (TL, TR, BR, BL) della tastiera per ogni frame.

    quad: se dato (4 punti in pixel del frame) vale per tutti i frame. Altrimenti
    YOLO (`musical keyboard`, ripiego `piano`) + KeyboardTracker. Se `ogni_frame`
    e' False il tracker gira 1 frame su 5 e fra uno e l'altro si tiene l'ultimo quad.
    Serve `weights/yolov8l-oiv7.pt` (nessun download): se manca, errore chiaro.
    """
    cap = _apri(video)
    fps = _fps(cap)
    limite = int(max_secondi * fps) if max_secondi else None
    quad_fisso = None
    if quad is not None:
        quad_fisso = np.float32(quad).reshape(4, 2)
    tracker = None
    if quad_fisso is None:
        pesi = next((p for p in (Path("weights/yolov8l-oiv7.pt"), QUI / "weights/yolov8l-oiv7.pt",
                                 Path("weights/yolov8m-oiv7.pt"), QUI / "weights/yolov8m-oiv7.pt")
                     if p.is_file()), None)
        if pesi is None:
            cap.release()
            raise FileNotFoundError("pesi YOLO non trovati: attesi weights/yolov8l-oiv7.pt "
                                    "(o yolov8m). Nessun download automatico: oppure passa i 4 angoli.")
        from piano_detector import PianoDetector
        from keyboard_tracker import KeyboardTracker
        tracker = KeyboardTracker(PianoDetector(str(pesi), conf=0.15))
    risultato: list = []
    ultimo = None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok or (limite is not None and i >= limite):
            break
        if quad_fisso is not None:
            q = quad_fisso
        else:
            if ogni_frame or i % 5 == 0 or ultimo is None:
                t = tracker.init(frame, i) if i == 0 else tracker.update(frame, i)
                if t is not None:
                    q = (np.float32(t.quad).reshape(4, 2) if t.quad is not None and len(t.quad) == 4
                         else np.float32([[t.x1, t.y1], [t.x2, t.y1], [t.x2, t.y2], [t.x1, t.y2]]))
                    ultimo = q
            q = ultimo
            if q is None:
                i += 1
                risultato.append(None)
                continue
        risultato.append([(float(x), float(y)) for x, y in q])
        i += 1
    cap.release()
    primo = next((q for q in risultato if q is not None), None)
    if primo is None:
        raise RuntimeError("tastiera mai rilevata: abbassa la confidenza o segna i 4 angoli")
    return [q if q is not None else primo for q in risultato]   # prima del 1o rilevamento: il 1o quad


# ------------------------------------------------- 2. misure sulla striscia
def _banda_neri(med: np.ndarray) -> tuple[int, int]:
    """Righe [ya, yb] con piu' alternanza scuro/chiaro (la banda dei neri)."""
    sd = med.std(axis=1)
    sd = np.convolve(sd, np.ones(5) / 5, mode="same")
    ok = sd > 0.5 * sd.max()
    best, cur, start = (0, 0), 0, 0
    for y, v in enumerate(ok):
        if v:
            if cur == 0:
                start = y
            cur += 1
            if cur > best[1] - best[0]:
                best = (start, start + cur)
        else:
            cur = 0
    ya, yb = best
    if yb - ya < 6:
        raise RuntimeError("banda dei tasti neri non trovata (tastiera non inquadrata bene?)")
    return int(ya), int(yb)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out, s = [], None
    for x, v in enumerate(mask):
        if v and s is None:
            s = x
        elif not v and s is not None:
            out.append((s, x))
            s = None
    if s is not None:
        out.append((s, len(mask)))
    return out


def _misura_striscia(med: np.ndarray) -> dict:
    """Misure geometriche sulla striscia mediana: banda, neri, w, estensione tastiera."""
    hc, wc = med.shape
    ya, yb = _banda_neri(med)
    r0, r1 = ya + int(0.15 * (yb - ya)), yb - int(0.15 * (yb - ya))
    prof = med[r0:max(r1, r0 + 1)].mean(axis=0)
    prof_s = np.convolve(prof, np.ones(3) / 3, mode="same")
    soglia, _ = cv2.threshold(np.uint8(np.clip(prof_s, 0, 255)).reshape(1, -1), 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    scuro = prof_s < soglia
    runs = _runs(scuro)
    larg0 = float(np.median([b - a for a, b in runs])) if runs else 0.0
    # estensione: fascia frontale (sotto i neri), colonne chiare; chiusura dei separatori sottili
    f0 = min(hc - 2, yb + int(0.1 * (hc - yb)))
    fr = med[f0:hc].mean(axis=0)
    chiaro = (fr > 0.5 * (fr.max() + fr.min())).astype(np.uint8).reshape(1, -1)
    k = max(3, int(0.5 * larg0))
    chiaro = cv2.morphologyEx(chiaro, cv2.MORPH_CLOSE, np.ones((1, k), np.uint8)).ravel() > 0
    rr = _runs(chiaro)
    if not rr:
        raise RuntimeError("fascia frontale dei tasti non riconoscibile")
    xa, xb = max(rr, key=lambda r: r[1] - r[0])
    # i neri stanno DENTRO la tastiera: fuori dall'estensione sono margini scuri, non tasti
    runs = [(a, b) for a, b in runs if a >= xa and b <= xb]
    if len(runs) < 2:
        raise RuntimeError("meno di 2 tasti neri riconoscibili: impossibile misurare i tasti")
    med_l = float(np.median([b - a for a, b in runs]))
    neri = [(a, b) for a, b in runs if 0.5 * med_l <= (b - a) <= 1.6 * med_l]   # via artefatti
    centri = np.array([(a + b) / 2.0 for a, b in neri])
    sp = np.diff(centri)
    if len(sp) == 0:
        raise RuntimeError("tasti neri insufficienti per stimare la larghezza dei bianchi")
    w0 = float(np.median(sp[sp < 1.5 * sp.min()]))          # spaziatura "corta" (~1.1-1.2 w)
    g = np.where(sp / w0 >= 1.4, 2, 1).astype(int)           # 1 = vicini, 2 = c'e' un buco di un bianco
    # w dal modello reale: le spaziature attese non sono esattamente 1 e 2 (i neri sono
    # spostati di _OFFSET_NERI), quindi si usa la somma attesa per la fase compatibile
    attese = [1 + _OFFSET_NERI[3] - _OFFSET_NERI[1], 2 + _OFFSET_NERI[6] - _OFFSET_NERI[3],
              1 + _OFFSET_NERI[8] - _OFFSET_NERI[6], 1 + _OFFSET_NERI[10] - _OFFSET_NERI[8],
              2 + _OFFSET_NERI[1] - _OFFSET_NERI[10]]
    fasi = _fasi_compatibili(g.tolist())
    if fasi:
        w = float(np.mean([sp.sum() / sum(attese[(r + j) % 5] for j in range(len(sp))) for r in fasi]))
    else:
        w = float(sp.sum() / g.sum())
    return {"ya": ya, "yb": yb, "w": w, "centri": centri.tolist(), "gap": g.tolist(),
            "larg_nero": med_l, "span": (int(xa), int(xb)), "wc": wc, "hc": hc}


def _fasi_compatibili(gap: list[int]) -> list[int]:
    """Rotazioni r (classe del 1o nero 0..4) per cui la sequenza di spaziature e' coerente."""
    return [r for r in range(5)
            if all(gap[j] == _SCHEMA_NERI[(r + j) % 5] for j in range(len(gap)))]


def _griglia(m: dict, classe0: int, salto_ottava: int) -> dict:
    """
    Posizioni dei tasti sulla striscia, date la classe del 1o nero e l'ottava.
    Ritorna {nota: (xl, xr, nero, centro)} per i tasti INTERI dentro la tastiera.
    """
    w, c0 = m["w"], m["centri"][0]
    xa, xb = m["span"]
    pc0 = _PC_NERI[classe0]
    off = _OFFSET_NERI[pc0]
    confine = c0 - off * w                      # confine fra il bianco N-1 e il bianco N+1
    # nota del 1o nero: pc0 nell'ottava indicata (salto_ottava = numero MIDI del nero)
    n0 = salto_ottava
    iw = _BIANCHI_88.index(n0 - 1)              # indice del bianco a sinistra del confine
    tol = 0.15 * w
    k_min = int(math.floor((xa - confine) / w)) - 1
    k_max = int(math.ceil((xb - confine) / w)) + 1
    out: dict[int, tuple] = {}
    for j in range(k_min, k_max):               # bianco con bordo sinistro = confine + (j) w, j=0 e' N+1
        idx = iw + 1 + j
        xl = confine + j * w
        xr = xl + w
        if xl >= xa - tol and xr <= xb + tol:
            if not 0 <= idx < len(_BIANCHI_88):      # un tasto inquadrato non esiste sul pianoforte
                raise ValueError("griglia fuori da A0..C8: ottava incompatibile")
            out[_BIANCHI_88[idx]] = (xl, xr, False, (xl + xr) / 2)
    # i neri: fra due bianchi adiacenti (N-1, N+1)
    for n, (xl, xr, _, _) in list(out.items()):
        nn = n + 1
        if nn <= MIDI_MAX and e_nero(nn) and (n + 2) in out:
            conf = xr
            c = conf + _OFFSET_NERI[nn % 12] * w
            hw = m["larg_nero"] / 2.0
            out[nn] = (c - hw, c + hw, True, c)
    return out


def _candidate(m: dict, fasi: list[int], nota_min: int, nota_max: int) -> list[dict]:
    """Tutte le (fase, ottava) compatibili con 21..108 e con la finestra [nota_min, nota_max]."""
    cand = []
    for r in fasi:
        pc = _PC_NERI[r]
        for n0 in range(MIDI_MIN + 1, MIDI_MAX):
            if n0 % 12 != pc or not e_nero(n0) or (n0 - 1) not in _BIANCHI_88:
                continue
            try:
                gr = _griglia(m, r, n0)
            except ValueError:
                continue
            if not gr:
                continue
            note = sorted(gr)
            if note[0] < max(nota_min, MIDI_MIN) or note[-1] > min(nota_max, MIDI_MAX):
                continue
            # lo schema deve coincidere con i neri misurati (anche se i neri ai bordi sono tagliati)
            cand.append({"prima_nota": note[0], "ultima_nota": note[-1], "fase_pc": pc,
                         "nero_di_riferimento": n0})
    cand.sort(key=lambda c: (c["prima_nota"], c["fase_pc"]))
    return cand


def _profilo_neri(g: np.ndarray, ya: int, yb: int) -> np.ndarray:
    r0, r1 = ya + int(0.15 * (yb - ya)), max(yb - int(0.15 * (yb - ya)), ya + 2)
    return g[r0:r1].mean(axis=0).astype(np.float32)


def _scarto_frame(prof: np.ndarray, modello: np.ndarray, max_s: int) -> tuple[int, float]:
    """Scarto s (px) che massimizza la correlazione normalizzata col modello dei neri."""
    migliore, ncc_m = 0, -1.0
    p = prof - prof.mean()
    np_ = float(np.linalg.norm(p)) + 1e-6
    for s in range(-max_s, max_s + 1):
        m = np.roll(modello, s)
        m = m - m.mean()
        c = float(-(p @ m) / (np_ * (float(np.linalg.norm(m)) + 1e-6)))   # neri = scuro
        if c > ncc_m:
            migliore, ncc_m = s, c
    return migliore, ncc_m


# ------------------------------------------------------ 2b. cuore: riquadri
def riquadri_per_frame(video, quad, *, nota_min: int = 21, nota_max: int = 108,
                       prima_nota: int | None = None,
                       max_secondi: float | None = None) -> SagomeVideo:
    """
    Riquadri per nota e per frame (proiezione della griglia + raffinamento sull'immagine).

    quad: lista di quad (uno per frame, da regione_tastiera) oppure un solo quad.
    nota_min/nota_max: finestra entro cui l'ottava puo' cadere (restringe le candidate).
    prima_nota: (opzionale) prima nota visibile, indicata dall'utente: risolve l'ambiguita'.
    Il raffinamento fallito su un frame NON crea riquadri nuovi: riusa l'ultimo scarto
    buono con confidenza ridotta. Frame con confidenza < soglia vengono marcati nel campo
    `confidenza` e il motore non li usa per decidere.
    """
    cap = _apri(video)
    fps = _fps(cap)
    limite = int(max_secondi * fps) if max_secondi else None
    quad_lista = quad if (len(quad) and isinstance(quad[0][0], (tuple, list))) else None
    q_unico = None if quad_lista is not None else np.float32(quad).reshape(4, 2)

    def q_del(i):
        if q_unico is not None:
            return q_unico
        return np.float32(quad_lista[min(i, len(quad_lista) - 1)]).reshape(4, 2)

    # --- passo A: frame campione per la stima globale (mediana)
    n_tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if limite is not None and n_tot:
        n_tot = min(n_tot, limite)
    if n_tot <= 0:                                   # conteggio non affidabile: lo si misura
        c2 = _apri(video)
        n_tot = 0
        while c2.grab() and (limite is None or n_tot < limite):
            n_tot += 1
        c2.release()
    passo = max(1, n_tot // _N_STIMA)
    wc, hc = _dim_canonica(q_del(0))
    campioni: list[np.ndarray] = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok or i >= n_tot:
            break
        if i % passo == 0:
            campioni.append(_grigio_canonico(frame, q_del(i), wc, hc))
        i += 1
    cap.release()
    if not campioni:
        raise RuntimeError("video vuoto o illeggibile")
    pila = np.stack(campioni).astype(np.float32)
    med = np.median(pila, axis=0)
    m = _misura_striscia(med)
    # fase per segmenti del video (4): servono a dichiarare quanto e' stabile
    seg = np.array_split(np.arange(len(campioni)), min(4, len(campioni)))
    fasi_seg = []
    for idx in seg:
        try:
            ms = _misura_striscia(np.median(pila[idx], axis=0))
            fasi_seg.append(sorted(_fasi_compatibili(ms["gap"])))
        except RuntimeError:
            fasi_seg.append(None)
    fasi = _fasi_compatibili(m["gap"])
    if not fasi:
        raise RuntimeError("lo schema dei tasti neri misurato non e' coerente con un pianoforte "
                           f"(spaziature {m['gap']}): controlla i 4 angoli")
    cand = _candidate(m, fasi, nota_min, nota_max)
    if not cand:
        raise RuntimeError("nessuna ottava compatibile con la finestra richiesta "
                           f"({nota_min}..{nota_max}); fasi {fasi}")

    # --- scelta/dichiarazione dell'ottava
    scelta, usata, motivo = None, None, ""
    if prima_nota is not None:
        ok_u = [c for c in cand if c["prima_nota"] == int(prima_nota)]
        if not ok_u:
            raise RuntimeError(f"prima_nota={prima_nota} non e' fra le candidate: "
                               f"{[c['prima_nota'] for c in cand]}")
        scelta, usata, motivo = ok_u[0]["prima_nota"], ok_u[0], "indicata dall'utente"
    elif len(cand) == 1:
        scelta, usata = cand[0]["prima_nota"], cand[0]
        motivo = "unica posizione compatibile con 21..108 e con lo schema dei neri"
    else:
        usata = min(cand, key=lambda c: abs((c["prima_nota"] + c["ultima_nota"]) / 2 - 64.5))
        motivo = (f"{len(cand)} posizioni compatibili: lo schema dei neri fissa la nota entro "
                  "l'ottava, non l'ottava. Ipotesi usata = la piu' vicina al centro del pianoforte")
    gr = _griglia(m, [r for r in range(5) if _PC_NERI[r] == usata["fase_pc"]][0],
                  usata["nero_di_riferimento"])
    note_vis = sorted(gr)
    ottava = {
        "scelta": scelta, "ambigua": scelta is None,
        "ipotesi_usata": None if scelta is not None else usata["prima_nota"],
        "candidate": cand,
        "prova": {
            "motivo": motivo,
            "n_bianchi_misurati": round((m["span"][1] - m["span"][0]) / m["w"], 2),
            "n_neri_osservati": len(m["centri"]),
            "spaziature_neri": m["gap"],
            "fasi_compatibili_pc": [_PC_NERI[r] for r in fasi],
            "fasi_per_segmento": [None if f is None else [_PC_NERI[r] for r in f] for f in fasi_seg],
            "segmenti_concordi": all(f == sorted(fasi) for f in fasi_seg if f is not None),
            "larghezza_bianco_px": round(m["w"], 2),
            "frame_campione": len(campioni),
            "nota": ("tastiera intera in campo: ottava univoca" if len(cand) == 1 and
                     len(note_vis) >= 80 else None),
        },
    }

    # --- modello del profilo dei neri (binario) per la correzione per frame
    modello = np.full(wc, 255.0, np.float32)
    for n, (xl, xr, nero, c) in gr.items():
        if nero:
            modello[max(0, int(xl)):min(wc, int(math.ceil(xr)))] = 0.0
    max_s = max(2, int(0.3 * m["w"]))
    ya, yb = m["ya"], m["yb"]

    # --- passo B: ogni frame
    cap = _apri(video)
    riq: dict[int, list] = {n: [] for n in note_vis}
    quad_out = []
    s_prec, conf_prec = 0, 0.0
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok or i >= n_tot:
            break
        q = q_del(i)
        quad_out.append([(float(x), float(y)) for x, y in q])
        g = _grigio_canonico(frame, q, wc, hc)
        s, ncc = _scarto_frame(_profilo_neri(g, ya, yb), modello, max_s)
        if ncc >= _SOGLIA_NCC:
            s_prec, conf = s, float(min(1.0, max(0.0, ncc)))
            conf_prec = conf
        else:
            s, conf = s_prec, float(min(conf_prec, max(0.0, ncc)) * 0.5)   # riuso: confidenza ridotta
        Minv = np.linalg.inv(_omografia(q, wc, hc))
        for n, (xl, xr, nero, c) in gr.items():
            y0, y1 = (ya, yb) if nero else (ya, hc - 1)
            pts = np.float32([[xl + s, y0], [xr + s, y0], [xr + s, y1], [xl + s, y1]]).reshape(-1, 1, 2)
            fp = cv2.perspectiveTransform(pts, Minv).reshape(4, 2)
            riq[n].append(RiquadroNota(
                nota=n, nome=nome_nota(n), nero=bool(nero), frame=i, t=round(i / fps, 6),
                x1=int(round(fp[:, 0].min())), y1=int(round(fp[:, 1].min())),
                x2=int(round(fp[:, 0].max())), y2=int(round(fp[:, 1].max())),
                visibile=True, confidenza=round(conf, 3)))
        i += 1
    cap.release()
    s = SagomeVideo(video=Path(str(video)).name, fps=fps, n_frame=i, quad=quad_out,
                    riquadri=riq, visibili=note_vis, ottava=ottava)
    s.ottava["prova"]["geometria_canonica"] = {"wc": wc, "hc": hc, "banda_neri": [ya, yb],
                                               "span_tastiera": list(m["span"])}
    return s


# ------------------------------------------------------------ 3. clip
def _crop(frame, r: RiquadroNota, dim: tuple[int, int], margine: float = 0.25):
    """Crop della nota (riquadro + margine), ridimensionato a `dim` = (larghezza, altezza)."""
    h, w = frame.shape[:2]
    mx, my = (r.x2 - r.x1) * margine, (r.y2 - r.y1) * margine
    x1, x2 = int(max(0, r.x1 - mx)), int(min(w, r.x2 + mx))
    y1, y2 = int(max(0, r.y1 - my)), int(min(h, r.y2 + my))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return np.zeros((dim[1], dim[0], 3), np.uint8)
    return cv2.resize(frame[y1:y2, x1:x2], dim, interpolation=cv2.INTER_AREA)


def _dim_clip(rs: list) -> tuple[int, int]:
    w = float(np.median([r.x2 - r.x1 for r in rs])) * 1.5
    h = float(np.median([r.y2 - r.y1 for r in rs])) * 1.5
    return int(max(16, 2 * round(w / 2))), int(max(16, 2 * round(h / 2)))


def scrivi_clip_per_nota(s: SagomeVideo, video, cartella, *, formato: str = "mp4") -> list[Path]:
    """
    UNA clip per nota inquadrata, lunga TUTTO il video (n_frame frame), con dentro SOLO
    il crop di quella nota (riquadro + 25% di margine, dimensione fissa per clip).
    formato: "mp4" (H.264 via ffmpeg, ripiego mp4v di OpenCV) | "jpeg" (cartella per nota).
    Le note non inquadrate non hanno clip. Il video viene riletto a gruppi di 8 note.
    """
    if formato not in ("mp4", "jpeg"):
        raise ValueError("formato deve essere 'mp4' o 'jpeg'")
    cart = Path(cartella)
    cart.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg")
    dims = {n: _dim_clip(s.riquadri[n]) for n in s.visibili}
    scritti: list[Path] = []
    for gruppo in [s.visibili[k:k + 8] for k in range(0, len(s.visibili), 8)]:
        procs: dict = {}
        for n in gruppo:
            w, h = dims[n]
            if formato == "jpeg":
                (cart / f"{n:03d}").mkdir(exist_ok=True)
                procs[n] = None
            elif ff:
                procs[n] = subprocess.Popen(
                    [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                     "-s", f"{w}x{h}", "-r", f"{s.fps:.6f}", "-i", "-", "-an", "-c:v", "libx264",
                     "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "veryfast",
                     str(cart / f"{n:03d}.mp4")], stdin=subprocess.PIPE)
            else:
                procs[n] = cv2.VideoWriter(str(cart / f"{n:03d}.mp4"),
                                           cv2.VideoWriter_fourcc(*"mp4v"), s.fps, (w, h))
        cap = _apri(video)
        for i in range(s.n_frame):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"il video ha meno frame di quelli attesi ({i} < {s.n_frame})")
            for n in gruppo:
                crop = _crop(frame, s.riquadri[n][i], dims[n])
                if formato == "jpeg":
                    cv2.imwrite(str(cart / f"{n:03d}" / f"{i:06d}.jpg"), crop,
                                [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                elif ff:
                    procs[n].stdin.write(crop.tobytes())
                else:
                    procs[n].write(crop)
        cap.release()
        for n in gruppo:
            p = procs[n]
            if formato == "mp4":
                if ff:
                    p.stdin.close()
                    if p.wait() != 0:
                        raise RuntimeError(f"ffmpeg ha fallito sulla clip della nota {n}")
                else:
                    p.release()
            scritti.append(cart / f"{n:03d}.mp4" if formato == "mp4" else cart / f"{n:03d}")
    return scritti


# ------------------------------------------------------- serializzazione
def salva_sagome(s: SagomeVideo, path) -> Path:
    """sagome.json: riquadri per nota in colonne (x1,y1,x2,y2,confidenza), niente NaN."""
    doc = {
        "video": s.video, "fps": round(s.fps, 6), "n_frame": s.n_frame,
        "quad": [[[round(x, 2), round(y, 2)] for x, y in q] for q in s.quad],
        "visibili": s.visibili, "ottava": s.ottava,
        "riquadri": {str(n): {"nero": rs[0].nero, "nome": rs[0].nome,
                              "x1": [r.x1 for r in rs], "y1": [r.y1 for r in rs],
                              "x2": [r.x2 for r in rs], "y2": [r.y2 for r in rs],
                              "confidenza": [r.confidenza for r in rs],
                              "visibile": [r.visibile for r in rs]}
                     for n, rs in s.riquadri.items()},
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return p


def carica_sagome(path) -> SagomeVideo:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    fps = float(d["fps"])
    riq = {}
    for k, c in d["riquadri"].items():
        n = int(k)
        riq[n] = [RiquadroNota(nota=n, nome=c["nome"], nero=bool(c["nero"]), frame=i,
                               t=round(i / fps, 6), x1=c["x1"][i], y1=c["y1"][i], x2=c["x2"][i],
                               y2=c["y2"][i], visibile=bool(c["visibile"][i]),
                               confidenza=c["confidenza"][i]) for i in range(len(c["x1"]))]
    quad = [[(float(x), float(y)) for x, y in q] for q in d["quad"]]
    return SagomeVideo(video=d["video"], fps=fps, n_frame=int(d["n_frame"]), quad=quad,
                       riquadri=riq, visibili=[int(n) for n in d["visibili"]], ottava=d["ottava"])
