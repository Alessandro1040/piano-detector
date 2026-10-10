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

    Il 10/10/2026 a quel "incerto" si è aggiunto il secondo parere che mancava: quando il profilo
    non legge e la griglia è ANCORATA agli estremi misurati, la conferma arriva dai tasti stessi —
    `x_tasti_misurata` li misura uno per uno su tutto il video (esempio 69 `2024-09-02_20-00-16`:
    85 misure coerenti su 87, 2 incoerenti, escursione 0 tasti) — e il verdetto torna "ok"
    (vedi `_tasti_misurati_ok`).

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

    Un conto sbagliato si porta via il candidato "estremi": senza `_tastiera_intera` non c'è né
    l'ancoraggio agli estremi né l'ottava misurata, e a ritagliare resta il candidato "neri" — il
    bordo di LA0 letto su UN fotogramma — che su questa famiglia di riprese cade sei tasti e mezzo
    a destra. Misurato sull'esempio 87 (`2024-09-04_21-09-37`): col conto a 47 (quello delle
    fessure, +9,1% dal profilo) il candidato "neri" è il solo "ok" e vince con ritaglio 423..1843
    (LA0 a 427,4 px contro i 250 misurati), passo 27,39 px, 105 inlier e verdetto "incerto",
    tagliando i sette tasti più a sinistra; col conto a 52 l'ancoraggio c'è, il ritaglio diventa
    246..1656 (fascia 250..1652), il passo 26,96 px (−1,4% dal profilo), gli inlier 235, i neri al
    posto giusto 35 su 36 e il verdetto "ok". Quale dei due conti vale lo decide la dispersione dei
    neri in `tastiera_nel_video` (`_MEGLIO_NERI`), non il numero delle fessure da solo.

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
    Il retro dei tasti però quel run non sempre lo dà: quando fra i tasti e il mobile c'è il
    RIFLESSO della tastiera sul mobile lucido (chiaro dove sotto c'è un bianco, scuro dove c'è un
    nero) il run scuro accettato comincia più in basso, e di quanto cambia da un capo all'altro
    della tastiera — sull'esempio 92 (`2024-09-04_22-13-22`) 2 px a sinistra e 17 a destra, coi
    riquadri che partivano sotto l'attacco dei tasti. Il retro si misura quindi a parte, a
    STRISCE di tastiera (`retro_tasti`: il gradino scuro -> chiaro del profilo MEDIO della riga,
    che il riflesso non ha perché è chiaro per pochi px), e si tiene il più alto dei due.
    Le PUNTE dei neri, però, non sono sempre il bordo del tasto: su una tastiera lucida la faccia
    frontale riflette la stanza, va sopra la soglia del nero e il run scuro chiude prima — punta
    corta di 15-20 px e, con lei, tutta la scala verticale (misurato sull'esempio 83:
    `2024-09-04_20-09-07`, punte a 520,9 px contro le 539-540 vere). Da lì i riquadri si fermano a
    metà tasto, sia i bianchi sia i neri. I due FRONTI veri (dove finiscono i bianchi e i neri) si
    misurano quindi a parte, su tutto il pezzo (`fronte_bianchi` e `fronte_neri`) e finiscono nei
    disegni come `lw_fronte` e `lb_fronte` (`lw_al_fronte`, `lb_al_fronte`): il ritaglio, il
    verdetto e la geometria del dataset restano quelli di prima, cambia solo fin dove arrivano i
    riquadri disegnati nel controllo e nel video della griglia.
Non si usa il detector YOLO del progetto: su queste riprese restituisce il pianoforte INTERO
(box (0,2)-(1904,610), confidenza 0.31) e ritagliando lì dentro la griglia sbaglia ancora.

USCITA (dentro --out CARTELLA)
    <nome>.mp4            il video ritagliato (o raddrizzato), dagli stessi frame, stessi fps
    <nome>.json           rettangoli per frame, geometria, numeri di controllo e verdetto;
                          `angoli_tasti` dice se e quanto i 4 angoli dei tasti bianchi si sono
                          spostati in tutto il pezzo (`decisa`: "ferma" = nessun inseguimento,
                          "si muove" = griglia e ritaglio seguono i tasti), `inseguimento` porta i
                          numeri dell'inseguimento quando è stato fatto;
                          `finestra_usata` piu' `larghezza_uscita`/`altezza_uscita` dicono la
                          finestra del video CHE E' STATO SALVATO (col raddrizzamento e' il
                          ritaglio allargato, lo stesso del rettangolo viola del controllo) e
                          `griglia_sui_tasti` se la griglia disegnata comincia e finisce dove
                          comincia e finisce la tastiera misurata: se no, il verdetto scende da
                          "ok" a "incerto" (vedi `griglia_sui_tasti`)
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

LA GRIGLIA INSEGUITA (solo quando i 4 angoli dei tasti si spostano: `--insegui auto`, il default)
    Il rettangolo congelato dice dove sta la tastiera sul PRIMO fotogramma, e su una ripresa a
    mano libera non basta: misurato sul video dell'utente, la tastiera si sposta di 393 px in
    diagonale (7,5 tasti) e a fine pezzo il ritaglio fisso la lascia per metà fuori (i tasti neri
    inquadrati passano da 9 a 0), mentre il controllo disegnato col rettangolo del primo
    fotogramma mostra una griglia che "scivola" — un difetto del CONTROLLO, che farebbe scartare
    una griglia buona: la griglia misurata sul primo fotogramma era a 1,8 px dai tasti veri.

    Con `--insegui 1` -- o con `--insegui auto` quando i 4 angoli dei tasti si spostano, vedi sotto --
    la griglia si trasporta fotogramma per fotogramma col tracker del progetto
    (`griglia_prospettica.flusso`: flusso ottico + omografia + `affina`, ripartenza da zero solo su
    un cambio di inquadratura vero, deciso dal rapporto fra inlier e punti seguiti) e:
      - il video della griglia disegna la griglia di QUEL fotogramma (col ritaglio che la segue);
      - il video preparato si ritaglia seguendo la tastiera, così resta ferma al suo posto e grande
        uguale anche se la camera si muove;
      - il json porta i numeri dell'inseguimento (`inseguimento`), la misura dei 4 angoli
        (`angoli_tasti`) e se il ritaglio è "fisso" o "stabilizzato" (`ritaglio_video`).
    PRIMA DI INSEGUIRE SI GUARDA SE LA TASTIERA SI MUOVE, e a dirlo sono SOLO i 4 angoli della
    griglia verde -- il blocco dei tasti bianchi, dal retro al fronte (`angoli_bianchi`), non il
    rettangolo magenta del ritaglio. Con `--insegui auto` (il default sulle riprese caricate)
    `tastiera_ferma` li proietta su OGNI fotogramma registrandolo sul PRIMO (gli stessi punti e la
    stessa omografia dell'inseguimento: niente deriva, perché ogni fotogramma è confrontato col
    primo e non col vicino) e guarda quanto si allontanano da dove stavano al fotogramma 0. Se
    nessuno esce dalla tolleranza (`_TOLLERANZA_ANGOLI_PX` in x, `_TOLLERANZA_ANGOLI_Y_PX` in y:
    più stretta di quella che l'inseguimento accetta come "la griglia sta sui tasti") l'inseguimento
    NON si accende, e ritaglio e griglia restano quelli del primo fotogramma per tutto il video: su
    una tastiera che non si muove inseguire sarebbe solo un rischio (una griglia che scappa) e un
    video preparato ricampionato a ogni fotogramma. Se invece si spostano oltre la stessa soglia con
    cui l'inseguimento conclude "la camera sta ferma" (`_TOLLERANZA_ANGOLI_PX` in x e
    `_TOLLERANZA_ANGOLI_Y_PX` in y; `_ANGOLI_FUORI_MAX` campioni storti DI FILA si perdonano, perché
    un fotogramma solo -- e nemmeno quattro sparsi -- non è movimento) si insegue come prima, e la
    griglia si muove quando si muovono i suoi angoli. La misura si ferma appena i campioni storti
    infilano abbastanza righe, così chi si muove non paga il resto del passaggio.

    La decisione si prende sulla media pesata (EMA) del moto, non sul fotogramma singolo: il
    tremolio dell'aggancio non conta come movimento, e non fa tremare il video preparato. Sotto
    `_SOGLIA_SEGUI_TASTI` (0,35) la camera è ferma e si scrive il ritaglio fisso di sempre, cioè
    lo stesso file di prima; `--insegui 0` spegne tutto e dà esattamente il comportamento vecchio
    (verificato: file identico byte per byte). E se la camera si muove così poco che nemmeno i 4
    angoli della zona dei tasti si spostano di mezzo tasto su tutto il pezzo (`_moto_angoli`), il
    moto misurato si butta e vale la griglia del fotogramma 0: una griglia spostata di mezzo tasto
    non sbaglia nessuna nota, e inseguire quel poco costerebbe un video ricampionato e una griglia
    che si stacca. Il frame 0 del video preparato è il
    ritaglio di sempre in ogni caso, così l'ancoraggio del motore (che da un fotogramma solo indovina
    la fase dei tasti) non ha una scusa per sbagliare: con la finestra di modello al posto del moto
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


def ancora_utile(frame, profilo):
    """`True` se il fotogramma è almeno un'ancora per `candidati_auto` (vedi `avvio_utile`).

    Non dice se il fotogramma LEGGE: `profilo` è il `passo_profilo` già calcolato (o `None`) e se il
    profilo dà un passo il passo 0 ci sa lavorare — è la sua prima misura. Se il profilo non dà
    niente si prova la scala dei neri veri (`banda_dai_neri`), che è la stessa ancora del ripiego.
    Restano fuori i fotogrammi che non sono una tastiera affatto (nero, buio, la camera che si
    accende): lì `candidati_auto` si arrende con "in questo video non trovo nessuna periodicità di
    tasti" e il pezzo non si prepara.
    """
    return profilo is not None or banda_dai_neri(frame) is not None


def avvio_utile(video, inizio, durata, frame):
    """`(inizio, frame, nota)`: sposta l'inizio sul primo fotogramma che LEGGE, se quello di partenza no.

    Il passo 0 aggancia tutto su UN fotogramma: `candidati_auto` ne misura il passo e la banda dei
    neri, `griglia_nel_ritaglio` ci cerca la griglia, l'inseguimento e il ritaglio partono da lì.
    Se quel fotogramma non è una tastiera — la mano che tiene il telefono col QR davanti ai tasti,
    la camera che si sta ancora assestando, i primi decimi al buio — non c'è nessun motivo per cui
    il resto del pezzo debba pagarne il prezzo: la griglia finisce sulla cassa o sul tappeto e il
    verdetto dice "la griglia è scivolata", che è vero ma non è colpa del pezzo.

    Misurato su `2024-02-15_21-33-36` (esempio 17 della pagina, 1920x1080, 60 s, l'utente che
    presenta il QR del suo telefono davanti alla tastiera): sul fotogramma 0 il profilo dà NCC 0,32
    con passo 167,46 px, cioè sei volte i 33,58 veri, quindi `candidati_auto` ripiega sulla scala dei
    neri (`banda_dai_neri`) e trova 27,39 px; da t=2 s in poi il profilo legge con NCC 0,62-0,71 e
    passo 33,58 px. Col fotogramma 0: griglia sul tappeto, passo 27,19 px, 70,6 tasti nella finestra,
    42 inlier, verdetto "incerto" e video preparato 1920x730 su una banda larga. Partendo da 2 s:
    passo 33,1 px, 52,3 tasti nella finestra, 0 tasti fuori, 264 inlier, verdetto "ok" e 1760x270,
    cioè i soli tasti.

    Fra i fotogrammi che leggono si distingue "legge" da "legge bene": a 1,5 s l'NCC è 0,46, cioè
    sopra la soglia per un pelo, e la griglia che ne esce ha 8 tasti neri fuori posto su 34 (quando
    si sceglie la fase la mano copre ancora la tastiera); a 2,0 s l'NCC è 0,62 e i neri fuori posto
    sono 0. Quindi si prende il primo fotogramma che legge BENE (`_NCC_PROFILO_MIN +
    _AVVIO_CIECO_BUONO`); uno che legge appena vale solo se il suo passo e' una MISURA e non
    un'armonica (`passo_profilo_coerente`: la banda ha i tratti scuri larghi come un nero) e, quando
    nemmeno quello c'e', solo se il fotogramma di partenza non e' nemmeno un'ancora.

    Si sposta l'INIZIO e non solo la misura per due ragioni: quel fotogramma nel dataset è inutile
    (la tastiera è coperta, il tasto premuto non si vede) e la griglia inseguita col ritaglio parte
    comunque dal primo fotogramma del video preparato — è un invariante del passo 0 (vedi "LA
    GRIGLIA INSEGUITA" nella docstring del modulo), quindi l'unico modo per non farglielo sbagliare
    è non proporglielo. Il resto di `main` usa `a.inizio` per tutto (campioni, inseguimento,
    scrittura, `inizio_s` nel json), quindi basta spostarlo qui: il video preparato esce tagliato da
    lì e il json lo dice (`avvio_cieco`).

    Se il fotogramma di partenza legge già (`NCC >= _NCC_PROFILO_MIN`) non si tocca niente e la nota
    è `None`: sui video buoni il comportamento è quello di sempre. Se nessuno dei fotogrammi
    guardati legge si tiene quello che c'è: l'avvio cieco è un sospetto, non una condanna.

    "Quello che c'è", però, deve essere almeno un'ancora (`ancora_utile`): il fotogramma nero — la
    camera che si accende — non lo è, e lì tenerlo non è un sospetto ma la fine del passo 0
    (`candidati_auto` si arrende con "in questo video non trovo nessuna periodicità di tasti").
    Misurato sull'esempio 83 della pagina (`2024-09-04_20-09-07`, F. Chopin Ballade No.1, 1920x1080,
    60 s presi dal video remoto): il fotogramma 0 è nero (luminanza 0, né profilo né neri) e da
    0,5 s in poi il profilo legge il passo VERO — 27,35 px contro i 27,08 della tastiera misurata su
    tutto il pezzo (52 tasti, LA0 a 245 px, DO8 a 1653 px) — ma con NCC 0,37-0,40: la soglia 0,45
    quel video non la tocca MAI, in nessuno dei 1800 fotogrammi, e i neri lì non aiutano
    (`banda_dai_neri` o non trova niente o sbaglia di 2-6 volte). Con il fotogramma nero il passo 0
    usciva "profilo NCC fallito"; partendo dal primo fotogramma-ancora (0,5 s, che è quello che
    l'utente otterrebbe scrivendo `--inizio 0.5`): verdetto "ok", 216 inlier, 0 tasti fuori,
    1436x198, cioè i soli tasti. Quindi: se nessuno legge E il fotogramma di partenza non è
    un'ancora, si ripiega sul primo che lo è; se invece il fotogramma di partenza è già un'ancora
    (il caso obliquo, dove il profilo legge male ma ci si sa lavorare) non si tocca niente.

    IL "LEGGE APPENA" CHE NON VALE (misurato l'11/10/2026 su `video5906842636420915152.mp4`,
    848x464, tastiera inclinata): sul fotogramma 0 il profilo da' NCC 0,37 e il passo 0 ne fa una
    griglia da 8,84 px con 288 inlier e l'ECC a tutta immagine a 0,90 -- verdetto "ok" e 216/224
    fotogrammi inseguiti. A 2,5 s il profilo "legge" (NCC 0,51, sopra la soglia per un pelo) ma il
    passo e' 79,48 px, sei volte i 13,3 veri: un'armonica, e nessuna banda ha i tratti scuri larghi
    come un nero. Spostando li' l'inizio il profilo smette di essere illeggibile e diventa una prova
    a carico (l'ECC scende a 0,77): il verdetto diventa "rifiuto" e il video non si prepara piu'.
    Per questo decide il bit di `passo_profilo_coerente`: senza di lui "legge appena" sposta l'inizio
    anche quando non porta nessuna misura nuova. Su `2024-09-02_20-00-16` (fotogramma 0 nero, profilo
    che non tocca mai la soglia) il primo fotogramma che legge appena HA la banda coerente (26,05 px,
    misurati sui neri) e l'inizio si sposta come prima.
    """
    p = G.passo_profilo(frame)
    ncc = float(p[2]) if p is not None else 0.0
    t0 = max(0.0, float(inizio or 0.0))
    if p is not None and ncc >= _NCC_PROFILO_MIN:
        return t0, frame, None
    cap, fps, n = apri(video)
    fine = (n / fps) if n else t0 + _AVVIO_CIECO_S
    if durata:
        fine = min(fine, t0 + float(durata))
    limite = min(t0 + _AVVIO_CIECO_S, fine - 1.0 / max(float(fps), 1.0))
    letto, buono, ancora = None, None, None
    t = t0 + _AVVIO_CIECO_PASSO
    while t <= limite:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, f = cap.read()
        if ok:
            q = G.passo_profilo_coerente(f)            # serve anche il bit "banda coerente coi neri"
            fidato = bool(q[5]) if q is not None else False
            if q is not None and float(q[2]) >= _NCC_PROFILO_MIN:
                if letto is None:                      # il primo che legge: è il minimo che basta
                    letto = (t, f, float(q[2]), fidato)
                if float(q[2]) >= _NCC_PROFILO_MIN + _AVVIO_CIECO_BUONO:
                    buono = (t, f, float(q[2]))         # ... ma uno letto BENE vale di più: si prende
                    break                               # quello, e si smette di cercare
            elif ancora is None and ancora_utile(f, q):
                # non legge, ma ci si lavora (il fotogramma nero ha bisogno di questo ripiego)
                ancora = (t, f, float(q[2]) if q is not None else None, fidato)
        t += _AVVIO_CIECO_PASSO
    cap.release()
    # Quando spostare l'inizio NON e' giustificato: il fotogramma di partenza e' gia' un'ancora (il
    # profilo da' un passo, magari con NCC basso: il caso obliquo, dove il passo 0 ci sa lavorare) e
    # nessun fotogramma legge BENE. Li' "legge appena" non e' una ragione per spostare: la soglia
    # `_NCC_PROFILO_MIN` e' bassa apposta (sotto di lei il profilo non e' una prova, vedi `verdetto`),
    # quindi un fotogramma a NCC 0,51 sposta il profilo da "non e' una prova" a "e' una prova a
    # carico" senza portare nessuna misura nuova -- e con un passo che puo' essere un'armonica.
    # Misurato su `video5906842636420915152.mp4` (848x464, tastiera inclinata): sul fotogramma 0 il
    # profilo da' NCC 0,37 e la griglia sta sui tasti con 288 inlier e l'ECC a tutta immagine a 0,90
    # (verdetto "ok", 216/224 fotogrammi inseguiti, il pezzo si prepara); spostando l'inizio a 2,5 s
    # (NCC 0,51, passo 79,5 px = sei volte i 13,3 veri) l'ECC scende a 0,77 e il verdetto diventa
    # "rifiuto" (passo 11,7 px contro 79,5), cioe' il video non si prepara piu'. La partenza si
    # sposta quindi solo per un fotogramma letto BENE (`buono`), o quando la partenza non e' nemmeno
    # un'ancora (fotogramma nero, buio, camera che si accende: li' qualunque cosa che si lasci
    # misurare e' meglio, `ancora` o `letto`).
    partenza_utile = ancora_utile(frame, p)
    scelto = buono
    if scelto is None and letto is not None and letto[3]:
        # Legge appena, ma la banda ha i tratti scuri larghi come un nero: e' una misura, non
        # un'armonica. E' il caso di `2024-09-02_20-00-16` (fotogramma 0 nero, profilo sempre sotto
        # la soglia), dove spostare l'inizio a 0,5 s e' quello che fa uscire il verdetto "ok".
        scelto = letto
    if scelto is None and not partenza_utile:
        scelto = ancora or letto                        # meglio un'ancora che un fotogramma nero
    if scelto is None:
        return t0, frame, None
    letto_ncc = f"{scelto[2]:.2f}" if scelto[2] is not None else "nessuna periodicità"
    nota = (f"il primo fotogramma non legge (NCC {ncc:.2f} sotto {_NCC_PROFILO_MIN}): la tastiera è "
            f"coperta o la camera si sta assestando, griglia e ritaglio partono da {scelto[0]:.1f} s "
            f"(NCC {letto_ncc}), come se l'inizio l'avesse chiesto l'utente")
    return scelto[0], scelto[1], nota


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


_DISPERSIONE_MAX = 0.35      # dispersione (p90-mediana, in passi) oltre cui i neri non si leggono
_MEGLIO_NERI = 0.6           # quanto i neri devono spiegare meglio delle fessure per cambiare conto


def _scarti_neri(x_la0, passo, c):
    """Scarti (px) fra i neri misurati `c` e i neri del modello a quel passo, per ogni nero."""
    return np.array([float(np.min(np.abs(c - (x_la0 + (G.u_nero(k) - G.u_bianco(G.NOTA_MIN))
                                                 * passo)))) for k in G.NERI])


def neri_spiegati(x_la0, span, tasti, c):
    """(dispersione, colpi) di un conto `tasti`: i neri del modello spiegano quelli misurati?

    `dispersione` = p90-mediana degli scarti (px), `colpi` = quanti neri misurati cadono a meno
    di 0,3 passi dalla mediana. E' il metro di `quanti_tasti`: con il conto giusto i neri del
    modello cadono sui neri misurati e la dispersione resta sotto `_DISPERSIONE_MAX` passi, con
    un tasto in piu' o in meno gli scarti si aprono (0,6 px per tasto, 30 px in fondo alla
    tastiera). Lo usano sia la scelta del conto in `quanti_tasti` sia l'arbitraggio fra i due
    conti in `tastiera_nel_video`.
    """
    passo = span / tasti
    scarti = _scarti_neri(x_la0, passo, c)
    med = float(np.median(scarti))
    return float(np.percentile(scarti, 90)) - med, int((np.abs(scarti - med) < 0.3 * passo).sum())


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
        dispersione, colpi = neri_spiegati(x_la0, span, n, c)
        if mig is None or dispersione < mig[0]:
            mig = (dispersione, colpi, n)
    dispersione, colpi, n = mig
    if dispersione > _DISPERSIONE_MAX * (span / n):   # i neri non si leggono: meglio il profilo
        return int(round(span / passo_profilo)), colpi
    return n, colpi


_FESSURA_FRAZIONI = (0.45, 2.2)   # larghezze plausibili, in frazioni della mediana globale
_FESSURA_VICINE = 6               # larghezze per lato per la larghezza LOCALE di un tratto
_FESSURA_TAPPO = 4.0              # tasti che un tratto solo puo' valere (una fascia coperta)
_FESSURA_MINIME = 12              # sotto questo numero di fessure il conto non e' una misura
_FESSURA_PLAUSIBILI = 0.6         # ... e neppure sotto questa frazione di tratti plausibili


def fessure_bianchi(profilo, passo):
    """Tutte le fessure fra i tasti bianchi: i minimi del profilo che staccano dal bianco ai due lati.

    E' la stessa ricetta di `_fessura_nel_profilo` (minimo locale, contrasto almeno
    `_CONTRASTO_FESSURA` rispetto alla mediana dei due lati) senza il "piu' vicino a x_modello":
    qui le fessure NON si cercano, si contano, quindi vanno trovate tutte. La finestra del
    contrasto e' di mezzo tasto per lato (`_FESSURA_SCARTO`), come la'.
    """
    mezza = max(1, int(_FESSURA_SCARTO * passo))
    cand = []
    for j in range(2, profilo.size - 2):
        if profilo[j] != min(profilo[j - 2:j + 3]):
            continue
        lo = max(1, j - mezza)
        hi = min(profilo.size - 1, j + mezza)
        sx = float(np.median(profilo[lo:max(lo + 3, j - 2)]))
        dx = float(np.median(profilo[min(hi - 1, j + 3):hi]))
        if min(sx, dx) - float(profilo[j]) >= _CONTRASTO_FESSURA:
            cand.append(j)
    return cand


