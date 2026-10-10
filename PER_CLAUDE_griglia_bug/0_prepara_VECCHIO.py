#!/usr/bin/env python3
"""Passo 0 del corso: il video si ritaglia sulla tastiera e la griglia trovata si controlla a occhio.

Se la ripresa è a mano libera la griglia viene inseguita fotogramma per fotogramma e il ritaglio
la segue (vedi "LA GRIGLIA INSEGUITA" qui sotto): con `--insegui 0` il comportamento è quello di
sempre, rettangolo e griglia congelati sul primo fotogramma.

PERCHE' ESISTE
`motore_prospettica.py` cerca la griglia dei tasti per periodicità (profilo verticale + tasti
neri via NCC) e non ha nessun modello che dica "il pianoforte è lì": se la ripresa è larga si
aggancia alla fascia sbagliata senza accorgersene. Misurato sul frame 0 di una registrazione
PianoVAM (1920x1080, tasti veri da 33.4 px in una fascia a y 335..574):

    stadio                                  passo    inlier   "evidenza"
    griglia scelta dal motore (sbagliata)   29.9 px     29      0.837   <- 64 tasti nel frame
    stesso motore sul ritaglio (giusta)     33.2 px    231      0.567   <- 52 tasti, giusti

Il candidato sbagliato vince 29 a 28 perché H_iniziale sceglie chi ha *più inlier*: con la
tastiera lontana le corrispondenze valide sono troppo poche per distinguere, e la griglia si
posa sulla cassa del pianoforte (la metrica di plausibilità conta i tasti bianchi come se
dovessero essere scuri, quindi una zona scura prende un punteggio alto). Ritagliando invece le
corrispondenze diventano 231 e non c'è più partita.

COME TROVA LA TASTIERA (--auto, default)
    passo_profilo() sul primo fotogramma -> passo + banda dei TASTI NERI (y 340..491 nel caso
    sopra) -> la tastiera INTERA misurata su tutto il pezzo (vedi sotto) -> da lì quattro
    rettangoli "a forma di tastiera" (--margine passi sopra, --fondo passi sotto):
       intero   = la larghezza intera del fotogramma
       profilo  = tagliato ai lati attorno alla fase del profilo (fase + 53 tasti)
       neri     = il bordo di LA0 misurato sui tasti neri veri del primo fotogramma + 52 tasti
       estremi  = la tastiera vera: dal bordo di LA0 alla fine di DO8, misurati su tutto il pezzo
    -> dentro ogni rettangolo una griglia (H_iniziale, oppure ancorata agli estremi per il
       candidato "estremi") -> verifica (inlier + coerenza del passo + plausibilità + numero di
       tasti e tasti del modello fuori dal ritaglio, che però contano solo se la finestra la
       tastiera la può contenere + tasti del modello FUORI DALLA TASTIERA misurata): si tiene il
       primo che dà "ok", altrimenti il migliore (verdetto, poi inlier).
       "neri" ed "estremi" spostano il ritaglio, quindi entrano solo se sono "ok"; unica
       eccezione, "estremi" che è solo "incerto" ma sta DENTRO la tastiera misurata mentre il
       migliore degli altri ne esce (misurato su 2024-02-14_19-44-26 e 2024-02-14_20-37-55: 0,0
       tasti fuori contro 13,5 e 6,6, col passo vero al posto di +4% e +6,7%). Il verdetto resta
       "incerto", quindi l'avviso e l'immagine di controllo restano: cambia solo la griglia.
    Sul caso sopra il rettangolo ricavato così dà passo 33.2 px con 82-157 inlier (contro 28-29).

    I candidati stretti servono davvero perché nessuno vince sempre: sull'intera larghezza la
    finestra è più larga della tastiera, il centro della finestra non è il centro della tastiera,
    l'ottava scelta dal profilo cade due tasti a destra e la griglia disegna tasti sulla cassa
    (misurato: 59.2 tasti nella finestra invece di 52, bordo di LA0 a 171 px invece di 95, 226
    inlier che sembrano tanti solo perché le corrispondenze del feltro non vincolano la x). La
    striscia dei neri lì rimette tutto a posto (52.8 tasti, bordo di LA0 a 81 px contro i 95
    veri) ma su un'altra registrazione PianoVAM `_H_iniziale_classico` parte dal gruppo di neri
    sbagliato e chiede un ritaglio spostato di 13 tasti: là vinceva il profilo (55.1 tasti, passo
    32.3 px contro il vero 33.1, il caso documentato dei 35.9 px +8%).

    Il profilo però non sempre legge, e quando non legge non può decidere: su una tastiera OBLIQUA
    i neri non sono verticali, il profilo di colonne li spalma l'uno sull'altro e la periodicità
    che ne esce è quella sbagliata. Misurato sul primo fotogramma di
    `video5906842636420915152` (tastiera ruotata, ~10 px per tasto misurati uno per uno sui neri:
    scarti 11,5 / 12,5 / 18,5 px = 1,12 / 1,2 / 1,78 del passo vero): il profilo diceva 76,4 px
    (= 11 tasti nel fotogramma, dove si vede la tastiera intera da 52) con NCC 0,372, la più bassa
    delle 33 registrazioni in `web_runs/_prepara` contro 0,455-0,613 delle 14 PianoVAM e 0,89 del
    primo piano dell'utente, tutte col passo giusto. Il ritaglio "intero" lì aveva il passo a
    10,17 px (dentro l'1-3% dai neri veri), 193 inlier e 0,61 di plausibilità, e veniva RIFIUTATO
    per colpa del profilo: sotto `_NCC_PROFILO_MIN` (0,45) quello scarto vale "incerto" e non
    "rifiuto" (vedi `verdetto`), così il video preparato e il video della griglia si scrivono
    comunque, con l'avviso.

COME TROVA LA TASTIERA VERA (il candidato "estremi", quello che vince ora)
    Il difetto che si vede nell'esempio 7 (`2024-02-14_21-30-04`): la griglia cade due tasti a
    destra, i riquadri dei neri finiscono sul tablet e sul vestito, un do risulta etichettato "la"
    e a sinistra due tasti restano senza griglia. Sono tutti lo stesso errore: la x della griglia
    viene dal centro della finestra (H_profilo) o dai gruppi di neri del primo fotogramma
    (_H_iniziale_classico), e su questa ripresa sbagliano di +1,6 tasti (LA0 a 173 px contro 121)
    o di +10 tasti (il primo fotogramma ha il tablet davanti ai neri).

    La tastiera invece è una fascia in cui SOTTO le punte dei neri i tasti bianchi sono chiari:
    mettendo in OR quelle colonne su dodici fotogrammi sparsi, chi la copre (mani, tablet,
    spartito) da qualche parte si sposta e la fascia resta intera — basta chiedere che una colonna
    sia chiara in ALMENO METÀ dei fotogrammi, altrimenti un maglione chiaro che passa allunga la
    tastiera di tre tasti (misurato su `2024-02-15_15-13-10`: 0..1841 invece di 120..1839).
    Quanti tasti ci stanno dentro lo dice la scala dei tasti neri raccolta su tutto il pezzo:
    il passo del profilo è +1% e lo span diviso quello dà 51 tasti invece di 52. Misurato sui
    cinque pezzi PianoVAM con la verità nel metadata (LA0/DO8 veri 120..1842 e passo 33,12):
    fascia 119..1841, passo 33,12, 52 tasti, 180 inlier (contro 80 dell'intero), 27 neri al posto
    giusto (7 sotto una mano o un tablet, 2 fuori posto) e ZERO tasti del modello fuori dalla
    tastiera. Sull'altro pezzo dell'utente (LA0/DO8 veri 95..1769, passo 32,19): fascia
    95..1768, passo 32,17, 52 tasti, 186 inlier nella griglia, 36 neri su 36 al posto giusto.
    La fascia intera vince sul tratto buono più lungo quando ci sta dentro una tastiera: un
    tablet fermo per tutto il pezzo lascia un buco nella maschera e la tastiera continua di là.

    La x della griglia viene da lì (H_dagli_estremi: u=0 è 23 tasti dopo LA0, nessuna ottava da
    indovinare) e viene RI-ancorata agli estremi dopo l'affinamento (riancora_x), perché affina
    sposta il passo dello 0,9%.

    La y non si lascia indovinare a nessuno: il fondo dei tasti e le punte dei neri si MISURANO su
    tutto il pezzo (`verticale_neri`: per ogni nero, alla colonna del centro che gli danno gli
    estremi, si cerca il run scuro largo quanto un nero che sta più vicino, riga per riga) e si
    scrivono nell'omografia DOPO `affina` (`riga_y_misurata`), inclinazione compresa (il bordo
    posteriore scende di 11 px da destra a sinistra). Su questa ripresa `H_iniziale` dava 17,4 px
    per larghezza di tasto contro i 33,7 veri — bordo posteriore a y 356 a sinistra e 345 a
    destra, punte dei neri a 486: la griglia veniva alta la METÀ dei tasti, coi riquadri che
    coprono solo la parte dietro di ogni tasto e le pressioni sulla parte davanti restano fuori.
    Sui sette video di prova la misura riesce su tutti e sette (passo_y 27,5..34,8 px contro passi
    orizzontali 32,2..33,7). Sbagliava anche `H_profilo`: la riga di fondo la metteva a y=87 (il
    mobile scuro) invece che a 342, cioè una griglia disegnata 255 px troppo in alto.
Non si usa il detector YOLO del progetto: su queste riprese restituisce il pianoforte INTERO
(box (0,2)-(1904,610), confidenza 0.31) e ritagliando lì dentro la griglia sbaglia ancora.

USCITA (dentro --out CARTELLA)
    <nome>.mp4            il video ritagliato (o raddrizzato), dagli stessi frame, stessi fps
    <nome>.json           rettangoli per frame, geometria, numeri di controllo e verdetto
    <nome>_controllo.jpg  il frame 0 con UN RIQUADRO PER TASTO (verdi i bianchi, arancioni i
                          neri, col nome della nota), il riquadro magenta del ritaglio, i due
                          bordi gialli della tastiera misurata (LA0 e fine di DO8) e i numeri
                          dei tasti neri (al posto giusto / sotto una mano / fuori posto):
                          si guarda a occhio prima di addestrare
    <nome>_griglia.mp4    lo STESSO disegno su tutto il pezzo (un frame ogni tanto, riscalato):
                          l'immagine mostra solo il primo frame, e se la griglia scivola più
                          avanti, o le mani coprono i tasti, o il pianoforte si muove, lì non si
                          vede. Con l'inseguimento attivo (default) i riquadri seguono i tasti
                          fotogramma per fotogramma e il riquadro magenta segue il ritaglio.
                          Muto e corto apposta: è un controllo, non il video di lavoro

Il tempo non si tocca (nessun frame perso o aggiunto, gli fps restano quelli del video, l'audio si
copia dall'originale): il MIDI resta allineato com'era, il ritardo misurato non cambia. Poi si
prosegue come sempre, ma sulla `<nome>.mp4`:

    python3 ../motore_prospettica.py <nome>.mp4 -o <cartella dell'allineamento>
    python3 2_costruisci_dataset.py --video <nome>.mp4 --griglia <quella griglia> --midi ...

LA GRIGLIA INSEGUITA (quando la ripresa è a mano libera, `--insegui auto`, il default)
    Il rettangolo congelato dice dove sta la tastiera sul PRIMO fotogramma, e su una ripresa a
    mano libera non basta: misurato sul video dell'utente, la tastiera si sposta di 393 px in
    diagonale (7,5 tasti) e a fine pezzo il ritaglio fisso la lascia per metà fuori (i tasti neri
    inquadrati passano da 9 a 0), mentre il controllo disegnato col rettangolo del primo
    fotogramma mostra una griglia che "scivola" — un difetto del CONTROLLO, che farebbe scartare
    una griglia buona: la griglia misurata sul primo fotogramma era a 1,8 px dai tasti veri.

    Con `--insegui auto` (o `1`) la griglia si trasporta fotogramma per fotogramma col tracker del
    progetto (`griglia_prospettica.flusso`: flusso ottico + omografia + `affina`, ripartenza da
    zero solo su un cambio di inquadratura vero, deciso dal rapporto fra inlier e punti seguiti) e:
      - il video della griglia disegna la griglia di QUEL fotogramma (col ritaglio che la segue);
      - il video preparato si ritaglia seguendo la tastiera, così resta ferma al suo posto e grande
        uguale anche se la camera si muove;
      - il json porta i numeri dell'inseguimento e se il ritaglio è "fisso" o "stabilizzato".
    La decisione si prende sulla media pesata (EMA) del moto, non sul fotogramma singolo: il
    tremolio dell'aggancio non conta come movimento, e non fa tremare il video preparato. Sotto
    `_SOGLIA_SEGUI_TASTI` (0,35) la camera è ferma e si scrive il ritaglio fisso di sempre, cioè
    lo stesso file di prima; `--insegui 0` spegne tutto e dà esattamente il comportamento vecchio
    (verificato: file identico byte per byte). Il frame 0 del video preparato è il ritaglio di
    sempre in ogni caso, così l'ancoraggio del motore (che da un fotogramma solo indovina la fase
    dei tasti) non ha una scusa per sbagliare: con la finestra di modello al posto del moto
    relativo l'ancoraggio sbagliava (19 inlier invece di 58).

Esempi
    python3 0_prepara.py --video ~/pianovam_pezzi/brano1.mp4 --out ~/pianovam_pezzi
    python3 0_prepara.py --pianovam ~/PianoVAM_v1.2 --rec 2024-02-15_20-07-54 --durata 120 --out /tmp/p
    python3 0_prepara.py --video ~/mio_video.mp4 --rettangolo 210,880,1690,1050 --out ~/mio_video_pronti
    python3 0_prepara.py --video ~/a_mano_libera.mp4 --insegui 0 --out /tmp/p    # come prima
"""
import argparse
import json
import subprocess
import sys
import warnings
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # il motore sta qui sopra
import griglia_prospettica as G                                     # noqa: E402

# Non importa comune.py: quello tira dentro torch (pesante e inutile qui). A questo passo
# servono solo cv2, numpy e il motore geometrico, così gira anche nell'ambiente leggero.


