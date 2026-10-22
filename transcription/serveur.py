"""Service de transcription du RGPH-2 : messages vocaux → texte, hébergé par le projet.

Contrat (celui qu'attend coeur.comprehension.transcription) :
    POST /transcrire?langue=ln   corps : fichier audio (ogg/opus, mp3, wav, m4a…)
    → 200 {"texte": "…", "langue": "ln"}
    → 422 langue non prise en charge ou audio illisible ; 413 audio trop long
    GET /sante → {"statut": "ok", "modele": "…", "langues": ["fr", "ln", …]}

Deux moteurs, au choix (MOTEUR) :
- « mms » (défaut) : Meta MMS (facebook/mms-1b-all, licence CC-BY-NC 4.0), un adaptateur
  par langue ; ne connaît ni le kikongo ni le tshiluba ;
- « omnilingual » : Meta Omnilingual ASR (fairseq2, code Apache 2.0), plus de 1 600
  langues, dont le tshiluba. Le code « - » transcrit sans indiquer de langue au modèle
  (kikongo : le modèle n'a pas de code pour lui).

Rien n'est écrit sur disque : l'audio est décodé en mémoire par ffmpeg, transcrit, puis
oublié. Aucun journal ne contient de texte transcrit.

Réglages (variables d'environnement) :
    MOTEUR         mms ou omnilingual (défaut mms)
    MODELE         identifiant du modèle (défaut selon le moteur)
    CODES_LANGUES  code du cœur → code du modèle (défaut selon le moteur)
    DUREE_MAX      secondes d'audio au plus (défaut 180)
"""

import logging
import os
import subprocess
import threading
from typing import Protocol

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

FREQUENCE = 16_000
TRANCHE_SECONDES = 30
journal = logging.getLogger("transcription")


class Moteur(Protocol):
    nom: str

    def langues(self) -> list[str]:
        """Codes du cœur (fr, ln…) que le modèle sait transcrire."""

    def transcrire(self, signal: np.ndarray, langue: str) -> str:
        """`signal` : mono, 16 kHz, float32 entre -1 et 1."""


def codes_langues(texte: str) -> dict[str, str]:
    return dict(p.strip().split(":", 1) for p in texte.split(",") if ":" in p)


class MoteurMMS:
    """Wav2Vec2 + adaptateurs par langue. Un verrou : l'adaptateur actif est partagé."""

    def __init__(self, modele: str, codes: dict[str, str]):
        import torch
        from transformers import AutoProcessor, Wav2Vec2ForCTC

        self.nom, self._torch = modele, torch
        self.processeur = AutoProcessor.from_pretrained(modele)
        self.modele = Wav2Vec2ForCTC.from_pretrained(modele).eval()
        connus = set(self.processeur.tokenizer.vocab)
        # Une langue absente du modèle est écartée et signalée, plutôt que d'échouer plus tard.
        self.codes = {c: m for c, m in codes.items() if m in connus}
        for code, modele_code in codes.items():
            if code not in self.codes:
                journal.warning("Langue %s (%s) absente du modèle %s", code, modele_code, modele)
        self._actif: str | None = None
        self._verrou = threading.Lock()

    def langues(self) -> list[str]:
        return sorted(self.codes)

    def transcrire(self, signal: np.ndarray, langue: str) -> str:
        code = self.codes[langue]
        morceaux = []
        with self._verrou:
            if self._actif != code:
                self.processeur.tokenizer.set_target_lang(code)
                self.modele.load_adapter(code)
                self._actif = code
            pas = TRANCHE_SECONDES * FREQUENCE
            for debut in range(0, len(signal), pas):
                entrees = self.processeur(signal[debut:debut + pas], sampling_rate=FREQUENCE,
                                          return_tensors="pt")
                with self._torch.inference_mode():
                    logits = self.modele(**entrees).logits
                morceaux.append(self.processeur.decode(self._torch.argmax(logits, dim=-1)[0]))
        return " ".join(m.strip() for m in morceaux if m.strip())


