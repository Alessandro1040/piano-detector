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
# Estensione del modello: gli 88 tasti di un pianoforte (A0..C8), come gia' fanno
# sagome.py (`nota_min=21, nota_max=108`) e to_midi.py. Con 36..96 (C2..C7, 61 tasti) i
# tasti fuori finestra NON esistono nel lessico: in un video che inquadra la tastiera
# intera il bordo sinistro restava senza griglia e le pressioni li' non si vedevano.
NOTA_MIN, NOTA_MAX = 21, 108
_SOGLIA_FERMO = 0.05      # differenza media (livelli) sotto cui l'immagine e' "ferma"
_SOGLIA_TAGLIO = 20.0     # differenza media sopra cui, SE la griglia e' persa (meno di 10
                          # inlier nell'affinamento), vale la pena ritrovarla da zero. Da sola
                          # non basta: una panoramica a mano libera supera 20 e la griglia
                          # va inseguita col flusso, non rifatta.


def e_nero(n): return (n % 12) in _NERI_PC
# Convenzione dell'ottava: il numero MIDI 60 (il Do centrale) si scrive C4 nella notazione scientifica
# (default, quella di MIDI/Wikipedia/Scientific Pitch Notation: La0 = 21 ... Do8 = 108). Alcuni
# costruttori (Yamaha, Roland) lo chiamano C3, certi programmi C5. `OFFSET_OTTAVA` si somma
# al numero d'ottava scritto: 0 = scientifica, -1 = Do centrale C3, +1 = Do centrale C5.
OFFSET_OTTAVA = 0
CONVENZIONI = {"scientifica": 0, "c4": 0, "yamaha": -1, "c3": -1, "c5": 1}


def imposta_convenzione(valore):
    """Imposta `OFFSET_OTTAVA` da un nome ("scientifica", "c4", "yamaha", "c3", "c5") o da un intero."""
    global OFFSET_OTTAVA
    v = str(valore).strip().lower()
    if v in CONVENZIONI:
        OFFSET_OTTAVA = CONVENZIONI[v]
    else:
        try:
            OFFSET_OTTAVA = int(v)
        except ValueError:
            raise ValueError(f"convenzione dell'ottava sconosciuta: {valore!r} "
                             f"(usa {', '.join(CONVENZIONI)} oppure un intero)")
    return OFFSET_OTTAVA


def nome(n): return f"{NOMI[n % 12]}{n // 12 - 1 + OFFSET_OTTAVA}"


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
    """Omografia del movimento della tastiera fra due fotogrammi, con la sua qualita'.

    Ritorna `(H, inlier, tracciati)`: `inlier` = punti la cui corrispondenza sta
    sull'omografia trovata, `tracciati` = punti seguiti dall'LK. Il rapporto dice se ha senso
    fidarsi: una panoramica a mano libera ne mette ~0,6..0,8 (misurato 0,63..0,77 sui
    fotogrammi 282..287 di document_5904406621164936944.mp4) mentre un cambio di inquadratura
    non supera ~0,28, perche' li' il flusso sta inseguendo il contenuto vecchio.
    """
    m = maschera_tastiera(H_prev, prev.shape)
    p0 = cv2.goodFeaturesToTrack(prev, 400, 0.01, 6, mask=m)
    if p0 is None or len(p0) < 12:
        return np.eye(3), 0, 0
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None, winSize=(31, 31), maxLevel=4)
    ok = st.ravel() == 1
    if ok.sum() < 12:
        return np.eye(3), 0, int(ok.sum())
    Hf, mm = cv2.findHomography(p0[ok], p1[ok], cv2.RANSAC, 3.0)
    n_in = int(mm.sum()) if mm is not None else 0
    return (Hf if Hf is not None else np.eye(3)), n_in, int(ok.sum())


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
_TASTI_MIN_FINESTRA = 100.0    # passo minimo di ricerca (w/100): vedi il commento in `passo_profilo`
_QUANTI_PICCHI = 4             # picchi grossolani raffinati, per ogni banda di righe
_COERENZA_NERI = (0.5, 1.6)    # larghezza dei tratti scuri della banda / (BW * s)
_RIGHE_MEDIANA = 32            # righe lette (a passo) per la mediana dei tratti scuri


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


