# BRIEF n.2 — Motore "calibrato": le sagome per nota (un video → 88 clip)

> Documento da consegnare a Claude, nella cartella `/Users/alessandrolocurcio/Downloads/piano-detector/`.
> Affianca `BRIEF_CLAUDE.md` (stadio 2, già consegnato e funzionante): non lo sostituisce.
> Contiene i fatti verificati sui file attuali, le firme richieste e i divieti: le soluzioni che
> presuppongono altre librerie (elenco in §C) verranno rifiutate in integrazione.

## A) Messaggio da incollare a Claude

> Ti allego `BRIEF_CLAUDE_2_SAGOME.md` (più `README.md`, `pipeline_web.py`, `pipeline_studio.html`,
> `keyboard_grid.py`, `keyboard_tracker.py`, `note_events.py`) del progetto `piano-detector`.
> Già consegnato e funzionante, **da non riscrivere**: `piano_detector.py`, i 6 moduli dello
> stadio 2 (`pipeline.py`, `keyboard_tracker.py`, `hands.py`, `keyboard_grid.py`,
> `note_events.py`, `to_midi.py`), l'editor dei 4 angoli e il motore **PPAN** (quest'ultimo:
> sola lettura, non si tocca).
> Il motore **nostro** ("pipeline") trascrive male: deduce i tasti da una geometria stimata e le
> pressioni dalla profondità del polpastrello, quindi basta una piccola imprecisione sul
> quadrilatero e la griglia scivola di un tasto → tutte le note trasposte.
> Voglio una strada nuova, il motore **calibrato** (§D): per il video che sto trascrivendo il
> **software** capisce la regione del pianoforte e **disegna lui un riquadro per ogni nota in ogni
> frame** (l'area che il computer deve guardare per quella nota), poi ne ricava **88 clip, una per
> nota, ciascuna lunga tutto il video**, con dentro **solo** quella nota.
> Leggi il brief per intero, poi: (1) rispondi alle 4 decisioni di §I scegliendo un'opzione
> motivata in 2 righe ciascuna; (2) produci i deliverable di §E completi e funzionanti, senza
> `...` né `# TODO`; (3) rispetta i divieti di §H.
> Se una parte non è implementabile con ciò che è installato (§C), **dillo** con l'alternativa
> concreta invece di scrivere codice che presuppone altre librerie.

## B) Cosa esiste già — verificato sui file, non ipotesi

Cartella di lavoro: `/Users/alessandrolocurcio/Downloads/piano-detector/`.

| file | righe | ruolo |
|---|---|---|
| `piano_detector.py` | 202 | YOLOv8 Open Images V7: `piano` / `musical keyboard`. **Congelato** |
| `keyboard_tracker.py` | 395 | insegue il riquadro della tastiera fra i frame (`Traccia`, `_raffina_quad`, `_segui_template`) |
| `keyboard_grid.py` | 251 | geometria degli 88 tasti: `MIDI_MIN, MIDI_MAX = 21, 108`, `_N_BIANCHI_88 = 52`, `Tasto`, `KeyboardGrid(prima_nota, n_ottave, altezza_bianchi=0.62, larghezza_neri=0.60)`, `nota_a`, `frame_raddrizzato`, `stima_estensione`, `nome_nota`, `e_nero` |
| `note_events.py` | 282 | pressioni → eventi (`soglia_giu=0.06`, `soglia_su=0.03`, `EventoNota`, `RilevatoreNote`) |
| `hands.py` / `pipeline.py` / `to_midi.py` | 145 / 379 / 139 | mediapipe, orchestrazione, MIDI |
| `pipeline_web.py` | 696 | server Flask dello Studio, porta `PORTA` (7862), `RUNS = web_runs/`, upload max 4 GB |
| `pipeline_studio.html` | 1433 | la pagina (4 sezioni: `1 Video di input`, `2 Motore e parametri`, `3 Esecuzione`, Log, Esecuzioni precedenti) |
| `ppan_bridge.py` | 246 | converte l'uscita di PPAN nello schema della pipeline |

Fatti da tenere presenti:

- **Rotte esistenti**: `GET /`, `/favicon.ico`, `/api/stato`, `/api/jobs`, `POST /api/job`,
  `GET /api/job/<id>`, `POST /api/job/<id>/annulla`, `POST /api/job/<id>/elimina`,
  `GET /api/job/<id>/file/<nome>`. Ogni esecuzione vive in `web_runs/<id>/` con la sottocartella
  `out/`; `job.json` contiene `log`, `meta`, `riepilogo`, `eventi`. Il server rifiuta l'avvio con
  meno di 1 GB libero.
- **Il server non importa torch/mediapipe**: lancia il motore come **sottoprocesso** (primo venv
  disponibile: `.venv-mp10`). Un motore nuovo deve rispettare lo stesso schema:
  sottoprocesso → `out/notes.json` + `out/prima_griglia.jpg`.
- **Editor dei 4 angoli già pronto** nella pagina: `#quadCanvas` in `#stage`, pulsanti `#btnQuad`
  / `#btnQuadAuto`, funzioni `scalaTela`, `posizionaTela`, `ordinaQuad`, `ridisegna`, `salvaQuad`,
  `pixelVideo`, `attivaEditor`. **Riusalo**, non riscriverlo.
- **La pagina non ha webcam**: non esistono `getUserMedia` né `MediaRecorder`. L'input è solo
  `<input type="file" id="file">` + drag&drop su `#stage`, video in `<video id="preview">`.
- **Template matching già usato in casa**: `keyboard_tracker.py::_segui_template`
  (`cv2.matchTemplate`); `cv2.matchTemplate` è quindi una tecnica accettata.
- **Parametri già esposti** da `pipeline_web._comando()`: `--prima-nota`, `--ultima-nota`,
  `--n-ottave`. Oggi "quali tasti sono inquadrati" è un input manuale.
- **La pagina usa già una tastiera virtuale** per il piano roll (88 tasti, id `statKeys`, ecc.):
  riusala per mostrare quali note hanno la sagoma.

## C) Ambiente — verificato, non indovinarlo

macOS, **Apple M5**, 16 GB, **Python 3.14.6 arm64**.
Presenti: `cv2` **5.0.0**, `torch` 2.14.0 (MPS attivo, no CUDA), `torchvision` 0.29.0,
`ultralytics` 8.4.171, `numpy` 2.4.6, `Pillow` 12.3.0, `onnxruntime`, `pretty_midi` 0.2.11,
`mido`, `scipy`, `librosa`, `soundfile`, `torchaudio`, `flask`, `gradio`,
`ffmpeg`/`ffprobe` in `/opt/homebrew/bin/`.
Assenti nel venv principale: `mediapipe` (sta solo in `.venv-mp10` come **0.10.35**),
`transformers`, `basic_pitch`.

Tre trappole già pagate, da non ripetere:
1. **OpenCV 5: `cv2.legacy` non esiste** → niente `TrackerCSRT/KCF/MOSSE`; ci sono
   `TrackerMIL/Vit/Nano/DaSiamRPN`.
2. **`mediapipe==1.0.1` è rotto** (SIGABRT su ogni grafo Tasks Vision): usare `0.10.35` in
   `.venv-mp10`.
3. `weights/yolov8x-oiv7.pt` è **troncato** (100 MiB esatti): usare `yolov8l` / `yolov8m`.

Spazio libero su disco ~9,6 GB: **da tenere conto** quando si decide il formato delle 88 clip (§I.2).

## D) Cosa deve fare il motore "calibrato"

### D0 — Cos'è una "sagoma" (definizione, non interpretabile)

Una **sagoma è un rettangolo**: l'area del frame dove il computer deve guardare per decidere se
*quella* nota è premuta *in quel* frame. Non è un'impronta da addestrare, non è un modello, non è
un file scaricato da qualche parte: è **geometria misurata su quel video, frame per frame**. Il
**software la disegna da solo**: l'utente non disegna nulla, né per nota né per frame (se non,
volendo, i 4 angoli della tastiera che esistono già).