def tasti_dalle_fessure(est, profilo, passo):
    """Quanti tasti bianchi ci stanno fra i due capi della fascia, contando le FESSURE:
    (somma, tratti anomali, frazione di tratti plausibili, fessure) oppure None.

    Perche' non basta dividere. La larghezza del tasto non e' costante nell'immagine: misurata
    sull'esempio 52 (`2024-04-08_22-49-18`) va da 29 a 34 px sulla stessa tastiera, e il passo del
    profilo cade +2% sul passo medio vero dei tasti (32,83 contro 32,17), quindi lo span diviso il
    passo del profilo da' 51,48 — un tasto in meno dei veri, cioe' una griglia storta del 2% su
    tutta la tastiera e un verdetto "incerto" per il passo fuori tolleranza. Il numero di tasti e'
    un INTERO e lo dice il numero di fessure, che si vedono a UN tasto di distanza: si somma, tratto
    per tratto, quante larghezze LOCALI ci stanno, invece di dividere lo span per un passo solo.
    Le fessure non si contano una per una perche' non ci sono tutte: su 44 riprese di `web_runs`
    (_prepara) i minimi contati uno per uno danno da 48 a 56 fessure (mani, tablet, spartito,
    riflessi ne tolgono e ne aggiungono), mentre la somma qui sotto da' 51,78..52,34 — sempre 52 —
    e su 2024-02-14_20-37-55, dove una fessura sola in mezzo alla tastiera e' letta 113 px dopo la
    precedente (3,4 tasti: una fascia coperta per tutto il pezzo), la conta secca dava 51.

    Come. Fra una fessura e la successiva c'e' un numero intero di tasti e la larghezza locale la
    misura la mediana delle larghezze VICINE (piu' o meno `_FESSURA_VICINE` tasti per lato), dopo
    aver buttato le larghezze assurde: sotto `_FESSURA_FRAZIONI[0]` della mediana globale sono due
    fessure dentro lo stesso tasto (entrano ed escono dalla somma in coppia, 0,3 + 0,7 = 1 tasto) e
    sopra `_FESSURA_FRAZIONI[1]` sono due tasti con la fessura in mezzo persa (si contano col passo
    dei vicini, senza arrotondare niente a uno). La somma dei due capi della fascia e' compresa: i
    capi SONO bordi di tasto (il primo tasto e' fra il capo sinistro e la prima fessura).

    I tratti anomali (fuori dal 25% da un tasto intero) sono il metro di fiducia: 0 sui fotogrammi
    puliti, 14 sul peggiore dei 44 (dove la tastiera entra in ombra) e li' il conto non si usa.
    """
    x_la0, x_c8 = float(est[0]), float(est[1])
    if profilo is None or x_c8 - x_la0 < 2.0 * passo:
        return None
    fess = [j for j in fessure_bianchi(profilo, passo) if x_la0 < j < x_c8]
    if len(fess) < _FESSURA_MINIME:
        return None
    nodi = np.array([x_la0] + fess + [x_c8], dtype=float)
    d = np.diff(nodi)
    med = float(np.median(d))
    if not med > 0:
        return None
    buone = (d >= _FESSURA_FRAZIONI[0] * med) & (d <= _FESSURA_FRAZIONI[1] * med)
    if float(buone.mean()) < _FESSURA_PLAUSIBILI:
        return None
    mid = (nodi[:-1] + nodi[1:]) / 2.0                     # dov'e' ogni tratto, in x
    vicini = np.abs(mid[:, None] - mid[None, :]) <= _FESSURA_VICINE * passo
    somma, sporchi = 0.0, 0
    for j in range(d.size):
        camp = d[vicini[j] & buone]                        # il tratto stesso e' fra i vicini
        locale = float(np.median(camp)) if camp.size >= 3 else med
        quoz = d[j] / locale
        if abs(quoz - 1.0) > 0.25:
            sporchi += 1
        somma += min(quoz, _FESSURA_TAPPO)
    return float(somma), sporchi, float(buone.mean()), len(fess)


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

    I tasti li conta `tasti_dalle_fessure` sul profilo MEDIANO dei fotogrammi (le fessure fra i
    bianchi si vedono anche dove i neri si perdono), e il conto dei tasti neri di `quanti_tasti`
    resta il secondo parere e il `neri_misurati` che si legge nel log e nel verdetto: misurato
    sull'esempio 52, le fessure dicono 52 e i neri 53 — ed era il 53 a far scendere il passo a
    -3,8% dal profilo, cioè il verdetto "incerto" che si vedeva nell'esempio.
    """
    s, _fase, _ncc, ya, _yb = p
    y0 = int(ya + 0.9 * G.LB * s)                       # sotto le punte dei neri
    acc, letti, profili = None, 0, []
    for _t, f in campioni_video:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        h = g.shape[0]
        y1 = int(min(h - 1, ya + G.LW * s))             # fine dei tasti bianchi
        if y1 - y0 < 8:
            return None
        vis = (g[y0:y1] < G._soglia(g)).mean(axis=0) < 0.5      # colonna chiara = tasto
        acc = vis.astype(np.int16) if acc is None else acc + vis
        profilo = _profilo_tastiera(g, y0, y1)          # le fessure: vedi `tasti_dalle_fessure`
        if profilo is not None:
            profili.append(profilo)
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
    centri_neri = scala_dai_neri(campioni_video, ya, s, campioni_video[0][1].shape[1], est)
    tasti_neri, colpi = quanti_tasti(est, s, centri_neri)
    conto = None
    if profili:
        conto = tasti_dalle_fessure(est, np.median(np.array(profili, dtype=np.float32), axis=0), s)
    tasti = int(round(conto[0])) if conto is not None else 0
    if not 44 <= tasti <= 56:                           # fessure trovate poche o sbilanciate:
        tasti = tasti_neri                               # si tiene il conto dei tasti neri
    # I due conti possono non essere d'accordo di un tasto o piu' e l'arbitro e' lo stesso metro
    # che `quanti_tasti` usa per scegliere: i neri del modello devono cadere sui neri MISURATI
    # (`neri_spiegati`, dispersione sotto `_DISPERSIONE_MAX` passi). Le fessure si perdono dove la
    # tastiera e' in ombra o in controluce — e li' la larghezza LOCALE con cui `tasti_dalle_fessure`
    # somma i tratti si gonfia, quindi il conto crolla — mentre la scala dei neri si legge lo
    # stesso, perche' il conto dei neri si cerca fra i 46..56 che spiegano i neri visti.
    # Misurato sull'esempio 87 (`2024-09-04_21-09-37`): fascia 250..1652, fessure 47 (passo
    # 29,83 px, +9,1% dal profilo 27,35) e neri 52 (26,96 px, -1,4%, 36 neri letti = tastiera da
    # 88); con il 47 la tastiera non risultava "intera" (`_tastiera_intera`), quindi sparivano il
    # candidato "estremi" e l'ottava MISURATA, l'ottava si indovinava col centraggio (`+2`) e il
    # ritaglio tagliava i sette tasti piu' a sinistra. La soglia relativa `_MEGLIO_NERI` e'
    # calibrata sui quattro video del corpus in cui i due conti non sono d'accordo: dove il conto
    # giusto e' quello delle fessure il rapporto fra le dispersioni e' 0,83 (`2024-02-15_21-33-36`,
    # 53 contro 52), 0,89 (`2024-04-08_22-49-18`, 52 contro 53: e' l'esempio 52 della docstring,
    # dove il 53 sbagliava) e 0,97 (`2024-09-02_18-29-40`, 52 contro 51); sull'esempio 87 e' 0,43,
    # cioe' le fessure non reggono di netto. Sotto 0,6 si cambia conto, sopra no.
    if (44 <= tasti <= 56 and 44 <= tasti_neri <= 56 and tasti != tasti_neri and centri_neri):
        span = float(est[1] - est[0])
        c = np.asarray(grappoli_neri(centri_neri, s), dtype=float)
        spread_fessure, _ = neri_spiegati(est[0], span, tasti, c)
        spread_neri, _ = neri_spiegati(est[0], span, tasti_neri, c)
        if (spread_neri <= _DISPERSIONE_MAX * (span / tasti_neri)
                and spread_neri < _MEGLIO_NERI * spread_fessure):
            tasti = tasti_neri                            # le fessure non reggono: valgono i neri
    if not 44 <= tasti <= 56:
        return None
    dentro = visto[int(est[0]):int(est[1])]
    if dentro.mean() < 0.5:                             # più di metà mai vista: non mi fido
        return None
    return {"x_la0": float(est[0]), "x_c8": float(est[1]), "passo": float((est[1] - est[0]) / tasti),
            "tasti": int(tasti), "copertura": float(dentro.mean()),
            "neri_misurati": int(colpi), "visto": visto, "campioni": letti,
            "tasti_neri": int(tasti_neri),
            "fessure": None if conto is None else int(conto[3]),
            "fessure_somma": None if conto is None else round(conto[0], 2),
            "fessure_sporche": None if conto is None else int(conto[1])}


_SCARTO_NERO = 0.40        # px dentro cui un run scuro è "quel" tasto nero, in passi di tasto


_FRONTE_CHIARO = 0.75      # frazione del 90° percentile sotto cui un tasto non è più chiaro
_FRONTE_SCURO = 0.32       # sopra questa il bordo trovato sotto il fronte non è il rastrello
_FRONTE_MIN = 0.55         # tratto chiaro minimo (in lunghezze di tasto) perché sia un tasto
_FRONTE_NERI_MIN = 0.50    # tratto scuro minimo (in lunghezze di NERO) perché sia un tasto nero
_FRONTE_NERI_AVVIO = 0.50  # il run scuro deve cominciare entro tanto dal fondo dei tasti
_FRONTE_NERI_TETTO = 1.8   # oltre, il run scuro non è un tasto: è un'ombra, una mano, il mobile


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


def fronte_neri(campioni_video, x_neri, fondo, punte, xm, passo_y, passo):
    """Dove FINISCONO davvero i tasti neri (la punta, faccia frontale compresa).

    Perché serve, e perché non basta la punta di `verticale_neri`. La scala verticale del modello
    esce dalle punte dei neri, e lì la punta è presa dove finisce il RUN SCURO della colonna: quel
    bordo è il pixel giusto solo se la faccia frontale del tasto è scura. Su una tastiera lucida
    la faccia frontale riflette la stanza e legge 117-134 (sopra la soglia: la punta esce CORTA di
    15-20 px) mentre quella della chiave accanto legge 60-80 (sotto la soglia: la punta esce
    giusta). Misurato sull'esempio 83 (`2024-09-04_20-09-07`, la ripresa dell'utente): punte a
    520,9 px contro le 540-541 vere, con le chiavi che chiudono a 498 o a 539 secondo come batte
    la luce. Da lì `passo_y` esce 19,18 px per unità invece di 23,7 e i riquadri dei NERI si
    fermano a metà tasto, come quelli dei bianchi (vedi `fronte_bianchi`: dei due numeri il fronte
    misurato era l'unico giusto — 8,42 unità del modello contro il 6,2 — ed è lui a dire quanto
    sono lunghi i neri).

    Come. Le stesse colonne dei neri di `verticale_neri` (il centro del tasto, dove la colonna è
    scura dal fondo fino alla punta) e per ognuna il run scuro più lungo: deve cominciare sul
    fondo dei tasti (`_FRONTE_NERI_AVVIO`), essere lungo almeno mezzo nero (`_FRONTE_NERI_MIN`) e
    avere sotto di sé il BIANCO del tasto bianco che sta davanti (`_FRONTE_CHIARO`). La faccia
    frontale lucida si scarta da sola: sotto la SUA fine il bianco non c'è ancora (legge 117-134,
    sotto la soglia del bianco), quindi quella colonna non dà un punto invece di darne uno
    sbagliato. Il tetto `_FRONTE_NERI_TETTO` tiene fuori ombre e mani, che scure lo sono per
    decine di pixel di fila. Dodici fotogrammi danno ~250 punti: la retta che ne esce è il fronte
    e la dispersione dice se è credibile (misurata sull'esempio 83: 0,8 px su 213 punti).

    Ritorna (a, b, quanti, dispersione) con y = a + b * (x - x_riferimento) in pixel del
    fotogramma, oppure None quando i punti sono pochi o la retta è dispersa (0,35 passi in x:
    `passo` è il passo dei tasti in x, quello che usa anche `fronte_bianchi`).
    """
    a0, b0 = fondo
    a1, b1 = punte
    h, w = campioni_video[0][1].shape[:2]
    punti: list[tuple[float, float]] = []
    for _t, f in campioni_video:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        P = float(np.percentile(g, 90))
        Tc = _FRONTE_CHIARO * P                      # il bianco del tasto che sta davanti
        T = G._soglia(g)                             # sotto questa un tasto nero è nero
        for xc in x_neri:
            x = int(round(xc))
            if x < 2 or x > w - 3:
                continue
            y0 = a0 + b0 * (x - xm)
            y_lim = min(h - 3, int(y0 + _FRONTE_NERI_TETTO * (a1 + b1 * (x - xm) - y0)))
            mig, y = None, max(0, int(round(y0)))
            while y < y_lim:                                # il run scuro più lungo: il tasto
                if g[y, x] < T:
                    s = y
                    while y < y_lim and g[y, x] < T:
                        y += 1
                    if mig is None or y - s > mig[1]:
                        mig = (s, y - s)
                else:
                    y += 1
            if mig is None or mig[1] < _FRONTE_NERI_MIN * G.LB * passo_y:
                continue                                    # troppo corto: non è un tasto
            s, lun = mig
            if s - y0 > _FRONTE_NERI_AVVIO * G.LB * passo_y:
                continue                                    # comincia in basso: ombra o mano
            y_fronte = s + lun
            if y_fronte + 6 < h and g[y_fronte + 3, x] >= Tc and g[y_fronte + 6, x] >= Tc:
                punti.append((float(x), float(y_fronte)))    # sotto c'è il bianco: è la punta
    if len(punti) < 20:
        return None
    xs = np.asarray([p[0] for p in punti], np.float64)
    ys = np.asarray([p[1] for p in punti], np.float64)
    b, a = np.polyfit(xs, ys, 1)
    # Seconda passata come per i bianchi: le colonne che passano da un riflesso della stanza
    # chiudono il run scuro (e il punto) 15-20 px più in su, e sono quelle che farebbero pendere
    # la retta. Si buttano quelle oltre 2,5 volte la dispersione e si rifà la retta: il fronte è
    # una riga sola, se dopo la seconda passata resta disperso la misura non vale.
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


_STRISCE_RETRO = 6          # strisce in cui si divide la tastiera per misurare il retro
_RETRO_SALTO = 8.0          # livelli: sotto questo, il gradino non e' un bordo di tasti
_RETRO_DISPERSIONE = 0.35   # passi di tasto: sopra, la retta del retro non e' una misura


def retro_tasti(campioni_video, x_la0, x_c8, fondo, punte, xm, passo, passo_y):
    """Dove COMINCIANO i tasti visibili (il retro dei bianchi), misurato su TUTTO il pezzo.

    Il modello mette `v = 0` sul bordo posteriore dei tasti e i riquadri partono da li': se quel
    bordo e' misurato qualche px piu' in basso del vero, i riquadri cominciano DENTRO i tasti e la
    parte alta dei tasti resta scoperta (e' il difetto che si vede a occhio nel controllo: i
    riquadri verdi e blu che partono sotto l'attacco dei tasti). `verticale_neri` il retro lo
    prende dal primo run scuro largo-da-nero di ogni colonna: quando fra i tasti e il mobile c'e'
    il RIFLESSO della tastiera sul mobile lucido (chiaro dove sotto c'e' un bianco) quel run
    comincia piu' in basso, e di quanto cambia da un capo all'altro della tastiera. Misurato
    sull'esempio 92 (`2024-09-04_22-13-22`, `web_runs/_prepara/c22daac674294f8d`): il retro di
    `verticale_neri` e' 456,2 + 0,0111*(x-1020) mentre i tasti cominciano a 447 su tutta la
    larghezza (misurato qui: 447,0 - 0,0009*(x-929), dispersione 0,8 px) — cioe' 2 px di scarto a
    sinistra e 17 px a destra, con la griglia che a DO8 partiva 17 px sotto l'attacco dei tasti.

    Come. Sulle righe la tastiera e' una fascia: sopra c'e' il mobile (scuro, ma col riflesso dei
    tasti sopra i bianchi) e sotto i tasti (chiari). Il bordo posteriore e' il gradino
    SCURO -> CHIARO che poi resta chiaro per tutta la lunghezza del tasto, e il riflesso non lo e'
    (e' chiaro per pochi px e poi torna scuro sul bordo del mobile). Si guarda quindi il profilo
    MEDIO della riga su una striscia di tastiera (`_STRISCE_RETRO` strisce: centinaia di colonne,
    cosi' una mano o un'ombra su qualche tasto non sposta niente) e si prende la riga col gradino
    positivo piu' forte, chiedendo che sotto resti chiaro (`_RETRO_SALTO` livelli) — e' quel
    controllo che scarta il riflesso. La finestra di ricerca sta attorno al retro che da'
    `verticale_neri` (non piu' di `passo` sopra, non piu' di due passi sotto: sotto ci sono le
    punte dei neri, e li' il gradino non e' il retro).

    Ritorna (a, b, quanti, dispersione) con y = a + b * (x - x_riferimento) in pixel del
    fotogramma, oppure None quando i punti sono pochi o la retta e' dispersa
    (`_RETRO_DISPERSIONE` passi di tasto): li' il retro di `verticale_neri` resta quello di prima.
    """
    a0, b0 = fondo
    a1, b1 = punte
    h, w = campioni_video[0][1].shape[:2]
    x_lo, x_hi = int(x_la0), int(x_c8)
    if x_hi - x_lo < 4 * passo:
        return None
    k = max(2, int(round(0.11 * passo)))          # mezze finestre del gradino (~3 px)
    punti: list[tuple[float, float]] = []
    for _t, f in campioni_video:
        gb = cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (0, 0), 1.2).astype(np.float32)
        larga = (x_hi - x_lo) / _STRISCE_RETRO
        for i in range(_STRISCE_RETRO):
            xa, xb = int(x_lo + i * larga), int(x_lo + (i + 1) * larga)
            if xb - xa < 4:
                continue
            xc = 0.5 * (xa + xb)
            y0 = a0 + b0 * (xc - xm)
            y_lo = max(k + 1, int(y0 - 1.0 * passo_y))
            y_hi = min(h - k - 2, int(a1 + b1 * (xc - xm)) - 4, int(y0 + 2.0 * passo_y))
            if y_hi - y_lo < 2 * k:
                continue
            riga = gb[:, xa:xb].mean(1)
            mig = None
            for y in range(y_lo, y_hi):
                # Finestre ADIACENTI al gradino: il massimo cade sulla riga del bordo (con le
                # finestre staccate di k il massimo e' un plateau largo k righe e si prende la
                # prima, cioe' k px troppo in alto).
                salto = float(riga[y:y + k].mean() - riga[y - k:y].mean())
                if mig is None or salto > mig[1]:
                    mig = (y, salto)
            if mig is None or mig[1] < _RETRO_SALTO:
                continue
            y = mig[0]
            livello = float(riga[y:y + k].mean())
            corto = riga[y:y + int(0.35 * passo)]
            if (corto > 0.8 * livello).mean() < 0.8:
                continue                                    # il riflesso sul mobile: chiaro e corto
            sotto = float(riga[y + k:min(h - 1, y + k + int(0.6 * passo))].mean())
            sopra = float(riga[max(0, y - k - 20):y - k].mean())
            if sotto - sopra < _RETRO_SALTO:
                continue
            punti.append((float(xc), float(y)))
    if len(punti) < 20:
        return None
    xs = np.asarray([p[0] for p in punti], np.float64)
    ys = np.asarray([p[1] for p in punti], np.float64)
    b, a = np.polyfit(xs, ys, 1)
    # Come per il fronte: una passata robusta (le ombre delle mani spostano qualche striscia) e
    # poi la regola sulla dispersione.
    scarto = float(np.percentile(np.abs(ys - (a + b * xs)), 90))
    if scarto > _RETRO_DISPERSIONE * passo:
        return None
    tenuti = np.abs(ys - (a + b * xs)) <= 2.5 * max(scarto, 1.0)
    if tenuti.sum() >= 20:
        xs, ys = xs[tenuti], ys[tenuti]
        b, a = np.polyfit(xs, ys, 1)
        scarto = float(np.percentile(np.abs(ys - (a + b * xs)), 90))
        if scarto > _RETRO_DISPERSIONE * passo:
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
    # Il retro VERO dei tasti, misurato a strisce (`retro_tasti`): il bordo del run scuro dei neri
    # qui sopra puo' stare piu' in basso del bordo dei tasti (il riflesso della tastiera sul mobile
    # lucido, chiaro dove sotto c'e' un bianco, allunga il run scuro e quello accettato comincia
    # sotto: misurato sull'esempio 92, 456,2 invece di 447, con 17 px di scarto a DO8). Il retro
    # delle strisce e' il bordo dei tasti BIANCHI, e quello dei neri sta 3-4 px PIU' IN ALTO (i neri
    # sono rialzati: il loro bordo posteriore si vede sopra la linea dei bianchi — misurato
    # sull'esempio 19, `2024-02-15_21-57-38`: bianchi a 350,3, bordo dei neri a 346,2, che li' era
    # stato verificato pixel su pixel). Si tiene il PIU' ALTO dei due, cosi' nessun pixel di tasto
    # resta fuori dai riquadri, e si prende l'inclinazione misurata a strisce (sull'esempio 92
    # quella del run era +0,0111, cioe' 15 px di pendenza che nell'immagine non c'e'). `passo_y` si
    # rifa' con la nuova origine: le punte dei neri restano la scala, quindi finiscono dove
    # finivano, e il fronte dei bianchi misurato qui sotto resta dov'e' (`lw_al_fronte` usa proprio
    # questi due numeri).
    retro = retro_tasti(campioni_video, x_la0, x_c8, (a0, b0), (a1, b1), xm, passo, passo_y)
    fondo_run = (a0, b0)                                # il retro dei neri (run scuro), per il report
    if retro is not None:
        a0, b0 = min(float(retro[0]), a0), float(retro[1])
        passo_y = (a1 - a0) / G.LB
    fronte = fronte_bianchi(campioni_video, x_la0, x_c8, (a0, b0), (a1, b1), xm, passo_y)
    # La punta dei NERI misurata come il fronte dei bianchi (`fronte_neri`): quando la punta della
    # scala verticale esce corta (la faccia frontale lucida va sopra la soglia: vedi lì) è questa
    # a dire ai disegni fin dove arrivano i neri, come `fronte` fa per i bianchi.
    fronte_n = fronte_neri(campioni_video, [x for x, _n in x_neri], (a0, b0), (a1, b1), xm,
                           passo_y, passo)
    return {"fondo": (a0, b0), "punte": (a1, b1), "x_riferimento": xm,
            "passo_y": float(passo_y), "chiavi": len(chiavi),
            "retro": None if retro is None else round(float(retro[0]), 1),
            "retro_letti": 0 if retro is None else retro[2],
            "retro_scarto": None if retro is None else round(float(retro[3]), 1),
            "fondo_run": round(float(fondo_run[0]), 1), "inclinazione_run": round(float(fondo_run[1]), 5),
            "fronte": None if fronte is None else (fronte[0], fronte[1]),
            "fronte_letti": 0 if fronte is None else fronte[2],
            "fronte_scarto": None if fronte is None else round(float(fronte[3]), 1),
            "fronte_neri": None if fronte_n is None else (fronte_n[0], fronte_n[1]),
            "fronte_neri_letti": 0 if fronte_n is None else fronte_n[2],
            "fronte_neri_scarto": None if fronte_n is None else round(float(fronte_n[3]), 1)}
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


def dx_tasti_cornici(x_tasti, note):
    """Lo scarto in x (pixel del fotogramma) dei 4 angoli di ogni tasto: `(K, 4)`.

    È la stessa correzione che `_poligono_misurato_float` applica al fotogramma 0 — i due bordi di
    un tasto bianco sono due fessure diverse e ognuna ha la sua misura, un nero trasla rigido col
    suo centro — ma tenuta come SCARTO da sommare alla x del modello, nell'ordine di
    `_angoli_modello` (retro-sinistra, retro-destra, fronte-destra, fronte-sinistra). Serve a
    `poligoni_nel_tempo`: la correzione va messa al fotogramma 0 e poi TRASPORTATA dal moto, come fa
    il disegno (`trasporta_poligoni(poligoni_griglia(...))`), non riapplicata a ogni fotogramma.

    Senza misure (`x_tasti` vuoto) sono tutti zero: il modello resta quello di prima.
    """
    if not x_tasti:
        return np.zeros((len(note), 4), dtype=float)
    d = np.zeros((len(note), 4), dtype=float)
    for k, n in enumerate(note):
        if G.e_nero(n):
            d[k, :] = dx_del_tasto(x_tasti, "nero", G.u_nero(n))
        else:
            a = G.u_bianco(n)
            d[k, 0] = d[k, 3] = dx_del_tasto(x_tasti, "bordo", a)
            d[k, 1] = d[k, 2] = dx_del_tasto(x_tasti, "bordo", a + 1.0)
    return d


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


def _y_al_fronte(verticale, rect, larghezza, fronte):
    """La y del fronte e quella del fondo al centro del ritaglio, in pixel del fotogramma."""
    xc = 0.5 * (int(rect[0]) + int(rect[0]) + int(larghezza))
    xm = verticale["x_riferimento"]
    return (verticale["fondo"][0] + verticale["fondo"][1] * (xc - xm),
            fronte[0] + fronte[1] * (xc - xm))


def lw_al_fronte(verticale, rect, larghezza):
    """Quanto è lungo un tasto bianco VERO, in unità del modello (il fronte misurato).

    E' il numero che serve ai disegni: i bianchi arrivano a `lw_fronte` invece che a `G.LW`. Si
    legge al centro del ritaglio, dove i pixel sono tanti e le due rette del fronte e del fondo
    valgono per tutto il fotogramma. Si tiene solo se sta fra 0,9 e 1,6 volte il modello.

    Il tetto era 1,35 (misurato: 6,41 su `2024-02-14_20-58-43` e 7,09 su `2024-03-17_18-54-44`,
    contro il 6,2 del modello) e su questa ripresa tagliava fuori una misura giusta: il fronte dei
    bianchi sta a 8,42 unità — 604 px contro i 561 che disegna il modello — perché la scala
    verticale è corta, e la scala è corta perché la punta dei neri è misurata 20 px in alto (vedi
    `fronte_neri`). Il rapporto nero/bianco che ne esce (4,1 su 8,42 = 0,49) sembra impossibile
    solo finché si crede alla punta: il fronte dei bianchi è una riga netta su 418 punti con 0,77
    px di dispersione, e a 604 px i tasti ci sono davvero (le fessure fra i bianchi si vedono fino
    lì: 12 livelli di contrasto fra bordi e centri nella fascia 565-595, contro 44 appena sotto le
    punte). Il controllo che tiene i numeri onesti non è il tetto ma la COPPIA: `lb_al_fronte`
    misura i neri e li vuole fra il 50% e il 72% dei bianchi, come nei pianoforti veri.

    Non sposta il ritaglio, il verdetto né la geometria del dataset (`griglia.json`): dice solo
    fin dove si disegnano i riquadri bianchi nel controllo e nel video della griglia.
    """
    fronte = (verticale or {}).get("fronte")
    if not fronte:
        return None
    y_fondo, y_fronte = _y_al_fronte(verticale, rect, larghezza, fronte)
    lw = (y_fronte - y_fondo) / verticale["passo_y"]
    if not 0.9 * G.LW <= lw <= 1.6 * G.LW:
        return None
    return round(float(lw), 2)


def lb_al_fronte(verticale, rect, larghezza, lw=None):
    """Quanto è lungo un tasto nero VERO, in unità del modello (la punta misurata).

    E' il gemello di `lw_al_fronte` per i neri, e si legge allo stesso modo. Il modello li disegna
    lunghi `G.LB` (4,1) perché è da lì che esce la scala verticale — ma "da lì" vale solo se la
    punta misurata è il bordo del tasto, e su una tastiera lucida non lo è sempre: la faccia
    frontale riflette la stanza e va sopra la soglia, il run scuro chiude prima, e la punta esce
    corta di 15-20 px (misurato sull'esempio 83: 520,9 invece di 540, con le chiavi che chiudono a
    498 o a 539 secondo la luce — vedi `fronte_neri`). Quando succede, la scala verticale esce
    corta di quel tanto e i riquadri dei neri — che sono a `G.LB` di quella scala — si fermano a
    metà tasto, che è esattamente il difetto che si vede a occhio.

    Si tiene solo se sta fra `G.LB` e 1,7 volte `G.LB`, e fra il 50% e il 72% dei tasti BIANCHI:
    `lw` quando il fronte dei bianchi è stato misurato, il modello (`G.LW`) quando non lo è — così
    un nero misurato non esce mai più lungo dei riquadri verdi che gli stanno accanto, che è la
    cosa che si vedrebbe a occhio. Il limite inferiore è `G.LB` e non zero perché la punta del
    modello è già DENTRO il tasto (il run scuro finisce lì o prima): una punta misurata più corta
    del modello è un errore di misura, non un tasto più corto, e disegnarla stingerebbe i riquadri
    sotto quel che si vede oggi. Il rapporto coi bianchi è quello dei pianoforti veri (il nero è
    il 56-64% del bianco: qui 5,07 su 8,42 = 0,60) allargato di un pelo per le prospettive.

    Non sposta il ritaglio, il verdetto né la geometria del dataset: dice solo fin dove si disegnano
    i riquadri neri nel controllo e nel video della griglia.
    """
    fronte = (verticale or {}).get("fronte_neri")
    if not fronte:
        return None
    y_fondo, y_fronte = _y_al_fronte(verticale, rect, larghezza, fronte)
    lb = (y_fronte - y_fondo) / verticale["passo_y"]
    if not G.LB <= lb <= 1.7 * G.LB:
        return None
    if not 0.5 * (lw or G.LW) <= lb <= 0.72 * (lw or G.LW):
        return None
    return round(float(lb), 2)


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


def bordi_verticali_x(H):
    """Toglie alla x la dipendenza dalla riga: i bordi dei tasti restano dritti.

    Perché serve. `H_dagli_estremi` scrive la x SENZA la riga (x = passo*u + bordo di LA0) e la y
    dalla misura (`riga_y_misurata`): poi la x dipende dalla riga solo per colpa di `affina`, che
    chiude l'omografia sulle corrispondenze che `misure` trova DENTRO i tasti neri (v 0,45..3,75,
    nove righe) più i punti del feltro (u -9..9, una riga sola sul fondo dei tasti). Sul fronte
    dei bianchi (v fino a LW, e nel controllo fino a `lw_fronte`) non c'è NESSUNA corrispondenza:
    l'inclinazione delle verticali è l'unica direzione dell'omografia che quei punti non
    vincolano, e `findHomography` lì restituisce quello che capita.

    Misurato su `2024-09-02_20-00-16` (`web_runs/_prepara/d07d666968b645ce`, la griglia di DO8 che
    nel controllo esce dai tasti). Le fessure dei bianchi, seguite riga per riga sul fotogramma 0
    del SORGENTE (senza niente disegnato sopra) su y 546..602 — 56 righe per 9 bordi, dal fondo
    dei tasti a 4 px dal fronte — hanno pendenza -0,016..+0,021 px/px, cioè sono verticali entro
    3 px su tutta l'altezza del tasto; il bordo destro della tastiera (bianco -> legno, contrasto
    pieno) sta su x = 1649,7 + 0,007*(y-482) fra y 482 e 602, cioè verticale. La H che esce da
    `affina` inclina invece gli stessi bordi di +0,088 (a u=-20) .. +0,137 (a u=29, il bordo di
    DO8): 22 px di sbandata fra il fondo e il fronte del tasto, ed è quello che si vede — i
    riquadri verdi si staccano dai tasti sempre di più verso destra (+10 px a DO8 sul fronte
    contro +1,5 al fondo). Non è una misura: `H_iniziale` sulla stessa tastiera dà -0,133, cioè
    segno opposto, e la stessa `affina` partendo da una H senza sbandata ne trova una grande lo
    stesso (il vero è 0,02; una direzione non vincolata è rumore).

    Cosa resta. Il resto della x di `affina` è quello che serve — passo e prospettiva in
    larghezza (h00, h02, h20) — e non si tocca: qui si azzerano solo i coefficienti della riga
    (h01 al numeratore, h21 al denominatore), cioè la sbandata. Coi bordi verticali `riancora_x`
    ha il senso che dichiara: gli estremi misurati su tutto il video valgono su TUTTE le righe
    del tasto, non solo su quella in cui la fascia li ha letti (v da 0,9*LB a LW, sotto le punte
    dei neri, vedi `tastiera_nel_video`), ed è la ragione per cui la griglia non finisce più 21 px
    fuori dal bordo di DO8.

    Per una tastiera RUOTATA (ripresa obliqua) i bordi non sono verticali e la sbandata è
    geometria vera: lì questa funzione non va usata — e il candidato ancorato non entra, perché
    senza una fascia misurata su tutto il pezzo `estremi` è None (le riprese oblique restano al
    candidato non ancorato, vedi la docstring del modulo).
    """
    H2 = np.array(H, dtype=float, copy=True)
    H2[0, 1] = 0.0
    H2[2, 1] = 0.0
    return np.float64(H2)


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


# LA TASTIERA INTERA MISURATA SU TUTTO IL PEZZO SI ACCETTA ANCHE A UN TASTO DI MENO (10/10/2026).
# `tastiera_nel_video` misura la fascia chiara dei tasti e ne conta i tasti (`quanti_tasti`): dove
# l'ULTIMO tasto e' in ombra (o coperto in tutti i campioni) la fascia si ferma un tasto prima e il
# conteggio esce 51. Misurato sull'esempio 66 (`2024-09-02_18-29-40`, tastiera intera inquadrata):
# LA0 a 249 px, DO8 a 1650, passo 27,47, copertura 100% contro i 245 e i 1652 veri (misurati sulle
# fessure fra i tasti bianchi sul fotogramma 0, passo vero 27,1): una misura buona, buttata via dal
# confronto `tasti == 52`. Senza `estremi` il candidato ancorato non esiste, l'ancoraggio sparisce e
# `analizza_tastiera` ripiega sul centraggio delle 88 note: su quel video la griglia finiva 13 tasti
# (2 ottave) a destra, con i riquadri ancora sui tasti ma i nomi sbagliati e la prima ottava e mezza
# di tastiera senza griglia. Non esistono pianoforti da 51 tasti bianchi (88 tasti -> 52 bianchi,
# 76 -> 45, 61 -> 36, 49 -> 29), quindi un 51 e' la tastiera intera con un tasto perso dalla misura,
# non una tastiera piu' corta: si accettano 51 e 52, non di piu' (53 sarebbe un tasto FANTASMA letto
# fuori dalla tastiera, e lì la x si sposterebbe dall'altra parte).
# Quel che costa ancorarsi a una fascia che ha perso un tasto: il modello infila 52 tasti nella
# larghezza di 51, quindi il suo passo esce piu' corto del misurato (26,94 contro 27,47) e le
# fessure in mezzo si spostano di quel poco. Misurato sull'esempio 66 — le 51 fessure vere del
# fotogramma 0 contro le linee della griglia disegnata — lo scarto e' 0 px in mediana e 5 px nel
# caso peggiore, con la prima e l'ultima linea sui due capi veri della tastiera (274 su 272, 1652
# su 1655): sotto un quinto di tasto, cioe' meta' della soglia che il passo 0 considera "sui tasti"
# (`griglia_sui_tasti`). I tasti misurati uno per uno (`x_tasti_misurata`) vengono poi ridisegnati
# dove sono, quindi nemmeno quello scarto resta. Si legge nel log: la riga `[tastiera]` dice quanti
# tasti ha letto la fascia.
_TASTI_INTERA = 52
_TASTI_INTERA_MIN = 51


def _tastiera_intera(est):
    """La fascia misurata su tutto il pezzo e' la tastiera INTERA (LA0..DO8)?

    Vale `False` senza la misura (`est` vuoto) e per qualunque conteggio fuori da
    `_TASTI_INTERA_MIN.._TASTI_INTERA`: vedi la nota sopra, è lì che sta il perché del 51.
    """
    t = int((est or {}).get("tasti") or 0)
    return _TASTI_INTERA_MIN <= t <= _TASTI_INTERA


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
        if _tastiera_intera(est):                            # un pianoforte intero: LA0..DO8
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
    if _tastiera_intera(est) and vert is not None:
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
    if _tastiera_intera(est):                             # un pianoforte intero: LA0..DO8
        info["estremi"] = {k: round(est[k], 2) for k in ("x_la0", "x_c8", "passo", "copertura")}
        info["estremi"].update(tasti=est["tasti"], campioni=est["campioni"],
                               neri_misurati=est["neri_misurati"],
                               tasti_neri=est.get("tasti_neri"), fessure=est.get("fessure"),
                               fessure_somma=est.get("fessure_somma"),
                               fessure_sporche=est.get("fessure_sporche"))
        info["_estremi"] = est                             # con la maschera "visto": si toglie
        m = 0.15 * est["passo"]                            # prima di scrivere il json
        prove.append(("estremi", (max(0, int(round(est["x_la0"] - m))), y1,
                                  min(w, int(round(est["x_c8"] + m))), y2)))
        if vert is not None:
            info["_verticale"] = vert
            info["verticale"] = {
                "fondo_tasti": round(vert["fondo"][0], 1), "inclinazione_fondo": round(vert["fondo"][1], 5),
                "punte_neri": round(vert["punte"][0], 1), "inclinazione_punte": round(vert["punte"][1], 5),
                "passo_y": round(vert["passo_y"], 2), "chiavi": vert["chiavi"],
                "retro_letti": vert["retro_letti"], "retro_scarto": vert["retro_scarto"],
                "fondo_run": vert["fondo_run"], "inclinazione_run": vert["inclinazione_run"],
                # I due fronti misurati che i disegni usano al posto della geometria del modello
                # (`lw_al_fronte` e `lb_al_fronte`): qui si vedono i numeri della misura, per
                # capire da dove escono `lw_fronte` e `lb_fronte` quando non ci sono.
                "fronte_letti": vert["fronte_letti"], "fronte_scarto": vert["fronte_scarto"],
                "fronte_neri_letti": vert["fronte_neri_letti"],
                "fronte_neri_scarto": vert["fronte_neri_scarto"]}
    visti, fuori = set(), []
    for tag, r in prove:
        r = _pari(r)
        if r in visti or r[2] - r[0] < 200:
            continue
        visti.add(r)
        fuori.append((r, dict(info, ritaglio=tag, ancora=(tag == "estremi"))))
    return fuori


def candidato_obliquo(frame):
    """Il ritaglio di ripiego per la tastiera obliqua e piccola -- o `None` se non è il caso.

    È l'ULTIMA spiaggia, e ci si arriva solo quando oggi non esce nessuna griglia: il profilo di
    colonne non legge (NCC sotto `_NCC_PROFILO_MIN`: su una tastiera obliqua spalma ogni nero su
    quelli vicini), i neri non si accoppiano fra due quote (`banda_dai_neri` è `None`: il blocco è
    alto meno di 25 righe, la riga di misura di `banda_neri` cade fuori) e la scelta di oggi sarebbe
    "rifiuto" -- cioè oggi non esce nessuna griglia (vedi `main`, che qui prova il ripiego solo se
    la scelta di prima sarebbe "rifiuto" e solo se questo viene meglio di "rifiuto"). Un video che
    oggi una griglia ce l'ha, "ok" o anche solo "incerto", non entra mai qui: per tutti gli altri
    questo ritorna `None` e la scelta di prima resta quella di prima, byte per byte.

    Il ritaglio lo detta la MISURA, non il profilo: `tastiera_obliqua` (vedi
    `griglia_prospettica`) legge i neri uno per uno e dice dove cominciano (il bordo posteriore,
    che è inclinato), dove finiscono i bianchi (il fronte) e il passo. La fascia è quella fra il
    bordo e il fronte con un margine VERO sopra e sotto, perché la ricerca dei neri di `banda_neri`
    guarda le righe fra il 15% e l'85% dell'altezza del ritaglio: con la fascia appoggiata sul
    bordo posteriore -- com'è il candidato "intero" di oggi su questo video, y 262..512 -- quelle
    righe cadono fuori dal ritaglio e la misura non c'è più (misurato:
    `document_5931401697506107171.mp4`, dentro quella fascia 0 inlier, dentro questa 47 coi neri
    agganciati uno per uno).
    """
    h, w = frame.shape[:2]
    p = G.passo_profilo(frame)
    if p is None or float(p[2]) >= _NCC_PROFILO_MIN:
        return None
    if banda_dai_neri(frame) is not None:
        return None                     # il caso di sempre: la tastiera si legge
    try:
        obl = G.tastiera_obliqua(frame)
    except (RuntimeError, ValueError):
        return None
    if obl is None or obl.get("fronte") is None:
        return None
    retro, punte, fronte = float(obl["retro"]), float(obl["punte"]), float(obl["fronte"])
    alt = fronte - retro
    if not 6.0 <= alt <= 0.5 * h:
        return None
    y1 = max(0, int(round(retro - 0.35 * alt)))
    y2 = min(h, int(round(fronte + 0.35 * alt)))
    if y2 - y1 < 40 or w < 200:
        return None
    info = {"metodo": "auto", "ritaglio": "obliquo", "obliqua": True,
            "passo_profilo": round(float(p[0]), 2), "fase": round(float(p[1]), 1),
            "ncc": round(float(p[2]), 3), "banda_neri": [int(retro), int(punte)],
            "obliquo": {"passo": round(float(obl["passo"]), 2),
                        "passo_y": round(float(obl["passo_y"]), 2),
                        "retro": round(retro, 1), "fronte": round(fronte, 1),
                        "punte": round(punte, 1),
                        "inclinazione": round(float(obl["inclinazione"]), 5),
                        "x_neri": [round(float(x), 1) for x in obl["x_neri"]],
                        "note": [G.nome(n) for n in obl["note"]],
                        "perche": "il profilo non legge e i neri non si accoppiano fra due quote: "
                                  "passo, bordo posteriore e fronte misurati sui neri uno per uno"},
            "banda_dai_neri": {"passo": None, "y_inizio": None,
                               "perche": f"nessun accoppiamento fra due quote (NCC {float(p[2]):.2f} "
                                         f"sotto {_NCC_PROFILO_MIN})"}}
    return _pari((0, y1, w, y2)), info


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


def _render_modello(H, forma, lw=G.LW, lb=G.LB, note=None):
    """Il modello della tastiera disegnato come immagine: bianchi chiari, neri scuri, fessure grigie.

    Ritorna `(immagine, maschera)`: la maschera e' dove il modello dice "qui ci sono dei tasti",
    ed e' l'unico posto dove l'allineamento deve guardare (il resto e' cassa, muro, tappeto).
    """
    h, w = forma
    T = np.zeros((h, w), np.uint8)
    Mk = np.zeros((h, w), np.uint8)
    bianchi = [n for n in (note or G.BIANCHI) if not G.e_nero(n)]
    neri = [n for n in (note or G.NERI) if G.e_nero(n)]
    for n in bianchi:
        p = np.int32(np.round(G.poligono_tasto(H, n, lw=lw)))
        cv2.fillPoly(T, [p], 215)
        cv2.fillPoly(Mk, [p], 255)
        cv2.polylines(T, [p], True, 150, 1)
    for n in neri:
        cv2.fillPoly(T, [np.int32(np.round(G.poligono_tasto(H, n, lb=lb)))], 25)
    return T, Mk


def _ecc_griglia(g, H, scale=(4, 3, 2), lb=G.LB):
    """Allinea il modello all'immagine con ECC (omografia piena): ritorna `(H, correlazione)` o None.

    Perche' ECC e non `affina`: `affina` parte da `H_iniziale` e si ferma dove trova i neri, ma
    `H_iniziale` sbaglia y e x di decine di pixel sui primi piani e sulle riprese oblique, e un
    modello periodico (i tasti si ripetono) non si recupera da lontano. ECC invece confronta
    TUTTO il disegno del modello con TUTTA l'immagine (neri, fessure, fronte, retro) e stringe
    insieme x, y, scala e prospettiva: quello che si vedeva era la griglia troppo bassa, i
    riquadri blu sotto i neri veri e le linee verdi fuori fase.

    A piu' scale: prima sfocato (4 px: si allineano le masse chiare/scure), poi sempre meno
    (i singoli tasti). Da un'unica sfocatura fissa la convergenza dipendeva dal ritaglio.
    """
    best, cc = np.asarray(H, dtype=float), 0.0
    for blur in scale:
        T, Mk = _render_modello(best, g.shape, lb=lb)
        if Mk.sum() < 255 * 200:                       # modello quasi fuori dall'immagine
            return None
        gb = cv2.GaussianBlur(g, (0, 0), blur).astype(np.float32)
        Tb = cv2.GaussianBlur(T, (0, 0), blur).astype(np.float32)
        W = np.eye(3, dtype=np.float32)
        try:
            cc, W = cv2.findTransformECC(Tb, gb, W, cv2.MOTION_HOMOGRAPHY,
                                         (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6),
                                         Mk, 5)
        except cv2.error:
            if blur == scale[0]:
                return None                            # nemmeno la scala grossa: partenza sbagliata
            continue                                   # una scala fine che non converge: si tiene la precedente
        best = W.astype(float) @ best
    return best, float(cc)


def _scatola_tastiera(g):
    """Il rettangolo (minAreaRect) della fascia chiara e lunga dei tasti bianchi, o None.

    Serve da partenza quando la tastiera sta lontana o storta (ripresa larga, obliqua) e
    `H_iniziale` e' fuori di centinaia di pixel: la fascia dei bianchi e' l'unica cosa del
    fotogramma che sia chiara, lunga e sottile (rapporto 5+) e larga almeno un quarto dell'immagine.
    """
    h, w = g.shape
    gb = cv2.GaussianBlur(g, (0, 0), 1.2)
    cand = []
    for thr in (140, 160, 180, 120):
        m = (gb > thr).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)))
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        for k in range(1, n):
            if st[k, 4] < 0.003 * w * h:
                continue
            pts = np.column_stack(np.where(lab == k))[:, ::-1].astype(np.float32)
            r = cv2.minAreaRect(pts)
            lungo, corto = max(r[1]), max(1.0, min(r[1]))
            if lungo / corto >= 5 and lungo >= 0.25 * w:
                cand.append((lungo / corto * lungo, r))
    cand.sort(key=lambda t: -t[0])
    return cand[0][1] if cand else None


def _H_dalla_scatola(r):
    """Le due omografie possibili (retro dei tasti su un lato lungo o sull'altro) da una scatola."""
    box = cv2.boxPoints(r).astype(np.float64)
    c = box - box.mean(0)
    if c[1][0] * c[2][1] - c[1][1] * c[2][0] < 0:           # in senso orario nell'immagine
        box = box[::-1]
    if np.linalg.norm(box[1] - box[0]) < np.linalg.norm(box[2] - box[1]):
        box = np.roll(box, -1, 0)                           # il primo lato e' il lungo
    u0, u1 = G.u_bianco(G.NOTA_MIN), G.u_bianco(G.NOTA_MAX) + 1.0
    src = np.float32([[u0, 0], [u1, 0], [u1, G.LW], [u0, G.LW]])
    return [cv2.getPerspectiveTransform(src, np.float32(np.roll(box, -k, 0))).astype(float)
            for k in (0, 2)]


def griglia_da_immagine(g, Hi):
    """La griglia del fotogramma 0 allineata all'immagine: `(H, correlazione)` o None.

    Parte dalla stima di `H_iniziale` e dalle due orientazioni della fascia chiara trovata
    (`_scatola_tastiera`), le allinea tutte con ECC e tiene quella che combacia meglio. Un
    risultato e' accettato solo se correla bene (>= 0,6), non e' specchiato e lascia almeno 6 tasti
    bianchi dentro l'immagine.
    """
    partenze = [np.asarray(Hi, dtype=float)]
    r = _scatola_tastiera(g)
    if r is not None:
        partenze += _H_dalla_scatola(r)
    migliore = None
    for H in partenze:
        try:
            ris = _ecc_griglia(g, H)
        except (cv2.error, np.linalg.LinAlgError, ValueError):
            ris = None
        if ris is None:
            continue
        He, cc = ris
        if cc < 0.6 or He[0, 0] <= 0 or He[1, 1] <= 0 or not np.isfinite(He).all():
            continue
        h, w = g.shape
        dentro = sum(1 for n in G.BIANCHI
                     if 0 <= G.proietta(He, [(G.u_bianco(n) + 0.5, G.LW / 2)])[0][0] < w
                     and 0 <= G.proietta(He, [(G.u_bianco(n) + 0.5, G.LW / 2)])[0][1] < h)
        if dentro < 6:
            continue
        if migliore is None or cc > migliore[1]:
            migliore = (He, cc)
    if migliore is None:
        return None
    return _adatta_retro(g, migliore[0], migliore[1])


def _adatta_retro(g, H, cc):
    """Sposta il BORDO POSTERIORE della griglia dove cominciano davvero i bianchi visibili.

    Il modello mette il retro dei tasti a v=0, ma su una tastiera digitale i bianchi visibili
    cominciano piu' in basso (sotto la copertura): l'allineamento fa un compromesso e i riquadri
    dei neri sporgono sopra le punte vere (misurato: circa 12 px su tasti da 9 px). Si legge la
    luminosita' lungo la colonna centrale di ogni bianco (li' non ci sono neri), si trova dove
    passa da scuro a chiaro e si prende la mediana. Poi si ricalibra la v in modo che il fronte
    resti dov'e' (v = LW) e i neri finiscano dove finivano (la punta bassa combaciava): ritorna
    `(H, correlazione, lb)` con `lb` la nuova lunghezza dei neri in unita' di v.
    """
    h, w = g.shape[:2]
    gb = cv2.GaussianBlur(g, (0, 0), 1.0).astype(np.float32)
    vs = np.arange(-1.0, 3.01, 0.1)
    trovati = []
    for n in G.BIANCHI:
        u = G.u_bianco(n) + 0.5
        p = G.proietta(H, [(u, float(v)) for v in vs])
        if not (np.all(p[:, 0] >= 1) and np.all(p[:, 0] < w - 1) and np.all(p[:, 1] >= 1)
                and np.all(p[:, 1] < h - 1)):
            continue
        b = cv2.remap(gb, p[:, 0].astype(np.float32).reshape(1, -1), p[:, 1].astype(np.float32).reshape(1, -1),
                      cv2.INTER_LINEAR).ravel()
        scuro, chiaro = float(np.median(b[:5])), float(np.median(b[-6:]))
        if chiaro - scuro < 40:                          # niente contrasto (mano, ombra): non conta
            continue
        sopra = np.where(b > 0.5 * (scuro + chiaro))[0]
        if len(sopra):
            trovati.append(float(vs[sopra[0]]))
    if len(trovati) < 8:
        return H, cc, G.LB
    vb = float(np.median(trovati))
    if abs(vb) < 0.4 or vb > 2.5:                        # gia' a posto (o misura assurda)
        return H, cc, G.LB
    k = (G.LW - vb) / G.LW                   # v nuova in [0, LW]  <->  v vecchia in [vb, LW]
    A = np.array([[1.0, 0.0, 0.0], [0.0, k, vb], [0.0, 0.0, 1.0]])
    return np.asarray(H, dtype=float) @ A, cc, (G.LB - vb) / k


def griglia_nel_ritaglio(frame, rect, ancora=False, estremi=None, verticale=None,
                         campioni_video=None, obliqua=False):
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
    altri candidati, e infine la y misurata si riscrive (`riga_y_misurata`). L'inclinazione delle
    verticali però `affina` non la sa (sul fronte dei bianchi non ha corrispondenze) e quella che
    ne esce è rumore: si azzera (`bordi_verticali_x`) prima di riancorare la x, altrimenti la
    griglia si stacca dai tasti sempre di più verso destra (+10 px a DO8 su `2024-09-02_20-00-16`).
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
    # Il candidato "obliquo" (vedi `candidato_obliquo`) ha l'ancoraggio suo: dentro questa fascia
    # `H_iniziale` non ha niente da leggere -- il blocco dei neri e' alto 15 righe, la riga di
    # misura di `_H_iniziale_classico` cade fuori e il profilo di colonne su una tastiera obliqua
    # non e' una misura -- mentre `H_obliqua` legge i neri uno per uno e li' ne aggancia 47.
    # Se l'ancoraggio obliquo non riesce si resta su `H_iniziale`, come tutti gli altri candidati.
    Ho = G.H_obliqua(r) if obliqua else None
    if Ho is not None:
        Hi = np.asarray(Ho[0], dtype=float)
        print(f"[griglia] ancoraggio obliquo: {Ho[1]} inlier sui neri, "
              f"passo {G.passo_griglia(Hi):.2f} px")
    else:
        Hi = np.asarray(G.H_iniziale(r), dtype=float)
    ecc_cc = None                      # correlazione dell'allineamento all'immagine (se fatto)
    lb_nero = G.LB
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
        # `affina` non sa nulla dell'inclinazione delle verticali (nessuna corrispondenza sul
        # fronte dei bianchi): la sbandata che ne esce è rumore di una direzione non vincolata
        # (misurato +0,137 su questa ripresa contro un vero 0,02), quindi si azzera prima di
        # riancorare la x agli estremi misurati. Vedi `bordi_verticali_x`.
        H = riancora_x(bordi_verticali_x(Hf), estremi, rect) if k >= 10 else H0
    else:
        H0 = Hi
        if verticale is None:
            # Senza misure su tutto il pezzo la griglia del fotogramma 0 la si allinea
            # all'immagine (vedi `griglia_da_immagine`): `H_iniziale` da sola sbaglia y e x.
            ris = griglia_da_immagine(g, Hi)
            if ris is not None:
                H0 = ris[0]
                ecc_cc, lb_nero = ris[1], ris[2]
                print(f"[griglia] allineata all'immagine (ECC, correlazione {ris[1]:.2f}, neri lunghi {lb_nero:.1f})")
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
    if ecc_cc is not None:
        info["ecc_cc"] = round(float(ecc_cc), 3)
        info["lb"] = round(float(lb_nero), 2)
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
    # E la punta dei NERI misurata (`fronte_neri`), che serve quando la punta della scala verticale
    # esce corta: lì i riquadri dei neri sono a `G.LB` di una scala sbagliata e si fermano anche
    # loro a metà tasto. La coppia (neri, bianchi) deve stare nei rapporti dei pianoforti veri:
    # il controllo è dentro `lb_al_fronte`, che i neri li confronta coi bianchi misurati qui sopra.
    info["lb_fronte"] = lb_al_fronte(verticale, rect, x2 - x1, info.get("lw_fronte"))
    return info


_NCC_PROFILO_MIN = 0.45     # sotto questa NCC il passo del profilo non è una prova (vedi `verdetto`)
_AVVIO_CIECO_S = 4.0        # quanti secondi di avvio si guardano se il primo fotogramma non legge
_AVVIO_CIECO_PASSO = 0.5    # ogni quanto si cerca il primo fotogramma che legge (`avvio_utile`)
_AVVIO_CIECO_BUONO = 0.15   # NCC in più di `_NCC_PROFILO_MIN` perché il fotogramma sia "letto bene"
# IL SECONDO PARERE QUANDO IL PROFILO NON LEGGE (le chiavi misurate una per una, `x_tasti_misurata`).
# Il confronto col profilo è il controllo sul passo della griglia, ma su una ripresa dove il profilo
# non legge (NCC sotto `_NCC_PROFILO_MIN`) quel controllo non c'è, e lì il verdetto diceva "incerto"
# anche su una griglia giusta: misurato sull'esempio 69 (`2024-09-02_20-00-16`, pianoforte fermo e
# tastiera intera inquadrata) il profilo dava 115,3 px = 4,3 tasti contro i 27,0 veri, con NCC 0,308,
# su una griglia che nel controllo sta sui tasti con 0 px di scarto agli estremi e 154 inlier.
# Su queste riprese il secondo parere lo danno i tasti stessi, ed è più forte del profilo:
# `x_tasti_misurata` misura OGNI bordo bianco e OGNI nero lungo TUTTO il video e conta quante misure
# stanno col modello (le altre sono mani, maniche, riflessi). Sulla ripresa dell'esempio 69 sono 85
# misure coerenti su 87 (53 bordi e 31 neri; 2 fuori dal consenso, 4 tasti sotto le mani ipotizzati
# dal vicinato) e l'escursione è 0 tasti. La soglia sta sotto la peggiore delle griglie ancorate già
# misurate (64-91 misure su 24 passi 0 in `web_runs/_prepara`) e sopra il pavimento di
# `x_tasti_misurata`, che sotto 10 misure coerenti non restituisce niente (`tasti_misurati` non c'è
# e il secondo parere resta quello di prima).
_TASTI_MISURATI_MIN = 40        # misure coerenti perché la griglia ancorata si confermi da sola
_TASTI_MISURATI_INCOERENTI = 0.10   # quanta parte di quelle misure può restare fuori dal consenso
_TASTI_MISURATI_ESCURSIONE = 1      # di quanti tasti può scorrere la griglia fra i due capi


def _tasti_misurati_ok(info):
    """La griglia ancorata agli estremi si conferma da sola, tasto per tasto, lungo tutto il video?

    È il secondo parere sul passo quando il profilo non legge (vedi `_TASTI_MISURATI_MIN`): al posto
    del profilo si guardano le misure di `x_tasti_misurata`, che sono i tasti veri, misurati dove si
    vedono e ipotizzati dal vicinato dove una mano li copre. Si accetta solo la griglia ANCORATA agli
    estremi misurati: su quella il passo non è stimato ma è lo span misurato diviso 52 tasti (vedi
    `passo_medio`), quindi la misura dei tasti lo conferma; su una griglia non ancorata il passo se lo
    stima da sé e il profilo resta il solo controllo indipendente che c'è. Se `x_tasti_misurata` non
    ha misurato niente (`tasti_misurati` assente: sotto 10 misure coerenti non restituisce nulla) il
    secondo parere non c'è e chi chiama tiene il verdetto di prima.
    """
    if not info.get("ancorata"):
        return False
    tm = info.get("tasti_misurati") or {}
    misurati = int(tm.get("misurati") or 0)
    if misurati < _TASTI_MISURATI_MIN:
        return False
    if int(tm.get("incoerenti") or 0) > _TASTI_MISURATI_INCOERENTI * misurati:
        return False
    return int(tm.get("escursione_tasti") or 0) <= _TASTI_MISURATI_ESCURSIONE


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
    neri, la plausibilità, i tasti fuori). Dal 10/10/2026, se la griglia è ancorata agli estremi
    misurati e i tasti misurati uno per uno la confermano (vedi `_tasti_misurati_ok`), quel secondo
    parere c'è e il profilo illeggibile non è una ragione: il verdetto resta "ok".

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
    # I tasti bianchi nella finestra si controllano PRIMA del profilo, e non dopo: sopra 58 la
    # finestra è più larga della tastiera intera (52 bianchi) e la griglia è scivolata sulla cassa,
    # sullo sfondo o sul maglione di chi suona (misurato 59,2 sulla cassa; 70,6 su
    # `2024-02-15_21-33-36`, dove la banda dei neri era finita sul tappeto a y 593-705 e la pagina
    # diceva "il profilo non legge" — vero, ma non dice cosa guardare). E' il motivo che si vede nel
    # controllo, quindi è quello da leggere per primo quando il verdetto ha più di una ragione.
    # Il caso buono che supera i 58 è la tastiera intera inquadrata con qualche tasto oltre il
    # bordo e il modello che combacia a tutta l'immagine (`ecc_cc` >= 0,8): lì non si contesta.
    if auto and info["tasti_nel_frame"] > 58 and float(info.get("ecc_cc") or 0.0) < 0.8:
        problemi.append(("incerto", f"{info['tasti_nel_frame']:.0f} tasti bianchi nella finestra "
                                    f"(un pianoforte ne ha 52): la griglia non è appoggiata sui "
                                    f"tasti, è scivolata sulla cassa o sullo sfondo"))
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
        if scarto > limite and illeggibile and float(info.get("ecc_cc") or 0.0) >= 0.8:
            pass      # il profilo non legge, ma l'allineamento del modello a TUTTA l'immagine
                      # (ECC, correlazione >= 0,8) conferma la griglia: un secondo parere c'e'
        elif scarto > limite and illeggibile and _tasti_misurati_ok(info):
            pass      # il profilo non legge e l'ECC non c'e' (sul candidato ancorato non si fa,
                      # vedi `griglia_nel_ritaglio`), ma i tasti misurati uno per uno lungo tutto
                      # il video confermano la griglia: il secondo parere c'e' lo stesso
        elif scarto > limite and illeggibile:
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
    # contenerla (52 tasti bianchi o più); il controllo sui tasti di troppo (sopra 58) è più sopra,
    # prima del profilo. Sotto 52 la finestra NON può contenere la tastiera: è un primo piano, la
    # tastiera continua fuori dai bordi laterali, e sia i tasti che ci entrano sia quelli del
    # modello che restano fuori dal ritaglio sono numeri che escono dalla geometria del fotogramma,
    # non dalla griglia (misurato sul primo piano dell'utente: 13,7 tasti nella finestra e 36,8
    # fuori, con la griglia appoggiata sui tasti, 58 inlier e il passo a -0,9% dal profilo). Su un
    # primo piano restano le stesse verifiche di sempre — passo contro profilo e `inlier` — e una
    # finestra troppo stretta per dire qualcosa non passa lo stesso: `inlier` sono i punti che
    # reggono l'omografia sui neri e con pochi tasti inquadrati scendono da soli (sotto 40 è
    # rifiuto).
    tastiera_ci_sta = info["tasti_nel_frame"] >= 52
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


