"""Test del motore calibrato su video SINTETICI con verita' a terra (gen_test.py).
Esegui:  python3 test_sagome.py
Copre: G1 py_compile, G3 clip = n_frame, G4 MIDI, G5 (nota non premuta = 0 eventi), G6 (emesse ⊂ visibili),
G7 (ottava dichiarata). NON sostituisce la prova su un video reale."""
import os, subprocess, sys, tempfile, glob
import cv2, pretty_midi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_test import genera
import sagome as S
from motore_calibrato import RilevatoreCalibrato

QUI = os.path.dirname(os.path.abspath(__file__)); T = tempfile.mkdtemp(); ko = []
def check(nome, cond, extra=""):
    print(("OK  " if cond else "FAIL"), nome, extra); (None if cond else ko.append(nome))

r = subprocess.run([sys.executable, "-m", "py_compile", *[os.path.join(QUI, f) for f in
     ("sagome.py", "motore_calibrato.py", "pipeline_web.py")]], capture_output=True)
check("G1 py_compile", r.returncode == 0)

def esegui(nome, clip=False, **kw):
    v = f"{T}/{nome}.mp4"; g = genera(v, **kw)
    s = S.riquadri_per_frame(v, S.regione_tastiera(v, quad=g["quad"]))
    det = RilevatoreCalibrato(s); res = det.analizza(v, f"{T}/o_{nome}", sagome_dir=f"{T}/s_{nome}", scrivi_clip=clip)
    return g, s, det, res, v

g, s, det, res, v = esegui("a", clip=True, mano=False)
vere = {n for n, _, _ in g["premute"]}
check("G5 note non premute -> 0 eventi", set(res["emesse"]) == vere and res["n_eventi"] == len(vere),
      f"emesse={len(res['emesse'])} vere={len(vere)} eventi={res['n_eventi']}")
check("G6 emesse ⊂ visibili", set(det.note_emesse()) <= set(s.visibili), f"visibili={len(s.visibili)}/88")
nonvis = [n for n in range(21, 109) if n not in s.visibili]
check("G3 clip solo per note inquadrate", len(glob.glob(f"{T}/s_a/sagome/*.mp4")) == len(s.visibili)
      and not any(os.path.exists(f"{T}/s_a/sagome/{n:03d}.mp4") for n in nonvis))
nfr = {int(cv2.VideoCapture(f).get(cv2.CAP_PROP_FRAME_COUNT)) for f in glob.glob(f"{T}/s_a/sagome/*.mp4")}
check("G3 ogni clip ha n_frame frame", nfr == {s.n_frame}, f"n_frame={s.n_frame} clip={nfr}")
pm = pretty_midi.PrettyMIDI(f"{T}/o_a/song.mid"); note = pm.instruments[0].notes
check("G4 MIDI apribile, note in 21-108", len(note) == res["n_eventi"] and all(21 <= n.pitch <= 108 for n in note))
o = s.ottava
check("G7 ottava dichiarata (scelta o candidate)", (o["scelta"] is not None) or (o["ambigua"] and len(o["candidate"]) > 1),
      f"scelta={o['scelta']} candidate={len(o['candidate'])}")
g2, s2, d2, r2, _ = esegui("b", prima=60, n_bianchi=8, W=800, mano=False, premute=[(60, 1, 2), (64, 2, 3)])
check("G7 una sola ottava visibile: ambigua e dichiarata", s2.ottava["ambigua"] and s2.ottava["scelta"] is None
      and s2.ottava["ipotesi_usata"] is not None, f"candidate={len(s2.ottava['candidate'])}")
g3, s3, d3, r3, _ = esegui("c", prima=21, n_bianchi=52, W=3400, mano=False, premute=[(21, 1, 2), (60, 1, 2), (108, 2, 3)])
check("tastiera intera: 88 note, ottava univoca", len(s3.visibili) == 88 and s3.ottava["scelta"] == 21)
print("\nFALLITI:", ko or "nessuno"); sys.exit(1 if ko else 0)