def _picchi_profilo(prof, s_lo, s_hi, passo_s, passo_f, quanti=_QUANTI_PICCHI):
    """
    I `quanti` picchi piu' alti della curva grossolana (s, fase, ncc), raffinati.

    Il massimo grossolano non e' per forza il picco giusto: la curva ha una armonica ogni multiplo
    del passo vero e il campionamento grossolano non cade sul massimo di ciascuna (su un fotogramma
    1920x1080 il picco del passo vero e' largo +-0,3 px). Raffinando solo il massimo si rischia di
    raffinare un'armonica e di perdere il passo giusto (vedi `passo_profilo`).
    """
    s, vv, ss, ff = s_lo, [], [], []
    while s <= s_hi:
        fasi = np.arange(0.0, 7.0, passo_f)
        v = _ncc_profilo(prof, s, fasi)
        j = int(np.argmax(v))
        vv.append(float(v[j]))
        ss.append(float(s))
        ff.append(float(fasi[j]))
        s += passo_s
    vv, ss, ff = np.array(vv), np.array(ss), np.array(ff)
    picchi = [i for i in range(vv.size)
              if vv[i] >= vv[max(0, i - 1)] and vv[i] >= vv[min(vv.size - 1, i + 1)]]
    picchi.sort(key=lambda i: -vv[i])
    fuori = []
    for i in picchi[:quanti]:
        fine = _cerca_profilo(prof, max(2.0, ss[i] - 1.5), ss[i] + 1.5, 0.15, 0.10)
        fuori.append(fine if fine is not None and fine[2] > vv[i] else (ss[i], ff[i], vv[i]))
    return fuori


