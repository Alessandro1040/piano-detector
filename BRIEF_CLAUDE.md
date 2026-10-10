# BRIEF — Stadio 2 della pipeline: video MP4 → MIDI

> Documento da consegnare a Claude **insieme** ai file indicati in §B.
> Contiene già tutti i fatti sull'ambiente e le API esistenti: non serve
> indovinare nulla, e le soluzioni che presuppongono librerie/API diverse
> da quelle elencate in §C verranno rifiutate in integrazione.

---

## A) Messaggio da incollare a Claude

> Ti allego `BRIEF_CLAUDE.md`, `piano_detector.py` e `README.md` del mio progetto
> "piano-detector". Lo stadio 1 (rilevamento del pianoforte su singolo frame) è
> finito, verificato in browser reale e **non va modificato**.
>
> Il brief contiene: il contratto congelato dei moduli esistenti, i fatti
> verificati sul mio ambiente (versioni reali, API disponibili, API **assenti**),
> gli errori da non ripetere e i deliverable richiesti con firme esatte.
>
> Leggi il brief per intero, poi: (1) rispondi alle 5 domande aperte di §H
> scegliendo un'opzione motivata per ciascuna; (2) produci i 6 moduli di §E
> completi e funzionanti, senza `...` né placeholder; (3) rispetta i divieti di §D.
> Non riscrivere `piano_detector.py`: importalo e usalo.

---

## B) Cosa esiste e funziona già (stadio 1, congelato)

Libreria `piano_detector.py` — YOLOv8 pre-allenato su **Open Images V7**, nessun
training. Classi usate: `piano` e `musical keyboard`. API esatta:

```python
from piano_detector import PianoDetector, PianoBox

@dataclass
class PianoBox:
    x1: int; y1: int; x2: int; y2: int
    confidenza: float
    classe: str          # "piano" | "musical keyboard"
    @property
    def larghezza(self) -> int:  # x2 - x1
    @property
    def altezza(self) -> int:    # y2 - y1

class PianoDetector:
    def __init__(self, pesi: str = "weights/yolov8l-oiv7.pt",
                 conf: float = 0.15, iou: float = 0.5,
                 device: str | None = None)
    def detect_all(self, immagine) -> list[PianoBox]      # ordinate per confidenza desc
    def detect_piano(self, immagine, margine: float = 0.0) -> PianoBox | None
    def crop_piano(self, immagine, out_path: str | None = None,
                   margine: float = 0.0) -> np.ndarray | None
    def annota(self, immagine, out_path: str | None = None,
               margine: float = 0.0) -> np.ndarray
```

- `immagine` = `np.ndarray` BGR **oppure** `str`/`Path` (gestione interna in `_carica`).
- `detect_piano` preferisce la classe `piano`; ripiega su `musical keyboard`.
- Pesi disponibili in `weights/`: `yolov8m-oiv7.pt` (veloce), `yolov8l-oiv7.pt`,
  `yolov8x-oiv7.pt`.
- Hardware di prova: video demo `demo_video.mp4` 1280×720, 12 s, 30 fps, 360 frame.

### ⚠️ Fatti misurati sul video reale (verificati, non ipotesi)

Su un frame tipico del video (frame 34, modello yolov8m, conf 0.15) le due
rilevazioni sono:

| classe | confidenza | box (x1,y1,x2,y2) |
|---|---|---|
| `musical keyboard` | 0.386 | 151, 15, 1132, 391 |
| `piano` | 0.237 | 153, 4, 1131, 636 |

**Conseguenza progettuale obbligatoria:** il box `piano` copre l'**intero
strumento** (fino a y2=636: corpo, gambe, forse la panca), **non i tasti**.
Per la geometria della tastiera va usato il box `musical keyboard` quando
presente, con `piano` come ripiego. Non ereditare la preferenza di
`detect_piano()` per lo stadio dei tasti: è corretta per "dov'è il pianoforte",
sbagliata per "dove sono i tasti".

**Secondo fatto misurato:** le confidenze su questa classe sono **basse**
(0.24–0.49) e il margine tra il box scelto e l'alternativa è spesso ~0%.
Quindi: nessuna soglia a 0.5, nessuna logica che presupponga un box preciso o
stabile. Il box è "largo" per natura e va raffinato dopo (vedi §E3).

---

