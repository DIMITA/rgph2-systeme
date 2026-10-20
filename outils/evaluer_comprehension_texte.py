"""Un modèle multilingue retrouve-t-il, à partir d'un texte en langue nationale, le texte
français qui dit la même chose ? Mesure sur FLORES-200 (Meta, CC-BY-SA 4.0).

C'est la question que pose une FAQ rédigée en français et interrogée en lingala, en
kiswahili, en kikongo ou en tshiluba, sans formulation traduite dans le CMS. FLORES-200
contient 1 012 phrases (jeu « devtest ») traduites par des professionnels dans ces
quatre langues : lin_Latn, swh_Latn, kon_Latn (kikongo), lua_Latn (tshiluba).

Pour chaque phrase en langue nationale, on cherche sa traduction parmi des phrases
françaises : dans un lot de 100 (taille d'une FAQ) et parmi les 1 012. Le moteur
lexical du cœur sert de référence : il ne comprend aucune langue, il ne retrouve que les
noms propres, les nombres et les mots empruntés au français.

Limites : des phrases de Wikipédia, longues et riches en noms propres, pas des questions
courtes et orales sur le recensement. Le chiffre classe les modèles entre eux ; il ne
dit pas la part de bonnes réponses en service (pour cela : coeur.connaissances.evaluation
sur de vraies questions).

    python outils/evaluer_comprehension_texte.py st:sentence-transformers/LaBSE sonar
    python outils/evaluer_comprehension_texte.py lexical --requetes 200   # lent
"""

import argparse
import random
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

import numpy as np

FLORES = "https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz"
LANGUES = {"ln": "lin_Latn", "sw": "swh_Latn", "kg": "kon_Latn", "lua": "lua_Latn"}
FRANCAIS = "fra_Latn"
TAILLE_LOT = 100


def phrases(cache: Path) -> dict[str, list[str]]:
    """Code FLORES → les 1 012 phrases du jeu devtest, alignées d'une langue à l'autre."""
    archive = cache / "flores200_dataset.tar.gz"
    if not archive.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FLORES, archive)
    voulus = {f"{code}.devtest": code for code in [FRANCAIS, *LANGUES.values()]}
    trouvees = {}
    with tarfile.open(archive) as tar:
        for membre in tar:
            code = voulus.get(Path(membre.name).name)
            if code and membre.isfile():
                texte = tar.extractfile(membre).read().decode("utf-8")
                trouvees[code] = texte.splitlines()
    manquantes = set(voulus.values()) - set(trouvees)
    if manquantes:
        raise SystemExit(f"Absent de FLORES-200 : {', '.join(sorted(manquantes))}")
    return trouvees


class Lexical:
    """Le moteur du cœur, tel quel. Il est fait pour une FAQ de quelques centaines de
    formulations courtes : chaque phrase n'est comparée qu'à son lot de 100."""

    nom = "moteur lexical du cœur (référence)"
    lots_seulement = True

    def similarites(self, requetes: list[str], cibles: list[str], _langue: str,
                    lots_: list[list[int]]) -> np.ndarray:
        from coeur.connaissances.moteur import Entree, MoteurLexical

        scores = np.full((len(requetes), len(cibles)), -1.0, dtype=np.float32)
        for i, requete in enumerate(requetes):
            scores[i, lots_[i]] = 0.0
            moteur = MoteurLexical(Entree(j, "fr", cibles[j]) for j in lots_[i])
            for candidat in moteur.rechercher(requete, ["fr"]):
                scores[i, candidat.contenu_id] = candidat.score
        return scores


class SentenceTransformers:
    lots_seulement = False

    def __init__(self, modele: str):
        from sentence_transformers import SentenceTransformer

        self.nom = modele
        self.modele = SentenceTransformer(modele, device="cpu")
        # Les modèles E5 attendent un préfixe ; les autres non.
        self.prefixe = "query: " if "e5" in modele.lower() else ""

    def encoder(self, textes: list[str]) -> np.ndarray:
        return self.modele.encode([self.prefixe + t for t in textes], batch_size=32,
                                  normalize_embeddings=True, convert_to_numpy=True)

    def similarites(self, requetes: list[str], cibles: list[str], _langue: str,
                    _lots: list[list[int]]) -> np.ndarray:
        return self.encoder(requetes) @ self.encoder(cibles).T


