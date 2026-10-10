"""
Piano Detector — Studio web: esegue la pipeline `pipeline.py` su un video qualsiasi
e mostra il risultato (notes.json, song.mid, prima_griglia.jpg, debug.mp4) con un
player MIDI nel browser.

Avvio:  python3 pipeline_web.py
Apri:   http://127.0.0.1:7862

Il server NON importa torch/mediapipe: lancia `pipeline.py` come sottoprocesso,
usando il primo venv disponibile (`.venv-mp10`, `.venv`, ...) e altrimenti
l'interprete corrente. Senza mediapipe la pipeline gira comunque con --senza-mani.

Due motori, stesso formato di uscita:

* **pipeline** (default) — `pipeline.py`: YOLOv8 trova la tastiera, gli hand
  landmarker di mediapipe seguono le dita, il MIDI esce dalle profondita'.
* **ppan** — `ppan_infer.py` del progetto *PianoviVision-PPAN* ("Pay Attention
  to the Keys"): rete pretrainata che legge direttamente il video e predice il
  piano roll. Gira nel suo venv (torch + transformers), quindi il server la
  lancia come sottoprocesso esattamente come la pipeline.

In entrambi i casi lo Studio legge poi `out/notes.json` e `out/prima_griglia.jpg`:
per PPAN li prepara `ppan_bridge.py` (conversione + immagine del ritaglio usato).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

BASE = Path(__file__).resolve().parent
RUNS = BASE / "web_runs"
RUNS.mkdir(exist_ok=True)
PORTA = int(os.environ.get("PORTA", "7862"))
# Progetto PianoviVision-PPAN (motore alternativo "ppan"): contiene ppan_infer.py,
# weights/pytorch_model.bin e il suo venv. Si puo' spostare con PPAN_DIR o con il
# campo "cartella PPAN" del modulo.
PPAN_DIR = Path(os.environ.get("PPAN_DIR") or
                (Path.home() / ".cline" / "data" / "workspaces" / "chat" / "pianovision-ppan"))
ESTENSIONI = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v",
              ".mpg", ".mpeg", ".wmv", ".flv", ".ts", ".3gp", ".mts"}
FILE_SERVIZIO = {"song.mid": "audio/midi", "notes.json": "application/json",
                 "prima_griglia.jpg": "image/jpeg", "debug.mp4": "video/mp4",
                 "notes_ppan.json": "application/json"}   # uscita grezza di PPAN
MAX_LOG = 600

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 ** 3   # 4 GB: un video lungo "grezzo"

_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}
PROC: dict[str, subprocess.Popen] = {}


# --------------------------------------------------------------- ambiente
def python_pipeline() -> str:
    """Interprete da usare per la pipeline: preferisce un venv del progetto."""
    cand = [BASE / ".venv-mp10" / "bin" / "python",
            BASE / ".venv" / "bin" / "python"]
    cand += sorted(BASE.glob(".venv*/bin/python"))
    for p in cand:
        if p.exists():
            return str(p)
    return sys.executable


def _interprete_ppan(cartella: Path) -> str:
    """Interprete per PPAN: il venv del progetto PPAN, altrimenti uno dei nostri."""
    for cand in (cartella / ".venv" / "bin" / "python",
                 cartella / ".venv-ppan" / "bin" / "python"):
        if cand.exists():
            return str(cand)
    return python_pipeline()


def ppan_info(cartella: Path | str | None = None) -> dict:
    """Stato del motore PPAN: dove sta, cosa manca, con quale Python gira.

    PPAN vive in un altro progetto (`(PianoviVision-PPAN`), quindi qui si controlla
    solo che ci siano i pezzi: script, pesi, config e il ponte verso lo Studio.
    """
    d = Path(cartella) if cartella else PPAN_DIR
    infer = d / "ppan_infer.py"
    pesi = d / "weights" / "pytorch_model.bin"
    config = d / "weights" / "config.json"
    venv = d / ".venv" / "bin" / "python"
    try:
        mb = round(pesi.stat().st_size / 1024 ** 2, 1) if pesi.is_file() else 0.0
    except OSError:
        mb = 0.0
    return {
        "dir": str(d),
        "infer": str(infer),
        "esiste": infer.is_file(),
        "pesi": pesi.is_file(),
        "config": config.is_file(),
        "pesi_mb": mb,
        "interprete": _interprete_ppan(d),
        "interprete_venv": venv.is_file(),
        "ponte": (BASE / "ppan_bridge.py").is_file(),
        "pronto": infer.is_file() and pesi.is_file() and config.is_file()
                  and (BASE / "ppan_bridge.py").is_file(),
    }


def ffmpeg_exe() -> str | None:
    return shutil.which("ffmpeg") or ("/opt/homebrew/bin/ffmpeg"
                                      if Path("/opt/homebrew/bin/ffmpeg").exists() else None)


def spazio_libero() -> dict:
    u = shutil.disk_usage(BASE)
    return {"libero_gb": round(u.free / 1024 ** 3, 2),
            "totale_gb": round(u.total / 1024 ** 3, 2)}


def pesi_info(p: Path) -> dict:
    """Un .pt di ultralytics e' un archivio zip: un download troncato ha la firma PK
    ma non la central directory finale, quindi il controllo deve aprire lo zip."""
    if not p.is_file():
        return {"esiste": False, "valido": False, "mb": 0.0}
    mb = round(p.stat().st_size / 1024 ** 2, 1)
    try:
        with zipfile.ZipFile(p) as z:
            return {"esiste": True, "valido": bool(z.namelist()), "mb": mb}
    except Exception:                                          # noqa: BLE001
        return {"esiste": True, "valido": False, "mb": mb}


# ------------------------------------------------------------------- job
def _percorso_job(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{8,32}", job_id or ""):
        raise KeyError(job_id)
    return RUNS / job_id


def _salva(job: dict) -> None:
    d = _percorso_job(job["id"])
    d.mkdir(parents=True, exist_ok=True)
    doc = {k: v for k, v in job.items() if k != "log_da_salvare"}
    tmp = d / "job.json.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(d / "job.json")


def _job(job_id: str) -> dict:
    """Job dalla memoria o, se il server e' stato riavviato, dal disco."""
    with _LOCK:
        if job_id in JOBS:
            return JOBS[job_id]
    d = _percorso_job(job_id)
    f = d / "job.json"
    if not f.is_file():
        raise KeyError(job_id)
    job = json.loads(f.read_text(encoding="utf-8"))
    job.setdefault("log", [])
    if job.get("stato") == "in_corso":       # rimasto orfano da un riavvio
        job["stato"] = "errore"
        job["errore"] = "server riavviato durante l'elaborazione"
    with _LOCK:
        JOBS.setdefault(job_id, job)
        return JOBS[job_id]