def _poligono_misurato_float(H, rect, x_tasti, n, lw=G.LW, lb=G.LB):
    """Il riquadro di un tasto nel fotogramma intero (4 punti float), con la x MISURATA tasto per tasto.

    Le due regole del passo 0: dove il tasto si vede la sagoma combacia col tasto trovato, dove
    è coperto si ipotizza dal vicinato (`dx_del_tasto`). Per un tasto nero la correzione è quella
    del suo centro — il riquadro trasla rigido, la larghezza resta quella del modello — mentre i
    due bordi di un tasto bianco sono due fessure diverse e ognuna ha la sua misura.

    `lw` è la lunghezza dei tasti bianchi in unità del modello: `G.LW` (6,2) quando il fronte non
    è stato misurato, altrimenti `lw_fronte` (`lw_al_fronte`), che è dove finiscono davvero i
    tasti. I neri restano a `G.LB`: le loro punte sono la misura della scala verticale.

    Float e non interi: il riquadro del fotogramma 0 viene TRASPORTATO dal moto della tastiera
    (`poligoni_griglia`), e arrotondare prima di trasportare metterebbe l'errore due volte.
    """
    x1, y1 = int(rect[0]), int(rect[1])
    if G.e_nero(n):
        d = dx_del_tasto(x_tasti, "nero", G.u_nero(n))
        a, b, fondo = G.u_nero(n) - G.BW / 2, G.u_nero(n) + G.BW / 2, lb
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
        fuori.append((float(x) + d + x1, float(y) + y1))
    return np.float64(fuori)


