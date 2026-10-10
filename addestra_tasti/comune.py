"""Pezzi condivisi: patch dei tasti, distanza dalle mani, etichette MIDI, rete, aumento dei dati.

Tre cose importanti stanno qui:

* **la patch di un tasto** (`patch`/`stack`) e' la stessa per dataset, addestramento e
  inferenza: se cambia una cosa qui, i vecchi .pt non vanno piu' bene;
* **l'aumento dei dati** (`augmenta`) simula l'errore vero della griglia prospettica
  (10-20 px, anisotropo) e le differenze fra una ripresa e l'altra (luce, colore,
  sfocatura, rumore, occlusione): e' quello che permette alla rete di funzionare su
  video mai visti;
* **la decodifica** (`decodifica`) trasforma le probabilita' per tasto in note, con
  isteresi e durata minima: senza di questa il «F1» resta un numero sui frame e non dice
  niente su quante note sono state riconosciute davvero.
"""
import json
import math
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

PW, PH = 24, 56          # dimensione patch (larghezza, altezza) di ogni tasto
MARG, EXT = 0.6, 0.25    # contesto laterale (in larghezze di tasto) e prolungamento verso il fronte
LAG = 3                  # la rete vede il frame t e il frame t-LAG

MANI_ASSENTI = 1.5       # distanza finta quando le mani non si vedono in quel frame
SOGLIA_ON, SOGLIA_OFF = 0.5, 0.35    # isteresi di default nella decodifica probabilita' -> note
MIN_FRAME = 2            # durata minima (in frame) di una nota riconosciuta
TOL_ON = 0.05            # tolleranza (s) nell'accoppiare due onset a livello di nota

def carica_griglia(p):
    return json.load(open(p, encoding="utf-8"))


def stima_raggio(distanze, default=2.5, perc=90.0, massimo=12.0):
    """Il raggio da usare quando non lo si sceglie a mano.

    Il raggio decide, a addestramento E a inferenza, entro quante larghezze di tasto dal
    polpastrello si guarda: i tasti piu' lontani non vengono mai giudicati (probabilita' NaN).
    Misurato sui video veri, 2.5 butta via oltre la meta' dei tasti premuti (la distanza mediana
    e' ~4 larghezze), quindi qui si prende il percentile delle distanze dei tasti PREMUTI con le
    dita visibili: cosi' il modello vede quasi tutti i premuti e a inferenza li guarda.

    Ritorna (raggio, avviso): avviso e' None quando la misura e' pulita, altrimenti il testo da
    stampare per dire perche' si e' ripiegati su un valore di default.
    """
    d = np.asarray([float(x) for x in distanze if np.isfinite(x)], np.float64)
    if len(d) < 30:
        return float(default), (f"tasti premuti con le dita visibili troppo pochi ({len(d)}) per "
                                f"misurare il raggio: uso {default}")
    r = float(np.percentile(d, perc))
    if r > massimo:
        return float(massimo), (f"il {perc:.0f}% dei tasti premuti sta entro {r:.1f} larghezze di tasto "
                                f"dal polpastrello: e' troppo (griglia o mani.json sospetti). Uso "
                                f"{massimo}; se la misura e' giusta passa --raggio {round(r, 1)}")
    return max(round(r, 1), 0.5), None


def controlla_video(video, gr, forza=False):
    """Blocca l'errore piu' facile e piu' rovinoso: griglia di un video + video di un altro.

    La griglia sa da quale video e' stata misurata (`gr["video"]`) e quanti frame copre
    (`gr["n_frame"]`). Se il video e' un altro, i poligoni dei tasti cadono nel vuoto e si
    finisce per etichettare "premuto" su tasti che non c'entrano: il dataset e' spazzatura e
    ce ne si accorge solo dopo aver addestrato. Meglio fermarsi subito (o --forza, se si sa
    quello che si sta facendo).
    """
    atteso, dato = Path(str(gr.get("video", ""))).name, Path(str(video)).name
    cap = cv2.VideoCapture(str(video))
    quanti = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
    if atteso and atteso != dato and not forza:
        raise SystemExit(
            f"la griglia e' stata misurata su «{atteso}» ma il video e' «{dato}»: tasti e note "
            f"sarebbero di un altro video (dataset sbagliato in silenzio).\n"
            f"  - usa la griglia di QUESTO video (il nome giusto e' scritto dentro griglia.json),\n"
            f"  - oppure aggiungi --forza se sai che la geometria combacia davvero.")
    if quanti and quanti < int(gr["n_frame"]):
        raise SystemExit(f"la griglia copre {gr['n_frame']} frame ma «{dato}» ne ha {quanti}: "
                         f"manca la parte finale del video (o e' un altro video).")
    if quanti and quanti > int(gr["n_frame"]) + 2:
        print(f"[i] la griglia copre {gr['n_frame']} dei {quanti} frame di «{dato}»: gli ultimi "
              f"{quanti - gr['n_frame']} restano fuori (se sono suonati, rifai la griglia sul video intero)")
    return int(gr["n_frame"])