_RX_VIDEO = re.compile(r"^\[video\] .*?: (\d+)x(\d+), ([\d.]+) fps, (\d+) frame, passo=(\d+)")
_RX_GRIGLIA = re.compile(r"^\[griglia\] estensione (\d+)\.\.(\d+)")
_RX_EVENTI = re.compile(r"^eventi nota\s*:\s*(\d+)")
# --- motore PPAN ("ppan_infer.py"): le righe di stato arrivano indentate di 2 spazi
_RX_PPAN_FINESTRE = re.compile(r"^inferenza PPAN \((\d+)/(\d+) finestre\)")
_RX_PPAN_FINE = re.compile(r"^note:\s*(\d+) in ([\d.]+)s \(frame (\d+), device (\S+?), crop (.+)\)$")
_RX_PPAN_TASTIERA = re.compile(r"^tastiera:\s*(\d+) tasti da (\d+)")


def _log(job: dict, riga: str) -> None:
    riga = riga.rstrip()
    if not riga:
        return
    job["log"].append({"t": time.strftime("%H:%M:%S"), "s": riga})
    del job["log"][:-MAX_LOG]
    m = _RX_VIDEO.match(riga)
    if m:
        W, H, fps, n_tot, passo = m.groups()
        job["meta"]["fps"] = float(fps)
        job["meta"]["frame_totali"] = int(n_tot)
        job["meta"]["larghezza"] = int(W)
        job["meta"]["altezza"] = int(H)
        job["meta"]["passo"] = int(passo)
    m = _RX_GRIGLIA.match(riga)
    if m:
        job["meta"]["prima_nota"], job["meta"]["ultima_nota"] = (int(x) for x in m.groups())
    m = _RX_EVENTI.match(riga)
    if m:
        job["meta"]["n_eventi"] = int(m.group(1))
    _log_ppan(job, riga.strip())