class MoteurOmnilingual:
    """Omnilingual ASR. Le modèle refuse plus de 40 s : l'audio passe par tranches de 30 s."""

    SANS_LANGUE = "-"

    def __init__(self, modele: str, codes: dict[str, str]):
        import torch
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
        from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs

        self.nom = modele
        # Sur processeur, bfloat16 est lent ou absent : float32.
        type_ = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        self.pipeline = ASRInferencePipeline(model_card=modele, dtype=type_)
        connus = set(supported_langs) | {self.SANS_LANGUE}
        self.codes = {c: m for c, m in codes.items() if m in connus}
        for code, modele_code in codes.items():
            if code not in self.codes:
                journal.warning("Langue %s (%s) absente du modèle %s", code, modele_code, modele)
        self._verrou = threading.Lock()

    def langues(self) -> list[str]:
        return sorted(self.codes)

    def transcrire(self, signal: np.ndarray, langue: str) -> str:
        code = self.codes[langue]
        pas = TRANCHE_SECONDES * FREQUENCE
        tranches = [{"waveform": signal[debut:debut + pas], "sample_rate": FREQUENCE}
                    for debut in range(0, len(signal), pas)]
        with self._verrou:
            textes = self.pipeline.transcribe(
                tranches, lang=[None if code == self.SANS_LANGUE else code] * len(tranches),
                batch_size=1)
        return " ".join(t.strip() for t in textes if t.strip())


MOTEURS = {
    "mms": (MoteurMMS, "facebook/mms-1b-all", "fr:fra,ln:lin,sw:swh,kg:kng,lua:lua"),
    "omnilingual": (MoteurOmnilingual, "omniASR_LLM_1B",
                    "fr:fra_Latn,ln:lin_Latn,sw:swh_Latn,lua:lua_Latn,kg:-"),
}


def decoder(audio: bytes) -> np.ndarray:
    """N'importe quel format audio → mono 16 kHz float32, en mémoire (ffmpeg)."""
    resultat = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0",
         "-f", "f32le", "-ac", "1", "-ar", str(FREQUENCE), "pipe:1"],
        input=audio, capture_output=True, timeout=60, check=False)
    if resultat.returncode != 0 or not resultat.stdout:
        raise ValueError("audio illisible")
    return np.frombuffer(resultat.stdout, dtype=np.float32)


def creer_app(moteur: Moteur, duree_max: float = 180) -> FastAPI:
    app = FastAPI(title="Transcription RGPH-2", docs_url=None, redoc_url=None)

    @app.get("/sante")
    def sante() -> dict:
        return {"statut": "ok", "modele": moteur.nom, "langues": moteur.langues()}

    @app.post("/transcrire")
    async def transcrire(request: Request, langue: str = Query(pattern=r"^[a-z]{2,3}$")) -> dict:
        if langue not in moteur.langues():
            raise HTTPException(422, f"Langue non prise en charge : {langue}")
        audio = await request.body()
        try:
            signal = decoder(audio)
        except (ValueError, subprocess.TimeoutExpired) as erreur:
            raise HTTPException(422, "Audio illisible") from erreur
        if len(signal) > duree_max * FREQUENCE:
            raise HTTPException(413, "Audio trop long")
        # Calcul de plusieurs secondes : hors de la boucle asynchrone.
        texte = await run_in_threadpool(moteur.transcrire, signal, langue)
        return {"texte": texte, "langue": langue}

    return app


def app_depuis_environnement() -> FastAPI:
    """Point d'entrée d'uvicorn : `uvicorn serveur:app_depuis_environnement --factory`."""
    logging.basicConfig(level=logging.INFO)
    classe, modele, codes = MOTEURS[os.environ.get("MOTEUR", "mms")]
    moteur = classe(os.environ.get("MODELE", modele),
                    codes_langues(os.environ.get("CODES_LANGUES", codes)))
    return creer_app(moteur, float(os.environ.get("DUREE_MAX", "180")))