## C) Fatti verificati sull'ambiente (macOS, Apple M5, 16 GB, Python 3.14.6 arm64)

Questa tabella è **verificata in questo momento** sulla macchina di destinazione.
Claude non ha accesso al terminale: tutto ciò che scrive deve essere compatibile
con questi fatti, non con la documentazione generica.

### Installato e funzionante

| pacchetto | versione | note |
|---|---|---|
| `opencv` (`cv2`) | **5.0.0** | ⚠️ vedi sotto, cambia tutto |
| `torch` | 2.14.0 | **MPS disponibile** (`torch.backends.mps.is_available() == True`), CUDA assente |
| `torchvision` | 0.29.0 | |
| `ultralytics` | 8.4.171 | |
| `numpy` | 2.4.6 | attenzione: NumPy 2.x |
| `Pillow` | 12.3.0 | |
| `onnxruntime` | 1.30.0 | provider: **CoreMLExecutionProvider**, CPUExecutionProvider |
| `pretty_midi` | **0.2.11** | già presente: la scrittura MIDI non richiede installazioni |
| `mido` | presente | alternativa |
| `scipy` | 1.18.0 | |
| `flask` | 3.1.3 | |
| `ffmpeg` / `ffprobe` | `/opt/homebrew/bin/` | disponibili a riga di comando |
| `gradio` | ≥5 | |

### Assente (verificato)

| pacchetto | stato |
|---|---|
| `mediapipe` | **non installato**, ma installabile: l'unico wheel disponibile è `mediapipe-1.0.1-py3-none-macosx_11_0_arm64.whl` → **funziona su Python 3.14 / arm64**. Modello mani ufficiale verificato raggiungibile: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` (7 819 105 byte, HTTP 200) |
| `transformers` | **non installato** (non va installato, vedi §D) |

### ⚠️ Trappola 1 — OpenCV 5.0.0: i tracker legacy NON esistono

Verificato con `dir(cv2)` su questa macchina:

```
cv2 5.0.0 — moduli/attributi "Tracker" effettivamente presenti:
  Tracker, TrackerMIL_create, TrackerMIL_Params
  TrackerVit_create, TrackerVit_Params
  TrackerNano_create, TrackerNano_Params
  TrackerDaSiamRPN_create, TrackerDaSiamRPN_Params

ASSENTI:  cv2.TrackerCSRT_create   cv2.TrackerKCF_create
          cv2.TrackerMOSSE_create  cv2.legacy  (modulo rimosso del tutto)
```

Quindi: **CSRT, KCF, MOSSE e MedianFlow non sono utilizzabili**. Qualsiasi
snippet con `cv2.TrackerCSRT_create()` solleva `AttributeError` alla prima
esecuzione. Usare solo `TrackerMIL_create` / `TrackerVit_create` /
`TrackerNano_create` / `TrackerDaSiamRPN_create`, oppure — meglio — un
tracker proprio basato su template matching (`cv2.matchTemplate` con
`TM_CCOEFF_NORMED`) + ricerca locale, che non dipende dal modulo legacy ed è
più controllabile. `TrackerVit`/`TrackerNano`/`DaSiamRPN` richiedono file di
modello ONNX scaricati a parte: se li proponi, devi indicare esattamente da
dove e come, altrimenti si resta offline.

### ⚠️ Trappola 2 — MediaPipe 1.0.1: l'API `mp.solutions` NON esiste più

Ispezionando il contenuto del wheel (senza installarlo) **non c'è nessun
`mediapipe/solutions/hands.py`**. L'unica API per le mani presente è:

```
mediapipe/tasks/python/vision/hand_landmarker.py
```

Quindi `import mediapipe as mp; mp.solutions.hands.Hands(...)` **fallisce**.
Va usata l'API Tasks:

```python
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
```
con `vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(...))`,
`num_hands=2`, `running_mode=vision.RunningMode.VIDEO` (serve un timestamp in ms
crescente e monotono) e un modello `.task` da fornire come file locale.

### ⚠️ Trappola 3 — installare mediapipe tocca OpenCV

`pip install mediapipe` su questa macchina installa:
`mediapipe-1.0.1`, `opencv-contrib-python-5.0.0.93`, `sounddevice-0.5.6`.