def _log_ppan(job: dict, riga: str) -> None:
    """Riconosce le righe di `ppan_infer.py` per fase e barra di avanzamento."""
    if riga.startswith("carico i pesi"):
        job["meta"]["fase"] = "carico i pesi PPAN"
    elif riga.startswith("stima del ritaglio"):
        job["meta"]["fase"] = "stimo il ritaglio della tastiera"
    elif riga.startswith("post-processing"):
        job["meta"]["fase"] = "post-processing delle note"
        job["meta"]["avanzamento_ppan"] = 100.0
    m = _RX_PPAN_FINESTRE.match(riga)
    if m:
        fatto, totale = int(m.group(1)), int(m.group(2))
        job["meta"]["fase"] = f"inferenza PPAN ({fatto}/{totale} finestre)"
        if totale:
            job["meta"]["avanzamento_ppan"] = round(100.0 * fatto / totale, 1)
    m = _RX_PPAN_FINE.match(riga)
    if m:
        job["meta"]["n_eventi"] = int(m.group(1))
        job["meta"]["device"] = m.group(4)
        job["meta"]["crop"] = m.group(5)
        job["meta"]["fase"] = "scrivo JSON e MIDI"
    m = _RX_PPAN_TASTIERA.match(riga)
    if m:
        job["meta"]["ppan_tastiera"] = {"n_tasti": int(m.group(1)),
                                        "prima_nota": int(m.group(2))}
    if riga.startswith("ponte:"):
        job["meta"]["fase"] = "conversione per lo Studio"


# ------------------------------------------------------------ parametri CLI
def _cli(dati: dict) -> tuple[list[str], str | None]:
    """Costruisce gli argomenti di pipeline.py dal form. Ritorna (args, errore)."""
    a: list[str] = []
    modello = (dati.get("modello") or "yolov8l").strip()
    if modello != "yolov8l":
        a += ["--modello", modello]
    if dati.get("conf"):
        a += ["--conf", str(float(dati["conf"]))]
    if dati.get("fps_max"):
        a += ["--fps-max", str(float(dati["fps_max"]))]
    if dati.get("tracker") in ("template", "mil"):
        a += ["--tracker", dati["tracker"]]
    if dati.get("redetect"):
        a += ["--redetect", str(int(dati["redetect"]))]
    for chiave, flag in (("prima_nota", "--prima-nota"), ("ultima_nota", "--ultima-nota")):
        v = (dati.get(chiave) or "").strip()
        if v:
            try:
                n = int(v)
            except ValueError:
                return [], f"{chiave}: '{v}' non e' un numero intero"
            if not 0 <= n <= 127:
                return [], f"{chiave}: valore fuori 0-127"
            a += [flag, str(n)]
    v = (dati.get("n_ottave") or "").strip()
    if v:
        try:
            a += ["--n-ottave", str(float(v.replace(",", ".")))]
        except ValueError:
            return [], f"n_ottave: '{v}' non e' un numero"
    v = (dati.get("limite") or "").strip()
    if v:
        try:
            a += ["--limite", str(int(v))]
        except ValueError:
            return [], f"limite: '{v}' non e' un intero"
    for chiave, flag in (("senza_mani", "--senza-mani"),
                         ("senza_prospettiva", "--senza-prospettiva"),
                         ("debug_video", "--debug-video")):
        if dati.get(chiave) in ("1", "true", "on", True):
            a += [flag]
    return a, None


# ------------------------------------------------- parametri CLI di PPAN
def _numero(dati: dict, chiave: str) -> float | None:
    """Valore numerico opzionale dal form (accetta la virgola decimale)."""
    v = (dati.get(chiave) or "").strip().replace(",", ".")
    if not v:
        return None
    return float(v)                     # ValueError gestito da chi chiama