def patch(frame, poly, m=MARG, ext=EXT):
    tl, tr, br, bl = np.float32(poly)
    at, ab = tr - tl, br - bl
    tl, tr, bl, br = tl - m * at, tr + m * at, bl - m * ab, br + m * ab
    bl = bl + ext * (bl - tl); br = br + ext * (br - tr)
    M = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]),
                                    np.float32([[0, 0], [PW, 0], [PW, PH], [0, PH]]))
    return cv2.warpPerspective(frame, M, (PW, PH), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)

def stack(cur, prev, poly):
    return np.concatenate([patch(cur, poly), patch(prev, poly)], 2).transpose(2, 0, 1)

def dist_mani(tasto, BW, punti):
    """Distanza (in larghezze di tasto bianco) fra il centro del tasto e il polpastrello piu' vicino."""
    if not punti: return 1e9
    P = np.float32(tasto["poligono"]); c = P.mean(0)
    w = (np.linalg.norm(P[1] - P[0]) + np.linalg.norm(P[2] - P[3])) / 2 / (BW if tasto["nero"] else 1.0)
    d = np.linalg.norm(np.float32(punti) - c, axis=1).min()
    return float(d / max(w, 1e-3))

def carica_mani(p, n):
    if not p: return [[] for _ in range(n)]
    f = json.load(open(p))["frames"]
    return (f + [[]] * n)[:n]

def note_midi(path):
    import mido
    t, aperte, ev = 0.0, {}, []
    for msg in mido.MidiFile(path):
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            aperte.setdefault(msg.note, t)
        elif msg.type in ("note_off", "note_on") and msg.note in aperte:
            ev.append((msg.note, aperte.pop(msg.note), t))
    ev += [(n, t0, t) for n, t0 in aperte.items()]
    return ev

def etichette(ev, fps, n, ritardo=0.0):
    y = np.zeros((n, 128), bool)
    for nota, t0, t1 in ev:
        a = int(np.ceil((t0 + ritardo) * fps)); b = int(np.ceil((t1 + ritardo) * fps))
        y[max(a, 0):max(b, 0), nota] = True
    return y

def frames(video):
    cap = cv2.VideoCapture(str(video)); fps = cap.get(cv2.CAP_PROP_FPS)
    def gen():
        while True:
            ok, f = cap.read()
            if not ok: return
            yield f
    return fps, gen()


