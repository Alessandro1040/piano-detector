# La griglia dei tasti è sbagliata — pacchetto di evidenze per Claude

> Progetto: `/Users/alessandrolocurcio/Downloads/piano-detector/`
> Sottoprocesso osservato: `motore_calibrato.py` (stadio "calibrato": un video → una clip per nota).
> Clip di prova: `test_shotC.mp4` (1280×720, 30 fps, ~120 frame).
> Quadrilatero della tastiera usato dall'utente: `152,100  1128,100  1128,320  152,320`.

---

## 1. In una riga

`sagome.py` misura la geometria dei tasti sulla **striscia mediana** (la tastiera
raddrizzata con l'omografia del quadrilatero). La misura della banda dei tasti neri
(`_banda_neri`) e quella della "fascia frontale" (`_misura_striscia`) sono sbagliate:
la griglia risultante **non cade sui tasti**. Su `test_shotC.mp4` trova **7 note**,
su `test_shotA.mp4`/`demo_video.mp4` si ferma con `RuntimeError`.

Il numero atteso su questo video è **~45-50 tasti** (≈30 bianchi + ≈21 neri).

**Non è un problema di ambiente, di pesi YOLO o di formato video: il difetto è nella
misura geometrica dentro `sagome.py`.**

---

## 2. Come funziona il programma (chi fa cosa)

Pipeline "calibrato" (un video → una clip per nota):

```
motore_calibrato.py            orchestrazione (fasi 4-5 del brief)
 ├── sagome.regione_tastiera()  fase 1: quadrilatero della tastiera per ogni frame
 │     ├── piano_detector.py    YOLOv8 (Open Images) -> box "musical keyboard"/"piano"
 │     ├── keyboard_tracker.py  tracciamento del quadrilatero tra i frame
 │     └── (oppure) --quad      4 angoli dati dall'utente: nessun YOLO
 ├── sagome.riquadri_per_frame() (riga 351) fase 2: per ogni nota, il riquadro per frame
 │     ├── righe 375-400        N frame campione -> _grigio_canonico() (warp) -> np.median = striscia
 │     ├── _misura_striscia()   (riga 401) <- QUI IL DIFETTO: banda neri, w, estensione
 │     │     └── _banda_neri()  <- QUI IL DIFETTO: righe [ya,yb] della banda dei neri
 │     ├── _griglia() / _candidate()  posizioni dei tasti: (w, 1° nero, fase, ottava) -> A0..C8
 │     ├── _profilo_neri() / _scarto_frame()  raffinamento del quad per frame
 │     ├── salva_sagome()       scrive `sagome.json` (e scrivi_clip_per_nota le clip)
 │     └── (motore_calibrato.py:95, metodo _disegna)  disegna `prima_griglia.jpg` sul 1° frame
 ├── RilevatoreCalibrato        fase 5: patch 6×10 grigio dentro ogni sagoma,
 │                              mediana temporale = riposo, contrasto locale, isteresi
 ├── note_events.py             EventoNota (on/off, durata)
 └── to_midi.py                 notes.json / sagome.json / song.mid (pretty_midi)

pipeline_web.py + pipeline_studio.html   server locale (porta 7863) che lancia il
                                         sottoprocesso e mostra `prima_griglia.jpg`
```

Moduli di appoggio: `keyboard_grid.py` (modello geometrico dei tasti: `_OFFSET_NERI`,
`MIDI_MIN/MAX`, `e_nero`, `nome_nota`), `hands.py` (mappa delle mani, usata per la clip),
`ppan_bridge.py` (ponte col pianoforte vero, non coinvolto qui).

Tutti i moduli dello stadio 2 (`piano_detector.py`, `keyboard_tracker.py`,
`keyboard_grid.py`, `note_events.py`, `hands.py`, `to_midi.py`) sono **da non
riscrivere**: funzionano e sono già verificati.


---

## 3. Catena esatta della griglia (righe di codice)

`sagome.py`:

| riga | cosa fa | problema |
|---|---|---|
| 183-201 | `_banda_neri(med)`: righe `[ya,yb]` della banda dei neri | **ya/yb sbagliati** (vedi §4) |
| 217-262 | `_misura_striscia(med)`: banda, neri, `w`, estensione `span` | usa `yb` sbagliato → fascia frontale = fondo striscia |
| 230 | `f0 = min(hc-2, yb + int(0.1*(hc-yb)))` | con `yb≈hc` → `f0≈hc-2`: fascia frontale = ultime 2 righe |
| 231-238 | `fr = med[f0:hc].mean(axis=0)` → `xa, xb` = run chiaro più lungo | misura **mani/pantaloni**, non i tasti |
| 240-242 | tiene i neri con `xa <= a and b <= xb`, poi `raise` se < 2 | i neri "veri" cadono fuori dallo span fasullo |
| 249-260 | `w` dalle spaziature dei neri | giusto nei casi "OK" (w≈33) |
| 271-304 | `_griglia(m, classe0, salto_ottava)` | costruisce i tasti dallo span sbagliato |
| 307-328 | `_candidate(...)` | nessun controllo finale di plausibilità |
| 401 | `m = _misura_striscia(med)` dentro `riquadri_per_frame` | punto del traceback |

---

## 4. Evidenze raccolte (log allegati)

* `01_griglia_ATTUALE_sbagliata.jpg` — output del motore: il quadrilatero verde è
  giusto, ma le **verticali non cadono sui tasti**.
* `19_prove_sweep_shotC.log` — spazzata sul quadrilatero YOLO
  (x 152..1128, y 64..376, h=312):

  | y1f | y2f | esito | ya | yb | n run neri | larg_nero |
  |---|---|---|---|---|---|---|
  | 0.00 | 0.75 | OK, `w=33.0`, `span=(0,346)` | 94 | 233 | 26 | 20 |
  | 0.05 | 0.70 | OK, `w=34.06`, `span=(424,767)` | 78 | 202 | 26 | 20 |
  | 0.08 | 0.68 | **KO** "tasti neri insufficienti" | 69 | 186 | 28 | 20 |
  | 0.10 | 0.65 | OK, `w=10.48` (!), `span=(0,369)` | 62 | 171 | 28 | 20 |

  Nel caso 0.00/0.75 (striscia alta 234 px) la banda dei neri dovrebbe essere
  ~righe 14..186 e la fascia frontale ~righe 186..230: il codice restituisce invece
  `ya=94, yb=233` → `f0=232` → la "fascia frontale" diventa **le ultime 2 righe della
  striscia** (mani). Lo span `(0,346)` è la mano sinistra (a x≈370) che interrompe
  il run chiaro.
* `20_prove_sweep_shotA.log` — 6 configurazioni su 8 **falliscono**
  (`meno di 2 tasti neri`), 2 danno `w=40.85` e 7 neri.
* `21_prova_norquad_report.txt` — percorso senza `--quad` (YOLO+tracker):
  `RuntimeError: meno di 2 tasti neri riconoscibili` (sagome.py:242) e su
  `shotB.mp4` `tasti neri insufficienti` (sagome.py:248); 0 clip prodotte.
* `22_prove_misure_righe_frame.txt`, `23_prove_misure_striscia.txt`
  — misure indipendenti, rifatte a mano sul frame mediano (§5).
* `24_script_misure_ref_fit.py` — lo script con cui sono state rifatte.

---

## 5. Misure di riferimento, indipendenti da `sagome.py` (verificate)

Frame mediano di `test_shotC.mp4` (60 frame). Striscia 976×220 ottenuta con il quad
dell'utente.

**a) I tasti neri si misurano bene.** Run scuri larghi nella banda alta (sopra le dita):
14 rilevati (altri ~7 nascosti dalle mani), larghezze **20-25 px**, centri