Nota: `opencv-contrib-python` **co-installa** con `opencv-python` già presente
(entrambi forniscono il modulo `cv2`, è il classico conflitto "doppio OpenCV").
Conseguenza: leggi di §C-trappola-1 vanno riverificate **dopo** l'installazione
di mediapipe, perché il `cv2` effettivamente importato potrebbe cambiare.
Il codice non deve quindi dipendere da un singolo tracker esotico ma avere un
percorso di fallback.

---

## D) Errori da NON ripetere (dal piano precedente, verificati come errati)

1. **Grounding DINO / `transformers` / zero-shot detection: da scartare.**
   Il problema "trova la tastiera" è **già risolto e validato** con YOLOv8-OpenImages.
   Aggiungere `transformers` + `IDEA-Research/grounding-dino-tiny` significa
   ~700 MB di pesi, un'inferenza molto più lenta, una dipendenza che su Python
   3.14 non è verificata, e zero guadagno: `PianoDetector` è già la fase 1.
   Il piano precedente si contraddiceva da solo: la sua "strategia ottimale"
   finale (rileva sul 1° frame → traccia → ricalcola se il tracker perde) è
   **esattamente** la cosa da implementare, **senza** Grounding DINO.
2. **`cv2.TrackerCSRT` / `MedianFlow`: non esistono (vedi §C-trappola 1).**
3. **`mp.solutions.hands`: non esiste (vedi §C-trappola 2).**
4. **Nessuna modifica a `piano_detector.py` e `app.py`**: sono congelati.
5. **Nessuna conversione video lato server "a mano"** con `cv2.VideoWriter` +
   `mp4v`, che produce file senza audio e spesso illeggibili in browser.
   Per il video di debug va usato un codec che `ffmpeg` accetta (`ffv1`/`.mkv`
   o `libx264` + `-pix_fmt yuv420p`), oppure si scrivono i frame e si monta con
   `ffmpeg` passando `-r` esplicito.
