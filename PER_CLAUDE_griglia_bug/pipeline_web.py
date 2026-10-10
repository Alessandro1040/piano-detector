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

* **calibrato** — `motore_calibrato.py`: il software misura sul video dove sta ogni nota
  in ogni frame (sagome), ne ricava una clip per nota e decide premuto/rilasciato dentro
  ogni riquadro. Dichiara l'ottava (o le candidate) e non emette note non inquadrate.

* **prospettica** — `motore_prospettica.py`: la griglia dei tasti e' ricostruita dalla sola
  geometria della tastiera (profilo verticale + tasti neri via NCC), quindi regge le
  inquadrature oblique e non usa ne' YOLO ne' mediapipe. Sagome per nota e MIDI escono
  come nel calibrato; la griglia viene riagganciata da zero a ogni cambio di inquadratura.

In tutti i casi lo Studio legge poi `out/notes.json` e `out/prima_griglia.jpg`:
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
                 "griglia.mp4": "video/mp4",
                 "notes_ppan.json": "application/json",   # uscita grezza di PPAN
                 "griglia.json": "application/json", "mani.json": "application/json",
                 "modello.pt": "application/octet-stream", "probabilita.json": "application/json"}
EST_MIDI = {".mid", ".midi", ".smf"}
# Materiale e prove: glob relativi a BASE. La pagina "File e materiale" li mostra tutti
# come collegamenti (niente da copiare a mano): documenti, pacchetti, per_claude, prove.
MATERIALE = [
    ("📄 Documenti e brief", ["README.md", "BRIEF_CLAUDE*.md", "HANDOFF_CLINE.md",
                              "PER_DEEPSEEK.md", "*.md"]),
    ("📦 Pacchetti pronti da mandare", ["*.zip"]),
    ("🎹 Griglia prospettica 88 tasti (studio + prove)",
     ["per_claude/GRIGLIA_PROSPETTICA_88tasti/*"]),
    ("🧰 Materiale per Claude (codice e log per la chat)", ["per_claude/*"]),
    ("🎓 Addestra i tasti (script, dataset, modello, prova)",
     ["addestra_tasti/*.py", "addestra_tasti/*.html", "addestra_tasti/prova_1video/*",
      "addestra_tasti/prova_1video/*/*"]),
    ("🖼 Immagini di prova (griglia e ritagli)", ["test_images/*", "demo_output/*"]),
    ("🎬 Video di prova", ["*.mp4", "web_runs/*/out/*.mp4"]),
    ("⚙️ Motori e script del progetto", ["*.py", "*.html"]),
]
MAX_LOG = 600

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 ** 3   # 4 GB: un video lungo "grezzo"


@app.errorhandler(413)
def _carico_troppo_grosso(_e):
    """Oltre il limite il browser riceverebbe la pagina d'errore di Flask, che la pagina del sito
    non sa leggere (si vedrebbe un errore di JSON): meglio un messaggio che si capisce."""
    n = app.config["MAX_CONTENT_LENGTH"]
    quanto = (f"{n / 1024 ** 3:.0f} GB" if n >= 1024 ** 3
              else f"{n / 1024 ** 2:.0f} MB" if n >= 1024 ** 2 else f"{n} byte")
    return jsonify({"errore": f"hai caricato piu' di {quanto} in una volta: carica meno pezzi "
                              f"insieme oppure comprimi i video (es. ffmpeg -i brano1.mp4 "
                              f"-crf 20 brano1_piccolo.mp4) e riprova"}), 413

_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}
PROC: dict[str, subprocess.Popen] = {}

# --- passo 0: "Prepara il video" (ritaglio sulla tastiera) ------------------------------
# Non sono job come gli altri: non producono un modello, quindi NON entrano in JOBS (l'elenco
# dei lavori, «annulla» e «cancella le esecuzioni precedenti» non li devono vedere). Vivono in
# web_runs/_prepara/<id>/ e si cancellano a mano, o quando il pezzo va nel cantiere.
PREPARA: dict[str, dict] = {}
PREPARA_DIR = RUNS / "_prepara"
CANTIERE_DIR = RUNS / "_cantiere"
ESEMPI_SCRIPT = "addestra_tasti/7_esempio_pianovam.py"


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


_MP_OK: bool | None = None


def _mediapipe_ok() -> bool:
    """Vero se l'interprete della pipeline sa importare mediapipe (serve per le dita).

    Si controlla una volta per avvio del server: l'import di mediapipe costa qualche
    secondo e la pagina lo chiede a ogni caricamento.
    """
    global _MP_OK
    if _MP_OK is None:
        try:
            r = subprocess.run([python_pipeline(), "-c", "import mediapipe"], cwd=str(BASE),
                               capture_output=True, timeout=120)
            _MP_OK = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _MP_OK = False
    return _MP_OK


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


def _cli_calibrato(dati: dict, job_dir: str) -> tuple[list[str], str | None]:
    """Argomenti di motore_calibrato.py dal form. Ritorna (args, errore)."""
    a: list[str] = ["--cartella-sagome", job_dir]
    quad = (dati.get("ppan_quad") or dati.get("quad") or "").strip().replace(";", " ")
    if quad:
        if len(quad.replace(",", " ").split()) != 8:
            return [], "quad: servono 8 numeri (x,y dei 4 angoli)"
        a += ["--quad", quad]
    for chiave, flag, tipo in (("cal_prima_nota", "--prima-nota", int),
                               ("cal_max_sec", "--max-secondi", float),
                               ("cal_giu", "--soglia-giu", float),
                               ("cal_su", "--soglia-su", float),
                               ("cal_finestra", "--finestra", int)):
        v = (dati.get(chiave) or "").strip()
        if v:
            try:
                x = tipo(v.replace(",", "."))
            except ValueError:
                return [], f"{chiave}: '{v}' non e' un numero valido"
            a += [flag, str(x)]
    fmt = (dati.get("cal_formato") or "mp4").strip().lower()
    if fmt not in ("mp4", "jpeg"):
        return [], "cal_formato: usa mp4 oppure jpeg"
    a += ["--formato-clip", fmt]
    return a, None


def _cli_prospettica(dati: dict, job_dir: str) -> tuple[list[str], str | None]:
    """Argomenti di motore_prospettica.py dal form. Ritorna (args, errore)."""
    a: list[str] = ["--cartella-sagome", job_dir]
    for chiave, flag, tipo in (("pros_prima_nota", "--prima-nota", int),
                               ("pros_gruppo2", "--nota-gruppo2", int),
                               ("pros_max_sec", "--max-secondi", float),
                               ("pros_giu", "--soglia-giu", float),
                               ("pros_su", "--soglia-su", float),
                               ("pros_finestra", "--finestra", int),
                               ("pros_font_note", "--font-note", float),
                               ("pros_spessore_bordi", "--spessore-bordi", int)):
        v = (dati.get(chiave) or "").strip()
        if v:
            try:
                x = tipo(v.replace(",", "."))
            except ValueError:
                return [], f"{chiave}: '{v}' non e' un numero valido"
            a += [flag, str(x)]
    if dati.get("pros_filtro_mani") in ("1", "true", "on", True):
        # mani.json lo prepara il server prima del motore (vedi _prepara_mani)
        a += ["--mani", str(Path(job_dir) / "mani.json")]
        v = (dati.get("pros_raggio_mani") or "").strip()
        if v:
            try:
                a += ["--raggio-mani", str(float(v.replace(",", ".")))]
            except ValueError:
                return [], f"pros_raggio_mani: '{v}' non e' un numero valido"
    fmt = (dati.get("pros_formato") or "mp4").strip().lower()
    if fmt not in ("mp4", "jpeg"):
        return [], "pros_formato: usa mp4 oppure jpeg"
    a += ["--formato-clip", fmt]
    if dati.get("pros_senza_video") in ("1", "true", "on", True):
        a += ["--senza-video-griglia"]
    if dati.get("pros_senza_clip") in ("1", "true", "on", True):
        a += ["--senza-clip"]
    if dati.get("pros_senza_bordi") in ("1", "true", "on", True):
        a += ["--senza-bordi"]
    if dati.get("pros_senza_scritte") in ("1", "true", "on", True):
        a += ["--senza-scritte-note"]
    return a, None


def _comando(job: dict, video: Path) -> tuple[list[str] | None, str | None]:
    """Il comando da eseguire per questo job: (cmd, errore). Sceglie il motore."""
    p = job["parametri"]
    fuori = Path(job["out_dir"])
    if (p.get("motore") or "prospettica").strip().lower() == "ppan":
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
    if (p.get("motore") or "prospettica").strip().lower() == "calibrato":
        if not (BASE / "motore_calibrato.py").is_file() or not (BASE / "sagome.py").is_file():
            return None, "motore calibrato non disponibile: mancano motore_calibrato.py / sagome.py"
        args, errore = _cli_calibrato(p, str(_percorso_job(job["id"])))
        if errore:
            return None, errore
        return [python_pipeline(), str(BASE / "motore_calibrato.py"), str(video),
                "-o", job["out_dir"], *args], None
    if (p.get("motore") or "prospettica").strip().lower() == "prospettica":
        if not (BASE / "motore_prospettica.py").is_file() or not (BASE / "griglia_prospettica.py").is_file():
            return None, ("motore prospettica non disponibile: mancano "
                          "motore_prospettica.py / griglia_prospettica.py")
        args, errore = _cli_prospettica(p, str(_percorso_job(job["id"])))
        if errore:
            return None, errore
        return [python_pipeline(), str(BASE / "motore_prospettica.py"), str(video),
                "-o", job["out_dir"], *args], None
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
    # -nostdin: ffmpeg non deve leggere lo stdin. Se lo facesse mentre il server
    # gira come job in background sulla tty, il kernel manderebbe SIGTTIN a tutto
    # il gruppo di processi e il server si impunterebbe (pagina ferma su "0 s").
    cmd = [exe, "-nostdin", "-y", "-loglevel", "warning", "-stats", "-i", str(origine),
           "-an", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destinazione)]
    _log(job, f"[web] normalizzo con ffmpeg: {origine.name} -> input_norm.mp4")
    p = PROC[job["id"]] = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE,
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
def _togli_opzione(cmd: list[str], nome: str) -> list[str]:
    """Toglie `nome` e il suo valore dal comando (per riusarlo senza quell'opzione)."""
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] == nome:
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out