### D1 — Le 5 fasi, in quest'ordine

1. **Regione del pianoforte.** Prima si capisce *dove sono i tasti* nel video: YOLO (`musical
   keyboard`, con `piano` come ripiego) + il raffinamento del quadrilatero già in
   `keyboard_tracker.py`, + i 4 angoli manuali se l'utente li ha segnati. Se la camera si muove,
   la regione va **seguita frame per frame** (è già quello che fa `keyboard_tracker`).
2. **Riquadri per nota, per frame.** Dentro la regione, per **ogni frame** e per **ogni nota**
   MIDI 21…108, si calcola il rettangolo del tasto (proiezione della geometria di
   `keyboard_grid.py`, **raffinata sull'immagine**: banda dei tasti neri, confini dei bianchi).
   Ogni rettangolo porta con sé se quel tasto è davvero **inquadrato** in quel frame.
3. **88 clip.** Si scrive **una clip per nota**, e ogni clip contiene **tutti i frame e tutti i
   secondi del video**, con dentro **solo** quella nota (il resto fuori, o non disegnato: vedi
   §I.2). Quindi: 88 file, nessuno più corto del video.
4. **Decisione per nota.** Dentro il rettangolo di una nota, frame dopo frame, si decide
   premuto/rilasciato guardando i pixel (differenza rispetto ai frame di riposo, isteresi,
   chiusura per assenza). Il risultato sono eventi `note_on`/`note_off`.
5. **Uscita.** `out/notes.json` nello **schema della pipeline** (stessi campi di `pipeline.py`:
   `eventi`, `riepilogo`, `estensione_tastiera`; 3 decimali; niente `NaN`), `out/prima_griglia.jpg`
   con i riquadri per nota disegnati sui tasti, e `out/sagome/` con le 88 clip. Così tabella,
   statistiche, piano roll, player MIDI e download continuano a funzionare **senza modifiche**
   alla pagina.

### D2 — Tre regole dure (sono il motivo per cui esiste questo motore)

- **Nota non inquadrata → mai emessa.** Se il rettangolo di una nota non esiste in un frame
  (il tasto è fuori dalla regione), quella nota non può comparire nell'output. È il difetto
  speculare a quello di PPAN, che assume sempre 88 tasti A0–C8 e inventa le note mancanti.
- **Nota inquadrata ma non premuta → nessun evento.**
- **Un tasto tenuto = una nota.** Se un tasto resta premuto per 20 frame consecutivi esce **una**
  nota (un `note_on` all'inizio, un `note_off` alla fine), non 20 eventi.

### D3 — Ottava ambigua: si decide **guardando tutti i frame**

Se il video inquadra solo una parte della tastiera, il disegno dei tasti neri si ripete ogni 12
semitoni: **un singolo frame non basta** a dire *quale* ottava si sta vedendo. La decisione va
presa sull'**intero video** (finestra coerente nel tempo, insieme di note coerenti col numero di
tasti inquadrati, pattern dei neri, spostamento della finestra fra i frame).
Se l'ambiguità **resta**, l'output deve **dirlo**: nel JSON si scrivono l'ottava scelta e la prova,
oppure la lista delle candidate con il motivo dell'incertezza. Vietato indovinare in silenzio.

### D4 — La sagoma è del **singolo video**, non una libreria

I riquadri (e le 88 clip) sono calcolati **per quel video** e vivono nel progetto sotto
`web_runs/<id>/sagome/`. **Quando l'utente cambia video, spariscono** e si ricalcolano da zero:
nessuna cartella di sagome permanente, nessun riuso fra video diversi.

## E) Deliverable (firme richieste)

1. **`sagome.py`** — "dove guardare", per nota e per frame.

```python
@dataclass
class RiquadroNota:
    nota: int; nome: str; nero: bool
    frame: int; t: float
    x1: int; y1: int; x2: int; y2: int   # pixel del frame originale
    visibile: bool                       # True solo se il tasto e' dentro la regione inquadrata
    confidenza: float                    # 0..1: bonta' della misura su quel frame

@dataclass
class SagomeVideo:
    video: str; fps: float; n_frame: int
    quad: list[list[tuple[float, float]]]         # la regione, per frame (se la camera si muove)
    riquadri: dict[int, list[RiquadroNota]]       # nota -> un riquadro per frame
    visibili: list[int]                           # note che il video inquadra davvero
    ottava: dict                                  # {"scelta": int | None, "candidate": [...], "prova": {...}}

def regione_tastiera(video, *, quad=None, ogni_frame: bool = True,
                     max_secondi: float | None = None) -> list[list[tuple[float, float]]]
def riquadri_per_frame(video, quad, *, nota_min: int = 21, nota_max: int = 108) -> SagomeVideo
def scrivi_clip_per_nota(s: SagomeVideo, video, cartella, *, formato: str = "mp4") -> list[Path]
def salva_sagome(s: SagomeVideo, path) -> Path
def carica_sagome(path) -> SagomeVideo
```

   `riquadri_per_frame` è il cuore: proiezione della griglia + **raffinamento sull'immagine**, così
   un piccolo scarto non trasla tutte le note. `visibile=False` quando il tasto cade fuori regione.

2. **`motore_calibrato.py`** — il rilevatore.

```python
class RilevatoreCalibrato:
    def __init__(self, sagome: SagomeVideo, *, soglia_giu: float = 0.6,
                 soglia_su: float = 0.4, finestra: int = 5) -> None
    def analizza(self, video, out_dir, *, max_secondi: float | None = None) -> dict
    def note_emesse(self) -> list[int]
```

   `analizza()` scrive `notes.json` + `prima_griglia.jpg` + `sagome/` come in §D1.5.

3. **Rotte** in `pipeline_web.py`: `POST /api/job` con `motore=calibrato` (sottoprocesso, come
   PPAN), `GET /api/job/<id>/sagome.json`, `GET /api/job/<id>/clip/<nota>` (serve la clip di una
   nota), e la cancellazione di `sagome/` quando si cambia video (§D4).

4. **UI** in `pipeline_studio.html`: sezione nuova, visibile **solo** col motore *calibrato*, con
   la griglia delle 88 note (riusa la tastiera virtuale della pagina): clic su una nota → si apre
   la **sua clip**; le note **senza riquadro** (tasto non inquadrato) si vedono a colpo d'occhio e
   devono coincidere con quelle che il MIDI non potrà contenere.

5. **`README.md`**: sezione con numeri misurati (quante note visibili, quante emesse, con quale
   ritaglio), non "funziona meglio".

## F) Dati su disco

```
web_runs/<id>/
  sagome.json            # SagomeVideo serializzato (riquadri per nota per frame + ottava)
  sagome/
    021.mp4 ... 108.mp4  # una clip per nota inquadrata: tutti i frame/secondi del video
  out/notes.json song.mid prima_griglia.jpg
```

## G) Definition of done (verrà eseguita **qui**, sul tuo materiale)

1. `python3 -m py_compile` passa su tutti i file nuovi/modificati.
2. `prima_griglia.jpg` mostra i **riquadri per nota** che cadono sui tasti veri (ispezione visiva):
   il riquadro di C4 deve stare sul Do centrale, non sul tasto accanto.
3. **88 clip** in `out/sagome/`: ognuna copre **tutti** i frame del video (verifica: il conteggio
   dei frame di una clip è uguale a `n_frame` del video). Per le note non inquadrate la clip **non**
   esiste e la nota risulta assente da `visibili`.
4. `out/notes.json` nello schema della pipeline, `.mid` apribile con `pretty_midi`, note in 21–108.
5. **Test negativo A** — su una clip in cui un tasto **non** è premuto, non esce nessun evento per
   quella nota (0, non "uno debole").
6. **Test negativo B** — con un video che inquadra solo una parte della tastiera, **nessuna** nota
   emessa cade fuori dall'insieme `visibili` (confronto esplicito fra le note emesse e i riquadri).
7. **Test ottava** — su un video con una sola ottava visibile, il JSON dichiara `ottava.scelta` con
   la prova, oppure elenca le candidate; mai un'ottava di default non dichiarata.
8. **Cambio video** — lanciando un secondo video, `sagome.json` e `sagome/` del primo vengono
   azzerati e ricalcolati (§D4).
9. **UI** — `node --check` sullo script della pagina, nessun id duplicato né usato e non definito
   (come fa `valida_ui.py`), pagina su `http://127.0.0.1:7862` senza errori JS, e i motori
   `pipeline` e `ppan` ancora funzionanti.
10. Nessun import aggiuntivo oltre `cv2`/`numpy`/`Pillow`/stdlib (+ `ffmpeg` come processo).

## H) Divieti

- Non riscrivere `piano_detector.py`, `app.py`, `video_app.py`, `video_viewer.html`; **PPAN è di
  sola lettura**; `keyboard_grid.py` e `keyboard_tracker.py` si **importano** (estensioni: sì,
  riscritture: no).
- Niente `cv2.legacy`, `TrackerCSRT/KCF/MOSSE`, `mp.solutions`, `mediapipe==1.0.1`,
  `transformers`, `torch.hub`.
- Nessun download a runtime: tutti i file sono locali, con errore chiaro se mancano.
- Nomi di dominio in **italiano** (`Sagoma`, `RiquadroNota`, `SagomeVideo`, `Tasto`,
  `EventoNota`), termini tecnici standard in inglese, docstring in italiano.
- Il server resta senza torch/mediapipe: il lavoro pesante va nel sottoprocesso.
- Niente `...`, niente `# TODO`: se una parte non è fattibile, dillo con l'alternativa concreta.

## I) Decisioni aperte — rispondi scegliendo un'opzione (motiva in 2 righe)

1. **Raffinamento del riquadro.** Il rettangolo di ogni nota è la **proiezione** della griglia
   dentro la regione (semplice, ma eredita gli errori di oggi) oppure la proiezione **raffinata
   sull'immagine** frame per frame (banda dei tasti neri, confini dei bianchi, deriva della
   griglia)? Con il raffinamento: cosa fai sul frame in cui il raffinamento **fallisce**
   (confidenza bassa sul riquadro proiettivo, oppure riquadro assente = nota non emessa)?