```
53.5  90.5  127.0  184.0  222.5  280.0  354.0  409.5  448.0  504.5  542.5  577.0  808.0  965.0
```

distanze fra centri consecutivi: `37.0 36.5 57.0 38.5 57.5` → schema
**corto-corto-lungo-corto-lungo** = una ottava = **226.5 px** → **w ≈ 32.4 px**.
Nel frame (riga y=110) lo stesso schema dà ottava **225 px** → **w ≈ 32.14 px**.
Verifica con `_OFFSET_NERI` di `keyboard_grid.py` (C# −0.10, D# +0.10, F# −0.12,
G# 0.00, A# +0.12): i 6 neri consecutivi 207.5 → 432.5 px nel frame tornano
**entro 1 px**; le assegnazioni alternative (C#/D#/G#/A# come primo nero) falliscono.
Quindi i neri sono davvero tasti e **w ≈ 32.1-32.4 px**, non 23.8.

**b) I tasti bianchi.** Separazioni sottili nella fascia frontale (righe 175..205
della striscia), ripetibili su più bande:

```
18.5  51.0  84.0  117.0  149.5  182.0  214.0      -> passo 32.5-33.0
```

Tastiera nel frame da **x≈151 a x≈1135** (984 px) → **≈30 tasti bianchi**
(976 / 32.5 = 30.0 nella striscia). Un fit robusto (massimo di "scurezza" del profilo
frontale su tutte le posizioni di confine) dà **w = 32.50 px, x0 = 19.0 px, 30 tasti**.

**c) Dov'è la banda dei neri.** Nella striscia, la frazione di pixel scuri per riga è
**0.40-0.58 dalle righe 40-140** (neri con le loro ombre) e **0.14-0.20 dalle righe
150 in poi** (bianchi): la transizione neri→bianchi è alla **riga ~150 di 220**, non a
233. Nella striscia alta della spazzata (h=234) è alla riga ~186.

**Conclusione operativa:** su questa clip il risultato giusto è **w ≈ 32.5 px**,
**~30 tasti bianchi** e **~45-50 note**. Il codice arriva a `w=33.0` (giusto!) nel
caso 0.00/0.75, ma con `span=(0,346)` costruisce la griglia su ~10 tasti e ne tiene 7.