def _prepara_mani(job: dict, video: Path) -> bool:
    """Scrive `mani.json` (polpastrelli per frame) per il filtro mani. False = non si puo'.

    Usa `addestra_tasti/1_estrai_mani.py`, che ha bisogno di mediapipe: gira con
    l'interprete del progetto (il venv), non con il server. Se qualcosa manca non e' un
    errore fatale: il job prosegue senza filtro e la pagina lo dice.
    """
    script = BASE / "addestra_tasti" / "1_estrai_mani.py"
    out = _percorso_job(job["id"]) / "mani.json"
    if not script.is_file():
        _log(job, "[web] filtro mani non disponibile: manca addestra_tasti/1_estrai_mani.py")
        return False
    cmd = [python_pipeline(), str(script), str(video), "-o", str(out)]
    job["meta"]["fase"] = "cerco le mani nel video"
    _log(job, "[web] filtro mani: cerco le dita nel video (puo' durare quanto il video)")
    p = PROC[job["id"]] = subprocess.Popen(cmd, cwd=str(BASE), stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, bufsize=1,
                                           env=dict(os.environ, PYTHONUNBUFFERED="1"))
    for riga in p.stdout:
        _log(job, "[mani] " + riga.rstrip())
    code = p.wait()
    if code != 0 or not out.is_file():
        _log(job, f"[web] filtro mani: ricerca delle dita non riuscita (codice {code}): "
                  f"proseguo tenendo tutte le note")
        return False
    return True