class Sonar:
    """Meta SONAR : un encodeur par langue source, entraîné sur les 200 langues de NLLB."""

    nom = "SONAR (text_sonar_basic_encoder)"
    lots_seulement = False

    def __init__(self):
        from sonar.inference_pipelines.text import TextToEmbeddingModelPipeline

        self.pipeline = TextToEmbeddingModelPipeline(
            encoder="text_sonar_basic_encoder", tokenizer="text_sonar_basic_encoder")

    def encoder(self, textes: list[str], langue: str) -> np.ndarray:
        vecteurs = self.pipeline.predict(textes, source_lang=langue, batch_size=32).numpy()
        return vecteurs / np.linalg.norm(vecteurs, axis=1, keepdims=True)

    def similarites(self, requetes: list[str], cibles: list[str], langue: str,
                    _lots: list[list[int]]) -> np.ndarray:
        return self.encoder(requetes, langue) @ self.encoder(cibles, FRANCAIS).T


def modele(nom: str):
    if nom == "lexical":
        return Lexical()
    if nom == "sonar":
        return Sonar()
    if nom.startswith("st:"):
        return SentenceTransformers(nom[3:])
    raise SystemExit(f"Modèle inconnu : {nom} (lexical, sonar ou st:<modèle Hugging Face>)")


def lots(n: int, taille: int, graine: int = 0) -> list[list[int]]:
    """Pour chaque phrase : sa traduction, puis `taille - 1` autres tirées au hasard."""
    hasard = random.Random(graine)
    return [[i, *hasard.sample([j for j in range(n) if j != i], taille - 1)] for i in range(n)]


def justesse(scores: np.ndarray, lots_: list[list[int]]) -> tuple[float, float]:
    """Part des phrases dont la traduction arrive première : dans son lot, et parmi toutes.
    Une égalité compte comme une erreur."""
    dans_lot = np.mean([scores[i, i] > scores[i, lot[1:]].max() for i, lot in enumerate(lots_)])
    partout = np.mean(scores.argmax(axis=1) == np.arange(len(scores)))
    return float(dans_lot), float(partout)


def main() -> int:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("modeles", nargs="+")
    analyseur.add_argument("--requetes", type=int, default=0,
                           help="Ne chercher que les N premières phrases (défaut : toutes)")
    analyseur.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "flores")
    analyseur.add_argument("--sortie", type=Path, default=Path("rapport-comprehension.md"))
    args = analyseur.parse_args()

    textes = phrases(args.cache)
    francais = textes[FRANCAIS]
    n = args.requetes or len(francais)
    lots_ = lots(len(francais), TAILLE_LOT)[:n]
    entete = " | ".join(f"{code} lot / tout" for code in LANGUES)
    lignes = [
        "# Compréhension du texte : retrouver la phrase française (FLORES-200, devtest)", "",
        f"{n} phrases cherchées par langue. « lot » : parmi {TAILLE_LOT} phrases françaises "
        f"(taille d'une FAQ) ; « tout » : parmi les {len(francais)}. Processeur seul.", "",
        f"| Modèle | {entete} | Calcul |",
        "| --- |" + " --- |" * (len(LANGUES) + 1),
    ]
    exemples = []
    for nom in args.modeles:
        debut = time.monotonic()
        m = modele(nom)
        cellules = []
        for code, flores in LANGUES.items():
            scores = m.similarites(textes[flores][:n], francais, flores, lots_)
            lot, tout = justesse(scores, lots_)
            cellules.append(f"{lot:.0%} / " + ("—" if m.lots_seulement else f"{tout:.0%}"))
            rate = int(np.argmax(scores.argmax(axis=1) != np.arange(len(scores))))
            if scores[rate].argmax() != rate:
                exemples.append(
                    f"- **{m.nom}**, {code} : « {textes[flores][rate]} »\n"
                    f"  - attendu : {francais[rate]}\n"
                    f"  - choisi : {francais[int(scores[rate].argmax())]}")
        lignes.append(f"| {m.nom} | {' | '.join(cellules)} | {time.monotonic() - debut:.0f} s |")
        print(lignes[-1], flush=True)
    lignes += ["", "## Une erreur par modèle et par langue", "", *exemples]
    args.sortie.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("\n".join(lignes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
