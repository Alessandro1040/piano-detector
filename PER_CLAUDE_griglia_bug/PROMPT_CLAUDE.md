# Incarico: sistemare il motore della griglia (tasti + note) di piano-detector

## Contesto
`piano-detector` (Python + OpenCV + ffmpeg) ricava da un video di piano la tastiera a 88 tasti e ci
proietta sopra le note. Nella schermata **`/prepara`** il **passo 0** (`addestra_tasti/0_prepara.py`)
trova il ritaglio della tastiera e ci disegna sopra **una griglia: un riquadro per tasto** (verdi i
bianchi, blu i neri, con il nome della nota) per controllare a occhio che la griglia sia giusta
prima di addestrare.

## Il problema (GUARDARE LO SCREENSHOT ALLEGATO)
File da guardare: **`SCREENSHOT_ULTIMO_problema_09-41.png`** — è l'ultimo fotogramma mostrato in
quella schermata e **riflette esattamente il difetto**.

Cosa si vede:
- le **caselle blu dei tasti neri non stanno sopra i tasti neri veri**: i tasti neri reali sporgono
  sopra le caselle (la griglia è troppo "bassa"/piccola in verticale);
- le **linee verdi** (bordi dei bianchi) sono **fuori fase**: a sinistra combaciano quasi, verso
  destra lo scarto cresce → la posizione dell'ottava sbaglia andando verso il centro/destra;
- il **rettangolo magenta** ("QUESTO È IL RITAGLIO, SEGUE LA TASTIERA") **non è coerente con la
  griglia disegnata**: è spostato in alto/sinistra ed è più largo, quindi ritaglio e griglia non
  raccontano la stessa stima;
- il difetto è **statico** (a camera ferma la griglia è già spostata) **e dinamico** (muovendosi
  deriva e non resta incollata ai tasti).

Numeri di quel fotogramma (dal log del passo 0): inlier 231, evidenza 0.90, 52 tasti; "griglia
inseguita: 1800/1800 fotogrammi, **58 riavvii**, inlier mediano 224, la tastiera si sposta di 0.53
tasti"; "tasti neri: 31 al posto giusto, 2 sotto una mano/tablet, **3 fuori posto**"; "x tasto per
tasto: 90 misurati (36 neri, 53 bordi)... escursione 1 tasti"; "**verdetto: ok** - inlier 231,
plausibilità 0.90". Nota: il verdetto dice "ok" ma a occhio la griglia è sbagliata → **il verdetto
non è affidabile**.

## Cosa era stato provato e perché ha PEGGIORATO
Prima la griglia si disegnava con l'omografia **grezza** inseguita (`Hs`) e tremava a camera ferma.
L'ultimo tentativo è stato disegnarla con la versione **lisciata** (`lisce`, EMA α≈0.35) della stessa
inseguita: in `insegui_griglia` (in `addestra_tasti/0_prepara.py`) il ritorno è diventato
`(Hs, Ms, lisce, numeri)` e `scrivi_video_griglia` / `immagine_controllo` disegnano con `lisce`.
Risultato: **peggio di prima** — griglia staccata dai tasti e rettangolo magenta non allineato alla
griglia (è lo screenshot allegato).

## Obiettivo (criteri di accettazione)
1. a camera ferma la griglia **non trema**;
2. in movimento la griglia **resta incollata ai tasti** — niente deriva né sbandamento, **anche dopo
   un riavvio del tracking** (58 riavvii in un pezzo);
3. i **riquadri stanno uno per tasto** su tutto il pezzo (blu sui neri veri, verdi sugli spazi
   bianchi), anche in mezzo alla tastiera;
4. **ritaglio (rettangolo magenta) e griglia derivano dalla stessa stima** e restano coerenti;
5. il **verdetto/log** devono accorgersi quando la griglia è fuori posto (oggi dice "ok" con tasti
   neri fuori posto).

## Vincoli
- non rompere la sincronia col MIDI (stessi fotogrammi/fps) né l'audio (copiato, non ricodificato);
- la griglia si disegna con `griglia_prospettica._disegna` (un riquadro per tasto) e deve essere la
  stessa grafica sia per `immagine_controllo` (jpg fermo) sia per `scrivi_video_griglia` (video);
- commenti in italiano, come nel resto del file.

## File in questa cartella
- `griglia_prospettica_VECCHIO.py` — (versione **con il difetto**) modello geometrico della tastiera
  88 tasti + `insegui`/`affina`/`H_iniziale`/`_disegna` (chi disegna la griglia).
- `0_prepara_VECCHIO.py` — (versione **con il difetto**) il passo 0 della
  schermata `/prepara`: `griglia_nel_ritaglio`, `insegui_griglia` (tracking + EMA `lisce`),
  `sovrapponi_controllo`, `immagine_controllo`, `scrivi_video_griglia`.
- `griglia_prospettica_NUOVO.py`, `0_prepara_NUOVO.py` — **il fix mandato da Claude**, già applicato
  nel progetto e provato: esito in `ESITO_PROVA_2.md`.
- `motore_prospettica.py` — il motore che ridisegna la griglia e disegna le note sul video finale.
- `sagome.py` — le "sagome" dei tasti usate dal motore.
- `pipeline_web.py` — il server che serve la schermata `/prepara` e lancia il passo 0.
- `prepara_video.html` — la pagina della schermata `/prepara`.
- `SCREENSHOT_ULTIMO_problema_09-41.png` — **lo screenshot del problema (guardare questo)**.
- `SCREENSHOT_09-19.png`, `SCREENSHOT_09-15.png` — fotogrammi precedenti, stesso difetto.
- `controllo_run_web_09-11.jpg` — controllo di un run precedente, per confronto.

## Come riprodurre
```bash
python addestra_tasti/0_prepara.py --video <video> --out <cartella_out> \
  --rettangolo 115,333,1845,577 --insegui 1 --griglia-video 1
```
Poi si guarda `*_preparato_griglia.mp4` (video con la griglia disegnata) e
`*_preparato_controllo.jpg` (fotogramma fermo): la griglia deve stare sui tasti per tutta la durata,
senza tremare a camera ferma e senza staccarsi in movimento.