def _cli_ppan(dati: dict) -> tuple[list[str], str | None]:
    """Costruisce gli argomenti di `ppan_infer.py`. Ritorna (args, errore)."""
    a: list[str] = []
    quad = (dati.get("ppan_quad") or "").strip().replace(";", " ")
    bbox = (dati.get("ppan_bbox") or "").strip()
    if quad:
        punti = quad.split()
        if len(punti) != 4 or any(len(p.replace(",", " ").split()) != 2 for p in punti):
            return [], "4 angoli: servono 4 coppie 'x,y' (alto-sx, alto-dx, basso-dx, basso-sx)"
        a += ["--quad", *punti]
    elif bbox:
        parti = [v.strip() for v in bbox.replace(";", ",").split(",") if v.strip()]
        if len(parti) != 4:
            return [], "riquadro: servono x1,y1,x2,y2"
        a += ["--bbox", ",".join(parti)]
    for chiave, flag in (("ppan_start", "--start"),
                         ("ppan_max_seconds", "--max-seconds"),
                         ("ppan_batch", "--batch-size"),
                         ("ppan_crop_frames", "--crop-frames"),
                         ("ppan_min_note", "--min-note"),
                         ("ppan_thr_onset", "--threshold-onset"),
                         ("ppan_thr_frame", "--threshold-frame"),
                         ("ppan_sigma_onsets", "--sigma-onsets"),
                         ("ppan_sigma_frames", "--sigma-frames")):
        try:
            v = _numero(dati, chiave)
        except ValueError:
            return [], f"{chiave}: '{(dati.get(chiave) or '').strip()}' non e' un numero"
        if v is None:
            continue
        a += [flag, str(int(v)) if chiave in ("ppan_batch", "ppan_crop_frames") else str(v)]
    if dati.get("ppan_frames_only") in ("1", "true", "on", True):
        a += ["--frames-only"]
    return a, None


def _comando(job: dict, video: Path) -> tuple[list[str] | None, str | None]:
    """Il comando da eseguire per questo job: (cmd, errore). Sceglie il motore."""
    p = job["parametri"]
    fuori = Path(job["out_dir"])
    if (p.get("motore") or "pipeline").strip().lower() == "ppan":
        info = ppan_info(p.get("ppan_dir"))
        manca = []
        if not info["esiste"]:
            manca.append("ppan_infer.py")
        if not info["pesi"]:
            manca.append("weights/pytorch_model.bin")
        if not info["config"]:
            manca.append("weights/config.json")
        if not info["ponte"]:
            manca.append("ppan_bridge.py")
        if manca:
            return None, "motore PPAN non disponibile in %s: manca %s" % (
                info["dir"], ", ".join(manca))
        args, errore = _cli_ppan(p)
        if errore:
            return None, errore
        return ([info["interprete"], info["infer"], str(video),
                 "--json", str(fuori / "notes_ppan.json"),
                 "--midi", str(fuori / "song.mid"),
                 "--weights", str(Path(info["dir"]) / "weights")] + args), None
    args, errore = _cli(p)
    if errore:
        return None, errore
    return [python_pipeline(), str(BASE / "pipeline.py"), str(video),
            "-o", job["out_dir"], *args], None


# --------------------------------------------------------- normalizzazione
def _normalizza(job: dict, origine: Path) -> Path:
    """Converte in H.264/yuv420p con ffmpeg (risolve HEVC dei .mov e i bordi dispari).

    Serve perche' OpenCV ignora la rotazione nei metadati e non sempre legge HEVC.
    Se qualcosa va storto si continua con il file originale.
    """
    exe = ffmpeg_exe()
    if exe is None:
        _log(job, "[web] ffmpeg non trovato: uso il video originale")
        return origine
    destinazione = _percorso_job(job["id"]) / "input_norm.mp4"
    cmd = [exe, "-y", "-loglevel", "warning", "-stats", "-i", str(origine),
           "-an", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destinazione)]
    _log(job, f"[web] normalizzo con ffmpeg: {origine.name} -> input_norm.mp4")
    p = PROC[job["id"]] = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True,
                                           bufsize=1, env=dict(os.environ, PYTHONUNBUFFERED="1"))
    for riga in p.stdout:
        riga = riga.strip()
        if "time=" in riga or riga.startswith("frame="):
            job["meta"]["ffmpeg"] = riga[-80:]
        elif riga:
            _log(job, "[ffmpeg] " + riga)
    p.wait()
    job["meta"].pop("ffmpeg", None)
    if p.returncode == 0 and destinazione.is_file() and destinazione.stat().st_size > 0:
        return destinazione
    _log(job, f"[web] normalizzazione non riuscita (codice {p.returncode}): uso l'originale")
    return origine