6. **Vietato il mapping ingenuo dito↔tasto** ("se il landmark cade dentro il
   rettangolo del tasto, la nota è premuta"): le dita stazionano sopra i tasti
   anche senza premere → tutte le note suonerebbero sempre. Serve un criterio di
   *pressione* con isteresi (vedi §E5).

---

## E) Deliverable richiesti

6 file nuovi nella cartella del progetto. Nomi e firme **vincolanti**: verranno
importati così come sono da un orchestratore già scritto.

### E1 — `keyboard_tracker.py`

Traccia il riquadro della tastiera **senza** ricalcolare la rete neurale su ogni
frame; ritorna a ricalcolare da solo quando perde il bersaglio.

```python
@dataclass
class Traccia:
    x1: int; y1: int; x2: int; y2: int
    confidenza: float          # confidenza "di tracciamento" 0-1
    origine: str               # "detector" | "tracker"
    frame: int

class KeyboardTracker:
    def __init__(self, detector: "PianoDetector", conf: float = 0.15,
                 tracker: str = "template", intervallo_redetect: int = 30,
                 soglia_somiglianza: float = 0.55, ema: float = 0.35) -> None
    def init(self, frame: np.ndarray, frame_idx: int = 0) -> Traccia | None
    def update(self, frame: np.ndarray, frame_idx: int) -> Traccia | None
    def reset(self) -> None
```

Requisiti:
- `tracker="template"` (default, obbligatorio che funzioni): template matching
  `cv2.matchTemplate` con `TM_CCOEFF_NORMED` su una finestra di ricerca attorno
  alla posizione precedente (search radius ~ max(40, 0.25*altezza)), template
  aggiornato con EMA e **non** a ogni frame (evita il drift).
- `tracker="mil"`: usa `cv2.TrackerMIL_create()` con lo stesso contratto.
- Rilevazione periodica ogni `intervallo_redetect` frame **e** forzata quando la
  somiglianza scende sotto `soglia_somiglianza`; il ricalcolo usa `detect_all`
  e **preferisce la classe `musical keyboard`** (vedi §B, fatto misurato).
- `ema`: smoothing esponenziale del box per evitare jitter (0 = nessuno).
- Se non c'è né traccia né rilevazione → ritorna `None` (mai un box inventato).
- Il box deve restare sempre dentro i bordi del frame.
- Nessun uso di `cv2.legacy`, CSRT, KCF, MOSSE.

### E2 — `hands.py`

Landmark delle mani sul frame **originale** (non sul crop: i landmark del crop
vanno riportati, quindi è più semplice e più stabile lavorare sul frame intero e
usare il box solo per filtrare).

```python
@dataclass
class Mano:
    punte: dict[int, tuple[float, float]]   # {4: (x,y), 8: (...), 12, 16, 20}
    tutte: list[tuple[float, float]]        # 21 landmark (x,y) in pixel
    mano: str                               # "Left" | "Right"
    confidenza: float

class HandTracker:
    def __init__(self, modello: str = "weights/hand_landmarker.task",
                 max_mani: int = 2, soglia: float = 0.3) -> None
    def processa(self, frame: np.ndarray, timestamp_ms: int) -> list[Mano]
    def chiudi(self) -> None
```

Requisiti:
- **API Tasks** obbligatoria (`mediapipe.tasks.python.vision.HandLandmarker`),
  `RunningMode.VIDEO`, timestamp ms monotono crescente. Divieto assoluto di
  `mp.solutions.*`.
- Import di mediapipe **pigro** dentro `__init__`: se manca, `ImportError` con
  messaggio esplicito che dice esattamente `python3 -m pip install mediapipe` e
  dove scaricare il file `.task`:
  `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`
  → `weights/hand_landmarker.task` (7.5 MB, URL verificato raggiungibile).
  Il resto della pipeline deve poter girare
  senza mediapipe (con `--senza-mani`) senza crash all'import del modulo.
- I landmark sono **normalizzati 0-1** dall'API: convertili nelle coordinate
  pixel del frame passato (larghezza/altezza reali).
- Soglie consigliate: `min_hand_detection_confidence=0.3`,
  `min_hand_presence_confidence=0.3`, `min_tracking_confidence=0.3`.
- Se ci sono 2 mani, distinguile con `handedness` e mantieni l'ordine stabile
  fra i frame (es. ordina per x media) per non far "saltare" le note.

### E3 — `keyboard_grid.py`

Costruisce la geometria dei tasti **dentro** il riquadro della tastiera.

```python
@dataclass
class Tasto:
    nota: int          # numero MIDI (A0 = 21, C8 = 108)
    nome: str          # "C4", "F#3", ...
    nero: bool
    poligono: list[tuple[float, float]]   # 4 vertici nel frame originale

class KeyboardGrid:
    def __init__(self, prima_nota: int = 21, n_ottave: int = 7,
                 altezza_bianchi: float = 0.62, larghezza_neri: float = 0.60,
                 prospettiva: bool = True) -> None
    def costruisci(self, traccia: "Traccia", frame_shape: tuple[int, int]) -> list[Tasto]
    def nota_a(self, punto: tuple[float, float], margine_px: float = 0.0) -> int | None
    def frame_raddrizzato(self, frame: np.ndarray, traccia: "Traccia",
                          larghezza: int = 1200) -> tuple[np.ndarray, np.ndarray]
    #   -> (immagine raddrizzata, matrice omografia 3x3)
```

Requisiti:
- Il numero di tasti visibili **dipende dall'inquadratura**: parametro esplicito
  `prima_nota` + `n_ottave`, con default ragionevoli, e un metodo
  `stima_estensione(traccia, larghezza_frame) -> tuple[int, int]` che proponga
  l'estensione assumendo ~2.2 cm per tasto bianco rapportati alla larghezza:
  documenta chiaramente l'assunzione e l'errore risultante (una trasposizione
  di un'ottava è il rischio tipico se sbagli `prima_nota`).
- Se `prospettiva=True`: modello a **quadrilatero** (i 4 vertici della tastiera
  rilevata, non un rettangolo assi-allineato) + omografia verso un rettangolo
  canonico → la griglia si costruisce in coordinate raddrizzate e si riporta
  indietro con l'omografia. Questo è ciò che rende la griglia **stabile** anche
  se la videocamera si muove, inclina o ruota.
- I tasti neri non sono centrati: nel pattern di un'ottava gli offset dei neri
  (in semitoni sopra il Do) sono `{1, 3, 6, 8, 10}`; la loro posizione orizzontale
  ha uno scostamento noto rispetto ai bianchi e la loro lunghezza è
  `1 - altezza_bianchi` rispetto alla profondità del tasto. Documenta la formula
  esatta usata.
- `nota_a()` deve **ignorare i pixel fuori dai tasti** e, in caso di sovrapposizione
  nero/bianco, dare priorità al **nero** (è più in alto), perché l'area del nero
  è disegnata sopra le due porzioni di bianchi adiacenti.
- Il nome della nota va da numero MIDI: usa la notazione scientifica
  (MIDI 60 = `C4`), così come la userà il MIDI finale.

### E4 — `note_events.py`

Trasforma la sequenza (mani + griglia) in **eventi nota con onset/offset**.
Questo è il modulo dove si vince o si perde la trascrizione.

```python
@dataclass
class EventoNota:
    nota: int
    onset: float          # secondi dall'inizio del video
    offset: float
    velocity: int         # 1-127
    profondita: float     # 0-1, quanto il dito è sceso sotto il piano dei tasti
    mano: str

class RilevatoreNote:
    def __init__(self, fps: float, soglia_giu: float = 0.06, soglia_su: float = 0.03,
                 durata_minima: float = 0.05, durata_massima: float = 3.0,
                 distanza_minima_mani: float = 0.4) -> None
    def aggiorna(self, frame_idx: int, mani: list["Mano"],
                 griglia: "KeyboardGrid") -> list[EventoNota]
    def chiudi(self) -> list[EventoNota]
```

Requisiti:
- **Nessun test "il dito è dentro il rettangolo del tasto"**. La pressione va
  determinata con l'**isteresi** sulla *profondità*: distanza del polpastrello
  dalla linea del bordo superiore dei tasti, normalizzata sull'altezza del tasto.
  `soglia_giu` attiva la nota, `soglia_su` (più piccola) la rilascia: senza
  isteresi, il jitter di MediaPipe produce decine di note-nota-off fittizie.
- Ricostruzione dell'onset con **anti-rimbalzo**: una nota non può ripartire
  entro `durata_minima` dal suo offset; note più corte di `durata_minima` vengono
  scartate; note più lunghe di `durata_massima` vengono troncate (dito fermo).
- `velocity` derivata da `profondita` (mappa lineare 0→40, 1→127), non costante.
- Deve funzionare anche con **solo una mano** e con **zero mani** per molti frame
  (nessun crash, nessuna nota fantasma).
- Gestione del caso "mediapipe perde la mano per 1-2 frame" (buco di rilevazione):
  mantieni la nota attiva fino a un timeout breve invece di chiuderla subito.
- Output deterministico: a parità di input, stessi eventi.

### E5 — `to_midi.py`

```python
def salva_midi(eventi: list["EventoNota"], out_path: str,
               bpm: float = 120.0, programma: int = 0) -> str
def salva_json(eventi: list["EventoNota"], out_path: str) -> str
def riepiloga(eventi: list["EventoNota"]) -> dict
```
Requisiti: usa **`pretty_midi`** (già installato — niente nuove dipendenze).
Tempo irrilevante: gli onset sono in **secondi assoluti**, quindi `bpm` serve solo
per la mappa dei tick. Nota 0-127 valida, `note_on`/`note_off` bilanciati,
nessuna nota con `offset <= onset`. `riepiloga` restituisce conteggi
(nota più suonata, durata media, note al secondo, intervallo MIDI coperto).

### E6 — `pipeline.py` (orchestratore, CLI)

```bash
python pipeline.py video.mp4 -o out/ \
    --modello yolov8l --conf 0.15 --fps-max 30 \
    --tracker template --senza-mani --prima-nota 21 --n-ottave 7 \
    --debug-video --limite 200
```
Deve: aprire il video con `cv2.VideoCapture`, leggere fps e dimensioni, applicare
E1 su ogni frame, E2 ogni frame, E3, E4; alla fine E5. Produrre in `out/`:
`notes.json`, `song.mid`, `debug.mp4` (solo con `--debug-video`),
`prima_griglia.jpg` (frame 1 con i tasti disegnati e le note etichettate).
Stampare un riepilogo leggibile. Accettare `--limite N` per test rapidi.
Deve degradare con grazia: se il tracker o le mani non trovano nulla, avvisa e
continua, senza eccezioni non gestite.

---

## F) Schema JSON di `notes.json` (vincolante)

```json
{
  "video": "demo_video.mp4",
  "fps": 30.0,
  "frame_totali": 360,
  "durata_s": 12.0,
  "larghezza": 1280,
  "altezza": 720,
  "estensione_tastiera": {"prima_nota": 21, "ultima_nota": 108, "n_tasti": 88},
  "eventi": [
    {"nota": 60, "nome": "C4", "onset": 1.234, "offset": 1.512,
     "durata": 0.278, "velocity": 92, "profondita": 0.41, "mano": "Right",
     "frame_onset": 37, "frame_offset": 45}
  ],
  "riepilogo": {"n_eventi": 1, "note_uniche": 1, "note_al_secondo": 0.08,
                "durata_media": 0.278, "nota_piu_frequente": 60}
}
```

Tutti gli array ordinati per `onset` crescente. Nessun `NaN`/`Infinity` nel JSON
(JSON non li supporta): arrotonda a 3 decimali.

---

## G) Definition of done

Perché il lavoro sia accettato (verrà eseguito sul video reale `demo_video.mp4`,
1280×720, 30 fps):

1. `python3 -m py_compile` passa su tutti i file.
2. `python pipeline.py demo_video.mp4 -o out_test/ --limite 60 --senza-mani`
   termina **senza eccezioni** e produce un `prima_griglia.jpg` in cui i tasti
   sono disegnati sopra la tastiera reale con etichette di nota leggibili.
3. `python pipeline.py demo_video.mp4 -o out_test2/ --debug-video` (se mediapipe
   è installato) traccia le mani e produce un `notes.json` non vuoto con
   `note_on`/`note_off` bilanciati.
4. Il `.mid` si apre con `pretty_midi` e le note sono nella gamma 21-108.
5. Nessun `import` di `transformers`, `torch.hub`, `cv2.legacy`,
   `cv2.TrackerCSRT`, `cv2.TrackerKCF`, `cv2.TrackerMOSSE`, `mp.solutions`.
6. Nessun download implicito a runtime: tutti i modelli sono file locali e il
   percorso è indicato con un errore chiaro se mancano.
7. Il codice è in **italiano** per nomi di dominio (come il resto del progetto:
   `PianoBox`, `Traccia`, `Tasto`, `EventoNota`, `RilevatoreNote`) e in inglese
   per i termini tecnici standard. Docstring in italiano, come `piano_detector.py`.

---

## H) Decisioni aperte — rispondi scegliendo un'opzione (motiva in 2 righe)

1. **Tracker**: template matching proprio (consigliato, zero dipendenze) oppure
   `cv2.TrackerMIL_create`? E con quale intervallo di ri-rilevazione?
2. **Riquadro o quadrilatero**: la griglia va costruita su un rettangolo
   assi-allineato (semplice, si rompe se la tastiera è inclinata/prospettica)
   oppure su un quad + omografia (più robusta, più codice)? Nel video reale la
   tastiera è vista dall'alto ma non perfettamente frontale: quale scegli e perché.
3. **Origine della tastiera**: quali note sono visibili? Solo una parte della
   tastiera è inquadrata, quindi `prima_nota` è il parametro che determina se la
   trascrizione è corretta o trasposta. Proponi una strategia di
   auto-calibrazione, o dichiara esplicitamente che è un input manuale.
4. **Pressione**: confermi l'isteresi sulla profondità del polpastrello?
   Con quali soglie di default, e come normalizzi la profondità (rispetto
   all'altezza del tasto o alla distanza fra le due linee di riferimento)?
5. **Onset preciso**: l'istante di pressione reale sta *fra* due frame
   (30 fps = 33 ms). Fai interpolazione lineare sull'attraversamento della soglia
   o usi il frame intero? L'interpolazione riduce l'errore di timing: vale la pena?

---

## I) Cosa succede al tuo output (perché il brief è così rigido)

I moduli verranno eseguiti davvero su questa macchina e verificati con dati reali:
`VideoCapture` sul video demo, ricerca di `AttributeError`/`ImportError` a
runtime, apertura del `.mid` generato, conteggio degli eventi nota, e ispezione
visiva di `prima_griglia.jpg` per capire se i tasti sono geometricamente corretti.
Le firme di §E esistono perché l'integrazione avvenga **senza adattamenti**:
un `import` che fallisce o un nome diverso costa un giro di correzioni.

Quindi: meglio un modulo in meno e corretto che 6 moduli con `# TODO`.
Se una parte non è implementabile con ciò che è installato, **dillo**
esplicitamente con l'alternativa concreta, invece di scrivere codice che
presuppone librerie presenti in un altro ambiente.