def _larghezza_tratti(g, ya, yb, T, w):
    """
    Larghezza mediana (px) dei tratti scuri "da tasto" nella banda di righe, o None.

    Il tratto di un nero sta fra il 0,4% e il 7,5% di w (come in `banda_neri`: il limite dello 0,8%
    di `_bande_righe` serve a trovare le righe, non a MISURARE un nero). La mediana si legge su
    `_RIGHE_MEDIANA` righe distribuite nella banda: sulla tastiera vera tutte le righe danno la
    stessa larghezza, mentre le bande che cambiano da riga a riga sono proprio quelle che devono
    restare fuori (nel video 87, righe 444..595: mediana 17,00 px con un passo di 1, 2, 4, 8 e 16
    righe; righe 661..812, il tappeto: 32, 33, 33, 32,5 e 32 px).
    """
    lo, hi = max(2.5, 0.004 * w), 0.075 * w
    passo = max(1, (int(yb) - int(ya)) // _RIGHE_MEDIANA)
    larg = []
    for y in range(int(ya), int(yb), passo):
        larg += [b - a for a, b in _runs(g[y] < T) if lo <= b - a <= hi]
    return float(np.median(larg)) if larg else None


def passo_profilo(frame):
    """
    Passo dei tasti (px per tasto bianco) dal profilo: (s, fase, ncc, ya, yb) o None.

    La fase e' in larghezze di bianco: il centro di un nero sta a `x = fase + s * u`.

    Il passo minimo di ricerca non puo' venire dal pianoforte (52 bianchi al massimo, ma in
    fotogramma ne sta una frazione qualsiasi: nel video 87 la tastiera sta in 1417 px su 1920,
    cioe' 27,25 px per bianco, SOTTO il vecchio `w/60` = 32 px). Viene da quello che `_bande_righe`
    riesce ancora a vedere, cioe' un tratto scuro largo `wmin = 0.008 * w`, che per un nero di `BW`
    bianchi vuol dire `wmin / BW` px per bianco: a w = 1920 sono 23,3 px. Si tiene `w/100` = 19,2
    px, appena sotto, per non far dipendere la soglia dalla costante di `_bande_righe`.

    Con la soglia bassa il massimo grossolano di una banda puo' cadere su un'armonica del passo
    vero (nel video 87 il tappeto sotto la tastiera vinceva a 139,07 px, 5 volte 27,8) e puo'
    cadere su un'armonica anche DENTRO la banda giusta: per questo si raffinano i primi
    `_QUANTI_PICCHI` picchi di ogni banda (vedi `_picchi_profilo`) e non solo il massimo.

    La scelta fra le bande, poi, non si fa sul solo NCC: sui video con il tappeto chiaro sotto la
    tastiera l'armonica del tappeto ha NCC piu' ALTO del passo vero (0,336 contro 0,301 su
    `05b7f3df4e2045ea`), mentre i tratti scuri del tappeto sono larghi 0,21 di un nero contro 0,99.
    Una banda vale quindi solo se i tratti scuri al suo interno sono larghi come un nero
    (`_COERENZA_NERI`, in unita' di `BW * s`), e fra le bande che valgono vince l'NCC; se nessuna
    banda vale si torna al solo NCC, come prima.

    Misurato sui 76 video di `web_runs/_prepara` (0_prepara.py): 10 video rotti (il ritaglio
    prendeva il tappeto) passano alla banda dei tasti, 10 spostano il passo di <= 0,1 px restando
    sulla stessa banda, gli altri 56 non cambiano. Costo: 1,65 s contro 0,73 s su un fotogramma
    1920x1080 (2,3x).
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = _soglia(g)
    s_lo, s_hi = w / _TASTI_MIN_FINESTRA, w / 10.0
    passo_s = max(0.5, 0.02 * s_lo)
    fuori = []
    for ya, yb in _bande_righe(g, T, w, h):
        prof = (g[ya:yb] < T).mean(axis=0)
        med = _larghezza_tratti(g, ya, yb, T, w)          # non dipende dal passo: una volta per banda
        for s0, f0, val0 in _picchi_profilo(prof, s_lo, s_hi, passo_s, 0.30):
            r = None if med is None else med / (BW * s0)
            fuori.append((s0, f0, val0, ya, yb,
                          r is not None and _COERENZA_NERI[0] <= r <= _COERENZA_NERI[1]))
    if not fuori:
        return None
    coerenti = [c for c in fuori if c[5]]
    mig = max(coerenti or fuori, key=lambda c: c[2])
    return mig[0], mig[1], mig[2], mig[3], mig[4]


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


def banda_neri(frame):
    """I tasti neri del primo fotogramma: la banda di righe e come si leggono.

    Ritorna `(y0, ya, yb, pieno, leggi)`: `y0` e' la prima riga del blocco dei neri (il bordo
    posteriore dei tasti, cioe' `v = 0` del modello), `ya`/`yb` sono le due righe di misura di
    sempre (il "piatto" del conteggio, dove i neri si vedono TUTTI), `pieno` e' la riga in cui se
    ne vedono di piu' -- `None` quando `ya` e' gia' piena, cioe' quando non c'e' niente da
    correggere -- e `leggi(y)` restituisce `(centro, larghezza)` dei neri su una riga. E' la
    ricetta condivisa: la usa `_H_iniziale_classico` per l'ancora del primo fotogramma e la usa il
    passo 0 (`0_prepara.py`) per la banda e la scala dei neri quando il profilo dei tasti non
    legge -- la' il profilo non puo' dare ne' il passo ne' la fascia.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = _soglia(g)
    # Minimo a ~0.4% di w: con la tastiera lontana i neri veri sono 6-7 px (a w=848 il
    # vecchio minimo 0.015*w = 12.7 px li scartava tutti -> nessun nero, ancoraggio impossibile).
    lo, hi = max(2.5, 0.004 * w), 0.075 * w

    def leggi(y):
        return [((a + b) / 2.0, b - a) for a, b in _runs(g[y] < T) if lo <= b - a <= hi]

    ys = [y for y in range(int(0.15 * h), int(0.85 * h)) if len(leggi(y)) >= 5]
    if not ys:
        raise RuntimeError("tasti neri non trovati sul primo frame")
    blocchi, cur = [], [ys[0]]
    for y in ys[1:]:                              # blocco piu' lungo di righe con >=5 neri
        if y - cur[-1] <= 4:
            cur.append(y)
        else:
            blocchi.append(cur); cur = [y]
    blocchi.append(cur)
    blocco = max(blocchi, key=len)
    y0 = blocco[0]
    conta = {y: len(leggi(y)) for y in blocco}
    cmax = max(conta.values())
    ya, yb = y0 + 25, y0 + int(0.55 * (blocco[-1] - y0))
    # Le righe di misura restano quelle di sempre (geometria e coerenza con le prove di prima).
    # In piu' si dice qual e' la riga "PIENA", quella in cui i neri si vedono tutti: serve a chi
    # decide l'OTTAVA (il centro della tastiera, vedi `_H_iniziale_classico`). Se la riga di
    # misura perde dei neri -- succede quando il fotogramma e' RITAGLIATO in alto: il taglio porta
    # via le righe in cui il blocco si sta ancora formando, la riga di sempre finisce nella coda
    # dove il capo sinistro della tastiera e' in ombra -- il centro letto li' si sposta di mezza
    # ottava e l'ancora cambia ottava. Misurato sul caso b2 (848x464: blocco 168..204 con 40 neri,
    # piatto 183..194 con 41), ritaglio y 121..463: alla riga 197 i neri letti sono 31 invece di
    # 41, il centro dello span va a 479 px invece di 386 e il gruppo da due neri ancorato e'
    # C#5-D#5 invece di C#4-D#4 -- la griglia esce 7 tasti a destra; sul fotogramma intero la riga
    # di misura e' gia' piena e non cambia niente (228 inlier, celle 125..650).
    # `ya` puo' cadere FUORI dal blocco quando i neri si vedono per poche righe (blocco piu' corto
    # di 25: succede sui fotogrammi dove la tastiera e' lontana o la coda del blocco e' coperta):
    # li' non c'e' nessuna riga di misura da confrontare, e l'unica riga di cui fidarsi e' quella
    # piena. (`conta[ya]` diretto era un KeyError: misurato su 2024-09-02_14-10-41.mp4, blocco di
    # 11 righe, passo 0 che moriva con "KeyError: 75".)
    pieno = None if conta.get(ya, 0) >= 0.95 * cmax else max(blocco, key=lambda y: conta[y])
    return y0, ya, yb, pieno, leggi


def _H_iniziale_classico(frame, nota_gruppo2=61):
    """
    Frame 0, automatico: neri a due quote -> gruppi 2/3 dal passo -> omografia grezza.
    `nota_gruppo2` = nota del primo nero del gruppo da DUE neri piu' vicino al centro
    DELLA TASTIERA (C#4 = 61 di default). Lo schema 2/3 fissa la nota entro l'ottava,
    non l'ottava: il riferimento deve essere il centro della tastiera e non del frame,
    perche' con l'inquadratura decentrata il gruppo piu' vicino al centro del frame e'
    quello di un'ottava sopra e tutte le note escono 12 semitoni basse.

    Le due quote di misura sono il PIATTO del conteggio dei neri (le righe in cui si vedono
    tutti), non una riga a distanza fissa dall'inizio del blocco: il centro della tastiera si
    legge dai neri trovati, quindi una riga scelta male (cioe' con l'inizio della tastiera in
    ombra e non letto) lo sposta di mezza ottava e cambia l'ottava dell'ancora -- succede sul
    fotogramma ritagliato in alto, vedi il commento a `piatto` qui sotto.
    """
    w = frame.shape[1]
    y0, ya, yb, pieno, neri_riga = banda_neri(frame)
    ra = [c for c, _ in neri_riga(ya)]
    rb = [c for c, _ in neri_riga(yb)]
    # Il CENTRO della tastiera (che sceglie l'ottava del gruppo da due neri) si legge dalla riga
    # PIENA quando la riga di misura ne perde qualcuno: e' l'unico numero che decide l'ottava, e
    # con lo span amputato a sinistra il gruppo scelto e' quello di un'ottava sopra (vedi
    # `banda_neri`). La geometria (le due righe di misura, il passo, l'omografia) resta quella di
    # sempre: qui si sposta solo l'ottava, non la griglia.
    ra_c = ra if pieno is None else [c for c, _ in neri_riga(pieno)]
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
    # Centro della tastiera: i neri veri formano uno span senza buchi grandi, i blob fuori
    # tastiera (corpo del pianoforte, fondo) hanno buchi >= 3 passi e si tagliano dal centro
    # in fuori. Serve per l'ottava (vedi docstring): e' il centro della tastiera, non del frame.
    reg = [float(x) for x in ra_c]
    c0 = int(np.argmin(np.abs(np.asarray(reg) - np.median(reg))))
    im, jm = c0, c0
    while im > 0 and reg[im] - reg[im - 1] <= 3.6 * piccolo:
        im -= 1
    while jm + 1 < len(reg) and reg[jm + 1] - reg[jm] <= 3.6 * piccolo:
        jm += 1
    xc_tast = 0.5 * (reg[im] + reg[jm])
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
    k2 = min(due, key=lambda k: abs(np.mean([ra[i] for i in gruppi[k]]) - xc_tast))
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
        j = j0 + (i - i0)
        # neri rilevati oltre il range del modello: si scartano (prima IndexError).
        note[i] = ordine[j] if 0 <= j < len(ordine) else None
    src, dst = [], []
    for i in range(len(ra)):
        if note[i] is None:
            continue
        u = u_nero(note[i])
        src += [(u, (ya - y0) / wpx), (u, (yb - y0) / wpx)]
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


# ------------------------------------------------- inseguimento, con i freni
# Il flusso ottico da solo non tiene la griglia sulla tastiera. Quando il fotogramma cambia
# molto (un braccio, un tablet, gente che passa davanti) l'omografia del flusso puo' uscirsene
# con un salto qualsiasi, e da li' in poi la griglia e' persa -- senza che nessuno se ne
# accorga, perche' `affina` continua a trovare qualche inlier su quello che ha in mano.
# Misurato sul video 18 del dataset PianoVAM (2024-02-15_21-40-43, 1080p, a mano libera):
# fino al fotogramma 26 il flusso seguiva 380..400 punti su 400 (salto 0,00 tasti), al 27 e'
# crollato a 38/96 con la scala dell'omografia a 0,447, al 28 a 2/40 con un salto di 9,4 tasti,
# e li' `affina` ha accettato un'omografia degenere con 17 inlier. Da quel momento il flusso non
# aveva piu' niente da seguire (0/0, 0 inlier): la griglia e' rimasta congelata su quella
# sbagliata per il resto del pezzo e il ritaglio del video preparato e' andato dietro a una
# tastiera che non c'era -- "la tastiera si sposta di 2386,94 tasti" e i riquadri per tasto
# ridotti a un ventaglio (inlier mediano 0 su 1800 fotogrammi: la misura c'era, nessuno la
# leggeva). I tre freni che seguono valgono per questa corsa e per `0_prepara.insegui_griglia`:
#   1. in un fotogramma la tastiera NON salta piu' di `_SALTO_TASTI` tasti (una panoramica a mano
#      libera sta a 0,2 tasti per fotogramma: 1,5 e' gia' un salto che nessuna mano fa);
#   2. il passo non cambia piu' di `_SCARTO_SCALA` in un fotogramma (un'omografia che cambia scala
#      di colpo e' quella che ha agganciato un altro oggetto: qui 0,447 in un fotogramma solo);
#   3. ogni `_OGNI_RIANCORA` fotogrammi -- e ogni `_OGNI_CERCA_PERSO` quando un freno e' scattato
#      -- si cerca il pianoforte DA ZERO (`H_iniziale`, lo stesso ancoraggio del primo
#      fotogramma) e lo si tiene solo se spiega i neri del fotogramma MEGLIO della griglia in
#      mano e ha un passo da tastiera, non da altro. Cosi' una griglia persa si RITROVA, e una
#      griglia buona non si fa spostare da una lettura di ripiego.
_SALTO_TASTI = 1.5         # quanto puo' muoversi la tastiera in un fotogramma (tasti)
_SCARTO_SCALA = 0.12       # quanto puo' cambiare il passo in un fotogramma (frazione)
_OGNI_RIANCORA = 30        # fotogrammi fra due ricerche del pianoforte da zero (1 s a 30 fps)
_OGNI_CERCA_PERSO = 5      # ... e, se un freno e' scattato, ogni 5
_SCARTO_TROVATA = 0.35     # quanto puo' differire il passo di una griglia ritrovata da quello
                           # del primo fotogramma (0,35 esclude ancora l'ottava sopra, che raddoppia)
_MARGINE_MEGLIO = 1.3      # la griglia ritrovata si tiene se spiega il 30% di neri in piu'
_U_CENTRO = 0.5 * (u_bianco(NOTA_MIN) + u_bianco(NOTA_MAX))


def centro_griglia(H):
    """Dove cade nel fotogramma il centro della tastiera, o `None` se l'omografia non regge."""
    p = proietta(H, [(_U_CENTRO, LB / 2.0)])[0]
    return p if np.isfinite(p).all() else None


def passo_griglia(H):
    """Il passo della griglia in pixel (una unita' = un tasto bianco)."""
    return float(np.hypot(H[0, 0], H[1, 0]))


def _stessa_tastiera(Ha, H, tasti, scarto):
    """Vero se `Ha` e' la stessa tastiera di `H`: centro entro `tasti` e passo entro `scarto`."""
    ca, cb = centro_griglia(Ha), centro_griglia(H)
    sa, sb = passo_griglia(Ha), passo_griglia(H)
    if ca is None or cb is None or not (sb > 1e-6) or not np.isfinite(sa):
        return False
    return bool(np.hypot(*(ca - cb)) <= tasti * sb and abs(sa / sb - 1.0) <= scarto)


def insegui(H, prev, g, frame, conta=0, H0=None):
    """Il fotogramma dopo, con i freni (vedi sopra). Ritorna `(H, inlier, note)`.

    `H` e' la griglia del fotogramma prima (coordinate del fotogramma intero), `prev` la sua
    immagine in grigio, `g` quella nuova, `frame` il fotogramma a colori (servono il feltro e
    `H_iniziale`), `conta` quanti fotogrammi sono passati dall'ultima ricerca del pianoforte da
    zero, `H0` la griglia ancorata del primo fotogramma (per non scambiare un'altra tastiera per
    questa). `note` dice cosa e' successo, per il log: `diff` e `flusso`/`seguiti` (la qualita'
    del flusso), `scartata` (un freno e' scattato e la griglia non si e' mossa), `cercato` (si e'
    cercato il pianoforte da zero), `riancorata` (e la griglia e' quella trovata adesso), `inlier`.
    """
    nota = {"diff": 0.0, "flusso": -1, "seguiti": -1, "scartata": False,
            "cercato": False, "riancorata": False, "inlier": 0}
    if prev is None:                              # primo fotogramma: niente da inseguire
        Hp = H
    else:
        diff = float(np.mean(np.abs(prev.astype(np.int16) - g.astype(np.int16))))
        nota["diff"] = diff
        if diff < _SOGLIA_FERMO:                  # immagine identica: la geometria non cambia
            Hp = H
        else:
            Hf, n_in, n_tracc = flusso(prev, g, H)
            nota["flusso"], nota["seguiti"] = n_in, n_tracc
            Hp = Hf @ H
            if not _stessa_tastiera(Hp, H, _SALTO_TASTI, _SCARTO_SCALA):
                Hp, nota["scartata"] = H, True
    H2, k = affina(g, Hp, rosso(frame), 3)
    H_cur = H2 if k >= 10 else Hp
    nota["inlier"] = int(k)
    cercare = (nota["scartata"] and conta >= _OGNI_CERCA_PERSO) or conta >= _OGNI_RIANCORA
    if cercare:
        nota["cercato"] = True
        try:
            Ha = np.asarray(H_iniziale(frame), dtype=float)
        except (RuntimeError, ValueError):
            Ha = None
        if Ha is not None and _stessa_tastiera(Ha, H0 if H0 is not None else H,
                                               3.0, _SCARTO_TROVATA):
            H3, k3 = affina(g, Ha, rosso(frame), 3)
            if k3 >= max(12, _MARGINE_MEGLIO * k):
                H_cur, nota["riancorata"], nota["inlier"] = (H3 if k3 >= 10 else Ha), True, int(k3)
    return H_cur, nota["inlier"], nota


def _disegna(f, H, etichette=True, poligoni=None):
    """Un riquadro per tasto: verdi i bianchi, blu i neri, col nome della nota.

    `poligoni` (opzionale) = `{nota: 4 punti nel fotogramma}`: i riquadri GIA' calcolati (per
    esempio quelli del fotogramma 0 con la x misurata tasto per tasto, trasportati dal moto
    della tastiera). Con `poligoni` la grafica e' identica, ma `H` non serve: e' il modo di
    disegnare la stessa griglia sul fermo-immagine e sul video senza ricalcolarla dal modello.
    """
    def poli(n):
        return np.asarray(poligoni[n] if poligoni is not None else poligono_tasto(H, n),
                          dtype=float)
    o = f.copy()
    # linee sottili quando i tasti sono piccoli: con 9 px a tasto due righe da 2 px si accavallano
    # e i riquadri diventano una macchia. Il passo e' la larghezza media di un bianco in pixel.
    bianchi = [n for n in (poligoni if poligoni is not None else BIANCHI) if not e_nero(n)]
    neri = [n for n in (poligoni if poligoni is not None else NERI) if e_nero(n)]
    _b = (bianchi or BIANCHI)[:20]
    larg = float(np.median([np.linalg.norm(poli(n)[1] - poli(n)[0]) for n in _b]))
    sp = 1 if larg < 16 else 2
    for n in bianchi:
        cv2.polylines(o, [np.int32(np.round(poli(n)))], True, (60, 220, 60), sp, cv2.LINE_AA)
    for n in neri:
        cv2.polylines(o, [np.int32(np.round(poli(n)))], True, (255, 160, 30), sp, cv2.LINE_AA)
    if etichette:
        h, w = f.shape[:2]
        for n in bianchi:
            p = poli(n)
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
    H0, conta = None, 0
    t0 = time.time()
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if H is None:                    # primo fotogramma: si ancora da zero e si tiene da parte
            H = H_iniziale(f, a.nota_gruppo2)
            H0 = H
        # Il fotogramma dopo lo fa `insegui`, con i freni (vedi il commento lungo prima di
        # `insegui`): un flusso che salta -- un braccio, un tablet, gente che passa -- non porta
        # via la griglia, e una griglia persa si ritrova da zero invece di scappare per il resto
        # del pezzo. Un `diff` grande da solo NON vuol dire "cambio di inquadratura": una
        # panoramica a mano libera arriva a 25 di differenza media e il flusso la insegue
        # benissimo (misurato su document_5904406621164936944.mp4: diff 20,1..25,2 sui
        # fotogrammi 282..287 e 300..301, con 118..242 inlier su 154..335 punti seguiti);
        # a dire "inquadratura cambiata" e' il flusso che non regge, e a dirlo adesso e' il
        # freno sulla scala e sul salto, non la differenza fra le immagini.
        H, k, _nota = insegui(H, prev if prev is not None else g, g, f, conta, H0)
        conta = 0 if _nota["cercato"] else conta + 1
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
