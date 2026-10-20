"""Mesure du modèle de transcription sur de vrais enregistrements : Google FLEURS (CC-BY 4.0).

FLEURS contient des phrases lues par des locuteurs natifs, dont du lingala de RDC
(ln_cd), du kiswahili (sw_ke) et du français (fr_fr). Pas de kikongo ni de tshiluba :
pour ces langues, seule la présence d'un adaptateur dans le modèle est vérifiée.

Ce ne sont pas des questions sur le recensement : on mesure ici la transcription
seule (taux d'erreur de mots, temps de calcul), pas la reconnaissance du sujet. Chaque
enregistrement passe d'abord au format des messages vocaux de WhatsApp (Ogg/Opus),
puis par le service HTTP réel (serveur.creer_app), comme en production.

    python transcription/evaluer_fleurs.py --nombre 40 --sortie rapport.md
"""

import argparse
import csv
import statistics
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from fastapi.testclient import TestClient
from huggingface_hub import hf_hub_download

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serveur  # noqa: E402

from coeur.connaissances.evaluation import taux_erreur_mots  # noqa: E402

# Code du cœur → configuration FLEURS.
CORPUS = {"fr": "fr_fr", "ln": "ln_cd", "sw": "sw_ke"}
CODES_MODELE = "fr:fra,ln:lin,sw:swh,kg:kng,lua:lua"
# Codes à chercher pour le kikongo (koongo, kituba, kikongo, San Salvador) et le tshiluba.
CODES_A_VERIFIER = ["kng", "ktu", "kon", "kwy", "lua"]
# Autres versions de MMS : seul leur vocabulaire est téléchargé (quelques Mo), pour savoir
# si elles couvrent le kikongo ou le tshiluba sans charger 4 Go de poids.
AUTRES_MODELES = ["facebook/mms-1b-l1107", "facebook/mms-1b-fl102"]


def langues_d_un_modele(modele: str) -> set[str] | None:
    """Codes de langue du vocabulaire d'un modèle MMS, ou None s'il est illisible."""
    import json

    try:
        with open(hf_hub_download(modele, "vocab.json"), encoding="utf-8") as fichier:
            return set(json.load(fichier))
    except Exception as erreur:  # modèle absent ou format différent : on le dit
        print(f"{modele} : vocabulaire illisible ({type(erreur).__name__})", flush=True)
        return None


def en_opus(wav: bytes) -> bytes:
    """Comme un message vocal WhatsApp : Ogg/Opus mono, 16 kb/s."""
    return subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-ac", "1",
         "-c:a", "libopus", "-b:a", "16k", "-f", "ogg", "pipe:1"],
        input=wav, capture_output=True, check=True).stdout


def enregistrements(config: str, nombre: int) -> list[tuple[str, bytes, float]]:
    """(transcription de référence, wav, durée en secondes) des `nombre` premiers du test."""
    tsv = hf_hub_download("google/fleurs", f"data/{config}/test.tsv", repo_type="dataset")
    archive = hf_hub_download("google/fleurs", f"data/{config}/audio/test.tar.gz",
                              repo_type="dataset")
    lignes = []
    with open(tsv, encoding="utf-8", newline="") as fichier:
        # Colonnes : id, fichier, texte brut, texte normalisé, phonèmes, échantillons, genre.
        for ligne in csv.reader(fichier, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(ligne) >= 6 and ligne[1].endswith(".wav"):
                lignes.append((ligne[1], ligne[3], int(ligne[5]) / 16_000))
    voulus = {nom: (texte, duree) for nom, texte, duree in lignes[:nombre]}
    trouves = []
    with tarfile.open(archive) as tar:
        for membre in tar:
            nom = Path(membre.name).name
            if nom in voulus:
                texte, duree = voulus[nom]
                trouves.append((texte, tar.extractfile(membre).read(), duree))
            if len(trouves) == len(voulus):
                break
    if not trouves:
        raise SystemExit(f"Aucun enregistrement lu pour {config} : format de FLEURS inattendu")
    return trouves


def main() -> int:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--nombre", type=int, default=40)
    analyseur.add_argument("--modele", default="facebook/mms-1b-all")
    analyseur.add_argument("--sortie", type=Path, default=Path("rapport-transcription.md"))
    args = analyseur.parse_args()

    debut = time.monotonic()
    moteur = serveur.MoteurMMS(args.modele, serveur.codes_langues(CODES_MODELE))
    chargement = time.monotonic() - debut
    connus = set(moteur.processeur.tokenizer.vocab)
    client = TestClient(serveur.creer_app(moteur, duree_max=60))

    autres = []
    for modele in AUTRES_MODELES:
        langues = langues_d_un_modele(modele)
        autres.append(f"- `{modele}` : " + ("illisible" if langues is None else ", ".join(
            f"`{c}` {'oui' if c in langues else 'non'}" for c in CODES_A_VERIFIER)))
    lignes = [
        f"# Transcription : {args.modele} sur Google FLEURS (test)", "",
        f"Chargement du modèle : {chargement:.0f} s. Processeur seul (runner GitHub, 4 cœurs).", "",
        "Adaptateurs présents dans le modèle : " + ", ".join(
            f"`{c}` {'oui' if c in connus else 'non'}" for c in CODES_A_VERIFIER), "",
        "Dans les autres versions de MMS :", *autres, "",
        "| Langue | Enregistrements | WER moyen | WER médian | Durée moy. | Calcul moy. | Temps réel |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    exemples = []
    for langue, config in CORPUS.items():
        wers, calculs, durees = [], [], []
        for i, (reference, wav, duree) in enumerate(enregistrements(config, args.nombre)):
            audio = en_opus(wav)
            t0 = time.monotonic()
            r = client.post("/transcrire", params={"langue": langue}, content=audio,
                            headers={"Content-Type": "audio/ogg"})
            calculs.append(time.monotonic() - t0)
            r.raise_for_status()
            hypothese = r.json()["texte"]
            wers.append(taux_erreur_mots(reference, hypothese))
            durees.append(duree)
            if i < 3:
                exemples.append(f"- **{langue}** ({wers[-1]:.0%})\n  - dit : {reference}\n"
                                f"  - transcrit : {hypothese}")
        lignes.append(
            f"| {langue} ({config}) | {len(wers)} | {statistics.mean(wers):.0%} | "
            f"{statistics.median(wers):.0%} | {statistics.mean(durees):.1f} s | "
            f"{statistics.mean(calculs):.1f} s | {sum(calculs) / sum(durees):.2f} |")
        print(lignes[-1], flush=True)
    lignes += ["", "« Temps réel » : secondes de calcul par seconde d'audio (moins de 1 : plus "
               "rapide que la parole).", "", "## Exemples", "", *exemples]
    args.sortie.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("\n".join(lignes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
