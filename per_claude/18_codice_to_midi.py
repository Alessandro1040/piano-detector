"""
To MIDI — scrittura di .mid (pretty_midi) e notes.json dagli eventi nota.

Stadio 2 / E5 della pipeline video -> MIDI.

Gli onset/offset sono in secondi ASSOLUTI: `bpm` serve solo alla mappa dei tick
del file MIDI e non cambia i tempi reali.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import pretty_midi

_NOMI = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_EPS = 0.001   # distanza minima (s) fra la fine di una nota e il ripartire della stessa


def _nome(n: int) -> str:
    """Notazione scientifica (MIDI 60 = C4), come in keyboard_grid.nome_nota."""
    return f"{_NOMI[n % 12]}{n // 12 - 1}"


def _normalizza(eventi: list) -> list:
    """
    Eventi validi e ordinati: nota 0-127, velocity 1-127, tempi finiti con
    offset > onset e nessuna sovrapposizione fra note con la stessa altezza
    (cosi' note_on / note_off risultano bilanciati e non ambigui).
    Ritorna tuple (nota, onset, offset, velocity, evento_originale).
    """
    puliti = []
    for e in eventi:
        if not (math.isfinite(e.onset) and math.isfinite(e.offset)):
            continue
        n = int(e.nota)
        if not 0 <= n <= 127 or e.onset < 0 or e.offset <= e.onset:
            continue
        puliti.append([n, float(e.onset), float(e.offset),
                       int(min(max(int(e.velocity), 1), 127)), e])
    puliti.sort(key=lambda r: (r[1], r[0]))

    ultimo_per_nota: dict[int, list] = {}
    risultato = []
    for r in puliti:
        prec = ultimo_per_nota.get(r[0])
        if prec is not None and prec[2] > r[1] - _EPS:       # sovrapposta: accorcio la precedente
            prec[2] = r[1] - _EPS
            if prec[2] <= prec[1]:
                risultato.remove(prec)
        ultimo_per_nota[r[0]] = r
        risultato.append(r)
    return [r for r in risultato if r[2] > r[1]]


def salva_midi(eventi: list["EventoNota"], out_path: str,
               bpm: float = 120.0, programma: int = 0) -> str:
    """Scrive un MIDI (1 strumento, `programma` GM 0-127). Ritorna il percorso scritto."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(bpm))
    strumento = pretty_midi.Instrument(program=int(min(max(programma, 0), 127)))
    for nota, on, off, vel, _ in _normalizza(eventi):
        strumento.notes.append(pretty_midi.Note(velocity=vel, pitch=nota, start=on, end=off))
    pm.instruments.append(strumento)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out))
    return str(out)


def riepiloga(eventi: list["EventoNota"], durata_totale: float | None = None) -> dict:
    """
    Conteggi sugli eventi. `durata_totale` (s) e' il denominatore di
    note_al_secondo; se omessa si usa la fine dell'ultima nota.
    """
    ev = [r[4] for r in _normalizza(eventi)]
    if not ev:
        return {"n_eventi": 0, "note_uniche": 0, "note_al_secondo": 0.0,
                "durata_media": 0.0, "nota_piu_frequente": None,
                "intervallo_midi": None}
    conteggio = Counter(e.nota for e in ev)
    top = max(conteggio.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    durata = durata_totale if durata_totale and durata_totale > 0 \
        else max(e.offset for e in ev)
    return {
        "n_eventi": len(ev),
        "note_uniche": len(conteggio),
        "note_al_secondo": round(len(ev) / durata, 3) if durata > 0 else 0.0,
        "durata_media": round(sum(e.offset - e.onset for e in ev) / len(ev), 3),
        "nota_piu_frequente": int(top),
        "intervallo_midi": [int(min(conteggio)), int(max(conteggio))],
    }


def salva_json(eventi: list["EventoNota"], out_path: str, meta: dict | None = None) -> str:
    """
    Scrive notes.json (schema del brief §F). `meta` (opzionale) porta i dati del
    video: video, fps, frame_totali, durata_s, larghezza, altezza,
    estensione_tastiera. Nessun NaN/Infinity, decimali a 3 cifre.
    """
    meta = dict(meta or {})
    fps = float(meta.get("fps") or 0.0)
    norm = _normalizza(eventi)

    def r3(x) -> float:
        x = float(x)
        return round(x, 3) if math.isfinite(x) else 0.0

    lista = []
    for nota, on, off, vel, e in norm:
        f_on = getattr(e, "frame_onset", 0) or (int(round(on * fps)) if fps else 0)
        f_off = getattr(e, "frame_offset", 0) or (int(round(off * fps)) if fps else 0)
        lista.append({
            "nota": nota, "nome": _nome(nota),
            "onset": r3(on), "offset": r3(off), "durata": r3(off - on),
            "velocity": vel, "profondita": r3(e.profondita), "mano": e.mano,
            "frame_onset": int(f_on), "frame_offset": int(f_off),
        })

    durata_s = float(meta.get("durata_s") or 0.0)
    doc = {
        "video": str(meta.get("video", "")),
        "fps": r3(fps),
        "frame_totali": int(meta.get("frame_totali") or 0),
        "durata_s": r3(durata_s),
        "larghezza": int(meta.get("larghezza") or 0),
        "altezza": int(meta.get("altezza") or 0),
        "estensione_tastiera": meta.get("estensione_tastiera") or
                               {"prima_nota": 21, "ultima_nota": 108, "n_tasti": 88},
        "eventi": lista,
        "riepilogo": riepiloga(eventi, durata_s if durata_s > 0 else None),
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, allow_nan=False)
    return str(out)
