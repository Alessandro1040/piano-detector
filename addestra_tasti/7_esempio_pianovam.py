#!/usr/bin/env python3
"""Elenco e ritaglio di un esempio dal dataset PianoVAM, preso direttamente dal remoto.

PERCHE' ESISTE
Il corso vuole pezzi brevi (15-60 s) col video e col MIDI VERO. PianoVAM ha 107 registrazioni
con video + MIDI, ma i video pesano 220-700 MB l'uno: scaricarli interi per tenerne 60 secondi
non ha senso, e il disco è quasi pieno. HuggingFace serve i file a pezzi (richieste parziali) e
ffmpeg sa leggere un URL: qui si prende SOLO il pezzo richiesto (~10 MB) più il MIDI (pochi KB).

Il taglio è in ri-codifica, non `-c copy`: con la copia il video comincia alla chiave precedente
all'istante chiesto, quindi il pezzo partirebbe qualche decimo di secondo prima del MIDI e i
tasti rossi non starebbero sotto le dita. La ri-codifica fa partire il video esattamente da lì.

L'elenco viene dal `metadata.json` del dataset (compositore, brano, durata, chi suona) ed è
numerato in ordine di data: "4" = il quarto video. Lo tiene in cache in `~/.cache` per non
richiederlo ogni volta (`--aggiorna` per rifarlo).

Esempi
    python3 7_esempio_pianovam.py --elenco                     # la lista numerata
    python3 7_esempio_pianovam.py --elenco --json              # la stessa lista in JSON
    python3 7_esempio_pianovam.py --numero 4 --durata 60 --out ~/esempi
    python3 7_esempio_pianovam.py --caso --durata 60 --out ~/esempi     # una a caso
"""
import argparse
import json
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DATASET = "PianoVAM/PianoVAM_v1"
BASE_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/main"
CACHE = Path.home() / ".cache" / "pianovam_metadata.json"
SCADENZA_CACHE = 7 * 24 * 3600                     # il dataset non cambia: una settimana basta


def scarica(url: str, destinazione: Path) -> None:
    """Scarica un URL su file (il metadata e i MIDI sono piccoli)."""
    richiesta = urllib.request.Request(url, headers={"User-Agent": "piano-detector/0-prepara"})
    with urllib.request.urlopen(richiesta, timeout=120) as r, open(destinazione, "wb") as f:
        while True:
            blocco = r.read(1 << 16)
            if not blocco:
                break
            f.write(blocco)


def secondi(durata: str) -> float:
    """'0 days 00:12:25.493000' -> 745.5 secondi (a volte c'e' un '.000000' in coda: si ignora)."""
    m = re.search(r"(\d+)\s+days?\s+(\d+):(\d+):(\d+(?:\.\d+)?)", str(durata) or "")
    if not m:
        return 0.0
    g, h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4))
    return g * 86400 + h * 3600 + mi * 60 + s


def elenco(aggiorna: bool = False) -> list[dict]:
    """Le registrazioni del dataset, numerate in ordine di data: [{n, rec, compositore, ...}]."""
    if aggiorna or not CACHE.is_file() or time.time() - CACHE.stat().st_mtime > SCADENZA_CACHE:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        try:
            scarica(f"{BASE_URL}/metadata.json", CACHE)
            print(f"[elenco] scaricato {CACHE} dal dataset", file=sys.stderr)
        except (urllib.error.URLError, OSError) as e:
            if not CACHE.is_file():
                sys.exit(f"[!] non riesco a leggere il metadata del dataset ({e}). Serve internet "
                         f"la prima volta; poi resta in cache in {CACHE}")
            print(f"[!] niente internet per aggiornare l'elenco, uso la copia in cache ({e})",
                  file=sys.stderr)
    try:
        dati = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"[!] {CACHE} illeggibile ({e}): riprova con --aggiorna")
    voci = []
    for voce in dati.values():
        rec = voce.get("record_time")
        if rec:
            voci.append({"rec": rec, "compositore": voce.get("composer") or "",
                         "brano": voce.get("piece") or "", "durata": round(secondi(voce.get("duration")), 1),
                         "split": voce.get("split") or "", "suona": voce.get("P1_name") or ""})
    voci.sort(key=lambda v: v["rec"])
    for i, v in enumerate(voci, 1):
        v["n"] = i
    return voci