# ------------------------------------------------------------- esecuzione
def _esegui(job_id: str) -> None:
    job = _job(job_id)
    try:
        cmd, errore = _comando(job, Path(job["video_path"]))    # valida i parametri
        if errore:
            job["stato"], job["errore"] = "errore", errore
            _log(job, "[web] ERRORE parametri: " + errore)
            _salva(job)
            return

        motore = (job["parametri"].get("motore") or "pipeline").strip().lower()
        job["meta"]["motore"] = motore
        video = Path(job["video_path"])
        if job["parametri"].get("normalizza") in ("1", "true", "on", True):
            video = _normalizza(job, video)
            job["video_usato"] = str(video)
            _salva(job)
            if str(video) != job["video_path"]:                 # ricostruisci col nuovo file
                cmd, errore = _comando(job, video)
                if errore:
                    job["stato"], job["errore"] = "errore", errore
                    _log(job, "[web] ERRORE parametri: " + errore)
                    _salva(job)
                    return
            if motore == "ppan":
                _log(job, "[web] nota: PPAN legge il video ri-codificato da ffmpeg; la "
                          "ri-compressione puo' togliere note. Se il risultato e' scarso "
                          "riprova senza «normalizza con ffmpeg» (serve solo per .mov/HEVC o "
                          "video ruotati).")

        _log(job, "[web] motore: %s" % ("PPAN - Pay Attention to the Keys"
                                        if motore == "ppan" else "pipeline (YOLO + mani)"))
        _log(job, "[web] " + " ".join(cmd))
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        p = PROC[job_id] = subprocess.Popen(cmd, cwd=str(BASE), stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True,
                                            bufsize=1, env=env)
        job["pid"] = p.pid
        _salva(job)
        for riga in p.stdout:
            _log(job, riga)
        code = p.wait()
        job.pop("pid", None)

        if code == 0 and motore == "ppan":
            # PPAN scrive notes_ppan.json: il ponte lo porta nello schema della
            # pipeline (+ immagine del ritaglio), cosi' il resto del server e la
            # pagina non devono sapere quale motore ha prodotto il risultato.
            if _ponte_ppan(job, video) != 0:
                job["meta"]["avviso"] = ("il MIDI c'e' ma la conversione per lo Studio non "
                                         "e' riuscita: mancano notes.json/immagine del ritaglio")

        fuori = Path(job["out_dir"])
        job["risultati"] = sorted(f.name for f in fuori.glob("*")) if fuori.is_dir() else []
        try:
            dati = json.loads((fuori / "notes.json").read_text(encoding="utf-8"))
            job["riepilogo"] = dati.get("riepilogo")
            job["eventi"] = dati.get("eventi", [])
            job["meta"]["estensione"] = dati.get("estensione_tastiera")
            if motore == "ppan" and not job["eventi"]:
                # Il caso piu' frequente: il ritaglio automatico ha inquadrato
                # qualcos'altro (spartito, mobile) e la rete non vede nemmeno un tasto.
                job["meta"]["avviso"] = (
                    "PPAN non ha trovato nemmeno una nota: quasi sempre il ritaglio automatico "
                    "ha inquadrato qualcosa che non e' la tastiera (per esempio lo spartito). "
                    "Apri prima_griglia.jpg: se la striscia non mostra i tasti, segna i 4 angoli "
                    "della tastiera sul video e rilancia.")
                _log(job, "[web] avviso: PPAN ha trovato 0 note. Apri prima_griglia.jpg: se la "
                          "striscia non mostra i tasti, il ritaglio automatico ha preso "
                          "un'altra cosa (spartito, mobile). Segna i 4 angoli della tastiera e "
                          "rilancia.")
        except (OSError, json.JSONDecodeError):
            pass
        job["codice_uscita"] = code
        if job.get("annullato"):
            job["stato"] = "annullato"
        elif code == 0:
            job["stato"] = "fatto"
        else:
            job["stato"] = "errore"
            job["errore"] = ("%s e' uscita con codice %d"
                             % ("ppan_infer.py" if motore == "ppan" else "pipeline.py", code))
    except Exception as exc:                                   # noqa: BLE001
        job["stato"], job["errore"] = "errore", f"{type(exc).__name__}: {exc}"
        _log(job, f"[web] eccezione: {type(exc).__name__}: {exc}")
    finally:
        _finalizza(job)


