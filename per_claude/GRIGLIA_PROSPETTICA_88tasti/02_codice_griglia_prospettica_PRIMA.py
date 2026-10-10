"""
Griglia prospettica dei tasti, frame per frame (ripresa a mano libera).

Modello: spazio canonico (u, v) in LARGHEZZE DI TASTO BIANCO.
  u = 0 : bordo sinistro del Do centrale (C4); un bianco = 1 unita'.
  v = 0 : bordo posteriore dei tasti (dove partono i neri); v cresce verso il suonatore.
  neri  : v in [0, LB];   bianchi: v in [0, LW].
Per ogni frame si stima un'omografia H (canonico -> immagine) cosi':
  1. predizione: flusso ottico LK sui punti della tastiera (frame t-1 -> t);
  2. affinamento: si misurano i neri veri (righe scure) + fondo dei neri + feltro rosso
     e si ristima H con RANSAC.
Nessuna dipendenza oltre cv2 / numpy.
"""
from __future__ import annotations

import cv2
import numpy as np

NOMI = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NERI_PC = {1: -0.10, 3: 0.10, 6: -0.12, 8: 0.0, 10: 0.12}      # come keyboard_grid._OFFSET_NERI
LB = 4.1          # lunghezza dei neri (in larghezze di bianco)
LW = 6.2          # lunghezza visibile dei bianchi
BW = 0.66         # larghezza del nero (in bianchi)
V_FELTRO = -0.08  # posizione v del feltro rosso
NOTA_MIN, NOTA_MAX = 36, 96
_SOGLIA_FERMO = 0.05      # differenza media (livelli) sotto cui l'immagine e' "ferma"
_SOGLIA_TAGLIO = 20.0     # differenza media sopra cui si ha un cambio di inquadratura


def e_nero(n): return (n % 12) in _NERI_PC
def nome(n): return f"{NOMI[n % 12]}{n // 12 - 1}"


def _indice_bianco(n):               # indice del bianco n rispetto a C4=0
    base = 60
    cont = 0
    if n >= base:
        return sum(1 for k in range(base, n) if not e_nero(k))
    return -sum(1 for k in range(n, base) if not e_nero(k))


def u_bianco(n):
    return float(_indice_bianco(n))


def u_nero(n):
    return _indice_bianco(n - 1) + 1 + _NERI_PC[n % 12]


NERI = [n for n in range(NOTA_MIN, NOTA_MAX + 1) if e_nero(n)]
BIANCHI = [n for n in range(NOTA_MIN, NOTA_MAX + 1) if not e_nero(n)]


def proietta(H, pts):
    p = np.float32(pts).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(p, H).reshape(-1, 2)


def poligono_tasto(H, n, lw=LW, lb=LB, bw=BW):
    if e_nero(n):
        uc = u_nero(n)
        c = [(uc - bw / 2, 0), (uc + bw / 2, 0), (uc + bw / 2, lb), (uc - bw / 2, lb)]
    else:
        u = u_bianco(n)
        c = [(u, 0), (u + 1, 0), (u + 1, lw), (u, lw)]
    return proietta(H, c)


def _soglia(g):
    return 0.62 * float(np.percentile(g, 90))


def _runs(mask):
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _scala_px(H, u, v):
    a = proietta(H, [(u, v), (u + 1, v)])
    return float(np.linalg.norm(a[1] - a[0]))


def _dentro(p, w, h, m=0):
    return -m <= p[0] < w + m and -m <= p[1] < h + m