def poligono_tasto_misurato(H, rect, x_tasti, n, lw=G.LW, lb=G.LB):
    """Come `_poligono_misurato_float`, ma coi vertici arrotondati ai pixel (per disegnare)."""
    return np.int32(np.round(_poligono_misurato_float(H, rect, x_tasti, n, lw, lb)))


def poligoni_griglia(H, rect, info):
    """La griglia del FOTOGRAMMA 0, completa: `{nota: 4 punti}` nel fotogramma intero.

    E' LA griglia: quella con la y misurata (`riga_y_misurata`), la x tasto per tasto
    (`x_tasti_misurata`) e i fronti misurati (`lw_al_fronte`, `lb_al_fronte`). Il video della
    griglia non la rifà più dal modello a ogni fotogramma: la trasporta col moto della tastiera
    (`trasporta_poligoni`). Si calcola una volta e si tiene in `info["_poligoni"]`.

    `lw_fronte` e `lb_fronte` sono i fronti misurati su tutto il pezzo: dove ci sono, i riquadri
    arrivano alla punta vera del tasto invece che a quella del modello (vedi `lw_al_fronte` e
    `lb_al_fronte`: la punta dei neri, che è la scala verticale, può uscire corta).
    """
    if info.get("_poligoni") is not None:
        return info["_poligoni"]
    x_tasti = info.get("_x_tasti")
    lw = info.get("lw_fronte") or G.LW
    lb = info.get("lb_fronte") or info.get("lb") or G.LB
    Hf = _H_assoluta(H, rect)       # griglia locale -> frame intero (con la prospettiva: T @ H, non H[:, 2] += offset)
    poli = {}
    for n in list(G.BIANCHI) + list(G.NERI):
        if x_tasti:
            poli[n] = _poligono_misurato_float(H, rect, x_tasti, n, lw, lb)
        else:
            poli[n] = np.float64(G.poligono_tasto(Hf, n, lw=lw, lb=lb))
    info["_poligoni"] = poli
    return poli


def trasporta_poligoni(poli, M):
    """I riquadri del fotogramma 0 portati su un altro fotogramma dall'omografia `M` (0 -> t)."""
    if M is None:
        return poli
    chiavi = list(poli)
    p = G.proietta(np.asarray(M, dtype=float), np.concatenate([poli[n] for n in chiavi]))
    return {n: p[4 * i:4 * i + 4] for i, n in enumerate(chiavi)}


def disegna_griglia_misurata(frame, H, rect, x_tasti, etichette=True, lw=G.LW, lb=G.LB):
    """La griglia disegnata coi riquadri sui tasti: la stessa grafica di `G._disegna`.

    Verdi i tasti bianchi, blu i neri, col nome della nota in fondo al riquadro. `lw` è dove
    finiscono i bianchi: `lw_fronte` quando il fronte è stato misurato (vedi `lw_al_fronte`), `lb`
    dove finiscono i neri (`lb_fronte`, vedi `lb_al_fronte`).
    """
    im = frame.copy()
    for n in G.BIANCHI:
        cv2.polylines(im, [poligono_tasto_misurato(H, rect, x_tasti, n, lw, lb)], True,
                      (60, 220, 60), 2, cv2.LINE_AA)
    for n in G.NERI:
        cv2.polylines(im, [poligono_tasto_misurato(H, rect, x_tasti, n, lw, lb)], True,
                      (255, 160, 30), 2, cv2.LINE_AA)
    if etichette:
        h, w = im.shape[:2]
        for n in G.BIANCHI:
            p = poligono_tasto_misurato(H, rect, x_tasti, n, lw, lb)
            x, y = (p[2] + p[3]) / 2
            if 0 < x < w - 14 and 0 < y < h - 4:
                t = G.nome(n)
                pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
                cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return im


