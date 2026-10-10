"""
Note Events — da (mani + griglia dei tasti) a eventi nota con onset/offset.

Stadio 2 / E4 della pipeline video -> MIDI.

PRESSIONE (niente test "il dito e' dentro il rettangolo del tasto")
------------------------------------------------------------------
Per ogni polpastrello (mano, dito) si calcola in ogni frame:

    x   = v_punta - v_palmo        v = profondita' lungo i tasti (0 = bordo
                                   superiore, 1 = bordo frontale), nello spazio
                                   raddrizzato da KeyboardGrid.punto_raddrizzato;
                                   v_palmo = media di v sulle nocche (landmark 5,9,13,17)
    rel = x_filtrata - baseline    discesa del polpastrello rispetto al suo livello
                                   "a riposo" (hover)

Sottrarre il palmo elimina gli spostamenti dell'intera mano; la baseline e'
l'ultimo livello di hover del dito: segue subito le risalite (minimo) e deriva
lentamente verso l'alto (tau = `tau_baseline`), ed e' CONGELATA mentre la nota
suona o il dito e' bloccato. Cosi' un dito fermo sui tasti senza premere non
produce note. `rel` e' espressa in frazioni dell'altezza del tasto.

ISTERESI: la nota parte quando rel >= soglia_giu e finisce quando
rel < soglia_su (< soglia_giu). La nota e' quella sotto il polpastrello
all'onset (griglia.nota_a) e resta fissa fino al rilascio.

LIMITE DI FONDO: da una sola camera 2D la profondita' del dito non e' osservata
direttamente; `rel` e' un proxy (la discesa si vede come spostamento verso il
bordo frontale in una ripresa dall'alto/inclinata). Le soglie di default vanno
tarate sul video reale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_PUNTE = (4, 8, 12, 16, 20)
_NOCCHE = (5, 9, 13, 17)
_ALFA_FILTRO = 0.6        # peso del campione nuovo nel filtro a 1 polo di x
_TIMEOUT_MIN_S = 0.15     # buco di rilevazione tollerato (almeno 0.15 s, ~4 frame a 30 fps)


@dataclass
class EventoNota:
    nota: int
    onset: float          # secondi dall'inizio del video
    offset: float
    velocity: int         # 1-127
    profondita: float     # 0-1, quanto il dito e' sceso sotto il piano dei tasti
    mano: str
    frame_onset: int = 0
    frame_offset: int = 0


@dataclass
class _Dito:
    mano: str = ""
    baseline: float | None = None
    x_filt: float | None = None
    rel_prec: float = 0.0
    t_prec: float | None = None
    attivo: bool = False
    bloccato: bool = False
    nota: int = -1
    onset: float = 0.0
    frame_onset: int = 0
    picco: float = 0.0
    ultimo_t: float = 0.0
    ultimo_frame: int = 0


class RilevatoreNote:
    """Macchina a stati per dito: isteresi, anti-rimbalzo, timeout dei buchi, onset interpolato."""

    def __init__(self, fps: float, soglia_giu: float = 0.06, soglia_su: float = 0.03,
                 durata_minima: float = 0.05, durata_massima: float = 3.0,
                 distanza_minima_mani: float = 0.4,
                 profondita_piena: float = 0.30, tau_baseline: float = 0.4) -> None:
        """
        fps: frame al secondo del video (il tempo e' frame_idx / fps).
        soglia_giu / soglia_su: isteresi su rel, in frazioni di altezza del tasto.
        durata_minima: note piu' corte scartate; una nota non riparte entro questo
            tempo dal proprio offset (la ripartenza viene fusa con la nota precedente).
        durata_massima: note piu' lunghe troncate; il dito resta bloccato finche' non rilascia.
        distanza_minima_mani: due mani con centri a meno di questa distanza, in
            lunghezze di mano (polso -> nocca del medio), sono la stessa mano
            rilevata due volte: si tiene quella con confidenza maggiore.
        profondita_piena: rel che corrisponde a profondita' = 1 (velocity 127).
        tau_baseline: costante di tempo (s) con cui la baseline sale verso il dito.
        """
        if fps <= 0:
            raise ValueError("fps deve essere > 0")
        if not 0 < soglia_su < soglia_giu:
            raise ValueError("servono 0 < soglia_su < soglia_giu (isteresi)")
        self.fps = float(fps)
        self.soglia_giu = float(soglia_giu)
        self.soglia_su = float(soglia_su)
        self.durata_minima = float(durata_minima)
        self.durata_massima = float(durata_massima)
        self.distanza_minima_mani = float(distanza_minima_mani)
        self.profondita_piena = float(profondita_piena)
        self.tau = float(tau_baseline)
        self._diti: dict[tuple[str, int], _Dito] = {}
        self._pendenti: dict[int, dict] = {}     # note chiuse in attesa dell'anti-rimbalzo
        self._pronti: list[EventoNota] = []
        self._t_prec_frame: float | None = None
        self._dt_medio = 1.0 / self.fps

    # ------------------------------------------------------------------ API
    def aggiorna(self, frame_idx: int, mani: list["Mano"], griglia: "KeyboardGrid") -> list[EventoNota]:
        """Elabora un frame; ritorna gli eventi COMPLETATI (con offset noto) in questo passo."""
        t = frame_idx / self.fps
        if self._t_prec_frame is not None and t > self._t_prec_frame:
            self._dt_medio = 0.9 * self._dt_medio + 0.1 * (t - self._t_prec_frame)
        self._t_prec_frame = t
        timeout = max(_TIMEOUT_MIN_S, 4.0 * self._dt_medio)

        visti: set[tuple[str, int]] = set()
        if griglia is not None:
            for m in self._pulisci_mani(mani or []):
                v_palmo = self._v_palmo(m, griglia)
                if v_palmo is None:
                    continue
                for dito in _PUNTE:
                    p = m.punte.get(dito)
                    if p is None:
                        continue
                    u, v = griglia.punto_raddrizzato(p)
                    if not (math.isfinite(u) and math.isfinite(v)):
                        continue
                    chiave = (m.mano, dito)
                    visti.add(chiave)
                    st = self._diti.get(chiave)
                    if st is None:
                        st = self._diti[chiave] = _Dito()
                    self._passo_dito(st, m.mano, t, frame_idx, v - v_palmo, p, griglia, timeout)

        for chiave, st in self._diti.items():           # dita sparite: timeout breve
            if chiave not in visti and st.attivo and (t - st.ultimo_t) > timeout:
                self._chiudi_dito(st, st.ultimo_t, st.ultimo_frame)

        self._finalizza_scaduti(t)
        return self._svuota()

    def chiudi(self) -> list[EventoNota]:
        """Chiude le note ancora attive e svuota l'anti-rimbalzo; eventi ordinati per onset."""
        for st in self._diti.values():
            if st.attivo:
                self._chiudi_dito(st, st.ultimo_t, st.ultimo_frame)
        for nota in list(self._pendenti):
            self._emetti(self._pendenti.pop(nota))
        return self._svuota()

    def note_attive(self) -> list[int]:
        """Note attualmente premute (per i video di debug)."""
        return sorted({st.nota for st in self._diti.values() if st.attivo})

    # -------------------------------------------------------------- interni
    def _passo_dito(self, st: _Dito, mano: str, t: float, frame_idx: int, x: float,
                    punto, griglia, timeout: float) -> None:
        if st.t_prec is not None and (t - st.t_prec) > timeout:    # buco lungo: si riparte
            if st.attivo:
                self._chiudi_dito(st, st.ultimo_t, st.ultimo_frame)
            st.baseline = st.x_filt = st.t_prec = None
            st.bloccato = False
        st.x_filt = x if st.x_filt is None else _ALFA_FILTRO * x + (1.0 - _ALFA_FILTRO) * st.x_filt
        xf = st.x_filt
        if st.baseline is None:
            st.baseline = xf
        rel = xf - st.baseline
        tp, rp = st.t_prec, st.rel_prec
        dt = (t - tp) if tp is not None else 1.0 / self.fps

        if st.attivo:
            st.picco = max(st.picco, rel)
            if t - st.onset >= self.durata_massima:               # dito fermo: tronco
                self._chiudi_dito(st, st.onset + self.durata_massima, frame_idx)
                st.bloccato = True
            elif rel < self.soglia_su:                            # rilascio (con interpolazione)
                t_off = t
                if tp is not None and rp >= self.soglia_su and rp > rel:
                    frac = (rp - self.soglia_su) / (rp - rel)
                    t_off = tp + min(max(frac, 0.0), 1.0) * (t - tp)
                self._chiudi_dito(st, t_off, frame_idx)
        else:
            if st.bloccato:
                if rel < self.soglia_su:
                    st.bloccato = False
            elif rel >= self.soglia_giu:
                nota = griglia.nota_a(punto)
                if nota is not None:
                    self._avvia(st, mano, nota, t, frame_idx, rel, tp, rp)
            if not st.attivo and not st.bloccato:                  # baseline = livello di hover
                if xf < st.baseline:
                    st.baseline = xf
                else:
                    st.baseline += (1.0 - math.exp(-dt / self.tau)) * (xf - st.baseline)

        st.rel_prec = xf - st.baseline
        st.t_prec = t
        st.ultimo_t = t
        st.ultimo_frame = frame_idx

    def _avvia(self, st: _Dito, mano: str, nota: int, t: float, frame_idx: int,
               rel: float, tp, rp: float) -> None:
        t_on = t
        if tp is not None and rp < self.soglia_giu and rel > rp:    # attraversamento interpolato
            frac = (self.soglia_giu - rp) / (rel - rp)
            t_on = tp + min(max(frac, 0.0), 1.0) * (t - tp)
        pend = self._pendenti.get(nota)
        if pend is not None and (t_on - pend["offset"]) <= self.durata_minima:
            del self._pendenti[nota]                                # anti-rimbalzo: si fonde
            st.onset, st.frame_onset = pend["onset"], pend["frame_onset"]
            st.picco, st.mano = max(pend["picco"], rel), pend["mano"]
        else:
            st.onset, st.frame_onset, st.picco, st.mano = t_on, frame_idx, rel, mano
        st.attivo = True
        st.nota = nota

    def _chiudi_dito(self, st: _Dito, offset_t: float, frame_off: int) -> None:
        if not st.attivo:
            return
        vecchio = self._pendenti.pop(st.nota, None)
        if vecchio is not None:
            self._emetti(vecchio)
        self._pendenti[st.nota] = {
            "nota": st.nota, "onset": st.onset, "offset": max(offset_t, st.onset),
            "frame_onset": st.frame_onset, "frame_offset": int(frame_off),
            "picco": st.picco, "mano": st.mano,
        }
        st.attivo = False

    def _finalizza_scaduti(self, t: float) -> None:
        for nota in list(self._pendenti):
            if t - self._pendenti[nota]["offset"] > self.durata_minima:
                self._emetti(self._pendenti.pop(nota))

    def _emetti(self, p: dict) -> None:
        if p["offset"] - p["onset"] < self.durata_minima:           # troppo corta: scarto
            return
        prof = min(max(p["picco"] / self.profondita_piena, 0.0), 1.0)
        vel = int(min(max(round(40 + 87 * prof), 1), 127))           # 0 -> 40, 1 -> 127
        self._pronti.append(EventoNota(
            nota=int(p["nota"]), onset=float(p["onset"]), offset=float(p["offset"]),
            velocity=vel, profondita=round(prof, 3), mano=p["mano"],
            frame_onset=int(p["frame_onset"]), frame_offset=int(p["frame_offset"])))

    def _svuota(self) -> list[EventoNota]:
        out = sorted(self._pronti, key=lambda e: (e.onset, e.nota))
        self._pronti = []
        return out

    @staticmethod
    def _v_palmo(m, griglia) -> float | None:
        if len(m.tutte) < 18:
            return None
        vs = []
        for i in _NOCCHE:
            _, v = griglia.punto_raddrizzato(m.tutte[i])
            if math.isfinite(v):
                vs.append(v)
        return sum(vs) / len(vs) if vs else None

    def _pulisci_mani(self, mani: list) -> list:
        """Scarta mani incomplete e doppie rilevazioni; garantisce etichette distinte."""
        validi = [m for m in mani if len(m.tutte) >= 21 and all(d in m.punte for d in _PUNTE)]

        def centro(m):
            return (sum(p[0] for p in m.tutte) / len(m.tutte),
                    sum(p[1] for p in m.tutte) / len(m.tutte))

        tenuti: list = []
        for m in sorted(validi, key=lambda k: -k.confidenza):
            c = centro(m)
            lung = max(1.0, math.dist(m.tutte[0], m.tutte[9]))
            if all(math.dist(c, centro(k)) >= self.distanza_minima_mani * lung for k in tenuti):
                tenuti.append(m)
        tenuti.sort(key=lambda k: centro(k)[0])
        if len(tenuti) == 2 and tenuti[0].mano == tenuti[1].mano:
            tenuti[0].mano, tenuti[1].mano = "Left", "Right"
        return tenuti