---

## 6. Attenzione: due reticoli con passo diverso

Nella striscia raddrizzata il reticolo dei neri ha passo ~32.4 px e quello dei
bianchi ~32.5-32.8 px, con fasi non coincidenti fino a **~10 px** su alcuni tasti:
i neri sono fisicamente sopra il piano dei bianchi e la tastiera è vista in
prospettiva. Su questo video **nessuna coppia (w, fase) unica** soddisfa insieme tutti
i neri e tutte le separazioni bianche. Conseguenze pratiche:

* `w` va stimato **nella stessa banda in cui viene usato**: se i bianchi sono
  analizzati nella fascia frontale, `w` va misurato lì (dalle separazioni), non nella
  banda dei neri (~1% più stretta);
* i neri vanno posizionati con il modello (`_OFFSET_NERI`) a partire dai confini dei
  bianchi, non dalle posizioni dei loro pixel (spostate dalla parallasse);
* la fase va verificata **su tutto lo span**: 1 px di errore di passo su 30 tasti
  vale 30 px, quasi un tasto di deriva ai bordi.

---

## 7. Cosa serve dalla correzione (requisiti)

1. `_banda_neri` deve restituire la banda dei neri **vera**: `ya` = dove iniziano i
   neri, `yb` = dove **finiscono** (riga ~150/220 nel quad utente, ~186/234 nella
   striscia della spazzata), **non** `hc-1`. Discriminatore misurato e robusto: la
   **frazione di pixel scuri per riga** (~0.5 nella banda dei neri, ~0.15 nei bianchi)
   oppure la **larghezza dei run** (~0.6w per i neri, 2-4 px per le separazioni).
2. La "fascia frontale" (`f0`) deve cadere fra il fondo dei neri e la fine dei bianchi,
   **escludendo le mani**: se lì la frazione di scuri sale o il run chiaro si interrompe
   a metà tastiera, la misura va rifiutata con un errore esplicito (meglio un KO che
   una griglia da 7 note).
3. `w` e fase vanno stimati **nella fascia frontale** (o con un fit congiunto sui due
   piani) e verificati su tutto lo span.
4. **Validazione finale** (oggi assente): neri distinti ≥ ~14, `(xb-xa)/w` intero ±0.5,
   note totali ≥ ~25 quando la tastiera è tutta inquadrata; altrimenti `RuntimeError`
   con i numeri misurati, non una griglia silenziosamente sbagliata.
5. Nessuna nuova dipendenza (restano `cv2`, `numpy`, `pretty_midi`) e nessuna
   riscrittura dei moduli già chiusi (§2).

---

## 8. Come riprodurre e mappa del pacchetto

```bash
cd /Users/alessandrolocurcio/Downloads/piano-detector

# caso che l'utente vede sul sito (7 note, prima_griglia.jpg sbagliata)
python3 motore_calibrato.py test_shotC.mp4 -o /tmp/out_cal_C2 \
        --quad "152,100 1128,100 1128,320 152,320"

# caso senza --quad (fallisce in fase 2)
python3 motore_calibrato.py demo_video.mp4 -o /tmp/real_norquad

# misure di riferimento rifatte a mano (nessuna dipendenza da sagome.py)
python3 24_script_misure_ref_fit.py
```

| file | contenuto |
|---|---|
| `01_griglia_ATTUALE_sbagliata.jpg` | la griglia **sbagliata** prodotta ora dal motore |
| `02_griglia_CORRETTA_riferimento_misurato.png` | la griglia **giusta** misurata sui bianchi (w=32.50, x0=19, 30 tasti) |
| `03_striscia_mediana_senza_griglia.png` | la stessa striscia senza griglia |
| `04_frame_con_righello_pixel.jpg` | frame intero con righello in pixel (coordinate vere) |
| `05_frame_shotC.jpg`, `06_..._3s`, `07_..._9s` | frame dei tre shot del video demo |
| `08_zoom6x_verifica_fascia_frontale.png` | zoom 6× sulla fascia frontale (verifica a occhio) |
| `09_video_test_shotC.mp4`, `10_video_test_shotA.mp4` | i due video di prova |
| `11..18_codice_*.py` | moduli coinvolti (motore, sagome, grid, tracker, detector, hands, note_events, to_midi) |
| `19`, `20_prove_sweep_*.log` | spazzate del quadrilatero con esiti e misure |
| `21_prova_norquad_report.txt` | percorso YOLO+tracker senza `--quad` |
| `22`, `23_prove_misure_*.txt` | misure di riferimento rifatte a mano |
| `24_script_misure_ref_fit.py` | script delle misure indipendenti |
| `25_codice_test_sagome.py` | test esistente sui moduli dello stadio 2 |

Restano nel progetto (non allegati qui, già consegnati nel BRIEF n.2):
`BRIEF_CLAUDE_2_SAGOME.md`, `README.md`, `pipeline_web.py`, `pipeline_studio.html`.