def taglia(rec: str, inizio: float, durata: float, out: Path, fps: float, ffmpeg: str = "ffmpeg"):
    """Scrive `<out>/<rec>.mp4` (solo il pezzo, ri-codificato) e `<out>/<rec>.mid` (il MIDI vero)."""
    out.mkdir(parents=True, exist_ok=True)
    video, midi = out / f"{rec}.mp4", out / f"{rec}.mid"
    cmd = [ffmpeg, "-y", "-v", "error"]
    if inizio > 0:
        cmd += ["-ss", f"{inizio:.3f}"]
    if durata > 0:
        cmd += ["-t", f"{durata:.3f}"]
    cmd += ["-i", f"{BASE_URL}/Video/{rec}.mp4"]
    if fps > 0:
        cmd += ["-vf", f"fps={fps:g}"]
    cmd += ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(video)]
    print(f"[video] ffmpeg prende {durata:.0f} s da {inizio:.0f} s di {rec} (dal remoto, senza "
          f"scaricare i 200-700 MB interi)", flush=True)
    if subprocess.run(cmd).returncode != 0 or not video.is_file():
        sys.exit("[!] ffmpeg non è riuscito a prendere il pezzo dal dataset: serve internet e un "
                 "ffmpeg recente (richieste parziali su http). Prova a mano:\n    " + " ".join(cmd))
    try:
        scarica(f"{BASE_URL}/MIDI/{rec}.mid", midi)
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"[!] il MIDI del pianoforte non si è scaricato ({e}): senza MIDI vero il corso "
                 f"non ha una verità su cui misurare")
    mb = lambda p: p.stat().st_size / 1024 ** 2       # noqa: E731
    print(f"[pronto] {video} ({mb(video):.1f} MB) + {midi} ({mb(midi):.2f} MB)")
    return video, midi


def main() -> None:
    p = argparse.ArgumentParser(description="Esempi del dataset PianoVAM: elenco numerato e "
                                            "ritaglio di un pezzo, preso dal remoto.")
    p.add_argument("--elenco", action="store_true", help="stampa l'elenco numerato e basta")
    p.add_argument("--json", action="store_true", help="con --elenco: stampa la lista in JSON")
    p.add_argument("--numero", type=int, default=None, help="quale registrazione (1..107)")
    p.add_argument("--caso", action="store_true", help="prendine una a caso (col pezzo in un punto a caso)")
    p.add_argument("--durata", type=float, default=60.0, help="secondi di pezzo (0 = tutta la registrazione)")
    p.add_argument("--inizio", type=float, default=None, help="da che secondo (default 0; con --caso: a caso)")
    p.add_argument("--fps", type=float, default=30.0, help="fps del pezzo (0 = quelli del dataset, 60)")
    p.add_argument("--out", default="esempi_pianovam", help="cartella del pezzo")
    p.add_argument("--aggiorna", action="store_true", help="rilegge il metadata dal dataset")
    p.add_argument("--ffmpeg", default="ffmpeg", help="eseguibile ffmpeg")
    a = p.parse_args()

    voci = elenco(a.aggiorna)
    if not voci:
        sys.exit("[!] il metadata del dataset non ha nessuna registrazione: riprova con --aggiorna")
    if a.elenco:
        if a.json:
            print(json.dumps(voci, ensure_ascii=False))
        else:
            print(f"{len(voci)} registrazioni nel dataset (Video/<record_time>.mp4 + "
                  f"MIDI/<record_time>.mid)")
            for v in voci:
                mm, ss = divmod(int(v["durata"]), 60)
                print(f"  {v['n']:3d}. {v['rec']}  {v['compositore']} — {v['brano']}  "
                      f"({mm}:{ss:02d}, {v['split']}, {v['suona']})")
        return

    if a.caso:
        scelta = random.choice(voci)
    elif a.numero is not None:
        scelte = [v for v in voci if v["n"] == a.numero]
        if not scelte:
            sys.exit(f"[!] esempio {a.numero}: l'elenco va da 1 a {len(voci)} (guarda --elenco)")
        scelta = scelte[0]
    else:
        sys.exit("[!] dimmi quale esempio: --numero N (vedi --elenco) oppure --caso")

    rec, durata_brano = scelta["rec"], scelta["durata"]
    if a.inizio is not None:
        inizio = max(0.0, a.inizio)
    elif a.caso:
        fine = max(1.0, durata_brano - (a.durata or durata_brano) - 5.0)
        inizio = round(random.uniform(0.0, fine), 1)
    else:
        inizio = 0.0
    mm, ss = divmod(int(durata_brano), 60)
    print(f"[esempio] {scelta['n']}/{len(voci)}: {rec} — {scelta['compositore']} {scelta['brano']} "
          f"({mm}:{ss:02d}); prendo da {inizio:.0f} s per {a.durata:.0f} s", flush=True)
    taglia(rec, inizio, a.durata, Path(a.out).expanduser(), a.fps, a.ffmpeg)
    print("[fatto] ora il passo 0: python3 0_prepara.py --video <pezzo.mp4> --out <cartella>")


if __name__ == "__main__":
    main()
