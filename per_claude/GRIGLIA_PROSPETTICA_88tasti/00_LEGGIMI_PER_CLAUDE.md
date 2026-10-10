# Griglia prospettica: tastiera intera (88 tasti) e ottava giusta — pacchetto per Claude

> Progetto: `/Users/alessandrolocurcio/Downloads/piano-detector/`
> Modulo corretto: **`griglia_prospettica.py`** (la griglia dei tasti del percorso "prospettica",
> ripresa a mano libera: per ogni frame un'omografia `canonico -> immagine`).
> Orchestratore: `motore_prospettica.py` (un video → `griglia.json` + `notes.json` + `song.mid` +
> video di controllo `griglia.mp4` + `prima_griglia.jpg`).
> Caso di prova: `video5906842636420915152.mp4` (**848×464, 29.87 fps, 224 frame**) — pianoforte
> intero inquadrato ma piccolo (neri larghi 6-7 px, passo bianco reale ~10.5 px).
> Data del lavoro: 3 ottobre 2026 (sera).

Questo pacchetto è **autonomo** e contiene **solo** i file di questo giro di lavoro (le versioni
nuove + le prove che le sostengono). Il pacchetto precedente — il bug di misura in `sagome.py`,
file `00_..25_` — è rimasto dov'è, nella cartella superiore `per_claude/`, e non è stato toccato.

---

## 1. In tre righe

Sul video di prova il percorso "prospettica" inquadrava **la sola metà destra** della tastiera e
leggeva **tutte le note un'ottava sotto**. Sono **due difetti indipendenti**, entrambi in
`griglia_prospettica.py`, che si sommavano:

1. **copertura** — il lessico del modello era `NOTA_MIN, NOTA_MAX = 36, 96` (C2..C7, 61 tasti):
   i tasti fuori finestra *non esistevano*, quindi la metà sinistra della tastiera non aveva
   celle e le pressioni lì non si vedevano;
2. **ottava** — in `_H_iniziale_classico` il gruppo di due neri da ancorare veniva scelto come
   "il più vicino al **centro del frame**" (`w/2`): con l'inquadratura decentrata quel gruppo è
   il C#3-D#3 e non il C#4-D#4, quindi **tutte** le note uscivano 12 semitoni basse.

Dopo i due fix (nessun flag nuovo, nessuna modifica al modello geometrico):

| | ORIGINALE | dopo §5.2 (solo la larghezza dei neri) | **dopo §5.3 (questo giro)** |
|---|---|---|---|
| `prima_griglia.jpg` dice | griglia storta, 48..66 | `61 note inquadrate (36..96)` | **`88 note inquadrate (21..108)`** |
| inlier dell'affinamento (frame 0) | 0 | 162 | **228** |
| celle nella zona vera dei bianchi | — | 36/36 | **52/52** |
| estensione in x delle celle | — | 301..652 (metà destra) | **125..650 (tutta la tastiera)** |
| primo nero del modello | C#2 (x 308) | C#2 (x 308) | **A#0 (x 140)** |
| note inquadrate / emesse | 19 / 10 | 61 / 14 | **88 / 24** |
| intervallo MIDI emesso | 48..66 | 39..71 | **21..83** |
| eventi nota | 15 | 33 | **47** |

---

## 2. Misure che sostengono la diagnosi (ground truth)

Tutte rifatte a mano sui pixel, senza fidarsi del motore (log in questa cartella).

Nota sui log: `10_`, `11_` e `12_` sono le misure di *diagnosi*, fatte quando il modulo aveva
ancora l'ancora al centro del frame e il lessico 36..96 — la colonna "modello" che vi si legge è
quella vecchia, mentre le colonne misurate sui pixel restano valide. In fondo al paragrafo ci
sono le stesse misure rifatte **oggi** con il modulo corretto.

* `12_prova_neri_reali_frame0.log` — riga dei neri `y=188`: **35-36 blob alti** (15-17 righe di
  altezza) a x **140..631**, con i tre blob anomali fuori tastiera a x 667.5 (largh. 37),
  792.5 e 836.2 (largh. 23-28) che vanno **scartati**: sono il corpo del pianoforte e il fondo;
* `11_prova_copertura_modello.log` — frame 0: il modello (25 neri, x 308..633) lascia **12 neri
  reali fuori a sinistra** (x 106..290): è esattamente la metà sinistra mancante; il passo bianco
  delle celle è 10.00 px, quindi **~29 tasti in più** non coperti;
* `10_prova_identita_ottava.log` — riga neri `y=183`: passo bianco misurato **11.50 px**, il
  gruppo da 2 neri più vicino al centro del frame comincia a x 379.5; il modello mette
  C#4 a x 445.8 (**+66.3 px = +5.76 bianchi**, cioè sbagliato) mentre **C#3 dista +0.7 px
  (0.06 bianchi)**: quel gruppo *è* il C#3-D#3. Ecco perché l'ottava usciva −12 semitoni.
  Sul video compaiono **6 gruppi da 2 neri e 6 da 3** (una tastiera intera ne ha 7 e 7): il
  bordo sinistro della tastiera non era agganciato. Con la correzione (centro *della tastiera*)
  il log del motore stampa `prima griglia: 88 tasti inquadrati, note 21..108` e
  `[griglia] estensione 21..108 ... scarto +0 ottave`.

**Rifatte oggi con il modulo corretto** (`01_..NUOVO.py`, comandi di §5): `NOTA_MIN..MAX = 21..108`,
**36 neri nel modello** (note 22..106) a **x 140..631**, inlier **228**, **88 celle in frame a
x 125..650**, cella più a sinistra **A0 (21) a x 125**, più a destra C8 (108) a x 650; sulla riga
dei neri restano fuori dal modello solo blob **non-tastiera** (x 106 a sinistra; 633, 668, 794,
836 a destra = corpo/fondo e coda dell'ultimo nero). La stessa misura sulla versione *prima*
(`02_..PRIMA.py`): lessico 36..96, 25 neri nel modello, inlier **0**, 19 celle a x 41..834
(griglia a caso). Con il modulo corretto l'identità dell'ottava si chiude: il gruppo da 2 neri a
x 379.5 viene letto **C#4 con uno scarto di 0.5 px (0.05 bianchi)**, mentre le ipotesi vicine
distano 67 px (C#3, −5.85 bianchi) e 131 px (C#5): solo un numero intero di ottave può spiegare
un accordo sotto il pixel.


Il testo completo, con le tabelle prima/dopo e i ragionamenti, sta in
**`20_documentazione_PER_DEEPSEEK_AGG.md`**, sezioni **§5.2** e **§5.3** (è il documento di lavoro
del progetto, aggiornato in questo giro; `§7 Codice essenziale` contiene anche il sorgente di
tutti i moduli di contorno).

---

## 3. Le correzioni (cosa è cambiato, riga per riga)

Il diff completo è in **`03_diff_griglia_88tasti.patch`** (`02_..PRIMA.py` → `01_..NUOVO.py`,
4 gruppi di righe; i primi due sono il giro §5.2, gli altri due questo giro).

**(a) copertura — lessico del modello a 88 tasti** (§5.3)

```python
-NOTA_MIN, NOTA_MAX = 36, 96
+# Estensione del modello: gli 88 tasti di un pianoforte (A0..C8), come gia' fanno
+# sagome.py (`nota_min=21, nota_max=108`) e to_midi.py. Con 36..96 (C2..C7, 61 tasti) i
+# tasti fuori finestra NON esistono nel lessico: in un video che inquadra la tastiera
+# intera il bordo sinistro restava senza griglia e le pressioni li' non si vedevano.
+NOTA_MIN, NOTA_MAX = 21, 108
```

Effetto collaterale voluto: il modello torna **coerente col resto del progetto**
(`sagome.py` usa già 21..108, `to_midi.py` pure), quindi `nota_min/nota_max` non sono più
due mondi diversi a seconda del percorso.

**(b) ottava — ancoraggio al centro *della tastiera*, non del frame** (§5.3)

In `_H_iniziale_classico`, subito dopo la stima del passo (`piccolo`, `wpx`) si ricava il centro
della tastiera dai neri **veri**, tagliando i blob fuori tastiera (un buco ≥ 3.6 passi non è un
tasto, è il corpo del pianoforte / il fondo):

```python
reg = [float(x) for x in ra]
c0 = int(np.argmin(np.abs(np.asarray(reg) - np.median(reg))))
im, jm = c0, c0
while im > 0 and reg[im] - reg[im - 1] <= 3.6 * piccolo:
    im -= 1
while jm + 1 < len(reg) and reg[jm + 1] - reg[jm] <= 3.6 * piccolo:
    jm += 1
xc_tast = 0.5 * (reg[im] + reg[jm])
```

e la scelta del gruppo da due neri passa da `w/2` a `xc_tast`:

```python
-    k2 = min(due, key=lambda k: abs(np.mean([ra[i] for i in gruppi[k]]) - w / 2))
+    k2 = min(due, key=lambda k: abs(np.mean([ra[i] for i in gruppi[k]]) - xc_tast))
```

Quando la tastiera è centrata sul frame i due riferimenti coincidono: è per questo che i video
verticale / `test_shotA` / `demo_video` danno risultati **identici** al bit (vedi §4).

**(c) e (d)** — già del giro §5.2, restano perché il nuovo codice conta su di essi:
`lo = max(2.5, 0.004*w)` (i neri lontani sono 6-7 px, con il vecchio minimo `0.015*w = 12.7 px`
non ne passava nessuno) e la guardia `note[i] = ordine[j] if 0 <= j < len(ordine) else None`
(+ `continue` in `src/dst`) contro l'`IndexError` con più run dei neri del modello.

---

## 4. Verifica (numeri grezzi nei log di questa cartella)

**Ancoraggio al frame 0, stessa misura per ogni versione** (`09_prova_ancora_regressione.log`,
righe `orig` / `range21_108` / `PROGETTO`):

| video | orig (36..96) | §5.2 | **progetto ora (21..108)** |
|---|---|---|---|
| `19_video_caso_b2.mp4` (lontana) | passo 76.4 / **0 inlier** / 0 celle su 36 | 9.3 / 162 / 36 su 36 | **9.6 / 228 / 52 su 52** |
| video verticale | 51.9 / 76 | 51.9 / 76 | **51.9 / 76 (identico)** |
| `test_shotA.mp4` | 40.4 / 118 | 40.3 / 137 | **40.3 / 137 (identico)** |
| `test_shotC.mp4` | 32.2 / 70 | 32.2 / 69 | **32.2 / 81 (meglio)** |
| `demo_video.mp4` | 40.4 / 118 | 40.3 / 137 | **40.3 / 137 (identico)** |

**Corsa completa su b2** (`13_prova_corsa_completa_88.log`): `88 tasti inquadrati, note 21..108`,
inlier 228 → 328 su tutti i frame campionati, `224 frame / note inquadrate 88 / emesse 24 /
47 eventi / 4.9 s`. Esito grezzo: `21_esito_note.json` (note emesse) e `22_esito_song.mid`.

**Ottava**: delle 14 note emesse prima, **12 ricompaiono identiche trasposte di +12 semitoni**
(18 eventi allo stesso istante); le note nuove sono la mano sinistra che prima non esisteva
(F#2, A0, B1, A1, G1, A#3, C2+C#2, A#1, C2, D2, B1).

**A occhio** — tre versioni dello stesso `prima_griglia.jpg` (frame 0, prodotto dal motore):

| file | cosa si vede |
|---|---|
| `15_immagine_ORIGINALE_17note_sbagliata.jpg` | orig: colonne larghe su tutto il frame, che non cadono sui tasti (intestazione `48..66`) |
| `14_immagine_PRIMA_61tasti_meta_tastiera.jpg` | dopo §5.2: reticolo giusto, ma **solo dalla metà destra** (`61 note inquadrate 36..96`) |
| `16_immagine_DOPO_88tasti_tutta_tastiera.jpg` | **dopo §5.3: griglia su tutta la tastiera, etichette che partono da A0** (`88 note inquadrate 21..108`) |

Il video `18_video_DOPO_controllo_griglia.mp4` è il controllo del motore: la griglia segue la
tastiera su tutti i 224 frame, con i tasti premuti evidenziati.

---

## 5. Come ricontrollare (comandi)

```bash
D=/Users/alessandrolocurcio/Downloads/piano-detector/per_claude/GRIGLIA_PROSPETTICA_88tasti
P=/Users/alessandrolocurcio/Downloads/piano-detector
export PIANO_DETECTOR=$P          # gli script lo leggono da qui (default: il percorso sopra)

# 1) ancoraggio: deve dire NOTA_MIN..MAX = 21..108, inlier ~228, 88 celle, x 125..650, A0 a sinistra
python3 "$D/05_script_prova_ancora.py" "$D/01_codice_griglia_prospettica_NUOVO.py" \
        "$D/19_video_caso_b2.mp4"
#    stessa misura sulla versione "prima", per il confronto
python3 "$D/05_script_prova_ancora.py" "$D/02_codice_griglia_prospettica_PRIMA.py" \
        "$D/19_video_caso_b2.mp4"

# 2) ottava: il gruppo da 2 neri a x 379.5 viene letto C#4 con 0.5 px di scarto (C#3 dista 67 px)
python3 "$D/07_script_identita_ottava.py" "$D/19_video_caso_b2.mp4"

# 3) corsa completa + copertura del modello sui neri reali
cd "$P"
python3 motore_prospettica.py "$D/19_video_caso_b2.mp4" -o /tmp/run_b2
python3 "$D/06_script_copertura_modello.py" /tmp/run_b2 "$D/19_video_caso_b2.mp4"
#    atteso: modello 36 neri x 140..631; fuori dal modello restano solo blob non-tastiera
#    (x 106 a sinistra; 633, 668, 794, 836 a destra = corpo/fondo e coda dell'ultimo nero)
#    e guardare /tmp/run_b2/prima_griglia.jpg: le etichette devono partire da A0

# 4) confronto eventi prima/dopo una correzione
python3 "$D/08_script_confronto_note.py" /tmp/run_prima/notes.json /tmp/run_b2/notes.json
```

Nota: `06_` e `07_` importano `griglia_prospettica` **dal progetto** (`$PIANO_DETECTOR`), mentre
`05_` carica il modulo passato come argomento: serve proprio a misurare versioni diverse.

---

## 6. Cosa resta aperto (non blocca il fix)

1. **L'ottava è ancora un'euristica**: "il gruppo di due neri più vicino al **centro della
   tastiera** è C#4-D#4". È corretta quando la tastiera intera è inquadrata e il centro è il suo
   centro; quando la vista è parziale (video verticale) degenera nel comportamento di prima
   (centro del frame), che lì andava bene. Il criterio robusto è quello del progetto fratello
   `pianovam-video2midi/src/detect.py`: far combaciare i **bordi** del modello (A0, C8) con i
   bordi verticali della tastiera nell'immagine — il pattern dei neri si ripete ogni 12 tasti, i
   bordi no. Da fare se arrivano video con tastiera **parziale e decentrata** insieme.
2. **Tastiere più corte di 88 tasti**: con il modello a 21..108, su un synth a 61 tasti le celle
   in più **cadrebbero fuori dalla tastiera e verrebbero comunque campionate**. Nei 5 video di
   prova non succede (tastiera intera o parziale centrata), quindi va misurato su un video
   apposito prima di considerarla risolta.
3. La **scala dell'ancora al frame 0** resta compressa (`piccolo/1.15`, §5.2): invariata,
   funziona, ma è un numero tarato a mano.
4. Se `sagome.py` / `to_midi.py` / i pesi YOLO cambiano, gli artefatti derivati vanno rigenerati:
   il modello 21..108 non cambia da solo `sagome.json`, ma i due percorsi ora concordano.

---

## 7. Mappa di questa cartella

| file | cosa è |
|---|---|
| `00_LEGGIMI_PER_CLAUDE.md` | questo documento |
| `01_codice_griglia_prospettica_NUOVO.py` | **la versione corretta** (copia di `$P/griglia_prospettica.py`) |
| `02_codice_griglia_prospettica_PRIMA.py` | la versione *prima* dei due giri di fix (per il diff) |
| `03_diff_griglia_88tasti.patch` | `diff -u` fra `02_` e `01_`: 4 gruppi (2 del giro §5.2, 2 di questo) |
| `04_codice_motore_prospettica.py` | l'orchestratore usato nelle prove (non modificato in questo giro: serve per eseguire) |
| `05_script_prova_ancora.py` | inlier / tasti inquadrati / estensione in x con **una qualsiasi** versione del modulo |
| `06_script_copertura_modello.py` | quanti neri **reali** restano fuori dal modello (`griglia.json` + video) |
| `07_script_identita_ottava.py` | ricostruisce il pattern 2/3 neri e dice che nota è davvero il gruppo scelto |
| `08_script_confronto_note.py` | confronta due `notes.json` (eventi, note uniche, trasposizione +12) |
| `09_prova_ancora_regressione.log` | la matrice di regressione (5 video × 7 versioni del modulo) |
| `10_prova_identita_ottava.log` | l'errore di ottava misurato (il gruppo "C#4" che è un C#3) |
| `11_prova_copertura_modello.log` | i 12 neri reali fuori a sinistra del modello |
| `12_prova_neri_reali_frame0.log` | i blob alti veri della tastiera, con i 3 blob fuori tastiera |
| `13_prova_corsa_completa_88.log` | la corsa completa del motore sul caso b2 |
| `14_immagine_PRIMA_61tasti_meta_tastiera.jpg` | `prima_griglia.jpg` dopo §5.2: metà destra |
| `15_immagine_ORIGINALE_17note_sbagliata.jpg` | `prima_griglia.jpg` originale: griglia storta (48..66) |
| `16_immagine_DOPO_88tasti_tutta_tastiera.jpg` | `prima_griglia.jpg` **dopo §5.3**: 88 note, da A0 |
| `17_frame0_senza_griglia.jpg` | il frame 0 pulito, su cui sono state fatte le misure |
| `18_video_DOPO_controllo_griglia.mp4` | video di controllo del motore dopo il fix (224 frame) |
| `19_video_caso_b2.mp4` | il video del caso (848×464, 224 frame) |
| `20_documentazione_PER_DEEPSEEK_AGG.md` | documento di lavoro aggiornato (**§5.2, §5.3** nuove; §7 = sorgenti dei moduli) |
| `21_esito_note.json`, `22_esito_song.mid` | esito grezzo della corsa corretta (24 note, MIDI 21..83) |

**Restano nel progetto** — non modificati in questo giro, necessari solo per eseguire, con il
sorgente completo in `§7` di `20_documentazione_PER_DEEPSEEK_AGG.md`: `motore_calibrato.py`,
`sagome.py`, `to_midi.py`, `keyboard_grid.py`, `note_events.py`, `piano_detector.py`,
`keyboard_tracker.py`, `hands.py`, `weights/`.

---

## 8. In una riga, per chi legge solo questo

`griglia_prospettica.py`: `NOTA_MIN, NOTA_MAX` da `36, 96` a `21, 108` (88 tasti) e in
`_H_iniziale_classico` il gruppo di due neri da ancorare si sceglie rispetto a `xc_tast`
(centro dello span regolare dei neri = centro della **tastiera**) e non più a `w/2` (centro del
**frame**). Sul caso di prova: `88 note inquadrate (21..108)` al posto di `61 (36..96)`,
47 eventi al posto di 33, note dell'ottava giusta.