def _ponte_ppan(job: dict, video: Path) -> int:
    """Converte l'uscita di PPAN nello schema dello Studio (notes.json + immagine).

    Serve cv2/numpy, quindi gira nell'interprete di PPAN; il server resta senza
    dipendenze pesanti. Ritorna il codice di uscita del ponte.
    """
    fuori = Path(job["out_dir"])
    sorgente = fuori / "notes_ppan.json"
    if not sorgente.is_file():
        _log(job, "[web] PPAN non ha prodotto notes_ppan.json: niente conversione")
        return 1
    cmd = [ppan_info(job["parametri"].get("ppan_dir"))["interprete"],
           str(BASE / "ppan_bridge.py"), str(sorgente), str(fuori / "notes.json"),
           str(video), str(fuori / "prima_griglia.jpg")]
    _log(job, "[web] " + " ".join(cmd))
    p = PROC[job["id"]] = subprocess.Popen(cmd, cwd=str(BASE), stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, text=True, bufsize=1,
                                          env=dict(os.environ, PYTHONUNBUFFERED="1"))
    for riga in p.stdout:
        _log(job, riga)
    code = p.wait()
    PROC.pop(job["id"], None)
    if code != 0:
        _log(job, f"[web] il ponte PPAN e' uscito con codice {code}")
    return code