def misure(g, H, T, red=None):
    """Correspondenze (canonico, immagine) misurate attorno alla predizione H."""
    h, w = g.shape
    src, dst = [], []
    for n in NERI:
        uc = u_nero(n)
        vs = np.linspace(0.45, LB - 0.35, 9)
        pts = proietta(H, [(uc, v) for v in vs])
        if not any(_dentro(p, w, h) for p in pts):
            continue
        sc = _scala_px(H, uc, LB / 2)
        for v, (x, y) in zip(vs, pts):
            if not (8 < y < h - 8 and 0 <= x < w):
                continue
            yi = int(round(y))
            lo, hi = int(max(0, x - 0.7 * sc)), int(min(w, x + 0.7 * sc))
            if hi - lo < 4:
                continue
            for a, b in _runs(g[yi, lo:hi] < T):
                if 0.45 * BW * sc <= (b - a) <= 1.35 * BW * sc * 1.25:
                    xc = lo + (a + b) / 2.0
                    if abs(xc - x) < 0.40 * sc:
                        src.append((uc, v)); dst.append((xc, y))
                        break
        # fondo del nero: scendo lungo l'asse finche' diventa chiaro
        p0 = proietta(H, [(uc, LB - 1.0)])[0]
        p1 = proietta(H, [(uc, LB + 1.2)])[0]
        L = int(np.linalg.norm(p1 - p0))
        if L < 5:
            continue
        ts = np.linspace(0, 1, L)
        xs = (p0[0] + ts * (p1[0] - p0[0])).round().astype(int)
        ys = (p0[1] + ts * (p1[1] - p0[1])).round().astype(int)
        ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        if ok.sum() < L * 0.9:
            continue
        xs, ys = np.clip(xs, 0, w - 1), np.clip(ys, 0, h - 1)
        prof = g[ys, xs]
        buio = prof < T
        if buio[:max(3, L // 6)].mean() < 0.8:       # non parte dentro il nero (mano / sfocato)
            continue
        k = int(np.argmax(~buio & (np.convolve(~buio, np.ones(3), "same") >= 3)))
        if k > 0:
            xe, ye = xs[k] + 0.0, ys[k] + 0.0
            # centro orizzontale del nero a quella quota
            row = g[int(ye) - 3, max(0, int(xe - sc)):min(w, int(xe + sc))] < T
            rr = _runs(row)
            if rr:
                a, b = min(rr, key=lambda r: abs((r[0] + r[1]) / 2 + max(0, int(xe - sc)) - xe))
                if 0.45 * BW * sc <= (b - a) <= 1.6 * BW * sc:
                    xe = max(0, int(xe - sc)) + (a + b) / 2.0
            src.append((uc, LB)); dst.append((xe, ye - 1.5))
    # feltro rosso = bordo posteriore (vincola solo v)
    if red is not None:
        us = np.arange(-9, 10, 0.5)
        for u in us:
            x, y = proietta(H, [(u, V_FELTRO)])[0]
            if not (0 <= x < w and 12 < y < h - 12):
                continue
            sc = _scala_px(H, u, 0)
            xi = int(x)
            lo, hi = int(max(0, y - 0.4 * sc)), int(min(h, y + 0.4 * sc))
            col = red[lo:hi, max(0, xi - 1):xi + 2].mean(axis=1) > 40
            if col.sum() >= 3:
                yy = lo + np.where(col)[0].mean()
                src.append((u, V_FELTRO)); dst.append((x, yy))
    return np.float32(src), np.float32(dst)


def affina(g, H, red, iters=3):
    T = _soglia(g)
    n_in = 0
    for _ in range(iters):
        s, d = misure(g, H, T, red)
        if len(s) < 12:
            break
        H2, m = cv2.findHomography(s, d, cv2.RANSAC, 3.0)
        if H2 is None or m.sum() < 10:
            break
        H, n_in = H2, int(m.sum())
    return H, n_in


def maschera_tastiera(H, shape):
    h, w = shape
    poly = proietta(H, [(-12, 0), (12, 0), (12, LW), (-12, LW)])
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.int32(poly)], 255)
    return m


def flusso(prev, cur, H_prev):
    m = maschera_tastiera(H_prev, prev.shape)
    p0 = cv2.goodFeaturesToTrack(prev, 400, 0.01, 6, mask=m)
    if p0 is None or len(p0) < 12:
        return np.eye(3)
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None, winSize=(31, 31), maxLevel=4)
    ok = st.ravel() == 1
    if ok.sum() < 12:
        return np.eye(3)
    Hf, mm = cv2.findHomography(p0[ok], p1[ok], cv2.RANSAC, 3.0)
    return Hf if Hf is not None else np.eye(3)