def _esegui(job_id: str) -> None:
    job = _job(job_id)
    try:
        cmd, errore = _comando(job, Path(job["video_path"]))    # valida i parametri
        if errore:
            job["stato"], job["errore"] = "errore", errore
            _log(job, "[web] ERRORE parametri: " + errore)
            _salva(job)
            return

        motore = (job["parametri"].get("motore") or "prospettica").strip().lower()
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

        _log(job, "[web] motore: %s" % ("PPAN - Pay Attention to the Keys" if motore == "ppan"
                                        else "calibrato (sagome per nota)" if motore == "calibrato"
                                        else "prospettica (griglia geometrica dei tasti)"
                                        if motore == "prospettica"
                                        else "pipeline (YOLO + mani)"))
        if "--mani" in cmd:                       # filtro mani: prima servono i polpastrelli
            if not _prepara_mani(job, video):
                cmd = _togli_opzione(cmd, "--mani")
                job["meta"]["avviso"] = ("filtro mani non applicato (dita non riconosciute): "
                                        "il MIDI puo' contenere note lontane dalle mani")
        _log(job, "[web] " + " ".join(cmd))
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        p = PROC[job_id] = subprocess.Popen(cmd, cwd=str(BASE), stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE,
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
            filtro = ((dati.get("prospettica") or dati.get("calibrato") or {})
                      .get("filtro_mani"))
            if filtro:
                job["meta"]["filtro_mani"] = filtro
                _log(job, "[web] filtro mani: %d eventi -> %d (%d scartati perche' lontani dalle "
                          "dita, %d senza mani visibili)" % (filtro["eventi_prima"],
                                                             filtro["eventi_dopo"],
                                                             filtro["scartati_lontani"],
                                                             filtro["tenuti_senza_mani"]))
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
                             % ({"ppan": "ppan_infer.py", "calibrato": "motore_calibrato.py",
                                 "prospettica": "motore_prospettica.py"}.get(motore, "pipeline.py"),
                                code))
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
    p = PROC[job["id"]] = subprocess.Popen(cmd, cwd=str(BASE), stdin=subprocess.DEVNULL,
                                          stdout=subprocess.PIPE,
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


def _sgombera_precedenti(escluso: str | None, elimina_tutto: bool) -> tuple[list[str], list[str]]:
    """Libera il disco dalle esecuzioni precedenti. Ritorna (azzerate, eliminate).

    Un'esecuzione serve a produrre il MIDI: video di input, clip per nota, log e risultati
    sono la parte che pesa, e dopo che il risultato e' stato guardato non servono piu'. Per
    questo la pagina ha acceso `elimina_tutto` di default: la cartella precedente sparisce
    per intero, invece di restare li' a occupare spazio.

    Con `elimina_tutto=False` si cancellano solo le sagome (D4: valgono per il singolo video,
    cambiarne uno le invalida) e il resto resta consultabile dalla pagina.

    Le esecuzioni ancora in corso non si toccano mai: la loro cartella e' in uso dal processo
    del motore. `escluso=None` significa "nessuna esenzione" (pulizia globale).
    """
    azzerate: list[str] = []
    eliminate: list[str] = []
    for d in list(RUNS.iterdir()):            # lista: le cartelle spariscono mentre si scorre
        if not d.is_dir() or d.name == escluso:
            continue
        if _e_corso(d):                       # i corsi di addestramento non si buttano via
            continue
        p = PROC.get(d.name)
        if p is not None and p.poll() is None:          # job ancora in corso: non si tocca
            continue
        if elimina_tutto:
            shutil.rmtree(d, ignore_errors=True)
            with _LOCK:
                JOBS.pop(d.name, None)
            eliminate.append(d.name)
            continue
        toccato = False
        if (d / "sagome.json").exists():
            (d / "sagome.json").unlink()
            toccato = True
        if (d / "sagome").is_dir():
            shutil.rmtree(d / "sagome", ignore_errors=True)
            toccato = True
        if toccato:
            azzerate.append(d.name)
    return azzerate, eliminate


# ----------------------------------------------------- corsi di addestramento
class _Annullato(Exception):
    """Il corso e' stato annullato dall'utente."""


_RX_DATASET = re.compile(r"(\d+) campioni, (\d+) premuti \(([\d.]+)%")
_RX_RITARDO = re.compile(r"ritardo usato per le etichette:\s*([-+]?[\d.]+)")   # quello applicato
_RX_RIT_AUTO = re.compile(r"ritardo stimato\s*([-+]?[\d.]+) s \(correlazione ([\d.]+)\)")
_RX_RAGGIO = re.compile(r"raggio scelto (?:da 'auto'|a mano):\s*([\d.]+)")
_RX_EPOCA = re.compile(r"^epoca\s+(\d+)\s+loss ([\d.]+)")
_RX_F1 = re.compile(r"val F1 ([\d.]+)")
_RX_VAL = re.compile(r"^val\s+\d+ da \d+ pezzi: (.+)$")
_RX_F1NOTA = re.compile(r"TOTALE: F1 ([\d.]+)")          # l'uscita di 5_valuta (uscita vera)
_RX_F1_NOTE_TRAIN = re.compile(r"F1 sulle note ([\d.]+)")  # cosa ha scelto 3_addestra


def _e_corso(d: Path) -> bool:
    """Vero se la cartella e' un corso di addestramento (i suoi dataset non si buttano)."""
    if not (d / "pezzi").is_dir():
        return False
    try:
        return json.loads((d / "job.json").read_text(encoding="utf-8")).get("tipo") == "addestra"
    except (OSError, json.JSONDecodeError):
        return True                    # cartella con i pezzi ma senza job.json: meglio non toccarla


def _corso_passo(job: dict, cmd: list[str]) -> tuple[int, list[str]]:
    """Esegue un passo del corso: ogni riga di uscita finisce nel log della pagina."""
    righe: list[str] = []
    p = PROC[job["id"]] = subprocess.Popen(cmd, cwd=str(BASE), stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, bufsize=1,
                                           env=dict(os.environ, PYTHONUNBUFFERED="1"))
    job["pid"] = p.pid
    for riga in p.stdout:
        riga = riga.rstrip()
        if riga:
            _log(job, riga)
            righe.append(riga)
    code = p.wait()
    job.pop("pid", None)
    return code, righe


def _esegui_addestra(job_id: str) -> None:
    """Da "coppie video+MIDI caricate" a "modello.pt".

    Per ogni pezzo: griglia dei tasti (motore prospettico, solo JSON) -> polpastrelli ->
    dataset. Poi UN solo addestramento su tutti i dataset (la validazione e' su video
    interi, non su frame sparsi) e, se richiesto, l'inferenza di prova su un pezzo. Ogni
    passo e' un processo a se': nel log della pagina si vede tutto e «annulla» ferma il
    passo in corso.

    Il ritardo MIDI-video e' per pezzo (scostamento scelto a mano o stimato da `auto`) e ogni
    dataset porta con se' le immagini di controllo dell'allineamento (tasti che il MIDI dice
    premuti, disegnati sul video vero). Con `parametri.prepara` ci si ferma prima di addestrare:
    e' il «Controlla l'allineamento» della pagina. Griglia e dita gia' presenti nella cartella si
    riusano, cosi' il secondo tentativo (col ritardo sistemato) costa un minuto invece di un'ora.
    """
    job = _job(job_id)
    # la cartella degli input: con "riusa" il corso ripreso puo' avere gli input in un'ALTRA
    # cartella (quella del corso preparato), quindi si usa quella scritta nel job
    d = Path(job.get("in_dir") or _percorso_job(job_id))
    fuori = Path(job["out_dir"])
    py = python_pipeline()
    add = BASE / "addestra_tasti"
    p = job["parametri"]
    raggio = p.get("raggio") or "auto"
    desc_raggio = ("auto (misurato sui pezzi)" if str(raggio).strip().lower() == "auto"
                   else f"{raggio} larghezze di tasto")
    allineamenti = {k: str(v) for k, v in (p.get("allineamenti") or {}).items() if str(v).strip()}
    desc_rit = (f"{p.get('ritardo') or 'auto'}"
                + (f" e {len(allineamenti)} scelti a mano pezzo per pezzo" if allineamenti else ""))
    try:
        coppie = list(job["meta"]["coppie"])
        for nome in ("griglia", "mani", "dataset", "probabilita"):
            (fuori / nome).mkdir(parents=True, exist_ok=True)
        job["meta"]["fase"] = "preparo i pezzi"
        _log(job, "[corso] %d pezzi, %s epoche, raggio %s, ritardo MIDI %s"
                  % (len(coppie), p.get("epoche"), desc_raggio, desc_rit))
        if allineamenti:
            _log(job, "[corso] scostamenti scelti a mano (secondi, positivo = il video e' in "
                      "ritardo sul MIDI): " + ", ".join(f"{k} {v}" for k, v in allineamenti.items()))
        _log(job, "[corso] pezzi: " + ", ".join(c["stem"] for c in coppie))
        for c in coppie:
            if Path(c["midi"]).name.lower() == "song.mid":
                _log(job, f"[corso] attenzione su '{c['stem']}': il MIDI si chiama song.mid, cioe' il "
                          f"nome che i motori danno alle loro previsioni. Se non e' il MIDI VERO del "
                          f"brano, la rete impara a copiare gli errori del motore e non potra' mai "
                          f"essere meglio di lui.")
        pezzi_ok: list[str] = []
        for k, c in enumerate(coppie, 1):
            if job.get("annullato"):
                raise _Annullato()
            stem = c["stem"]
            video, midi = d / c["video"], d / c["midi"]
            job["meta"]["progresso"] = round(88.0 * (k - 1) / len(coppie), 1)

            # 1) griglia dei tasti del pezzo: e' quella che serve al dataset. Se c'e' gia'
            # (corso ripreso dopo il controllo dell'allineamento) si riusa: rifarla costerebbe
            # minuti e darebbe lo stesso risultato.
            job["meta"]["fase"] = f"[{k}/{len(coppie)}] {stem}: griglia dei tasti"
            cartella = fuori / "griglia" / stem
            griglia = cartella / "griglia.json"
            if griglia.is_file():
                _log(job, f"[corso] '{stem}': riuso la griglia gia' calcolata")
            else:
                cmd = [py, str(BASE / "motore_prospettica.py"), str(video), "-o", str(cartella),
                       "--json-griglia", "--senza-clip", "--senza-video-griglia"]
                if p.get("prima_nota"):
                    cmd += ["--prima-nota", str(p["prima_nota"])]
                code, _ = _corso_passo(job, cmd)
                if code != 0 or not griglia.is_file():
                    _log(job, f"[corso] pezzo '{stem}': griglia non riuscita (codice {code}): "
                              f"salto il pezzo")
                    continue

            # 2) polpastrelli per frame (filtro mani). Senza mediapipe si prosegue lo stesso.
            mani = fuori / "mani" / f"{stem}.json"
            if mani.is_file():
                _log(job, f"[corso] '{stem}': riuso le dita gia' estratte")
            else:
                job["meta"]["fase"] = f"[{k}/{len(coppie)}] {stem}: dita nel video"
                code, _ = _corso_passo(job, [py, str(add / "1_estrai_mani.py"), str(video),
                                             "-o", str(mani)])
                if code != 0 or not mani.is_file():
                    _log(job, f"[corso] pezzo '{stem}': dita non riconosciute; il dataset si fa lo "
                              f"stesso, ma senza filtro mani")
            if not mani.is_file():
                mani = None

            # 3) dataset del pezzo (ritagli dei tasti + etichetta dal MIDI). Il ritardo e' quello
            # scelto a mano per QUESTO pezzo, se c'e'; altrimenti quello globale (di solito auto).
            rit_pezzo = allineamenti.get(stem) or str(p.get("ritardo") or "auto")
            job["meta"]["fase"] = f"[{k}/{len(coppie)}] {stem}: dataset (ritardo MIDI {rit_pezzo})"
            npz = fuori / "dataset" / f"{stem}.npz"
            cmd = [py, str(add / "2_costruisci_dataset.py"), "--video", str(video),
                   "--griglia", str(griglia), "--midi", str(midi), "--out", str(npz),
                   "--raggio", str(raggio), "--ritardo", str(rit_pezzo), "--disegna", "6"]
            if p.get("p_neg"):
                cmd += ["--p-neg", str(p["p_neg"])]
            if mani is not None:
                cmd += ["--mani", str(mani)]
            code, righe = _corso_passo(job, cmd)
            if code != 0 or not npz.is_file():
                _log(job, f"[corso] pezzo '{stem}': dataset non costruito (codice {code}): "
                          f"salto il pezzo")
                continue
            testo = " | ".join(righe)
            m = _RX_DATASET.search(testo)
            if m:
                c["campioni"], c["premuti"] = int(m.group(1)), int(m.group(2))
                job["meta"]["campioni"] = job["meta"].get("campioni", 0) + int(m.group(1))
                job["meta"]["premuti"] = job["meta"].get("premuti", 0) + int(m.group(2))
            # il ritardo e il raggio VERI (scritti dal costruttore nel log) finiscono nel
            # riepilogo: cosi' si vede pezzo per pezzo cos'e' stato applicato davvero
            for rx, chiave in ((_RX_RITARDO, "ritardi"), (_RX_RAGGIO, "raggi")):
                m2 = rx.search(testo)
                if m2:
                    job["meta"].setdefault(chiave, {})[stem] = m2.group(1)
            m2 = _RX_RIT_AUTO.search(testo)
            if m2:
                job["meta"].setdefault("ritardi_auto", {})[stem] = {"s": m2.group(1),
                                                                   "correlazione": m2.group(2)}
            usato = (job["meta"].get("ritardi") or {}).get(stem, str(rit_pezzo))
            _log(job, f"[corso] '{stem}': etichette MIDI spostate di {usato} s "
                      f"({'scelto a mano' if stem in allineamenti else 'stimato da auto'})")
            pezzi_ok.append(stem)

        if not pezzi_ok:
            raise RuntimeError("nessun pezzo ha prodotto un dataset: controlla i video, i MIDI e "
                               "che la tastiera sia inquadrata")
        if len(pezzi_ok) == 1:
            _log(job, "[corso] attenzione: un solo pezzo. Non c'e' nessun video mai visto su cui "
                      "misurare, quindi il modello si allena su tutto e il numero di validazione "
                      "non esiste. Con 3-4 pezzi il risultato si puo' giudicare.")

        # 3b) se si e' chiesto solo il controllo dell'allineamento, ci si ferma qui: il modello
        # non si addestra. Si guardano le immagini, si sistemano gli scostamenti e si riparte.
        if str(p.get("prepara") or "") not in ("", "0", "false", "off", "False"):
            job["meta"]["prepara"] = True
            job["meta"]["fase"] = "pronto: controlla l'allineamento, poi premi Addestra"
            _log(job, "[corso] preparazione finita: NON ho addestrato. Apri le immagini di "
                      "controllo qui sotto: i tasti che il MIDI dice premuti sono in rosso e "
                      "devono stare sotto le dita.")
            _log(job, "[corso] se per un pezzo sono spostati, scrivi il suo scostamento nel campo "
                      "accanto al pezzo (secondi, positivo = il video e' in ritardo sul MIDI, "
                      "cioe' le note arrivano prima di quello che si vede) e ripremi Controlla. "
                      "Quando va bene premi Addestra: griglia e dita restano quelle, si rifa' "
                      "solo il dataset (un minuto, non un'ora).")
            job["stato"] = "fatto"
            return

        # 4) addestramento: una sola volta, su tutti i dataset
        job["meta"]["fase"] = "addestramento del modello"
        job["meta"]["progresso"] = 90.0
        modello = fuori / "modello.pt"
        cmd = [py, str(add / "3_addestra.py"), "--dati", str(fuori / "dataset"),
               "--epoche", str(p.get("epoche") or "15"), "-o", str(modello)]
        try:                                  # il raggio vero e' scritto nei dataset (auto): lo passa
            cmd += ["--raggio", str(float(raggio))]        # a 3_addestra solo se e' un numero
        except ValueError:
            pass
        if p.get("val"):
            cmd += ["--val", *[s.strip() for s in str(p["val"]).split(",") if s.strip()]]
        code, righe = _corso_passo(job, cmd)
        if code != 0 or not modello.is_file():
            raise RuntimeError(f"l'addestramento e' uscito con codice {code}")
        for riga in righe:
            m = _RX_EPOCA.match(riga)
            if m:
                job["meta"]["epoca"] = int(m.group(1))
        f1 = [float(m.group(1)) for m in (_RX_F1.search(r) for r in righe) if m]
        f1n = [float(m.group(1)) for m in (_RX_F1_NOTE_TRAIN.search(r) for r in righe) if m]
        job["meta"]["f1_patch"] = max(f1) if f1 else None
        job["meta"]["f1"] = max(f1n) if f1n else job["meta"]["f1_patch"]   # sulle NOTE, non sulle patch

        # 4b) la misura che conta: F1 sulle NOTE dei brani tenuti fuori, calcolato come lo vedrebbe
        # chi usa il modello (inferenza completa sul video, non solo sulle patch campionate)
        val_stems = []
        for riga in righe:
            m = _RX_VAL.match(riga)
            if m:
                val_stems = [x.split(" (")[0].strip() for x in m.group(1).split(",") if x.strip()]
        if val_stems:
            job["meta"]["fase"] = "misura sulle note dei brani mai visti"
            job["meta"]["progresso"] = 94.0
            _log(job, "[corso] misura finale sulle NOTE dei brani tenuti fuori: "
                      + ", ".join(val_stems))
            punteggi = []
            for s in val_stems:
                c = next((x for x in coppie if x["stem"] == s), None)
                griglia_s = fuori / "griglia" / s / "griglia.json"
                if c is None or not griglia_s.is_file():
                    continue
                cmd = [py, str(add / "5_valuta.py"), "--modello", str(modello),
                       "--video", str(d / c["video"]), "--griglia", str(griglia_s),
                       "--midi", str(d / c["midi"])]
                if (fuori / "mani" / f"{s}.json").is_file():
                    cmd += ["--mani", str(fuori / "mani" / f"{s}.json")]
                code, righe_v = _corso_passo(job, cmd)
                if code != 0:
                    _log(job, f"[corso] la misura su '{s}' non e' riuscita (il modello c'e' comunque)")
                    continue
                m = _RX_F1NOTA.search(" | ".join(righe_v))
                if m:
                    punteggi.append(float(m.group(1)))
                    job["meta"].setdefault("f1_note_pezzi", {})[s] = float(m.group(1))
            if punteggi:
                job["meta"]["f1_note"] = round(sum(punteggi) / len(punteggi), 3)
                _log(job, f"[corso] F1 sulle note sui brani mai visti: {job['meta']['f1_note']:.3f} "
                          f"(media di {len(punteggi)} brani) <- questo e' il numero da guardare")
        (fuori / "modello.json").write_text(json.dumps(
            {"campioni": job["meta"].get("campioni"), "premuti": job["meta"].get("premuti"),
             "pezzi": pezzi_ok, "epoche": p.get("epoche"), "raggio": raggio,
             "ritardo_midi_per_pezzo": job["meta"].get("ritardi"),
             "ritardo_midi_scelto_a_mano": allineamenti or None,
             "ritardo_stimato_da_auto": job["meta"].get("ritardi_auto"),
             "raggio_misurato_per_pezzo": job["meta"].get("raggi"),
             "brani_tenuti_fuori": val_stems,
             "f1_validazione": job["meta"].get("f1"),
             "f1_patch_validazione": job["meta"].get("f1_patch"),
             "f1_note_video_mai_visti": job["meta"].get("f1_note"),
             "f1_note_per_pezzo": job["meta"].get("f1_note_pezzi")}, ensure_ascii=False, indent=2),
            encoding="utf-8")

        # 5) prova: probabilita' dei tasti su un pezzo (si guardano nel visualizzatore)
        if str(p.get("inferenza", "1")) not in ("0", "false", "off", "False"):
            stem = pezzi_ok[-1]
            job["meta"]["fase"] = f"prova dell'inferenza su '{stem}'"
            job["meta"]["progresso"] = 96.0
            c = next(x for x in coppie if x["stem"] == stem)
            prob = fuori / "probabilita" / f"{stem}.json"
            cmd = [py, str(add / "4_inferenza.py"), "--video", str(d / c["video"]),
                   "--modello", str(modello),
                   "--griglia", str(fuori / "griglia" / stem / "griglia.json"),
                   "-o", str(prob)]
            if (fuori / "mani" / f"{stem}.json").is_file():
                cmd += ["--mani", str(fuori / "mani" / f"{stem}.json")]
            code, _ = _corso_passo(job, cmd)
            if code != 0:
                _log(job, "[corso] la prova dell'inferenza non e' riuscita (il modello c'e' "
                          "comunque)")
            else:
                job["meta"]["prova_pezzo"] = stem
                job["meta"]["prova"] = f"probabilita/{stem}.json"
        job["meta"]["fase"] = "fatto"
        job["stato"] = "fatto"
    except _Annullato:
        job["stato"] = "annullato"
        _log(job, "[corso] annullato")
    except Exception as exc:                                   # noqa: BLE001
        job["stato"], job["errore"] = "errore", f"{type(exc).__name__}: {exc}"
        _log(job, f"[corso] errore: {type(exc).__name__}: {exc}")
    finally:
        job["meta"]["progresso"] = 100.0
        job["finito_il"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            job["risultati"] = sorted(str(x.relative_to(fuori)) for x in fuori.rglob("*")
                                      if x.is_file())
            # le immagini di controllo dell'allineamento, raggruppate per pezzo: la pagina le
            # mostra sotto il riepilogo, cosi' si vede se un pezzo ha le etichette spostate
            for c in job["meta"].get("coppie") or []:
                s = c["stem"]
                img = [r for r in job["risultati"]
                       if r.startswith("dataset/allineamento/")
                       and Path(r).name.startswith(s + "_f")]
                if img:
                    job["meta"].setdefault("allineamento_immagini", {})[s] = img
            (fuori / "log.txt").write_text("\n".join(r["s"] for r in job.get("log", [])),
                                           encoding="utf-8")
        except OSError:
            pass
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
        "prospettica": bool((BASE / "motore_prospettica.py").is_file()
                            and (BASE / "griglia_prospettica.py").is_file()),
        "addestra": {
            "script": all((BASE / "addestra_tasti" / s).is_file()
                          for s in ("1_estrai_mani.py", "2_costruisci_dataset.py",
                                    "3_addestra.py", "4_inferenza.py")),
            "mediapipe": _mediapipe_ok(),
            "dataset": len(list((BASE / "addestra_tasti" / "dataset").glob("*.npz"))),
            "modello": (BASE / "addestra_tasti" / "modello.pt").is_file(),
        },
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
                       "tipo": j.get("tipo", "video"),
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

    motore = (request.form.get("motore") or "prospettica").strip().lower()
    if motore == "ppan":
        info = ppan_info(request.form.get("ppan_dir"))
        if not info["pronto"]:
            return jsonify({"errore": f"motore PPAN non pronto in {info['dir']}: servono "
                                      f"ppan_infer.py, weights/pytorch_model.bin, "
                                      f"weights/config.json e ppan_bridge.py"}), 409
    elif motore == "calibrato":
        quad = (request.form.get("ppan_quad") or request.form.get("quad") or "").strip()
        if not quad:                                    # senza angoli serve YOLO
            info_pesi = pesi_info(BASE / "weights" / "yolov8l-oiv7.pt")
            if not info_pesi["valido"]:
                return jsonify({"errore": "motore calibrato senza i 4 angoli: servono i pesi "
                                          "weights/yolov8l-oiv7.pt (assenti o troncati). "
                                          "Segna i 4 angoli sul video oppure riscarica i pesi."}), 409
    elif motore == "prospettica":
        # la griglia e' stimata dal profilo dei tasti: nessun modello esterno richiesto
        if not (BASE / "motore_prospettica.py").is_file() or not (BASE / "griglia_prospettica.py").is_file():
            return jsonify({"errore": "motore prospettica non disponibile: mancano "
                                      "motore_prospettica.py / griglia_prospettica.py"}), 409
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
    # "elimina le esecuzioni precedenti" e' acceso di default: si libera il disco prima di partire
    elimina_tutto = request.form.get("elimina_precedenti") not in ("0", "false", "off")
    azzerate, eliminate = _sgombera_precedenti(job_id, elimina_tutto)
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
    if eliminate:
        _log(job, "[web] esecuzioni precedenti eliminate: %d (%s)"
             % (len(eliminate), ", ".join(sorted(eliminate)[:4]) +
                (" ..." if len(eliminate) > 4 else "")))
    if azzerate:
        _log(job, "[web] nuovo video: azzerate le sagome di %d esecuzioni precedenti" % len(azzerate))
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
        "tipo": job.get("tipo", "video"),
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


@app.post("/api/jobs/elimina")
def elimina_tutte():
    """Cancella le esecuzioni concluse: libera il disco senza aspettare un nuovo job."""
    azzerate, eliminate = _sgombera_precedenti(None, True)
    return jsonify({"esito": "eliminate %d esecuzioni" % len(eliminate),
                    "eliminate": eliminate, "azzerate": azzerate})


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


@app.get("/api/job/<job_id>/file/<path:nome>")
def file_job(job_id, nome):
    """Un file prodotto dal job (`out/nome`, oppure dovunque dentro la cartella del job)."""
    try:
        d = _percorso_job(job_id).resolve()
        job = _job(job_id)
    except KeyError:
        return jsonify({"errore": "job inesistente"}), 404
    fuori = Path(job.get("out_dir") or (d / "out")).resolve()
    for base in (fuori, d):
        f = (base / nome).resolve()
        # dentro la cartella del job, oppure nella sua cartella di uscita: con "riusa" (corso
        # ripreso dopo il controllo dell'allineamento) l'uscita sta nella cartella del corso
        # preparato, che e' un'altra cartella rispetto a questa
        if f.is_file() and (str(f).startswith(str(d) + os.sep)
                            or str(f).startswith(str(fuori) + os.sep)):
            return send_file(f, mimetype=FILE_SERVIZIO.get(f.name), conditional=True)
    return jsonify({"errore": f"{nome} non presente"}), 404


@app.get("/api/job/<job_id>/sagome.json")
def sagome_job(job_id):
    try:
        f = _percorso_job(job_id) / "sagome.json"
    except KeyError:
        return jsonify({"errore": "job inesistente"}), 404
    if not f.is_file():
        return jsonify({"errore": "sagome non presenti (motore senza sagome per nota, o azzerate "
                                  "perche' e' stato caricato un altro video)"}), 404
    return send_file(f, mimetype="application/json", conditional=True)


@app.get("/api/job/<job_id>/clip/<int:nota>")
@app.get("/api/job/<job_id>/clip/<int:nota>/<int:frame>")
def clip_job(job_id, nota, frame=None):
    """Clip della nota (mp4) oppure, se le clip sono JPEG, il frame richiesto."""
    try:
        base = _percorso_job(job_id) / "sagome"
    except KeyError:
        return jsonify({"errore": "job inesistente"}), 404
    if not 21 <= nota <= 108:
        return jsonify({"errore": "nota fuori da 21-108"}), 404
    mp4 = base / f"{nota:03d}.mp4"
    if frame is None and mp4.is_file():
        return send_file(mp4, mimetype="video/mp4", conditional=True)
    cart = base / f"{nota:03d}"
    if frame is not None and cart.is_dir():
        jpg = cart / f"{frame:06d}.jpg"
        if jpg.is_file():
            return send_file(jpg, mimetype="image/jpeg")
    return jsonify({"errore": f"nessuna clip per la nota {nota}: tasto non inquadrato in questo "
                              "video (o sagome azzerate)"}), 404


@app.post("/api/addestra")
def nuovo_addestra():
    """Crea un corso di addestramento: coppie video+MIDI (stesso nome del file)."""
    files = request.files.getlist("file")
    if not files:
        return jsonify({"errore": "nessun file caricato: servono le coppie video + MIDI"}), 400
    if spazio_libero()["libero_gb"] < 1.0:
        return jsonify({"errore": "meno di 1 GB libero su disco: libera spazio prima di procedere"}), 507
    for s in ("1_estrai_mani.py", "2_costruisci_dataset.py", "3_addestra.py"):
        if not (BASE / "addestra_tasti" / s).is_file():
            return jsonify({"errore": f"manca addestra_tasti/{s}"}), 409

    coppie: dict[str, dict[str, str]] = {}
    for f in files:
        nome = Path(f.filename or "").name
        ext = Path(nome).suffix.lower()
        if ext in ESTENSIONI:
            tipo = "video"
        elif ext in EST_MIDI:
            tipo = "midi"
        else:
            return jsonify({"errore": f"'{nome}': usa un video (mp4, mov…) o un MIDI (.mid)"}), 400
        coppie.setdefault(Path(nome).stem, {})[tipo] = nome
    incompleti = sorted(s for s, v in coppie.items() if not {"video", "midi"}.issubset(v))
    if incompleti:
        return jsonify({"errore": "per ogni pezzo servono un video e un MIDI con lo STESSO nome "
                                  "(es. brano1.mp4 + brano1.mid). Senza coppia: "
                                  + ", ".join(incompleti)}), 400

    def numero(chiave: str, default: str, minimo: float = 0.0,
               intero: bool = False) -> str | None:
        v = (request.form.get(chiave) or "").strip().replace(",", ".")
        if not v:
            return default
        try:
            x = float(v)
        except ValueError:
            return None
        if x < minimo:
            return None
        return str(int(round(x))) if intero else str(x)

    epoche = numero("epoche", "15", 1, intero=True)
    raggio = ("auto" if (request.form.get("raggio") or "auto").strip().lower() == "auto"
              else numero("raggio", "auto", 0.1))
    pneg = numero("p_neg", "0.4", 0.0)
    prima = numero("prima_nota", "", 0, intero=True)
    for chiave, v in (("epoche", epoche), ("raggio", raggio), ("p_neg", pneg),
                      ("prima_nota", prima)):
        if v is None:
            come = " ('auto' oppure un numero di larghezze di tasto)" if chiave == "raggio" else ""
            return jsonify({"errore": f"{chiave}: valore non valido{come}"}), 400

    # Allineamento a mano, pezzo per pezzo: il campo `allinea__<nome del pezzo>` dice di quanto
    # spostare il MIDI rispetto al video per QUEL pezzo (secondi, positivo = il video e' in
    # ritardo sul MIDI). Vuoto o `auto` = lo stima il costruttore del dataset come al solito.
    allineamenti: dict[str, str] = {}
    for s in sorted(coppie):
        v = (request.form.get(f"allinea__{s}") or "").strip().replace(",", ".")
        if not v or v.lower() == "auto":
            continue
        try:
            x = float(v)
        except ValueError:
            return jsonify({"errore": f"'{s}': scostamento MIDI \"{v}\" non e' un numero. "
                                      f"Scrivi i secondi (es. 0.35 o -0.2) oppure lascia vuoto "
                                      f"per farlo stimare da solo"}), 400
        if not -10.0 <= x <= 10.0:
            return jsonify({"errore": f"'{s}': scostamento {x:+.2f} s fuori misura: si va da "
                                      f"-10 a +10 secondi"}), 400
        allineamenti[s] = str(round(x, 3))

    if request.form.get("pulisci") in ("1", "true", "on"):
        _sgombera_precedenti(None, True)          # i corsi di addestramento non si toccano
    # `riusa` = id del corso gia' preparato con "Controlla l'allineamento": si riparte dalla sua
    # cartella, quindi griglia e dita (la parte lenta) non si ricalcolano.
    riusa = (request.form.get("riusa") or "").strip()
    job_id = uuid.uuid4().hex[:16]
    d = None
    if riusa:
        try:
            if _job(riusa).get("tipo") == "addestra" and _percorso_job(riusa).is_dir():
                d = _percorso_job(riusa)
        except KeyError:
            d = None
    if d is None:
        if riusa:
            return jsonify({"errore": f"il corso {riusa} da riusare non esiste piu': ripremi "
                                      f"Controlla l'allineamento"}), 400
        d = _percorso_job(job_id)
    (d / "pezzi").mkdir(parents=True, exist_ok=True)
    (d / "out").mkdir(parents=True, exist_ok=True)
    for f in files:
        f.save(str(d / "pezzi" / Path(f.filename or "").name))
    elenco = [{"stem": s, "video": f"pezzi/{v['video']}", "midi": f"pezzi/{v['midi']}"}
              for s, v in sorted(coppie.items())]
    parametri = {"epoche": epoche, "raggio": raggio, "p_neg": pneg, "prima_nota": prima or "",
                 "ritardo": (request.form.get("ritardo") or "auto").strip() or "auto",
                 "allineamenti": allineamenti,
                 "prepara": "1" if request.form.get("prepara") in ("1", "true", "on") else "0",
                 "riusa": riusa,
                 "val": (request.form.get("val") or "").strip(),
                 "inferenza": "0" if request.form.get("inferenza") in ("0", "false", "off")
                              else "1"}
    job = {"id": job_id, "tipo": "addestra", "stato": "in_corso",
           "creato_il": time.strftime("%Y-%m-%d %H:%M:%S"),
           "video_nome": "corso: %d pezzi (%s%s)" % (
               len(elenco), ", ".join(x["stem"] for x in elenco[:3]),
               "…" if len(elenco) > 3 else ""),
           "out_dir": str(d / "out"), "in_dir": str(d), "parametri": parametri,
           "risultati": [],
           "meta": {"fase": "in coda", "coppie": elenco, "progresso": 0.0}, "log": []}
    with _LOCK:
        JOBS[job_id] = job
    _salva(job)
    # Il controllo dell'allineamento si ripete piu' volte (si aggiusta un numero e si riprova):
    # ogni volta i video verrebbero ricopiati in una cartella nuova. Con `scarta` si butta via il
    # controllo precedente. Un modello gia' addestrato non si cancella mai.
    scarta = (request.form.get("scarta") or "").strip()
    if scarta and scarta not in (job_id, riusa, ""):
        try:
            vecchio = _job(scarta)
            if (vecchio.get("tipo") == "addestra"
                    and not (Path(vecchio["out_dir"]) / "modello.pt").is_file()):
                shutil.rmtree(_percorso_job(scarta), ignore_errors=True)
                with _LOCK:
                    JOBS.pop(scarta, None)
                _log(job, f"[corso] buttato via il controllo precedente {scarta} sugli stessi "
                          f"video: tiene libero il disco")
        except (KeyError, OSError):
            pass
    threading.Thread(target=_esegui_addestra, args=(job_id,), daemon=True).start()
    return jsonify({"id": job_id, "pezzi": [x["stem"] for x in elenco]})


@app.get("/api/modelli")
def modelli():
    """I modelli addestrati dai corsi, con la misura di validazione (se c'e')."""
    out = []
    for f in sorted(RUNS.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if j.get("tipo") != "addestra" or (j.get("meta") or {}).get("prepara"):
            continue                  # i "controlla l'allineamento" non sono modelli
        fuori = Path(j.get("out_dir") or "")
        modello = fuori / "modello.pt"
        if not modello.is_file():
            continue
        meta = j.get("meta") or {}
        out.append({"id": j.get("id"), "pezzi": [c.get("stem") for c in (meta.get("coppie") or [])],
                    "campioni": meta.get("campioni"), "premuti": meta.get("premuti"),
                    "f1": meta.get("f1"), "f1_note": meta.get("f1_note"), "epoca": meta.get("epoca"),
                    "creato_il": j.get("creato_il"), "stato": j.get("stato"),
                    "epoche": (j.get("parametri") or {}).get("epoche"),
                    "raggio": (j.get("parametri") or {}).get("raggio"),
                    "mb": round(modello.stat().st_size / 1024 ** 2, 2),
                    "prova": meta.get("prova"), "prova_pezzo": meta.get("prova_pezzo"),
                    "modello": f"/api/job/{j.get('id')}/file/modello.pt"})
    return jsonify(out)


@app.get("/api/file")
def materiale():
    """Catalogo del materiale del progetto: documenti, pacchetti, prove, video, script."""
    gruppi, visti = [], set()
    for titolo, pattern in MATERIALE:
        voci = []
        for pat in pattern:
            for f in sorted(BASE.glob(pat)):
                if not f.is_file() or f.name.startswith("."):
                    continue
                rel = f.relative_to(BASE).as_posix()
                if rel in visti or rel.startswith(("web_runs/", "__pycache__/")) or ".venv" in rel:
                    continue
                visti.add(rel)
                try:
                    mb = round(f.stat().st_size / 1024 ** 2, 2)
                except OSError:
                    mb = 0.0
                voci.append({"nome": f.name, "percorso": rel, "mb": mb,
                             "tipo": f.suffix.lower().lstrip("."), "url": "/file/" + rel})
        if voci:
            gruppi.append({"titolo": titolo, "voci": voci})
    return jsonify({"base": str(BASE), "gruppi": gruppi})


@app.get("/file/<path:rel>")
def file_progetto(rel):
    """Serve un file del progetto (documenti, ZIP, video, immagini) senza uscire da BASE."""
    base = BASE.resolve()
    f = (BASE / rel).resolve()
    if not (f.is_file() and str(f).startswith(str(base) + os.sep)):
        return jsonify({"errore": "file non disponibile"}), 404
    return send_file(f, as_attachment=request.args.get("scarica") == "1", conditional=True)


# ------------------------------------------------- passo 0: prepara il video (tastiera)
def _percorso_prepara(pid: str) -> Path:
    return PREPARA_DIR / pid


def _stato_prepara(pid: str) -> dict:
    """Lo stato del passo 0: in memoria (se il server gira) o dal file su disco."""
    try:
        return PREPARA[pid]
    except KeyError:
        pass
    f = _percorso_prepara(pid) / "prepara_stato.json"
    if f.is_file():
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            # Se lo stato arriva dal disco l'elaborazione NON è in corso in questo processo: un
            # «in_corso» scritto su disco è rimasto orfano (server riavviato, finestra chiusa,
            # processo fermato) e la pagina lo mostrerebbe in corsa per sempre. Stessa regola dei
            # lavori (vedi _leggi_job).
            if p.get("stato") == "in_corso":
                p["stato"] = "errore"
                p["errore"] = p.get("errore") or "server riavviato durante l'elaborazione"
                p["fase"] = "interrotto: il server è stato riavviato, riavvia il passo 0"
            PREPARA[pid] = p
            _salva_prepara(pid)
            return PREPARA[pid]
        except (OSError, json.JSONDecodeError):
            pass
    raise KeyError(pid)


def _salva_prepara(pid: str) -> None:
    d = _percorso_prepara(pid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "prepara_stato.json").write_text(json.dumps(PREPARA[pid], ensure_ascii=False, indent=1),
                                          encoding="utf-8")


def _log_prepara(pid: str, riga: str) -> None:
    p = _stato_prepara(pid)
    p.setdefault("log", []).append(riga)
    del p["log"][:-MAX_LOG]
    print(f"[prepara {pid}] {riga}", flush=True)
    _salva_prepara(pid)


def _esegui_prepara_cmd(pid: str, cmd: list[str]) -> int:
    """Esegue un passo (scarico o ritaglio) e ne porta l'uscita nel log della pagina.

    `PYTHONUNBUFFERED=1` non è un dettaglio: i passi sono python e quando scrivono su una pipe il
    loro stdout è a blocchi, quindi le righe arrivavano alla pagina tutte insieme alla FINE del
    passo. Il passo 0 dura minuti (l'inseguimento della griglia ~55 ms a fotogramma, misurato) e
    senza le righe che arrivano mentre lavora la pagina sembrava bloccata: adesso si vedono
    scorrere anche le righe di avanzamento (`[insegui] 900/1800 ...`).
    """
    _log_prepara(pid, "$ " + " ".join(cmd))
    # `stdin=DEVNULL` non è un dettaglio: senza, il figlio eredita lo stdin del server e ffmpeg --
    # che di suo legge stdin per il tasto «q» -- appena è in un gruppo di processi in BACKGROUND
    # rispetto al terminale del server viene FERMATO dal kernel con SIGTTIN (`ps` lo mostra in
    # stato «T», CPU 0%, e non scarica niente: sembra bloccato per sempre). Con /dev/null su stdin
    # ffmpeg non tocca mai il terminale. Le altre `Popen` del server lo facevano già; qui mancava.
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            bufsize=1, stdin=subprocess.DEVNULL,
                            env=dict(os.environ, PYTHONUNBUFFERED="1"))
    PROC[pid] = proc
    try:
        for riga in proc.stdout or []:
            riga = riga.rstrip()
            if riga:
                _log_prepara(pid, riga)
        return proc.wait()
    finally:
        PROC.pop(pid, None)


def _preparati_per_esempio() -> dict[str, dict]:
    """Gli esempi già preparati, per non rifare lo stesso lavoro: {record_time: {id, stato...}}."""
    fuori: dict[str, dict] = {}
    if not PREPARA_DIR.is_dir():
        return fuori
    for cart in sorted(PREPARA_DIR.iterdir(), key=lambda q: q.stat().st_mtime, reverse=True):
        f = cart / "prepara_stato.json"
        if not f.is_file():
            continue
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rec = s.get("esempio") or s.get("pezzo")
        if rec and rec not in fuori:
            fuori[rec] = {"id": s.get("id") or cart.name, "stato": s.get("stato"),
                          "verdetto": (s.get("numeri") or {}).get("verdetto"),
                          "quando": s.get("creato_il")}
    return fuori


def _modelli_per_pezzo() -> dict[str, list[dict]]:
    """Tutti i pezzi usati dai modelli (uno per file): si legge una volta sola, non 107 volte."""
    indice: dict[str, list[dict]] = {}
    for f in sorted(RUNS.glob("*/out/modello.json"), key=lambda q: q.stat().st_mtime, reverse=True):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        voce = {"id": f.parent.parent.name, "pezzi": [str(x) for x in (m.get("pezzi") or [])],
                "f1_note": m.get("f1_note_video_mai_visti")}
        for pezzo in voce["pezzi"]:
            indice.setdefault(pezzo, []).append(voce)
    return indice


def _modelli_con_pezzo(nome: str, indice: dict[str, list[dict]]) -> list[dict]:
    """I modelli già addestrati su questo pezzo: la pagina lo dice invece di addestrare a vuoto."""
    visti, fuori = set(), []
    for pezzo, mods in indice.items():
        if nome in pezzo:
            for m in mods:
                if m["id"] not in visti:
                    visti.add(m["id"])
                    fuori.append(m)
    return fuori


_ESEMPI_CACHE: dict = {"quando": 0.0, "voci": [], "errore": None}


def _elenco_esempi(aggiorna: bool = False) -> list[dict]:
    """Le registrazioni del dataset numerate (1..107), con l'indicazione di cosa è già stato fatto."""
    ora = time.time()
    if aggiorna or not _ESEMPI_CACHE["voci"] or ora - float(_ESEMPI_CACHE["quando"]) > 3600:
        cmd = [python_pipeline(), str(BASE / ESEMPI_SCRIPT), "--elenco", "--json"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                               stdin=subprocess.DEVNULL)
            voci = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
            _ESEMPI_CACHE["errore"] = None if voci else (r.stderr or "").strip()[-500:]
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            voci, _ESEMPI_CACHE["errore"] = [], f"{type(e).__name__}: {e}"
        if voci:
            _ESEMPI_CACHE["quando"] = ora
            _ESEMPI_CACHE["voci"] = voci
    voci = [dict(v) for v in _ESEMPI_CACHE["voci"]]
    preparati = _preparati_per_esempio()
    indice = _modelli_per_pezzo()
    for v in voci:
        v["preparato"] = preparati.get(v["rec"])
        v["modelli"] = _modelli_con_pezzo(v["rec"], indice)
    return voci, _ESEMPI_CACHE["errore"]


def _pezzi_cantiere() -> list[dict]:
    """I pezzi già preparati e messi da parte per l'addestramento (video + MIDI, stesso nome)."""
    if not CANTIERE_DIR.is_dir():
        return []
    fuori = []
    visti = set()
    for v in sorted(CANTIERE_DIR.glob("*.mp4")):
        midi = v.with_suffix(".mid")
        if not midi.is_file():
            midi = v.with_suffix(".midi")
        fuori.append({"nome": v.stem, "video": v.name, "midi": midi.name if midi.is_file() else None,
                      "mb": round(v.stat().st_size / 1024 ** 2, 1),
                      "ok": midi.is_file()})
    return fuori


def _esegui_prepara(pid: str) -> None:
    """Prende il pezzo (esempio del dataset o file caricati) e lo ritaglia sulla tastiera.

    Due passi, ognuno un processo a sé: (1) il pezzo + il MIDI vero, (2) `0_prepara.py`, che
    trova la tastiera e scrive il video preparato. Alla fine i numeri del verdetto finiscono
    nello stato, insieme ai file da guardare (video originale, video preparato, il controllo
    fermo e il controllo in movimento).
    """
    p = _stato_prepara(pid)
    d = _percorso_prepara(pid)
    py = python_pipeline()
    try:
        if p.get("sorgente") == "esempio":
            p["fase"] = "prendo il pezzo dal dataset"
            _salva_prepara(pid)
            cmd = [py, str(BASE / ESEMPI_SCRIPT)]
            cmd += ["--caso"] if p.get("caso") else ["--numero", str(p.get("numero") or 1)]
            cmd += ["--durata", str(p.get("durata") or 60), "--out", str(d)]
            if float(p.get("inizio") or 0) > 0:
                cmd += ["--inizio", str(p["inizio"])]
            code = _esegui_prepara_cmd(pid, cmd)
            if code != 0:
                raise RuntimeError(f"lo scarico dell'esempio è uscito con codice {code}")
            video = sorted(d.glob("*.mp4"))
            if len(video) != 1:
                raise RuntimeError(f"mi aspettavo un solo video in {d}, ne trovo {len(video)}")
            video = video[0]
            p["esempio"] = video.stem
        else:
            video = next(iter(sorted(d.glob("*.mp4"))), None)
            if video is None:
                raise RuntimeError("non trovo il video caricato")
        stem = video.stem
        p["pezzo"] = stem
        midi: Path | None = video.with_suffix(".mid")
        if not midi.is_file():
            altri = sorted(d.glob("*.mid")) + sorted(d.glob("*.midi"))
            if altri:
                midi = altri[0]
            elif p.get("forza"):
                # niente verità da confrontare, ma il video preparato e la griglia si guardano lo stesso
                midi = None
                p["senza_midi"] = True
                _log_prepara(pid, "[prepara] in questa cartella non c'è nessun MIDI: vado avanti lo "
                                  "stesso e ti mostro il video preparato con la griglia trovata "
                                  "(senza il MIDI vero di questa esecuzione non si può addestrare)")
            else:
                raise RuntimeError("manca il MIDI di questo pezzo: senza il MIDI vero del brano "
                                   "il corso non ha una verità su cui misurare (spunta «procedi lo "
                                   "stesso» per vedere comunque la griglia)")
        p["fase"] = "cerco la tastiera e ritaglio"
        _salva_prepara(pid)
        nome = f"{stem}_preparato"
        cmd = [py, str(BASE / "addestra_tasti" / "0_prepara.py"), "--video", str(video),
               "--out", str(d), "--nome", nome]
        if p.get("rettangolo"):
            cmd += ["--rettangolo", str(p["rettangolo"])]
        code = _esegui_prepara_cmd(pid, cmd)
        dati: dict = {}
        f_json = d / f"{nome}.json"
        if f_json.is_file():
            try:
                dati = json.loads(f_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                dati = {}
        p["numeri"] = {k: dati.get(k) for k in ("passo", "passo_profilo", "scarto_dal_profilo_percento",
                                                "inlier", "evidenza", "tasti_nel_frame", "tasti_fuori",
                                                "tasti_fuori_dalla_tastiera", "neri_ok", "neri_coperti",
                                                "neri_mancanti", "bordo_tastiera", "estremi", "passo_medio",
                                                "verdetto", "perche", "rettangolo", "metodo",
                                                "banda_neri", "ritaglio", "candidati_provati",
                                                "tasti_misurati", "lw_fronte",
                                                "inseguimento", "ritaglio_video")}
        p["file"] = {"origine": video.name, "preparato": f"{nome}.mp4",
                     "controllo": f"{nome}_controllo.jpg", "json": f"{nome}.json"}
        if midi is not None:
            p["file"]["midi"] = midi.name
        # Il controllo in movimento (0_prepara.py lo scrive anche inseguendo la griglia: solo il
        # vecchio --traccia, che sposta il ritaglio col template matching, lo salta): la pagina lo
        # mostra accanto all'immagine, e se non c'è resta solo l'immagine.
        griglia = Path(str(dati.get("griglia_video") or f"{nome}_griglia.mp4")).name
        if (d / griglia).is_file():
            p["file"]["griglia"] = griglia
        if midi is not None and (d / f"{nome}.mp4").is_file():
            # la coppia che il corso si aspetta: video e MIDI con lo STESSO nome
            shutil.copy2(midi, d / f"{nome}{midi.suffix}")
            p["file"]["midi_preparato"] = f"{nome}{midi.suffix}"
        verdetto = str(dati.get("verdetto") or "").lower()
        if code != 0 or verdetto == "rifiuto":
            p["stato"] = "rifiuto"
            p["errore"] = dati.get("perche") or f"0_prepara.py è uscito con codice {code}"
            p["fase"] = "rifiutato: guarda il controllo e prova col rettangolo a mano"
        else:
            p["stato"] = "fatto"
            coda = " (verdetto incerto: guarda il controllo)" if verdetto == "incerto" else ""
            if p.get("senza_midi"):
                coda += " · senza MIDI: la griglia si guarda, non si addestra"
            p["fase"] = "pronto" + coda
            n = p["numeri"]
            _log_prepara(pid, "[prepara] pronto: %s (passo %s px, %s inlier, plausibilità %s)"
                         % (p["file"]["preparato"], n.get("passo"), n.get("inlier"), n.get("evidenza")))
    except Exception as exc:                      # noqa: BLE001
        p["stato"] = "errore"
        p["errore"] = f"{type(exc).__name__}: {exc}"
        _log_prepara(pid, f"[prepara] errore: {p['errore']}")
    finally:
        if p.get("stato") == "in_corso":
            p["stato"] = "errore"
            p["errore"] = p.get("errore") or "il passo 0 si è fermato"
        _salva_prepara(pid)


def _crea_corso(pezzi: list[tuple[str, Path, Path]], parametri: dict) -> str:
    """Crea un corso coi pezzi già preparati e avvia l'addestramento. Ritorna l'id del corso.

    Non passa da /api/addestra perché quella rotta lavora su file CARICATI (li salva lei e
    gestisce il «riusa»): qui video e MIDI sono già su disco e vanno solo copiati nella cartella
    dei pezzi del corso. Da qui in poi è tutto il corso normale: griglia, dita, dataset,
    addestramento, misura sui brani mai visti e (se richiesto) l'inferenza di prova.
    """
    job_id = uuid.uuid4().hex[:16]
    d = _percorso_job(job_id)
    (d / "pezzi").mkdir(parents=True, exist_ok=True)
    (d / "out").mkdir(parents=True, exist_ok=True)
    elenco = []
    for nome, video, midi in pezzi:
        shutil.copy2(video, d / "pezzi" / f"{nome}.mp4")
        shutil.copy2(midi, d / "pezzi" / f"{nome}{midi.suffix}")
        elenco.append({"stem": nome, "video": f"pezzi/{nome}.mp4",
                       "midi": f"pezzi/{nome}{midi.suffix}"})
    job = {"id": job_id, "tipo": "addestra", "stato": "in_corso",
           "creato_il": time.strftime("%Y-%m-%d %H:%M:%S"),
           "video_nome": "corso: %d pezzi (%s)" % (len(elenco), ", ".join(x["stem"] for x in elenco)),
           "out_dir": str(d / "out"), "in_dir": str(d), "parametri": parametri,
           "risultati": [], "meta": {"fase": "in coda", "coppie": elenco, "progresso": 0.0}, "log": []}
    with _LOCK:
        JOBS[job_id] = job
    _salva(job)
    threading.Thread(target=_esegui_addestra, args=(job_id,), daemon=True).start()
    return job_id


@app.get("/prepara")
def pagina_prepara():
    """Il passo 0: scegli un esempio del dataset o i tuoi file, guarda l'anteprima, decidi."""
    return send_from_directory(BASE / "addestra_tasti", "prepara_video.html")


@app.get("/api/esempi")
def api_esempi():
    """L'elenco numerato degli esempi del dataset: «4» = il quarto video (per data)."""
    if not (BASE / ESEMPI_SCRIPT).is_file():
        return jsonify({"esempi": [], "errore": f"manca {ESEMPI_SCRIPT}"}), 409
    try:
        voci, errore = _elenco_esempi(request.args.get("aggiorna") == "1")
    except Exception as exc:                      # noqa: BLE001
        return jsonify({"esempi": [], "errore": f"{type(exc).__name__}: {exc}"}), 502
    return jsonify({"esempi": voci, "dataset": "PianoVAM/PianoVAM_v1", "errore": errore,
                    "spazio_libero_gb": spazio_libero()["libero_gb"]})


def _numero_form(chiave: str, default, minimo: float = 0.0):
    """Un numero dal form (virgola o punto), None se non è un numero o è sotto il minimo."""
    v = (request.form.get(chiave) or "").strip().replace(",", ".")
    if not v:
        return default
    try:
        x = float(v)
    except ValueError:
        return None
    return x if x >= minimo else None


@app.post("/api/prepara")
def nuovo_prepara():
    """Avvia il passo 0: un esempio del dataset oppure un video + MIDI caricati."""
    if spazio_libero()["libero_gb"] < 0.5:
        return jsonify({"errore": "meno di 0,5 GB libero su disco: libera spazio prima di procedere"}), 507
    for nome in ("0_prepara.py", "7_esempio_pianovam.py"):
        if not (BASE / "addestra_tasti" / nome).is_file():
            return jsonify({"errore": f"manca addestra_tasti/{nome}"}), 409
    sorgente = (request.form.get("sorgente") or "esempio").strip().lower()
    if sorgente not in ("esempio", "file"):
        return jsonify({"errore": "sorgente: scegli «esempio» (dal dataset) o «file» (i tuoi)"}), 400
    durata = _numero_form("durata", 60.0, 1.0)
    inizio = _numero_form("inizio", 0.0, 0.0)
    if durata is None or inizio is None:
        return jsonify({"errore": "durata/inizio: scrivi un numero di secondi"}), 400
    caso = request.form.get("caso") in ("1", "true", "on")
    # «procedi lo stesso»: se il MIDI manca o i nomi non combaciano si prepara il video lo stesso,
    # così la griglia trovata si guarda comunque (senza la verità non si addestra, ma si vede)
    forza = request.form.get("forza") in ("1", "true", "on")
    numero = _numero_form("numero", 1.0, 1.0)
    if sorgente == "esempio" and not caso and numero is None:
        return jsonify({"errore": "numero: scrivi quale esempio (es. 4) oppure spunta «a caso»"}), 400
    pid = uuid.uuid4().hex[:16]
    d = _percorso_prepara(pid)
    d.mkdir(parents=True, exist_ok=True)
    caricati = 0
    if sorgente == "file":
        files = request.files.getlist("file")
        if not files:
            shutil.rmtree(d, ignore_errors=True)
            return jsonify({"errore": "nessun file caricato: servono il video e il MIDI dello stesso "
                                      "brano (es. brano1.mp4 + brano1.mid)"}), 400
        coppie: dict[str, dict] = {}
        for f in files:
            nome_file = Path(f.filename or "").name
            ext = Path(nome_file).suffix.lower()
            if ext in ESTENSIONI:
                coppie.setdefault(Path(nome_file).stem, {})["video"] = f
            elif ext in EST_MIDI:
                coppie.setdefault(Path(nome_file).stem, {})["midi"] = f
            else:
                shutil.rmtree(d, ignore_errors=True)
                return jsonify({"errore": f"'{nome_file}': usa un video (mp4, mov…) o un MIDI (.mid)"}), 400
        scelte = sorted(coppie.items(), key=lambda x: x[0].lower())
        if len(scelte) != 1:                   # più video, oppure video e MIDI con nomi diversi
            if not forza:
                shutil.rmtree(d, ignore_errors=True)
                return jsonify({"errore": "prepara UN pezzo per volta: un video e un MIDI con lo "
                                          "stesso nome", "forzabile": True}), 400
            # con «procedi lo stesso» prendo la prima coppia che ha il video (meglio se completa)
            intere = [x for x in scelte if {"video", "midi"}.issubset(x[1])]
            col_video = [x for x in scelte if "video" in x[1]]
            scelte = (intere or col_video)[:1]
        if not scelte or "video" not in scelte[0][1]:
            shutil.rmtree(d, ignore_errors=True)
            return jsonify({"errore": "tra i file caricati non c'è nessun video: col solo MIDI non "
                                      "c'è niente da preparare (serve il video del brano)"}), 400
        stem, coppia = scelte[0]
        if not {"video", "midi"}.issubset(coppia) and not forza:
            shutil.rmtree(d, ignore_errors=True)
            return jsonify({"errore": f"'{stem}': servono il video E il MIDI con lo stesso nome "
                                      f"(il MIDI vero di quella esecuzione, non le previsioni di un "
                                      f"motore di trascrizione)", "forzabile": True}), 400
        for f in coppia.values():
            f.save(str(d / Path(f.filename or "").name))
            caricati += 1
    p = {"id": pid, "stato": "in_corso", "creato_il": time.strftime("%Y-%m-%d %H:%M:%S"),
         "sorgente": sorgente, "numero": int(numero) if numero else None, "caso": caso,
         "durata": durata, "inizio": inizio, "forza": forza, "senza_midi": False,
         "rettangolo": (request.form.get("rettangolo") or "").strip() or None,
         "esempio": None, "pezzo": None, "file_caricati": caricati,
         "numeri": None, "file": {}, "log": [], "fase": "in coda", "errore": None}
    PREPARA[pid] = p
    _salva_prepara(pid)
    threading.Thread(target=_esegui_prepara, args=(pid,), daemon=True).start()
    return jsonify({"id": pid, "sorgente": sorgente, "stato": "in_corso"})


@app.get("/api/prepara/<pid>")
def stato_prepara(pid):
    """Lo stato del passo 0 + i link ai file da guardare (video originale, preparato, controllo)."""
    try:
        p = _stato_prepara(pid)
    except KeyError:
        return jsonify({"errore": "passo 0 sconosciuto"}), 404
    fuori = dict(p)
    fuori["url"] = {k: f"/file/web_runs/_prepara/{pid}/{v}" for k, v in (p.get("file") or {}).items()}
    fuori["in_corso"] = p.get("stato") == "in_corso"
    return jsonify(fuori)


@app.post("/api/prepara/<pid>/elimina")
def elimina_prepara(pid):
    """Butta via la cartella del passo 0 (libera disco): se il pezzo è nel cantiere resta lì."""
    try:
        _stato_prepara(pid)
    except KeyError:
        return jsonify({"errore": "passo 0 sconosciuto"}), 404
    shutil.rmtree(_percorso_prepara(pid), ignore_errors=True)
    with _LOCK:
        PREPARA.pop(pid, None)
    return jsonify({"ok": True, "id": pid})


@app.get("/viewer")
def viewer():
    """Il visualizzatore delle probabilita' per tasto (addestra_tasti)."""
    return send_from_directory(BASE / "addestra_tasti", "sezione_tasti_probabilita.html")


@app.get("/api/cantiere")
def api_cantiere():
    """I pezzi preparati e messi da parte per l'addestramento (video + MIDI accoppiati)."""
    return jsonify({"pezzi": _pezzi_cantiere(), "spazio_libero_gb": spazio_libero()["libero_gb"]})


@app.post("/api/prepara/<pid>/cantiere")
def metti_nel_cantiere(pid):
    """Il pezzo preparato (video ritagliato + MIDI vero) va nel cantiere per l'addestramento."""
    try:
        p = _stato_prepara(pid)
    except KeyError:
        return jsonify({"errore": "passo 0 sconosciuto"}), 404
    if p.get("stato") != "fatto":
        return jsonify({"errore": f"questo pezzo non è pronto ({p.get('stato')}): prima preparalo e "
                                  f"guarda l'anteprima"}), 409
    if p.get("senza_midi"):
        return jsonify({"errore": "questo pezzo è stato preparato senza MIDI: la griglia si può "
                                  "guardare, ma per addestrare serve il MIDI vero di quella "
                                  "esecuzione (stesso nome del video)"}), 409
    files = p.get("file") or {}
    video = _percorso_prepara(pid) / str(files.get("preparato") or "")
    midi = _percorso_prepara(pid) / str(files.get("midi_preparato") or "")
    if not (video.is_file() and midi.is_file()):
        return jsonify({"errore": "i file del pezzo preparato non ci sono più: riprepara"}), 409
    nome = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(p.get("pezzo") or video.stem))
    CANTIERE_DIR.mkdir(parents=True, exist_ok=True)
    for vecchio in (CANTIERE_DIR / f"{nome}.mp4", CANTIERE_DIR / f"{nome}.mid",
                    CANTIERE_DIR / f"{nome}.midi"):
        vecchio.unlink(missing_ok=True)            # se c'era già, lo rimpiazzo
    shutil.copy2(video, CANTIERE_DIR / f"{nome}.mp4")
    shutil.copy2(midi, CANTIERE_DIR / f"{nome}{midi.suffix}")
    return jsonify({"ok": True, "pezzo": nome, "pezzi": _pezzi_cantiere()})


@app.post("/api/cantiere/svuota")
def svuota_cantiere():
    """Butta via i pezzi del cantiere (i corsi e i modelli già fatti non si toccano)."""
    shutil.rmtree(CANTIERE_DIR, ignore_errors=True)
    return jsonify({"ok": True, "pezzi": []})


@app.post("/api/cantiere/addestra")
def addestra_cantiere():
    """Addestra su tutti i pezzi del cantiere: è un corso normale, si vede nell'elenco dei lavori."""
    pezzi = _pezzi_cantiere()
    completi = [x for x in pezzi if x["ok"]]
    if not pezzi:
        return jsonify({"errore": "il cantiere è vuoto: prepara almeno un pezzo"}), 400
    if not completi:
        return jsonify({"errore": "nessun pezzo del cantiere ha il MIDI: senza la verità non si "
                                  "può addestrare né misurare niente"}), 400
    epoche = _numero_form("epoche", 15.0, 1.0)
    p_neg = _numero_form("p_neg", 0.4, 0.0)
    if epoche is None or p_neg is None:
        return jsonify({"errore": "epoche/p_neg: scrivi un numero"}), 400
    raggio = (request.form.get("raggio") or "auto").strip() or "auto"
    if raggio.lower() != "auto":
        r = _numero_form("raggio", 2.5, 0.1)
        if r is None:
            return jsonify({"errore": "raggio: «auto» oppure un numero di larghezze di tasto"}), 400
        raggio = str(r)
    if spazio_libero()["libero_gb"] < 1.0:
        return jsonify({"errore": "meno di 1 GB libero su disco: libera spazio prima di addestrare"}), 507
    parametri = {"epoche": str(int(round(epoche))), "raggio": raggio, "p_neg": str(p_neg),
                 "prima_nota": "", "ritardo": (request.form.get("ritardo") or "auto").strip() or "auto",
                 "allineamenti": {}, "prepara": "0", "riusa": "",
                 "val": (request.form.get("val") or "").strip(),
                 "inferenza": "0" if request.form.get("inferenza") in ("0", "false", "off") else "1"}
    job_id = _crea_corso([(x["nome"], CANTIERE_DIR / x["video"], CANTIERE_DIR / str(x["midi"]))
                          for x in completi], parametri)
    if request.form.get("svuota") in ("1", "true", "on"):
        shutil.rmtree(CANTIERE_DIR, ignore_errors=True)
    return jsonify({"corso": job_id, "pezzi": [x["nome"] for x in completi]})


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
    pr = ((BASE / "motore_prospettica.py").is_file()
          and (BASE / "griglia_prospettica.py").is_file())
    print(f"   motore prospettica: {'pronto' if pr else 'NON pronto'} "
          f"(motore_prospettica.py + griglia_prospettica.py)")
    ad = BASE / "addestra_tasti"
    pronto_ad = all((ad / s).is_file() for s in ("1_estrai_mani.py", "2_costruisci_dataset.py",
                                                 "3_addestra.py", "4_inferenza.py"))
    print(f"   addestramento     : {'pronto' if pronto_ad else 'NON pronto'} (addestra_tasti/)")
    print(f"   filtro mani       : {'mediapipe ok: le note lontane dalle dita si scartano' if _mediapipe_ok() else 'mediapipe NON disponibile: filtro mani spento'}")
    print(f"   Apri              : http://127.0.0.1:{PORTA}")
    app.run(host="127.0.0.1", port=PORTA, threaded=True, debug=False)