def _finalizza(job: dict) -> None:
    """Elimina il video caricato (se richiesto), toglie il processore e salva."""
    PROC.pop(job["id"], None)
    if job["parametri"].get("elimina_input") in ("1", "true", "on", True):
        for chiave in ("video_path", "video_usato"):
            f = job.get(chiave)
            if f and Path(f).is_file() and Path(f).parent == _percorso_job(job["id"]):
                try:
                    Path(f).unlink()
                except OSError:
                    pass
        job["input_eliminato"] = True
    job["finito_il"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _salva(job)


# ----------------------------------------------------------------- rotte
@app.get("/")
def index():
    return send_from_directory(BASE, "pipeline_studio.html")


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/api/stato")
def stato():
    py = python_pipeline()
    return jsonify({
        "python": py,
        "python_progetto": py != sys.executable,
        "ffmpeg": ffmpeg_exe(),
        "spazio": spazio_libero(),
        "pesi_yolo": {n: pesi_info(BASE / "weights" / f"{n}-oiv7.pt")
                      for n in ("yolov8m", "yolov8l", "yolov8x")},
        "modello_mani": (BASE / "weights" / "hand_landmarker.task").exists(),
        "ppan": ppan_info(),
    })


@app.get("/api/jobs")
def jobs():
    elenco = []
    for d in sorted(RUNS.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            j = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        elenco.append({"id": j.get("id"), "video": j.get("video_nome"),
                       "creato": j.get("creato_il"), "stato": j.get("stato"),
                       "motore": (j.get("parametri") or {}).get("motore"),
                       "n_eventi": (j.get("riepilogo") or {}).get("n_eventi")})
    return jsonify(elenco[:30])


@app.post("/api/job")
def nuovo_job():
    file = request.files.get("video")
    if file is None or not file.filename:
        return jsonify({"errore": "nessun video caricato"}), 400
    ext = Path(file.filename).suffix.lower()
    if ext not in ESTENSIONI:
        return jsonify({"errore": f"estensione '{ext or '?'}' non supportata"}), 400
    if spazio_libero()["libero_gb"] < 1.0:
        return jsonify({"errore": "meno di 1 GB libero su disco: libera spazio prima di procedere"}), 507

    motore = (request.form.get("motore") or "pipeline").strip().lower()
    if motore == "ppan":
        info = ppan_info(request.form.get("ppan_dir"))
        if not info["pronto"]:
            return jsonify({"errore": f"motore PPAN non pronto in {info['dir']}: servono "
                                      f"ppan_infer.py, weights/pytorch_model.bin, "
                                      f"weights/config.json e ppan_bridge.py"}), 409
    else:
        modello = (request.form.get("modello") or "yolov8l").strip()
        percorso_pesi = (Path(modello) if modello.endswith(".pt") and Path(modello).is_file()
                         else BASE / "weights" / (modello if modello.endswith(".pt")
                                                  else f"{modello}-oiv7.pt"))
        info_pesi = pesi_info(percorso_pesi)
        if not info_pesi["valido"]:
            motivo = "assente" if not info_pesi["esiste"] else "corrotto o troncato"
            return jsonify({"errore": f"i pesi '{modello}' risultano {motivo} "
                                      f"({info_pesi['mb']} MB): riscaricali con  wget "
                                      f"https://github.com/ultralytics/assets/releases/download/"
                                      f"v8.3.0/{modello}-oiv7.pt -P weights/"}), 409

    job_id = uuid.uuid4().hex[:16]
    d = _percorso_job(job_id)
    (d / "out").mkdir(parents=True, exist_ok=True)
    destinazione = d / f"input{ext}"
    file.save(str(destinazione))

    parametri = {k: v for k, v in request.form.items()}
    job = {
        "id": job_id, "creato_il": time.strftime("%Y-%m-%d %H:%M:%S"),
        "video_nome": Path(file.filename).name, "video_path": str(destinazione),
        "video_mb": round(destinazione.stat().st_size / 1024 ** 2, 1),
        "out_dir": str(d / "out"), "stato": "in_corso", "errore": None,
        "parametri": parametri, "meta": {}, "log": [], "riepilogo": None,
        "eventi": [], "risultati": [],
    }
    with _LOCK:
        JOBS[job_id] = job
    _log(job, f"[web] job {job_id}: {job['video_nome']} ({job['video_mb']} MB)")
    _salva(job)
    threading.Thread(target=_esegui, args=(job_id,), daemon=True).start()
    return jsonify({"id": job_id})


@app.get("/api/job/<job_id>")
def leggi_job(job_id):
    try:
        job = _job(job_id)
    except KeyError:
        return jsonify({"errore": "job inesistente"}), 404
    with _LOCK:
        job["log"] = job.get("log", [])
    return jsonify({
        "id": job["id"], "stato": job["stato"], "errore": job.get("errore"),
        "video_nome": job.get("video_nome"), "video_mb": job.get("video_mb"),
        "creato_il": job.get("creato_il"), "finito_il": job.get("finito_il"),
        "meta": job.get("meta", {}), "riepilogo": job.get("riepilogo"),
        "eventi": job.get("eventi", []), "risultati": job.get("risultati", []),
        "codice_uscita": job.get("codice_uscita"), "parametri": job.get("parametri", {}),
        "input_eliminato": job.get("input_eliminato", False),
        "log": [r for r in job.get("log", [])],
    })


@app.post("/api/job/<job_id>/annulla")
def annulla(job_id):
    try:
        _job(job_id)
    except KeyError:
        return jsonify({"errore": "job inesistente"}), 404
    p = PROC.get(job_id)
    if p is None or p.poll() is not None:
        return jsonify({"esito": "gia' concluso"})
    JOBS[job_id]["annullato"] = True
    p.terminate()
    _log(JOBS[job_id], "[web] annullamento richiesto: termino il processo")
    return jsonify({"esito": "terminato"})


@app.post("/api/job/<job_id>/elimina")
def elimina(job_id):
    try:
        d = _percorso_job(job_id)
    except KeyError:
        return jsonify({"errore": "job inesistente"}), 404
    if job_id in PROC and PROC[job_id].poll() is None:
        return jsonify({"errore": "job in corso: annullalo prima"}), 409
    with _LOCK:
        JOBS.pop(job_id, None)
    shutil.rmtree(d, ignore_errors=True)
    return jsonify({"esito": "eliminato"})


@app.get("/api/job/<job_id>/file/<nome>")
def file_job(job_id, nome):
    if nome not in FILE_SERVIZIO:
        return jsonify({"errore": "file non previsto"}), 404
    try:
        f = _percorso_job(job_id) / "out" / nome
    except KeyError:
        return jsonify({"errore": "job inesistente"}), 404
    if not f.is_file():
        return jsonify({"errore": f"{nome} non presente"}), 404
    return send_file(f, mimetype=FILE_SERVIZIO[nome], conditional=True)


if __name__ == "__main__":
    print("🎹 Piano Detector — Studio (pipeline video → MIDI)")
    print(f"   interprete pipeline: {python_pipeline()}")
    print(f"   ffmpeg            : {ffmpeg_exe() or 'NON trovato (niente normalizzazione, niente debug.mp4)'}")
    s = spazio_libero()
    print(f"   spazio disco      : {s['libero_gb']} GB liberi su {s['totale_gb']} GB")
    pp = ppan_info()
    print(f"   motore PPAN       : {'pronto' if pp['pronto'] else 'NON pronto'} "
          f"({pp['pesi_mb']} MB di pesi) in {pp['dir']}")
    if not pp["pronto"]:
        print("                       motore PPAN non utilizzabile: la pagina lo disabilita "
              "(serve ppan_infer.py + weights/ + ppan_bridge.py)")
    print(f"   Apri              : http://127.0.0.1:{PORTA}")
    app.run(host="127.0.0.1", port=PORTA, threaded=True, debug=False)