def rosso(frame):
    b, g, r = [frame[..., i].astype(np.int16) for i in range(3)]
    return (r - (g + b) // 2).astype(np.int16)


# ------------------------------------------------- ancoraggio dal profilo dei tasti
# Il passo si misura confrontando il profilo di colonne scure (i tasti neri su fondo
# bianco) con la maschera del modello (neri + bianchi): il confronto e' sensibile alla
# SCALA, quindi sceglie l'ottava di passo giusta. I centri dei run invece si incatenano
# anche a passi sbagliati (meta' o doppio), per questo il filtro sulle larghezze dei
# run da solo non basta quando la tastiera e' lontana (neri piu' stretti di 1.5% di w).

_RES_LUT = 0.02        # risoluzione della maschera attesa (in larghezze di bianco)
_LARG_BANDA = 0.14     # altezza della banda di righe del profilo (frazione di h)


def _lut_attesa():
    """Maschera attesa su u in [0, 7) (1 = tasto nero), centrata e normalizzata."""
    u = np.arange(0.0, 7.0, _RES_LUT)
    m = np.zeros(u.size)
    for n in NERI[:5]:                              # un'ottava completa di neri
        o = u_nero(n) % 7.0
        m[np.abs(((u - o + 3.5) % 7.0) - 3.5) < BW / 2.0] = 1.0
    return m - m.mean()


_LUT_ATTESA = _lut_attesa()
_LUT_SCARTO = float(_LUT_ATTESA.std())


def _ncc_profilo(prof, s, fasi):
    """Correlazione (NCC) fra profilo di colonne e maschera attesa, per ogni fase."""
    out = np.zeros(fasi.size)
    p = prof - prof.mean()
    np_ = float(np.linalg.norm(p))
    if np_ < 1e-9 or s < 2.0:
        return out
    # il profilo ha una riga per colonna: la maschera campionata ha scarto ~ quello della
    # tavola, quindi il denominatore e' |p| * sqrt(n_colonne) * scarto
    den = np_ * np.sqrt(prof.size) * _LUT_SCARTO
    if den < 1e-9:
        return out
    iu = np.arange(prof.size, dtype=np.float64) / s
    for k, f0 in enumerate(fasi):
        idx = np.rint((iu - f0) % 7.0 / _RES_LUT).astype(np.int64) % _LUT_ATTESA.size
        out[k] = float(p @ _LUT_ATTESA[idx]) / den
    return out


def _bande_righe(g, T, w, h):
    """Bande di righe candidate per il profilo (dove ci sono tasti neri)."""
    wmin = max(3, int(0.008 * w))
    wmax = max(6, int(0.075 * w))
    ys = [y for y in range(max(3, int(0.04 * h)), int(0.88 * h))
          if sum(1 for a, b in _runs(g[y] < T) if wmin <= b - a <= wmax) >= 5]
    if not ys:
        return []
    blocchi, cur = [], [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] <= 6:
            cur.append(y)
        else:
            blocchi.append(cur); cur = [y]
    blocchi.append(cur)
    blocchi.sort(key=len, reverse=True)
    alt = max(6, int(_LARG_BANDA * h))
    bande = []
    for b in blocchi[:2]:
        b0, b1 = b[0], b[-1]
        for q in (0.0, 0.25, 0.5, 0.75):
            ya = int(b0 + q * max(0, b1 - b0))
            if ya + 6 <= min(h, ya + alt):
                bande.append((ya, min(h, ya + alt)))
    return bande


def _cerca_profilo(prof, s_lo, s_hi, passo_s, passo_f):
    """Miglior (s, fase, ncc) sul profilo dato."""
    mig = None
    s = s_lo
    while s <= s_hi:
        fasi = np.arange(0.0, 7.0, passo_f)
        v = _ncc_profilo(prof, s, fasi)
        j = int(np.argmax(v))
        if mig is None or v[j] > mig[2]:
            mig = (float(s), float(fasi[j]), float(v[j]))
        s += passo_s
    return mig


def passo_profilo(frame):
    """
    Passo dei tasti (px per tasto bianco) dal profilo: (s, fase, ncc, ya, yb) o None.

    La fase e' in larghezze di bianco: il centro di un nero sta a `x = fase + s * u`.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = _soglia(g)
    s_lo, s_hi = w / 60.0, w / 10.0           # pianoforte reale: 52 bianchi al massimo
    mig = None
    for ya, yb in _bande_righe(g, T, w, h):
        prof = (g[ya:yb] < T).mean(axis=0)
        grosso = _cerca_profilo(prof, s_lo, s_hi, max(1.0, 0.04 * s_lo), 0.30)
        if grosso is None:
            continue
        fine = _cerca_profilo(prof, grosso[0] - 1.5, grosso[0] + 1.5, 0.15, 0.10)
        if fine is None:
            continue
        best = fine if fine[2] > grosso[2] else grosso
        if mig is None or best[2] > mig[2]:
            mig = (best[0], best[1], best[2], ya, yb)
    return mig


def H_profilo(frame, nota_gruppo2=61):
    """Omografia grezza dal profilo (affine, scala isotropa): passo, fase, quota."""
    p = passo_profilo(frame)
    if p is None:
        return None
    s, fase, _, _, _ = p
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    # ottava assoluta: il gruppo da DUE neri piu' vicino al centro e' [nota, nota+2]
    giu, su = u_nero(nota_gruppo2), u_nero(nota_gruppo2 + 2)
    base = 0.5 * (giu + su)
    k_ott = int(round(((w / 2.0 - fase) / s - base) / 7.0))
    fase += 7.0 * k_ott * s
    # bordo posteriore dei tasti: prima riga con neri (come H_iniziale classico)
    T = _soglia(g)
    wmin = max(3, int(0.008 * w))
    wmax = max(6, int(0.075 * w))
    ys = [y for y in range(max(3, int(0.04 * h)), int(0.88 * h))
          if sum(1 for a, b in _runs(g[y] < T) if wmin <= b - a <= wmax) >= 5]
    if not ys:
        return None
    y_back = float(ys[0])
    # scala verticale: distanza fra bordo posteriore e punte dei neri (LB in bianchi)
    xs = []
    for n in NERI[:5]:
        o = u_nero(n) % 7.0
        for k in range(-2, int(w / (7.0 * s)) + 3):
            x = fase + s * (o + 7.0 * k)
            if 2.0 <= x < w - 2.0:
                xs.append(x)
    s_y = s
    if len(xs) >= 6:
        osc = (g[:, np.rint(xs).astype(int)] < T).mean(axis=1)
        i0 = int(min(h - 1, max(0, y_back)))
        i1 = int(min(h - 1, y_back + (LB + 2.0) * s))
        sotto = i0 + int(np.argmax(osc[i0:i1 + 1] < 0.55))     # punte dei neri
        if i0 < sotto < i1 and osc[i0:sotto].mean() > 0.6:
            misura = (sotto - y_back) / LB
            if 0.5 * s <= misura <= 1.6 * s:
                s_y = misura
    return np.float64([[s, 0.0, fase], [0.0, s_y, y_back], [0.0, 0.0, 1.0]])


def _H_iniziale_classico(frame, nota_gruppo2=61):
    """
    Frame 0, automatico: neri a due quote -> gruppi 2/3 dal passo -> omografia grezza.
    `nota_gruppo2` = nota del primo nero del gruppo da DUE neri piu' vicino al centro
    (C#4 = 61 di default). Lo schema 2/3 fissa la nota entro l'ottava, non l'ottava.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = _soglia(g)
    lo, hi = 0.015 * w, 0.075 * w

    def neri_riga(y):
        return [((a + b) / 2.0, b - a) for a, b in _runs(g[y] < T) if lo <= b - a <= hi]

    ys = [y for y in range(int(0.15 * h), int(0.85 * h)) if len(neri_riga(y)) >= 5]
    if not ys:
        raise RuntimeError("tasti neri non trovati sul primo frame")
    blocchi, cur = [], [ys[0]]
    for y in ys[1:]:                              # blocco piu' lungo di righe con >=5 neri
        if y - cur[-1] <= 4:
            cur.append(y)
        else:
            blocchi.append(cur); cur = [y]
    blocchi.append(cur)
    ys = max(blocchi, key=len)
    ya = ys[0] + 25
    yb = ys[0] + int(0.55 * (ys[-1] - ys[0]))
    ra = [c for c, _ in neri_riga(ya)]
    rb = [c for c, _ in neri_riga(yb)]
    if len(ra) < 5 or len(rb) < 5:
        raise RuntimeError("neri insufficienti sul primo frame")
    rb_ok, ra_ok = [], []                         # accoppio per vicinanza (un nero puo' mancare in una riga)
    for c in ra:
        d = [abs(c - x) for x in rb]
        j = int(np.argmin(d))
        if d[j] < 0.12 * w:
            ra_ok.append(c); rb_ok.append(rb[j])
    if len(ra_ok) < 5:
        raise RuntimeError("neri incoerenti fra le due quote del primo frame")
    ra, rb = ra_ok, rb_ok
    sp = np.diff(ra)
    piccolo = float(np.median(sp[sp < 1.4 * sp.min()]))
    wpx = piccolo / 1.15
    grande = sp > 1.4 * sp.min()
    # gruppi separati dai passi grandi
    gruppi, cur = [], [0]
    for i, gr in enumerate(grande):
        if gr:
            gruppi.append(cur); cur = [i + 1]
        else:
            cur.append(i + 1)
    gruppi.append(cur)
    due = [k for k, gp in enumerate(gruppi) if len(gp) == 2]
    if not due:
        raise RuntimeError("nessun gruppo da 2 neri completo sul primo frame")
    k2 = min(due, key=lambda k: abs(np.mean([ra[i] for i in gruppi[k]]) - w / 2))
    # assegno le note: C# D# | F# G# A# | C# D# | ...
    seq = [1, 3, 6, 8, 10]
    note = {}
    i0 = gruppi[k2][0]
    pc0 = nota_gruppo2
    k = 0
    pos = 0
    # indice assoluto nella sequenza dei neri (da nota_gruppo2 avanti e indietro)
    ordine = [n for n in range(NOTA_MIN, NOTA_MAX + 1) if e_nero(n)]
    j0 = ordine.index(nota_gruppo2)
    for i in range(len(ra)):
        note[i] = ordine[j0 + (i - i0)]
    src, dst = [], []
    for i in range(len(ra)):
        u = u_nero(note[i])
        src += [(u, (ya - ys[0]) / wpx), (u, (yb - ys[0]) / wpx)]
        dst += [(ra[i], ya), (rb[i], yb)]
    H, _ = cv2.findHomography(np.float32(src), np.float32(dst), cv2.RANSAC, 4.0)
    if H is None:
        raise RuntimeError("omografia iniziale non calcolabile")
    return H


def H_iniziale(frame, nota_gruppo2=61):
    """
    Griglia iniziale senza storia: prova l'ancoraggio dal profilo (passo certo anche
    quando la tastiera e' lontana) e quello classico, poi tiene il migliore.

    Il confronto si fa sugli inlier di `affina` sul frame: una griglia sbagliata
    aggancia pochi tasti veri, una giusta ne aggancia decine.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    red = rosso(frame)
    cand: list[tuple[np.ndarray, int]] = []
    try:
        Hp = H_profilo(frame, nota_gruppo2)
    except (RuntimeError, ValueError):
        Hp = None
    if Hp is not None:
        H2, k2 = affina(g, Hp, red, 3)
        cand.append((np.float64(H2), int(k2)) if k2 >= 10 else (np.float64(Hp), int(k2)))
    try:
        Hc = np.float64(_H_iniziale_classico(frame, nota_gruppo2))
        H3, k3 = affina(g, Hc, red, 3)
        cand.append((np.float64(H3), int(k3)) if k3 >= 10 else (np.float64(Hc), int(k3)))
    except (RuntimeError, ValueError):
        pass
    if not cand:
        raise RuntimeError("griglia iniziale non calcolabile")
    return max(cand, key=lambda c: c[1])[0]


def _disegna(f, H, etichette=True):
    o = f.copy()
    for n in BIANCHI:
        cv2.polylines(o, [np.int32(poligono_tasto(H, n))], True, (60, 220, 60), 2, cv2.LINE_AA)
    for n in NERI:
        cv2.polylines(o, [np.int32(poligono_tasto(H, n))], True, (255, 160, 30), 2, cv2.LINE_AA)
    if etichette:
        h, w = f.shape[:2]
        for n in BIANCHI:
            p = poligono_tasto(H, n)
            x, y = (p[2] + p[3]) / 2
            if 0 < x < w - 14 and 0 < y < h - 4:
                t = nome(n)
                pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
                cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return o


def _celle(H, n, k=3):
    """k celle lungo la profondita' del tasto (punta/centro/base): poligoni nel frame."""
    if e_nero(n):
        uc, a, b, L = u_nero(n), u_nero(n) - BW / 2, u_nero(n) + BW / 2, LB
    else:
        a = u_bianco(n); b = a + 1; L = LW
        if (n + 1) <= NOTA_MAX and e_nero(n + 1):      # a destra c'e' un nero: lascio il tasto intero
            pass
    out = []
    for j in range(k):
        v0, v1 = L * j / k, L * (j + 1) / k
        out.append(proietta(H, [(a, v0), (b, v0), (b, v1), (a, v1)]))
    return out


def main(argv=None):
    import argparse, json, time
    from pathlib import Path
    p = argparse.ArgumentParser(description="Griglia prospettica dei tasti, frame per frame.")
    p.add_argument("video")
    p.add_argument("-o", "--output", default="out_griglia")
    p.add_argument("--nota-gruppo2", type=int, default=61,
                   help="nota del primo nero del gruppo da 2 neri piu' vicino al centro (61=C#4)")
    p.add_argument("--senza-json", action="store_true")
    a = p.parse_args(argv)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        raise SystemExit(f"impossibile aprire {a.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W, Hh = int(cap.get(3)), int(cap.get(4))
    # H.264 (`avc1`) e' l'unico mp4 che i browser riproducono: se questo build di OpenCV non
    # ha un encoder H.264 si ripiega su mp4v (MPEG-4 Part 2), leggibile fuori dal browser.
    vw = cv2.VideoWriter(str(out / "griglia.mp4"), cv2.VideoWriter_fourcc(*"avc1"), fps, (W, Hh))
    if not vw.isOpened():
        vw = cv2.VideoWriter(str(out / "griglia.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (W, Hh))
    H, prev, i, doc = None, None, 0, []
    t0 = time.time()
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if H is None:
            H = H_iniziale(f, a.nota_gruppo2)
            Hp = H
        else:
            diff = float(np.mean(np.abs(prev.astype(np.int16) - g.astype(np.int16))))
            if diff < _SOGLIA_FERMO:              # immagine identica: geometria invariata
                Hp = H
            elif diff >= _SOGLIA_TAGLIO:          # cambio di inquadratura: griglia da zero
                try:
                    H = H_iniziale(f, a.nota_gruppo2)
                except (RuntimeError, ValueError):
                    pass
                Hp = H
            else:
                Hp = flusso(prev, g, H) @ H
        H2, k = affina(g, Hp, rosso(f), 3)
        H = H2 if k >= 10 else Hp
        prev = g
        vw.write(_disegna(f, H))
        if i == 0:
            cv2.imwrite(str(out / "primo_frame_griglia.jpg"), _disegna(f, H))
        if not a.senza_json:
            tasti = {}
            for n in BIANCHI + NERI:
                pol = poligono_tasto(H, n)
                if not (np.isfinite(pol).all() and (pol[:, 0] > -50).any() and (pol[:, 0] < W + 50).any()):
                    continue
                if pol[:, 0].max() < 0 or pol[:, 0].min() > W:
                    continue
                tasti[str(n)] = {"nome": nome(n), "nero": e_nero(n),
                                 "poligono": np.round(pol, 1).tolist(),
                                 "celle_profondita": [np.round(c, 1).tolist() for c in _celle(H, n)]}
            doc.append({"frame": i, "t": round(i / fps, 4), "inlier": k,
                        "H": np.round(H, 6).tolist(), "tasti": tasti})
        i += 1
    cap.release(); vw.release()
    if not a.senza_json:
        (out / "griglia.json").write_text(json.dumps(
            {"video": Path(a.video).name, "fps": fps, "n_frame": i,
             "modello": {"LB": LB, "LW": LW, "BW": BW, "u0": "bordo sinistro di C4"},
             "frames": doc}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"{i} frame in {time.time() - t0:.1f} s -> {out}/")


if __name__ == "__main__":
    main()
