"""Synchronise le serveur vocal (SVI) avec les contenus publiés dans le cœur.

1. lit le menu dans l'API (GET /v1/appels/svi, clé du canal centre_ecoute) ;
2. prépare les audios (question et réponse) au format téléphonique :
   - fichier audio du CMS (audio_url, audio_question_url) s'il existe ;
   - sinon, si SVI_SYNTHESE_PROVISOIRE=true et que le texte est en français,
     voix de synthèse provisoire ; sinon l'élément est retiré du menu ;
3. réécrit extensions_svi.conf et recharge le dialplan s'il a changé.

    python3 synchroniser_svi.py              # une fois
    python3 synchroniser_svi.py --boucle 300 # toutes les 5 minutes
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from audio import convertir, dossier_rgph, synthetiser

FICHIER_DIALPLAN = Path("/etc/asterisk/extensions_svi.conf")
SONS = "/var/lib/asterisk/sounds"


# --- Génération du dialplan (fonction pure, testée) -----------------------------------

def generer_dialplan(langues: list[dict], menus: dict[str, list[tuple[int, int]]]) -> str:
    """langues : [{"code": "fr", "touche": 1}, …] ; menus : code → [(touche, contenu_id), …]."""
    lignes = ["; Généré automatiquement par synchroniser_svi.py — ne pas modifier.", ""]
    annonces = "&".join(f"{SONS}/{l['code']}/rgph/choix_langue" for l in langues)
    lignes += [
        "[svi-langue]",
        "exten => s,1,Set(ESSAIS=0)",
        f" same => n(menu),Background({annonces})" if annonces else " same => n(menu),NoOp()",
        " same => n,WaitExten(5)",
    ]
    for l in langues:
        code = l["code"]
        lignes += [
            f"exten => {l['touche']},1,Set(__LANGUE={code})",
            f" same => n,Set(CHANNEL(language)={code})",
            f" same => n,Gosub(evenement,s,1(type=langue&langue={code}))",
            f" same => n,Goto(svi-{code},s,1)",
        ]
    defaut = langues[0]["touche"] if langues else None
    lignes += [
        "exten => t,1,Set(ESSAIS=$[${ESSAIS} + 1])",
        " same => n,GotoIf($[${ESSAIS} < 2]?s,menu)",
        f" same => n,Goto({defaut},1)" if defaut else " same => n,Goto(file-attente,s,1)",
        "exten => i,1,Playback(rgph/choix_invalide)",
        " same => n,Goto(s,menu)",
        "",
    ]
    for l in langues:
        code, elements = l["code"], menus.get(l["code"], [])
        lignes.append(f"[svi-{code}]")
        if not elements:
            lignes += ["exten => s,1,Playback(rgph/aucune_reponse_langue)",
                       " same => n,Goto(file-attente,s,1)", ""]
            continue
        annonces = "&".join(f"rgph/touche_{t}&rgph/svi/q-{cid}" for t, cid in elements)
        lignes += [
            "exten => s,1,Set(ESSAIS=0)",
            " same => n(menu),Background(rgph/svi_intro)",
            f" same => n,Background({annonces})",
            " same => n,WaitExten(6)",
        ]
        for touche, cid in elements:
            lignes += [
                f"exten => {touche},1,Gosub(evenement,s,1(type=svi_ecoute&contenu_id={cid}))",
                f" same => n,Playback(rgph/svi/r-{cid})",
                " same => n,Goto(s,menu)",
            ]
        lignes += [
            "exten => 0,1,Goto(file-attente,s,1)",
            "exten => t,1,Set(ESSAIS=$[${ESSAIS} + 1])",
            " same => n,GotoIf($[${ESSAIS} < 2]?s,menu)",
            " same => n,Goto(file-attente,s,1)",
            "exten => i,1,Playback(rgph/choix_invalide)",
            " same => n,Goto(s,menu)",
            "",
        ]
    return "\n".join(lignes)


# --- Audios ----------------------------------------------------------------------------

def telecharger(url: str, destination: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        brut = Path(tmp) / "source"
        with urllib.request.urlopen(url, timeout=30) as reponse:
            brut.write_bytes(reponse.read())
        convertir(brut, destination)


def preparer(destination: Path, url: str | None, texte: str, francais: bool,
             manifeste: dict, synthese: bool) -> bool:
    """Prépare un audio s'il a changé depuis la dernière fois. Renvoie False si impossible."""
    if url:
        signature = "url:" + url
    elif synthese and francais:
        signature = "tts:" + hashlib.sha256(texte.encode()).hexdigest()
    else:
        return False
    if manifeste.get(destination.name) == signature and destination.exists():
        return True
    try:
        telecharger(url, destination) if url else synthetiser(texte, destination)
    except Exception as erreur:  # audio inaccessible ou illisible : élément ignoré
        print(f"SVI : audio impossible pour {destination.name} : {erreur}", flush=True)
        return False
    manifeste[destination.name] = signature
    return True


def lire_menu() -> dict:
    requete = urllib.request.Request(
        os.environ.get("API_URL", "http://api:8000") + "/v1/appels/svi",
        headers={"X-Cle-API": os.environ["CLE_API_CENTRE_ECOUTE"]},
    )
    with urllib.request.urlopen(requete, timeout=15) as reponse:
        return json.load(reponse)


def recharger_asterisk() -> None:
    if subprocess.run(["asterisk", "-rx", "core show version"],
                      capture_output=True).returncode == 0:
        subprocess.run(["asterisk", "-rx", "dialplan reload"], capture_output=True)


def synchroniser() -> None:
    menu = lire_menu()
    synthese = os.environ.get("SVI_SYNTHESE_PROVISOIRE", "").lower() in ("1", "true", "oui")
    menus: dict[str, list[tuple[int, int]]] = {}
    for langue in menu["langues"]:
        code = langue["code"]
        dossier = dossier_rgph(code) / "svi"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin_manifeste = dossier / "manifeste.json"
        manifeste = json.loads(chemin_manifeste.read_text()) if chemin_manifeste.exists() else {}
        elements, utilises = [], {"manifeste.json"}
        for el in menu["menus"].get(code, []):
            cid, francais = el["contenu_id"], el["langue"] == "fr"
            q, r = dossier / f"q-{cid}.wav", dossier / f"r-{cid}.wav"
            if (preparer(q, el["audio_question_url"], el["question"], francais, manifeste, synthese)
                    and preparer(r, el["audio_url"], el["reponse"], francais, manifeste, synthese)):
                # Touches renumérotées sans trou si un élément n'a pas d'audio.
                elements.append((len(elements) + 1, cid))
                utilises |= {q.name, r.name}
        for ancien in dossier.iterdir():
            if ancien.name not in utilises:
                ancien.unlink()
                manifeste.pop(ancien.name, None)
        chemin_manifeste.write_text(json.dumps(manifeste, indent=1))
        menus[code] = elements

    texte = generer_dialplan(menu["langues"], menus)
    ancien = FICHIER_DIALPLAN.read_text() if FICHIER_DIALPLAN.exists() else ""
    if texte != ancien:
        FICHIER_DIALPLAN.write_text(texte)
        recharger_asterisk()
        resume = ", ".join(f"{c} : {len(e)}" for c, e in menus.items())
        print(f"SVI mis à jour ({resume} réponse(s)).", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--boucle":
        intervalle = int(sys.argv[2])
        while True:
            time.sleep(intervalle)
            try:
                synchroniser()
            except Exception as erreur:
                print(f"SVI : synchronisation impossible : {erreur}", flush=True)
    else:
        synchroniser()
