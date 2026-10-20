"""Configure Asterisk au démarrage du conteneur.

Les modèles de asterisk/config/ contiennent des marqueurs {{NOM}} remplacés par
les variables d'environnement (les ${...} sont, eux, des variables du dialplan).
Aucun secret n'est écrit dans le dépôt : ils n'existent que dans le conteneur.
"""

import hashlib
import hmac
import os
import shutil
import socket
from pathlib import Path

from audio import convertir, dossier_rgph, source_enregistree, synthetiser
from messages import PHRASES, phrase_choix_langue, touches_langues

MODELES = Path("/opt/rgph/modeles")
MESSAGES = Path("/opt/rgph/messages")
CONF = Path("/etc/asterisk")
ENREGISTREMENTS = Path("/var/spool/asterisk/enregistrements")
GROUPE_MEDIA = "rgph-media"


def env(nom: str, defaut: str = "") -> str:
    return os.environ.get(nom, defaut).strip()


def vrai(nom: str) -> bool:
    return env(nom).lower() in ("1", "true", "oui", "yes")


def rendre(modele: str, valeurs: dict[str, str]) -> str:
    for nom, valeur in valeurs.items():
        modele = modele.replace("{{" + nom + "}}", valeur)
    if "{{" in modele:
        debut = modele.index("{{")
        raise ValueError(f"Marqueur non remplacé : {modele[debut:debut + 40]!r}")
    return modele


def mot_de_passe_poste(secret: str, poste: str) -> str:
    """Même formule que coeur.centre_appels.postes (le cœur le donne au navigateur de l'agent)."""
    return hmac.new(secret.encode(), poste.encode(), hashlib.sha256).hexdigest()[:32]


def section_postes(secret: str, nombre: int, domaine: str) -> str:
    blocs = []
    for n in range(1, nombre + 1):
        poste = f"poste{n}"
        blocs.append(f"""[{poste}]
type=endpoint
context=postes
disallow=all
; G.711 seulement : comme l'opérateur, sans transcodage (pas de module Opus libre dans Asterisk).
allow=alaw,ulaw
webrtc=yes
dtls_auto_generate_cert=yes
; Le navigateur annonce un contact fictif : on réutilise la connexion WebSocket ouverte.
rewrite_contact=yes
rtp_symmetric=yes
force_rport=yes
; Domaine valide dans les messages envoyés au navigateur (JsSIP refuse un nom de conteneur).
from_domain={domaine}
auth={poste}
aors={poste}
callerid="Poste {n}" <{poste}>

[{poste}]
type=auth
auth_type=userpass
username={poste}
password={mot_de_passe_poste(secret, poste)}

[{poste}]
type=aor
max_contacts=1
remove_existing=yes
qualify_frequency=30
""")
    return "\n".join(blocs)


def section_simulateur(mot_de_passe: str) -> str:
    if not mot_de_passe:
        return "; Simulateur désactivé (SIMULATEUR_MDP vide)."
    return f"""; Téléphone logiciel de test (MicroSIP, Linphone…) : ses appels suivent le même
; parcours qu'un appel au numéro vert.
[simulateur]
type=endpoint
context=simulateur
disallow=all
allow=alaw,ulaw
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
auth=simulateur
aors=simulateur

[simulateur]
type=auth
auth_type=userpass
username=simulateur
password={mot_de_passe}

[simulateur]
type=aor
max_contacts=1
remove_existing=yes
"""


def section_operateur() -> str:
    hote = env("OPERATEUR_SIP_HOTE")
    if not hote:
        return "; Liaison opérateur non configurée (OPERATEUR_SIP_HOTE vide)."
    port = env("OPERATEUR_SIP_PORT", "5060")
    utilisateur = env("OPERATEUR_SIP_UTILISATEUR")
    mdp = env("OPERATEUR_SIP_MDP")
    lignes = [f"""; Liaison SIP de l'opérateur (numéro vert).
[operateur]
type=aor
contact=sip:{hote}:{port}
qualify_frequency=60

[operateur]
type=identify
endpoint=operateur
match={hote}

[operateur]
type=endpoint
context=entree-operateur
disallow=all
allow=alaw,ulaw
direct_media=no
aors=operateur
from_domain={hote}
"""]
    if utilisateur:
        lignes[0] += f"outbound_auth=operateur-auth\nfrom_user={utilisateur}\n"
        lignes.append(f"""[operateur-auth]
type=auth
auth_type=userpass
username={utilisateur}
password={mdp}
""")
    if utilisateur and vrai("OPERATEUR_SIP_ENREGISTREMENT"):
        lignes.append(f"""[operateur-enregistrement]
type=registration
outbound_auth=operateur-auth
server_uri=sip:{hote}:{port}
client_uri=sip:{utilisateur}@{hote}
retry_interval=60
""")
    return "\n".join(lignes)


def adresse_externe() -> str:
    adresse = env("SIP_ADRESSE_EXTERNE")
    if not adresse:
        return "; Pas d'adresse publique (SIP_ADRESSE_EXTERNE vide) : réseau local uniquement."
    return (f"external_media_address={adresse}\nexternal_signaling_address={adresse}\n"
            "local_net=10.0.0.0/8\nlocal_net=172.16.0.0/12\nlocal_net=192.168.0.0/16")


