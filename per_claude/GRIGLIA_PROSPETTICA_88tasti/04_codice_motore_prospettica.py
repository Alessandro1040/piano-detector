"""
Motore prospettico — griglia dei tasti stimata frame per frame dal modello
`griglia_prospettica.py` (ripresa a mano libera) e decisione premuto/rilasciato
dentro i riquadri per nota (la stessa misura del motore calibrato).

    python3 motore_prospettica.py video.mp4 -o out/ [--nota-gruppo2 61] [--prima-nota 48]
        [--cartella-sagome DIR] [--formato-clip mp4|jpeg] [--senza-clip]
        [--senza-video-griglia] [--json-griglia]

Perche' non servono YOLO ne' mediapipe
-------------------------------------
La tastiera e' un oggetto rigido con una griglia regolare: il modello stima per ogni
frame un'omografia (spazio canonico in larghezze di tasto bianco -> immagine) usando i
tasti neri veri, il fondo dei neri e il feltro rosso, poi la insegue con il flusso
ottico. Da qui si ricavano i riquadri di OGNI tasto in ogni frame, come nel motore
calibrato: nessun modello neurale, solo cv2 + numpy, e la griglia segue i movimenti
della ripresa a mano libera (i riquadri restano sui tasti anche quando la tastiera si
sposta nell'inquadratura).

Uscita (identica al motore calibrato, cosi' lo Studio web la mostra senza casi speciali)
---------------------------------------------------------------------------------------
    out/notes.json          eventi nota + meta + blocco "prospettica"
    out/song.mid            MIDI
    out/prima_griglia.jpg   primo frame con la griglia del modello (blu = tasti neri)
    out/griglia.mp4         tutto il video con la griglia disegnata, in H.264 (controllo visivo
                            frame per frame: si riproduce nel browser). Nei frame in cui il
                            modello segna un tasto come premuto il tasto viene scurito da un
                            velo semitrasparente: l'evento si vede senza perdere lo sfondo
    out/griglia.json        (--json-griglia) poligoni e celle per frame, come il modello
    sagome/sagome.json      riquadri per nota in colonne (riuso con --cartella-sagome)
    sagome/<nota>.mp4       clip della nota (una clip per tasto, per il controllo umano)

Limiti dichiarati
-----------------
* L'ottava dei tasti non e' deducibile dalla sola immagine: il modello la fissa con
  `--nota-gruppo2` (default 61 = C#4, il primo nero del gruppo da due piu' vicino al
  centro). `--prima-nota 50` (D3) corregge l'ottava senza cambiare la geometria.
* Le note non inquadrate nel primo frame non esistono in uscita: non possono comparire
  nel MIDI (stessa regola del motore calibrato).
* Vale il limite 2D del motore calibrato: un dito che sfiora un tasto cambia l'immagine
  come un dito che preme; le soglie vanno tarate sul video reale.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

import griglia_prospettica as G
from motore_calibrato import RilevatoreCalibrato
from sagome import (RiquadroNota, SagomeVideo, ScrittoreVideo, carica_sagome, salva_sagome,
                    scrivi_clip_per_nota)
from to_midi import riepiloga, salva_json, salva_midi

QUOTA_VISIBILE = 0.60      # quota minima del tasto dentro il frame per dire "inquadrato"
LATO_MIN = 6               # lato minimo (px) del riquadro per potervi misurare dentro
_HC = _WC = 100            # spazio canonico di riferimento per la zona di analisi
_VEL_MAX = 20.0            # inlier di `affina` che valgono confidenza 1.0
_SOGLIA_FERMO = 0.05       # differenza media (livelli di grigio) sotto cui il frame e' "fermo"
_SOGLIA_TAGLIO = 38.0      # differenza media (livelli) sopra cui si SOSPETTA un cambio di
                           # inquadratura. Misurato: uno stacco vero fra due riprese sta a 60+,
                           # mentre una mano che passa davanti o una luce che cambia sta a 20-30.
                           # Con la soglia a 20 (valore precedente) un movimento brusco rifaceva la
                           # griglia da zero: 8 falsi tagli in 20 frame sul video verticale di prova.
_SOGLIA_PIXEL = 25.0       # differenza (livelli) sotto cui due pixel sono "lo stesso punto"
_QUOTA_IMPRONTA = 0.72     # quota di punti dell'impronta che deve combaciare per dire "fermo"

# --- guardie sul cambio di inquadratura: un taglio si adotta solo se e' convincente ---------
# Il sospetto da solo non basta: quando la differenza di frame supera `_SOGLIA_TAGLIO` la griglia
# NON viene piu' rifatta subito. Resta "in verifica" finche' non si dimostra che la nuova scena
# e' una tastiera e che e' la stessa per piu' frame di fila:
_CONFERME_TAGLIO = 3       # frame in cui il nuovo anchor deve concordare con se stesso
_TAGLIO_ACCORDO = 0.15     # accordo fra due anchor: scarto max (frazione di larghezza tastiera)
_TAGLIO_TENUE = 0.30       # salto oltre cui il nuovo anchor e' "sospetto" e pretende piu' prove
_TAGLIO_MIN_EVIDENZA = 0.80        # evidenza "ottima" di un nuovo anchor sospetto
_TAGLIO_MARGINE_EVIDENZA = 0.05    # ...oppure un'evidenza non peggiore di cosi' rispetto alla
                                   # griglia in uso: nei video scuri/obliqui la tastiera VERA sta
                                   # a 0.62-0.79 (misurato), quindi il solo 0.80 assoluto
                                   # bloccherebbe anche i tagli veri
_TAGLIO_OSTINATO = 15      # se il candidato regge comunque per tanti frame, lo si adotta: la
                           # scena e' cambiata davvero e attendere oltre non serve
_TAGLIO_ATTESA = 45        # frame di verifica dopo i quali si smette di cercare un nuovo anchor
                           # (la scena non si stabilizza: si continua a tracciare la griglia)
_ATTESA_STAMPA = 15        # ogni quanti frame, mentre si e' in verifica, si stampa il log

_TINTA_PREMUTO = (0.75, 0.60, 0.60)   # BGR: fattori del tasto premuto. Tutti < 1 = il tasto
                                      # si scurisce; il blu cala meno degli altri = resta una
                                      # tinta fredda. Moltiplicare (invece di miscelare verso un
                                      # colore fisso) conserva il contrasto dello sfondo sotto il
                                      # velo e non schiarisce i tasti neri, che restano neri.
_TASTI = set(G.BIANCHI) | set(G.NERI)   # note del modello: i soli tasti che si possono scurire
_FATT_PREMUTO = np.array(_TINTA_PREMUTO, np.float32)


def _scurisci(o: np.ndarray, mask: np.ndarray) -> None:
    """Scurisce i pixel sotto `mask` (in place), lasciando passare lo sfondo attenuato.

    Si lavora solo sul rettangolo che contiene la maschera, cosi' il costo non dipende
    dalla risoluzione del video. `mask` e' antialiasata (cv2.LINE_AA): l'effetto sfuma
    sui bordi del tasto.
    """
    y, x = np.where(mask > 0)
    if not len(y):
        return
    y1, y2, x1, x2 = int(y.min()), int(y.max()) + 1, int(x.min()), int(x.max()) + 1
    regione = o[y1:y2, x1:x2].astype(np.float32)
    m = (mask[y1:y2, x1:x2].astype(np.float32) / 255.0)[..., None]
    fattore = 1.0 - m * (1.0 - _FATT_PREMUTO)          # m=0 -> 1 (intatto); m=1 -> la tinta
    np.clip(regione * fattore, 0, 255, out=regione)
    o[y1:y2, x1:x2] = regione.astype(np.uint8)


# --------------------------------------------------------------- disegno
def disegna(frame: np.ndarray, H: np.ndarray, offset: int = 0, etichette: bool = True,
            premuti: set[int] | None = None) -> np.ndarray:
    """Come `griglia_prospettica._disegna`, con le etichette corrette (+offset semitoni).

    Blù (255,160,30 BGR) = tasti neri, verde = tasti bianchi: gli stessi colori del
    modello, cosi' il video di controllo e' identico a quello di riferimento.

    `premuti` (note in semitoni, come in `notes.json`) sono i tasti che il modello segna
    come premuti *in questo frame*: ognuno viene scurito da un velo semitrasparente, cosi'
    il video di controllo mostra gli stessi eventi del MIDI lasciando vedere lo sfondo.
    """
    o = frame.copy()
    h, w = frame.shape[:2]
    if premuti:
        mask = None
        for n in premuti:
            m = n - offset                              # da semitoni finali al lessico del modello
            if m not in _TASTI:
                continue
            pol = G.poligono_tasto(H, m)
            if not np.isfinite(pol).all():
                continue
            if pol[:, 0].max() < 0 or pol[:, 0].min() > w or pol[:, 1].max() < 0 or pol[:, 1].min() > h:
                continue                                # tasto fuori inquadratura
            if mask is None:
                mask = np.zeros((h, w), np.uint8)
            cv2.fillPoly(mask, [np.int32(pol).reshape(-1, 1, 2)], 255, cv2.LINE_AA)
        if mask is not None:                            # una sola passata per frame, non una per tasto
            _scurisci(o, mask)
    for n, col in ((G.BIANCHI, (60, 220, 60)), (G.NERI, (255, 160, 30))):
        for m in n:
            pol = G.poligono_tasto(H, m)
            if not np.isfinite(pol).all():
                continue
            if pol[:, 0].max() < 0 or pol[:, 0].min() > w or pol[:, 1].max() < 0 or pol[:, 1].min() > h:
                continue                                   # tasto fuori inquadratura
            cv2.polylines(o, [np.int32(pol)], True, col, 2, cv2.LINE_AA)
    if not etichette:
        return o
    for m in G.BIANCHI:
        p = G.poligono_tasto(H, m)
        x, y = (p[2] + p[3]) / 2.0
        if 0 < x < w - 14 and 0 < y < h - 4:
            t = G.nome(m + offset)
            pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
            cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return o


# ------------------------------------------------------------ geometria
def _flusso(prev: np.ndarray, cur: np.ndarray, H_prev: np.ndarray) -> np.ndarray:
    """Come `griglia_prospettica.flusso`, ma senza fidarsi di un flusso degenere.

    Su una scena ferma (telefono appoggiato, video ripetuto, tasti non in movimento) i
    punti tracciati non si spostano: l'omografia stimata su corrispondenze identiche e'
    degenere e cambia da frame a frame, facendo VAGARE la griglia (e quindi riquadri
    diversi sullo stesso pixel) e inventando note. Se il flusso e' degenere si tiene la
    griglia precedente e sara' `affina` a misurarla di nuovo sull'immagine.
    """
    m = G.maschera_tastiera(H_prev, prev.shape)
    p0 = cv2.goodFeaturesToTrack(prev, 400, 0.01, 6, mask=m)
    if p0 is None or len(p0) < 12:
        return np.eye(3)
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None, winSize=(31, 31), maxLevel=4)
    ok = st.ravel() == 1
    if int(ok.sum()) < 12:
        return np.eye(3)
    a, b = p0[ok].reshape(-1, 2), p1[ok].reshape(-1, 2)
    spost = float(np.median(np.linalg.norm(b - a, axis=1)))
    if spost < 0.15:                                  # immagine ferma: flusso inutile
        return np.eye(3)
    Hf, mask = cv2.findHomography(a, b, cv2.RANSAC, 3.0)
    if (Hf is None or not np.isfinite(Hf).all() or int(np.sum(mask)) < 12
            or not np.isfinite(np.linalg.det(Hf[:2, :2]))
            or abs(float(np.linalg.det(Hf[:2, :2])) - 1.0) > 0.5):
        return np.eye(3)                              # omografia schiacciata/assurda
    return Hf


def _dentro(pol: np.ndarray, w: int, h: int) -> tuple[float, tuple[int, int, int, int]]:
    """Quota del poligono dentro il frame e riquadro (x1,y1,x2,y2) della parte visibile."""
    a_pol = float(abs(cv2.contourArea(np.float32(pol))))
    if a_pol < 1.0:
        return 0.0, (0, 0, 0, 0)
    rect = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    a_int, pol_int = cv2.intersectConvexConvex(np.float32(pol), rect)
    if pol_int is None or not np.size(pol_int) or float(a_int) < 1.0:
        return 0.0, (0, 0, 0, 0)
    p = pol_int.reshape(-1, 2)
    box = (int(np.floor(p[:, 0].min())), int(np.floor(p[:, 1].min())),
           int(np.ceil(p[:, 0].max())), int(np.ceil(p[:, 1].max())))
    return min(1.0, float(a_int) / a_pol), box


def _griglia(video, out: Path, *, nota_gruppo2: int = 61, prima_nota: int | None = None,
             max_secondi: float | None = None, json_griglia: bool = False,
             soglia_vis: float = QUOTA_VISIBILE,
             etichette: bool = True) -> tuple[SagomeVideo, np.ndarray, int]:
    """Stima la griglia per ogni frame e la impacchetta come `SagomeVideo`.

    Ritorna (sagome, H del primo frame, scarto d'ottava applicato in semitoni). La griglia
    per frame finisce in `sagome.H_serie`: e' quello che serve a `scrivi_video_griglia`, che
    e' l'unico posto dove si scrive `griglia.mp4` — dopo la decisione, perche' solo allora si
    sa quali tasti scurire frame per frame.
    """
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"impossibile aprire il video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    limite = int(max_secondi * fps) if max_secondi else None
    if limite is not None and n_tot:
        n_tot = min(n_tot, limite)
    H: np.ndarray | None = None
    H0 = np.eye(3, dtype=np.float64)
    H_anc: np.ndarray | None = None                  # griglia del primo frame (ancora)
    impronta: np.ndarray | None = None               # pixel dell'ancora sui punti campione
    punti: list[tuple[float, float]] = []
    neri_mod: list[int] = []
    bianchi_mod: list[int] = []
    prev: np.ndarray | None = None
    base_visibili: list[int] = []                    # note nel lessico del modello
    riq: dict[int, list[RiquadroNota]] = {}
    quad_lista: list[list[tuple[float, float]]] = []
    H_list: list[np.ndarray] = []
    visibili: list[int] = []
    delta, u0, u1, i = 0, -12.0, 12.0, 0
    k_prec, statici, tagli = 0, 0, 0                 # inlier ultimo frame; fermi; cambi scena
    cand: np.ndarray | None = None                   # griglia candidata in attesa di conferma
    cand_conferme, attesa = 0, 0                     # frame concordi sul candidato; frame di verifica
    diff_cand, conferme_taglio = 0.0, 1              # differenza e conferme del taglio da stampare
    while True:
        if limite is not None and i >= limite:
            break
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        fermo = False
        nuovo = H is None
        if not nuovo:
            diff = float(np.mean(np.abs(prev.astype(np.int16) - g.astype(np.int16))))
            fermo = diff < _SOGLIA_FERMO
            nuovo = diff >= _SOGLIA_TAGLIO
            if not nuovo:
                Hp = H if fermo else _flusso(prev, g, H) @ H
        sospetto = nuovo or cand is not None          # cambio di scena: vero o solo presunto
        adottata = False
        if sospetto:                                 # la griglia si rifa' solo dopo verifica
            if nuovo and H is not None:   # in un frame sospetto non c'e' una predizione di flusso
                Hp = H                    # fresca: si riparte dalla griglia precedente
            Hs, k2 = _ancora(f, g, nota_gruppo2)
            if Hs is None:
                if H is None:
                    raise RuntimeError("neri insufficienti sul primo frame: inquadra la tastiera")
                print(f"[prospettica] frame {i}: cambio di scena ma griglia non ritrovata: "
                      f"tengo la precedente", flush=True)
                cand, cand_conferme, attesa = None, 0, 0
            elif H is None:                          # primo frame: non c'e' nessuna storia
                adottata = True
            else:
                # Fix B: la stessa scena deve reggere per piu' frame di fila. Una mano che passa
                # davanti o una luce che cambia danno un anchor diverso a ogni frame (non regge);
                # uno stacco vero invece si rifa' identico frame dopo frame.
                if cand is not None and _distanza_griglie(cand, Hs) <= _TAGLIO_ACCORDO:
                    cand_conferme += 1
                else:
                    cand_conferme, attesa = 1, 0      # ancora instabile: si riparte da zero
                    diff_cand = diff                  # differenza che ha fatto scattare il sospetto
                cand = Hs
                attesa += 1
                if attesa > _TAGLIO_ATTESA:          # la scena non si stabilizza: non e' un taglio
                    print(f"[prospettica] frame {i}: la scena non si stabilizza ({attesa} frame): "
                          f"smetto di cercare un nuovo anchor, continuo a tracciare la griglia",
                          flush=True)
                    cand, cand_conferme, attesa = None, 0, 0
                elif cand_conferme >= _CONFERME_TAGLIO:
                    # Fix C: il salto e' credibile solo se la scena nuova "spiega" i tasti almeno
                    # quanto quella in uso. Se il candidato insiste per `_TAGLIO_OSTINATO` frame
                    # si adotta comunque: la scena e' cambiata davvero.
                    seg_c = _visibili_di(Hs, w, h, soglia_vis)
                    ev_new = _evidenza(g, Hs, [n for n in seg_c if G.e_nero(n)],
                                       [n for n in seg_c if not G.e_nero(n)], G._soglia(g))
                    ev_old = (_evidenza(g, H, neri_mod, bianchi_mod, G._soglia(g))
                              if neri_mod or bianchi_mod else 0.0)
                    salto = _distanza_griglie(H, Hs)
                    if (salto > _TAGLIO_TENUE and cand_conferme < _TAGLIO_OSTINATO
                            and ev_new < _TAGLIO_MIN_EVIDENZA
                            and ev_new < ev_old - _TAGLIO_MARGINE_EVIDENZA):
                        if attesa <= 3 or attesa % _ATTESA_STAMPA == 0:
                            print(f"[prospettica] frame {i}: salto {salto:.2f} larghezze "
                                  f"tastiera, evidenza {ev_new:.2f} contro {ev_old:.2f} della "
                                  f"griglia in uso: anchor sospetto, tengo la precedente "
                                  f"({cand_conferme} conferme)", flush=True)
                    else:
                        adottata = True
                elif attesa <= 3 or attesa % _ATTESA_STAMPA == 0:
                    print(f"[prospettica] frame {i}: nuovo anchor in verifica "
                          f"({cand_conferme}/{_CONFERME_TAGLIO} conferme, salto "
                          f"{_distanza_griglie(H, Hs):.2f} larghezze tastiera): tengo la griglia "
                          f"precedente", flush=True)
            if adottata:
                H = Hp = np.float64(Hs)
                k = k2
                conferme_taglio = cand_conferme
                cand, cand_conferme, attesa = None, 0, 0
                seg = _visibili_di(H, w, h, soglia_vis)
                if len(seg) < 4:
                    raise RuntimeError(f"solo {len(seg)} tasti inquadrati: inquadra meglio "
                                       f"la tastiera")
                neri_mod = [n for n in seg if G.e_nero(n)]
                bianchi_mod = [n for n in seg if not G.e_nero(n)]
                if not base_visibili:            # primo segmento del video
                    H0 = H
                    base_visibili = seg
                    if prima_nota is not None:
                        delta = _delta_ottava(base_visibili, prima_nota)
                    visibili = sorted(n + delta for n in base_visibili)
                    riq = {n: [] for n in visibili}
                    ub = [G.u_bianco(n) for n in bianchi_mod]
                    u0, u1 = (min(ub) - 0.1, max(ub) + 1.1) if ub else (-12.0, 12.0)
                    print(f"[prospettica] primo frame: {len(base_visibili)} tasti inquadrati, "
                          f"note {min(visibili)}..{max(visibili)}"
                          + (f", ottave {delta // 12:+d}" if delta else ""), flush=True)
                else:                            # taglio: la griglia riparte da zero
                    tagli += 1
                    nuovi = [n for n in seg if (n + delta) not in riq]
                    for n in nuovi:              # riquadri vuoti per i frame gia' passati
                        nv = n + delta
                        riq[nv] = [RiquadroNota(nota=nv, nome=G.nome(nv), nero=G.e_nero(n),
                                                frame=j, t=round(j / fps, 6), x1=0, y1=0,
                                                x2=0, y2=0, visibile=False, confidenza=0.0)
                                   for j in range(i)]
                    base_visibili += nuovi
                    visibili = sorted(riq)
                    print(f"[prospettica] frame {i}: cambio di inquadratura confermato "
                          f"({diff_cand:.0f} livelli, {conferme_taglio} frame concordi): "
                          f"griglia rifatta, {len(seg)} tasti inquadrati "
                          f"({len(nuovi)} nuovi)", flush=True)
                punti = _punti_impronta(neri_mod, bianchi_mod)
                H_anc = H.copy()                 # ancora del segmento
                impronta = _campiona(g, H_anc, punti)
                k_prec = k
        if not adottata:                         # nessun cambio di scena: si traccia come sempre
            if fermo:                            # immagine identica: la geometria non cambia
                k = k_prec
                H = Hp
            elif (impronta is not None
                  and _stessa_scena(g, impronta, H_anc, punti, _QUOTA_IMPRONTA)):
                k = k_prec                       # tastiera ferma: vale la griglia del segmento
                H = H_anc
                statici += 1
            else:
                H2, k = G.affina(g, Hp, G.rosso(f), 3)
                if H2 is not None and k >= 10:
                    H = np.float64(H2)
                else:
                    H = Hp
                k_prec = k
        prev = g
        conf = round(float(min(1.0, max(0.0, k / _VEL_MAX))), 3)
        for n_model in base_visibili:
            quota, box = _dentro(G.poligono_tasto(H, n_model), w, h)
            n = n_model + delta
            riq[n].append(RiquadroNota(
                nota=n, nome=G.nome(n), nero=G.e_nero(n_model), frame=i, t=round(i / fps, 6),
                x1=box[0], y1=box[1], x2=box[2], y2=box[3],
                visibile=bool(quota >= soglia_vis and (box[2] - box[0]) >= LATO_MIN
                              and (box[3] - box[1]) >= LATO_MIN),
                confidenza=conf))
        q4 = G.proietta(H, [(u0, 0), (u1, 0), (u1, G.LW), (u0, G.LW)])
        quad_lista.append([(float(x), float(y)) for x, y in q4])
        H_list.append(H.copy())
        if i == 0:                                   # anteprima: il video completo si scrive dopo
            cv2.imwrite(str(out / "prima_griglia.jpg"), disegna(f, H, delta, etichette))
        if i % 30 == 0:
            print(f"[prospettica] frame {i}: inlier {k}, tasti inquadrati "
                  f"{sum(1 for n in riq if riq[n][-1].visibile)}, "
                  f"evidenza {_evidenza(g, H, neri_mod, bianchi_mod, G._soglia(g)):.2f}, "
                  f"tastiera ferma {'si' if statici and H is H_anc else 'no'}", flush=True)
        i += 1
    cap.release()
    if statici:
        print(f"[prospettica] {statici} frame con la tastiera identica all'ancora del segmento: "
              f"usata quella (niente deriva)", flush=True)
    if tagli:
        print(f"[prospettica] {tagli} cambi di inquadratura confermati: la griglia e' stata rifatta "
              f"da zero",
              flush=True)
    if i == 0 or not riq:
        raise RuntimeError("nessun frame utilizzabile nel video")
    if json_griglia:
        doc_g: list[dict] = []
        for j, Hj in enumerate(H_list):
            tasti = {}
            for n_model in base_visibili:
                n = n_model + delta
                tasti[str(n)] = {"nome": G.nome(n), "nero": G.e_nero(n_model),
                                 "poligono": np.round(G.poligono_tasto(Hj, n_model), 1).tolist(),
                                 "celle_profondita": [np.round(c, 1).tolist()
                                                      for c in G._celle(Hj, n_model, 3)]}
            doc_g.append({"frame": j, "t": round(j / fps, 4), "tasti": tasti})
        (out / "griglia.json").write_text(json.dumps(
            {"video": Path(str(video)).name, "fps": round(fps, 6), "n_frame": i,
             "modello": {"LB": G.LB, "LW": G.LW, "BW": G.BW,
                         "offset_ottave": delta // 12, "nota_gruppo2": nota_gruppo2},
             "frames": doc_g}, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    ub = [G.u_bianco(n) for n in base_visibili if not G.e_nero(n)] or [-12.0, 12.0]
    g_can = {"wc": _WC, "hc": _HC, "banda_neri": [0, int(round(_HC * G.LB / G.LW))],
             "span_tastiera": [float(min(ub)), float(max(ub) + 1)]}
    ottava = {"scelta": min(visibili), "ambigua": False, "ipotesi_usata": None, "candidate": [],
              "scarto_ottave": delta // 12, "nota_gruppo2": nota_gruppo2,
              "prova": {"geometria_canonica": g_can}}
    s = SagomeVideo(video=Path(str(video)).name, fps=fps, n_frame=i, quad=quad_lista,
                    riquadri=riq, visibili=visibili, ottava=ottava, H_serie=H_list)
    return s, H0, delta


# ------------------------------------------------- video con i tasti premuti
def _serie_premuti(eventi, n_frame: int) -> list[set[int]]:
    """Per ogni frame, le note (semitoni come in `notes.json`) che un evento copre.

    Un evento vale dal frame di attacco all'ultimo frame premuto: sono esattamente i frame
    in cui il modello dice "premuto", cioe' gli stessi che finiscono nel MIDI.
    """
    serie: list[set[int]] = [set() for _ in range(n_frame)]
    for e in eventi:
        for i in range(max(0, e.frame_onset), min(n_frame, e.frame_offset + 1)):
            serie[i].add(e.nota)
    return serie


def scrivi_video_griglia(video, out: Path, sagome: SagomeVideo, eventi, *, delta: int = 0,
                         etichette: bool = True) -> Path | None:
    """(Ri)scrive `out/griglia.mp4`: la griglia su tutto il video e i tasti premuti scuriti.

    Va chiamata *dopo* la decisione (gli eventi esistono solo allora) e rilegge il video una
    volta. Senza `sagome.H_serie` — cioe' quando la griglia e' riusata da `sagome.json` — non
    c'e' modo di ridisegnarla: si avvisa e non si scrive nulla.
    """
    if not sagome.H_serie:
        print("[prospettica] griglia.mp4 non riscritto: la griglia e' stata riusata da "
              "sagome.json, manca l'omografia per frame", flush=True)
        return None
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"impossibile aprire il video: {video}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    n = min(int(sagome.n_frame), len(sagome.H_serie))
    serie = _serie_premuti(eventi, n)
    vw = ScrittoreVideo(out / "griglia.mp4", w, h, fps)
    i = 0
    while i < n:
        ok, f = cap.read()
        if not ok:
            break
        vw.scrivi(disegna(f, sagome.H_serie[i], delta, etichette, serie[i]))
        i += 1
    cap.release()
    vw.chiudi()
    print(f"[prospettica] video di controllo: {out / 'griglia.mp4'} ({i} frame, "
          f"tasti premuti in evidenza)", flush=True)
    return out / "griglia.mp4"


def _evidenza(g: np.ndarray, H: np.ndarray, neri: list[int], bianchi: list[int],
              T: float) -> float:
    """Quanto la griglia (H) spiega l'immagine: tasti neri scuri, bianchi chiari.

    Non usa le corrispondenze interne del modello: campiona punti fissi dello spazio
    canonico (centro dei neri, fascia frontale dei bianchi) e guarda cosa c'e' sotto.
    Serve a distinguere una griglia giusta da una derivata/tiltata, che il conteggio
    degli inlier di RANSAC non vede (le misure sono fatte *attorno* alla predizione).
    """
    h, w = g.shape
    quote = ((neri, (0.8, 1.4, 2.0, 2.6, 3.2)), (bianchi, (G.LB + 0.35, G.LW - 0.35)))
    pezzi: list[float] = []
    for note, vs in quote:
        pts = [(G.u_nero(n) if (n % 12) in G._NERI_PC else G.u_bianco(n) + 0.5, v)
               for n in note for v in vs]
        if not pts:
            continue
        p = G.proietta(H, pts)
        dentro = (np.isfinite(p).all(axis=1) & (p[:, 0] >= 1) & (p[:, 0] < w - 1)
                  & (p[:, 1] >= 1) & (p[:, 1] < h - 1))
        if not dentro.any():
            continue
        p = p[dentro]
        pezzi.append(float((g[p[:, 1].astype(int), p[:, 0].astype(int)] < T).mean()))
    return float(np.mean(pezzi)) if pezzi else 0.0


def _punti_impronta(neri: list[int], bianchi: list[int]) -> list[tuple[float, float]]:
    """Punti canonici (centro dei neri, fascia frontale dei bianchi) per l'impronta."""
    pts: list[tuple[float, float]] = []
    for n in neri:
        pts += [(G.u_nero(n), v) for v in (0.9, 1.6, 2.3, 3.0)]
    for n in bianchi:
        pts += [(G.u_bianco(n) + 0.5, v) for v in (G.LB + 0.5, G.LB + 1.1, G.LW - 0.25)]
    return pts


def _campiona(g: np.ndarray, H: np.ndarray, pts: list[tuple[float, float]],
              fuori: float = -1.0) -> np.ndarray:
    """Valori di grigio nei punti (canonico) proiettati; -1 dove non c'e' immagine."""
    h, w = g.shape
    p = G.proietta(H, pts)
    out = np.full(len(pts), fuori, dtype=np.float32)
    if not np.isfinite(p).all():
        p = np.nan_to_num(p, nan=-10.0, posinf=-10.0, neginf=-10.0)
    dentro = (p[:, 0] >= 1) & (p[:, 0] < w - 1) & (p[:, 1] >= 1) & (p[:, 1] < h - 1)
    if dentro.any():
        q = p[dentro]
        out[dentro] = g[q[:, 1].astype(int), q[:, 0].astype(int)]
    return out


def _stessa_scena(g: np.ndarray, impronta: np.ndarray, H: np.ndarray,
                  punti: list[tuple[float, float]], soglia: float) -> bool:
    """La tastiera e' la stessa dell'ancora? (camera ferma: stessi pixel, stessi punti).

    Se i pixel sotto i punti dell'ancora sono quelli del primo frame, la geometria della
    tastiera NON e' cambiata: usare la griglia del primo frame e' corretto, e anzi evita
    che le misure frame-per-frame del modello facciano derivare la griglia (mani che
    coprono i tasti, RANSAC, flusso ottico degenere).
    """
    cur = _campiona(g, H, punti)
    ok = (cur >= 0) & (impronta >= 0)
    if int(ok.sum()) < 20:
        return False
    return float((np.abs(cur[ok] - impronta[ok]) < _SOGLIA_PIXEL).mean()) >= soglia


def _distanza_griglie(Ha: np.ndarray, Hb: np.ndarray) -> float:
    """Distanza fra due griglie, in frazione di larghezza di tastiera (0 = identiche).

    Proietta lo stesso ventaglio di punti canonici con le due omografie e prende la distanza
    MEDIANA fra le due proiezioni; la normalizza con l'ampiezza inquadrata di due ottave, cosi'
    il numero non dipende ne' dalla risoluzione ne' dalla distanza della tastiera. Serve a dire
    se due griglie descrivono la STESSA tastiera (accordo: sono l'una la continuazione
    dell'altra) oppure due tastiere diverse (una delle due e' un falso allarme).

    Si usa la proiezione, non i pixel: due griglie possono essere la stessa tastiera anche se
    il frame nel frattempo si e' mosso, mentre due falsi allarmi consecutivi (la "tastiera"
    trovata su una mano, su un'ombra) cadono in punti diversi dell'immagine.
    """
    pts = [(float(u), float(v)) for u in (-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0)
           for v in (0.5, G.LW / 2.0, G.LW - 0.5)]
    pa, pb = G.proietta(Ha, pts), G.proietta(Hb, pts)
    if not (np.isfinite(pa).all() and np.isfinite(pb).all()):
        return float("inf")
    amp = [float(np.linalg.norm(G.proietta(Hx, [(6.0, G.LW / 2.0)])[0]
                               - G.proietta(Hx, [(-6.0, G.LW / 2.0)])[0]))
           for Hx in (Ha, Hb)]
    if min(amp) < 1.0:                            # griglia degenere: nessun confronto possibile
        return float("inf")
    return float(np.median(np.linalg.norm(pa - pb, axis=1)) / (0.5 * sum(amp)))


def _ancora(f: np.ndarray, g: np.ndarray,
            nota_gruppo2: int) -> tuple[np.ndarray | None, int]:
    """Griglia assoluta del frame corrente (dall'immagine, senza storia): (H, inlier)."""
    try:
        H = np.float64(G.H_iniziale(f, nota_gruppo2))
    except (RuntimeError, ValueError):
        return None, 0
    H2, k = G.affina(g, H, G.rosso(f), 3)
    if H2 is not None and k >= 10:
        return np.float64(H2), int(k)
    return H, int(k)


def _visibili_di(H: np.ndarray, w: int, h: int, soglia: float) -> list[int]:
    """Note del modello che la griglia H mette (quasi) dentro il frame."""
    fuori = []
    for n in G.BIANCHI + G.NERI:
        quota, box = _dentro(G.poligono_tasto(H, n), w, h)
        if (quota >= soglia and (box[2] - box[0]) >= LATO_MIN and (box[3] - box[1]) >= LATO_MIN):
            fuori.append(n)
    return fuori


def _delta_ottava(visibili: list[int], prima_nota: int) -> int:
    """Scarto d'ottava (multiplo di 12) fra le etichette del modello e `prima_nota`.

    `prima_nota` = MIDI del tasto piu' a sinistra fra quelli inquadrati. Si confronta col
    tasto piu' a sinistra DELLO STESSO NOME che il modello vede: due tasti omonimi
    differiscono per un multiplo di 12, quindi la differenza dice di quante ottave il
    modello sbaglia (la geometria non cambia: cambiano solo le etichette).
    """
    stesso_nome = [n for n in visibili if (n - prima_nota) % 12 == 0]
    if stesso_nome:
        m = min(stesso_nome)                      # il piu' a sinistra con lo stesso nome
    else:
        m = min(visibili, key=lambda n: (abs((n - prima_nota + 6) % 12 - 6), n))
        print(f"[prospettica] avviso: nel video non si vede nessun {G.nome(prima_nota)}: "
              f"uso {G.nome(m)} come riferimento", flush=True)
    d = 12 * int(round((prima_nota - m) / 12.0))
    print(f"[prospettica] 'prima nota' {prima_nota} ({G.nome(prima_nota)}) contro "
          f"{m} ({G.nome(m)}) del modello: scarto d'ottava {d // 12:+d}", flush=True)
    return d


# -------------------------------------------------------------- rilevatore
class RilevatoreProspettico(RilevatoreCalibrato):
    """Premuto/rilasciato dentro i riquadri della griglia prospettica.

    Riusa la misura del motore calibrato (patch 6x10 della zona del tasto, mediana
    temporale come riposo, contrasto locale fra tasti vicini, isteresi): cambia solo la
    provenienza dei riquadri (qui il modello prospettico invece di `sagome`).
    """

    def __init__(self, sagome: SagomeVideo, H0: np.ndarray, *, delta: int = 0,
                 soglia_giu: float = 0.6, soglia_su: float = 0.4, finestra: int = 5) -> None:
        super().__init__(sagome, soglia_giu=soglia_giu, soglia_su=soglia_su, finestra=finestra)
        self.H0 = np.float64(H0)
        self.delta = int(delta)

    def _disegna(self, frame: np.ndarray) -> np.ndarray:
        o = disegna(frame, self.H0, self.delta)
        v = self.sagome.visibili
        txt = f"prospettica: {len(v)} note inquadrate ({min(v)}..{max(v)})"
        if self.delta:
            txt += f" · ottave {self.delta // 12:+d}"
        cv2.putText(o, txt, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(o, txt, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 235, 0), 1, cv2.LINE_AA)
        return o

    def analizza(self, video, out_dir, *, max_secondi=None, sagome_dir=None,
                 formato_clip: str = "mp4", scrivi_clip: bool = True,
                 video_griglia: bool = True) -> dict:
        r = super().analizza(video, out_dir, max_secondi=max_secondi, sagome_dir=sagome_dir,
                             formato_clip=formato_clip, scrivi_clip=scrivi_clip)
        p = Path(out_dir) / "notes.json"                    # rietichetta: e' un'altra griglia
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["motore"] = "prospettica"
        if "calibrato" in doc:
            doc["prospettica"] = doc.pop("calibrato")
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if video_griglia:            # ora si sa quali tasti scurire e in quali frame
            scrivi_video_griglia(video, Path(out_dir), self.sagome, self._eventi, delta=self.delta)
        return r


# ---------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Motore prospettico: griglia dei tasti per frame -> MIDI.")
    p.add_argument("video")
    p.add_argument("-o", "--output", default="out")
    p.add_argument("--nota-gruppo2", type=int, default=61,
                   help="nota del primo nero del gruppo da 2 neri piu' vicino al centro (61 = C#4)")
    p.add_argument("--prima-nota", type=int, default=None,
                   help="MIDI della prima nota visibile a sinistra: corregge l'ottava")
    p.add_argument("--soglia-giu", type=float, default=0.6)
    p.add_argument("--soglia-su", type=float, default=0.4)
    p.add_argument("--finestra", type=int, default=5)
    p.add_argument("--max-secondi", type=float, default=None)
    p.add_argument("--cartella-sagome", default=None,
                   help="dove scrivere/leggere sagome.json: se esiste, la griglia viene riusata")
    p.add_argument("--sagome-json", default=None, help="griglia gia' calcolata da usare")
    p.add_argument("--formato-clip", choices=("mp4", "jpeg"), default="mp4")
    p.add_argument("--senza-clip", action="store_true")
    p.add_argument("--senza-video-griglia", action="store_true",
                   help="non scrivere griglia.mp4 (niente video con i tasti premuti in evidenza)")
    p.add_argument("--json-griglia", action="store_true",
                   help="scrive anche griglia.json (poligoni e celle per frame)")
    a = p.parse_args(argv)
    t0 = time.time()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    try:
        cap = cv2.VideoCapture(a.video)
        if not cap.isOpened():
            print(f"[ERRORE] impossibile aprire il video: {a.video}", file=sys.stderr)
            return 2
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        W, Hh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        print(f"[video] {a.video}: {W}x{Hh}, {fps:.3f} fps, {n} frame, passo=1")
        cache = (Path(a.sagome_json) if a.sagome_json
                 else Path(a.cartella_sagome or a.output) / "sagome.json")
        if cache.is_file():
            print(f"[prospettica] riuso la griglia gia' calcolata: {cache}")
            s = carica_sagome(cache)
            c2 = cv2.VideoCapture(a.video)
            ok, f0 = c2.read()
            c2.release()
            if not ok:
                raise RuntimeError("video illeggibile: non posso ricalcolare la griglia")
            H0 = np.float64(G.H_iniziale(f0, a.nota_gruppo2))
            delta = 12 * int(s.ottava.get("scarto_ottave") or 0)
        else:
            print(f"[prospettica] fase 1: griglia dei tasti frame per frame "
                  f"(nota_gruppo2={a.nota_gruppo2})")
            s, H0, delta = _griglia(a.video, out, nota_gruppo2=a.nota_gruppo2,
                                    prima_nota=a.prima_nota, max_secondi=a.max_secondi,
                                    json_griglia=a.json_griglia)
            salva_sagome(s, cache)
        v = s.visibili
        print(f"[griglia] estensione {min(v)}..{max(v)} ({len(v)} note inquadrate) - ottava dal "
              f"modello, scarto {delta // 12:+d} ottave")
        print("[prospettica] fasi 2-5: decisione, clip, uscita")
        r = RilevatoreProspettico(s, H0, delta=delta, soglia_giu=a.soglia_giu,
                                  soglia_su=a.soglia_su, finestra=a.finestra).analizza(
            a.video, a.output, sagome_dir=a.cartella_sagome, formato_clip=a.formato_clip,
            scrivi_clip=not a.senza_clip, video_griglia=not a.senza_video_griglia)
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"[ERRORE] {e}", file=sys.stderr)
        return 2
    print("\n=== RIEPILOGO ===")
    print(f"frame                 : {r['n_frame']}")
    print(f"note inquadrate       : {len(r['visibili'])}  emesse {len(r['emesse'])}")
    print(f"eventi nota           : {r['n_eventi']} (note uniche {r['riepilogo']['note_uniche']})")
    print(f"clip scritte          : {r['n_clip']}")
    print(f"tempo                 : {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