def apri(video):
    """(cap, fps, n_frame) del video."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        sys.exit(f"[!] non riesco ad aprire {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    return cap, fps, n


def evidenza_giusta(grigio, H, T):
    """Versione corretta di `motore_prospettica._evidenza`: i tasti BIANCHI devono essere CHIARI.

    Là dentro si conta la frazione di pixel scuri sotto la griglia sia per i neri sia per i
    bianchi, quindi una griglia posata su una superficie scura prende ~0.84 mentre una giusta
    si ferma a ~0.55 (misurato): la soglia `_TAGLIO_MIN_EVIDENZA = 0.80` premia la zona scura.
    Qui si chiede "neri scuri E bianchi chiari": giusta 0.76-0.79, sulla cassa del pianoforte
    0.48. Riportata qui e non nel motore perché cambiare il motore sposta anche il tracciamento
    dei video degli utenti: prima si misura, poi eventualmente si porta là.
    """
    neri = [n for n in range(21, 109) if n % 12 in G._NERI_PC]
    bianchi = [n for n in range(21, 109) if n % 12 not in G._NERI_PC]
    parti = []
    for note, vs, scuro_voluto in ((neri, (0.8, 1.4, 2.0, 2.6, 3.2), True),
                                   (bianchi, (G.LB + 0.35, G.LW - 0.35), False)):
        pts = [(G.u_nero(n) if n % 12 in G._NERI_PC else G.u_bianco(n) + 0.5, v)
               for n in note for v in vs]
        p = G.proietta(H, pts)
        h, w = grigio.shape
        dentro = (np.isfinite(p).all(axis=1) & (p[:, 0] >= 1) & (p[:, 0] < w - 1)
                  & (p[:, 1] >= 1) & (p[:, 1] < h - 1))
        if not dentro.any():
            continue
        p = p[dentro]
        scuro = grigio[p[:, 1].astype(int), p[:, 0].astype(int)] < T
        parti.append(float(scuro.mean() if scuro_voluto else (~scuro).mean()))
    return float(np.mean(parti)) if parti else 0.0


# --- 1. dove sta la tastiera ---------------------------------------------------------

def tastiera_dai_neri(banda):
    """(x del bordo di LA0, passo) misurati agganciando i TASTI NERI veri, o None.

    `_H_iniziale_classico` trova i neri nell'immagine, ne raggruppa 2+3 e li lega alle note del
    modello: è l'unico ancoraggio che NON dipende da dove sta la finestra (misurato sul frame 0
    di una ripresa PianoVAM: 70,5 px col ritaglio intero, 70,5 stretto, 75,1 tagliato a destra),
    mentre `H_profilo` sceglie l'ottava col centro della finestra e sull'intero fotogramma
    sbagliava di +2,26 tasti (bordo a 167,6 px invece di 95). Da quel bordo la tastiera di un
    pianoforte è larga esattamente 52 bianchi.

    `banda` è il fotogramma tagliato alla sola fascia dei tasti: sul fotogramma INTERO la stessa
    funzione trova prima la cassa scura del pianoforte (righe con tanti blob larghi) e si arrende,
    quindi la fascia gliela passa `candidati_auto` (l'x resta in pixel del fotogramma perché il
    taglio è verticale).
    """
    try:
        H = np.asarray(G._H_iniziale_classico(banda), dtype=float)
    except (RuntimeError, ValueError):
        return None
    s = float(np.hypot(H[0, 0], H[1, 0]))
    x = float(G.proietta(H, [(G.u_bianco(G.NOTA_MIN), 0.0)])[0][0])
    w = banda.shape[1]
    if not (np.isfinite(x) and np.isfinite(s)) or not (0.004 * w < s < 0.09 * w):
        return None
    return x, s


def banda_dai_neri(frame):
    """(passo, y del bordo posteriore dei neri) misurati sui TASTI NERI veri, o None.

    Serve quando il profilo non legge (NCC sotto `_NCC_PROFILO_MIN`): su una tastiera obliqua il
    profilo di colonne spalma un nero sull'altro e il passo che ne esce non e' una misura (misurato
    sul caso b2: 76,4 px contro 10,2 veri). La scala e la banda dei neri ci sono lo stesso, e sono
    le stesse che usa l'ancora del primo fotogramma (`griglia_prospettica.banda_neri`): il passo e'
    la scala di `_H_iniziale_classico`, la y e' la prima riga del blocco dei neri -- cioe' il bordo
    posteriore dei tasti, che e' `v = 0` del modello e quindi la quota da cui `tastiera_nel_video`
    conta i tasti bianchi sotto le punte.
    """
    try:
        y0, _ya, _yb, _pieno, _leggi = G.banda_neri(frame)
        H = np.asarray(G._H_iniziale_classico(frame), dtype=float)
    except (RuntimeError, ValueError):
        return None
    w = frame.shape[1]
    s = float(np.hypot(H[0, 0], H[1, 0]))
    if not (0.004 * w < s < 0.09 * w):
        return None
    return s, float(y0)


def campioni(video, inizio, durata, quanti=12):
    """Fotogrammi distribuiti su TUTTO il pezzo: [(t, frame)].

    Serve a `tastiera_nel_video`: la tastiera si guarda anche in tutti i momenti in cui
    mani, tablet o spartito la coprono, non solo sul primo fotogramma.
    """
    cap, fps, n = apri(video)
    t0 = max(0.0, float(inizio or 0.0))
    fine = (n / fps) if n else t0 + 60.0
    if durata:
        fine = min(fine, t0 + float(durata))
    if fine - t0 < 0.5:                    # pezzo più corto di mezzo secondo: un fotogramma
        fine = t0 + 0.5
    fuori = []
    for t in np.linspace(t0, max(t0, fine - 0.5), max(3, int(quanti))):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(float(t) * fps)))
        ok, f = cap.read()
        if ok:
            fuori.append((float(t), f))
    cap.release()
    return fuori


def estremi_fascia(acc, s):
    """(primo, ultimo) colonna della tastiera dentro la maschera accumulata `acc`.

    `acc` è "questa colonna è stata un tasto bianco nella maggior parte dei fotogrammi". La
    fascia buona è quella in cui la densità di colonne-tasto su una finestra di un tasto e mezzo
    resta sopra metà: fuori dalla tastiera non c'è niente di chiaro per tutta l'altezza dei tasti,
    quindi la densità crolla e la fascia si chiude. Si prova prima la fascia INTERA (primo e
    ultimo tratto buono): se ci sta dentro una tastiera (44..56 tasti bianchi) è quella — un
    tablet fermo per tutto il pezzo lascia un buco in mezzo e la tastiera continua di là. Se la
    fascia intera è troppo larga (una parete chiara, un altro pezzo di tastiera in un'altra
    inquadratura) si ripiega sul tratto buono più lungo.
    """
    k = max(3, int(1.5 * s))
    dens = np.convolve(acc.astype(np.float32), np.ones(k, np.float32) / k, mode="valid")
    buono = np.zeros(dens.size, bool)
    buono[dens >= 0.5] = True
    run = G._runs(buono)
    if not run:
        return None
    for a, b in ((run[0][0], run[-1][1]), max(run, key=lambda r: r[1] - r[0])):
        idx = np.where(acc[a:min(acc.size, b + k)])[0]
        if idx.size < 3:
            continue
        x0, x1 = float(a + idx[0]), float(a + idx[-1] + 1)     # ultima colonna + 1 = bordo destro
        if 44 <= (x1 - x0) / s <= 56:
            return x0, x1
    return None


def scala_dai_neri(campioni_video, ya, s, w, dentro):
    """I centri dei tasti neri visti su TUTTO il pezzo, in pixel (x assoluta del fotogramma).

    `dentro` è (primo, ultimo) colonna della tastiera: fuori di lì i neri sono il mobile di
    legno e i riflessi e non dicono niente. Si raccolgono i neri di tutte le riprese perché
    ogni fotogramma ne perde qualcuno (una mano, un riflesso) e la scala vuole essere intera.
    """
    x0, x1 = dentro
    wmin, wmax = max(2.5, 0.004 * w), 0.075 * w
    centri = []
    for _t, f in campioni_video:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        T = G._soglia(g)
        for v in (1.1, 2.0, 2.9):                    # dentro i neri, lontano dalle punte
            y = int(round(ya + v * s))
            if 1 <= y < g.shape[0] - 1:
                for a, b in G._runs(g[y] < T):
                    if wmin <= b - a <= wmax and x0 - 0.5 * s <= (a + b) / 2 <= x1 + 0.5 * s:
                        centri.append((a + b) / 2.0)
    return centri


def grappoli_neri(centri, passo):
    """Un rappresentante per tasto nero: lo stesso nero in fotogrammi diversi dista pochi pixel,
    due neri diversi almeno mezzo passo. Senza questo raggruppamento i centri sono centinaia (n
    fotogrammi x n righe) e il rumore premia il passo sbagliato: misurato su
    2024-02-14_20-37-55, con 1265 centri grezzi vinceva 53 tasti (31 colpi) contro i 52 veri (26).
    """
    c = np.sort(np.asarray(centri, dtype=float))
    gruppi, cur = [], [float(c[0])]
    for x in c[1:]:
        if x - cur[-1] <= 0.25 * passo:
            cur.append(float(x))
        else:
            gruppi.append(float(np.median(cur)))
            cur = [float(x)]
    gruppi.append(float(np.median(cur)))
    return gruppi


def quanti_tasti(estremi_x, passo_profilo, centri_neri):
    """Quanti tasti bianchi stanno fra i due estremi: lo dice la scala dei tasti neri.

    Gli estremi dicono dove comincia e dove finisce la tastiera; il numero di tasti che ci sta
    dentro lo dice la scala dei neri, che è periodica e si vede su tutto il video. Dividere per
    il passo del profilo sarebbe più fragile: misurato, quel passo è +1% (33,43 px contro 33,12
    veri) e lo span diviso 33,43 dà 51,48, cioè un tasto in meno dei veri — e un tasto in meno su
    52 è una griglia storta del 2% su tutta la tastiera.

    Si prova con 46..56 tasti e si tiene quello i cui neri del modello "spiegano" i neri misurati
    senza sbavature. Non si conta quante note cadono vicine: il rilevatore dei neri è spostato di
    ~6 px a sinistra rispetto al modello (misurato su tutte le riprese PianoVAM: il primo nero
    trovato sta a 0,93 tasti da LA0 contro gli 1,12 del modello) e quel bias è uguale per tutti i
    tasti, quindi non dice niente. Quello che dice è la DISPERSIONE degli scarti attorno al loro
    mediano: con il conto giusto il p90-mediano resta sotto 9 px, con un tasto in più o in meno
    (0,6 px per tasto, 30 px in fondo alla tastiera) sale a 11-16 px.
    """
    x_la0, x_c8 = estremi_x
    span = x_c8 - x_la0
    if not centri_neri:
        return int(round(span / passo_profilo)), 0
    c = np.asarray(grappoli_neri(centri_neri, passo_profilo), dtype=float)
    mig = None
    for n in range(46, 57):
        passo = span / n
        scarti = np.array([float(np.min(np.abs(c - (x_la0 + (G.u_nero(k) - G.u_bianco(G.NOTA_MIN))
                                                           * passo)))) for k in G.NERI])
        med = float(np.median(scarti))
        dispersione = float(np.percentile(scarti, 90)) - med
        colpi = int((np.abs(scarti - med) < 0.3 * passo).sum())
        if mig is None or dispersione < mig[0]:
            mig = (dispersione, colpi, n, passo)
    dispersione, colpi, n, passo = mig
    if dispersione > 0.35 * passo:            # i neri non si leggono: meglio quello del profilo
        return int(round(span / passo_profilo)), colpi
    return n, colpi


def tastiera_nel_video(p, campioni_video):
    """Dove comincia e dove finisce la tastiera, guardando TUTTO il pezzo.

    Sul singolo fotogramma il bordo di LA0 lo dà il centro della finestra (`H_profilo`, che
    assume il centro della tastiera al centro dell'inquadratura) o i gruppi di tasti neri
    (`_H_iniziale_classico`, che si perde un nero sul mobile di legno o sui riflessi): sono
    le due strade che sbagliano, e le misure stanno nella docstring del modulo. La tastiera
    invece è una fascia in cui SOTTO le punte dei neri i tasti bianchi sono chiari: mettendo
    in OR quelle colonne su dodici fotogrammi sparsi, chi la copre (mani, tablet, spartito)
    da qualche parte si sposta e la fascia resta intera.

    Misurato sull'esempio 7 (`2024-02-14_21-30-04`, verità di metadata.json 121..1842, passo
    33,12 px): fascia 119..1841 -> 52 tasti da 33,12 px (+0,0%), mentre la stessa tastiera
    ancorata dal profilo cadeva a 173..1919, un tasto e mezzo a destra; il bordo dai neri di
    `tastiera_dai_neri` sul primo fotogramma cadeva a 458 (10 tasti a destra), sul quarantesimo
    a 102.

    Ritorna dict(x_la0, x_c8, passo, tasti, copertura, visto, campioni) oppure None quando la
    fascia trovata non ha la larghezza di una tastiera (o è quasi tutta coperta).
    """
    s, _fase, _ncc, ya, _yb = p
    y0 = int(ya + 0.9 * G.LB * s)                       # sotto le punte dei neri
    acc, letti = None, 0
    for _t, f in campioni_video:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        h = g.shape[0]
        y1 = int(min(h - 1, ya + G.LW * s))             # fine dei tasti bianchi
        if y1 - y0 < 8:
            return None
        vis = (g[y0:y1] < G._soglia(g)).mean(axis=0) < 0.5      # colonna chiara = tasto
        acc = vis.astype(np.int16) if acc is None else acc + vis
        letti += 1
    if acc is None or not acc.any():
        return None
    # "tasto" = colonna chiara in ALMENO METÀ dei fotogrammi: con uno solo basta un maglione
    # chiaro che passa, o una parete illuminata, e la tastiera si allunga di tre tasti a
    # sinistra (misurato su 2024-02-15_15-13-10: la fascia diventava 0..1841 invece di 120..1839).
    visto = acc >= max(2, int(np.ceil(0.5 * acc.max())))
    est = estremi_fascia(visto, s)
    if est is None:
        return None
    tasti, colpi = quanti_tasti(est, s, scala_dai_neri(campioni_video, ya, s,
                                                       campioni_video[0][1].shape[1], est))
    if not 44 <= tasti <= 56:
        return None
    dentro = visto[int(est[0]):int(est[1])]
    if dentro.mean() < 0.5:                             # più di metà mai vista: non mi fido
        return None
    return {"x_la0": float(est[0]), "x_c8": float(est[1]), "passo": float((est[1] - est[0]) / tasti),
            "tasti": int(tasti), "copertura": float(dentro.mean()),
            "neri_misurati": int(colpi), "visto": visto, "campioni": letti}


_SCARTO_NERO = 0.40        # px dentro cui un run scuro è "quel" tasto nero, in passi di tasto


_FRONTE_CHIARO = 0.75      # frazione del 90° percentile sotto cui un tasto non è più chiaro
_FRONTE_SCURO = 0.32       # sopra questa il bordo trovato sotto il fronte non è il rastrello
_FRONTE_MIN = 0.55         # tratto chiaro minimo (in lunghezze di tasto) perché sia un tasto


def fronte_bianchi(campioni_video, x_la0, x_c8, fondo, punte, xm, passo_y):
    """Dove FINISCONO i tasti bianchi (il fronte, prima del rastrello), misurato su tutto il pezzo.

    E' l'ultimo pezzo della geometria verticale che restava indovinato. La scala verticale si
    misura sulle punte dei neri (`verticale_neri`), che sono l'unico bordo netto, e il modello
    dei tasti dà ai neri il 66% della lunghezza del tasto (`griglia_prospettica.LB` su 6,2):
    fra i pianoforti veri quel rapporto va dal 56% al 64%, quindi il fronte dei bianchi cade
    dove dice il modello, corto di 7-25 px (misurato sull'esempio 48: fronte vero a 652 px, il
    modello lo disegna a 627). Quella differenza sono i riquadri dei bianchi che si fermano prima
    della punta del tasto: è il difetto che si vede a occhio nel controllo ("i tasti bianchi non
    sono coperti fino in fondo"). Qui si misura, come si fa per fondo e punte.

    Come. La colonna al CENTRO di un tasto bianco è chiara dal bordo posteriore al fronte (i neri
    stanno sui BORDI del tasto, non al centro): si prende il tratto chiaro più lungo della colonna
    e il fronte è dove finisce. Sotto c'è il rastrello del pianoforte, nerissimo e staccato di
    netto: la colonna vale solo se il tratto chiaro è lungo almeno `_FRONTE_MIN` tasti e dopo il
    crollo è secco (`_FRONTE_SCURO`). Così le mani (scure), le ombre e il tappeto (chiaro a
    chiazze, ma non attaccato al tasto) si scartano da soli — a differenza delle punte dei neri
    il fronte non è mai netto "a riga", va cercato colonna per colonna. Dodici fotogrammi sparsi
    danno ~250 punti: la retta che ne esce è il fronte e la dispersione dice se è credibile
    (misurata: 1,5-8,5 px su 12 fotogrammi).

    Ritorna (a, b, quanti, dispersione) con y = a + b * (x - x_riferimento) in pixel del
    fotogramma, oppure None quando i punti sono pochi o la retta è dispersa (0,35 passi in x).
    """
    passo = (x_c8 - x_la0) / 52.0
    a0, b0 = fondo
    a1, b1 = punte
    w = campioni_video[0][1].shape[1]
    h = campioni_video[0][1].shape[0]
    punti: list[tuple[float, float]] = []
    for _t, f in campioni_video:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        P = float(np.percentile(g, 90))
        Tc, Ts = _FRONTE_CHIARO * P, _FRONTE_SCURO * P
        for i in range(52):
            x = int(round(x_la0 + (i + 0.5) * passo))
            if x < 2 or x > w - 3:
                continue
            y0 = a0 + b0 * (x - xm)
            y_lim = min(h - 3, int(y0 + 1.9 * (a1 + b1 * (x - xm) - y0) / G.LB * G.LW))
            mig, y = None, max(0, int(y0))
            while y < y_lim:                                    # il tratto chiaro più lungo
                if g[y, x] > Tc:
                    s = y
                    while y < y_lim and g[y, x] > Tc:
                        y += 1
                    if mig is None or y - s > mig[1]:
                        mig = (s, y - s)
                else:
                    y += 1
            if mig is None or mig[1] < _FRONTE_MIN * G.LW * passo_y:
                continue                                        # mano o ombra: colonna scartata
            y_fronte = mig[0] + mig[1]
            if y_fronte < h - 3 and g[y_fronte + 2, x] <= Ts:
                punti.append((float(x), float(y_fronte)))        # stacco secco: è il rastrello
    if len(punti) < 20:
        return None
    xs = np.asarray([p[0] for p in punti], np.float64)
    ys = np.asarray([p[1] for p in punti], np.float64)
    b, a = np.polyfit(xs, ys, 1)
    # Seconda passata: le ombre delle mani allungano il tratto chiaro di qualche pixel (misurato
    # 8,5 px di dispersione sui fotogrammi con la mano appoggiata, contro 1,5-2,7 senza), quindi
    # si butta via quello che sta oltre 2,5 volte la dispersione e si rifà la retta. Il fronte è
    # una riga sola: se dopo la seconda passata resta disperso, la misura non vale e si dice None.
    scarto = float(np.percentile(np.abs(ys - (a + b * xs)), 90))
    if scarto > 0.35 * passo:
        return None
    tenuti = np.abs(ys - (a + b * xs)) <= 2.5 * scarto
    if tenuti.sum() >= 20:
        xs, ys = xs[tenuti], ys[tenuti]
        b, a = np.polyfit(xs, ys, 1)
        scarto = float(np.percentile(np.abs(ys - (a + b * xs)), 90))
        if scarto > 0.35 * passo:
            return None
    return float(a), float(b), int(len(xs)), scarto


def verticale_neri(campioni_video, banda, est):
    """Dove cominciano e dove FINISCONO i tasti neri, misurati su TUTTO il pezzo.

    La y della griglia è la geometria che `H_iniziale` sbaglia di più, e sbagliandola non si
    vede a occhio: su `2024-02-14_20-58-43` dà 17,4 px per larghezza di tasto contro i 33,7
    veri (dal metadata: bordo posteriore a y 356 a sinistra e 345 a destra, punte dei neri a
    486), cioè una griglia alta la META' dei tasti — i riquadri coprono solo la parte dietro di
    ogni tasto e le pressioni sulla parte davanti restano fuori. La causa è
    `_H_iniziale_classico`: la sua scala verticale viene dalla spaziatura dei neri trovati sulla
    prima riga, e su questa ripresa quella riga cade sulla testa dei neri, dove i run sono
    spezzati e la spaziatura misurata è metà di quella vera.

    Qui la scala verticale si MISURA, come la x. Per ogni tasto nero (il centro viene dagli
    estremi misurati: la fase del profilo su questa ripresa sbaglia di 20 px, vedi
    `tastiera_nel_video`) si guarda la colonna riga per riga e si tiene il run scuro largo
    quanto un nero che sta più vicino a quel centro: le stesse `_runs` di `H_profilo`, che
    distinguono i tasti dal mobile (sopra la tastiera il buio è largo come il fotogramma).
    Il primo e l'ultimo run così trovati, mediati sui fotogrammi (mani e tablet coprono qualche
    tasto in qualche fotogramma, non tutti in tutti), danno il bordo posteriore e le punte; le
    due rette danno anche l'inclinazione, che qui non è zero: il bordo posteriore scende di 11
    px da destra a sinistra (e le punte lo seguono).

    Ritorna dict(fondo=(a, b), punte=(a, b), x_riferimento, passo_y, chiavi) con
    y = a + b * (x - x_riferimento) in pixel del fotogramma, oppure None quando la misura non è
    credibile (pochi tasti letti, o una scala verticale fuori dal 0,5-1,7 del passo).

    Un limite da sapere: la scala esce dalle PUNTE DEI NERI, l'unico bordo netto della tastiera
    che si veda senza mani in mezzo, e il modello dei tasti dà ai neri il 66% della lunghezza del
    tasto (`griglia_prospettica.LB` su 6,2) mentre fra i pianoforti veri quel rapporto va dal 56%
    al 64%. Le punte dei neri finiscono al pixel giusto, quindi il FRONTE dei BIANCHI cade dove
    dice il modello, cioè corto del 6-18% (misurato: 7 px su `2024-02-14_20-58-43`, 25 px su
    `2024-03-17_18-54-44`): nel controllo i riquadri dei bianchi si fermano prima della punta del
    tasto e sembra che la griglia non li copra. Quel fronte ora si misura (`fronte_bianchi`) e
    `griglia_nel_ritaglio` lo passa ai disegni come `lw_fronte`: il ritaglio, la geometria del
    dataset e il verdetto restano quelli di prima, cambia solo fin dove arrivano i riquadri
    disegnati. Prima di questa misura sbagliava di 88 px il bordo POSTERIORE (la griglia si
    posava sulla cassa), quindi il cambio è comunque tutto guadagno.
    """
    x_la0, x_c8 = est["x_la0"], est["x_c8"]
    passo = (x_c8 - x_la0) / 52.0
    ya, yb = banda
    w = campioni_video[0][1].shape[1]
    h = campioni_video[0][1].shape[0]
    x_neri = [(x_la0 + (G.u_nero(n) - G.u_bianco(G.NOTA_MIN)) * passo, n) for n in G.NERI
              if x_la0 + 1.0 * passo <= x_la0 + (G.u_nero(n) - G.u_bianco(G.NOTA_MIN)) * passo
              <= x_c8 - 1.0 * passo]
    if len(x_neri) < 8:
        return None
    lo_run, hi_run = max(2.5, 0.004 * w), 0.075 * w
    righe = list(range(max(2, int(ya - 3.0 * passo)), min(h - 2, int(yb + 4.0 * passo)) + 1))
    tetti: dict[int, list[float]] = {}
    fondi: dict[int, list[float]] = {}
    misurati: dict[int, list[float]] = {}
    letti = 0
    for _t, f in campioni_video:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        T = G._soglia(g)
        centro = np.full((len(righe), w), np.nan, np.float32)
        for i, y in enumerate(righe):
            for a, b in G._runs(g[y] < T):
                if lo_run <= b - a <= hi_run:                # un tasto nero, non il mobile
                    centro[i, a:b] = (a + b) / 2.0
        for i_n, (xc, _n) in enumerate(x_neri):
            # il run del tasto: quello più vicino al centro che gli estremi gli danno. Sul bordo
            # sinistro la tastiera si vede un po' più larga di com'è nel piano dei tasti bianchi
            # (i neri sono rialzati: vedi `neri_verificati`), quindi il nero vero sta 8-10 px
            # fuori dal centro del modello e una colonna fissa cadrebbe sul suo bordo.
            i_x = int(round(xc))
            riga_nera = np.full(len(righe), np.nan, np.float32)
            for i in range(len(righe)):
                lo = max(0, i_x - int(_SCARTO_NERO * passo))
                hi = min(w, i_x + int(_SCARTO_NERO * passo) + 1)
                v = centro[i, lo:hi]
                buoni = np.where(~np.isnan(v))[0]
                if buoni.size:
                    j = buoni[np.argmin(np.abs(lo + buoni - xc))]
                    riga_nera[i] = lo + j
            idx = np.where(~np.isnan(riga_nera))[0]
            if idx.size < 4:
                continue
            pezzi = np.split(idx, np.where(np.diff(idx) > 3)[0] + 1)
            idx = max(pezzi, key=len)                       # un buco di 2 righe non spezza il nero
            if idx[-1] - idx[0] < 1.6 * passo:
                continue
            tetti.setdefault(i_n, []).append(float(righe[idx[0]]))
            fondi.setdefault(i_n, []).append(float(righe[idx[-1]]))
            misurati.setdefault(i_n, []).append(float(np.median(riga_nera[idx])))
        letti += 1
    chiavi = sorted(tetti)
    if letti < 3 or len(chiavi) < 8:
        return None
    xs = np.array([x_neri[i][0] for i in chiavi])
    a0, b0, xm = _retta(xs, np.array([float(np.median(tetti[i])) for i in chiavi]))
    a1, b1, _ = _retta(xs, np.array([float(np.median(fondi[i])) for i in chiavi]))
    passo_y = (a1 - a0) / G.LB
    if not (0.5 * passo <= passo_y <= 1.7 * passo):
        return None
    # Controllo finale sulla fascia trovata: dentro dev'esserci la tastiera, cioè neri scuri NEI
    # tasti neri e bianchi CHIARI fra loro. Le colonne sono quelle MISURATE (il run scuro trovato
    # tasto per tasto, non il centro del modello) e per i bianchi si guarda a METÀ fra due neri:
    # i neri rialzati si vedono spostati verso l'esterno anche di 15 px (vedi `neri_verificati`) e
    # con le colonne del modello il controllo scartava una misura giusta.
    idx_neri = sorted(int(round(float(np.median(misurati[i])))) for i in chiavi)
    idx_neri = [x for x in idx_neri if 0 <= x < w]
    idx_bianchi = [int(round(0.5 * (a + b))) for a, b in zip(idx_neri, idx_neri[1:])
                   if 0 <= 0.5 * (a + b) < w]
    ok_banda = 0
    for _t, f in campioni_video[:6]:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        T = G._soglia(g)
        for y in range(int(a0 + 0.35 * G.LB), int(a1 - 0.35 * G.LB) + 1, max(2, int(0.25 * passo))):
            if ((g[y, idx_neri] < T).mean() >= 0.6
                    and (g[y, idx_bianchi] > T).mean() >= 0.5):
                ok_banda += 1
        if ok_banda >= 3:
            break
    if ok_banda < 3:
        return None
    fronte = fronte_bianchi(campioni_video, x_la0, x_c8, (a0, b0), (a1, b1), xm, passo_y)
    return {"fondo": (a0, b0), "punte": (a1, b1), "x_riferimento": xm,
            "passo_y": float(passo_y), "chiavi": len(chiavi),
            "fronte": None if fronte is None else (fronte[0], fronte[1]),
            "fronte_letti": 0 if fronte is None else fronte[2],
            "fronte_scarto": None if fronte is None else round(float(fronte[3]), 1)}
_V_NERI = (1.0, 3.6)        # dentro i tasti neri (le punte sono a LB = 4,1)
_V_FRONTE = (4.5, 5.9)      # sotto le punte: fra un bianco e l'altro si vede la fessura
_CONTRASTO_FESSURA = 6.0    # livelli: una fessura meno netta di così non si distingue dal rumore
_FONDO_NERO = 0.30          # sotto questa frazione del bianco un run è un tasto nero, non ombra
_FESSURA_SCARTO = 0.50      # passi di tasto: dove si cerca la fessura attorno al bordo del modello
_NERO_SCARTO = 0.50         # passi di tasto: dove si cerca il run scuro del nero
_BORDI = [G.u_bianco(n) for n in G.BIANCHI] + [G.u_bianco(G.NOTA_MAX) + 1.0]


def _profilo_tastiera(grigio, y_da, y_a):
    """Profilo orizzontale MEDIATO sulle righe della banda, in pixel del fotogramma.

    Una riga sola è rumore: la fessura fra due tasti è un minimo largo un pixel e su una riga
    capita di non vederlo (misurato sull'esempio 9: su una riga le fessure si vedono a metà
    tasti, mediati su trenta righe si vedono sempre). Mediare in verticale non sposta la x: le
    fessure sono linee quasi verticali, il tasto no.
    """
    a = int(max(1, min(y_da, y_a)))
    b = int(min(grigio.shape[0] - 1, max(y_da, y_a)))
    if b - a < 4:
        return None
    riga = grigio[a:b].mean(axis=0).astype(np.float32)
    return np.convolve(riga, np.ones(3, np.float32) / 3, mode="same")


def _fessura_nel_profilo(profilo, x_modello, passo):
    """La fessura (il bordo fra due tasti bianchi) più vicina a `x_modello`: (x, contrasto).

    Il bordo è il minimo locale del profilo e il contrasto è la differenza fra il minimo e il
    livello dei bianchi ai due lati (`min` dei due lati: se da un lato c'è l'ombra di un nero,
    conta l'altro). Sotto i sei livelli non si accetta: su queste riprese le fessure ci sono
    sempre, ma con la tastiera in ombra il minimo è il rumore e ipotizzare è meglio che sbagliare.
    La finestra è di MEZZO tasto per lato: la griglia può sbagliare di mezzo tasto (è la deriva
    che si vuole misurare, 0,48 tasti sull'esempio 9) e la fessura più vicina è a un tasto intero,
    quindi mezza tasto non è ambiguo e con meno si perdono i bordi ai due capi.
    """
    lo = int(max(1, x_modello - _FESSURA_SCARTO * passo))
    hi = int(min(profilo.size - 1, x_modello + _FESSURA_SCARTO * passo))
    if hi - lo < 3:
        return None
    j = lo + int(np.argmin(profilo[lo:hi]))
    sinistra = float(np.median(profilo[lo:max(lo + 3, j - 2)])) if j - 2 > lo else float(profilo[j])
    destra = float(np.median(profilo[min(hi - 1, j + 3):hi])) if j + 3 < hi else float(profilo[j])
    contrasto = min(sinistra, destra) - float(profilo[j])
    return (float(j), contrasto) if contrasto >= _CONTRASTO_FESSURA else None


def _nero_nel_profilo(profilo, x_modello, passo):
    """Il run scuro che sta DENTRO il tasto nero che il modello mette a `x_modello`.

    Si tiene il run a soglia più vicino a `x_modello` (come `scale_dai_neri`, `verticale_neri` e
    `neri_verificati`: la stessa ricetta di tutto il resto) e si pretende che sia largo come un
    nero e DAVVERO scuro: un'ombra morbida sul fianco, la manica di una mano o il riflesso sul
    legno restano sopra la soglia. Il centro è il punto medio del run, che è quello che serve:
    qui non si misura la larghezza del tasto ma dove sta.
    """
    soglia = 0.45 * float(np.percentile(profilo, 90))            # livello dei tasti bianchi
    candidati = []
    for a, b in G._runs(profilo < soglia):
        if 0.45 * passo <= b - a <= 1.05 * passo:
            candidati.append((abs(0.5 * (a + b) - x_modello), a, b, float(profilo[a:b].min())))
    if not candidati:
        return None
    _scarto, a, b, fondo = min(candidati)
    if fondo > _FONDO_NERO * soglia / 0.45:                     # penombra, non un tasto nero
        return None
    return 0.5 * (a + b)


def misure_x_un_fotogramma(grigio, xm, ym, passo):
    """{u: x} dei tasti neri (centro) e delle fessure (bordo) visti in QUESTO fotogramma."""
    profilo_neri = _profilo_tastiera(grigio, ym(_V_NERI[0]), ym(_V_NERI[1]))
    profilo_fronte = _profilo_tastiera(grigio, ym(_V_FRONTE[0]), ym(_V_FRONTE[1]))
    neri, fessure = {}, {}
    if profilo_neri is not None:
        for n in G.NERI:
            trovato = _nero_nel_profilo(profilo_neri, xm(G.u_nero(n), 2.0), passo)
            if trovato is not None:
                neri[n] = trovato
    if profilo_fronte is not None:
        for u in _BORDI:
            trovato = _fessura_nel_profilo(profilo_fronte, xm(u, 5.2), passo)
            if trovato is not None:
                fessure[u] = trovato[0]
    return neri, fessure


def x_tasti_misurata(campioni_video, est, H, rect):
    """Dove stanno DAVVERO i tasti, uno per uno: dove si vedono si MISURA, dove sono coperti
    si IPOTIZZA dal vicinato.

    Perché serve. La x della griglia viene da `H_iniziale` o dagli estremi misurati, cioè da un
    modello con un passo e due capi: sulla ripresa dell'esempio 9 (`2024-02-15_20-07-54`, verità
    del dataset 120..1842) la griglia ancorata ai capi è giusta agli estremi e sbagliata in mezzo,
    e i riquadri dei neri finiscono a mezza chiave dal tasto vero: misurata sul pezzo, la distanza
    fra il centro del riquadro e il nero vero è 11,3 px di media e 19,5 px al peggio (un tasto è
    33,1 px, quindi mezzo tasto) — è la deriva che si vede a occhio, un do che cade sul do diesis.
    Una sola omografia non può correggerla (gli estremi devono restare fermi): serve una
    correzione che cambia da tasto a tasto, 27,8 px di escursione su questa ripresa, 0,84 tasti.

    Come si misura. Un tasto nero è un run scuro largo ~0,6 tasti: il suo centro è il punto medio
    di quel run. Un tasto bianco è delimitato da due fessure, e la fessura è il minimo del profilo
    orizzontale MEDIATO su trenta righe (su una riga sola si vede a metà tasti, vedi
    `_profilo_tastiera`). Si guarda sempre DENTRO la banda giusta: i neri fra v 1,0 e 3,6, le
    fessure sotto le punte fra v 4,5 e 5,9, con la scala y misurata da `verticale_neri`. Le due
    famiglie di misure si controllano a vicenda e concordano (sull'esempio 9: +4,5 px dalle
    fessure e +4,8 px dai neri sulla stessa ottava), quindi si usano entrambe come ancore.
    La scala y deve essere quella MISURATA: chi chiama passa la `H` che ha già passato
    `riga_y_misurata`, altrimenti le bande dei neri e delle fessure cadono fuori dai tasti.

    L'ipotesi. Le misure diventano un campo di correzione dx(u) (dx = misurato - modello): una
    cubica robusta dice quali misure sono COERENTI col vicinato — una mano sulla tastiera, una
    manica, un riflesso danno un run scuro che non è un tasto, e quei tasti si trattano come
    coperti — e il campo si riempie interpolando fra le misure buone. Provato togliendo una misura
    per volta: l'ipotesi dai vicini sbaglia 1,2 px di media e 2,8 px al peggio (0,08 tasti), quindi
    sotto una mano il riquadro resta sul tasto.

    Ritorna dict(nero={u: dx}, bordo={u: dx}, ug, dg, ...) oppure None quando le misure coerenti
    sono troppo poche per fidarsi (e allora la griglia resta quella di prima).
    """
    x1 = rect[0]
    passo = float(est["passo"])
    u0, u1 = G.u_bianco(G.NOTA_MIN), G.u_bianco(G.NOTA_MAX) + 1.0

    def xm(u, v):
        return float(G.proietta(H, [(float(u), float(v))])[0][0]) + x1          # pixel del video

    def ym(v):
        return float(G.proietta(H, [(0.0, float(v))])[0][1]) + rect[1]

    raccolta_n = {n: [] for n in G.NERI}
    raccolta_b = {u: [] for u in _BORDI}
    for _t, fotogramma in campioni_video:
        grigio = cv2.cvtColor(fotogramma, cv2.COLOR_BGR2GRAY)
        neri, fessure = misure_x_un_fotogramma(grigio, xm, ym, passo)
        for n, x in neri.items():
            raccolta_n[n].append(x)
        for u, x in fessure.items():
            raccolta_b[u].append(x)
    # le due estremità misurate della tastiera sono ancore forti con dx = 0: lì il modello è
    # ancorato alla misura (vedi `riancora_x`), quindi non si sposta niente
    anc = [(u0, 0.0, 3.0, "bordo"), (u1, 0.0, 3.0, "bordo")]
    for u, misure in raccolta_b.items():
        if len(misure) >= 3 and _concordi(misure, passo):
            anc.append((u, float(np.median(misure)) - xm(u, 5.2), 2.0, "bordo"))
    for n, misure in raccolta_n.items():
        if len(misure) >= 3 and _concordi(misure, passo):
            anc.append((G.u_nero(n), float(np.median(misure)) - xm(G.u_nero(n), 2.0), 1.5, "nero"))
    if len(anc) < 12:
        return None
    anc.sort()
    uc = 0.5 * (u0 + u1)
    coef = _cubica_di_consenso(anc, uc)
    tolleranza = max(4.0, 0.12 * passo)
    buoni = [a for a in anc if abs(a[1] - float(np.polyval(coef, (a[0] - uc) / 10.0))) <= tolleranza]
    if len(buoni) < 10:
        return None
    ug = np.arange(u0, u1 + 1e-9, 0.25)
    dg = np.interp(ug, [a[0] for a in buoni], [a[1] for a in buoni])    # fra due misure: retta
    dg = np.convolve(np.pad(dg, 2, mode="edge"), np.ones(5) / 5, mode="valid")  # niente zigzag
    escursione = float(np.max(dg) - np.min(dg))
    return {"nero": {a[0]: a[1] for a in buoni if a[3] == "nero"},
            "bordo": {a[0]: a[1] for a in buoni if a[3] == "bordo"},
            "ug": ug, "dg": dg, "misurati": len(buoni), "provati": len(anc),
            "incoerenti": len(anc) - len(buoni),
            "ipotizzati": max(0, len(G.NERI) + len(_BORDI) - len(buoni)),
            "escursione": escursione,
            "tasti": int(round(escursione / passo)) if passo > 0 else 0}




def _retta(x, y):
    """(a, b, x_medio) della retta y = a + b * (x - x_medio) che passa per i punti, robusta.

    Tre passaggi di minimi quadrati scartando chi resta a più di 3 scarti assoluti (una mano
    che copre un tasto per tutto il pezzo dà un bordo posteriore sbagliato lì).
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    coef = np.zeros(2)
    for _ in range(3):
        A = np.vstack([np.ones_like(x), x - x.mean()]).T
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        res = y - A @ coef
        scarto = 1.4826 * float(np.median(np.abs(res - np.median(res)))) + 1e-6
        tieni = np.abs(res - np.median(res)) < 3.0 * scarto
        if tieni.all() or tieni.sum() < 4:
            break
        x, y = x[tieni], y[tieni]
    return float(coef[0]), float(coef[1]), float(x.mean())


def _concordi(misure, passo):
    """I fotogrammi dicono la stessa cosa? (camera ferma e tasto non coperto a metà)

    Sull'esempio 9 le misure dello stesso tasto distano fra loro 2,2 px di scarto assoluto medio;
    una mano che passa ne sposta qualcuna di mezzo tasto. Se i fotogrammi non concordano quel tasto
    non si misura: si ipotizza. (Una camera che si muove è un caso che Passo 0 non copre:
    `--traccia` esiste per quello, e lì le misure di fotogrammi diversi non sono confrontabili.)
    """
    m = np.asarray(misure, dtype=float)
    mad = 1.4826 * float(np.median(np.abs(m - np.median(m))))
    return mad <= 0.25 * passo


def _cubica_di_consenso(ancore, uc, ripetizioni=600):
    """Cubica robusta (RANSAC) sulle ancore: serve a riconoscere le misure INCOERENTI.

    Quattro misure quasi sullo stesso tasto non vincolano niente (la cubica esploderebbe), e una
    misura di una mano o di un riflesso non deve piegare la griglia: si cerca il consenso più largo
    entro 4 px e poi si rifinisce su quello.
    """
    u = (np.array([a[0] for a in ancore], float) - uc) / 10.0
    d = np.array([a[1] for a in ancore], float)
    pesi = np.array([a[2] for a in ancore], float)
    if u.size < 5:
        return np.polyfit(u, d, max(1, u.size - 1), w=np.sqrt(pesi))
    rng = np.random.default_rng(7)
    migliore = None
    for _ in range(ripetizioni):
        idx = np.sort(rng.choice(u.size, 4, replace=False))
        if np.ptp(u[idx]) < 0.4:                 # quattro misure quasi sullo stesso tasto: non
            continue                             # vincolano niente e la cubica esploderebbe
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")      # polyfit avvisa quando i punti sono allineati
            c = np.polyfit(u[idx], d[idx], 3)
        r = np.abs(d - np.polyval(c, u))
        dentro = r <= 4.0
        n = int(dentro.sum())
        medio = float(r[dentro].mean()) if n else 1e9
        if migliore is None or (n, -medio) > (migliore[0], -migliore[1]):
            migliore = (n, medio, c)
    c = migliore[2]
    for _ in range(3):
        r = np.abs(d - np.polyval(c, u))
        tenere = r <= 4.0
        if int(tenere.sum()) < 5:
            break
        c = np.polyfit(u[tenere], d[tenere], 3, w=np.sqrt(pesi[tenere]))
    return c


def dx_del_tasto(x_tasti, genere, u):
    """La correzione della x per un bordo (`bordo`) o il centro di un tasto nero (`nero`).

    La misura di QUEL bordo/tasto se c'è, altrimenti l'ipotesi: il campo interpolato fra le misure
    vicine. È la regola del passo 0: dove il tasto si vede la sagoma combacia con quello trovato,
    dove è coperto si ipotizza dove sta.
    """
    if not x_tasti:
        return 0.0
    misure = x_tasti.get(genere) or {}
    if misure:
        vicino = min(misure, key=lambda k: abs(k - u))
        if abs(vicino - u) <= 0.25:
            return float(misure[vicino])
    return float(np.interp(float(u), x_tasti["ug"], x_tasti["dg"]))


def H_dagli_estremi(estremi, rect, y_back, s_y):
    """Omografia LOCALE al ritaglio, ancorata agli estremi misurati su tutto il video.

    u = 0 è il bordo sinistro di DO4, che sta 23 tasti bianchi dopo il bordo di LA0: qui LA0
    è dove comincia la fascia chiara, non dove lo metterebbe il centro della finestra, quindi
    non c'è nessuna ottava da indovinare e nessun tasto del modello fuori dalla tastiera. La
    riga di fondo e la scala verticale vengono dal profilo (`H_profilo`, che quelle le misura
    bene: il suo errore è tutto in x).
    """
    s = estremi["passo"]
    x_c4 = estremi["x_la0"] - G.u_bianco(G.NOTA_MIN) * s        # u_bianco(LA0) = -23
    return np.float64([[s, 0.0, x_c4 - rect[0]],
                       [0.0, s_y, y_back - rect[1]],
                       [0.0, 0.0, 1.0]])


def riga_y_misurata(H, verticale, rect):
    """L'omografia con la riga della y presa dalla MISURA (`verticale_neri`), non da affina.

    La x resta quella di `H` (ritaglio, estremi, affinamento): qui si sostituisce solo la y,
    perché il fondo dei tasti e le punte dei neri si vedono nell'immagine e non c'è niente da
    indovinare. `affina` e `H_iniziale` hanno una y sola per tutti i ritagli e su questa
    ripresa l'avevano alta la metà (vedi `verticale_neri`), quindi va rifatta DOPO di loro.

    L'inclinazione è la media fra quella del fondo e quella delle punte (una rotazione della
    camera le inclina uguali): senza, il bordo posteriore resta orizzontale mentre nell'immagine
    scende di 11 px da destra a sinistra.
    """
    x1, y1 = int(rect[0]), int(rect[1])
    xm = verticale["x_riferimento"]
    a0, b0 = verticale["fondo"]
    a1, b1 = verticale["punte"]
    x_c = float(G.proietta(H, [(0.0, 0.0)])[0][0]) + x1        # la x di u=0 (centro tastiera)
    y_fondo = a0 + b0 * (x_c - xm)
    s_y = ((a1 + b1 * (x_c - xm)) - y_fondo) / G.LB
    incl = 0.5 * (b0 + b1)
    H2 = np.array(H, dtype=float, copy=True)
    # y_locale(u, v) = fondo + incl * (x_locale(u) - x_c) + s_y * v, con x_locale ≈ h00*u + h02
    H2[1, :] = [incl * float(H[0, 0]), s_y,
                (y_fondo - y1) - incl * (x_c - x1) + incl * float(H[0, 2])]
    return H2


def lw_al_fronte(verticale, rect, larghezza):
    """Quanto è lungo un tasto bianco VERO, in unità del modello (il fronte misurato).

    E' il numero che serve ai disegni: i neri restano a `G.LB` (le loro punte sono la misura
    della scala verticale), i bianchi arrivano a `lw_fronte` invece che a `G.LW`. Si legge al
    centro del ritaglio, dove i pixel sono tanti e le due rette del fronte e del fondo valgono
    per tutto il fotogramma. Si tiene solo se sta fra 0,9 e 1,35 volte il modello: fuori di lì
    non è un fronte (misurato: 6,41 su `2024-02-14_20-58-43` e 7,09 su `2024-03-17_18-54-44`,
    contro il 6,2 del modello), quindi si resta alla geometria di sempre.

    Non sposta il ritaglio, il verdetto né la geometria del dataset (`griglia.json`): dice solo
    fin dove si disegnano i riquadri bianchi nel controllo e nel video della griglia.
    """
    fronte = (verticale or {}).get("fronte")
    if not fronte:
        return None
    xc = 0.5 * (int(rect[0]) + int(rect[0]) + int(larghezza))
    xm = verticale["x_riferimento"]
    y_fondo = verticale["fondo"][0] + verticale["fondo"][1] * (xc - xm)
    y_fronte = fronte[0] + fronte[1] * (xc - xm)
    lw = (y_fronte - y_fondo) / verticale["passo_y"]
    if not 0.9 * G.LW <= lw <= 1.35 * G.LW:
        return None
    return round(float(lw), 2)


def riancora_x(H, estremi, rect):
    """Rimette la x dove dicono gli estremi misurati.

    `affina` è bravo sulla prospettiva ma sposta un po' il passo (misurato: da 33,15 a 33,43
    px, +0,9%): qui si applica una scala in x che riporta i bordi di LA0 e DO8 esattamente
    sulle colonne misurate su tutto il video, senza toccare la y. La x è l'unica cosa che
    sposta le note di un tasto, e quella la sa la misura, non l'affinamento.
    """
    a = float(G.proietta(H, [(G.u_bianco(G.NOTA_MIN), 0.0)])[0][0])
    b = float(G.proietta(H, [(G.u_bianco(G.NOTA_MAX) + 1.0, 0.0)])[0][0])
    x_la0, x_c8 = estremi["x_la0"] - rect[0], estremi["x_c8"] - rect[0]
    if b - a < 1.0:
        return H
    k = (x_c8 - x_la0) / (b - a)
    T = np.float64([[k, 0.0, x_la0 - k * a], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    return np.float64(T @ H)


def neri_verificati(ritaglio, H, estremi, x1=0, x_tasti=None):
    """Tasti neri del modello che hanno DAVVERO un nero scuro al posto giusto.

    Quando l'ancoraggio sbaglia, i riquadri dei neri cadono sul vestito, sul tablet o sul
    mobile: è il difetto più evidente a occhio (e il più rovinoso per le note). Qui si guarda
    una riga dentro la banda dei neri e per ogni tasto nero del modello si decide se c'è un
    nero scuro dove dice la griglia, se lì non si è mai visto niente (mani o tablet: il tasto
    c'è lo stesso, e la griglia va disegnata lo stesso) o se invece il posto è scoperto e vuoto
    (la griglia è spostata). Si contano a parte i neri scuri che nessun tasto del modello
    spiega: sono i falsi (riflessi, mobile, feltro) e crescono quando la griglia scivola.

    Con `x_tasti` (la misura tasto per tasto di `x_tasti_misurata`) la x di ogni nero è quella
    MISURATA su tutto il pezzo dove c'è, e ipotizzata dove il tasto è coperto: i riquadri dei
    neri si spostano di quella correzione, quindi il conto dice la verità anche quando la griglia
    uniforme sbaglia di mezzo tasto (sull'esempio 9: da 11,3 px di scarto a 0,9).

    Ritorna dict(neri_ok, neri_mancanti, neri_coperti, neri_in_piu, neri_mancanti_note).
    """
    g = cv2.cvtColor(ritaglio, cv2.COLOR_BGR2GRAY)
    h, w = g.shape[:2]
    T = G._soglia(g)
    passo = estremi["passo"]
    lo, hi = max(2.5, 0.004 * w), 0.075 * w
    righe = []
    for v in (1.1, 2.0, 2.9):                      # dentro i neri, lontano dalle punte
        y = int(round(float(G.proietta(H, [(0.0, v)])[0][1])))
        if 1 <= y < h - 1:
            pezzi = [(a, b) for a, b in G._runs(g[y] < T) if lo <= b - a <= hi]
            righe.append(([(a + b) / 2.0 for a, b in pezzi],
                          [(a, b) for a, b in G._runs(g[y] < T) if b - a > 1.2 * passo]))
    if not righe:
        return {}
    esito = {"ok": [], "mancante": [], "coperto": []}
    for n in G.NERI:
        u = G.u_nero(n)
        x = float(G.proietta(H, [(u, 1.0)])[0][0]) + dx_del_tasto(x_tasti, "nero", u)
        xf = x + x1
        i0, i1 = int(xf - 0.35 * passo), int(xf + 0.35 * passo)
        visto_li = bool(estremi["visto"][max(0, i0):max(0, i1)].any())
        voti = []
        for centri, larghi in righe:
            if any(abs(c - x) < 0.35 * passo for c in centri):
                voti.append("ok")
            elif any(a <= x <= b for a, b in larghi):
                voti.append("coperto")          # un dito, una manica, un tablet: non un tasto nero
            elif not visto_li:
                voti.append("coperto")          # lì non si è mai visto niente
            else:
                voti.append("mancante")
        esito["ok" if "ok" in voti else
              ("coperto" if all(v == "coperto" for v in voti) else "mancante")].append(G.nome(n))
    in_piu = 0
    for centri, _larghi in righe:
        spiegano = [False] * len(centri)
        for n in G.NERI:
            u = G.u_nero(n)
            x = float(G.proietta(H, [(u, 1.0)])[0][0]) + dx_del_tasto(x_tasti, "nero", u)
            for i, c in enumerate(centri):
                if abs(c - x) < 0.35 * passo:
                    spiegano[i] = True
        in_piu = max(in_piu, sum(1 for i, c in enumerate(centri) if not spiegano[i]
                                 and estremi["x_la0"] <= c + x1 <= estremi["x_c8"]))
    return {"neri_ok": len(esito["ok"]), "neri_mancanti": len(esito["mancante"]),
            "neri_coperti": len(esito["coperto"]), "neri_in_piu": int(in_piu),
            "neri_mancanti_note": esito["mancante"]}


def candidati_auto(frame, margine, fondo, video=None, inizio=0.0, durata=0.0):
    """I rettangoli candidati ricavati dallo stadio del profilo (nessun detector).

    `passo_profilo` dice dove stanno i TASTI NERI (una banda di righe) e quanto è largo un tasto;
    da lì la tastiera è quella banda più il corpo dei tasti bianchi verso il fronte
    (`--margine`/`--fondo`). I candidati sono, nell'ordine: la larghezza intera, la striscia
    della fase del profilo (fase + 53 tasti), la striscia della tastiera misurata sui neri
    (bordo di LA0 + 52 tasti bianchi, vedi `tastiera_dai_neri`) e — quando si conosce il video,
    non solo il fotogramma — la tastiera INTERA misurata su tutto il pezzo (`estremi`, vedi
    `tastiera_nel_video`).

    Nessuno degli altri vince sempre, per questo si provano tutti (vedi la docstring del modulo
    per le misure): l'intero sbaglia l'ottava, la striscia dei neri sbaglia quando
    `_H_iniziale_classico` parte dal gruppo di neri sbagliato, la fase del profilo sbaglia quando
    il margine di cassa dentro al fotogramma è grande. La scelta la fa `verdetto` (che guarda i
    tasti del modello fuori dal ritaglio, i tasti fuori dalla TASTIERA misurata e i neri
    verificati uno per uno), non gli inlier; "neri" e "estremi" entrano in gioco solo se sono
    "ok" (vedi `main`). Ritorna [(rettangolo, info)] con "intero" prima e "estremi" ultimo.
    """
    h, w = frame.shape[:2]
    p = G.passo_profilo(frame)
    if p is None:
        sys.exit("[!] in questo video non trovo nessuna periodicità di tasti (profilo NCC "
                 "fallito): guarda un fotogramma e passa --rettangolo x1,y1,x2,y2")
    s, fase, ncc, ya, yb = p
    # La banda e la scala dei neri VERI, quando il profilo non legge (NCC sotto `_NCC_PROFILO_MIN`:
    # tastiera obliqua, il profilo di colonne spalma un nero sull'altro): il passo del profilo li'
    # non e' una misura -- misurato sul video 18 del dataset (2024-02-15_21-40-43): 166,17 px contro
    # 34,33 veri. Servono a misurare la tastiera su tutto il pezzo (`estremi`) e, se quella misura
    # c'e', a ritagliare sulla sola fascia dei tasti (vedi sotto).
    b_neri = banda_dai_neri(frame) if ncc < _NCC_PROFILO_MIN else None
    if b_neri is not None:
        s_v, ya_v = b_neri
        yb_v = ya_v + G.LB * s_v
    else:
        s_v, ya_v, yb_v = s, ya, yb
    info = {"metodo": "auto", "passo_profilo": round(float(s), 2), "fase": round(float(fase), 1),
            "ncc": round(float(ncc), 3), "banda_neri": [int(ya_v), int(yb_v)]}
    if b_neri is not None:
        info["banda_dai_neri"] = {"passo": round(s_v, 2), "y_inizio": round(ya_v, 1),
                                  "perche": "il profilo non legge (NCC sotto "
                                            f"{_NCC_PROFILO_MIN}): passo e banda dai neri"}
    # Con quale passo si misura la tastiera su tutto il pezzo. Quello del profilo quando il profilo
    # legge. Quando NON legge il suo passo non e' una misura e su questo video vale 76,4 px contro
    # 10,2 veri: `tastiera_nel_video` con quella scala cercava la fascia dei bianchi 280 px sotto i
    # tasti e non la trovava, quindi non c'era nessun `estremi` -- e senza `estremi` la x della
    # griglia resta quella del centro della finestra (`H_iniziale`), che qui cade 7 tasti a destra.
    # La scala dei neri veri c'e' lo stesso (`banda_dai_neri`).
    campioni_video = campioni(video, inizio, durata) if video is not None else None
    est, vert = None, None
    if campioni_video:
        info["_campioni"] = campioni_video                  # servono anche alla x tasto per tasto
        p_est = (s_v, fase, ncc, ya_v, yb_v) if b_neri is not None else p
        est = tastiera_nel_video(p_est, campioni_video)
        if est is not None and est["tasti"] == 52:          # un pianoforte intero: LA0..DO8
            # La y della griglia: fondo dei tasti e punte dei neri, misurati su tutto il pezzo
            # (vedi `verticale_neri`). Senza, `H_iniziale` la sbaglia della metà su questa ripresa
            # e i riquadri coprono solo la parte dietro dei tasti.
            vert = verticale_neri(campioni_video, (ya_v, yb_v), est)
    # Il ritaglio, in verticale: la sola fascia dei tasti quando la tastiera e' stata MISURATA su
    # tutto il pezzo (`estremi`) E la verticale e' misurata (`verticale`), perche' da li' in poi la
    # griglia si ancora a quelle misure e si puo' ritagliare stretto senza perdere niente; il
    # ritaglio di sempre (scala del profilo) in ogni altro caso. Il ritaglio stretto NON si prende
    # senza le due misure: li' la griglia la deve ancora indovinare `H_iniziale`, e dentro una fascia
    # alta due tasti resta senza contesto e aggancia un'armonica -- misurato sul video 18 su 3 s:
    # "intero" dava passo 164,59 px (= 5x i 33,1 veri) con 0 inlier, cioe' "rifiuto", mentre con la
    # scala del profilo (166,17 px, sbagliata ma larga) la stessa griglia usciva "incerto" (passo
    # 35,14 px, 46 inlier). Quando il profilo legge `b_neri` non c'e' e questo ramo da' esattamente
    # il ritaglio di sempre.
    if est is not None and est["tasti"] == 52 and vert is not None:
        y1 = max(0, int(round(ya_v - margine * s_v)))
        y2 = min(h, int(round(ya_v + fondo * s_v)))
    else:
        y1 = max(0, int(round(ya - margine * s)))
        y2 = min(h, int(round(ya + fondo * s)))
    prove = [("intero", (0, y1, w, y2)),
             ("profilo", (max(0, int(round(fase - s))), y1, min(w, int(round(fase + 53 * s))), y2))]
    anc = tastiera_dai_neri(frame[y1:y2])
    if anc is not None:
        m = 0.15 * anc[1]                                # un filo di margine, per non tagliare LA0
        prove.append(("neri", (max(0, int(round(anc[0] - m))), y1,
                               min(w, int(round(anc[0] + 52 * anc[1] + m))), y2)))
        info["bordo_la0"] = round(anc[0], 1)
    if est is not None and est["tasti"] == 52:            # un pianoforte intero: LA0..DO8
        info["estremi"] = {k: round(est[k], 2) for k in ("x_la0", "x_c8", "passo", "copertura")}
        info["estremi"].update(tasti=est["tasti"], campioni=est["campioni"],
                               neri_misurati=est["neri_misurati"])
        info["_estremi"] = est                             # con la maschera "visto": si toglie
        m = 0.15 * est["passo"]                            # prima di scrivere il json
        prove.append(("estremi", (max(0, int(round(est["x_la0"] - m))), y1,
                                  min(w, int(round(est["x_c8"] + m))), y2)))
        if vert is not None:
            info["_verticale"] = vert
            info["verticale"] = {
                "fondo_tasti": round(vert["fondo"][0], 1), "inclinazione_fondo": round(vert["fondo"][1], 5),
                "punte_neri": round(vert["punte"][0], 1), "inclinazione_punte": round(vert["punte"][1], 5),
                "passo_y": round(vert["passo_y"], 2), "chiavi": vert["chiavi"]}
    visti, fuori = set(), []
    for tag, r in prove:
        r = _pari(r)
        if r in visti or r[2] - r[0] < 200:
            continue
        visti.add(r)
        fuori.append((r, dict(info, ritaglio=tag, ancora=(tag == "estremi"))))
    return fuori


def rettangolo_manuale(testo, w, h):
    """Rettangolo dato a mano, in pixel del video originale: x1,y1,x2,y2."""
    try:
        x1, y1, x2, y2 = (int(round(float(v))) for v in testo.replace(" ", "").split(","))
    except ValueError:
        sys.exit("[!] --rettangolo vuole quattro numeri: x1,y1,x2,y2 (pixel del video)")
    x1, x2 = max(0, min(x1, x2)), min(w, max(x1, x2))
    y1, y2 = max(0, min(y1, y2)), min(h, max(y1, y2))
    if x2 - x1 < 100 or y2 - y1 < 40:
        sys.exit(f"[!] --rettangolo troppo piccolo ({x2 - x1}x{y2 - y1} px): la tastiera non ci sta")
    return (x1, y1, x2, y2), {"metodo": "rettangolo"}


def rettangolo_pianovam(dataset, rec, margine):
    """Gli angoli della tastiera da `metadata.json` di PianoVAM: è la verità, non una stima."""
    meta = json.load(open(dataset / "metadata.json", encoding="utf-8"))
    voce = next((v for v in meta.values() if v.get("record_time") == rec), None)
    if voce is None:
        sys.exit(f"[!] '{rec}' non è in {dataset / 'metadata.json'}")
    punti = []
    for chiave in ("Point_LT", "Point_RT", "Point_RB", "Point_LB"):
        x, y = (float(t) for t in str(voce[chiave]).split(","))
        punti.append([x, y])
    rect = (int(min(x for x, _ in punti)) - margine, int(min(y for _, y in punti)) - margine,
            int(max(x for x, _ in punti)) + margine, int(max(y for _, y in punti)) + margine)
    info = {"metodo": "pianovam", "rec": rec, "angoli": punti, "margine_px": margine}
    return rect, info


def griglia_nel_ritaglio(frame, rect, ancora=False, estremi=None, verticale=None,
                         campioni_video=None):
    """La griglia che il motore troverebbe DENTRO il ritaglio, coi numeri per fidarsi o no.

    `tasti_fuori` conta i tasti del modello (LA0..DO8) che cadono oltre i bordi del ritaglio:
    quando il ritaglio È la tastiera (i candidati "neri" ed "estremi") allora sono tasti
    disegnati sulla cassa, cioè il difetto da vedere subito; sull'intero fotogramma il numero
    include anche il margine di cassa che c'è per forza e va letto per quello che è.

    Con `ancora=True` (il candidato "estremi") la griglia NON si fa indovinare al motore: la x
    viene dagli estremi misurati su tutto il video (`H_dagli_estremi`, nessuna ottava da
    indovinare) e la y da `verticale` quando c'è (il fondo dei tasti e le punte dei neri misurati
    su tutto il pezzo, vedi `verticale_neri`), altrimenti dal ritaglio stesso, perché `H_profilo`
    la riga di fondo dei tasti la sbaglia quando sopra la tastiera c'è il mobile scuro del
    pianoforte (misurato sull'esempio 7: y=87 invece di 342, cioè una griglia disegnata 255 px
    troppo in alto). Poi `affina` rimette a posto la prospettiva coi neri veri, come per tutti gli
    altri candidati, e infine la y misurata si riscrive (`riga_y_misurata`).
    Il passo che esce da qui è la MEDIA sui tasti del modello: con la griglia ancorata i due capi
    stanno sulla misura e l'affinamento può piegare un po' l'interno, quindi la derivata in x al
    centro della tastiera non è più il numero da confrontare col profilo.

    Con `estremi` (la tastiera misurata su tutto il video, vedi `tastiera_nel_video`) si
    aggiungono i due numeri che dicono la verità a colpo d'occhio: `tasti_fuori_dalla_tastiera`
    (quanti tasti del modello la griglia mette fuori dalla tastiera vera) e i neri verificati
    uno per uno (`neri_ok`, `neri_mancanti`, `neri_coperti`, `neri_in_piu`).

    Con `campioni_video` (i fotogrammi sparsi su tutto il pezzo) si misura anche dove sta OGNI
    tasto — i neri dal loro run scuro, i bianchi dalle loro fessure — e si tira fuori la
    correzione tasto per tasto (`x_tasti`: dove il tasto si vede la sagoma combacia con quello
    trovato, dove è coperto si ipotizza dal vicinato, vedi `x_tasti_misurata`). I neri verificati
    qui sopra sono contati con quella correzione, e l'immagine di controllo la disegna: è la
    differenza fra una griglia che in mezzo alla tastiera sbaglia di mezzo tasto e una che sta
    sui tasti. La correzione NON sposta il ritaglio né il verdetto: cambia quello che si vede.
    """
    x1, y1, x2, y2 = rect
    r = frame[y1:y2, x1:x2]
    g = cv2.cvtColor(r, cv2.COLOR_BGR2GRAY)
    Hi = np.asarray(G.H_iniziale(r), dtype=float)
    if ancora and estremi is not None:
        H0 = H_dagli_estremi(estremi, rect, float(Hi[1, 2]) + y1, float(Hi[1, 1]))
        if verticale is not None:
            # La y di `H_iniziale` su un ritaglio STRETTO non è affidabile: sul video 18 del
            # dataset (2024-02-15_21-40-43) il profilo interno aggancia un'armonica e restituisce
            # un passo verticale di 132,6 px (= 4× i 33,1 veri), la griglia esce alta il quadruplo
            # e `affina` non trova nemmeno un nero (0 inlier) — da lì il verdetto "rifiuto" su un
            # ritaglio che i tasti li contiene. La y misurata su tutto il pezzo (`verticale_neri`)
            # c'è lo stesso, e `riga_y_misurata` la scrive comunque DOPO `affina`: scriverla anche
            # PRIMA (quando c'è) fa cadere le righe che `affina` campiona dentro i tasti neri VERI
            # invece che su una scala sbagliata. La x non ne soffre: per il candidato ancorato
            # `riancora_x` la riporta comunque sugli estremi misurati.
            H0 = riga_y_misurata(H0, verticale, rect)
        Hf, k = G.affina(g, np.float64(H0), G.rosso(r), 3)
        H = riancora_x(Hf, estremi, rect) if k >= 10 else H0
    else:
        H0 = Hi
        H = H0
        _, k = G.affina(g, np.float64(H), G.rosso(r), 3)
    if verticale is not None:
        # La y VERA (fondo dei tasti e punte dei neri misurati su tutto il pezzo) si riscrive DOPO
        # affina, che la sua la prende da `H_iniziale` e su queste riprese la sbaglia della metà
        # (vedi `verticale_neri`). Per il candidato ancorato la si è già scritta PRIMA (vedi sopra)
        # perché lì `H_iniziale` può sbagliarla di tutta un'armonica; sugli altri la si lascia dopo,
        # come sempre: le righe che affina campiona per cercare i neri cadono dentro i tasti neri
        # lo stesso (v 0,45-3,75 su una scala sbagliata resta dentro un tasto alto il doppio),
        # quindi la x che ne esce è quella di sempre e non va rimescolata.
        H = riga_y_misurata(H, verticale, rect)
    passo = float(np.hypot(H[0, 0], H[1, 0]))
    xa = float(G.proietta(H, [(G.u_bianco(G.NOTA_MIN), 0.0)])[0][0])            # bordo di LA0
    xd = float(G.proietta(H, [(G.u_bianco(G.NOTA_MAX) + 1.0, 0.0)])[0][0])     # fine di DO8
    # Il passo che conta è la MEDIA sui tasti del modello (span/52), non la derivata in x al
    # centro della tastiera: con la griglia ancorata agli estremi i due capi sono fissi sulla
    # misura e l'affinamento può piegare un po' l'interno (misurato sull'altro pezzo dell'utente:
    # derivata 31,72 px contro 32,17 di media, la verità 32,19). Con una griglia affine i due
    # numeri coincidono, quindi questo non cambia niente per gli altri candidati.
    passo_medio = (xd - xa) / (G.u_bianco(G.NOTA_MAX) + 1.0 - G.u_bianco(G.NOTA_MIN))
    if ancora:
        passo = passo_medio
    fuori = (max(0.0, -xa) + max(0.0, xd - r.shape[1])) / passo
    info = {"H": H, "inlier": int(k), "passo": passo, "evidenza": evidenza_giusta(g, H, G._soglia(g)),
            "tasti_nel_frame": round(r.shape[1] / passo, 1), "tasti_fuori": round(fuori, 1),
            "passo_medio": passo_medio}
    if estremi is not None:
        info["ancorata"] = bool(ancora)
        info["bordo_tastiera"] = [round(float(estremi["x_la0"]), 1), round(float(estremi["x_c8"]), 1)]
        fuori_t = (max(0.0, estremi["x_la0"] - (xa + x1))
                   + max(0.0, (xd + x1) - estremi["x_c8"])) / passo
        info["tasti_fuori_dalla_tastiera"] = round(fuori_t, 2)
        # La x tasto per tasto: la misura su tutto il pezzo (dove il tasto si vede) e l'ipotesi
        # dal vicinato (dove è coperto). Non muove il ritaglio né il verdetto: serve a disegnare
        # i riquadri sui tasti (vedi `x_tasti_misurata` e `immagine_controllo`).
        x_tasti = (x_tasti_misurata(campioni_video, estremi, H, rect)
                   if campioni_video and verticale is not None else None)
        if x_tasti is not None:
            info["_x_tasti"] = x_tasti
            info["tasti_misurati"] = {
                "misurati": x_tasti["misurati"], "incoerenti": x_tasti["incoerenti"],
                "ipotizzati": x_tasti["ipotizzati"], "escursione_tasti": x_tasti["tasti"],
                "neri": len(x_tasti["nero"]), "bordi": len(x_tasti["bordo"])}
        info.update(neri_verificati(r, H, estremi, x1, x_tasti))
    # Il fronte dei tasti BIANCHI misurato (`fronte_bianchi`): il modello lo mette a v=LW=6,2,
    # che fra i pianoforti veri è corto del 6-18%, e nel controllo i riquadri dei bianchi si
    # fermano a metà tasto. Non sposta né il ritaglio né il verdetto: dice ai disegni (controllo
    # e video della griglia) fin dove arrivano davvero i tasti.
    info["lw_fronte"] = lw_al_fronte(verticale, rect, x2 - x1)
    return info


_NCC_PROFILO_MIN = 0.45     # sotto questa NCC il passo del profilo non è una prova (vedi `verdetto`)


def verdetto(info, passo_profilo, ncc_profilo=None, auto=True):
    """ok / incerto / rifiuto, con la ragione: meglio fermarsi che addestrare su una griglia sbagliata.

    Soglie misurate sulle registrazioni PianoVAM, dove il passo vero (angoli nel metadata del
    dataset) è 33,12 px in tutte: il profilo lo stima entro l'1-2%, quindi uno scarto sotto il 3%
    è rumore, fra il 3% e il 6% è "guardala a occhio", oltre il 6% la griglia è sbagliata
    (trovato: 35,9 px = +8% e i tasti si contano uno ogni due verso i bordi).

    Il confronto col profilo vale finché i tasti neri sono VERTICALI nell'immagine: su una ripresa
    ruotata il profilo di colonne spalma ogni nero su quelli vicini e la periodicità che ne esce è
    sbagliata di un fattore intero. Misurato sul primo fotogramma di `video5906842636420915152`
    (tastiera obliqua, ~10 px per tasto misurati uno per uno sui neri: scarti 11,5 / 12,5 / 18,5 px
    = 1,12 / 1,2 / 1,78 del passo vero): `passo_profilo` dice 76,4 px — cioè 11 tasti bianchi nel
    fotogramma, mentre la tastiera intera (52) si vede tutta — con NCC 0,372, la più bassa delle 33
    registrazioni in `web_runs/_prepara` (14 PianoVAM 0,455-0,613 e il primo piano dell'utente
    0,89, tutte col passo giusto). Per questo `ncc_profilo` è un argomento: sotto
    `_NCC_PROFILO_MIN` (0,45) uno scarto grande non è più "rifiuto" ma "incerto", perché lì il
    profilo non è una prova e a decidere resta quello che la griglia ha dalla sua (gli inlier sui
    neri, la plausibilità, i tasti fuori).

    La finestra dei tasti (solo per il ritaglio automatico, `auto=True`: col rettangolo a mano
    comanda l'utente) è quella della tastiera intera, 52 tasti bianchi, e vale per le finestre che
    una tastiera la possono contenere (52 tasti o più): misurato 59,2 quando la finestra era più
    larga della tastiera e la griglia scivolava di 2 tasti, quei 7 tasti di troppo erano cassa.

    Su un PRIMO PIANO (finestra più stretta della tastiera: la tastiera continua fuori dai bordi
    laterali del fotogramma) quel numero non è un indizio. Quanti tasti ci entrano lo decide il
    passo, e i tasti del modello che restano fuori dal ritaglio sono tanti per costruzione:
    misurato sul primo piano dell'utente (un 720x386 sulla parte sinistra della tastiera) 13,7
    tasti nella finestra e 36,8 fuori, con la griglia appoggiata sui tasti (etichette da MI2 a DO4
    sui tasti veri, 52,4 px contro i 52,9 del profilo, 58 inlier). Lì il difetto da temere non è
    "la finestra non mostra 52 tasti" — che è la geometria del fotogramma — ma la griglia spostata
    di mezzo tasto o di un'ottava, e si vede dalle stesse due cose di sempre: il passo (confronto
    col profilo, qui sopra) e i neri che `affina` aggancia (`inlier`). Una finestra troppo stretta
    per dire qualcosa non passa comunque: `inlier` sono i punti che reggono l'omografia sui neri, e
    con pochi tasti inquadrati scendono da soli (una tastiera intera ne dà 226-231, il primo piano
    dell'utente con 14 tasti 58, sotto 40 è rifiuto).

    Quando si sa dove sta la tastiera davvero (misurata su tutto il pezzo, `bordo_tastiera`) la
    regola che conta diventa `tasti_fuori_dalla_tastiera`: quanti tasti del modello la griglia
    disegna oltre LA0 o oltre DO8. E' l'unico numero che distingue una griglia giusta da una
    spostata di due tasti quando il ritaglio è largo quanto il fotogramma (il caso dell'esempio 7:
    i "tasti fuori dal ritaglio" erano 0, così la griglia sbagliata passava per buona). Misurato
    sui candidati dell'esempio 7: intero 2,0 / profilo 6,8 / neri 9,1 tasti fuori dalla tastiera, e
    il candidato misurato sugli estremi 0,0. I neri verificati uno per uno NON entrano qui: la loro
    percentuale non distingue (47% con la griglia giusta quando il telefono copre mezza tastiera,
    contro 68% con una griglia spostata di 6 tasti), restano un numero da leggere nel controllo.
    """
    ordine = {"ok": 0, "incerto": 1, "rifiuto": 2}
    problemi: list[tuple[str, str]] = []
    if info["inlier"] < 40:
        problemi.append(("rifiuto", f"solo {info['inlier']} inlier: la griglia non regge (una buona "
                                    f"ne ha 80+), quasi sempre vuol dire che il ritaglio non "
                                    f"contiene i tasti"))
    if passo_profilo:
        # Per il candidato ancorato agli estremi il passo NON è quello che dice affina: è lo span
        # misurato diviso 52 tasti (`passo_medio`, vedi `griglia_nel_ritaglio`), perché lì la x è
        # fissata dagli estremi. Il confronto col profilo resta come rete di sicurezza (se lo span
        # fosse largo per colpa di qualcosa di chiaro fuori tastiera, il passo medio sarebbe più
        # grande del profilo), con una tolleranza più larga della solita. Misurato sull'esempio 7:
        # il profilo dice 33,43 px e gli estremi 33,15 (la verità 33,12), quindi il profilo lì è
        # quello spostato e la griglia ancorata non si contesta per 1%.
        ancorata = bool(info.get("ancorata"))
        passo = info["passo"]
        scarto = abs(passo / passo_profilo - 1)
        limite = 0.08 if ancorata else 0.06
        illeggibile = ncc_profilo is not None and float(ncc_profilo) < _NCC_PROFILO_MIN
        if scarto > limite and illeggibile:
            # Il profilo non sa dire di no (vedi la docstring): non si rifiuta, ma nemmeno si
            # tace, perché senza il profilo il passo della griglia non ha un secondo parere.
            problemi.append(("incerto", f"il passo ({passo:.1f} px) non si può confrontare col "
                                        f"profilo ({passo_profilo:.1f} px, "
                                        f"{(passo / passo_profilo - 1) * 100:+.1f}%): su questo "
                                        f"fotogramma il profilo non legge (NCC {ncc_profilo:.2f} "
                                        f"sotto {_NCC_PROFILO_MIN}), quindi il passo resta quello "
                                        f"dei tasti neri del fotogramma"))
        elif scarto > limite:
            problemi.append(("rifiuto", f"il passo finale ({passo:.1f} px) non è coerente "
                                        f"con quello del profilo ({passo_profilo:.1f} px, "
                                        f"{(passo / passo_profilo - 1) * 100:+.1f}%)"))
        elif scarto > (0.05 if ancorata else 0.03) and not illeggibile:
            problemi.append(("incerto", f"passo spostato del {scarto * 100:.1f}% rispetto al profilo: "
                                        f"guarda che i riquadri stiano uno per tasto"))
    # La finestra dei tasti vale per la tastiera INTERA, quindi solo quando la finestra può
    # contenerla (52 tasti bianchi o più). Sopra 58 la finestra è più larga della tastiera e la
    # griglia è scivolata sulla cassa (misurato 59,2). Sotto 52 la finestra NON può contenere la
    # tastiera: è un primo piano, la tastiera continua fuori dai bordi laterali, e sia i tasti che
    # ci entrano sia quelli del modello che restano fuori dal ritaglio sono numeri che escono dalla
    # geometria del fotogramma, non dalla griglia (misurato sul primo piano dell'utente: 13,7 tasti
    # nella finestra e 36,8 fuori, con la griglia appoggiata sui tasti, 58 inlier e il passo a -0,9%
    # dal profilo). Su un primo piano restano le stesse verifiche di sempre — passo contro profilo e
    # `inlier` — e una finestra troppo stretta per dire qualcosa non passa lo stesso: `inlier` sono
    # i punti che reggono l'omografia sui neri e con pochi tasti inquadrati scendono da soli (sotto
    # 40 è rifiuto).
    tastiera_ci_sta = info["tasti_nel_frame"] >= 52
    if auto and info["tasti_nel_frame"] > 58:
        problemi.append(("incerto", f"{info['tasti_nel_frame']:.0f} tasti bianchi nella finestra: "
                                    f"strano (una tastiera a 88 tasti inquadrata per intero ne "
                                    f"mostra 52)"))
    if tastiera_ci_sta and info.get("tasti_fuori", 0) > 1.5:
        problemi.append(("incerto", f"{info['tasti_fuori']:.1f} tasti del modello finiscono fuori "
                                    f"dal ritaglio: la griglia non è appoggiata sulla tastiera "
                                    f"(i riquadri sulla cassa si vedono nel controllo)"))
    fuori_t = info.get("tasti_fuori_dalla_tastiera")
    if auto and fuori_t is not None and fuori_t > 0.5:
        # Qui si sa dove sta la tastiera davvero (misurata su tutto il video): la griglia che
        # comincia prima di LA0 o finisce dopo DO8 disegna tasti che non esistono e sposta le
        # note di altrettanti tasti (un do etichettato come un la: è il difetto dell'esempio 7).
        # Non si rifiuta: il candidato ancorato agli estremi è quello giusto e vince da solo; se
        # non c'è, meglio il ritaglio di sempre con l'avviso che niente.
        bordi = info.get("bordo_tastiera") or ["?", "?"]
        problemi.append(("incerto", f"la griglia esce dalla tastiera di {fuori_t:.1f} tasti (LA0 a "
                                    f"{bordi[0]} px, DO8 a {bordi[1]} px, misurati su tutto il "
                                    f"video): i riquadri di quei tasti sono sulla cassa e le note "
                                    f"sono spostate"))
    # I neri verificati NON entrano nel verdetto: misurato, la loro percentuale non distingue una
    # griglia giusta da una sbagliata (47% con la griglia giusta di 2024-02-14_19-44-26, dove il
    # telefono copre mezza tastiera, contro 68% con una griglia spostata di 6 tasti). Restano nei
    # numeri e nell'immagine di controllo, dove li legge l'occhio: "neri 26 su 36 al posto giusto,
    # 6 coperti da una mano" dice subito se la griglia sta sui tasti.
    if info["evidenza"] < 0.60:
        problemi.append(("incerto", f"plausibilità {info['evidenza']:.2f} bassa (neri scuri e "
                                    f"bianchi chiari danno 0.75+): guarda l'immagine di controllo"))
    if not problemi:
        # Su un primo piano si dice anche quanto è stretta la finestra: "14 tasti nella finestra"
        # senza spiegazione è il numero che ha fatto sembrare sbagliata una griglia giusta (13,7
        # tasti e 36,8 fuori dal ritaglio sono la geometria di un fotogramma stretto, non un difetto).
        coda = ("" if tastiera_ci_sta else
                f"; primo piano: nella finestra ci stanno {info['tasti_nel_frame']:.0f} tasti bianchi, "
                f"la tastiera continua fuori dal fotogramma")
        return "ok", f"inlier {info['inlier']}, plausibilità {info['evidenza']:.2f}" + coda
    livello = max((p[0] for p in problemi), key=lambda l: ordine[l])
    return livello, next(t for l, t in problemi if l == livello)


def scelta_finale(prove, estremi_incerto=None):
    """Quale ritaglio si tiene, fra quelli provati: ((rect, info, numeri, verdetto, perche)).

    Prima si prende il migliore per verdetto e poi per inlier, come sempre. Poi l'eccezione: un
    ritaglio "estremi" solo "incerto" (di solito per la plausibilità, che crolla quando una mano
    o un telefono copre mezza tastiera) ma APPOGGIATO sulla tastiera misurata è comunque meglio
    di una griglia che ne esce, che è il difetto che questo passo esiste per non far passare.
    Misurato: su `2024-02-14_19-44-26` e `2024-02-14_20-37-55` il ritaglio di ripiego (l'intero)
    disegna 13,5 e 6,6 tasti fuori dalla tastiera mentre gli estremi 0,0, e col passo vero
    (33,10 px contro i 33,12 del metadata) invece che +4% e +6,7%. Il verdetto resta "incerto":
    l'avviso e l'immagine di controllo restano, cambia solo la griglia che si vede.
    """
    ordine = {"ok": 0, "incerto": 1, "rifiuto": 2}
    scelto = min(prove, key=lambda t: (ordine[t[3]], -t[2]["inlier"]))
    if (estremi_incerto is not None and scelto[3] != "ok"
            and estremi_incerto[2].get("tasti_fuori_dalla_tastiera", 9.9) <= 0.5
            and scelto[2].get("tasti_fuori_dalla_tastiera", 0.0) > 1.5):
        print(f"[scelta] il ritaglio 'estremi' è solo 'incerto' ({estremi_incerto[4]}) ma sta sulla "
              f"tastiera ({estremi_incerto[2].get('tasti_fuori_dalla_tastiera'):.1f} tasti fuori "
              f"contro {scelto[2].get('tasti_fuori_dalla_tastiera', 0.0):.1f} di "
              f"'{scelto[1].get('ritaglio')}'): si tiene quello")
        return estremi_incerto
    return scelto



# --- 2. controllo a occhio e scrittura del video -------------------------------------

def _pari(rect):
    """Larghezza e altezza pari: libx264 con yuv420p rifiuta le dimensioni dispari."""
    x1, y1, x2, y2 = (int(v) for v in rect)
    return (x1, y1, x1 + (x2 - x1) // 2 * 2, y1 + (y2 - y1) // 2 * 2)


def poligono_tasto_misurato(H, rect, x_tasti, n, lw=G.LW):
    """Il riquadro di un tasto nel fotogramma intero, con la x MISURATA tasto per tasto.

    Le due regole del passo 0: dove il tasto si vede la sagoma combacia col tasto trovato, dove
    è coperto si ipotizza dal vicinato (`dx_del_tasto`). Per un tasto nero la correzione è quella
    del suo centro — il riquadro trasla rigido, la larghezza resta quella del modello — mentre i
    due bordi di un tasto bianco sono due fessure diverse e ognuna ha la sua misura.

    `lw` è la lunghezza dei tasti bianchi in unità del modello: `G.LW` (6,2) quando il fronte non
    è stato misurato, altrimenti `lw_fronte` (`lw_al_fronte`), che è dove finiscono davvero i
    tasti. I neri restano a `G.LB`: le loro punte sono la misura della scala verticale, quella
    non si tocca.
    """
    x1, y1 = int(rect[0]), int(rect[1])
    if G.e_nero(n):
        d = dx_del_tasto(x_tasti, "nero", G.u_nero(n))
        a, b, fondo = G.u_nero(n) - G.BW / 2, G.u_nero(n) + G.BW / 2, G.LB
        lati = ((a, 0.0, d), (b, 0.0, d), (b, fondo, d), (a, fondo, d))
    else:
        a, b = G.u_bianco(n), G.u_bianco(n) + 1.0
        lati = ((a, 0.0, dx_del_tasto(x_tasti, "bordo", a)),
                (b, 0.0, dx_del_tasto(x_tasti, "bordo", b)),
                (b, lw, dx_del_tasto(x_tasti, "bordo", b)),
                (a, lw, dx_del_tasto(x_tasti, "bordo", a)))
    fuori = []
    for u, v, d in lati:
        x, y = G.proietta(H, [(u, v)])[0]
        fuori.append((int(round(float(x) + d + x1)), int(round(float(y) + y1))))
    return np.int32(fuori)


def disegna_griglia_misurata(frame, H, rect, x_tasti, etichette=True, lw=G.LW):
    """La griglia disegnata coi riquadri sui tasti: la stessa grafica di `G._disegna`.

    Verdi i tasti bianchi, blu i neri, col nome della nota in fondo al riquadro. `lw` è dove
    finiscono i bianchi: `lw_fronte` quando il fronte è stato misurato (vedi `lw_al_fronte`).
    """
    im = frame.copy()
    for n in G.BIANCHI:
        cv2.polylines(im, [poligono_tasto_misurato(H, rect, x_tasti, n, lw)], True,
                      (60, 220, 60), 2, cv2.LINE_AA)
    for n in G.NERI:
        cv2.polylines(im, [poligono_tasto_misurato(H, rect, x_tasti, n, lw)], True,
                      (255, 160, 30), 2, cv2.LINE_AA)
    if etichette:
        h, w = im.shape[:2]
        for n in G.BIANCHI:
            p = poligono_tasto_misurato(H, rect, x_tasti, n, lw)
            x, y = (p[2] + p[3]) / 2
            if 0 < x < w - 14 and 0 < y < h - 4:
                t = G.nome(n)
                pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
                cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return im


def disegna_griglia_al_fronte(frame, Hf, lw):
    """`G._disegna` (nessuna misura della x tasto per tasto) coi bianchi lunghi fino al fronte.

    Senza questa, quando il fronte dei bianchi è stato misurato l'unica strada era disegnare la
    geometria del modello e i riquadri si fermavano prima della punta del tasto: qui i bianchi
    arrivano a `lw` e i neri restano a `G.LB` (le punte sono la misura della scala verticale).
    """
    im = frame.copy()
    for n in G.BIANCHI:
        cv2.polylines(im, [np.int32(G.poligono_tasto(Hf, n, lw=lw))], True,
                      (60, 220, 60), 2, cv2.LINE_AA)
    for n in G.NERI:
        cv2.polylines(im, [np.int32(G.poligono_tasto(Hf, n))], True,
                      (255, 160, 30), 2, cv2.LINE_AA)
    h, w = im.shape[:2]
    for n in G.BIANCHI:
        p = G.poligono_tasto(Hf, n, lw=lw)
        x, y = (p[2] + p[3]) / 2
        if 0 < x < w - 14 and 0 < y < h - 4:
            t = G.nome(n)
            pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
            cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return im


def sovrapponi_controllo(frame, rect, info, H, H_abs=None, quad=None):
    """Disegna su un fotogramma il rettangolo del ritaglio e la griglia trovata.

    UN RIQUADRO PER TASTO: la stessa grafica del motore (`griglia_prospettica._disegna`, quella
    di `primo_frame_griglia.jpg`), verdi i tasti bianchi, blu i neri, col nome della nota.
    Lo usano sia l'immagine ferma (`immagine_controllo`) sia il video della griglia
    (`scrivi_video_griglia`), così quel che si guarda nei due file è la stessa cosa.

    E' il controllo a occhio prima di addestrare: se la griglia e' giusta i riquadri stanno
    appoggiati uno per tasto; se e' sbagliata finiscono sulla cassa, fuori dalla tastiera, o
    non combaciano coi bordi — e si vede subito, prima di ore di addestramento.

    Quando la tastiera e' stata misurata su tutto il video (`estremi`) si segnano anche i due
    bordi veri — LA0 e DO8 — e i numeri dei tasti neri: quelli dicono se i riquadri stanno sui
    tasti o accanto (i neri "coperti" sono sotto una mano o un tablet: lì la griglia va disegnata
    lo stesso, il tasto c'è).

    Con `x_tasti` (la misura tasto per tasto, vedi `x_tasti_misurata`) i riquadri si disegnano
    sulla posizione MISURATA di ogni tasto, non su quella del modello: è la differenza fra la
    griglia che sbaglia di mezzo tasto in mezzo alla tastiera e i riquadri appoggiati sui tasti.

    Con `lw_fronte` (il fronte dei tasti bianchi misurato, vedi `fronte_bianchi` e `lw_al_fronte`)
    i riquadri dei BIANCHI scendono fino a dove i tasti finiscono davvero e non a v=6,2 del
    modello: è la differenza fra "i tasti bianchi non sono coperti fino in fondo" e i riquadri
    che arrivano al fronte. I neri restano a `G.LB`, perché le loro punte sono la misura della
    scala verticale. Ritaglio, verdetto e geometria del dataset non cambiano.

    Con `H_abs` (l'omografia inseguita, già nelle coordinate del fotogramma intero, vedi
    `insegui_griglia`) la griglia si disegna dov'è su QUEL fotogramma invece che al primo, e con
    `quad` (i 4 angoli del ritaglio su quel fotogramma) il rettangolo magenta mostra dove il
    video viene ritagliato lì: è il controllo in movimento di una ripresa a mano libera, dove il
    rettangolo del primo fotogramma non direbbe la verità.
    """
    x1, y1, x2, y2 = (int(v) for v in rect)
    if H_abs is not None:                    # griglia inseguita: è già nel fotogramma intero
        Hf = np.asarray(H_abs, dtype=float).copy()
        im = G._disegna(frame, Hf)           # un riquadro per tasto, la grafica del motore
    else:
        Hf = np.asarray(H, dtype=float).copy()
        Hf[0, 2] += x1                                      # griglia locale -> frame intero
        Hf[1, 2] += y1
        x_tasti = info.get("_x_tasti")
        lw = info.get("lw_fronte") or G.LW  # dove finiscono i tasti bianchi (fronte misurato)
        if x_tasti:
            im = disegna_griglia_misurata(frame, H, rect, x_tasti, lw=lw)   # un riquadro per tasto
        elif lw != G.LW:
            im = disegna_griglia_al_fronte(frame, Hf, lw)                   # bianchi fino al fronte
        else:
            im = G._disegna(frame, Hf)                              # un riquadro per tasto
    est = info.get("estremi")
    if est:
        for x, t in ((est["x_la0"], "LA0"), (est["x_c8"], "DO8 fine")):
            cv2.line(im, (int(x), y1), (int(x), y2), (0, 255, 255), 2)
            cv2.putText(im, t, (int(x) + 4, y2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 4,
                        cv2.LINE_AA)
            cv2.putText(im, t, (int(x) + 4, y2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255),
                        1, cv2.LINE_AA)
    if quad is not None:              # il ritaglio si muove con la tastiera: si disegna quello
        pol = np.int32(np.round(np.asarray(quad, dtype=float)))
        cv2.polylines(im, [pol], True, (255, 0, 255), 2, cv2.LINE_AA)
        etichetta = "QUESTO E' IL RITAGLIO (SEGUE LA TASTIERA)"
        ex, ey = int(pol[0][0]) + 8, max(int(pol[0][1]) + 24, 24)
    else:
        cv2.rectangle(im, (x1, y1), (x2, y2), (255, 0, 255), 2)  # il ritaglio del video: magenta
        etichetta = "QUESTO E' IL RITAGLIO"
        ex, ey = x1 + 8, max(y1 + 24, 24)
    cv2.putText(im, etichetta, (ex, ey),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 6, cv2.LINE_AA)
    cv2.putText(im, etichetta, (ex, ey),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2, cv2.LINE_AA)
    righe = [f"passo {info['passo']:.1f}px  inlier {info['inlier']}  evidenza {info['evidenza']:.2f}"
             f"  tasti {info['tasti_nel_frame']:.0f}"]
    ins = info.get("inseguimento")
    if ins:
        righe.append(f"griglia inseguita: {ins['agganciati']}/{ins['frame']} fotogrammi, "
                     f"{ins['riavvii']} riavvii, inlier mediano {ins['inlier_mediano']}, "
                     f"la tastiera si sposta di {ins['spostamento_tasti']} tasti")
    if est:
        righe.append(f"tastiera misurata su tutto il pezzo: x {est['x_la0']:.0f}..{est['x_c8']:.0f}"
                     f" ({est['tasti']} tasti, buchi coperti {100 * (1 - est['copertura']):.0f}%)")
        if info.get("neri_ok") is not None:
            righe.append(f"tasti neri: {info['neri_ok']} al posto giusto, {info['neri_coperti']} "
                         f"sotto una mano/tablet, {info['neri_mancanti']} fuori posto")
    tm = info.get("tasti_misurati")
    if tm:
        righe.append(f"x tasto per tasto: {tm['misurati']} misurati ({tm['neri']} neri, "
                     f"{tm['bordi']} bordi), {tm['incoerenti']} incoerenti, "
                     f"{tm['ipotizzati']} ipotizzati; escursione {tm['escursione_tasti']} tasti")
    if info.get("lw_fronte"):
        righe.append(f"fronte dei tasti bianchi misurato: lunghi {info['lw_fronte']} tasti "
                     f"(il modello ne disegna {G.LW:.1f}): i riquadri verdi arrivano fin lì")
    # La riga del verdetto è l'ultima e la più lunga: si taglia a 110 caratteri, ma alla prima
    # parola intera e coi puntini, così non si legge "…la tastier" (l'immagine è larga 720 px:
    # quello che avanza lo taglia comunque il bordo).
    testo = f"verdetto: {info['verdetto']} - {info['perche']}"
    if len(testo) > 110:
        testo = testo[:110].rsplit(" ", 1)[0] + "..."
    righe.append(testo)
    for i, testo in enumerate(righe):
        cv2.putText(im, testo, (10, 34 + 34 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 6, cv2.LINE_AA)
        cv2.putText(im, testo, (10, 34 + 34 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    return im


# --- la griglia inseguita, fotogramma per fotogramma ---------------------------------

_SOGLIA_SEGUI_TASTI = 0.35   # sopra questo spostamento (in tasti) il ritaglio fisso perde la tastiera
_EMA_INSEGUIMENTO = 0.35     # quanto il ritaglio segue subito: il tremolio dell'aggancio non passa
_MAX_SEGUI_TASTI = 12.0      # oltre questo la tastiera non si sta muovendo: la griglia e' persa


def _credibile(inseguito, agganciati_min=0.5, inlier_min=20, saltomax=_MAX_SEGUI_TASTI):
    """Vero se la griglia inseguita ha davvero i tasti in mano, non una griglia scappata.

    I tre numeri di `insegui_griglia` dicono cose diverse e servono tutti e tre:
    `agganciati/frame` = su quanti fotogrammi l'affinamento ha agganciato i tasti veri (una
    griglia appiccicata sta sopra 0,9; quella scappata del video 18 del dataset stava a 30/1800
    = 0,017), `inlier_mediano` = quanto e' sicuro l'aggancio quando c'e' (la' era 0), e
    `spostamento_tasti` = quanto si e' mossa la tastiera in tutto il pezzo (una mano libera ne
    fa 7,5; una griglia scappata ne dichiarava 2386,94). Con un numero solo non si distingue
    "camera ferma con griglia buona" (0 tasti, 200 inlier) da "griglia scappata" (0 tasti, 0
    inlier). NON e' un giudizio sulla griglia del primo fotogramma: quello lo dà `verdetto`.
    """
    n = max(1, int(inseguito.get("frame", 0)))
    return (inseguito.get("agganciati", 0) >= agganciati_min * n
            and inseguito.get("inlier_mediano", 0) >= inlier_min
            and inseguito.get("spostamento_tasti", 0.0) <= saltomax)

def _H_assoluta(H, rect):
    """Omografia del ritaglio -> coordinate del fotogramma intero (somma dell'origine)."""
    T = np.array([[1.0, 0.0, float(rect[0])],
                  [0.0, 1.0, float(rect[1])],
                  [0.0, 0.0, 1.0]])
    return T @ np.asarray(H, dtype=float)


def _angoli_finestra(rect, M):
    """I 4 angoli del ritaglio trasportati dall'omografia `M` (dal frame 0 a quel frame).

    Si usano gli angoli dell'ULTIMO pixel del rettangolo (`x2-1`, `y2-1`) e non quelli esterni:
    con `M` identica la proiezione ricade sui pixel di partenza, quindi il frame 0 del video
    stabilizzato è il ritaglio di sempre, pixel per pixel, e non una versione riscalata di un
    filo (che basterebbe a far sbagliare l'ancoraggio al motore, che da un fotogramma solo
    indovina la fase dei tasti: misurato, 19 inlier invece di 58).
    """
    x1, y1, x2, y2 = _pari(rect)
    ang = np.array([[x1, y1, 1.0], [x2 - 1, y1, 1.0],
                    [x2 - 1, y2 - 1, 1.0], [x1, y2 - 1, 1.0]])
    p = (np.asarray(M, dtype=float) @ ang.T).T
    return p[:, :2] / p[:, 2:3]


def _ogni_avanzamento(tot, parti=10):
    """Ogni quanti fotogrammi stampare l'avanzamento di una fase lunga (`0` = non stampare mai).

    Le fasi lunghe del passo 0 -- l'inseguimento della griglia e la scrittura dei video -- non
    stampano niente fino all'ultimo fotogramma, e durano minuti: misurato sull'esempio 30 (60 s,
    1800 fotogrammi) l'inseguimento sono ~55 ms a fotogramma, cioè ~100 s, e la scrittura del
    controllo altrettanto. Sulla pagina del corso il passo 0 sembrava bloccato mentre stava
    lavorando: con una riga ogni `1/parti` del totale si vede che va avanti, e nel log della
    pagina restano i numeri veri (inlier, deriva) letti a metà strada.
    """
    return max(1, int(tot // parti)) if tot else 0


def _deriva_tasti(H_cur, H0, passo):
    """Di quanto si è spostata la griglia rispetto al primo fotogramma, in tasti (solo per il log)."""
    c, c0 = G.centro_griglia(H_cur), G.centro_griglia(H0)
    if c is None or c0 is None:
        return 0.0
    c, c0 = np.asarray(c, dtype=float), np.asarray(c0, dtype=float)
    if not (np.isfinite(c).all() and np.isfinite(c0).all()):
        return 0.0
    return float(np.hypot(*(c - c0)) / max(float(passo), 1e-6))


def insegui_griglia(video, rect, H, inizio=0.0, durata=0.0):
    """La griglia su OGNI fotogramma del pezzo, inseguendo la tastiera col tracker del progetto.

    È lo stesso giro di `griglia_prospettica.main`: flusso ottico fra due fotogrammi, omografia
    composta, `affina` che rimette a posto la prospettiva sui neri veri, e `H_iniziale` da zero
    solo quando l'inquadratura cambia davvero. A dire "cambiata" è il rapporto fra inlier e punti
    seguiti (`flusso`), non la differenza fra le immagini: una panoramica a mano libera sta a
    0,6-0,8 e va inseguita, un taglio di regia non passa 0,28 (misurato).

    Perché serve al passo 0. Il rettangolo congelato dice dove sta la tastiera sul PRIMO
    fotogramma: su una ripresa a mano libera la tastiera si sposta di parecchi tasti (misurato
    sull'esempio dell'utente: 393 px in diagonale = 7,5 tasti), quindi dopo metà pezzo il
    ritaglio è per metà fuori dai tasti e il controllo disegnato col rettangolo del primo
    fotogramma mostra una griglia che "scivola" — che è il difetto vero, non la griglia. Qui la
    griglia di partenza è quella scelta dal resto del passo 0 e viene trasportata: quello che si
    guarda è la stessa griglia, sul posto giusto, fotogramma per fotogramma.

    Ritorna `(Hs, Ms, lisce, numeri)`: `Hs[i]` = omografia inseguita GREZZA del fotogramma i-esimo
    letto (coordinate del fotogramma intero; si parte da `inizio`), `lisce[i]` = la stessa
    inseguita passata per la media pesata (vedi sotto: è la griglia da DISEGNARE, senza il
    tremolio dell'aggancio, quella che il video di controllo mostra), `Ms[i]` = il moto del
    ritaglio da quel fotogramma al primo (`lisce[i] @ inv(lisce[0])`, lisciato: è il ritaglio da
    trasportare, e da `Ms` si ricava `lisce[i] = Ms[i] @ Hs[0]` perché `lisce[0]` è `Hs[0]`),
    `numeri` = i numeri da mettere nel log e nel json.
    """
    H0 = _H_assoluta(H, rect)
    passo = float(np.hypot(H0[0, 0], H0[1, 0])) or 1.0
    Hs, inlier = [], []
    cap, fps_v, n_v = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    limite = int(round(durata * fps_v)) if durata else 0
    tot = limite or n_v
    ogni = _ogni_avanzamento(tot)
    if tot:
        print(f"[insegui] inseguo la griglia su {tot} fotogrammi ({tot / fps_v:.0f} s a {fps_v:g} fps): "
              "è la fase lunga del passo 0, un fotogramma alla volta")
    H_cur, prev, agganciati = H0, None, 0
    conta, riavvii, riancorate, scartate = 0, 0, 0, 0
    while True:
        ok, f = cap.read()
        if not ok or (limite and len(Hs) >= limite):
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        # Il fotogramma lo fa `griglia_prospettica.insegui`: flusso, affinamento e i tre freni
        # (salto massimo, scala che non cambia di colpo, ricerca del pianoforte da zero -- vedi il
        # commento lungo la', con la misura del guasto su questo genere di ripresa). Qui si
        # contano solo le volte che e' successo, per il log e per `_credibile`.
        H_cur, k, nota = G.insegui(H_cur, prev if prev is not None else g, g, f, conta, H0)
        conta = 0 if nota["cercato"] else conta + 1
        riavvii += 1 if nota["cercato"] else 0
        riancorate += 1 if nota["riancorata"] else 0
        scartate += 1 if nota["scartata"] else 0
        if k >= 10:
            agganciati += 1
        inlier.append(int(k))
        prev, Hs = g, Hs + [H_cur]
        if ogni and len(Hs) % ogni == 0:
            print(f"[insegui] {len(Hs)}/{tot} fotogrammi seguiti (agganciati {agganciati}, "
                  f"inlier mediano {int(np.median(inlier))}, "
                  f"deriva {_deriva_tasti(H_cur, H0, passo):.1f} tasti)")
    cap.release()
    n = len(Hs)
    if not n:
        return [], [], [], {}
    # Il tremolio dell'aggancio (l'affina che ritocca la griglia fotogramma per fotogramma)
    # NON deve far tremare la camera nel video preparato: il moto del ritaglio si prende dalla
    # stessa inseguita ma passata per una media pesata (EMA), e la decisione "si muove / sta
    # ferma" si prende su quella. Una ripresa ferma che l'affina fa oscillare di 20 px resta
    # "ferma" (il tremolio si media via), una panoramica vera no: quella si somma. La stessa
    # versione lisciata (`lisce`) è quella da DISEGNARE nel video di controllo: se lì si
    # disegnasse l'inseguita grezza (`Hs`) i riquadri porterebbero il tremolio dell'aggancio,
    # e su una ripresa ferma i tasti vibrerebbero mentre il rettangolo magenta (da `Ms`, liscio)
    # sta buono. Griglia disegnata e ritaglio vengono così dalla stessa media pesata.
    S, lisce = None, []
    for H_cur in Hs:
        S = H_cur if S is None else _EMA_INSEGUIMENTO * H_cur + (1 - _EMA_INSEGUIMENTO) * S
        lisce.append(S)
    Ms = [Si @ np.linalg.inv(lisce[0]) for Si in lisce]
    p = np.linalg.inv(lisce[0]) @ np.array([(rect[0] + rect[2]) / 2.0,
                                            (rect[1] + rect[3]) / 2.0, 1.0])
    rif = (float(p[0] / p[2]), float(p[1] / p[2]))
    spost = np.asarray([G.proietta(Si, [rif])[0] for Si in lisce], dtype=float)
    dist = np.hypot(spost[:, 0] - spost[0, 0], spost[:, 1] - spost[0, 1])
    salto = float(np.max(np.hypot(np.diff(spost[:, 0]), np.diff(spost[:, 1])))) if n > 1 else 0.0
    numeri = {"frame": n, "agganciati": agganciati, "riavvii": riavvii,
              "riancorate": riancorate, "scartati": scartate,
              "tasti_persi": n - agganciati,
              "inlier_mediano": int(np.median(inlier)) if inlier else 0,
              "inlier_minimo": int(min(inlier)) if inlier else 0,
              "spostamento_px": [round(float(dist.max()), 1),
                                 round(float(np.max(np.abs(spost[:, 1] - spost[0, 1]))), 1)],
              "spostamento_tasti": round(float(dist.max()) / passo, 2),
              "spostamento_per_frame_max": round(salto / passo, 2)}
    return Hs, Ms, lisce, numeri


def scrivi_stabilizzato(video, out, rect, Ms, canonica, inizio, durata):
    """Il video preparato con la tastiera ferma al suo posto, e l'audio copiato dall'originale.

    Su una ripresa a camera ferma il ritaglio a rettangolo fisso basta e costa una copia sola;
    su una ripresa a mano libera no: la tastiera esce dal rettangolo e il video preparato (quello
    su cui girano il motore e il dataset) perde i tasti di metà pezzo. Qui il rettangolo si porta
    dietro la tastiera: su ogni fotogramma si ritaglia il rettangolo trasportato dal moto della
    griglia inseguita (`insegui_griglia`), cioè sempre la STESSA finestra della tastiera, alla
    stessa dimensione — vedi `_angoli_finestra`.

    Il moto `Ms[i]` è quello rispetto al PRIMO fotogramma e passato per la media pesata (lì dentro,
    in `insegui_griglia`): al frame 0 è l'identità, quindi il video preparato comincia col ritaglio
    di sempre, pixel per pixel, e l'ancoraggio del motore (che da un fotogramma solo indovina la
    fase dei tasti) non ha una scusa per sbagliare. Il tremolio dell'aggancio non passa, così il
    video non trema. Su una ripresa a camera ferma il moto è nullo e il video esce come prima: per
    questo la strada si usa solo quando serve.

    Stessi fotogrammi e stessi fps dell'originale — non si tocca il tempo, quindi il MIDI resta
    allineato — e l'audio si COPIA dall'originale, senza ricodificarlo (verificato: ritardo 0).
    Si scrive a ffmpeg in pipe (rawvideo -> H.264, l'unico mp4 che i browser leggono).

    Ritorna il numero di fotogrammi scritti (0 = non si è scritto niente: si ripiega sul ritaglio
    fisso).
    """
    x1, y1, x2, y2 = _pari(rect)
    larghezza = int(canonica) if canonica else x2 - x1
    larghezza = max(2, larghezza // 2 * 2)
    altezza = max(2, int(round((y2 - y1) * larghezza / max(1, x2 - x1))) // 2 * 2)
    dst = np.float32([[0, 0], [larghezza - 1, 0], [larghezza - 1, altezza - 1], [0, altezza - 1]])
    cap, fps_v, _ = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    tot, ogni = len(Ms), _ogni_avanzamento(len(Ms))
    if tot:
        print(f"[video] scrivo il video preparato con la tastiera ferma: {tot} fotogrammi "
              "(ritaglio trasportato, un fotogramma alla volta)")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{larghezza}x{altezza}", "-r", f"{fps_v:g}", "-i", "-"]
    if inizio:
        cmd += ["-ss", f"{inizio:g}"]
    if durata:
        cmd += ["-t", f"{durata:g}"]
    cmd += ["-i", str(video), "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-crf", "20",
            "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
            "-movflags", "+faststart", str(out)]
    print("ffmpeg:", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (OSError, FileNotFoundError):
        cap.release()
        sys.exit("[!] ffmpeg non trovato: senza di lui non si scrive il video preparato")
    scritti, i, M_prec = 0, 0, None
    try:
        while True:
            ok, f = cap.read()
            if not ok or i >= len(Ms):
                break
            M = np.asarray(Ms[i], dtype=float)              # dal frame 0 a questo fotogramma
            if not np.isfinite(M).all():
                M = M_prec if M_prec is not None else np.eye(3)
            ang = _angoli_finestra(rect, M)
            if not np.isfinite(ang).all():
                ang = _angoli_finestra(rect, M_prec if M_prec is not None else np.eye(3))
            proc.stdin.write(cv2.warpPerspective(f, cv2.getPerspectiveTransform(np.float32(ang), dst),
                                                 (larghezza, altezza),
                                                 flags=cv2.INTER_LINEAR).tobytes())
            M_prec, scritti, i = M, scritti + 1, i + 1
            if ogni and scritti % ogni == 0:
                print(f"[video] {scritti}/{tot} fotogrammi scritti")
    except (BrokenPipeError, OSError):
        pass
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait()
        cap.release()
    if proc.returncode not in (0, None):
        print(f"[!] ffmpeg è uscito con codice {proc.returncode}: il video preparato può essere "
              "incompleto")
    return scritti


def immagine_controllo(frame, rect, info, H, percorso):
    """Il frame 0 col rettangolo del ritaglio e la griglia trovata: UN RIQUADRO PER TASTO.

    E' lo stesso disegno del video della griglia (`scrivi_video_griglia`), ma su un fotogramma
    solo: qui c'è tutto nel dettaglio (risoluzione piena), il video dice se tiene su tutto il
    pezzo. Se la griglia scivola a metà brano è il video a mostrarlo.
    """
    im = sovrapponi_controllo(frame, rect, info, H)
    cv2.imwrite(str(percorso), im, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"[controllo] {percorso}")


def filtro_ffmpeg(rect, canonica, fps):
    """-vf per il ritaglio a rettangolo fisso: crop (+ riscala canonica) (+ fps)."""
    x1, y1, x2, y2 = (int(v) for v in rect)
    vf = [f"crop={x2 - x1}:{y2 - y1}:{x1}:{y1}"]
    if canonica:
        vf.append(f"scale={int(canonica)}:-2")
    if fps:
        vf.append(f"fps={fps:g}")
    return ",".join(vf)


def scrivi_ffmpeg(video, out, rect, canonica, fps, inizio, durata):
    """Ritaglio a rettangolo fisso in un solo passaggio: audio compreso, qualità buona."""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if inizio:
        cmd += ["-ss", f"{inizio:g}"]
    cmd += ["-i", str(video)]
    if durata:
        cmd += ["-t", f"{durata:g}"]
    cmd += ["-vf", filtro_ffmpeg(rect, canonica, fps), "-c:v", "libx264", "-crf", "20",
            "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(out)]
    print("ffmpeg:", " ".join(cmd))
    if subprocess.run(cmd).returncode != 0:
        sys.exit("[!] ffmpeg ha fallito: è installato?")


def scrivi_video_griglia(video, out, rect, info, H, inizio, durata, fps=15.0, larghezza=1280,
                         Hs=None, Ms=None, lisce=None):
    """Il controllo in MOVIMENTO: la stessa griglia dell'immagine, su tutto il pezzo.

    Perché serve. `immagine_controllo` guarda un fotogramma solo (il primo dopo `--inizio`):
    se la griglia scivola a metà brano, se una mano copre i tasti, se il pianoforte si muove
    o se la tastiera cambia luce, lì non si vede niente. Qui si ridisegna lo stesso rettangolo
    per tasto su tutto il pezzo — verdi i bianchi, arancioni i neri, magenta il ritaglio — e i
    riquadri si vedono muoversi insieme al video: è il modo di guardare la griglia come la
    guarderebbe l'addestramento, ma a colpo d'occhio.

    Come. Si legge l'ORIGINALE (gli stessi fotogrammi dell'immagine, così quello che si vede è
    identico), se ne tiene uno ogni `fps_v/fps` (15 fps bastano, e il file resta piccolo: è un
    controllo, non il video di lavoro) e si manda il disegno a ffmpeg per l'H.264, senza audio
    e riscalato a `larghezza` px — un pezzo da 60 s sta in pochi MB. Se ffmpeg non c'è, o non
    si riesce a scrivere, si avvisa e si va avanti: il passo 0 non si ferma per un controllo.
    Ritorna il numero di frame scritti (0 = niente video).

    Con `lisce` (la griglia inseguita fotogramma per fotogramma e LISCIATA dalla media pesata,
    vedi `insegui_griglia`) e `Ms` (il moto del ritaglio, lisciato) si disegna la griglia di QUEL
    fotogramma e il ritaglio dove sta lì: su una ripresa a camera ferma è la stessa cosa di prima,
    su una a mano libera è la differenza fra vedere la griglia appiccicata ai tasti (con in più il
    rettangolo che segue) e vederla scivolare via col rettangolo fermo del primo fotogramma.
    `Hs` (la griglia GREZZA) resta come ripiego per quando `lisce` non c'è: senza la lisciatura i
    riquadri porterebbero il tremolio dell'aggancio, che è il difetto che il video deve mostrare.
    """
    x1, y1, x2, y2 = (int(v) for v in rect)
    cap, fps_v, n_v = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        print("[!] non riesco a rileggere il video per il controllo: niente video della griglia")
        return 0
    h, w = frame.shape[:2]
    lw = min(int(larghezza) if larghezza else w, w) // 2 * 2       # yuv420p vuole dimensioni pari
    lh = int(round(h * lw / w)) // 2 * 2
    # `-s` è la misura dei frame che mando (li riscalo io qui sotto): se non combaciano, ffmpeg
    # ricompone i frame a pezzi e il video esce con la risoluzione e la durata sbagliate.
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{lw}x{lh}", "-r", f"{fps:g}", "-i", "-", "-an",
           "-c:v", "libx264", "-crf", "26", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(out)]
    print("ffmpeg:", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (OSError, FileNotFoundError):
        cap.release()
        print("[!] ffmpeg non trovato: niente video della griglia (l'immagine di controllo c'è lo stesso)")
        return 0
    salto = max(1, int(round(fps_v / fps))) if fps and fps < fps_v else 1
    limite = int(round(durata * fps)) if durata else 0
    tot = limite or int(round(n_v / fps_v * fps))
    ogni = _ogni_avanzamento(tot)
    if tot:
        print(f"[griglia-video] disegno la griglia su {tot} fotogrammi ({fps:g} fps)")
    letti, scritti = 0, 0
    try:
        while True:
            if letti % salto == 0:
                if Hs and letti < len(Hs):           # griglia inseguita: si disegna quella
                    # Si disegna la griglia LISCIATA (`lisce`, la stessa media pesata che muove
                    # il ritaglio): così i riquadri non portano il tremolio dell'aggancio, che
                    # sulla camera ferma faceva vibrare i tasti e a mano libera li faceva
                    # scivolare. Il rettangolo magenta (`quad`, ricavato dalla stessa `Ms`) mostra
                    # dove il video viene ritagliato lì: griglia e ritaglio vengono dalla stessa
                    # `lisce`, quindi si muovono insieme. `Hs` (grezza) è solo il ripiego.
                    H_disegno = (lisce[letti] if lisce and letti < len(lisce) else Hs[letti])
                    q = (_angoli_finestra(rect, Ms[letti])
                         if Ms and letti < len(Ms) else None)
                    im = sovrapponi_controllo(frame, rect, info, H, H_abs=H_disegno, quad=q)
                else:
                    im = sovrapponi_controllo(frame, rect, info, H)
                if (lw, lh) != (w, h):
                    im = cv2.resize(im, (lw, lh), interpolation=cv2.INTER_AREA)
                proc.stdin.write(im.tobytes())
                scritti += 1
                if ogni and scritti % ogni == 0:
                    print(f"[griglia-video] {scritti}/{tot} fotogrammi disegnati")
                if limite and scritti >= limite:
                    break
            letti += 1
            ok, frame = cap.read()
            if not ok:
                break
    except (BrokenPipeError, OSError):
        pass                     # ffmpeg è morto prima: si tiene quel che è stato scritto
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait()
        cap.release()
    if proc.returncode not in (0, None):
        print(f"[!] ffmpeg è uscito con codice {proc.returncode}: il video della griglia può essere incompleto")
    return scritti




def scrivi_tracciato(video, out, rect0, canonica, fps, inizio, durata, ema=0.35, cerca=0.04):
    """Scrive il video inseguendo la tastiera, frame per frame (per una camera che si muove).

    `matchTemplate` del contenuto del primo ritaglio dentro una finestra attorno all'ultimo
    rettangolo; il rettangolo segue con una media pesata (EMA) per non tremare. Se il punteggio
    crolla si tiene l'ultimo rettangolo e si conta il fallimento (alla fine si dice quanti sono).
    Niente audio: all'addestramento serve solo l'immagine. Per una camera che si muove sul serio
    serve il KeyboardTracker del progetto, questo no.
    Ritorna (frame scritti, frame con inseguimento fallito).
    """
    cap, fps_v, _ = apri(video)
    salto = max(1, int(round(fps_v / fps))) if fps else 1      # --fps dimezza il lavoro, non il tempo
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    x1, y1, x2, y2 = (int(v) for v in rect0)
    bw, bh = x2 - x1, y2 - y1
    larghezza = int(canonica) if canonica else bw
    altezza = int(round(bh * larghezza / bw)) // 2 * 2
    wri = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps or fps_v, (larghezza, altezza))
    if not wri.isOpened():
        sys.exit(f"[!] non riesco a scrivere {out}: codec mp4v non disponibile?")
    tpl, letti, scritti, falliti = None, 0, 0, 0
    limite = int(round(durata * (fps or fps_v))) if durata else 0
    rett = np.array([x1, y1], float)
    scala = 0.25                    # modello e finestra ALLA STESSA risoluzione, un quarto basta
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if letti % salto == 0:
            h, w = frame.shape[:2]
            if tpl is None:                                    # il primo ritaglio è il modello
                tpl = cv2.resize(cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY), None,
                                 fx=scala, fy=scala, interpolation=cv2.INTER_AREA)
            else:
                mx, my = int(cerca * w), int(cerca * h)
                a = (max(0, int(rett[0]) - mx), max(0, int(rett[1]) - my))
                b = (min(w, int(rett[0]) + bw + mx), min(h, int(rett[1]) + bh + my))
                fin = cv2.cvtColor(frame[a[1]:b[1], a[0]:b[0]], cv2.COLOR_BGR2GRAY)
                fin = cv2.resize(fin, None, fx=scala, fy=scala, interpolation=cv2.INTER_AREA)
                if fin.shape[0] >= tpl.shape[0] and fin.shape[1] >= tpl.shape[1]:
                    _, v, _, loc = cv2.minMaxLoc(cv2.matchTemplate(fin, tpl, cv2.TM_CCOEFF_NORMED))
                    if v >= 0.5:
                        nuova = np.array([a[0] + loc[0] / scala, a[1] + loc[1] / scala], float)
                        rett = ema * nuova + (1 - ema) * rett
                    else:
                        falliti += 1
            cx, cy = max(0, int(round(rett[0]))), max(0, int(round(rett[1])))
            rit = frame[cy:cy + bh, cx:cx + bw]
            if rit.size == 0:
                rit = np.zeros((bh, bw, 3), np.uint8)
            elif rit.shape[:2] != (bh, bw):
                rit = cv2.copyMakeBorder(rit, 0, bh - rit.shape[0], 0, bw - rit.shape[1],
                                         cv2.BORDER_CONSTANT, value=(0, 0, 0))
            if canonica:
                rit = cv2.resize(rit, (larghezza, altezza), interpolation=cv2.INTER_AREA)
            wri.write(rit)
            scritti += 1
            if limite and scritti >= limite:
                break
        letti += 1
    wri.release()
    cap.release()
    return scritti, falliti, (int(round(rett[0])), int(round(rett[1])))



# --- 3. il programma -----------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Passo 0: ritaglia (o raddrizza) il video sulla tastiera.")
    p.add_argument("--video", default=None, help="il video da preparare (con --pianovam si ricava da solo)")
    p.add_argument("--out", default=".", help="cartella dove scrivere i tre file di uscita")
    p.add_argument("--nome", default=None, help="nome dei file (default: <video>_preparato)")
    p.add_argument("--rettangolo", default=None,
                   help="x1,y1,x2,y2 in pixel del video: salta la ricerca automatica (quando quella sbaglia)")
    p.add_argument("--pianovam", default=None, help="cartella del dataset PianoVAM: usa gli angoli di metadata.json")
    p.add_argument("--rec", default=None, help="record_time della registrazione PianoVAM")
    p.add_argument("--margine", type=float, default=0.3,
                   help="(auto) quanti passi di tasto tenere sopra la banda dei tasti neri (default 0.3)")
    p.add_argument("--fondo", type=float, default=7.0,
                   help="(auto) passi di tasto sotto la banda dei neri: la tastiera e' profonda 6.2")
    p.add_argument("--margine-px", type=int, default=10, help="(pianovam) pixel di margine attorno ai 4 angoli")
    p.add_argument("--trim-x", type=int, default=0,
                   help="(auto) 1 = parti dai ritagli stretti (profilo e neri), saltando la "
                        "larghezza intera: di solito non serve, si provano da soli e si tiene il "
                        "migliore")
    p.add_argument("--traccia", type=int, default=0,
                   help="1 = insegue la tastiera frame per frame (camera che si muove; il video esce senza audio)")
    p.add_argument("--insegui", default="auto",
                   help="auto (default) = insegue la griglia fotogramma per fotogramma e fa seguire "
                        "il ritaglio alla tastiera quando la camera si muove; 0 = rettangolo e "
                        "griglia congelati sul primo fotogramma; 1 = forzato")
    p.add_argument("--canonica", type=int, default=0,
                   help="larghezza in px dell'uscita: tasti della stessa dimensione in tutti i pezzi (0 = 1:1)")
    p.add_argument("--fps", type=float, default=0, help="fps di uscita (0 = quelli del video; 30 dimezza i 60 fps)")
    p.add_argument("--griglia-video", type=int, default=1,
                   help="1 = scrive <nome>_griglia.mp4, il video col rettangolo per tasto su tutto "
                        "il pezzo (15 fps, 1280 px: pochi MB); 0 = solo l'immagine di controllo")
    p.add_argument("--inizio", type=float, default=0, help="da che secondo partire")
    p.add_argument("--durata", type=float, default=0, help="quanti secondi (0 = tutto)")
    a = p.parse_args()

    dataset = Path(a.pianovam).expanduser() if a.pianovam else None
    if dataset and not a.rec:
        sys.exit("[!] con --pianovam serve --rec (il record_time della registrazione)")
    if a.video:
        video = Path(a.video).expanduser()
    elif dataset:
        video = dataset / "Video" / f"{a.rec}.mp4"
    else:
        sys.exit("[!] serve --video (oppure --pianovam insieme a --rec)")
    if not video.is_file():
        sys.exit(f"[!] manca {video}")

    uscita = Path(a.out).expanduser()
    uscita.mkdir(parents=True, exist_ok=True)
    nome = a.nome or (video.stem + "_preparato")
    mp4, js, jpg = uscita / f"{nome}.mp4", uscita / f"{nome}.json", uscita / f"{nome}_controllo.jpg"
    griglia_mp4 = uscita / f"{nome}_griglia.mp4"

    cap, fps_v, n_v = apri(video)
    if a.inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, a.inizio * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit("[!] non riesco a leggere un fotogramma (--inizio oltre la fine del video?)")
    h, w = frame.shape[:2]
    print(f"{video.name}: {w}x{h}, {fps_v:.3g} fps, {n_v} frame; analizzo il primo frame utile")

    if a.rettangolo:
        candidati = [rettangolo_manuale(a.rettangolo, w, h)]
    elif dataset:
        candidati = [rettangolo_pianovam(dataset, a.rec, a.margine_px)]
    else:
        candidati = candidati_auto(frame, a.margine, a.fondo, video=video,
                                   inizio=a.inizio, durata=a.durata)
        if a.trim_x and len(candidati) > 1:
            candidati = candidati[1:]        # l'utente vuole direttamente quello tagliato ai lati
    prove = []
    estremi_incerto = None
    for rect_i, info_i in candidati:
        try:
            numeri_i = griglia_nel_ritaglio(frame, rect_i, ancora=info_i.get("ancora", False),
                                            estremi=info_i.get("_estremi"),
                                            verticale=info_i.get("_verticale"),
                                            campioni_video=info_i.get("_campioni"))
            v_i, perche_i = verdetto(numeri_i, info_i.get("passo_profilo"),
                                     ncc_profilo=info_i.get("ncc"),
                                     auto=info_i.get("metodo") == "auto")
        except (RuntimeError, ValueError) as e:
            numeri_i = {"inlier": 0, "passo": 0.0, "evidenza": 0.0, "tasti_nel_frame": 0.0,
                        "tasti_fuori": 0.0, "H": None}
            v_i, perche_i = "rifiuto", f"griglia non calcolabile: {e}"
        tag = info_i.get("ritaglio", "?")
        # I due ritagli stretti (i neri sul primo fotogramma, gli estremi su tutto il video)
        # SPOSTANO il ritaglio: quello dei neri su una ripresa PianoVAM lo spostava di 13 tasti
        # (tagliando via mezza tastiera), quindi entra solo se è tutto "ok", cioè se passo,
        # inlier, tasti nella finestra, tasti fuori dal ritaglio e neri verificati tornano. Se è
        # solo "incerto" si scarta e resta la scelta di sempre, che è quella che l'utente ha
        # già visto — con una sola eccezione, `estremi_incerto` qui sotto.
        coda = (f"   (scartato: il ritaglio '{tag}' entra solo se è tutto ok)"
                if tag in ("neri", "estremi") and v_i != "ok" else "")
        print(f"[candidato] {tag:7s} x {rect_i[0]:>5}..{rect_i[2]:<5} y {rect_i[1]}..{rect_i[3]}: "
              f"passo {numeri_i['passo']:.2f} px, inlier {numeri_i['inlier']}, "
              f"tasti fuori {numeri_i['tasti_fuori']:.1f}, "
              f"dalla tastiera {numeri_i.get('tasti_fuori_dalla_tastiera', 0.0):.1f}, "
              f"neri {numeri_i.get('neri_ok', -1)}/{numeri_i.get('neri_ok', 0) + numeri_i.get('neri_mancanti', 0)}, "
              f"plausibilità {numeri_i['evidenza']:.2f} -> {v_i}{coda}")
        if tag in ("neri", "estremi") and v_i != "ok":
            if tag == "estremi" and v_i == "incerto":
                estremi_incerto = (rect_i, info_i, numeri_i, v_i, perche_i)
            continue
        prove.append((rect_i, info_i, numeri_i, v_i, perche_i))
        if v_i == "ok":
            break
    # a parità di verdetto si tiene quella con più inlier, come prima. I candidati "neri" ed
    # "estremi" hanno peso solo quando sono l'UNICO "ok" (allora il ciclo sopra si ferma lì e il
    # verdetto decide): così sui video dove i candidati sono tutti "incerto" il ritaglio resta
    # quello di sempre, con l'eccezione di un "estremi" che sta sulla tastiera e gli altri no
    # (vedi `scelta_finale`). Un "estremi" solo "incerto" NON entra in `prove`: se no vincerebbe
    # per inlier anche dove non ha niente di meglio da dire.
    scelto = scelta_finale(prove, estremi_incerto)
    if estremi_incerto is not None and scelto is not estremi_incerto:
        prove.append(estremi_incerto)            # provato e lasciato lì: si legge nel json
    rect, info, numeri, verdetto_scelto, perche = scelto
    H = numeri.pop("H")
    info.update(numeri)
    for k in ("H0", "_estremi", "_verticale", "_y_fondo", "_s_y",
              "ancora"):   # roba di servizio: non va nel json
        info.pop(k, None)
    info["passo"] = round(info["passo"], 2)
    info["evidenza"] = round(info["evidenza"], 3)
    info["verdetto"], info["perche"] = verdetto_scelto, perche
    if info.get("passo_profilo"):
        info["scarto_dal_profilo_percento"] = round((info["passo"] / info["passo_profilo"] - 1) * 100, 1)
    if len(prove) > 1:
        info["candidati_provati"] = [{"rettangolo": list(t[0]), "passo": round(t[2]["passo"], 2),
                                      "inlier": t[2]["inlier"], "tasti_fuori": t[2]["tasti_fuori"],
                                      "tasti_fuori_dalla_tastiera": t[2].get("tasti_fuori_dalla_tastiera"),
                                      "neri_ok": t[2].get("neri_ok"),
                                      "neri_mancanti": t[2].get("neri_mancanti"),
                                      "verdetto": t[3]} for t in prove]
    print(f"[rettangolo] {info['metodo']}: x {rect[0]}..{rect[2]}  y {rect[1]}..{rect[3]} "
          f"({rect[2] - rect[0]}x{rect[3] - rect[1]} px)")
    print(f"[griglia] passo {info['passo']} px, inlier {info['inlier']}, "
          f"plausibilità {info['evidenza']}, tasti nel frame {info['tasti_nel_frame']}, "
          f"tasti fuori {info['tasti_fuori']}")
    if info.get("estremi"):
        e = info["estremi"]
        print(f"[tastiera] misurata su tutto il pezzo: LA0 {e['x_la0']:.0f} px, DO8 {e['x_c8']:.0f} px "
              f"({e['tasti']} tasti da {e['passo']:.2f} px, {e['neri_misurati']} neri letti, "
              f"copertura {e['copertura'] * 100:.0f}%)")
        print(f"[griglia] rispetto alla tastiera: {info.get('tasti_fuori_dalla_tastiera')} tasti fuori, "
              f"neri {info.get('neri_ok')} al posto giusto / {info.get('neri_coperti')} sotto una "
              f"mano o un tablet / {info.get('neri_mancanti')} fuori posto")
        if info.get("lw_fronte"):
            print(f"[fronte] tasti bianchi misurati lunghi {info['lw_fronte']} unità del modello "
                  f"(il modello ne disegna {G.LW}): i riquadri verdi arrivano al fronte vero")
    tm = info.get("tasti_misurati")
    if tm:
        print(f"[tasti] x misurata tasto per tasto su tutto il pezzo: {tm['misurati']} misurati "
              f"({tm['neri']} neri e {tm['bordi']} bordi), {tm['incoerenti']} incoerenti "
              f"(mani/ombre: ipotizzati), {tm['ipotizzati']} ipotizzati dal vicinato; "
              f"la griglia si sposta fino a {tm['escursione_tasti']} tasti")
    print(f"[verdetto] {info['verdetto']}: {info['perche']}")

    # La griglia inseguita fotogramma per fotogramma (vedi `insegui_griglia`). Su una ripresa a
    # camera ferma dà la stessa cosa del rettangolo congelato; su una a mano libera è la
    # differenza fra un controllo che dice la verità e uno che mostra la griglia scivolare via
    # (e, per il video preparato, fra un ritaglio che perde i tasti a metà pezzo e uno che li
    # tiene). Gli esempi PianoVAM no: lì gli angoli sono misurati e la camera è fissa.
    insegui = str(a.insegui).strip().lower()
    if insegui == "auto":
        insegui = "" if (dataset or a.traccia) else "1"
    if insegui in ("0", "no", "false", "off", ""):
        insegui = ""
    Hs, Ms, lisce, inseguito = None, None, None, None
    if insegui and info["verdetto"] != "rifiuto":
        try:
            Hs, Ms, lisce, inseguito = insegui_griglia(video, rect, H, a.inizio, a.durata)
        except (RuntimeError, ValueError) as e:
            print(f"[!] inseguimento non riuscito ({e}): resta il rettangolo del primo fotogramma")
            Hs, Ms, lisce, inseguito = None, None, None, None
        if not Hs or not Ms or not inseguito:
            Hs, Ms, lisce, inseguito = None, None, None, None
        else:
            inseguito["credibile"] = _credibile(inseguito)
            info["inseguimento"] = inseguito
            print(f"[inseguito] {inseguito['agganciati']}/{inseguito['frame']} fotogrammi con la "
                  f"griglia agganciata, {inseguito['riavvii']} ricerche del pianoforte da zero "
                  f"({inseguito['riancorate']} riancorate) e {inseguito['scartati']} fotogrammi "
                  f"respinti dai freni, inlier mediano {inseguito['inlier_mediano']} (minimo "
                  f"{inseguito['inlier_minimo']}); la tastiera si sposta di "
                  f"{inseguito['spostamento_tasti']} tasti "
                  f"({inseguito['spostamento_px'][0]} px in diagonale; il salto più grande fra "
                  f"due fotogrammi è {inseguito['spostamento_per_frame_max']} tasti)")
            if not inseguito["credibile"]:
                # Una griglia che ha perso i tasti non deve né far seguire il ritaglio né
                # ridisegnare i riquadri (vedi `_credibile`): meglio il rettangolo e la griglia
                # del primo fotogramma, che sono quello che il verdetto ha già misurato.
                print(f"[inseguito] la griglia inseguita NON è credibile su questo pezzo "
                      f"({inseguito['agganciati']}/{inseguito['frame']} fotogrammi agganciati, "
                      f"inlier mediano {inseguito['inlier_mediano']}, "
                      f"{inseguito['spostamento_tasti']} tasti di spostamento dichiarato): "
                      f"restano il ritaglio e la griglia del primo fotogramma")
                Hs, Ms, lisce = None, None, None
            elif inseguito["spostamento_tasti"] > _SOGLIA_SEGUI_TASTI:
                print(f"[inseguito] la tastiera si muove: il video si ritaglia seguendola e la "
                      f"griglia resta appiccicata ai tasti (sopra {_SOGLIA_SEGUI_TASTI} tasti)")
            else:
                print("[inseguito] la camera sta ferma: ritaglio e griglia del primo fotogramma "
                      "vanno bene così")
    immagine_controllo(frame, rect, info, H, jpg)

    extra_salvato: dict = {}
    def salva(**extra):
        extra_salvato.update(extra)          # risalvando non si perdono i campi di prima
        dati = {"video": str(video), "uscita": str(mp4), "controllo": str(jpg),
                "griglia_video": str(griglia_mp4) if griglia_mp4.is_file() else None,
                "fps_origine": round(fps_v, 3), "fps_uscita": a.fps or round(fps_v, 3),
                "n_frame_origine": n_v, "inizio_s": a.inizio, "durata_s": a.durata or None,
                "rettangolo": list(rect), "larghezza_uscita": a.canonica or rect[2] - rect[0],
                "perche_ritaglio": ("la griglia dei tasti si cerca per periodicità: sulla ripresa "
                                    "intera si aggancia alla fascia sbagliata, dentro il ritaglio le "
                                    "corrispondenze passano da ~30 a ~200 e la scelta non è più ambigua")}
        dati.update(info)
        dati.update(extra_salvato)
        for k in ("_campioni", "_x_tasti"):     # roba di servizio: non va nel json
            dati.pop(k, None)
        js.write_text(json.dumps(dati, indent=1, ensure_ascii=False), encoding="utf-8")

    if info["verdetto"] == "rifiuto":
        salva()
        sys.exit(f"[!] NON addestrare con questo ritaglio: {info['perche']}\n"
                 f"    guarda {jpg} e riprova con --rettangolo x1,y1,x2,y2 a mano")

    if a.traccia:
        if rect[0] == 0 or rect[1] == 0 or rect[2] == w or rect[3] == h:
            print("[!] il rettangolo tocca il bordo del video: in quella direzione l'inseguimento "
                  "non ha spazio per muoversi (usa --trim-x 1 o un margine)")
        scritti, falliti, fine = scrivi_tracciato(video, mp4, rect, a.canonica, a.fps, a.inizio, a.durata)
        spostamento = [fine[0] - rect[0], fine[1] - rect[1]]
        print(f"[video] {scritti} frame inseguendo la tastiera, {falliti} falliti, "
              f"spostamento finale {spostamento} px")
        if falliti > 0.1 * max(scritti, 1):
            print(f"[!] inseguimento fallito sul {100 * falliti / max(scritti, 1):.0f}% dei frame: la "
                  "camera si muove più di quanto questo script sappia seguire (qui si insegue il "
                  "ritaglio col contenuto del ritaglio: per la camera che si muove sul serio c'è "
                  "l'inseguimento della griglia, --insegui auto/1, che è il default sulle riprese "
                  "caricate)")
        salva(frame_scritti=scritti, frame_inseguimento_fallito=falliti,
              rettangolo_finale=list(fine), spostamento_px=spostamento)
        if a.griglia_video:
            print("[!] con --traccia il video della griglia non si scrive: il ritaglio si sposta "
                  "frame per frame, quindi i riquadri disegnati col rettangolo del primo frame "
                  "non direbbero la verità (l'immagine di controllo resta)")
    else:
        stabilizzato = 0
        if Hs is not None and inseguito and inseguito["spostamento_tasti"] > _SOGLIA_SEGUI_TASTI:
            stabilizzato = scrivi_stabilizzato(video, mp4, rect, Ms, a.canonica,
                                               a.inizio, a.durata)
            if stabilizzato:
                print(f"[video] {stabilizzato} fotogrammi con la tastiera ferma e raddrizzata "
                      f"(la camera si muoveva di {inseguito['spostamento_tasti']} tasti: col "
                      f"ritaglio fisso il pezzo perdeva i tasti), audio copiato dall'originale")
        if not stabilizzato:
            scrivi_ffmpeg(video, mp4, rect, a.canonica, a.fps, a.inizio, a.durata)
        salva(ritaglio_video="stabilizzato" if stabilizzato else "fisso")
        if a.griglia_video:
            # Dopo il video preparato: è il controllo, non il lavoro (se fallisce non conta).
            quanti = scrivi_video_griglia(video, griglia_mp4, rect, info, H, a.inizio, a.durata,
                                          Hs=Hs, Ms=Ms, lisce=lisce)
            if quanti:
                mb = griglia_mp4.stat().st_size / 1024 ** 2
                print(f"[griglia-video] {quanti} frame col rettangolo per tasto ({mb:.1f} MB): "
                      "la griglia si guarda scorrere tutto il pezzo")
            salva()                     # risalva: adesso il video della griglia c'è

    print(f"[fatto] {mp4}\n        {js}\n        {jpg}"
          + (f"\n        {griglia_mp4}" if griglia_mp4.is_file() else ""))
    if info["verdetto"] == "incerto":
        print("[!] verdetto 'incerto': guarda il controllo (immagine e video) prima di addestrare")
    print("prossimi passi, sul video PREPARATO (non sull'originale):\n"
          f"  1) python3 ../motore_prospettica.py {mp4} -o <cartella dell'allineamento>\n"
          f"  2) python3 2_costruisci_dataset.py --video {mp4} --griglia <quella griglia> "
          f"--midi <il MIDI vero> --ritardo auto ...")


if __name__ == "__main__":
    main()

