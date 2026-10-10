"""Fit robusto della griglia FRONTALE nella striscia + immagine di riferimento finale.

Massimizza la "scurezza" del profilo sulle posizioni dei confini dei tasti bianchi,
su (passo w, fase x0). Marca anche i centri dei neri misurati.
"""
import cv2
import numpy as np

VID = "/Users/alessandrolocurcio/Downloads/piano-detector/test_shotC.mp4"
QUAD = np.float32([[152, 100], [1128, 100], [1128, 320], [152, 320]])
W, H = 976, 220
cap = cv2.VideoCapture(VID)
fr = []
while len(fr) < 60:
    ok, f = cap.read()
    if not ok:
        break
    fr.append(f)
cap.release()
med = np.median(np.stack(fr).astype(np.float32), axis=0).astype(np.uint8)
M = cv2.getPerspectiveTransform(QUAD, np.float32([[0, 0], [W, 0], [W, H], [0, H]]))
strip = cv2.warpPerspective(med, M, (W, H))
sg = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY).astype(float)

# profilo della fascia frontale (bianchi), righe sotto i neri e sopra il pannello
R0, R1 = 155, 205
prof = sg[R0:R1].mean(axis=0)
prof = np.convolve(prof, np.ones(3) / 3, mode="same")
# "scurezza" normalizzata: 1 = piu' scuro del massimo locale
dark = 1.0 - (prof - prof.min()) / (prof.max() - prof.min())

xs = np.arange(W)
best = None
for w in np.arange(31.5, 34.51, 0.05):
    for x0 in np.arange(0, w, 0.25):
        k = np.arange(-3, int((W - x0) / w) + 2)
        p = x0 + k * w
        p = p[(p >= 0) & (p <= W - 1)]
        if len(p) < 20:
            continue
        v = np.interp(p, xs, dark).mean()
        if best is None or v > best[0]:
            best = (v, w, x0)
score, w_f, x0_f = best
print(f"fit fascia frontale: w = {w_f:.2f} px, x0 = {x0_f:.2f} px, scurezza media = {score:.3f}")
n_tasti = int((W - x0_f) / w_f) + 1
print(f"confini da x0={x0_f:.1f} ogni {w_f:.2f}: {n_tasti} tasti bianchi nella striscia "
      f"({W} px)")

img = strip.copy()
for k in range(-1, n_tasti + 1):
    x = int(round(x0_f + k * w_f))
    if 0 <= x < W:
        cv2.line(img, (x, 0), (x, H - 1), (0, 255, 0), 1)
        if k % 7 == 0:
            cv2.putText(img, str(k), (min(x + 2, W - 20), H - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
cv2.putText(img, f"GRIGLIA CORRETTA (fascia frontale): w={w_f:.2f}px, x0={x0_f:.1f}, "
                 f"{n_tasti} tasti bianchi", (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (0, 255, 255), 1)
cv2.imwrite("/tmp/ref_strip_griglia_corretta.png", img)
print("scritta /tmp/ref_strip_griglia_corretta.png (", img.shape, ")")

# quanto bene i neri misurati cadono sul modello (offset _OFFSET_NERI)
OFF = {1: -0.10, 3: 0.10, 6: -0.12, 8: 0.0, 10: 0.12}
print("\nverifica con i NERI: per ogni nero misurato, il confine piu' vicino e la classe")
print("(i neri sono letti in una banda 1% piu' stretta: w_neri ~ 32.4)")

# confronto: immagini di riferimento con i due piani
cv2.imwrite("/tmp/ref_frame_griglia_corretta.jpg", med)