def disegna_griglia_al_fronte(frame, Hf, lw, lb=G.LB):
    """`G._disegna` (nessuna misura della x tasto per tasto) coi tasti lunghi fino al fronte.

    Senza questa, quando il fronte dei bianchi è stato misurato l'unica strada era disegnare la
    geometria del modello e i riquadri si fermavano prima della punta del tasto: qui i bianchi
    arrivano a `lw` e i neri a `lb` (i fronti misurati: `lw_al_fronte` e `lb_al_fronte`).
    """
    im = frame.copy()
    for n in G.BIANCHI:
        cv2.polylines(im, [np.int32(G.poligono_tasto(Hf, n, lw=lw, lb=lb))], True,
                      (60, 220, 60), 2, cv2.LINE_AA)
    for n in G.NERI:
        cv2.polylines(im, [np.int32(G.poligono_tasto(Hf, n, lw=lw, lb=lb))], True,
                      (255, 160, 30), 2, cv2.LINE_AA)
    h, w = im.shape[:2]
    for n in G.BIANCHI:
        p = G.poligono_tasto(Hf, n, lw=lw, lb=lb)
        x, y = (p[2] + p[3]) / 2
        if 0 < x < w - 14 and 0 < y < h - 4:
            t = G.nome(n)
            pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
            cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(im, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return im


def sovrapponi_controllo(frame, rect, info, H, M=None, rect_viola=None):
    """Disegna su un fotogramma il rettangolo del ritaglio e la griglia trovata.

    UN RIQUADRO PER TASTO: la stessa grafica del motore (`griglia_prospettica._disegna`, quella
    di `primo_frame_griglia.jpg`), verdi i tasti bianchi, blu i neri, col nome della nota.
    Lo usano sia l'immagine ferma (`immagine_controllo`) sia il video della griglia
    (`scrivi_video_griglia`), così quel che si guarda nei due file è la stessa cosa.

    E' il controllo a occhio prima di addestrare: se la griglia e' giusta i riquadri stanno
    appoggiati uno per tasto; se e' sbagliata finiscono sulla cassa, fuori dalla tastiera, o
    non combaciano coi bordi — e si vede subito, prima di ore di addestramento.

    LA GRIGLIA E' UNA SOLA: quella del fotogramma 0 (`poligoni_griglia`: y misurata sui neri veri,
    x tasto per tasto, fronte dei bianchi misurato). Con `M` (l'omografia dal fotogramma 0 a
    QUESTO fotogramma, vedi `insegui_griglia`) i riquadri, il ritaglio magenta e i due bordi gialli
    (LA0 e DO8) si trasportano tutti con la STESSA `M`: griglia e ritaglio non possono
    raccontare due stime diverse. Senza `M` (immagine ferma) e' il fotogramma 0 com'e'.

    Quando la tastiera e' stata misurata su tutto il video (`estremi`) si segnano anche i due
    bordi veri — LA0 e DO8 — e i numeri dei tasti neri: quelli dicono se i riquadri stanno
    sui tasti o accanto (i neri "coperti" sono sotto una mano o un tablet: lì la griglia va
    disegnata lo stesso, il tasto c'è).
    """
    x1, y1, x2, y2 = (int(v) for v in rect)
    poli = trasporta_poligoni(poligoni_griglia(H, rect, info), M)
    im = G._disegna(frame, None, poligoni=poli)          # un riquadro per tasto, grafica del motore
    est = info.get("estremi")
    if est:
        for x, t in ((est["x_la0"], "LA0"), (est["x_c8"], "DO8 fine")):
            a = np.float64([[x, y1], [x, y2]])
            if M is not None:                     # i bordi misurati al fotogramma 0 seguono la tastiera
                a = G.proietta(np.asarray(M, dtype=float), a)
            pa, pb = (int(round(a[0][0])), int(round(a[0][1]))), (int(round(a[1][0])), int(round(a[1][1])))
            cv2.line(im, pa, pb, (0, 255, 255), 2)
            cv2.putText(im, t, (pb[0] + 4, pb[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 4,
                        cv2.LINE_AA)
            cv2.putText(im, t, (pb[0] + 4, pb[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255),
                        1, cv2.LINE_AA)
    if M is not None or rect_viola is not None:
        # il ritaglio si muove con la tastiera: stessa `M` della griglia. `rect_viola` e' il ritaglio
        # ALLARGATO ai tasti che compaiono dopo (`canvas_esteso`): puo' uscire dal fotogramma
        pol = np.int32(np.round(_angoli_finestra(rect_viola or rect, M if M is not None else np.eye(3))))
        cv2.polylines(im, [pol], True, (255, 0, 255), 2, cv2.LINE_AA)
        etichetta = "QUESTO E' IL RITAGLIO (SEGUE LA TASTIERA)"
        ex, ey = max(int(pol[0][0]) + 8, 8), max(int(pol[0][1]) + 24, 24)
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
    ten = (ins or {}).get("tenuta")
    if ten:
        righe.append(f"tenuta in movimento: griglia sui neri in {ten['campioni_buoni']}/{ten['campioni']} "
                     f"campioni (scarto x massimo {ten['scarto_max_px']} px, soglia {ten['soglia_px']})")
    tm = info.get("tasti_misurati")
    if tm:
        righe.append(f"x tasto per tasto: {tm['misurati']} misurati ({tm['neri']} neri, "
                     f"{tm['bordi']} bordi), {tm['incoerenti']} incoerenti, "
                     f"{tm['ipotizzati']} ipotizzati; escursione {tm['escursione_tasti']} tasti")
    if info.get("lw_fronte"):
        righe.append(f"fronte dei tasti bianchi misurato: lunghi {info['lw_fronte']} tasti "
                     f"(il modello ne disegna {G.LW:.1f}): i riquadri verdi arrivano fin lì")
    if info.get("lb_fronte"):
        righe.append(f"punta dei tasti neri misurata: lunghi {info['lb_fronte']} tasti "
                     f"(il modello ne disegna {G.LB:.1f}): i riquadri blu arrivano fin lì")
    av = info.get("avvio_cieco")
    if av:
        righe.append(f"avvio: il fotogramma 0 non legge, si parte da {av['inizio_usato']:.1f} s "
                     f"(chiesto {av['inizio_chiesto']:.1f} s)")
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

_LARGHEZZA_MAX = 3000           # larghezza massima del video preparato quando il ritaglio contiene tutte le 88 note
_SOGLIA_SEGUI_TASTI = 0.35   # sopra questo spostamento (in tasti) il ritaglio fisso perde la tastiera
# QUANDO IL MOTO MISURATO NON VALE NIENTE E SI BUTTA (`_moto_angoli`, in `main`): se gli ANGOLI della
# zona dei tasti si spostano di meno di mezzo tasto su tutto il pezzo, seguire il moto non puo'
# cambiare l'etichetta di nessuna nota -- l'etichettatura e' per tasto, e mezzo tasto e' la stessa
# soglia con cui `griglia_sui_tasti` accetta la griglia -- e inseguire costa due cose che si vedono:
# il video preparato si ricampiona a ogni fotogramma e la griglia inseguita puo' staccarsi dai tasti.
# Su `2024-09-02_20-00-16` (il pianoforte fermo dell'esempio 69) il moto inseguito vale 0,2 tasti
# (5,3 px) mentre la griglia trasportata arrivava a 12 px di scarto in y al secondo 49: "traballante",
# e il verdetto "incerto". Con l'identita' la griglia del fotogramma 0 vale per tutto il video, che e'
# quello che il messaggio dell'inseguimento prometteva gia' ("ritaglio e griglia del primo fotogramma
# vanno bene così") senza pero' buttare via `Ms`.
# Non e' una soglia da tarare sul rumore: il moto che arriva qui e' GIA' LISCIATO a fase zero
# (`_liscia_angoli`), e su una camera ferma vale pochi px su un passo di 27-33 px. Mezzo tasto sta
# invece sopra il margine che l'inseguimento stesso usa per dire "la camera sta ferma" (0,35 tasti):
# cosi' si butta solo quel che non si vede, e uno zoom o una rotazione -- che spostano gli angoli
# senza spostare il centro della zona -- restano misurati e inseguiti (vedi `_moto_angoli`).
_ANGOLI_MIN_TASTI = 0.5      # sotto mezzo tasto il moto misurato si butta: resta la griglia del fotogramma 0
_FC_MIN = 0.3                # filtro del moto: frequenza di taglio a riposo (Hz): il tremolio non passa
_FC_BETA = 0.08              # ... e quanto sale con la velocita' (px/s): in movimento NON ritarda
_MIN_INLIER_REG = 20         # inlier minimi per dire "questo fotogramma e' agganciato al fotogramma 0"
_MAX_SEGUI_TASTI = 12.0      # oltre questo la tastiera non si sta muovendo: la griglia e' persa

# --- la tastiera si muove? Lo dicono SOLO i 4 angoli dei tasti bianchi (vedi `tastiera_ferma`) --
# La tolleranza NON e' una soglia nuova da tarare: e' la stessa domanda che l'inseguimento si fa da
# sempre quando conclude "la camera sta ferma" (`_SOGLIA_SEGUI_TASTI` = 0,35 tasti, cioe' ~12 px sul
# passo da 33 px di `2024-02-15_21-33-36`), solo misurata sugli angoli invece che sul moto inseguito.
# Stringerla non si puo': la misura ha un suo rumore (ai bordi del fotogramma l'omografia e'
# estrapolata, e la registrazione e' meno vincolata) che sui due pezzi con la camera ferma arriva a
# 2,7 px in x. Con le 2 px di prima il video INTERO di `2024-02-15_21-33-36` veniva dichiarato
# "si muove" per un fotogramma solo, mentre l'inseguimento su quel pezzo misurava 0,04 tasti e
# scriveva "la camera sta ferma". In x la misura e' piu' precisa che in y (i bordi dei tasti la
# vincolano: 1,9 px contro 5,9 px sullo stesso fotogramma di `2024-09-02_20-00-16`), da cui la
# stessa asimmetria di `verifica_griglia`.
_TOLLERANZA_ANGOLI_PX = 8.0      # scostamento in x (px del fotogramma) che conta come "si muove"
_TOLLERANZA_ANGOLI_Y_PX = 12.0   # scostamento in y (px): la y e' vincolata di meno (vedi sopra)
# UN FOTOGRAMMA STORTO DA SOLO NON E' MOVIMENTO, E NON LO SONO NEPPURE QUATTRO SPARSI: una mano che
# sfiora i bordi, una sfocatura, una registrazione andata male durano un fotogramma, non una fila. Si
# perdonano `_ANGOLI_FUORI_MAX` campioni storti DI FILA (sul pezzo fermo di `2024-02-15_21-33-36` la
# verifica della griglia ne trovava 2 su 60 campioni sparsi e li ignorava); da `_ANGOLI_FUORI_MAX` + 1
# di fila in poi la camera si sta muovendo da un pezzo e si insegue.
# IL CONTO E' DI FILA, NON TOTALE, ed e' la correzione del 10/10/2026. Su `2024-09-02_20-00-16` (il
# pianoforte FERMO dell'esempio 69) il conteggio TOTALE -- 4 campioni storti su 143, il 2,8%, con
# 11,2 px di scostamento massimo contro una soglia di 8 -- bastava a superare il margine di 3 e ad
# accendere l'inseguimento, e da li' la griglia inseguita si e' messa a traballare (scarto in y fino a
# 12 px al fotogramma 1470, cioe' al secondo 49, verdetto "incerto") mentre l'inseguimento stesso, su
# tutto il pezzo, misurava 0,2 tasti e scriveva "la camera sta ferma". Con la fila quei 4 campioni
# sparsi sono quello che sono: rumore della registrazione, e la griglia resta quella del fotogramma 0.
_ANGOLI_FUORI_MAX = 3            # campioni storti DI FILA che si perdonano: dal quarto si insegue
# ...E IL MARGINE IN FOTOGRAMMI NON PUO' BASTARE DA SOLO: se stanno fuori tolleranza piu' di
# `_ANGOLI_FUORI_FRAZIONE` dei campioni non sono fotogrammi storti, e' il pezzo che si muove (o che
# non si misura). Serve anche a un altro guaio, capitato davvero: una costante di prova lasciata nel
# file (`_ANGOLI_FUORI_MAX` a 100000) dichiarava "ferma" un video che si muove di 779 px, con la
# griglia del fotogramma 0 inchiodata addosso e il MIDI sbagliato. Con questa regola non puo' piu'.
_ANGOLI_FUORI_FRAZIONE = 0.10
_ANGOLI_MISURABILI_MIN = 0.85    # sotto questa frazione di campioni misurati non si decide "ferma"
# QUANTO SPESSO SI GUARDA: il controllo costa 17 ms a fotogramma (registrazione + proiezione) e su un
# pezzo che sta fermo va pagato TUTTO fino alla fine, mentre l'inseguimento che si risparmia ne costa
# 25. Guardando un fotogramma ogni 2 il controllo si dimezza (i fotogrammi saltati si consumano con
# `grab`, senza decodificarli) e su 60 s il passo 0 scende da 53 s a ~35 s invece di 48. Un movimento
# vero della tastiera dura decine di fotogrammi, non uno: campionare non puo' farlo sparire.
_PASSO_ANGOLI = 2                # 1 = ogni fotogramma (controllo pieno, il doppio del tempo)
_ANGOLI_ESITO = {"ferma": "non si muove", "si muove": "si muove",
                 "non misurata": "non si riesce a misurare (si insegue come prima)"}


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


def _moto_angoli(Ms, zona, H):
    """Di quanto si spostano, al massimo, i 4 angoli della zona dei tasti su tutto il pezzo (in tasti).

    Serve a decidere se il moto inseguito si puo' BUTTARE e tenere la griglia del fotogramma 0 per
    tutto il video (vedi `_ANGOLI_MIN_TASTI`). `insegui_griglia` riassume il moto con
    `spostamento_tasti`, che e' lo spostamento del CENTRO della zona: uno zoom o una rotazione
    spostano gli angoli -- e cambiano la dimensione o l'inclinazione dei tasti -- senza spostare il
    centro, e buttare via quel moto vorrebbe dire inchiodare la griglia su tasti che nel frattempo
    sono cambiati. Qui si guarda la cosa che conta per la griglia, dove finiscono i suoi 4 angoli,
    con la stessa unita' di `spostamento_tasti` (in tasti, col passo dato dalla scala del modello,
    `hypot(H[0, 0], H[1, 0])`, lo stesso conto di `insegui_griglia` e `verifica_griglia`).

    Ritorna `inf` se non si riesce a misurare: chi chiama, allora, non butta niente.
    """
    if Ms is None or len(Ms) == 0:
        return float("inf")
    zx1, zy1, zx2, zy2 = zona
    ang = np.float64([[zx1, zy1], [zx2 - 1, zy1], [zx2 - 1, zy2 - 1], [zx1, zy2 - 1]])
    try:
        M_arr = np.asarray(Ms, dtype=float)
    except (TypeError, ValueError):
        return float("inf")
    if not np.isfinite(M_arr).all():
        # Una matrice non finita (`Ms` viene da `insegui_griglia`, che ha i suoi ripieghi) NON e' un
        # moto nullo: senza sapere dove e' finita la griglia non si butta niente. (`G.proietta` una
        # matrice di NaN la renderebbe 0,0, cioe' uno spostamento enorme: qui non si sta a sperare.)
        return float("inf")
    try:
        C = np.asarray([G.proietta(M, ang) for M in M_arr], dtype=float)
    except (cv2.error, ValueError, np.linalg.LinAlgError):
        return float("inf")
    if not np.isfinite(C[0]).all():
        return float("inf")
    if not np.isfinite(C).all():                  # i ripieghi di `insegui_griglia`: mai un NaN
        for i in range(1, len(C)):
            if not np.isfinite(C[i]).all():
                C[i] = C[i - 1]
    return float(np.abs(C - C[0]).max()) / max(float(np.hypot(H[0, 0], H[1, 0])), 1.0)


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


def angoli_bianchi(H_abs, lw=G.LW):
    """I 4 angoli ESTERNI della griglia VERDE: il blocco dei tasti BIANCHI, dal retro al fronte.

    In senso orario, come `_angoli_modello`: retro-sinistra, retro-destra, fronte-destra,
    fronte-sinistra. Sono gli stessi angoli che si vedono disegnati (l'unione dei poligoni verdi
    dei bianchi), NON il rettangolo magenta del ritaglio (`rect`) e nemmeno la banda con margine
    che serve al ritaglio (`_banda_tastiera`). Se questi 4 punti non si spostano la tastiera non
    si e' mossa, e la griglia del primo fotogramma vale per tutto il pezzo (`tastiera_ferma`).
    `lw` e' la lunghezza del tasto bianco in unita' del modello (il fronte VERO misurato e'
    `info['lw_fronte']`): il vertice di fronte sta li'.
    """
    u0, u1 = G.u_bianco(G.NOTA_MIN), G.u_bianco(G.NOTA_MAX) + 1.0
    return np.float64(G.proietta(np.asarray(H_abs, dtype=float),
                                 [(u0, 0.0), (u1, 0.0), (u1, lw), (u0, lw)]))


def _quadro_tastiera(H_abs):
    """I 4 angoli della tastiera (tutti i tasti, dal fronte al retro) nel fotogramma, con `H_abs`.

    E' `angoli_bianchi`: qui il nome dice a cosa serve (la maschera e la zona dei tasti), li' cosa
    sono (gli angoli della griglia verde).
    """
    return angoli_bianchi(H_abs)


def _banda_tastiera(H_abs, margine_u=0.5, v0=-0.5, v1=None):
    """La BANDA della tastiera nel fotogramma: tutti i tasti dal retro al fronte, con un po' di margine.

    4 angoli, in senso orario. E' l'area che un ritaglio "giusto" deve contenere: tutta la
    tastiera (anche la parte che il primo fotogramma non mostra) e non il resto della stanza.
    `margine_u` e' in larghezze di bianco ai due lati; `v0`/`v1` in unita' del modello (v=0 retro,
    v=LW fronte) sopra e sotto.
    """
    u0, u1 = G.u_bianco(G.NOTA_MIN) - margine_u, G.u_bianco(G.NOTA_MAX) + 1.0 + margine_u
    v1 = G.LW + 0.9 if v1 is None else v1
    return np.float64(G.proietta(np.asarray(H_abs, dtype=float), [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]))


def stringi_rettangolo(H, rect, forma):
    """Stringe il ritaglio attorno ai soli tasti: `(rect, H)` nuovi, oppure None se non serve.

    Su una ripresa larga il ritaglio automatico puo' essere tutto il fotogramma: tastiera, muro,
    libri, pavimento. Con la griglia allineata all'immagine si sa dove sono i tasti, quindi il
    ritaglio buono e' il riquadro della loro banda (`_banda_tastiera`), dentro il fotogramma.
    Si stringe solo se cosi' l'area scende almeno al 60%: nel primo piano (la tastiera esce dal
    fotogramma) la banda e' gia' quasi tutto il ritaglio e non cambia niente.
    `H` e' nelle coordinate del ritaglio: la nuova H e' quella del nuovo ritaglio.
    """
    h, w = forma
    q = _banda_tastiera(_H_assoluta(H, rect))
    x1, y1 = max(0, int(np.floor(q[:, 0].min()))), max(0, int(np.floor(q[:, 1].min())))
    x2, y2 = min(w, int(np.ceil(q[:, 0].max()))), min(h, int(np.ceil(q[:, 1].max())))
    nuovo = _pari((x1, y1, x2, y2))
    vecchio = _pari(rect)
    if nuovo[2] - nuovo[0] < 40 or nuovo[3] - nuovo[1] < 20:
        return None
    if (nuovo[2] - nuovo[0]) * (nuovo[3] - nuovo[1]) > 0.6 * (vecchio[2] - vecchio[0]) * (vecchio[3] - vecchio[1]):
        return None
    T = np.array([[1.0, 0.0, -nuovo[0]], [0.0, 1.0, -nuovo[1]], [0.0, 0.0, 1.0]])
    return nuovo, T @ _H_assoluta(H, rect)


def canvas_esteso(rect, Ms, H, forma, tetto=2.5):
    """Il ritaglio ALLARGATO ai tasti che compaiono in qualche momento del pezzo.

    Il ritaglio nasce dal primo fotogramma: se la camera si sposta e scopre tasti che il primo non
    mostrava (primo piano: la tastiera esce dal fotogramma) un ritaglio fisso nel piano della
    tastiera li lascerebbe fuori per sempre. Qui, per ogni fotogramma, si porta il suo contorno
    nel piano del fotogramma 0 (con l'inversa del moto), lo si interseca con la banda della
    tastiera e si tiene l'unione di tutti: e' la parte di tastiera che si vede almeno una volta.
    Il ritaglio nuovo contiene quello vecchio (non si restringe mai). Le coordinate possono uscire
    dal fotogramma 0 (anche negative): sono coordinate del PIANO della tastiera, e nel video
    preparato la parte non visibile in un fotogramma resta nera. `tetto` limita la crescita (volte
    la dimensione del ritaglio) contro un moto impazzito.
    """
    h, w = forma
    banda = np.float32(_banda_tastiera(_H_assoluta(H, rect)))
    fr = np.float64([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    x1, y1, x2, y2 = _pari(rect)
    lo, hi = np.float64([x1, y1]), np.float64([x2, y2])
    for M in Ms:
        try:
            P = G.proietta(np.linalg.inv(np.asarray(M, dtype=float)), fr)
            if not np.isfinite(P).all():
                continue
            area, inter = cv2.intersectConvexConvex(banda, np.float32(P))
        except (cv2.error, np.linalg.LinAlgError, ValueError):
            continue
        if area > 1.0 and inter is not None:
            pts = inter.reshape(-1, 2).astype(np.float64)
            lo, hi = np.minimum(lo, pts.min(0)), np.maximum(hi, pts.max(0))
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    lw_, lh_ = tetto * (x2 - x1) / 2.0, tetto * (y2 - y1) / 2.0
    lo = np.maximum(lo, [cx - lw_, cy - lh_])
    hi = np.minimum(hi, [cx + lw_, cy + lh_])
    return _pari((int(np.floor(lo[0])), int(np.floor(lo[1])), int(np.ceil(hi[0])), int(np.ceil(hi[1]))))


# ======================================================================================
#  LA TASTIERA COMPLETA: ogni nota, dove sta in ogni fotogramma, e quanto si sa davvero
# ======================================================================================

def _angoli_modello(n, lw=G.LW, lb=G.LB):
    """I 4 angoli del tasto `n` nel piano del modello (u, v): retro-sinistra, retro-destra, fronte-destra, fronte-sinistra."""
    if G.e_nero(n):
        a, b = G.u_nero(n) - G.BW / 2, G.u_nero(n) + G.BW / 2
        return [(a, 0.0), (b, 0.0), (b, lb), (a, lb)]
    a = G.u_bianco(n)
    return [(a, 0.0), (a + 1.0, 0.0), (a + 1.0, lw), (a, lw)]


def _H_continuata(H_abs, forma):
    """Un'omografia per ESTRAPOLARE i tasti lontani dal fotogramma: la vera se regge, altrimenti l'affine.

    Un'omografia stimata su 14 tasti, portata a 40 tasti di distanza, puo' mandare i punti
    all'infinito (il denominatore passa per zero) o dall'altra parte della camera. Se su tutto
    l'intervallo esteso dei tasti e' ben condizionata si usa cosi' com'e'; altrimenti si usa la sua
    linearizzazione (affine) al centro del fotogramma: tasti equidistanti e paralleli, che e' la
    migliore ipotesi quando non si sa com'e' la prospettiva li'.
    """
    H = np.asarray(H_abs, dtype=float)
    h, w = forma
    u0, u1 = G.u_bianco(G.NOTA_MIN) - 8.0, G.u_bianco(G.NOTA_MAX) + 9.0
    pts = np.array([[u0, 0, 1], [u1, 0, 1], [u1, G.LW, 1], [u0, G.LW, 1]], float)
    p = pts @ H.T
    centro = np.array([w / 2.0, h / 2.0, 1.0])
    q = np.linalg.solve(H, centro)
    q = q / q[2]
    wc = (np.array([q[0], q[1], 1.0]) @ H.T)[2]
    if np.all(p[:, 2] * np.sign(wc) > 0.3 * abs(wc)):
        xy = p[:, :2] / p[:, 2:3]
        if np.abs(xy).max() < 8 * max(w, h):
            return H
    uc, vc = float(q[0]), float(q[1])
    e = 1e-3
    def f(u, v):
        r = H @ np.array([u, v, 1.0])
        return r[:2] / r[2]
    p0 = f(uc, vc)
    ju = (f(uc + e, vc) - f(uc - e, vc)) / (2 * e)
    jv = (f(uc, vc + e) - f(uc, vc - e)) / (2 * e)
    A = np.array([[ju[0], jv[0], p0[0] - ju[0] * uc - jv[0] * vc],
                  [ju[1], jv[1], p0[1] - ju[1] * uc - jv[1] * vc],
                  [0.0, 0.0, 1.0]])
    return A


def poligoni_nel_tempo(H_abs, Ms, note, forma, lw=G.LW, lb=G.LB, dx=None):
    """Il rettangolo di ogni nota in ogni fotogramma: `P` di forma (T, K, 4, 2), `vera` (K,), `Hc`.

    `Ms[t]` e' il moto della tastiera dal fotogramma 0 al fotogramma t. Ogni tasto usa
    l'omografia VERA se al fotogramma 0 cade vicino al fotogramma (dentro una volta e mezzo la
    sua dimensione, davanti alla camera), altrimenti quella continuata (`_H_continuata`):
    cosi' i tasti che si vedono sono esatti e quelli lontani, che si ipotizzano, non vanno
    all'infinito. Dove il punto sta dietro la camera ci sono NaN.

    `dx` (K, 4) e' lo scarto in x dei 4 angoli al fotogramma 0, pixel del fotogramma
    (`dx_tasti_cornici`): le misure tasto per tasto. Si somma al fotogramma 0 e da li' lo porta
    il moto — e' quel che fa il disegno (`trasporta_poligoni(poligoni_griglia(...))`) — quindi i
    riquadri di `P` sono gli stessi che si vedono nel video della griglia. Senza `dx` (o con
    tutti zero) resta il solo modello.
    """
    H = np.asarray(H_abs, dtype=float)
    Hc = _H_continuata(H, forma)
    h, w = forma
    C = np.array([[(u, v, 1.0) for (u, v) in _angoli_modello(n, lw, lb)] for n in note])    # (K,4,3)
    p0 = C @ H.T
    q = np.linalg.solve(H, np.array([w / 2.0, h / 2.0, 1.0]))
    sg = np.sign((np.array([q[0] / q[2], q[1] / q[2], 1.0]) @ H.T)[2]) or 1.0
    w0 = p0[..., 2] * sg
    with np.errstate(divide="ignore", invalid="ignore"):
        xy0 = p0[..., :2] / p0[..., 2:3]
    vicina = ((w0 > 1e-6).all(1) & (xy0[..., 0].min(1) > -1.5 * w) & (xy0[..., 0].max(1) < 2.5 * w)
              & (xy0[..., 1].min(1) > -1.5 * h) & (xy0[..., 1].max(1) < 2.5 * h))
    Ms = np.asarray(Ms, dtype=float)
    off = None if dx is None else np.asarray(dx, dtype=float)
    n_t, n_k = len(Ms), len(note)
    P = np.full((n_t, n_k, 4, 2), np.nan, dtype=np.float32)
    for gruppo, Hg in ((vicina, H), (~vicina, Hc)):
        idx = np.where(gruppo)[0]
        if len(idx) == 0:
            continue
        Pg = np.einsum("ij,kcj->kci", Hg, C[idx])                             # (Kg,4,3) al fotogramma 0
        if off is not None:
            # Lo scarto entra in coordinate omogenee: x/w + d = (x + d*w)/w, cosi' il segno del
            # denominatore resta quello di prima e `Ms` lo trasporta insieme al resto.
            o = off[idx][..., None] * Pg[..., 2:3]
            Pg = Pg + np.concatenate([o, np.zeros_like(o), np.zeros_like(o)], axis=-1)
        Pt = np.einsum("tij,kcj->tkci", Ms, Pg)                               # (T,Kg,4,3)
        ww = Pt[..., 2]
        ok = (ww * sg) > 1e-6
        xy = Pt[..., :2] / np.where(ok, ww, 1.0)[..., None]
        xy = np.where(ok[..., None], xy, np.nan)
        P[:, idx] = xy.astype(np.float32)
    return P, vicina, Hc


def visibilita(P, forma):
    """Per ogni fotogramma e nota: 0 = fuori dal fotogramma, 1 = in parte, 2 = quasi tutta dentro (>= 3 angoli su 4)."""
    h, w = forma
    x, y = P[..., 0], P[..., 1]
    dentro = np.isfinite(x) & np.isfinite(y) & (x >= 0) & (x < w) & (y >= 0) & (y < h)
    n = dentro.sum(-1)
    return np.where(n >= 3, 2, np.where(n >= 1, 1, 0)).astype(np.uint8)


def presenza_tasti(video, P, note, vis, forma, inizio=0.0, campioni=24):
    """Per ogni nota BIANCA: il disegno del modello coincide con l'immagine, cioe' li' c'e' davvero un tasto?

    Si campionano `campioni` fotogrammi; per ognuno si disegna il modello coi poligoni di quel
    fotogramma e si calcola, nel riquadro di ogni bianco (con un po' di margine ai lati), la
    correlazione a media zero fra il modello e l'immagine sfocata. Dove c'e' una tastiera il modello
    la ricalca (correlazione alta); oltre la fine della tastiera, sulla cassa o sul muro, no.
    Le mani abbassano il valore, per questo si prende la mediana sui fotogrammi in cui il tasto e'
    tutto dentro. Ritorna `(punteggio (K,) con NaN dove mai dentro, quanti fotogrammi)`.
    """
    n_t = len(P)
    h, w = forma
    cada = max(1, n_t // max(1, campioni))
    cap, _, _ = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    bianchi = [k for k, n in enumerate(note) if not G.e_nero(n)]
    neri = [k for k, n in enumerate(note) if G.e_nero(n)]
    punt = [[] for _ in note]
    for t in range(n_t):
        if not cap.grab():
            break
        if t % cada:
            continue
        ok, f = cap.retrieve()
        if not ok:
            continue
        Ib = cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (0, 0), 1.5).astype(np.float32)
        T = np.zeros((h, w), np.uint8)
        for k in bianchi:
            if vis[t, k] and np.isfinite(P[t, k]).all():
                p = np.int32(np.round(P[t, k]))
                cv2.fillPoly(T, [p], 215)
                cv2.polylines(T, [p], True, 150, 1)
        for k in neri:
            if vis[t, k] and np.isfinite(P[t, k]).all():
                cv2.fillPoly(T, [np.int32(np.round(P[t, k]))], 25)
        Tb = cv2.GaussianBlur(T, (0, 0), 1.5).astype(np.float32)
        for k in bianchi:
            if vis[t, k] < 2 or not np.isfinite(P[t, k]).all():
                continue
            lar = float(np.linalg.norm(P[t, k][1] - P[t, k][0]))
            x1 = int(max(0, np.floor(P[t, k][:, 0].min() - 0.2 * lar)))
            x2 = int(min(w, np.ceil(P[t, k][:, 0].max() + 0.2 * lar)))
            y1, y2 = int(max(0, np.floor(P[t, k][:, 1].min()))), int(min(h, np.ceil(P[t, k][:, 1].max())))
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            a, b = Tb[y1:y2, x1:x2], Ib[y1:y2, x1:x2]
            a, b = a - a.mean(), b - b.mean()
            den = float(np.sqrt((a * a).sum() * (b * b).sum()))
            if den > 1e-6:
                punt[k].append(float((a * b).sum() / den))
    cap.release()
    out = np.array([np.median(v) if len(v) >= 2 else np.nan for v in punt])
    return out, np.array([len(v) for v in punt])


def decidi_tastiera(note, punteggio, quanti):
    """Dove comincia e dove finisce DAVVERO la tastiera, dai punteggi di presenza (`presenza_tasti`).

    Un bianco e' "presente" se il suo punteggio supera il 45% del plateau (85 percentile dei
    punteggi: il valore tipico di un tasto vero). Si prende la serie piu' lunga di bianchi presenti
    consecutivi (si tollera un buco: una mano). Un ESTREMO e' CERTO solo se i DUE bianchi
    successivi oltre la serie sono stati misurati e sono entrambi assenti: cioe' si e' visto, in
    piu' fotogrammi, che li' non c'e' un tasto ma cassa o muro. Se l'estremo esce dal fotogramma,
    o se la misura non e' affidabile, non e' certo.
    Ritorna un dict: `lo`, `hi` (primo e ultimo bianco presente, o None), `certo_sx`, `certo_dx`,
    `presente` (dict nota -> bool per i bianchi misurati), `plateau`.
    """
    bianchi = [n for n in note if not G.e_nero(n)]
    mis = {}
    for k, n in enumerate(note):
        if not G.e_nero(n) and np.isfinite(punteggio[k]) and quanti[k] >= 2:
            mis[n] = float(punteggio[k])
    vuoto = {"lo": None, "hi": None, "certo_sx": False, "certo_dx": False, "presente": {}, "plateau": 0.0}
    if len(mis) < 6:
        return vuoto
    plateau = float(np.percentile(list(mis.values()), 85))
    if plateau < 0.5:                      # nessun disegno di tastiera riconoscibile
        vuoto["plateau"] = plateau
        return vuoto
    pres = {n: v >= 0.45 * plateau for n, v in mis.items()}
    # serie piu' lunga di bianchi presenti consecutivi, tollerando UN buco isolato (una mano)
    serie, i = [], 0
    while i < len(bianchi):
        if pres.get(bianchi[i]) is True:
            j = i
            while True:
                if j + 1 < len(bianchi) and pres.get(bianchi[j + 1]) is True:
                    j += 1
                elif j + 2 < len(bianchi) and pres.get(bianchi[j + 2]) is True:
                    j += 2
                else:
                    break
            serie.append((i, j))
            i = j + 1
        else:
            i += 1
    if not serie:
        return dict(vuoto, plateau=plateau, presente=pres)
    a, b = max(serie, key=lambda ab: ab[1] - ab[0])
    if b - a + 1 < 6:
        return dict(vuoto, plateau=plateau, presente=pres)
    lo, hi = bianchi[a], bianchi[b]
    def assente(i):
        return 0 <= i < len(bianchi) and pres.get(bianchi[i]) is False
    certo_sx = assente(a - 1) and assente(a - 2)
    certo_dx = assente(b + 1) and assente(b + 2)
    return {"lo": lo, "hi": hi, "certo_sx": certo_sx, "certo_dx": certo_dx, "presente": pres, "plateau": plateau}


_MARGINE_CANVAS = 0.10       # passi di tasto: margine minimo del canvas sopra `v = 0` (vedi `canvas_tastiera`)


def canvas_tastiera(H_abs, rect, forma, lo, hi):
    """Il ritaglio che contiene TUTTE le note da `lo` a `hi`: la banda della tastiera + il ritaglio di prima.

    Per i tasti lontani si usa l'omografia continuata (`_H_continuata`). E' un'ipotesi dove i tasti
    non si vedono: nel video preparato quella parte resta nera.

    Il margine sopra `v = 0` non sale piu' di quanto serva: col retro dei tasti misurato
    (`retro_tasti`) i mezzi passi di margine di prima cadono sul RIFLESSO della tastiera sul mobile
    lucido, cioe' su 6-10 px che non sono tasti e che allungherebbero il video preparato per
    niente. Il ritaglio ha gia' il suo margine sopra i tasti (`--margine`, 0,3 passi): la banda si
    ferma al bordo del ritaglio quando ci arriverebbe (`_MARGINE_CANVAS` passi di margine in ogni
    caso, per non tagliare i tasti).
    """
    Hc = _H_continuata(H_abs, forma)
    u0, u1 = G.u_bianco(lo) - 0.5, G.u_bianco(hi) + 1.5
    x1, y1, x2, y2 = _pari(rect)
    # Quanto margine sopra `v = 0` si puo' tenere: il piu' basso degli angoli del ritaglio (il
    # ritaglio puo' stare obliquo, `v = 0` no), mai piu' di -0.5 come sempre e mai meno di
    # `_MARGINE_CANVAS` (una banda di tastiera tagliata a filo sul retro dei tasti non si vuole).
    v_back = -0.5
    if y1 > 0:
        quote = []
        for u in np.linspace(u0, u1, 6):
            p0 = np.float64(G.proietta(Hc, [(float(u), 0.0)]))[0]
            p1 = np.float64(G.proietta(Hc, [(float(u), 1.0)]))[0]
            s_v = float(p1[1] - p0[1])
            if s_v > 1e-6:
                quote.append((y1 - float(p0[1])) / s_v)
        if quote:
            v_back = float(np.clip(max(quote) + 0.03, -0.5, -_MARGINE_CANVAS))
    q = np.float64(G.proietta(Hc, [(u0, v_back), (u1, v_back),
                                   (u1, G.LW + 0.9), (u0, G.LW + 0.9)]))
    lo_ = np.minimum(q.min(0), [x1, y1])
    hi_ = np.maximum(q.max(0), [x2, y2])
    return _pari((int(np.floor(lo_[0])), int(np.floor(lo_[1])), int(np.ceil(hi_[0])), int(np.ceil(hi_[1]))))


def _dim_uscita(rect, canonica):
    """Larghezza e altezza del video preparato (le stesse formule di `scrivi_stabilizzato`)."""
    x1, y1, x2, y2 = _pari(rect)
    larg = int(canonica) if canonica else x2 - x1
    larg = max(2, larg // 2 * 2)
    alt = max(2, int(round((y2 - y1) * larg / max(1, x2 - x1))) // 2 * 2)
    return larg, alt


def finestra_utile(rect, Ms, canonica, forma):
    """Il pezzo di canvas che ha DAVVERO dei pixel: lo spazio nero dall'inizio alla fine si taglia.

    Sul video stabilizzato il canvas e' la finestra della tastiera allargata ai tasti del modello.
    Su una tastiera intera la finestra sta dentro il fotogramma e non c'e' niente da tagliare; su un
    PRIMO PIANO copre anche i tasti che nel fotogramma non ci sono, e li' il video preparato usciva
    quasi tutto nero: misurato sul primo piano dell'utente (`document_5904406621164936944`, 720x1280)
    la finestra e' 3122 px con l'uscita a 3000x484 e ~800 px di tastiera in mezzo (tre quarti di
    banda nera), e per giunta il taglio andava a finire anche nella griglia salvata (`dim_preparato`
    e `poligoni_preparato`).

    Qui si guarda dove cade il FOTOGRAMMA dentro il canvas su tutti i fotogrammi inseguiti (la stessa
    omografia con cui si scrive il video, quindi il conto e' esatto) e si tiene l'UNIONE: si taglia
    solo quello che sarebbe nero in ogni fotogramma. Il taglio e' un offset nel canvas, non un
    riscala: i tasti restano della stessa dimensione in pixel, come chiede il formato del dataset.

    Ritorna `(x, y, larghezza, altezza)` nel canvas, oppure None se non c'e' niente da tagliare.
    """
    if Ms is None or not len(Ms):
        return None
    h, w = forma
    larg, alt = _dim_uscita(rect, canonica)
    if larg < 8 or alt < 8 or w < 2 or h < 2:
        return None
    dst = np.float32([[0, 0], [larg - 1, 0], [larg - 1, alt - 1], [0, alt - 1]])
    cornice = np.float32([[[0, 0]], [[w - 1, 0]], [[w - 1, h - 1]], [[0, h - 1]]])
    lo, hi = np.array([np.inf, np.inf]), np.array([-np.inf, -np.inf])
    visti = 0
    for M in Ms:
        M = np.asarray(M, dtype=float)
        if not np.isfinite(M).all():
            continue
        try:
            T = cv2.getPerspectiveTransform(np.float32(_angoli_finestra(rect, M)), dst)
        except (cv2.error, ValueError):
            continue
        q = cv2.perspectiveTransform(cornice, T)[:, 0, :]
        if not np.isfinite(q).all():
            continue
        lo = np.minimum(lo, q.min(0))
        hi = np.maximum(hi, q.max(0))
        visti += 1
    if not visti or not np.isfinite([*lo, *hi]).all():
        return None
    x1 = int(max(0, np.floor(lo[0])))
    y1 = int(max(0, np.floor(lo[1])))
    x2 = int(min(larg, np.ceil(hi[0])))
    y2 = int(min(alt, np.ceil(hi[1])))
    larg_u = min(larg - x1, max(2, (x2 - x1 + 1) // 2 * 2))       # pari, mai sotto il contenuto
    alt_u = min(alt - y1, max(2, (y2 - y1 + 1) // 2 * 2))
    larg_u = max(2, larg_u // 2 * 2)
    alt_u = max(2, alt_u // 2 * 2)
    if larg_u >= larg - 2 and alt_u >= alt - 2:
        return None                       # il fotogramma copre tutto il canvas: niente da tagliare
    return x1, y1, larg_u, alt_u


def _finestra_tagliata(rect, taglio, canonica):
    """La finestra del video preparato riportata nel fotogramma (canvas meno il taglio).

    `finestra_usata` e il rettangolo viola del controllo devono dire quello che si vede DAVVERO nel
    video preparato: col taglio il video non comincia piu' dall'angolo del canvas, quindi si riporta
    l'angolo del taglio nel sistema del ritaglio (`x = x1 + offset / scala`). Non si riscala niente.
    """
    x1, y1, _, _ = _pari(rect)
    larg, _alt = _dim_uscita(rect, canonica)
    esc = larg / max(1, _pari(rect)[2] - x1)
    return _pari((x1 + int(round(taglio[0] / esc)), y1 + int(round(taglio[1] / esc)),
                  x1 + int(round((taglio[0] + taglio[2]) / esc)),
                  y1 + int(round((taglio[1] + taglio[3]) / esc))))


def analizza_tastiera(video, rect, H, Ms, forma, info, n_frame, inizio=0.0):
    """Guarda TUTTO il video e decide quali note ci sono, come si chiamano e che ritaglio serve.

    Passi: (1) si proiettano i tasti, anche 12 oltre i due estremi, in ogni fotogramma col moto
    inseguito; (2) per ogni bianco si misura se li' c'e' davvero un tasto (`presenza_tasti`); (3) si
    decide l'estensione (`decidi_tastiera`): se i DUE estremi sono certi la tastiera e' quella
    vista (puo' essere 88 tasti, 61, 25, un'ottava...), altrimenti si ipotizzano 88 tasti;
    (4) le ottave: se la tastiera misurata su tutto il pezzo (`estremi`) e' quella INTERA (52
    bianchi, da LA0 a DO8; anche 51, vedi `_TASTI_INTERA_MIN`) e la griglia ci sta sopra,
    l'estensione E' quella e non c'e' nessuna
    ottava da indovinare (`presenza_tasti` misura se il DISEGNO del modello combacia con quella luce
    li', non quanti tasti ci sono: sul pezzo `2024-02-15_22-12-41` tagliava i 12 bianchi piu' a
    sinistra, che ci sono, e il centraggio spostava tutto di un'ottava); altrimenti con la forma dei
    tasti neri si sa la nota ma non l'ottava e si sceglie quella che porta il blocco di tasti visti
    piu' al CENTRO della tastiera da 88 (il Do centrale e' il riferimento), e solo se la tastiera e'
    quella standard da 88 (La0..Do8, entrambi gli estremi visti) i nomi sono certi; (5) il ritaglio
    contiene tutte le note ipotizzate.
    Ritorna un dict, o None se non si e' potuto fare.
    """
    lb = float(info.get("lb_fronte") or info.get("lb") or G.LB)
    lw = float(info.get("lw_fronte") or G.LW)
    H_abs = _H_assoluta(H, rect)
    n = len(Ms) if Ms is not None else max(1, n_frame)
    Ms_a = np.asarray(Ms, dtype=float) if Ms is not None else np.array([np.eye(3)] * n)
    note_est = list(range(G.NOTA_MIN - 12, G.NOTA_MAX + 13))
    P, vera, Hc = poligoni_nel_tempo(H_abs, Ms_a, note_est, forma, lw, lb)
    vis = visibilita(P, forma)
    punt, quanti = presenza_tasti(video, P, note_est, vis, forma, inizio)
    dec = decidi_tastiera(note_est, punt, quanti)
    # L'ESTENSIONE MISURATA su tutto il pezzo (`estremi`, vedi `tastiera_nel_video`) decide quando e'
    # quella intera: la tastiera si vede tutta (52 bianchi, da LA0 a DO8, o 51 misurati: vedi
    # `_TASTI_INTERA_MIN`) e la griglia ci sta sopra
    # (`tasti_fuori_dalla_tastiera` = 0: nessun tasto del modello fuori dalla tastiera misurata).
    # Serve perche' `presenza_tasti` NON conta i tasti: confronta il DISEGNO del modello con
    # l'immagine, quindi misura se il disegno combacia con quella luce li'. Misurato su
    # `2024-02-15_22-12-41` con la griglia GIUSTA (LA0 a 119 px): i punteggi dei bianchi vanno da
    # 0,83 a -0,20 con plateau 0,89 e soglia 0,40 — quasi casuali, e togliendo i tasti neri dal
    # disegno il punteggio SALE (misurato: da 0,24 a 0,63 su SOL2, da 0,31 a 0,52 su RE3), perche'
    # i neri del disegno stanno 14 px piu' in basso del vero (vedi `verticale`, il retro dei neri).
    # Attenti a leggere quei 14 px: misurato colonna per colonna sul controllo di
    # `568bae412e9c49a1` (9/10/2026), il buio che sta 14 px sopra il nero e' il MOBILE col feltro,
    # largo come il fotogramma, che `verticale_neri` scarta apposta col vincolo di larghezza
    # (`_runs` largo-da-tasto: il nero vero comincia dove comincia QUEL run). A x 1086 il modello
    # mette il retro dei neri a 345,6 px e li' il run del nero parte a y 346, pixel su pixel; a 5x
    # i riquadri blu stanno sul nero, top sul retro e fondo sulle punte. I punteggi bassi di
    # `presenza_tasti` vengono quindi da luci e feltro, non da un retro disegnato sbagliato.
    # Da li' `decidi_tastiera` dichiarava "assenti" i 12 bianchi piu' a sinistra, l'estremo sinistro
    # risultava CERTO 12 semitoni piu' a destra e il centraggio spostava nomi e griglia di un'ottava
    # (`H_abs @ T`, +7 bianchi = +230 px): la griglia partiva dal LA1 vero e i 7 tasti piu' bassi
    # restavano senza griglia. Con la tastiera misurata intera non c'e' nessuna ottava da
    # indovinare: la presenza dei tasti resta un numero da leggere, non decide piu' l'estensione.
    est = info.get("estremi") or {}
    misurata_intera = (_tastiera_intera(est)              # 51 o 52: vedi `_TASTI_INTERA_MIN`
                       and float(est.get("copertura") or 0.0) >= 0.9
                       and int(est.get("neri_misurati") or 0) >= 30
                       and float(est.get("x_c8") or 0.0) > float(est.get("x_la0") or 0.0)
                       and info.get("tasti_fuori_dalla_tastiera") == 0)
    if misurata_intera:
        certi, lo, hi, ott = True, G.NOTA_MIN, G.NOTA_MAX, 0
        # Il conteggio della fascia si legge solo quando NON e' 52: se e' 51 il tasto in piu' del
        # modello e' quello che la misura ha perso (vedi `_TASTI_INTERA_MIN`), e va detto.
        letti = int(est.get("tasti") or 0)
        quanto = (f"{_TASTI_INTERA} bianchi" if letti == _TASTI_INTERA
                  else f"{_TASTI_INTERA} bianchi, la fascia ne ha letti {letti}")
        # Le fessure e i neri sono i due conti che hanno portato a `letti`: si leggono solo quando
        # NON dicono la stessa cosa, che e' il caso in cui la riga spiega davvero qualcosa (sull'esempio
        # 52 le fessure dicono 52 e i neri 53: il 53 era la ragione del verdetto "incerto").
        if est.get("fessure") is not None and int(est["fessure"]) + 1 != int(est.get("tasti_neri") or 0):
            quanto += (f"; fessure {int(est['fessure']) + 1} (somma {est['fessure_somma']:.2f}, "
                       f"{est['fessure_sporche']} tratti anomali), neri {int(est.get('tasti_neri') or 0)}")
        print(f"[tastiera] la tastiera misurata su tutto il pezzo e' quella intera ({quanto}, "
              f"LA0 {float(est['x_la0']):.0f} px .. DO8 {float(est['x_c8']):.0f} px, "
              f"{int(est.get('neri_misurati') or 0)} neri letti) e la griglia ci sta sopra: "
              f"l'estensione e' LA0..DO8, nessuna ottava da indovinare")
    else:
        certi = bool(dec["lo"] is not None and dec["certo_sx"] and dec["certo_dx"])
        if certi:
            lo, hi = dec["lo"], dec["hi"]
        else:
            lo, hi = G.NOTA_MIN, G.NOTA_MAX
        # ottava: il blocco di tasti presenti (o visti) piu' al centro della tastiera da 88
        if dec["lo"] is not None:
            blocco = (dec["lo"], dec["hi"])
        else:
            visti = [n_ for k, n_ in enumerate(note_est) if vis[:, k].max() == 2 and G.NOTA_MIN <= n_ <= G.NOTA_MAX]
            blocco = (min(visti), max(visti)) if visti else (G.NOTA_MIN, G.NOTA_MAX)
        centro = (blocco[0] + blocco[1]) / 2.0
        ott = int(round((64.5 - centro) / 12.0))
        # il blocco deve restare dentro La0..Do8
        while ott != 0 and (blocco[0] + 12 * ott < G.NOTA_MIN or blocco[1] + 12 * ott > G.NOTA_MAX):
            ott += -1 if ott > 0 else 1
        if certi:
            lo, hi = lo + 12 * ott, hi + 12 * ott
    spostamento = 12 * ott
    T = np.array([[1.0, 0.0, -7.0 * ott], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    H_abs_n = H_abs @ T                       # le note si rinominano di `ott` ottave: il tasto n+12*ott sta dove stava n
    H_n = np.linalg.inv(_H_assoluta(np.eye(3), rect)) @ H_abs_n
    nomi_certi = bool(certi and lo == G.NOTA_MIN and hi == G.NOTA_MAX)
    note = list(range(lo, hi + 1))
    pres_nuovo = {nn + spostamento: v for nn, v in dec["presente"].items()}
    rect_ext = canvas_tastiera(H_abs_n, rect, forma, lo, hi)
    if tuple(rect_ext) == tuple(_pari(rect)):
        rect_ext = None
    return {"H": H_n, "H_abs": H_abs_n, "lo": lo, "hi": hi, "note": note, "certi": certi,
            "estremo_sx_certo": bool(dec["certo_sx"]), "estremo_dx_certo": bool(dec["certo_dx"]),
            "nomi_certi": nomi_certi, "ottave_spostate": ott, "presente": pres_nuovo,
            "rect_ext": rect_ext, "plateau": dec["plateau"], "lb": lb, "lw": lw}


def scrivi_griglia_nel_tempo(base, video, fps_v, inizio, Ms, tastiera, rect, rect_usato, canonica, stabilizzato, forma, convenzione, ritaglio_uscita=None, x_tasti=None):
    """Salva dove sta OGNI nota in OGNI fotogramma: `<base>_griglia_nel_tempo.npz` + `<base>_note.json`.

    npz (tutti gli array float32 salvo diversa indicazione):
      poligoni_originale (T, K, 4, 2)   i 4 angoli di ogni nota, in pixel del video ORIGINALE, per ogni fotogramma
                                        (con la x MISURATA tasto per tasto, `x_tasti` di
                                        `x_tasti_misurata`: gli stessi riquadri del video della
                                        griglia), NaN dove il punto starebbe dietro la camera;
                                        i tasti fuori dal fotogramma hanno coordinate fuori dal
                                        fotogramma, estrapolate
      visibile (T, K) uint8             0 = fuori dal fotogramma, 1 = in parte, 2 = quasi tutta dentro
      poligoni_preparato (K, 4, 2)      i 4 angoli di ogni nota nel video PREPARATO (li' la tastiera sta ferma);
                                        col taglio dell'uscita (`ritaglio_uscita`) sono relativi alla
                                        finestra SCRITTA, non all'angolo del canvas, come `dim_preparato`
      moto (T, 3, 3)                    omografia dal fotogramma 0 al fotogramma t (originale)
      note_midi (K,), tempo_s (T,), indice_fotogramma (T,), fps, dim_preparato (2,)
    json: per ogni nota il nome, il tipo, se si vede nel video, se la presenza di un tasto e' stata
    verificata e se il nome (ottava) e' certo o ipotizzato.
    """
    note = tastiera["note"]
    n = len(Ms)
    P, vera, _ = poligoni_nel_tempo(tastiera["H_abs"], np.asarray(Ms, dtype=float), note, forma,
                                    tastiera["lw"], tastiera["lb"],
                                    dx=dx_tasti_cornici(x_tasti, note))
    vis = visibilita(P, forma)
    i0 = int(round(inizio * fps_v))
    X1, Y1, X2, Y2 = _pari(rect_usato)
    larg, alt = _dim_uscita(rect_usato, canonica)
    esc = larg / max(1, X2 - X1)
    P0 = P[0].astype(np.float64)
    # Col taglio dell'uscita (primo piano: vedi `finestra_utile`) le coordinate sono relative alla
    # finestra SCRITTA, la stessa del video preparato: si sposta tutto dell'angolo del taglio, senza
    # riscalare. `rettangolo_usato` resta il ritaglio del canvas, il taglio si salva a parte.
    ox, oy = (float(ritaglio_uscita[0]), float(ritaglio_uscita[1])) if ritaglio_uscita else (0.0, 0.0)
    dim_uscita = [int(ritaglio_uscita[2]), int(ritaglio_uscita[3])] if ritaglio_uscita else [larg, alt]
    prep = (((P0 - np.float64([X1, Y1])) * esc) - np.float64([ox, oy])).astype(np.float32)
    npz = Path(str(base) + "_griglia_nel_tempo.npz")
    np.savez_compressed(npz, poligoni_originale=P, visibile=vis, poligoni_preparato=prep,
                        moto=np.asarray(Ms, dtype=np.float32), note_midi=np.array(note, dtype=np.int16),
                        tempo_s=((i0 + np.arange(n)) / fps_v).astype(np.float64),
                        indice_fotogramma=(i0 + np.arange(n)).astype(np.int64), fps=np.float64(fps_v),
                        dim_preparato=np.array(dim_uscita, dtype=np.int32),
                        ritaglio_uscita=np.array(ritaglio_uscita or (0, 0, larg, alt), dtype=np.int32),
                        rettangolo_usato=np.array([X1, Y1, X2, Y2], dtype=np.int32))
    elenco = []
    for k, nn in enumerate(note):
        visto = bool(vis[:, k].max() == 2)
        pres = tastiera["presente"].get(nn)
        if G.e_nero(nn):
            pres = None                     # la presenza si misura solo sui bianchi
        elenco.append({"midi": nn, "nome": G.nome(nn), "tipo": "nero" if G.e_nero(nn) else "bianco",
                       "visto_nel_video": visto,
                       "tasto_verificato": bool(pres) if pres is not None else None,
                       "ipotizzata": not visto,
                       "nome_certo": bool(tastiera["nomi_certi"])})
    js = Path(str(base) + "_note.json")
    js.write_text(json.dumps({
        "convenzione_ottava": convenzione, "do_centrale": G.nome(60),
        "numero_note": len(note), "prima_nota": G.nome(note[0]), "ultima_nota": G.nome(note[-1]),
        "estremo_sinistro_certo": tastiera["estremo_sx_certo"], "estremo_destro_certo": tastiera["estremo_dx_certo"],
        "tastiera_completa_vista": tastiera["certi"], "nomi_certi": tastiera["nomi_certi"],
        "ottave_spostate_per_centrare": tastiera["ottave_spostate"],
        "stabilizzato": bool(stabilizzato), "dim_preparato": dim_uscita,
        "ritaglio_uscita": list(ritaglio_uscita) if ritaglio_uscita else None,
        "rettangolo_usato": [X1, Y1, X2, Y2],
        "file_griglia": npz.name, "note": elenco}, ensure_ascii=False, indent=1), encoding="utf-8")
    return npz, js


def zona_tastiera(H_abs, rect, forma=None, margine=24):
    """Il riquadro (x1, y1, x2, y2) intorno ai SOLI tasti, in coordinate del fotogramma intero.

    Perche': su una ripresa larga il ritaglio contiene muro, libri, pavimento, e con la parallasse
    della camera a mano quei piani si muovono diversamente dalla tastiera: seguirli, o misurare
    la tenuta su di loro, vuol dire seguire un'altra cosa. Si tiene solo il rettangolo dei tasti
    (piu' un margine), dentro il ritaglio e il fotogramma.
    """
    q = _quadro_tastiera(H_abs)
    x1, y1, x2, y2 = (int(v) for v in rect)
    a = [max(x1, int(np.floor(q[:, 0].min())) - margine), max(y1, int(np.floor(q[:, 1].min())) - margine),
         min(x2, int(np.ceil(q[:, 0].max())) + margine), min(y2, int(np.ceil(q[:, 1].max())) + margine)]
    if forma is not None:
        a = [max(0, a[0]), max(0, a[1]), min(forma[1], a[2]), min(forma[0], a[3])]
    return a if a[2] - a[0] > 40 and a[3] - a[1] > 20 else [x1, y1, x2, y2]


def _punti_riferimento(g0, H_abs, rect, quanti=700):
    """Punti buoni da seguire nel fotogramma 0, SOLO sui tasti, DISTRIBUITI su tutta la lunghezza.

    Distribuiti: con `goodFeaturesToTrack` su tutta la tastiera i punti si ammassano dove c'e'
    piu' contrasto (il centro, i neri in primo piano) e agli estremi ne restano pochi: l'omografia
    e' ben vincolata dove i punti sono densi e ruota all'estremo opposto (misurato: a tratti
    l'estremo sinistro sfasato di un tasto intero mentre il centro e la destra erano a posto).
    Si divide la tastiera in colonne e si prendono i migliori punti di ognuna.
    """
    m = np.zeros(g0.shape[:2], np.uint8)
    cv2.fillPoly(m, [np.int32(np.round(_quadro_tastiera(H_abs)))], 255)
    zx1, zy1, zx2, zy2 = zona_tastiera(H_abs, rect, g0.shape[:2], margine=0)
    ritaglio = np.zeros_like(m)
    ritaglio[zy1:zy2, zx1:zx2] = 255
    m = cv2.bitwise_and(m, ritaglio)
    colonne = max(4, min(14, (zx2 - zx1) // 45))
    per_col = max(20, quanti // colonne)
    bordi = np.linspace(zx1, zx2, colonne + 1).astype(int)
    pezzi = []
    for k in range(colonne):
        mc = np.zeros_like(m)
        mc[:, bordi[k]:bordi[k + 1]] = 255
        p = cv2.goodFeaturesToTrack(g0, per_col, 0.003, 4, mask=cv2.bitwise_and(m, mc), blockSize=5)
        if p is not None:
            pezzi.append(p)
    return np.concatenate(pezzi).astype(np.float32) if pezzi else None


def _lk_andata_ritorno(a, b, p, win=21, livelli=3):
    """LK da `a` a `b` col controllo di ritorno: tiene solo i punti che tornano dov'erano (<1 px).

    Su una tastiera il disegno si ripete ogni tasto: senza il ritorno un punto puo' agganciarsi
    al tasto accanto e nessuno se ne accorge.
    """
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
    p1, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p, None, winSize=(win, win), maxLevel=livelli,
                                         criteria=crit)
    p0, st2, _ = cv2.calcOpticalFlowPyrLK(b, a, p1, None, winSize=(win, win), maxLevel=livelli,
                                          criteria=crit)
    ok = (st.ravel() == 1) & (st2.ravel() == 1) & (np.hypot(*(p - p0).reshape(-1, 2).T) < 1.0)
    return p1.reshape(-1, 2), ok


def _riferimento(g0, p_rif, rect, margine=24, H_abs=None):
    """Il riferimento fisso: il fotogramma 0 ritagliato attorno ai tasti + i suoi punti buoni.

    Si lavora su un ritaglio (la tastiera e un po' di margine) e non sul fotogramma intero:
    il warp e il flusso costano un terzo e il resto del fotogramma non serve a niente.
    """
    h, w = g0.shape[:2]
    x1, y1, x2, y2 = rect
    bx1, by1 = max(0, x1 - margine), max(0, y1 - margine)
    bx2, by2 = min(w, x2 + margine), min(h, y2 + margine)
    T = np.array([[1.0, 0.0, -bx1], [0.0, 1.0, -by1], [0.0, 0.0, 1.0]])
    p = p_rif.reshape(-1, 2) - np.float32([bx1, by1])
    return {"g": g0[by1:by2, bx1:bx2].copy(), "p": np.ascontiguousarray(p, dtype=np.float32).reshape(-1, 1, 2),
            "T": T, "dim": (bx2 - bx1, by2 - by1), "p_pieno": p_rif.reshape(-1, 2).astype(np.float32),
            # striscia sottile (tastiera lontana e larga): l'omografia si stima male in prospettiva e
            # estrapolata lontano amplifica ogni errore; l'affine (6 parametri) no
            "sottile": False,
            "H_abs": None if H_abs is None else np.asarray(H_abs, dtype=float)}


def _stima_moto(a, b, soglia, sottile):
    """Il moto che porta i punti `a` nei punti `b`: omografia, o affine se la striscia e' sottile.

    Ritorna `(matrice 3x3, maschera inlier)` o `(None, None)`.
    """
    if sottile:
        A, mm = cv2.estimateAffine2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=soglia)
        if A is None:
            return None, None
        return np.vstack([A, [0.0, 0.0, 1.0]]), mm
    return cv2.findHomography(a, b, cv2.RANSAC, soglia)


def _registra(rif, g_cur, M, giri=2):
    """Affina `M` (fotogramma 0 -> corrente) registrando il fotogramma corrente sul fotogramma 0.

    PERCHE' E' IL CUORE: la deriva. Incatenare le omografie fotogramma per fotogramma somma
    ogni piccolo errore e dopo mille fotogrammi la griglia e' altrove. Qui, a ogni fotogramma, si
    rimette il corrente nel sistema del fotogramma 0 (`warpPerspective` con l'inversa di `M`) e si
    misura il RESIDUO contro i punti del fotogramma 0: l'errore non si accumula mai, perche' ogni
    fotogramma e' confrontato con lo stesso riferimento e non col vicino.

    Ritorna `(M, inlier, punti_seguiti)`.
    """
    T = rif["T"]
    n_in, n_ok = 0, 0
    for _ in range(giri):
        try:
            W = cv2.warpPerspective(g_cur, T @ np.linalg.inv(M), rif["dim"], flags=cv2.INTER_LINEAR)
        except np.linalg.LinAlgError:
            break
        p1, ok = _lk_andata_ritorno(rif["g"], W, rif["p"])
        n_ok = int(ok.sum())
        if n_ok < 12:
            break
        Rc, mm = _stima_moto(rif["p"].reshape(-1, 2)[ok], p1[ok], 2.0, rif["sottile"])
        if Rc is None or mm is None:
            break
        M = M @ (np.linalg.inv(T) @ Rc @ T)
        n_in = int(mm.sum())
    return M, n_in, n_ok


def _affina_su_modello(g, H_abs, scala=2.0, prove=12, lb=G.LB):
    """Rifinisce la griglia di UN fotogramma allineando il modello dei tasti all'immagine (ECC).

    I punti buoni seguiti dal fotogramma 0 vincolano bene la x ma poco la scala verticale: su una
    ripresa con zoom o cambio di inclinazione il retro della griglia si alzava di 10-15 px sopra
    le punte dei neri. L'ECC del modello usa il disegno intero (punte dei neri, fronte dei
    bianchi, fessure) e lavora solo sulla zona dei tasti, partendo dalla stima inseguita: pochi
    passi e pochi millisecondi. Ritorna `(H, correlazione)` o None se non converge.
    """
    h, w = g.shape[:2]
    q = _quadro_tastiera(H_abs)
    x1, y1 = max(0, int(np.floor(q[:, 0].min())) - 12), max(0, int(np.floor(q[:, 1].min())) - 12)
    x2, y2 = min(w, int(np.ceil(q[:, 0].max())) + 12), min(h, int(np.ceil(q[:, 1].max())) + 12)
    if x2 - x1 < 40 or y2 - y1 < 20:
        return None
    # riduzione: ECC costa in proporzione ai pixel; con tasti larghi (primo piano) si lavora a
    # risoluzione ridotta, con tasti piccoli (ripresa larga) mai, o si perderebbero i neri
    passo = float(np.hypot(H_abs[0, 0], H_abs[1, 0]))
    # tasti piccoli (7-24 px): fattore 2, provato sulla ripresa larga (tasti da 9 px); tasti grandi:
    # passo // 12, come prima (con tasti da 33 px un fattore 4 li riduceva a 8 px e l'ECC trovava un
    # ottimo a 6-30 px dalla verita' nel video sintetico)
    rid = 2 if 7 <= passo < 24 else max(1, min(4, int(passo // 12)))
    T0 = np.array([[1.0, 0.0, -x1], [0.0, 1.0, -y1], [0.0, 0.0, 1.0]])
    S = np.diag([1.0 / rid, 1.0 / rid, 1.0])
    T = S @ T0
    crop = g[y1:y2, x1:x2]
    if rid > 1:
        crop = cv2.resize(crop, (max(8, crop.shape[1] // rid), max(8, crop.shape[0] // rid)),
                          interpolation=cv2.INTER_AREA)
        scala = max(1.0, scala / rid)
    Hc = T @ np.asarray(H_abs, dtype=float)                 # griglia nelle coordinate del ritaglio
    tm, mk = _render_modello(Hc, crop.shape, lb=lb)
    if mk.sum() < 255 * 200 // (rid * rid):
        return None
    Tb = cv2.GaussianBlur(tm, (0, 0), scala).astype(np.float32)
    Ib = cv2.GaussianBlur(crop, (0, 0), scala).astype(np.float32)
    # correlazione di PARTENZA (la griglia inseguita cosi' com'e'): la stessa misura che ECC
    # massimizza, cioe' la correlazione a media zero dentro la maschera dei tasti. Serve per
    # accettare la rifinitura solo se migliora davvero.
    sel = mk > 0
    a0, b0 = Tb[sel] - Tb[sel].mean(), Ib[sel] - Ib[sel].mean()
    cc0 = float((a0 * b0).sum() / (np.sqrt((a0 * a0).sum() * (b0 * b0).sum()) + 1e-9))
    Wm = np.eye(3, dtype=np.float32)
    try:
        cc, Wm = cv2.findTransformECC(Tb, Ib, Wm, cv2.MOTION_HOMOGRAPHY,
                                      (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, prove, 1e-4),
                                      mk, 5)
    except cv2.error:
        return None
    if not np.isfinite(Wm).all():
        return None
    return np.linalg.inv(T) @ Wm.astype(float) @ Hc, float(cc), cc0


def _predici(prev, cur, M, rif):
    """Il moto fra due fotogrammi vicini, seguendo i punti del riferimento DOVE SONO ORA.

    Niente ricerca di punti nuovi a ogni fotogramma (e' la parte piu' lenta del flusso): i punti
    del fotogramma 0 stanno in `M @ p` sul fotogramma prima, si seguono fino al corrente e
    l'omografia che li lega e' il passo. Ritorna `(Hf, inlier, seguiti)`, Hf = identita' se fallisce.
    """
    pts = G.proietta(M, rif["p_pieno"]).astype(np.float32).reshape(-1, 1, 2)
    h, w = prev.shape[:2]
    dentro = ((pts[:, 0, 0] > 8) & (pts[:, 0, 0] < w - 8) & (pts[:, 0, 1] > 8) & (pts[:, 0, 1] < h - 8))
    pts = pts[dentro]
    if len(pts) < 12:
        return np.eye(3), 0, 0
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, winSize=(31, 31), maxLevel=4, criteria=crit)
    ok = st.ravel() == 1
    if ok.sum() < 12:
        return np.eye(3), 0, int(ok.sum())
    Hf, mm = _stima_moto(pts[ok], p1[ok], 3.0, rif["sottile"])
    return (Hf if Hf is not None else np.eye(3)), (int(mm.sum()) if mm is not None else 0), int(ok.sum())


def _liscia_angoli(C, fps):
    """Lisciatura a FASE ZERO del moto dei 4 angoli del ritaglio: `C` ha forma (n, 4, 2).

    Perche' non l'EMA di prima. Una media pesata fatta solo "in avanti" RITARDA: quando la
    camera si muove la griglia disegnata resta indietro (e dopo i riavvii "sbanda"), che e' proprio
    il difetto di `lisce`. Qui: (1) si lisciano i 4 angoli (punti), non i nove numeri della matrice
    (un'omografia non si media elemento per elemento); (2) il filtro e' adattivo (One-Euro: a
    riposo taglia forte, il tremolio sparisce; in movimento quasi non taglia); (3) si passa avanti
    E indietro e si fa la media: i due ritardi si annullano. Tutto il pezzo e' gia' in memoria,
    quindi il futuro si puo' guardare.
    """
    n = len(C)
    X = C.reshape(n, 8).astype(float)

    def passata(Y):
        out = np.empty_like(Y)
        out[0] = Y[0]
        v = np.zeros(8)
        for i in range(1, len(Y)):
            vi = (Y[i] - out[i - 1]) * fps                         # velocita' (px/s)
            v = 0.5 * vi + 0.5 * v
            # Frequenza di taglio SEPARATA per x e per y: con una camera che si muove forte in
            # orizzontale (3 px/fotogramma) una velocita' unica teneva aperto il filtro anche in
            # verticale, e il rumore della y (misurato: +-3-7 px da un fotogramma all'altro mentre
            # l'immagine saliva regolarmente di 1 px) passava intero. Ogni asse usa la propria
            # velocita' media sui 4 angoli.
            vv = np.abs(v.reshape(4, 2)).mean(axis=0)               # (vx, vy)
            fc = _FC_MIN + _FC_BETA * vv
            a = np.tile(1.0 / (1.0 + fps / (2.0 * np.pi * fc)), 4)   # (8,): x, y, x, y, ...
            out[i] = a * Y[i] + (1.0 - a) * out[i - 1]
        return out

    avanti = passata(X)
    indietro = passata(X[::-1])[::-1]
    return (0.5 * (avanti + indietro)).reshape(n, 4, 2)


def _rifinisci_sul_modello(video, Ms, H0, passo, inizio, n, zona, punti, lb=G.LB):
    """Seconda passata: la griglia allineata al modello (vedi `_affina_su_modello`), a OGNI fotogramma.

    Il tracking dal fotogramma 0 (punti + registrazione) e' stabile ma su una tastiera lontana
    (strisce sottili) ha due difetti: vincola poco la scala verticale (con uno zoom il retro si
    alzava di 15 px) e a tratti sbaglia UN ESTREMO (misurato: l'estremo sinistro sfasato fino a
    un tasto e mezzo per qualche fotogramma, con centro e destra a posto). L'ECC sul modello li vede
    entrambi, e a immagine ridotta e con pochi passi costa poco: si rilegge il video e si
    corregge la griglia fotogramma per fotogramma, partendo da quella inseguita. La correzione
    si misura sui 4 angoli della zona dei tasti e (per i fotogrammi non accettati) si interpola
    fra i vicini. Ritorna `(Ms rifinite, fotogrammi rifiniti)`.
    """
    salto = 1
    zx1, zy1, zx2, zy2 = zona
    cap, _, _ = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    ang = np.float64([[zx1, zy1], [zx2 - 1, zy1], [zx2 - 1, zy2 - 1], [zx1, zy2 - 1]])
    pr = np.asarray(punti, dtype=float).reshape(-1, 2)         # i punti dei tasti realmente visibili
    cap.read()                                                 # il fotogramma 0 e' gia' l'identita'
    idx, corr, ultima = [0], [np.zeros((4, 2))], None
    for i in range(1, n):
        ok, f = cap.read()
        if not ok:
            break
        M = np.asarray(Ms[i], dtype=float)
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        # Partenze: la stima del tracking e, se non va, l'ultima griglia GIA' rifinita (al massimo
        # 4 fotogrammi fa): quando il tracking sbaglia un estremo di un tasto la stima grezza e'
        # troppo lontana perche' l'ECC converga (o la correzione viene scartata), ma la camera in
        # un fotogramma si muove di un pixel o due e la griglia rifinita del fotogramma prima e'
        # un'ottima partenza.
        partenze = [M] + ([ultima[1]] if ultima is not None and i - ultima[0] <= 4 else [])
        scelta = None
        for Mp in partenze:
            try:
                ris = _affina_su_modello(g, Mp @ H0, lb=lb)
            except (cv2.error, np.linalg.LinAlgError, ValueError):
                ris = None
            if ris is None or ris[1] < 0.55:
                continue
            M_new = ris[0] @ np.linalg.inv(H0)
            if not np.isfinite(M_new).all():
                continue
            d = G.proietta(M_new, pr) - G.proietta(M, pr)
            if np.median(np.abs(d[:, 0])) > 0.35 * passo or np.median(np.abs(d[:, 1])) > 2.0 * passo:
                continue
            c = G.proietta(M_new, ang) - G.proietta(M, ang)
            # accettata se migliora la correlazione (>= 0,02) o se la correzione e' grande (>= 3 px a
            # un angolo): una correzione piccola senza guadagno e' rumore dell'ECC (nel sintetico,
            # dove il tracking era esatto, introduceva 2 px di errore), una grande e' un difetto vero
            if ris[1] - ris[2] < 0.02 and float(np.abs(c).max()) < 3.0:
                continue
            scelta = (M_new, c)
            break
        if scelta is None:
            continue
        ultima = (i, scelta[0])
        c = scelta[1]
        idx.append(i)
        corr.append(c)
    cap.release()
    if len(idx) < 2:
        return list(Ms), 0
    idx_a, corr_a = np.asarray(idx), np.asarray(corr)             # (k,), (k, 4, 2)
    out = [np.eye(3)]
    src = np.float32(ang)
    for i in range(1, n):
        D = np.stack([[np.interp(i, idx_a, corr_a[:, c, e]) for e in range(2)] for c in range(4)])
        M = np.asarray(Ms[i], dtype=float)
        try:
            Mi = cv2.getPerspectiveTransform(src, np.float32(G.proietta(M, ang) + D)).astype(float)
            out.append(Mi if np.isfinite(Mi).all() else M)
        except cv2.error:
            out.append(M)
    print(f"[rifinitura] {len(idx) - 1} fotogrammi su {n - 1} rifiniti sul modello")
    return out, len(idx) - 1


def tastiera_ferma(video, rect, H, inizio=0.0, durata=0.0):
    """La tastiera sta ferma o si muove nel pezzo? Lo dicono SOLO i 4 angoli della griglia VERDE.

    PERCHE' PRIMA DI INSEGUIRE: se quei 4 angoli (`angoli_bianchi`: il blocco dei tasti bianchi, dal
    retro al fronte) non si spostano in tutto il pezzo, il ritaglio e la griglia del fotogramma 0
    valgono per TUTTI i fotogrammi, e inseguirli e' un rischio senza guadagno: una griglia inseguita
    puo' scappare e il video preparato viene ricampionato a ogni fotogramma. Se invece si spostano --
    oltre `_TOLLERANZA_ANGOLI_PX` in x e `_TOLLERANZA_ANGOLI_Y_PX` in y, la stessa soglia con cui
    l'inseguimento conclude "la camera sta ferma" -- l'inseguimento serve, e la griglia si muove
    quando si muovono i suoi angoli (e' quello che fa `insegui_griglia`).

    COME: i 4 angoli si proiettano nei fotogrammi del pezzo col moto misurato registrando il
    fotogramma sul PRIMO (`_registra`: gli stessi punti e la stessa omografia dell'inseguimento,
    quindi niente deriva, perche' ogni fotogramma e' confrontato col primo e non col vicino) e si
    guarda quanto sono lontani da dove stavano al fotogramma 0. Si guarda la MEDIANA dei 4 angoli:
    quando il modello e' piu' largo del fotogramma (primo piano) gli angoli estremi cadono fuori
    dall'immagine, dove l'omografia estrapolata e' meno vincolata, e un angolo solo non deve
    decidere per tutti; se il video mostra solo una PARTE del pianoforte la misura vale lo stesso,
    perche' un movimento dei tasti muove anche gli angoli del modello (sul video di prova
    `document_5904406621164936944`, telefonino a mano, gli angoli si spostano di 779 px). Un
    fotogramma storto da solo non e' movimento, e non lo sono neppure quattro sparsi: fino a
    `_ANGOLI_FUORI_MAX` campioni storti DI FILA si perdonano, oltre -- o oltre il
    `_ANGOLI_FUORI_FRAZIONE` dei campioni -- si decide "si muove" e si smette di misurare: il pezzo
    che si muove, il caso piu' frequente, non paga il resto del passaggio (`_PASSO_ANGOLI` campioni su
    `_PASSO_ANGOLI` fotogrammi, ~17 ms a fotogramma).

    Ritorna `(fermo, numeri)`:
      - `fermo` vero solo se i campioni storti restano entro `_ANGOLI_FUORI_MAX` DI FILA e la loro
        frazione, e i campioni misurabili sono almeno `_ANGOLI_MISURABILI_MIN` di quelli guardati: un
        pezzo coperto da mani e tablet non ha il diritto di dire "ferma", li' si insegue come sempre;
      - `numeri` per il log e per il json (`decisa`, `x_max_px`, `y_max_px`, `fuori`, `fuori_max`,
        `di_fila_max` -- la fila piu' lunga di campioni storti, ed e' quella che decide --,
        `primo_fuori`, `misurabili`, `campioni`, `passo`, `frame` e le due tolleranze) o `{}` se non
        si e' potuto misurare niente;
      - `(None, {})` se il video non si legge o non ci sono punti da seguire: chi chiama insegue.
    """
    rx = _pari(rect)
    H0 = _H_assoluta(H, rect)
    angoli0 = angoli_bianchi(H0)
    if not np.isfinite(angoli0).all():
        return None, {}
    cap, fps_v, n_v = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    limite = int(round(durata * fps_v)) if durata else 0
    tot = limite or n_v
    ok, f0 = cap.read()
    if not ok:
        cap.release()
        return None, {}
    g0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY)
    p_rif = _punti_riferimento(g0, H0, rx)
    if p_rif is None or len(p_rif) < 30:
        print("[angoli] nessun punto da seguire sul primo fotogramma: non so se la tastiera si muove")
        cap.release()
        return None, {}
    rif = _riferimento(g0, p_rif, zona_tastiera(H0, rx, g0.shape[:2]), margine=12, H_abs=H0)
    I3 = np.eye(3)
    passo = max(1, int(_PASSO_ANGOLI))
    # `n` = fotogrammi consumati del pezzo, `campioni` = fotogrammi guardati (uno ogni `passo`, piu'
    # il primo), `misurabili` = campioni dove la registrazione ha agganciato abbastanza punti per
    # fidarsi. La frazione che conta per dire "ferma" e' misurabili/campioni, non misurabili/n.
    M, n, campioni, misurabili = I3, 1, 1, 1
    storti, di_fila, di_fila_max, primo_storto, x_max, y_max = 0, 0, 0, None, 0.0, 0.0
    while True:
        if limite and n >= limite:                # il pezzo da controllare finisce qui
            break
        if passo > 1 and n % passo:               # campione saltato: consumato senza decodificarlo
            if not cap.grab():
                break
            n += 1
            continue
        ok, f = cap.read()
        if not ok:
            break
        n += 1
        campioni += 1
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        M_reg, n_in, n_ok = _registra(rif, g, M, giri=1)
        if n_in < _MIN_INLIER_REG:                 # ripescaggio: dall'omografia ferma
            M_reg, n_in, n_ok = _registra(rif, g, I3, giri=2)
        if n_in < _MIN_INLIER_REG or n_in < 0.5 * max(1, n_ok):
            # campione non misurabile (mano sui tasti, sfocatura, salto troppo grande): non conta
            # ne' come fermo ne' come mosso, ma se sono troppi non si puo' piu' dire "ferma"
            if campioni - misurabili > (1.0 - _ANGOLI_MISURABILI_MIN) * campioni:
                break
            continue
        M = M_reg
        a = G.proietta(M, angoli0)
        if not np.isfinite(a).all():
            continue
        misurabili += 1
        dx = float(np.median(np.abs(a[:, 0] - angoli0[:, 0])))
        dy = float(np.median(np.abs(a[:, 1] - angoli0[:, 1])))
        x_max, y_max = max(x_max, dx), max(y_max, dy)
        if dx > _TOLLERANZA_ANGOLI_PX or dy > _TOLLERANZA_ANGOLI_Y_PX:
            storti += 1
            di_fila += 1
            di_fila_max = max(di_fila_max, di_fila)
            if primo_storto is None:
                primo_storto = n                 # dove e' cominciato: nel log serve per capire
            if di_fila > _ANGOLI_FUORI_MAX:      # una FILA di storti, non quattro sparsi: si muove
                break
        else:
            di_fila = 0                          # un campione buono interrompe la fila
    cap.release()
    frazione = misurabili / max(1, campioni)
    # "si muove" se i campioni storti formano una FILA OPPURE se la loro frazione e' troppa: cosi' un
    # pezzo in cui si muove quasi tutto non puo' passare per fermo nemmeno con un margine sbagliato, e
    # quattro campioni sparsi (il rumore di `2024-09-02_20-00-16`) non accendono l'inseguimento.
    fuori = di_fila_max > _ANGOLI_FUORI_MAX or storti > _ANGOLI_FUORI_FRAZIONE * campioni
    decisa = ("si muove" if fuori else
              "ferma" if frazione >= _ANGOLI_MISURABILI_MIN else "non misurata")
    numeri = {"frame": n, "campioni": campioni, "passo": passo, "misurabili": misurabili,
              "frazione_misurabile": round(frazione, 3),
              "x_max_px": round(x_max, 1), "y_max_px": round(y_max, 1),
              "tolleranza_x_px": _TOLLERANZA_ANGOLI_PX, "tolleranza_y_px": _TOLLERANZA_ANGOLI_Y_PX,
              "fuori": storti, "fuori_max": _ANGOLI_FUORI_MAX,
              "di_fila_max": di_fila_max,
              "fuori_frazione_max": _ANGOLI_FUORI_FRAZIONE,
              "primo_fuori": primo_storto, "decisa": decisa}
    if tot:
        # I campioni fuori tolleranza si dicono SEMPRE, anche quando non decidono: un pezzo con 2
        # fotogrammi storti non e' un pezzo perfetto, e chi legge il log deve poterlo vedere. Con la
        # fila il numero che decide e' `di_fila_max`: il totale si dice lo stesso, cosi' "4 storti"
        # non fa piu' pensare al movimento quando sono quattro fotogrammi sparsi su tutto il pezzo.
        storti_txt = (f", {storti} fuori tolleranza (al massimo {di_fila_max} di fila)" if storti
                      else "")
        passo_txt = f"uno ogni {passo}, " if passo > 1 else ""
        print(f"[angoli] i 4 angoli dei tasti bianchi su {n} fotogrammi ({passo_txt}{campioni} "
              f"campioni): al massimo {x_max:.1f} px in x e {y_max:.1f} px in y da dove stavano al "
              f"primo fotogramma (mediana dei 4 angoli, soglia {_TOLLERANZA_ANGOLI_PX:.0f} in x e "
              f"{_TOLLERANZA_ANGOLI_Y_PX:.0f} in y px; si muove con oltre {_ANGOLI_FUORI_MAX} campioni "
              f"storti di fila o oltre il {_ANGOLI_FUORI_FRAZIONE:.0%}{storti_txt}), {misurabili} "
              f"misurati -> la tastiera {_ANGOLI_ESITO[decisa]}")
    return (decisa == "ferma"), numeri


def insegui_griglia(video, rect, H, inizio=0.0, durata=0.0, lb=G.LB):
    """Il MOTO della tastiera su ogni fotogramma del pezzo: `Ms[i]` = omografia fotogramma 0 -> i.

    La griglia NON si ristima piu' a ogni fotogramma. Il difetto di prima (griglia staccata dai
    tasti, ritaglio non coerente, deriva dopo i "riavvii") aveva tre cause, tutte sparite qui:

      1. a ogni fotogramma `griglia_prospettica.insegui` rifaceva `affina` sul MODELLO e ogni
         30 fotogrammi cercava il pianoforte da zero (`H_iniziale`, i "58 riavvii"): cosi' si
         buttava la griglia misurata del fotogramma 0 (y sui neri veri, x tasto per tasto,
         fronte dei bianchi) e ogni riavvio la rimetteva a una stima diversa e piu' sbagliata
         (`H_iniziale` sbaglia la y della meta' su queste riprese). Ora la griglia e' UNA, quella
         del fotogramma 0, e si traccia solo il suo moto.
      2. il moto si rimisurava solo fra fotogrammi vicini, quindi ogni errore si sommava: ora a
         ogni fotogramma si registra il corrente sul fotogramma 0 (`_registra`), niente deriva.
      3. la lisciatura (EMA sulle matrici) ritardava: ora e' a fase zero sui 4 angoli.

    Ritorna `(Ms, numeri)`: `Ms[0]` e' l'identita' (cosi' il frame 0 del video preparato e'
    il ritaglio di sempre pixel per pixel), e SIA la griglia SIA il ritaglio SIA il video
    stabilizzato si ricavano da `Ms[i]` (griglia: `trasporta_poligoni`; ritaglio:
    `_angoli_finestra`). Un "riavvio" ora e' solo un fotogramma in cui l'aggancio si e' perso e
    poi ritrovato: l'omografia riparte dal fotogramma 0, non da una ricerca da zero.
    """
    rx = _pari(rect)
    H0 = _H_assoluta(H, rect)
    passo = float(np.hypot(H0[0, 0], H0[1, 0])) or 1.0
    cap, fps_v, n_v = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    limite = int(round(durata * fps_v)) if durata else 0
    tot = limite or n_v
    ogni = _ogni_avanzamento(tot)
    ok, f0 = cap.read()
    if not ok:
        cap.release()
        return [], {}
    g0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY)
    p_rif = _punti_riferimento(g0, H0, rx)
    zona = zona_tastiera(H0, rx, g0.shape[:2])
    if p_rif is None or len(p_rif) < 30:
        cap.release()
        return [], {}
    if tot:
        print(f"[insegui] inseguo la tastiera su {tot} fotogrammi ({tot / fps_v:.0f} s a {fps_v:g} fps): "
              f"{len(p_rif)} punti del fotogramma 0 come riferimento fisso (niente deriva)")
    rif = _riferimento(g0, p_rif, zona, margine=12, H_abs=H0)
    # Gli angoli per il controllo di continuita' e per la lisciatura sono quelli della ZONA DEI TASTI:
    # i punti seguiti stanno li', e un'omografia estrapolata ai quattro angoli di un ritaglio che
    # contiene mezza stanza amplificherebbe ogni errore di prospettiva (un "salto" di 17 tasti).
    angoli = np.float64([[zona[0], zona[1]], [zona[2] - 1, zona[1]], [zona[2] - 1, zona[3] - 1],
                         [zona[0], zona[3] - 1]])
    I3 = np.eye(3)
    M, prev = I3.copy(), g0
    Ms_grezze, inlier = [I3.copy()], [len(p_rif)]
    agganciati, riavvii, scartate, solo_flusso, persi_di_fila, persi_max = 1, 0, 0, 0, 0, 0
    perso = False
    while True:
        ok, f = cap.read()
        if not ok or (limite and len(Ms_grezze) >= limite):
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        Hc = M @ H0                                        # dov'e' la griglia nel fotogramma prima
        M_pred, flusso_ok = M, False
        diff = float(np.mean(np.abs(prev.astype(np.int16) - g.astype(np.int16))))
        if diff >= G._SOGLIA_FERMO:                        # l'immagine si e' mossa: predizione col flusso
            Hf, n_fl, n_tr = _predici(prev, g, M, rif)
            if n_fl >= 12 and n_fl >= 0.4 * max(1, n_tr):
                if G._stessa_tastiera(Hf @ Hc, Hc, G._SALTO_TASTI, G._SCARTO_SCALA):
                    M_pred, flusso_ok = Hf @ M, True
                else:
                    scartate += 1                          # un freno e' scattato: la griglia sta ferma
        else:
            flusso_ok = True                               # identica: la geometria non cambia
        M_reg, n_in, n_ok = _registra(rif, g, M_pred)
        buono = n_in >= _MIN_INLIER_REG and n_in >= 0.5 * max(1, n_ok)
        if buono:
            # il residuo non puo' essere piu' di mezzo tasto: oltre sarebbe l'aggancio al tasto
            # accanto (la tastiera si ripete), non una correzione
            # misurato sui PUNTI dei tasti (mediana), non agli angoli: agli angoli un errore minimo
            # di scala si amplifica e boccerebbe un aggancio giusto durante uno zoom; un aggancio al
            # tasto accanto sposta TUTTI i punti di un passo e qui si vede.
            sp = float(np.median(np.hypot(*(G.proietta(M_reg, rif["p_pieno"])
                                            - G.proietta(M_pred, rif["p_pieno"])).T)))
            sc = float(np.hypot(*(M_reg @ H0)[:2, 0])) / passo
            buono = (sp <= 0.5 * passo and 0.5 <= sc <= 2.0
                     and G.centro_griglia(M_reg @ H0) is not None
                     and _deriva_tasti(M_reg @ H0, H0, passo) <= _MAX_SEGUI_TASTI)
        if not buono and perso:                            # ripescaggio: da fermo e dall'ultima posizione
            for M_try in (I3, M):
                M_r, n_r, n_o = _registra(rif, g, M_try, giri=3)
                if n_r >= 2 * _MIN_INLIER_REG and n_r >= 0.5 * max(1, n_o):
                    M_reg, n_in, buono = M_r, n_r, True
                    break
        if buono:
            M = M_reg
            agganciati += 1
            if perso:
                riavvii += 1                               # ritrovata dopo averla persa
            perso, persi_di_fila = False, 0
        elif flusso_ok and M_pred is not M:
            M = M_pred                                     # niente aggancio, ma il flusso regge
            solo_flusso += 1
            perso = True
            persi_di_fila += 1
        else:                                              # persa: si resta dov'era
            perso = True
            persi_di_fila += 1
        persi_max = max(persi_max, persi_di_fila)
        Ms_grezze.append(M.copy())
        inlier.append(int(n_in))
        prev = g
        if ogni and len(Ms_grezze) % ogni == 0:
            print(f"[insegui] {len(Ms_grezze)}/{tot} fotogrammi seguiti (agganciati {agganciati}, "
                  f"inlier mediano {int(np.median(inlier))}, "
                  f"deriva {_deriva_tasti(M @ H0, H0, passo):.1f} tasti)")
    cap.release()
    n = len(Ms_grezze)
    # Solo con tasti PICCOLI (passo < 16 px): li' pochi punti e il disegno periodico rendono il tracking
    # impreciso e l'ECC e' chiaramente migliore (verificato a occhio su tasti da 9 px). Con tasti
    # grandi il tracking e' gia' esatto (sintetico con tasti da 33 px: 0,05 px di errore) e l'ECC,
    # che confronta con un modello un po' diverso dal disegno vero, aggiungerebbe un bias di
    # qualche pixel (misurato: 3-19 px).
    # La rifinitura sul modello serve dove la y e' mal vincolata dai punti: una STRISCIA SOTTILE (zona
    # alta meno di un quarto della larghezza: ripresa larga, tastiera lontana). In un primo piano i
    # punti coprono tutta l'altezza, il tracking e' gia' giusto e l'ECC verticale, poco vincolato,
    # peggiorerebbe (misurato: retro della griglia 478 px col tracking, 368 dopo la rifinitura,
    # contro i ~470 reali).
    if (zona[3] - zona[1]) < 0.25 * (zona[2] - zona[0]) and passo < 16:
        Ms_grezze, rifinite = _rifinisci_sul_modello(video, Ms_grezze, H0, passo, inizio, n, zona, rif["p_pieno"], lb)
    else:
        rifinite = 0
    # Lisciatura a fase zero sui 4 angoli (vedi `_liscia_angoli`); il fotogramma 0 resta
    # l'identita' esatta, cosi' il video preparato comincia col ritaglio di sempre.
    C = np.asarray([G.proietta(Mi, angoli) for Mi in Ms_grezze], dtype=float)
    C = np.where(np.isfinite(C), C, np.nan)
    if np.isnan(C).any():                                  # ripieghi: mai un NaN nelle matrici
        for i in range(1, n):
            if np.isnan(C[i]).any():
                C[i] = C[i - 1]
    Cs = _liscia_angoli(C, fps_v) if n > 2 else C
    src = np.float32(angoli)
    Ms = [I3.copy()]
    for i in range(1, n):
        try:
            Mi = cv2.getPerspectiveTransform(src, np.float32(Cs[i])).astype(float)
            if not np.isfinite(Mi).all():
                raise ValueError
        except (cv2.error, ValueError):
            Mi = Ms_grezze[i]
        Ms.append(Mi)
    centro = ((zona[0] + zona[2]) / 2.0, (zona[1] + zona[3]) / 2.0)
    spost = np.asarray([G.proietta(Mi, [centro])[0] for Mi in Ms], dtype=float)
    dist = np.hypot(spost[:, 0] - spost[0, 0], spost[:, 1] - spost[0, 1])
    salto = float(np.max(np.hypot(np.diff(spost[:, 0]), np.diff(spost[:, 1])))) if n > 1 else 0.0
    numeri = {"frame": n, "agganciati": agganciati, "riavvii": riavvii,
              "riancorate": 0, "scartati": scartate,
              "solo_flusso": solo_flusso, "persi_di_fila_max": persi_max,
              "tasti_persi": n - agganciati,
              "inlier_mediano": int(np.median(inlier)) if inlier else 0,
              "inlier_minimo": int(min(inlier)) if inlier else 0,
              "spostamento_px": [round(float(dist.max()), 1),
                                 round(float(np.max(np.abs(spost[:, 1] - spost[0, 1]))), 1)],
              "spostamento_tasti": round(float(dist.max()) / passo, 2),
              "spostamento_per_frame_max": round(salto / passo, 2)}
    numeri["zona"] = [int(v) for v in zona]
    numeri["rifinite_su_modello"] = rifinite
    return Ms, numeri


def _concordanza(ref, cur, dx, dy, m):
    """Quanti pixel di `cur` spostato di (dx, dy) coincidono con `ref` (frazione 0..1, margine `m`)."""
    h, w = ref.shape
    a = ref[m:h - m, m:w - m].astype(np.int16)
    b = cur[m + dy:h - m + dy, m + dx:w - m + dx].astype(np.int16)
    return float(np.mean(np.abs(a - b) < 22))


def _bordo_esterno(n, sinistro):
    """Dove cade il bordo ESTERNO del tasto `n` in unita' del modello (sinistro o destro).

    I tasti neri sono centrati su `u_nero` e larghi `BW`: il loro bordo esterno sta a mezzo `BW`
    dal centro, non su un confine di bianco.
    """
    if G.e_nero(n):
        return G.u_nero(n) + (-G.BW / 2 if sinistro else G.BW / 2)
    return G.u_bianco(n) if sinistro else G.u_bianco(n) + 1.0


def griglia_sui_tasti(H, rect, tastiera, info):
    """La griglia disegnata comincia e finisce dove comincia e finisce la tastiera MISURATA?

    `info['estremi']` (`tastiera_nel_video`) dice dove stanno LA0 e DO8 nell'immagine, con la x
    misurata su tutto il pezzo: sono le due colonne dei bordi gialli nel controllo. Qui si
    proietta la STESSA cosa con l'omografia della griglia che si disegna e si confrontano le due
    stime. Lo scarto e' quanto distano in x; la soglia e' mezzo tasto bianco, cioe' il massimo che
    si puo' sbagliare senza che il riquadro cada sul tasto accanto.

    E' il controllo che mancava quando un centraggio sbagliato spostava tutto di un'ottava e il
    verdetto restava "ok": misurato su `2024-02-15_21-57-38`, la prima linea verde stava a 358 px
    contro un LA0 vero a 122 px (+236 px, un'ottava appunto) mentre l'inlier era 224 e la
    plausibilita' 0,87. Guarda l'omografia e la misura, non l'inlier: sono due stime indipendenti.

    Ritorna un dict (col "ok"), o None se la tastiera non e' stata misurata e non c'e' niente da
    confrontare.
    """
    est = info.get("estremi") or {}
    if not est.get("x_la0") or not est.get("x_c8"):
        return None
    H_abs = _H_assoluta(H, rect)
    x_mod_sx = float(G.proietta(H_abs, [(_bordo_esterno(tastiera["lo"], True), 0.0)])[0][0])
    x_mod_dx = float(G.proietta(H_abs, [(_bordo_esterno(tastiera["hi"], False), 0.0)])[0][0])
    x_la0, x_c8 = float(est["x_la0"]), float(est["x_c8"])
    soglia = 0.5 * float(est.get("passo") or 33.0)
    scarto_sx, scarto_dx = x_mod_sx - x_la0, x_mod_dx - x_c8
    fuori = info.get("tasti_fuori_dalla_tastiera")
    return {"x_modello_la0": round(x_mod_sx, 1), "x_modello_c8": round(x_mod_dx, 1),
            "x_la0": round(x_la0, 1), "x_c8": round(x_c8, 1),
            "scarto_sx_px": round(scarto_sx, 1), "scarto_dx_px": round(scarto_dx, 1),
            "soglia_px": round(soglia, 1), "tasti_fuori_dalla_tastiera": fuori,
            "ok": bool(abs(scarto_sx) <= soglia and abs(scarto_dx) <= soglia
                       and (fuori in (None, 0)))}


def verifica_griglia(video, rect, H, info, Ms, estremi=None, inizio=0.0, durata=0.0, campioni=60):
    """La griglia inseguita sta DAVVERO sui tasti? Controllo indipendente, su campioni sparsi.

    Il verdetto di prima diceva "ok" con la griglia fuori posto perche' guardava solo il
    fotogramma 0, e in movimento nessuno controllava niente. Qui, per ~`campioni` fotogrammi del
    pezzo, il fotogramma si RIPORTA nel sistema del fotogramma 0 con l'inversa del moto che si
    disegna (`Ms[i]`, la stessa di griglia e ritaglio): se il moto e' giusto la tastiera
    riportata coincide con quella del fotogramma 0. Si misura di quanto NON coincide cercando lo
    scarto (dx, dy) che da' la concordanza migliore fra le due immagini: scarto ~0 = la griglia sta
    sui tasti; scarto di qualche pixel o di un tasto = griglia staccata (o agganciata al tasto
    accanto: i neri non si ripetono con periodo di un tasto, quindi non passa inosservata).

    Perche' non contare i neri "al posto giusto" come fa il fotogramma 0: una mano che copre i
    tasti per qualche fotogramma li fa sembrare "fuori posto" e darebbe falsi allarmi. Qui una mano
    abbassa la concordanza a TUTTI gli scarti ugualmente, quindi il massimo non si sposta.

    Un campione e' "buono" se lo scarto stimato e' sotto il 12% del passo (circa 4 px) in x e in y.
    Ritorna un dict per il log/json, o `{}` se non si riesce a misurare. (`H`, `info`, `estremi`
    restano nella firma per compatibilita': il controllo non ne ha bisogno.)
    """
    if not Ms:
        return {}
    x1, y1, x2, y2 = (int(v) for v in rect)
    passo = max(float(np.hypot(H[0, 0], H[1, 0])), 4.0)
    soglia = max(2, int(round(0.12 * passo)))
    cerca = int(round(0.6 * passo))
    marg = cerca + 2
    n = len(Ms)
    cada = max(1, n // max(1, campioni))
    cap, _, _ = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    T = np.array([[1.0, 0.0, -x1], [0.0, 1.0, -y1], [0.0, 0.0, 1.0]])
    ref, righe, i = None, [], 0
    while i < n:
        if not cap.grab():
            break
        if i % cada == 0:
            ok, f = cap.retrieve()
            if ok:
                try:
                    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
                    W = cv2.warpPerspective(g, T @ np.linalg.inv(np.asarray(Ms[i], float)),
                                            (x2 - x1, y2 - y1), flags=cv2.INTER_LINEAR)
                    W = cv2.GaussianBlur(W, (0, 0), 1.5)
                    if ref is None:                                # il primo campione e' il fotogramma 0
                        ref = W
                    if W.shape[0] > 2 * marg + 8 and W.shape[1] > 2 * marg + 8:
                        px = [(_concordanza(ref, W, d, 0, marg), d) for d in range(-cerca, cerca + 1, 2)]
                        py = [(_concordanza(ref, W, 0, d, marg), d) for d in range(-min(cerca, 12), min(cerca, 12) + 1)]
                        s0 = _concordanza(ref, W, 0, 0, marg)
                        dx = max(px)[1] if max(px)[0] > s0 + 0.004 else 0
                        dy = max(py)[1] if max(py)[0] > s0 + 0.004 else 0
                        righe.append((i, int(dx), int(dy)))
                except (cv2.error, np.linalg.LinAlgError, ValueError):
                    pass
        i += 1
    cap.release()
    if len(righe) < 3:
        return {}
    sx = np.array([abs(r[1]) for r in righe])
    sy = np.array([abs(r[2]) for r in righe])
    # x e y pesano diversamente: la x decide su quale tasto cade un punto (tolleranza stretta);
    # in y la griglia puo' differire di qualche pixel dal fotogramma 0 perche' la rifinitura sul
    # modello (`_rifinisci_sul_modello`) corregge proprio la scala verticale che il confronto col
    # fotogramma 0 non vede (misurato: dx 0-1 px, dy 2-4 px su tasti di 9 px)
    soglia_y = int(min(10, max(4, round(0.45 * passo))))
    scarti = np.maximum(sx, sy * soglia / soglia_y)
    buoni = int(((sx <= soglia) & (sy <= soglia_y)).sum())
    peggiori = [righe[k][0] for k in np.argsort(-scarti)[:3]]
    return {"campioni": len(righe), "campioni_buoni": buoni, "soglia_px": soglia,
            "soglia_y_px": soglia_y, "scarto_y_max_px": int(sy.max()),
            "scarto_max_px": int(sx.max()), "scarto_mediano_px": int(np.median(sx)),
            "frazione_buona": round(buoni / len(righe), 3),
            "peggiori_fotogrammi": [int(p) for p in peggiori]}


def scrivi_stabilizzato(video, out, rect, Ms, canonica, inizio, durata, ritaglio_uscita=None):
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
    # `ritaglio_uscita` = (x, y, larghezza, altezza) DENTRO il canvas: si scrive solo quel pezzo
    # (stesso raddrizzamento, stessa scala: cambia solo da dove comincia la finestra scritta). Sul
    # primo piano il canvas copre gli 88 tasti del modello mentre nel fotogramma ce ne stanno 14, e
    # senza taglio il video preparato usciva per tre quarti nero (vedi `finestra_utile`).
    # ATTENZIONE: `dst` e' il canvas INTERO spostato dell'angolo del taglio, non il rettangolo del
    # taglio: se ci si mettesse dentro anche la larghezza scritta il fotogramma verrebbe riscalato
    # (provato: il contenuto finiva fuori dalla finestra e il video usciva tutto nero).
    ox, oy = (int(ritaglio_uscita[0]), int(ritaglio_uscita[1])) if ritaglio_uscita else (0, 0)
    scritta_larg = int(ritaglio_uscita[2]) if ritaglio_uscita else larghezza
    scritta_alt = int(ritaglio_uscita[3]) if ritaglio_uscita else altezza
    dst = np.float32([[-ox, -oy], [larghezza - 1 - ox, -oy],
                      [larghezza - 1 - ox, altezza - 1 - oy], [-ox, altezza - 1 - oy]])
    cap, fps_v, _ = apri(video)
    if inizio:
        cap.set(cv2.CAP_PROP_POS_MSEC, inizio * 1000.0)
    tot, ogni = len(Ms), _ogni_avanzamento(len(Ms))
    if tot:
        print(f"[video] scrivo il video preparato con la tastiera ferma: {tot} fotogrammi "
              "(ritaglio trasportato, un fotogramma alla volta)")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{scritta_larg}x{scritta_alt}", "-r", f"{fps_v:g}", "-i", "-"]
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
                                                 (scritta_larg, scritta_alt),
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


def immagine_controllo(frame, rect, info, H, percorso, rect_viola=None):
    """Il frame 0 col rettangolo del ritaglio e la griglia trovata: UN RIQUADRO PER TASTO.

    E' lo stesso disegno del video della griglia (`scrivi_video_griglia`), ma su un fotogramma
    solo: qui c'è tutto nel dettaglio (risoluzione piena), il video dice se tiene su tutto il
    pezzo. Se la griglia scivola a metà brano è il video a mostrarlo.
    """
    im = sovrapponi_controllo(frame, rect, info, H, rect_viola=rect_viola)
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
                         Ms=None, rect_viola=None):
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

    Con `Ms` (il moto della tastiera fotogramma per fotogramma, vedi `insegui_griglia`) la griglia
    del fotogramma 0 e il ritaglio si trasportano sul fotogramma corrente con la STESSA `Ms[i]`:
    su una ripresa a camera ferma e' la stessa cosa di prima, su una a mano libera i riquadri
    restano incollati ai tasti e il rettangolo magenta li segue, sempre coerenti fra loro.
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
                # Griglia e ritaglio vengono dalla STESSA `Ms[letti]`: stessa stima, stesso fotogramma
                # (letti = indice del fotogramma originale, lo stesso di `insegui_griglia`).
                M_i = Ms[letti] if Ms and letti < len(Ms) else None
                im = sovrapponi_controllo(frame, rect, info, H, M=M_i, rect_viola=rect_viola)
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
                   help="auto (default) = insegue la griglia fotogramma per fotogramma SOLO se i 4 "
                        "angoli dei tasti bianchi si spostano (vedi `tastiera_ferma`): se restano "
                        "fermi, ritaglio e griglia del primo fotogramma bastano e il video "
                        "preparato non si ricampiona; 0 = rettangolo e griglia congelati sul primo "
                        "fotogramma; 1 = insegue sempre, senza guardare gli angoli")
    p.add_argument("--convenzione-ottava", default="scientifica",
                   help="come si chiama il Do centrale (MIDI 60): scientifica/c4 (default: C4), yamaha/c3 (C3), "
                        "c5 (C5), oppure un intero da sommare al numero d'ottava")
    p.add_argument("--canonica", type=int, default=0,
                   help="larghezza in px dell'uscita: tasti della stessa dimensione in tutti i pezzi (0 = 1:1)")
    p.add_argument("--fps", type=float, default=0, help="fps di uscita (0 = quelli del video; 30 dimezza i 60 fps)")
    p.add_argument("--griglia-video", type=int, default=1,
                   help="1 = scrive <nome>_griglia.mp4, il video col rettangolo per tasto su tutto "
                        "il pezzo (15 fps, 1280 px: pochi MB); 0 = solo l'immagine di controllo")
    p.add_argument("--inizio", type=float, default=0, help="da che secondo partire")
    p.add_argument("--durata", type=float, default=0, help="quanti secondi (0 = tutto)")
    a = p.parse_args()
    G.imposta_convenzione(a.convenzione_ottava)

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

    # Se il primo fotogramma non è una tastiera (la mano col telefono davanti ai tasti, la camera
    # che si sta assestando) si parte dal primo che legge: vedi `avvio_utile`. Si sposta `a.inizio`,
    # così campioni, inseguimento, ritaglio e `inizio_s` del json seguono tutti da soli. Non sui
    # video PianoVAM: lì gli angoli sono misurati e i tempi servono all'allineamento col MIDI.
    avvio, inizio_chiesto = None, a.inizio
    if dataset is None:
        a.inizio, frame, avvio = avvio_utile(video, a.inizio, a.durata, frame)
        if avvio:
            print(f"[avvio] {avvio}")

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

    def _prova(rect_i, info_i):
        """La griglia di un candidato nel suo ritaglio, col verdetto e la riga di log."""
        nonlocal estremi_incerto
        try:
            numeri_i = griglia_nel_ritaglio(frame, rect_i, ancora=info_i.get("ancora", False),
                                            estremi=info_i.get("_estremi"),
                                            verticale=info_i.get("_verticale"),
                                            campioni_video=info_i.get("_campioni"),
                                            obliqua=bool(info_i.get("obliqua")))
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
            return None
        return (rect_i, info_i, numeri_i, v_i, perche_i)

    for rect_i, info_i in candidati:
        esito = _prova(rect_i, info_i)
        if esito is None:
            continue
        prove.append(esito)
        if esito[3] == "ok":
            break
    # L'ultima spiaggia, per la tastiera obliqua e piccola: `candidato_obliquo` ritorna un ritaglio
    # solo quando il profilo non legge e i neri non si accoppiano fra due quote, e qui lo si prova
    # solo se NESSUN candidato di sopra è arrivato a "ok" E la scelta di oggi sarebbe "rifiuto",
    # cioè se oggi non esce nessuna griglia (con "rifiuto" il video preparato non si scrive nemmeno:
    # vedi `main`). Un video che oggi una griglia ce l'ha -- "ok" o anche solo "incerto" -- non
    # entra in questo ramo, e la scelta di prima resta identica: la griglia, il verdetto, il json e
    # il video sono quelli di prima, byte per byte. Il ripiego entra in `prove` solo se è meglio di
    # "rifiuto": non può mai peggiorare il verdetto di un video, al massimo glielo dà.
    if not any(t[3] == "ok" for t in prove) and prove:
        oggi = scelta_finale(prove, estremi_incerto)[3]
        if oggi == "rifiuto":
            obliquo = candidato_obliquo(frame)
            if obliquo is not None:
                esito = _prova(*obliquo)
                if esito is not None and esito[3] != "rifiuto":
                    prove.append(esito)
                    print("[scelta] nessun candidato arrivava a una griglia (tutti 'rifiuto'): "
                          "entra il ritaglio 'obliquo', misurato sui tasti neri uno per uno")
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
    estremi_pieni = info.get("_estremi")      # con la maschera "visto": serve a `verifica_griglia`
    info.update(numeri)
    for k in ("H0", "_estremi", "_verticale", "_y_fondo", "_s_y",
              "ancora"):   # roba di servizio: non va nel json
        info.pop(k, None)
    info["passo"] = round(info["passo"], 2)
    info["evidenza"] = round(info["evidenza"], 3)
    info["verdetto"], info["perche"] = verdetto_scelto, perche
    if avvio:                              # l'avvio cieco: si legge nel json e sul controllo
        info["avvio_cieco"] = {"inizio_chiesto": round(float(inizio_chiesto), 3),
                               "inizio_usato": round(float(a.inizio), 3), "perche": avvio}
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
        fess = ("" if e.get("fessure") is None else
                f", tasti contati su {int(e['fessure'])} fessure (somma {e['fessure_somma']:.2f}, "
                f"{e['fessure_sporche']} tratti anomali; i neri ne dicono {e.get('tasti_neri')})")
        print(f"[tastiera] misurata su tutto il pezzo: LA0 {e['x_la0']:.0f} px, DO8 {e['x_c8']:.0f} px "
              f"({e['tasti']} tasti da {e['passo']:.2f} px, {e['neri_misurati']} neri letti, "
              f"copertura {e['copertura'] * 100:.0f}%{fess})")
        print(f"[griglia] rispetto alla tastiera: {info.get('tasti_fuori_dalla_tastiera')} tasti fuori, "
              f"neri {info.get('neri_ok')} al posto giusto / {info.get('neri_coperti')} sotto una "
              f"mano o un tablet / {info.get('neri_mancanti')} fuori posto")
        if info.get("lw_fronte"):
            print(f"[fronte] tasti bianchi misurati lunghi {info['lw_fronte']} unità del modello "
                  f"(il modello ne disegna {G.LW}): i riquadri verdi arrivano al fronte vero")
        if info.get("lb_fronte"):
            print(f"[fronte] punta dei tasti neri misurata lunga {info['lb_fronte']} unità del modello "
                  f"(il modello ne disegna {G.LB}): i riquadri blu arrivano alla punta vera")
    tm = info.get("tasti_misurati")
    if tm:
        print(f"[tasti] x misurata tasto per tasto su tutto il pezzo: {tm['misurati']} misurati "
              f"({tm['neri']} neri e {tm['bordi']} bordi), {tm['incoerenti']} incoerenti "
              f"(mani/ombre: ipotizzati), {tm['ipotizzati']} ipotizzati dal vicinato; "
              f"la griglia si sposta fino a {tm['escursione_tasti']} tasti")
    print(f"[verdetto] {info['verdetto']}: {info['perche']}")

    # Ritaglio troppo largo (ripresa larga: mezza stanza dentro): se la griglia e' stata allineata
    # all'immagine e i tasti occupano poco del ritaglio, si stringe ai soli tasti. Un rettangolo
    # dato a mano (--rettangolo) non si tocca.
    if not a.rettangolo and float(info.get("ecc_cc") or 0.0) >= 0.8 and info["verdetto"] != "rifiuto":
        stretto = stringi_rettangolo(H, rect, frame.shape[:2])
        if stretto is not None:
            info["rettangolo_automatico_largo"] = [int(v) for v in rect]
            rect, H = stretto
            print(f"[rettangolo] stretto ai soli tasti: x {rect[0]}..{rect[2]}  y {rect[1]}..{rect[3]} "
                  f"({rect[2] - rect[0]}x{rect[3] - rect[1]} px): il ritaglio di prima conteneva "
                  f"molto altro oltre alla tastiera")

    # La griglia inseguita fotogramma per fotogramma (vedi `insegui_griglia`). Su una ripresa a
    # camera ferma dà la stessa cosa del rettangolo congelato; su una a mano libera è la
    # differenza fra un controllo che dice la verità e uno che mostra la griglia scivolare via
    # (e, per il video preparato, fra un ritaglio che perde i tasti a metà pezzo e uno che li
    # tiene). Gli esempi PianoVAM no: lì gli angoli sono misurati e la camera è fissa.
    insegui = str(a.insegui).strip().lower()
    auto = insegui == "auto"
    if auto:
        insegui = "" if (dataset or a.traccia) else "1"
    if insegui in ("0", "no", "false", "off", ""):
        insegui = ""

    # SE LA TASTIERA SI MUOVE LO DICONO I SUOI 4 ANGOLI (vedi `tastiera_ferma`), e si guardano PRIMA
    # di inseguire: con `auto` l'inseguimento si accende solo se gli angoli della griglia verde si
    # spostano -- anche di poco -- in qualche fotogramma del pezzo. Se restano fermi, ritaglio e
    # griglia del primo fotogramma valgono per tutto il video: la griglia non può scappare e il
    # video preparato non viene ricampionato a ogni fotogramma (è il ritaglio di sempre, pixel per
    # pixel). `--insegui 1` e `--insegui 0` restano comandi espliciti e non passano di qui.
    angoli = None
    if auto and insegui and info["verdetto"] != "rifiuto":
        try:
            fermo, angoli = tastiera_ferma(video, rect, H, a.inizio, a.durata)
        except (RuntimeError, ValueError, cv2.error) as e:
            print(f"[angoli] non riesco a misurare i 4 angoli della tastiera ({e}): si insegue come prima")
            fermo, angoli = None, {}
        if angoli:
            info["angoli_tasti"] = angoli
        if fermo:
            insegui = ""
            storti = (f"{angoli['fuori']} fotogrammi fuori tolleranza, perdonati" if angoli.get("fuori")
                      else "nessun fotogramma fuori tolleranza")
            print(f"[angoli] i 4 angoli dei tasti bianchi restano fermi su tutto il pezzo (al massimo "
                  f"{angoli['x_max_px']} px in x e {angoli['y_max_px']} px in y, {storti}): NIENTE "
                  f"inseguimento, ritaglio e griglia del primo fotogramma per tutto il video")
        elif angoli:
            dove = (f"dal fotogramma {angoli['primo_fuori']} (oltre "
                    f"{angoli['tolleranza_x_px']:.0f} px in x / {angoli['tolleranza_y_px']:.0f} px in y)"
                    if angoli.get("primo_fuori") else
                    f"ma si misurano solo sul {angoli['frazione_misurabile'] * 100:.0f}% dei fotogrammi")
            print(f"[angoli] i 4 angoli dei tasti bianchi si muovono, {dove}: inseguo la griglia e il "
                  f"ritaglio, così restano sui tasti")
    Ms, inseguito = None, None
    if insegui and info["verdetto"] != "rifiuto":
        try:
            Ms, inseguito = insegui_griglia(video, rect, H, a.inizio, a.durata, lb=info.get("lb") or G.LB)
        except (RuntimeError, ValueError, cv2.error) as e:
            print(f"[!] inseguimento non riuscito ({e}): resta il rettangolo del primo fotogramma")
            Ms, inseguito = None, None
        if not Ms or not inseguito:
            Ms, inseguito = None, None
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
                Ms = None
                inseguito["segue"] = False
                # SE LA TASTIERA SI MUOVE DAVVERO, quel ritaglio non basta: la griglia del primo
                # fotogramma esce dai tasti e il video preparato non e' piu' il pezzo. Il movimento
                # qui non lo dice l'inseguimento (ha fallito: e' il numero di cui NON fidarsi), lo
                # dicono i 4 angoli dei tasti misurati in `tastiera_ferma` -- la misura indipendente
                # che ha acceso l'inseguimento. Sopra `_SOGLIA_SEGUI_TASTI` il ritaglio fermo perde
                # la tastiera (vedi la costante) e qui il passo 0 non sa seguirla: meglio rifiutare
                # il pezzo che consegnare un video con i riquadri accanto ai tasti per tutto il
                # pezzo. Misurato su `document_5931401697506107171.mp4` (478x850, telefono a mano,
                # tastiera obliqua e sfocata): gli angoli si spostano di 54,1 px in x e 21,3 px in y
                # (tolleranze 8 e 12) dentro un ritaglio alto 68 px e l'inseguimento aggancia 12
                # fotogrammi su 80 -- dopo il motion blur dei fotogrammi 12-14 non si riprende piu'
                # (con piu' punti di riferimento, modo affine e soglie di aggancio piu' basse: 12-31
                # su 80, tutte misurate). Prima usciva lo stesso un video 478x68 "stabilizzato" con
                # la griglia sul muro: adesso il pezzo si rifiuta e il perche' sta nel json.
                # `--insegui 0` resta il modo esplicito di chiedere lo stesso il ritaglio fermo.
                if (angoli or {}).get("decisa") == "si muove":
                    motivo = (f"la tastiera si muove ({angoli['x_max_px']:.0f} px in x e "
                              f"{angoli['y_max_px']:.0f} px in y, oltre i "
                              f"{angoli['tolleranza_x_px']:.0f}/{angoli['tolleranza_y_px']:.0f} px di "
                              f"tolleranza) e l'inseguimento non l'ha tenuta "
                              f"({inseguito['agganciati']} fotogrammi su {inseguito['frame']} "
                              f"agganciati, inlier mediano {inseguito['inlier_mediano']}): col "
                              f"ritaglio fermo sul primo fotogramma la griglia esce dai tasti, quindi "
                              f"il video preparato non si scrive (un pezzo che si muove vuole una "
                              f"ripresa che lo tenga in campo; `--insegui 0` scrive lo stesso il "
                              f"ritaglio del primo fotogramma)")
                    info["verdetto"] = "rifiuto"
                    info["perche"] = f"{info['perche']}; {motivo}" if info["perche"] else motivo
                    print(f"[!] pezzo rifiutato: {motivo}")
            elif inseguito["spostamento_tasti"] > _SOGLIA_SEGUI_TASTI:
                print(f"[inseguito] la tastiera si muove: il video si ritaglia seguendola e la "
                      f"griglia resta appiccicata ai tasti (sopra {_SOGLIA_SEGUI_TASTI} tasti)")
                inseguito["segue"] = True
            else:
                # L'INSEGUIMENTO HA MISURATO CHE LA CAMERA STA FERMA, quindi la griglia del
                # fotogramma 0 vale per TUTTI i fotogrammi e il video non si ricampiona: si tiene
                # quella, come il messaggio qui sotto dice. Prima il messaggio lo prometteva e `Ms`
                # restava lo stesso: il video usciva "stabilizzato" e la griglia veniva trasportata a
                # ogni fotogramma da un moto che era solo rumore (su `2024-09-02_20-00-16`, il
                # pianoforte fermo dell'esempio 69, 0,2 tasti dichiarati e scarto in y fino a 12 px al
                # secondo 49: la griglia "traballante" che si e' vista). `Ms` diventa l'IDENTITA' --
                # non `None` -- perche' i consumatori a valle (la griglia nel tempo, il controllo in
                # movimento, `verifica_griglia`) restano gli stessi e da qui in poi vedono la griglia
                # ferma; e `verifica_griglia` con l'identita' diventa il controllo onesto che quella
                # griglia tiene su tutto il pezzo (se non tenesse, il verdetto si declassa qui sotto).
                mosso = _moto_angoli(Ms, inseguito.get("zona") or rect, H)
                inseguito["moto_angoli_tasti"] = round(mosso, 2) if np.isfinite(mosso) else None
                if mosso > _ANGOLI_MIN_TASTI:
                    # Il centro sta fermo ma gli angoli no: e' uno zoom o una rotazione, cioe' tasti
                    # che cambiano dimensione o inclinazione. Quel moto NON si butta (vedi
                    # `_moto_angoli`): la griglia del fotogramma 0 comincerebbe a sbagliare verso i
                    # bordi, dove lo scostamento e' maggiore.
                    print(f"[inseguito] il centro della tastiera sta fermo ma i suoi 4 angoli si "
                          f"spostano di {mosso:.2f} tasti (soglia {_ANGOLI_MIN_TASTI}): zoom o "
                          f"rotazione, inseguo come prima")
                    inseguito["segue"] = True
                else:
                    print(f"[inseguito] la camera sta ferma: ritaglio e griglia del primo fotogramma "
                          f"vanno bene così (i 4 angoli della zona dei tasti si spostano di "
                          f"{mosso:.2f} tasti, sotto la soglia di {_ANGOLI_MIN_TASTI}, e la griglia "
                          f"resta quella del fotogramma 0 per tutto il video)")
                    Ms = [np.eye(3)] * len(Ms)
                    inseguito["ferma"] = True
                    inseguito["segue"] = False
    if Ms is not None and inseguito:
        # Il verdetto del fotogramma 0 non vede cosa succede dopo: qui si controlla la griglia
        # inseguita (vedi `verifica_griglia`) e si DECLASSA l'"ok" se non tiene.
        ten = verifica_griglia(video, inseguito.get("zona") or rect, H, info, Ms, estremi_pieni, a.inizio, a.durata)
        if ten:
            inseguito["tenuta"] = ten
            print(f"[tenuta] griglia sui tasti in {ten['campioni_buoni']}/{ten['campioni']} campioni "
                  f"sparsi sul pezzo (scarto in x dal fotogramma 0: mediano {ten['scarto_mediano_px']} px, "
                  f"massimo {ten['scarto_max_px']} px, soglia {ten['soglia_px']} px; in y massimo "
                  f"{ten['scarto_y_max_px']} px, soglia {ten['soglia_y_px']} px; "
                  f"fotogrammi peggiori {ten['peggiori_fotogrammi']})")
        motivi = []
        if ten and ten["frazione_buona"] < 0.85:
            motivi.append(f"la griglia inseguita sta sui tasti solo in {ten['campioni_buoni']} campioni "
                          f"su {ten['campioni']} (scarto fino a {ten['scarto_max_px']} px in x, fotogrammi "
                          f"peggiori {ten['peggiori_fotogrammi']}): si stacca dai tasti")
        if inseguito["tasti_persi"] > 0.10 * inseguito["frame"]:
            motivi.append(f"l'aggancio e' perso in {inseguito['tasti_persi']} fotogrammi su "
                          f"{inseguito['frame']} (al massimo {inseguito['persi_di_fila_max']} di fila)")
        if motivi and info["verdetto"] == "ok":
            info["verdetto"], info["perche"] = "incerto", "; ".join(motivi)
            print(f"[verdetto] declassato a incerto: {info['perche']}")
        elif motivi:
            info["perche"] = info["perche"] + "; " + "; ".join(motivi)
    # LA TASTIERA COMPLETA (vedi `analizza_tastiera`): si guarda tutto il video, si decide quante note ci
    # sono e come si chiamano, e il ritaglio contiene TUTTE le note (le ipotizzate restano nere).
    rect_ext, tastiera = None, None
    if info["verdetto"] != "rifiuto":
        try:
            tastiera = analizza_tastiera(video, rect, H, Ms, frame.shape[:2], info, n_v, a.inizio)
        except (cv2.error, ValueError, np.linalg.LinAlgError, MemoryError) as e:
            print(f"[!] analisi della tastiera completa non riuscita ({e}): resta il ritaglio di prima")
    if tastiera:
        H = tastiera["H"]
        info["_poligoni"] = None                  # i riquadri si ricalcolano con le note rinominate
        rect_ext = tastiera["rect_ext"]
        info["tastiera"] = {"note": len(tastiera["note"]), "prima": G.nome(tastiera["lo"]),
                            "ultima": G.nome(tastiera["hi"]), "completa_vista": tastiera["certi"],
                            "estremo_sx_certo": tastiera["estremo_sx_certo"],
                            "estremo_dx_certo": tastiera["estremo_dx_certo"],
                            "nomi_certi": tastiera["nomi_certi"], "ottave_spostate": tastiera["ottave_spostate"]}
        print(f"[tastiera] {len(tastiera['note'])} note da {G.nome(tastiera['lo'])} a {G.nome(tastiera['hi'])}: "
              + ("tastiera completa vista (inizio e fine certi)" if tastiera["certi"] else
                 "inizio/fine non certi: si ipotizzano 88 tasti") +
              f"; nomi {'certi' if tastiera['nomi_certi'] else 'ipotizzati (ottava non verificabile)'}"
              + (f"; ottave spostate per centrare: {tastiera['ottave_spostate']}" if tastiera["ottave_spostate"] else ""))
        # IL VERDETTO DEVE VEDERE LA GRIGLIA, NON SOLO L'INLIER: se la tastiera e' stata misurata su
        # tutto il pezzo (`estremi`) si sa dove stanno LA0 e DO8 nell'immagine, e la griglia che si
        # disegna deve cominciare e finire li'. E' il controllo che mancava quando un centraggio
        # sbagliato spostava tutto di un'ottava e il verdetto restava "ok" (vedi `griglia_sui_tasti`).
        sui_tasti = griglia_sui_tasti(H, rect, tastiera, info)
        if sui_tasti:
            info["griglia_sui_tasti"] = sui_tasti
            print(f"[griglia] la griglia batte coi tasti misurati: LA0 del modello a "
                  f"{sui_tasti['x_modello_la0']:.0f} px (misurato {sui_tasti['x_la0']:.0f}, scarto "
                  f"{sui_tasti['scarto_sx_px']:+.0f}), DO8 a {sui_tasti['x_modello_c8']:.0f} px "
                  f"(misurato {sui_tasti['x_c8']:.0f}, scarto {sui_tasti['scarto_dx_px']:+.0f}); "
                  f"soglia mezzo tasto, {sui_tasti['soglia_px']:.0f} px")
            if not sui_tasti["ok"]:
                motivo = (f"la griglia non sta sulla tastiera misurata (LA0 del modello a "
                          f"{sui_tasti['x_modello_la0']:.0f} px contro {sui_tasti['x_la0']:.0f} px "
                          f"misurati, DO8 a {sui_tasti['x_modello_c8']:.0f} px contro "
                          f"{sui_tasti['x_c8']:.0f} px, soglia {sui_tasti['soglia_px']:.0f} px: i "
                          f"riquadri cadono accanto ai tasti)")
                if info["verdetto"] == "ok":
                    info["verdetto"] = "incerto"
                    print(f"[verdetto] declassato a incerto: {motivo}")
                info["perche"] = f"{info['perche']}; {motivo}" if info["perche"] else motivo
        if rect_ext is not None:
            info["ritaglio_esteso"] = [int(v) for v in rect_ext]
            print(f"[rettangolo] il ritaglio contiene tutte le note: x {rect_ext[0]}..{rect_ext[2]}  "
                  f"y {rect_ext[1]}..{rect_ext[3]} ({rect_ext[2] - rect_ext[0]}x{rect_ext[3] - rect_ext[1]} px, "
                  f"prima {rect[2] - rect[0]}x{rect[3] - rect[1]})")
    canonica_eff = a.canonica
    if rect_ext is not None and not a.canonica and (rect_ext[2] - rect_ext[0]) > _LARGHEZZA_MAX:
        canonica_eff = _LARGHEZZA_MAX            # 88 tasti a scala 1:1 sarebbero enormi: si riduce
        print(f"[rettangolo] il video preparato verrebbe largo {rect_ext[2] - rect_ext[0]} px: lo riduco a {_LARGHEZZA_MAX} px")
    if rect_ext is not None and Ms is None:      # nessun moto inseguito (fermo): identita' per allargare il ritaglio
        Ms = [np.eye(3)] * max(1, n_v if not a.durata else int(round(a.durata * fps_v)))
    # Lo spazio che resta nero dall'inizio alla fine non si scrive (sul primo piano il canvas copre
    # gli 88 tasti del modello mentre nel fotogramma ce ne stanno 14: vedi `finestra_utile`). Si
    # calcola QUI, prima del controllo, perche' il rettangolo viola deve mostrare il bordo che il
    # video preparato avra' davvero, e non il canvas intero con le bande nere.
    stabilizza_previsto = bool(Ms is not None and not a.traccia and
                               (rect_ext is not None or
                                (inseguito and inseguito["spostamento_tasti"] > _SOGLIA_SEGUI_TASTI)))
    taglio = (finestra_utile(rect_ext or rect, Ms, canonica_eff, frame.shape[:2])
              if stabilizza_previsto else None)
    finestra_uscita = (_finestra_tagliata(rect_ext or rect, taglio, canonica_eff)
                       if taglio else rect_ext)
    immagine_controllo(frame, rect, info, H, jpg, rect_viola=finestra_uscita)

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
        for k in ("_campioni", "_x_tasti", "_poligoni"):     # roba di servizio: non va nel json
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
        if stabilizza_previsto:
            stabilizzato = scrivi_stabilizzato(video, mp4, rect_ext or rect, Ms, canonica_eff,
                                               a.inizio, a.durata, ritaglio_uscita=taglio)
            if stabilizzato and taglio:
                print(f"[video] il fotogramma copre solo una parte del canvas (primo piano): scrivo "
                      f"x {taglio[0]}..{taglio[0] + taglio[2]} y {taglio[1]}..{taglio[1] + taglio[3]} "
                      f"del canvas, {taglio[2]}x{taglio[3]} px, stessa scala dei tasti")
            if not stabilizzato:
                taglio = None                # il video e' il ritaglio base: il taglio non vale piu'
            if stabilizzato:
                # Che cosa e' stato scritto DAVVERO (vedi `stabilizza_previsto` e, nel json,
                # `ritaglio_video`): il ritaglio puo' essere quello INSEGUITO (`segue`: la camera si
                # muove e `Ms` la segue) o quello FISSO del primo fotogramma, e il secondo caso ha
                # tre cause diverse, che vanno distinte perche' non sono la stessa cosa per chi legge:
                # la tastiera non si muove (lo dicono i 4 angoli, `tastiera_ferma`: il ritaglio del
                # fotogramma 0 vale per tutto il pezzo), la tastiera si muove ma l'inseguimento non
                # l'ha tenuta (`inseguito` non credibile: e' un RIPIEGO, e va detto), oppure nessuno
                # ha chiesto di seguirla (`--insegui 0`). Prima questo messaggio diceva "tastiera
                # ferma e raddrizzata" in tutti e tre i casi: chi leggeva il log credeva inseguita
                # una tastiera che nessuno aveva seguito.
                seg = inseguito or {}
                if seg.get("segue"):
                    quanto = (f" (la camera si muoveva di {seg['spostamento_tasti']} tasti"
                              + (f" e i 4 angoli della zona dei tasti di {seg['moto_angoli_tasti']}"
                                 if seg.get("moto_angoli_tasti") else "")
                              + ": col ritaglio fisso il pezzo perdeva i tasti)")
                    print(f"[video] {stabilizzato} fotogrammi con la tastiera ferma e raddrizzata"
                          f"{quanto}, audio copiato dall'originale")
                elif seg:
                    # L'inseguimento c'e' stato e NON ha tenuto la tastiera: il ritaglio fermo e' un
                    # ripiego, non una scelta. Qui gli angoli non dicono "si muove" (se lo dicessero
                    # il pezzo sarebbe stato rifiutato piu' sopra), quindi il ripiego e' innocuo --
                    # ma va detto lo stesso, e va detto che la tastiera non e' stata seguita.
                    dove = (f" (l'inseguimento non l'ha tenuta: {seg['agganciati']} fotogrammi su "
                            f"{seg['frame']} agganciati, {seg['spostamento_tasti']} tasti dichiarati)")
                    print(f"[video] {stabilizzato} fotogrammi col ritaglio FISSO del primo fotogramma"
                          f"{dove}: la tastiera NON e' stata seguita, audio copiato dall'originale")
                elif (angoli or {}).get("decisa") == "ferma":
                    # Nessun inseguimento, e non per pigrizia: gli angoli dei tasti sono stati
                    # misurati e stanno fermi, quindi il ritaglio del fotogramma 0 vale per tutto il
                    # pezzo. E' il caso piu' comune e il video e' quello giusto: dirlo con i numeri.
                    print(f"[video] {stabilizzato} fotogrammi col ritaglio del primo fotogramma, che "
                          f"qui vale per tutto il pezzo (i 4 angoli dei tasti si spostano di al "
                          f"massimo {angoli['x_max_px']} px in x e {angoli['y_max_px']} px in y, "
                          f"sotto le tolleranze di {angoli['tolleranza_x_px']:.0f}/"
                          f"{angoli['tolleranza_y_px']:.0f} px): la tastiera non si muove, audio "
                          f"copiato dall'originale")
                else:
                    # Nessun inseguimento e nessuna misura del movimento: il ritaglio fermo e' quello
                    # che e' stato chiesto (`--insegui 0`). Va detto che il movimento non si e'
                    # misurato, altrimenti "ritaglio del primo fotogramma" si legge come "tastiera
                    # ferma" e non lo sappiamo.
                    print(f"[video] {stabilizzato} fotogrammi col ritaglio FISSO del primo fotogramma "
                          f"(l'inseguimento non e' stato chiesto e il movimento dei tasti non e' stato "
                          f"misurato), audio copiato dall'originale")
        if not stabilizzato:
            scrivi_ffmpeg(video, mp4, rect, a.canonica, a.fps, a.inizio, a.durata)
        # QUEL CHE E' SALVATO, NON QUEL CHE SI SPERA: la finestra vera del video preparato -- con la
        # tastiera inseguita e' il ritaglio ALLARGATO (`rect_ext`), non il ritaglio base -- e la sua
        # dimensione. Serve perche' `larghezza_uscita` diceva la larghezza del ritaglio base anche
        # quando il video usciva dall'allargato (misurato su `2024-02-15_21-57-38`: json 1730, video
        # 1756x266) e perche' il rettangolo viola del controllo e' `rect_ext`: cosi' i due numeri
        # dicono la stessa cosa e `finestra_usata` e' la finestra da confrontare col viola.
        finestra = (rect_ext or rect) if stabilizzato else rect
        larg_eff, alt_eff = _dim_uscita(finestra, canonica_eff if stabilizzato else a.canonica)
        if stabilizzato and taglio:
            # Col taglio il video preparato non comincia piu' dall'angolo del canvas: la finestra che
            # si vede (e il rettangolo viola del controllo) e' il pezzo scritto riportato nel
            # fotogramma, e le due dimensioni sono quelle del taglio.
            finestra = finestra_uscita or finestra
            larg_eff, alt_eff = taglio[2], taglio[3]
        # "stabilizzato" solo se il ritaglio ha davvero SEGUITO la tastiera (`segue`): con
        # l'inseguimento respinto `Ms` e' l'identita' e quello che si scrive e' il ritaglio fermo del
        # primo fotogramma -- e la pagina lo chiamava "stabilizzato" lo stesso.
        salva(ritaglio_video="stabilizzato" if (stabilizzato and (inseguito or {}).get("segue")) else "fisso",
              finestra_usata=list(finestra), larghezza_uscita=larg_eff, altezza_uscita=alt_eff)
        if not stabilizzato and rect_ext is not None:
            print(f"[!] la tastiera non e' stata raddrizzata: il video preparato e' il ritaglio base "
                  f"x {rect[0]}..{rect[2]} y {rect[1]}..{rect[3]}, mentre il rettangolo viola del "
                  f"controllo e' l'allargato x {rect_ext[0]}..{rect_ext[2]} y {rect_ext[1]}..{rect_ext[3]}: "
                  f"lì il viola NON e' il bordo del video preparato")
        if tastiera and Ms is not None:
            try:
                npz, js_note = scrivi_griglia_nel_tempo(
                    mp4.with_suffix(""), video, fps_v, a.inizio, Ms, tastiera, rect,
                    (rect_ext or rect) if stabilizzato else rect, canonica_eff if stabilizzato else a.canonica,
                    stabilizzato, frame.shape[:2], G.nome(60) + " = Do centrale (MIDI 60)",
                    ritaglio_uscita=taglio if (stabilizzato and taglio) else None,
                    x_tasti=info.get("_x_tasti"))
                salva(griglia_nel_tempo=str(npz), note_json=str(js_note))
                print(f"[griglia nel tempo] {len(tastiera['note'])} note x {len(Ms)} fotogrammi salvate in {npz.name} "
                      f"({npz.stat().st_size / 1024 ** 2:.1f} MB) e {js_note.name}")
            except (cv2.error, ValueError, OSError, np.linalg.LinAlgError) as e:
                print(f"[!] non riesco a salvare la griglia nel tempo: {e}")
        if a.griglia_video:
            # Dopo il video preparato: è il controllo, non il lavoro (se fallisce non conta).
            quanti = scrivi_video_griglia(video, griglia_mp4, rect, info, H, a.inizio, a.durata,
                                          Ms=Ms, rect_viola=finestra_uscita)
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