def appel_sortant() -> str:
    """Rappels : par l'opérateur ; à défaut, vers le téléphone logiciel de test."""
    if env("OPERATEUR_SIP_HOTE"):
        return "Dial(PJSIP/${EXTEN}@operateur,60)"
    if env("SIMULATEUR_MDP"):
        return "Dial(PJSIP/simulateur,60)  ; pas d'opérateur : rappel sonne sur le simulateur"
    return "Playback(rgph/hors_service)  ; pas d'opérateur configuré"


def ice_hotes() -> str:
    """Remplace l'adresse du conteneur par l'adresse publique dans les candidats ICE (WebRTC)."""
    adresse = env("SIP_ADRESSE_EXTERNE")
    if not adresse:
        return "; SIP_ADRESSE_EXTERNE vide : candidats ICE non modifiés."
    interne = socket.gethostbyname(socket.gethostname())
    return f"[ice_host_candidates]\n{interne} => {adresse}"


def membres_file(nombre: int) -> str:
    return "\n".join(
        f"member => PJSIP/poste{n},0,Poste {n},PJSIP/poste{n}" for n in range(1, nombre + 1)
    )


def valeurs() -> dict[str, str]:
    secret = env("SECRET_POSTES")
    if len(secret) < 32:
        raise SystemExit("SECRET_POSTES manquant ou trop court (32 caractères au moins).")
    if not env("CLE_API_CENTRE_ECOUTE"):
        raise SystemExit("CLE_API_CENTRE_ECOUTE manquante.")
    nombre = int(env("NB_POSTES", "6"))
    stun = env("STUN_SERVEUR")
    return {
        "API_URL": env("API_URL", "http://api:8000"),
        "CLE_API": env("CLE_API_CENTRE_ECOUTE"),
        "RAPPEL_APRES_SECONDES": env("RAPPEL_APRES_SECONDES", "180"),
        "POSTES": section_postes(secret, nombre, env("SIP_DOMAINE", "rgph2.local")),
        "SIMULATEUR": section_simulateur(env("SIMULATEUR_MDP")),
        "OPERATEUR": section_operateur(),
        "ADRESSE_EXTERNE": adresse_externe(),
        "MEMBRES": membres_file(nombre),
        "RTP_DEBUT": env("RTP_DEBUT", "10000"),
        "RTP_FIN": env("RTP_FIN", "10050"),
        "STUN": f"stunaddr={stun}" if stun else "; pas de serveur STUN",
        "APPEL_SORTANT": appel_sortant(),
        "ICE_HOTES": ice_hotes(),
    }


def ecrire_configuration() -> None:
    v = valeurs()
    for modele in sorted(MODELES.glob("*.conf")):
        if modele.name == "extensions_simulation.conf":
            continue
        (CONF / modele.name).write_text(rendre(modele.read_text(encoding="utf-8"), v),
                                        encoding="utf-8")
    simulation = CONF / "extensions_simulation.conf"
    if vrai("TELEPHONIE_SIMULATION"):
        shutil.copy(MODELES / "extensions_simulation.conf", simulation)
    else:
        simulation.write_text("; Simulation désactivée (TELEPHONIE_SIMULATION=false).\n")
    # Menu de secours tant que la première synchronisation du SVI n'a pas réussi.
    svi = CONF / "extensions_svi.conf"
    if not svi.exists():
        svi.write_text("[svi-langue]\nexten => s,1,Set(__LANGUE=fr)\n"
                       " same => n,Goto(file-attente,s,1)\n")


def installer_messages() -> None:
    """Pour chaque langue : enregistrement du locuteur, sinon français, sinon synthèse provisoire."""
    langues = touches_langues(env("SVI_TOUCHES_LANGUES", "fr:1,ln:2,sw:3,kg:4,lua:5"))
    phrases = dict(PHRASES)
    for code in dict.fromkeys(["fr", *langues]):
        destination = dossier_rgph(code)
        destination.mkdir(parents=True, exist_ok=True)
        textes = {**phrases, "choix_langue": phrase_choix_langue(code, langues.get(code, 0))}
        for nom, texte in textes.items():
            cible = destination / f"{nom}.wav"
            source = (source_enregistree(MESSAGES / code, nom)
                      or (None if nom == "choix_langue" else source_enregistree(MESSAGES / "fr", nom)))
            if source:
                convertir(source, cible)
            elif code != "fr" and nom != "choix_langue" and (dossier_rgph("fr") / cible.name).exists():
                shutil.copy(dossier_rgph("fr") / cible.name, cible)
            else:
                synthetiser(texte, cible)
        (destination / "svi").mkdir(exist_ok=True)


def preparer_dossiers() -> None:
    import grp  # propre à Linux : importé ici pour que le module reste testable ailleurs

    ENREGISTREMENTS.mkdir(parents=True, exist_ok=True)
    gid = grp.getgrnam(GROUPE_MEDIA).gr_gid
    # Propriétaire asterisk (Asterisk ne garde pas ses groupes secondaires), groupe
    # partagé en écriture avec bit setgid : l'API (même groupe) peut supprimer les fichiers.
    shutil.chown(ENREGISTREMENTS, "asterisk", gid)
    ENREGISTREMENTS.chmod(0o2775)
    for dossier in Path("/var/lib/asterisk/sounds").glob("*/rgph"):
        shutil.chown(dossier, "asterisk", "asterisk")


if __name__ == "__main__":
    ecrire_configuration()
    installer_messages()
    preparer_dossiers()
    print("Asterisk configuré.", flush=True)
