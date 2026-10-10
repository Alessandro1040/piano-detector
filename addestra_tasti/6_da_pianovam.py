#!/usr/bin/env python3
"""Un pezzo pronto per il corso di addestramento, preso da una registrazione PianoVAM.

PianoVAM (https://huggingface.co/datasets/PianoVAM/PianoVAM_v1) ha, per ogni registrazione,
`Video/<record_time>.mp4` + `MIDI/<record_time>.mid` (il MIDI VERO del pianoforte, gia' allineato
al video) e in `metadata.json` i 4 angoli della tastiera (`Point_LT`, `Point_RT`, `Point_RB`,
`Point_LB`).

Perche' non si puo' dare il video intero al corso: in queste riprese la tastiera e' lontana e i
tasti larghi ~19 px, e `motore_prospettica.py` si aggancia alla fascia sbagliata (passo di ~2
tasti, griglia sopra la tastiera) senza accorgersene. Ritagliando il fotogramma sulla tastiera
invece trova tutti e 88 i tasti, coi nomi giusti (A0..C8).

Cosa fa questo script, in un colpo:
  1. legge i 4 angoli della tastiera da `metadata.json`;
  2. taglia dal video la finestra [inizio, inizio+durata] e la ritaglia su quegli angoli (+margine),
     riportandola a --fps (il dataset e' a 60 fps: 30 basta e dimezza il lavoro);
  3. taglia il MIDI dello stesso intervallo (stesso tempo 0): i due file restano allineati;
  4. scrive `<out>/<nome>.mp4` e `<nome>.mid`, da trascinare nel sito come coppia.

Esempio:
    python3 6_da_pianovam.py --dataset ~/PianoVAM_v1.2 --rec 2024-02-15_20-07-54 \
        --inizio 30 --durata 120 --nome brano2 --out ~/pianovam_pezzi
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import mido


def angoli_tastiera(dataset: Path, rec: str, margine: int) -> tuple[int, int, int, int]:
    """Rettangolo (x, y, larghezza, altezza) che contiene i 4 angoli della tastiera."""
    meta = json.load(open(dataset / "metadata.json"))
    voce = next((v for v in meta.values() if v.get("record_time") == rec), None)
    if voce is None:
        sys.exit(f"'{rec}' non e' in {dataset / 'metadata.json'}")
    punti = []
    for chiave in ("Point_LT", "Point_RT", "Point_RB", "Point_LB"):
        x, y = (float(t) for t in str(voce[chiave]).split(","))
        punti.append((x, y))
    x1 = int(min(x for x, _ in punti)) - margine
    x2 = int(max(x for x, _ in punti)) + margine
    y1 = int(min(y for _, y in punti)) - margine
    y2 = int(max(y for _, y in punti)) + margine
    print(f"[angoli] tastiera {x1}..{x2} x {y1}..{y2} (margine {margine} px)")
    return x1, y1, x2 - x1, y2 - y1


def taglia_midi(src: Path, dst: Path, inizio: float, durata: float) -> None:
    """MIDI di [inizio, inizio+durata] secondi, riscritto col tempo 0 = inizio."""
    mf = mido.MidiFile(str(src))
    tempi = [m for tr in mf.tracks for m in tr if m.type == "set_tempo"]
    tempo = tempi[0].tempo if tempi else 500000          # microsecondi per battito
    if len({t.tempo for t in tempi}) > 1:
        print(f"[!] {src.name}: piu' di un tempo nel file, il taglio usa {tempo} us/battito")
    tick_s = mf.ticks_per_beat * 1e6 / tempo             # tick per secondo
    t0, t1 = inizio * tick_s, (inizio + durata) * tick_s

    ev = []
    for tr in mf.tracks:                                 # tempi assoluti, in tick
        t = 0
        for m in tr:
            t += m.time
            if not m.is_meta:
                ev.append((t, m))
    ev.sort(key=lambda x: x[0])

    out = mido.MidiFile(type=1, ticks_per_beat=mf.ticks_per_beat)
    capo = mido.MidiTrack()
    out.tracks.append(capo)
    capo.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    capo.append(mido.MetaMessage("end_of_track", time=0))
    tr = mido.MidiTrack()
    out.tracks.append(tr)
    tr.append(mido.MetaMessage("track_name", name="taglio PianoVAM", time=0))
    ultimo, aperte, prima = 0, set(), 0
    for t, m in ev:
        if t >= t1:
            break
        if t < t0:
            if m.type == "note_on" and m.velocity > 0:
                prima += 1                               # iniziata prima del taglio: si butta
            continue
        if m.type == "note_on" and m.velocity > 0:
            aperte.add(m.note)
        elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
            aperte.discard(m.note)
        nuovo = int(round(t - t0))
        tr.append(m.copy(time=nuovo - ultimo))
        ultimo = nuovo
    for nota in sorted(aperte):                          # note ancora giu' al taglio: le chiudo
        coda = int(round(t1 - t0))
        tr.append(mido.Message("note_off", note=nota, velocity=0, time=coda - ultimo))
        ultimo = coda
    tr.append(mido.MetaMessage("end_of_track", time=0))
    out.save(str(dst))
    print(f"[midi] {len(ev)} eventi, {prima} iniziati prima del taglio (buttati), "
          f"{len(aperte)} chiusi sul taglio -> {dst.name}")


def main() -> None:
    p = argparse.ArgumentParser(description="Da una registrazione PianoVAM a un pezzo del corso.")
    p.add_argument("--dataset", default="PianoVAM_v1.2", help="cartella del dataset scaricato")
    p.add_argument("--rec", required=True, help="record_time della registrazione (nome dei file)")
    p.add_argument("--out", default=".", help="dove scrivere i due file")
    p.add_argument("--nome", default=None, help="nome del pezzo (default: record_time)")
    p.add_argument("--inizio", type=float, default=0.0, help="da che secondo tagliare")
    p.add_argument("--durata", type=float, default=120.0, help="quanti secondi (default 120)")
    p.add_argument("--fps", type=float, default=30.0, help="fps del pezzo (default 30)")
    p.add_argument("--margine", type=int, default=10, help="px di margine attorno alla tastiera")
    a = p.parse_args()

    dataset = Path(a.dataset).expanduser()
    video, midi = dataset / "Video" / f"{a.rec}.mp4", dataset / "MIDI" / f"{a.rec}.mid"
    for f in (video, midi):
        if not f.is_file():
            sys.exit(f"manca {f}: scaricalo da HuggingFace (vedi docstring)")
    nome = a.nome or a.rec
    uscita = Path(a.out).expanduser()
    uscita.mkdir(parents=True, exist_ok=True)
    x, y, w, h = angoli_tastiera(dataset, a.rec, a.margine)

    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(a.inizio), "-t", str(a.durata),
           "-i", str(video), "-vf", f"crop={w}:{h}:{x}:{y},fps={a.fps:g}", "-c:v", "libx264",
           "-crf", "20", "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart", str(uscita / f"{nome}.mp4")]
    print("ffmpeg:", " ".join(cmd))
    if subprocess.run(cmd).returncode != 0:
        sys.exit("ffmpeg ha fallito")
    taglia_midi(midi, uscita / f"{nome}.mid", a.inizio, a.durata)
    print(f"pronto: {uscita / (nome + '.mp4')} + {uscita / (nome + '.mid')} "
          f"(trascinali nel sito come coppia)")


if __name__ == "__main__":
    main()
