"""
Confronta gli eventi nota prima/dopo una correzione (per esempio 88 tasti + centro tastiera)
sul video b2: conta gli eventi, le note uniche, e quante note "dopo" corrispondono a "prima"
trasposte di +12 semitoni (utile per accorgersi di un errore di ottava).

Uso: python3 08_script_confronto_note.py <notes_prima.json> <notes_dopo.json>

Esempio (i due file vengono dalle due corse del motore):
  python3 04_codice_motore_prospettica.py 19_video_caso_b2.mp4 -o /tmp/run_prima
  python3 04_codice_motore_prospettica.py 19_video_caso_b2.mp4 -o /tmp/run_dopo
  python3 08_script_confronto_note.py /tmp/run_prima/notes.json /tmp/run_dopo/notes.json
"""
import collections
import json
import sys


def carica(p):
    d = json.loads(open(p).read())
    ev = d["eventi"] if isinstance(d, dict) and "eventi" in d else d
    out = []
    for e in ev:
        out.append((round(float(e.get("onset", 0.0)), 2), int(e["nota"]),
                    round(float(e.get("durata", 0.0)), 2)))
    return out, d


a, da = carica(sys.argv[1])
b, db = carica(sys.argv[2])
print(f"prima : {len(a)} eventi, note {min(n for _, n, _ in a)}..{max(n for _, n, _ in a)}  "
      f"uniche {len({n for _, n, _ in a})}")
print(f"dopo  : {len(b)} eventi, note {min(n for _, n, _ in b)}..{max(n for _, n, _ in b)}  "
      f"uniche {len({n for _, n, _ in b})}")
print(f"\nprima, note usate: {sorted(collections.Counter(n for _, n, _ in a))}")
print(f"dopo,  note usate: {sorted(collections.Counter(n for _, n, _ in b))}")
# quanti eventi "dopo" sono quelli "prima" trasposti di +12
aa = collections.Counter((t, n) for t, n, _ in a)
bb = collections.Counter((t, n) for t, n, _ in b)
pari = sum(min(c, bb.get((t, n + 12), 0)) for (t, n), c in aa.items())
print(f"\neventi 'dopo' che corrispondono a 'prima' +12 semitoni (stesso istante): {pari}/{len(a)}")
nuovi = [(t, n) for (t, n), c in bb.items() if (t, n - 12) not in aa]
nuovi.sort()
print(f"eventi nuovi (non presenti fra i 'prima' a +12): {len(nuovi)}")
print(f"  note dei nuovi: {sorted({n for _, n in nuovi})}")
print(f"  primi 20: {nuovi[:20]}")
print(f"\nmeta' info altre chiavi prima: {[k for k in da if k != 'eventi'][:8]}")
print(f"meta' info altre chiavi dopo : {[k for k in db if k != 'eventi'][:8]}")
print(f"\nestensione prima: {json.dumps(da.get('estensione', da.get('meta', {})), default=str)[:300]}")
print(f"estensione dopo : {json.dumps(db.get('estensione', db.get('meta', {})), default=str)[:300]}")