2. **Formato delle 88 clip.** *Tutto il frame* o *solo il crop della nota*? E mp4 (pesante: le 88
   clip insieme possono pesare ~88× il video; con `demo_video.mp4`, 12 s, sono nella decina di MB
   per clip) oppure **una cartella di JPEG per nota** (molto più leggera, ma non è "un filmato")?
   Il disco ha ~9,6 GB liberi e il server rifiuta l'avvio sotto 1 GB: dai i numeri della tua scelta.
3. **Cosa significa "premuto"** dentro il riquadro: differenza rispetto ai frame di riposo
   (quale riposo, se all'inizio il tasto è già premuto?), luminosità media, confronto fra frame
   consecutivi? Con quali soglie e con quanta isteresi (`soglia_giu`/`soglia_su` come in
   `note_events.py`)?
4. **Ottava.** Con quale algoritmo la stimi sull'intero video (finestra coerente nel tempo, numero
   di tasti inquadrati, pattern dei neri, spostamento fra i frame)? E cosa scrivi nel JSON quando
   resta ambigua?

## J) Cosa succede al tuo output

Verrà eseguito davvero: `py_compile`, il motore su `demo_video.mp4` e su un video reale con la
tastiera solo in parte inquadrata, i due test negativi di §G5/§G6, il test dell'ottava di §G7,
l'apertura del `.mid` con `pretty_midi`, l'ispezione visiva di `prima_griglia.jpg` per vedere se i
riquadri cadono sui tasti veri, e il controllo che una clip duri quanto tutto il video.
Meglio un modulo in meno e corretto che cinque con `# TODO`.