def disegna_allineamento(video, gr, Y, fps, n, rit, cartella, quanti=6):
    """Alcune immagini di controllo: i tasti che il MIDI (col ritardo applicato) dice premuti,
    disegnati in rosso sui frame veri del video.

    E' il controllo a occhio dell'allineamento MIDI-video PRIMA di addestrare: se i tasti rossi
    non stanno sotto le dita nell'immagine, il ritardo e' sbagliato (e la rete imparerebbe note
    spostate). Le immagini sono pochi JPEG, si guardano nel sito o con un doppio clic.
    """
    cartella.mkdir(parents=True, exist_ok=True)
    con_tasti = [j for j in range(min(n, len(gr["frames"]))) if gr["frames"][j]["tasti"]]
    if not con_tasti:
        return []
    quanti = max(1, min(int(quanti), len(con_tasti)))
    scelti = sorted({int(con_tasti[i]) for i in
                     np.linspace(0, len(con_tasti) - 1, quanti).round().astype(int)})
    ultimo, fatti = scelti[-1], []
    for j, f in enumerate(frames(video)[1]):
        if j not in scelti:
            continue
        img, sopra, premuti = f.copy(), None, 0
        for k, t in gr["frames"][j]["tasti"].items():
            if not Y[j, int(k)]:
                continue
            premuti += 1
            pol = np.int32(t["poligono"]).reshape(-1, 1, 2)
            if sopra is None:
                sopra = f.copy()
            cv2.fillPoly(sopra, [pol], (0, 0, 255), cv2.LINE_AA)      # rosso = il MIDI lo dice premuto
            cv2.polylines(img, [pol], True, (255, 255, 255), 1, cv2.LINE_AA)
        if sopra is not None:
            img = cv2.addWeighted(sopra, 0.45, img, 0.55, 0)
        cv2.rectangle(img, (0, 0), (img.shape[1], 28), (0, 0, 0), -1)
        cv2.putText(img, f"frame {j}  t {j / fps:.2f}s  ritardo MIDI {rit:+.2f}s  "
                         f"tasti premuti secondo il MIDI: {premuti}",
                    (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        nome = cartella / f"{Path(video).stem}_f{j:05d}.jpg"
        cv2.imwrite(str(nome), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        fatti.append(nome)
        if j >= ultimo:
            break
    return fatti


def extra_campione(nero, dist, raggio, mani_viste):
    """I numeri che accompagnano la patch: [nero, distanza normalizzata, «ci sono le mani»].

    Prima c'era solo la distanza e valeva 0 sia per «nessuna mano rilevata» sia per «dito
    sul tasto»: la rete non poteva distinguere «non so» da «premuto». Qui i due casi sono
    separati: senza mani la distanza vale `MANI_ASSENTI` e il terzo numero e' 0.
    """
    if mani_viste:
        return np.array([float(nero), min(float(dist) / max(float(raggio), 1e-6), MANI_ASSENTI), 1.0], np.float32)
    return np.array([float(nero), MANI_ASSENTI, 0.0], np.float32)

class ReteVecchia(nn.Module):
    """L'architettura di prima: serve solo a far girare i modello.pt gia' addestrati."""
    versione = 1
    def __init__(s, canali=6, extra=2):
        super().__init__()
        s.canali, s.extra = canali, extra
        def blk(i, o): return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.MaxPool2d(2))
        s.conv = nn.Sequential(blk(canali, 32), blk(32, 64), blk(64, 96))
        s.fc = nn.Sequential(nn.Linear(96 * (PH // 8) * (PW // 8) + extra, 128), nn.ReLU(), nn.Dropout(0.3),
                             nn.Linear(128, 1))
    def forward(s, x, extra):          # x: (B,6,PH,PW) in [0,1]; extra: (B,2) = [nero, distanza/raggio]
        h = s.conv(x - 0.5).flatten(1)
        return s.fc(torch.cat([h, extra], 1)).squeeze(1)


class Rete(nn.Module):
    """CNN sui ritagli dei tasti — versione 2.

    Vede una patch per tasto (6 numeri per pixel: il frame attuale e quello di LAG frame
    prima, in BGR) e 3 numeri per campione: tasto nero, distanza dalle dita, «le dita ci
    sono». Con `movimento=True` si costruisce da sola due canali in piu' con il movimento
    (differenza fra i due frame): e' il segnale piu' diretto per l'attacco di una nota, e non
    cambia niente nel formato dei dataset (che restano a 6 canali).
    """
    versione = 2
    def __init__(s, movimento=True, extra=3, drop=0.3, mu=0.5, sigma=1.0):
        super().__init__()
        s.movimento, s.extra, s.mu, s.sigma = movimento, extra, mu, sigma
        def blk(i, o): return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.MaxPool2d(2))
        s.conv = nn.Sequential(blk(6 + (2 if movimento else 0), 32), blk(32, 64), blk(64, 96))
        s.norm = nn.BatchNorm1d(extra)
        s.fc = nn.Sequential(nn.Linear(96 * (PH // 8) * (PW // 8) + extra, 192), nn.ReLU(), nn.Dropout(drop),
                             nn.Linear(192, 64), nn.ReLU(), nn.Linear(64, 1))
    def forward(s, x, extra):
        x = (x - s.mu) / s.sigma
        if s.movimento:                       # movimento esplicito: frame attuale meno frame vecchio
            d = x[:, :3].mean(1, keepdim=True) - x[:, 3:6].mean(1, keepdim=True)
            x = torch.cat([x, d, d.abs()], 1)
        return s.fc(torch.cat([s.conv(x).flatten(1), s.norm(extra)], 1)).squeeze(1)


def carica_rete(ck, dev=None):
    """Costruisce la rete giusta per un checkpoint: i .pt di prima continuano a funzionare.

    La versione si legge da `versione` nel checkpoint; per i .pt vecchi (che non lo hanno) si
    guarda l'ultimo strato: la rete di prima finisce con `fc.3`, la v2 con `fc.5`.
    """
    sd = ck["stato"]
    cin = sd["conv.0.0.weight"].shape[1]
    extra = sd["fc.0.weight"].shape[1] - 96 * (PH // 8) * (PW // 8)
    if int(ck.get("versione", 2 if "fc.5.weight" in sd else 1)) >= 2:     # rete v2
        net = Rete(movimento=bool(ck.get("movimento", cin >= 8)), extra=extra,
                   mu=float(ck.get("mu", 0.5)), sigma=float(ck.get("sigma", 1.0)))
    else:                                                                 # rete di prima
        net = ReteVecchia(canali=cin, extra=extra)
    net.load_state_dict(sd); net.eval()
    return net.to(dev) if dev is not None else net


def predici_rete(net, X, E, dev, lotto=1024):
    """Probabilita' (0-1) di «premuto» per ogni campione. X: (N,6,PH,PW) in 0-255, E: (N,k)."""
    if len(X) == 0: return np.zeros(0, np.float32)
    E = np.asarray(E, np.float32)
    if E.shape[1] > net.extra:      # la rete di prima vuole solo [nero, distanza]
        E = E[:, :net.extra]
    out = []
    net.eval()
    with torch.no_grad():
        for i in range(0, len(X), lotto):
            x = torch.from_numpy(np.ascontiguousarray(X[i:i + lotto])).to(dev).float() / 255
            out.append(torch.sigmoid(net(x, torch.from_numpy(E[i:i + lotto]).to(dev))).cpu().numpy())
    return np.concatenate(out)


def probabilita_video(net, ck, video, gr, mani=None, dita=True, mostra=True, forza=False):
    """Probabilita' (n_frame x 128, NaN dove il tasto non e' stato guardato) su un video intero.

    E' la stessa identica cosa che fa `4_inferenza.py`: sta qui perche' anche `5_valuta.py`
    deve usarla, e se le due divergessero la misura non varrebbe piu' niente. Con `dita=False`
    si valutano tutti i tasti come se le dita fossero sempre visibili (modelli addestrati
    senza mani.json).
    """
    BW = gr["modello"]["BW"]; fps, it = frames(video); n = controlla_video(video, gr, forza)
    raggio = float(ck.get("raggio", 2.5))
    P = np.full((n, 128), np.nan, np.float32)
    buf = deque(maxlen=int(ck.get("LAG", LAG)) + 1)
    for j, f in enumerate(it):
        if j >= n: break
        buf.append(f); X, E, K = [], [], []
        viste = 1.0 if ((dita and mani[j]) or not dita) else 0.0
        for k, t in gr["frames"][j]["tasti"].items():
            d = dist_mani(t, BW, mani[j]) if dita else 0.0
            if d > raggio: continue                 # lontano dalle dita: non viene valutato
            X.append(stack(f, buf[0], t["poligono"])); K.append(int(k))
            E.append(extra_campione(t["nero"], d, raggio, viste))
        if K: P[j, K] = predici_rete(net, np.stack(X), np.array(E, np.float32), device())
        if mostra and j % 200 == 0: print("  frame", j, "/", n, flush=True)
    return P, fps, n


def liscia(P, r=3):
    """Media mobile su `r` frame, per tasto, senza sporcare i buchi (NaN = tasto non valutato)."""
    if r <= 1: return P
    h = r // 2
    V, C = np.nan_to_num(P, nan=0.0), (~np.isnan(P)).astype(np.float32)
    S = np.full_like(P, np.nan)
    for j in range(P.shape[0]):
        a, b = max(j - h, 0), min(j + h + 1, P.shape[0])
        n = C[a:b].sum(0)
        S[j] = np.where(n > 0, V[a:b].sum(0) / np.maximum(n, 1.0), np.nan)
    return S


def decodifica(P, fps, soglia_on=SOGLIA_ON, soglia_off=SOGLIA_OFF, min_frame=MIN_FRAME):
    """Da probabilita' per tasto (n_frame x 128, NaN dove non valutato) alle note.

    Isteresi: il tasto si accende sopra `soglia_on` e si spegne sotto `soglia_off`; le note
    piu' corte di `min_frame` si buttano (i tremolii di un frame solo non sono note). Un frame
    NaN non cambia lo stato: vuol dire «tasto non guardato», non «non premuto».
    Ritorna [(nota, t_on, t_off, frame_on)] in secondi.
    """
    fuori = []
    for k in np.unique(np.nonzero(~np.all(np.isnan(P), 0))[0]):
        s = P[:, int(k)]
        acceso, inizio, ultimo = False, 0, -1
        for j in range(len(s)):
            if np.isnan(s[j]): continue          # tasto non guardato: non cambia niente
            ultimo = j
            if not acceso and s[j] >= soglia_on: acceso, inizio = True, j
            elif acceso and s[j] <= soglia_off:
                acceso = False
                if j - inizio >= min_frame: fuori.append((int(k), inizio / fps, j / fps, inizio))
        if acceso and ultimo + 1 - inizio >= min_frame:      # nota ancora premuta alla fine
            fuori.append((int(k), inizio / fps, (ultimo + 1) / fps, inizio))
    return sorted(fuori, key=lambda e: (e[1], e[0]))


def confronta_note(trovate, vere, tol=TOL_ON):
    """Accoppia le note riconosciute con quelle vere: stessa nota, onset entro `tol` secondi."""
    usate, scarti, presi = set(), [], 0
    for nota, t0, _t1, _f in trovate:
        migliore = None
        for i, (nv, tv0, _tv1) in enumerate(vere):
            if i in usate or int(nv) != int(nota): continue
            d = abs(float(tv0) - float(t0))
            if d <= tol and (migliore is None or d < migliore[0]): migliore = (d, i, float(tv0))
        if migliore is None: continue
        usate.add(migliore[1]); presi += 1; scarti.append((float(t0) - migliore[2]) * 1000.0)
    pr = presi / len(trovate) if trovate else 0.0
    rc = presi / len(vere) if vere else 0.0
    return {"precision": pr, "recall": rc, "f1": 2 * pr * rc / (pr + rc) if pr + rc else 0.0,
            "n_trovate": len(trovate), "n_vere": len(vere), "n_giuste": presi,
            "n_extra": len(trovate) - presi, "n_mancate": len(vere) - presi,
            "onset_mediano_ms": float(np.median(scarti)) if scarti else None,
            "onset_5_95_ms": [float(np.percentile(scarti, 5)), float(np.percentile(scarti, 95))] if scarti else None}


def eventi_da_npz(d):
    """Gli attacchi veri di un pezzo: (nota, t_on, t_off) in secondi, salvati dal dataset."""
    if "eventi" in d.files and len(np.asarray(d["eventi"])):
        return [(int(n), float(a), float(b)) for n, a, b in np.asarray(d["eventi"])]
    fps = float(d["fps"]) if "fps" in d.files else 0.0          # dataset vecchi: si ricavano
    if not fps: return []
    fr, no, y = np.asarray(d["frame"]), np.asarray(d["nota"]), np.asarray(d["y"])
    fuori = []
    for k in np.unique(no):
        m = no == k; o = np.argsort(fr[m]); f2, y2 = fr[m][o], y[m][o]
        for i in np.nonzero((y2[1:] == 1) & (y2[:-1] == 0))[0]:
            fuori.append((int(k), float(f2[i + 1]) / fps, 0.0))
    return sorted(fuori, key=lambda e: e[1])


def salva_midi_eventi(eventi, path, bpm=120.0, velocity=80):
    """Scrive un .mid dagli eventi (nota, t_on, t_off) in secondi: e' l'uscita della rete."""
    import mido
    tpb = 480
    mf = mido.MidiFile(ticks_per_beat=tpb)
    tr = mido.MidiTrack(); mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    ev = []
    for nota, t0, t1 in eventi:
        t1 = max(float(t1), float(t0) + 0.05)
        ev.append((float(t0), 1, int(nota))); ev.append((t1, 0, int(nota)))
    ev.sort(key=lambda e: (e[0], e[1]))          # a pari tempo prima i note_off
    prec = 0
    for quando, tipo, nota in ev:
        tick = int(round(quando * bpm / 60.0 * tpb))
        tr.append(mido.Message("note_on" if tipo else "note_off", note=nota,
                               velocity=velocity if tipo else 0, time=max(0, tick - prec)))
        prec = max(prec, tick)
    mf.save(str(path))
    return str(path)


def augmenta(x, pot=1.0):
    """Alterazioni casuali sulle patch di un lotto (x: (B,C,PH,PW) in 0-1, gia' sul device).

    Geometria: rotazione, scala, traslazione e un po' di prospettiva per campione — la stessa
    cosa che succede quando la griglia dei tasti sbaglia di 10-20 px.
    Fotometria: esposizione, contrasto, gamma, colore, vignettatura, rumore, sfocatura e
    qualcosa davanti al tasto. E' quello che fa funzionare la rete su riprese diverse da
    quelle di partenza: senza, impara a memoria la scena che ha visto.
    """
    if pot <= 0: return x
    B, _, H, W = x.shape
    dev = x.device
    r = lambda *s: torch.rand(*s, device=dev)
    ang = (r(B) - 0.5) * (5.0 * pot) * math.pi / 180
    scala = 1 + (r(B) - 0.5) * 0.20 * pot
    co, si = torch.cos(ang) * scala, torch.sin(ang) * scala
    th = torch.zeros(B, 2, 3, device=dev)
    th[:, 0, 0], th[:, 0, 1], th[:, 0, 2] = co, -si + (r(B) - 0.5) * 0.20 * pot, (r(B) - 0.5) * 0.18 * pot
    th[:, 1, 0], th[:, 1, 1], th[:, 1, 2] = si, co + (r(B) - 0.5) * 0.10 * pot, (r(B) - 0.5) * 0.12 * pot
    x = F.grid_sample(x, F.affine_grid(th, x.shape, align_corners=False), mode="bilinear",
                      padding_mode="border", align_corners=False)
    x = x * (1 + (r(B, 1, 1, 1) - 0.5) * 0.9 * pot) + (r(B, 1, 1, 1) - 0.5) * 0.25 * pot
    x = x.clamp(1e-4, 1) ** (1 + (r(B, 1, 1, 1) - 0.5) * 0.9 * pot)
    x = x * (1 + (r(B, x.shape[1], 1, 1) - 0.5) * 0.3 * pot)
    if float(r(1)) < 0.5:                                   # obiettivo morbido / fuori fuoco
        k = (torch.tensor([1., 2., 1., 2., 4., 2., 1., 2., 1.], device=dev) / 16).view(1, 1, 3, 3)
        x = F.conv2d(F.pad(x, (1, 1, 1, 1), mode="replicate"), k.expand(x.shape[1], 1, 3, 3), groups=x.shape[1])
    x = x + 0.03 * pot * torch.randn_like(x)                # rumore del sensore
    yy = (torch.arange(H, device=dev).float() / H - 0.5)[None, None, :, None]
    xx = (torch.arange(W, device=dev).float() / W - 0.5)[None, None, None, :]
    x = x * (1 - (r(B) * 1.2 * pot)[:, None, None, None] * (xx ** 2 + yy ** 2))   # vignettatura
    ar, ac = torch.arange(W, device=dev), torch.arange(H, device=dev)
    x0, y0 = (r(B) * W * 0.7).long(), (r(B) * H * 0.7).long()
    ww, hh = (1 + r(B) * 0.4 * W).long(), (1 + r(B) * 0.5 * H).long()
    davanti = ((ar[None, :] >= x0[:, None]) & (ar[None, :] < (x0 + ww)[:, None]))[:, None, None, :] & \
              ((ac[None, :] >= y0[:, None]) & (ac[None, :] < (y0 + hh)[:, None]))[:, None, :, None]
    x = x * (1 - davanti.float() * (r(B, 1, 1, 1) < 0.6).float() * (0.15 + 0.35 * r(B, 1, 1, 1)))
    return x.clamp(0, 1)


def device():
    return torch.device("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")
