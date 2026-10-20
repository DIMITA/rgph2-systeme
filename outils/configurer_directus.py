"""Configure Directus pour la base de connaissances du RGPH-2.

Les tables sont créées par les migrations de l'API ; ce script règle seulement
leur présentation dans Directus et crée les rôles et droits :

- Rédacteur : rédige et modifie les contenus en « brouillon » ou « en revue ».
  Il ne peut ni publier, ni modifier un contenu publié, ni toucher aux formulations.
- Validateur BCR : seul habilité à passer un contenu ou une traduction à « publié ».
- Lecteur : consultation seule.
- Tableau de bord : aucun accès aux contenus ; sert seulement à se connecter au
  tableau de bord du Ministère (ex. comptes UNFPA).
- Agent centre d'appels : console des agents (téléphone, FAQ, signalements, rappels).
- Superviseur qualité : écoute des conversations enregistrées (chaque écoute est journalisée).

Le calendrier de passage suit le même circuit que les contenus (rédigé, puis publié par
le Validateur BCR). La liste des territoires proposée est lue dans l'API (API_URL) :
relancer le script après chaque import du référentiel des territoires.

Idempotent : on peut le relancer après chaque mise à jour (les droits des trois
rôles sont recréés à l'identique).

Variables : DIRECTUS_URL, DIRECTUS_ADMIN_EMAIL, DIRECTUS_ADMIN_MDP, API_URL
"""

import csv
import os
import sys
import time
from pathlib import Path

import httpx

STATUTS = [
    {"text": "Brouillon", "value": "brouillon", "color": "#9E9E9E"},
    {"text": "En revue", "value": "en_revue", "color": "#FFA000"},
    {"text": "Publié (validé BCR)", "value": "publie", "color": "#2E7D32"},
    {"text": "Archivé", "value": "archive", "color": "#616161"},
]
NON_PUBLIES = ["brouillon", "en_revue"]
CHAMP_STATUT = {
    "interface": "select-dropdown",
    "options": {"choices": STATUTS},
    "display": "labels",
    "display_options": {"showAsDot": True, "choices": STATUTS},
    "width": "half",
    "required": True,
}

COLLECTIONS = {
    "contenus": {
        "icon": "quiz",
        "note": "Sujets de la FAQ. Un contenu n'est servi aux citoyens que s'il est « Publié ».",
        "display_template": "{{cle}}",
        "archive_field": "statut",
        "archive_value": "archive",
        "unarchive_value": "brouillon",
        "sort": 1,
    },
    "contenus_traductions": {
        "icon": "translate",
        "note": "Texte d'un contenu dans une langue. Chaque langue est validée séparément.",
        "display_template": "{{langue_code}} — {{question}}",
        "sort": 2,
    },
    "formulations": {
        "icon": "manage_search",
        "note": "Autres façons de poser la question, pour aider la recherche.",
        "display_template": "{{texte}}",
        "sort": 3,
    },
    "langues": {
        "icon": "language",
        "note": "Langues proposées aux citoyens.",
        "display_template": "{{nom}} ({{code}})",
        "sort": 4,
    },
    "calendrier_passages": {
        "icon": "event",
        "note": "Dates de passage des agents par territoire (USSD, SMS, WhatsApp). "
                "Servies seulement si « Publié ».",
        "display_template": "{{territoire_code}} : {{date_debut}} → {{date_fin}}",
        "archive_field": "statut",
        "archive_value": "archive",
        "unarchive_value": "brouillon",
        "sort": 5,
    },
}

CHAMPS = {
    ("contenus", "id"): {"hidden": True, "readonly": True},
    ("contenus", "cle"): {"note": "Identifiant court et stable, ex. calendrier-passage", "width": "half", "required": True},
    ("contenus", "categorie"): {
        "interface": "select-dropdown",
        "options": {"allowOther": True, "choices": [
            {"text": t, "value": v} for t, v in [
                ("Général", "general"), ("Calendrier", "calendrier"), ("Agents", "agents"),
                ("Confidentialité", "confidentialite"), ("Signalement", "signalement"),
            ]
        ]},
        "width": "half",
    },
    ("contenus", "statut"): CHAMP_STATUT,
    ("contenus", "ordre_svi"): {
        "interface": "input", "width": "half",
        "options": {"min": 1, "max": 8},
        "note": "Position dans le menu du serveur vocal (1 à 8). Vide : absent du téléphone.",
    },
    ("contenus", "date_creation"): {"special": ["date-created"], "readonly": True, "width": "half"},
    ("contenus", "date_maj"): {"special": ["date-updated"], "readonly": True, "width": "half"},
    ("contenus_traductions", "id"): {"hidden": True, "readonly": True},
    ("contenus_traductions", "contenu_id"): {"interface": "select-dropdown-m2o", "width": "half", "required": True,
                                             "options": {"template": "{{cle}}"}},
    ("contenus_traductions", "langue_code"): {"interface": "select-dropdown-m2o", "width": "half", "required": True,
                                              "options": {"template": "{{nom}}"}},
    ("contenus_traductions", "question"): {"interface": "input-multiline", "required": True},
    ("contenus_traductions", "reponse"): {"interface": "input-multiline", "required": True,
                                          "note": "Réponse complète (web, WhatsApp, kiosque)."},
    ("contenus_traductions", "reponse_courte"): {"interface": "input", "options": {"softLength": 160},
                                                 "note": "160 caractères au plus : utilisée pour l'USSD et le SMS."},
    ("contenus_traductions", "audio_url"): {"note": "Lien vers l'enregistrement audio (locuteur natif)."},
    ("contenus_traductions", "audio_question_url"): {
        "note": "Question enregistrée, annoncée dans le menu du serveur vocal (format wav ou mp3)."},
    ("contenus_traductions", "statut"): CHAMP_STATUT,
    ("contenus_traductions", "date_maj"): {"special": ["date-updated"], "readonly": True, "width": "half"},
    ("formulations", "id"): {"hidden": True, "readonly": True},
    ("formulations", "contenu_id"): {"interface": "select-dropdown-m2o", "width": "half", "required": True,
                                     "options": {"template": "{{cle}}"}},
    ("formulations", "langue_code"): {"interface": "select-dropdown-m2o", "width": "half", "required": True,
                                      "options": {"template": "{{nom}}"}},
    ("calendrier_passages", "id"): {"hidden": True, "readonly": True},
    ("calendrier_passages", "date_debut"): {"interface": "datetime", "width": "half", "required": True},
    ("calendrier_passages", "date_fin"): {"interface": "datetime", "width": "half", "required": True,
                                          "note": "Dernier jour de passage (inclus)."},
    ("calendrier_passages", "statut"): CHAMP_STATUT,
    ("calendrier_passages", "date_maj"): {"special": ["date-updated"], "readonly": True, "width": "half"},
}

# Champs « liste » ajoutés sur un contenu pour éditer ses traductions et formulations.
LISTES = {
    ("contenus_traductions", "contenu_id"): ("traductions", "Traductions"),
    ("formulations", "contenu_id"): ("formulations", "Formulations"),
}

TOUTES = list(COLLECTIONS)
FILTRE_NON_PUBLIE = {"statut": {"_in": NON_PUBLIES}}


def droits_redacteur() -> list[dict]:
    droits = [{"collection": c, "action": "read"} for c in TOUTES]
    for collection in ("contenus", "contenus_traductions", "calendrier_passages"):
        droits.append({"collection": collection, "action": "create", "validation": FILTRE_NON_PUBLIE})
        droits.append({
            "collection": collection, "action": "update",
            "permissions": FILTRE_NON_PUBLIE, "validation": FILTRE_NON_PUBLIE,
        })
    return droits


def droits_validateur() -> list[dict]:
    droits = [{"collection": c, "action": a} for c in TOUTES for a in ("create", "read", "update")]
    droits += [{"collection": c, "action": "delete"}
               for c in ("contenus_traductions", "formulations", "calendrier_passages")]
    return droits


def droits_lecteur() -> list[dict]:
    return [{"collection": c, "action": "read"} for c in TOUTES]


ROLES = {
    "Rédacteur": ("edit_note", "Rédige les contenus ; ne peut pas publier.", droits_redacteur),
    "Validateur BCR": ("verified", "Valide et publie les contenus au nom du BCR.", droits_validateur),
    "Lecteur": ("visibility", "Consultation seule.", droits_lecteur),
    "Tableau de bord": ("monitoring", "Accès au tableau de bord du Ministère, pas aux contenus.",
                        lambda: []),
    "Agent centre d'appels": ("support_agent", "Console des agents du numéro vert.", lambda: []),
    "Superviseur qualité": ("headphones", "Écoute des conversations enregistrées.", lambda: []),
}


class Directus:
    def __init__(self, url: str, email: str, mdp: str):
        self.http = httpx.Client(base_url=url, timeout=30)
        jeton = self._attendre_et_connecter(email, mdp)
        self.http.headers["Authorization"] = f"Bearer {jeton}"

    def _attendre_et_connecter(self, email: str, mdp: str) -> str:
        for _ in range(60):
            try:
                r = self.http.post("/auth/login", json={"email": email, "password": mdp})
                if r.status_code == 200:
                    return r.json()["data"]["access_token"]
            except httpx.TransportError:
                pass
            time.sleep(2)
        sys.exit("Impossible de se connecter à Directus.")

    def appel(self, methode: str, chemin: str, **kwargs):
        r = self.http.request(methode, chemin, **kwargs)
        if r.status_code >= 400:
            raise RuntimeError(f"{methode} {chemin} → {r.status_code} {r.text}")
        return r.json().get("data") if r.content else None

    def premier(self, chemin: str, champ: str, valeur: str):
        trouves = self.appel("GET", chemin, params={f"filter[{champ}][_eq]": valeur, "limit": 1})
        return trouves[0] if trouves else None


def configurer_collections(d: Directus) -> None:
    for collection, meta in COLLECTIONS.items():
        d.appel("PATCH", f"/collections/{collection}", json={"meta": meta})
    for (collection, champ), meta in CHAMPS.items():
        d.appel("PATCH", f"/fields/{collection}/{champ}", json={"meta": meta})
    existants = {f["field"] for f in d.appel("GET", "/fields/contenus")}
    for (collection, champ), (liste, libelle) in LISTES.items():
        if liste not in existants:
            d.appel("POST", "/fields/contenus", json={
                "field": liste, "type": "alias",
                "meta": {"special": ["o2m"], "interface": "list-o2m",
                         "options": {"template": "{{langue_code}} — {{question}}"
                                     if liste == "traductions" else "{{texte}}"},
                         "note": libelle},
            })
        d.appel("PATCH", f"/relations/{collection}/{champ}", json={
            "collection": collection, "field": champ, "related_collection": "contenus",
            # On redonne la règle de suppression : Directus recrée la clé étrangère.
            "schema": {"on_delete": "CASCADE"},
            "meta": {"many_collection": collection, "many_field": champ,
                     "one_collection": "contenus", "one_field": liste},
        })


def choix_territoires(api_url: str) -> list[dict]:
    """Territoires du référentiel (API), sinon ceux du fichier d'exemple du dépôt."""
    try:
        provinces = httpx.get(f"{api_url}/v1/territoires", timeout=10).raise_for_status().json()
    except httpx.HTTPError:
        chemin = Path(__file__).resolve().parents[1] / "donnees" / "territoires.csv"
        with chemin.open(encoding="utf-8-sig") as f:
            lignes = [l for l in csv.DictReader(f) if l["territoire_code"]]
        return [{"text": f"{l['province_nom']} — {l['territoire_nom']}",
                 "value": l["territoire_code"]} for l in lignes]
    return [{"text": f"{p['nom']} — {t['nom']}", "value": t["code"]}
            for p in provinces for t in p["territoires"]]


def configurer_calendrier(d: Directus, api_url: str) -> None:
    choix = choix_territoires(api_url)
    d.appel("PATCH", "/fields/calendrier_passages/territoire_code", json={"meta": {
        "interface": "select-dropdown", "display": "labels", "width": "half", "required": True,
        "options": {"choices": choix}, "display_options": {"choices": choix},
        "note": "Territoire ou ville du référentiel.",
    }})
    print(f"Calendrier configuré ({len(choix)} territoires proposés).")


def configurer_roles(d: Directus) -> None:
    for nom, (icone, description, droits) in ROLES.items():
        politique = d.premier("/policies", "name", nom)
        if politique is None:
            politique = d.appel("POST", "/policies", json={
                "name": nom, "icon": icone, "description": description,
                "app_access": True, "admin_access": False,
            })
        anciens = d.appel("GET", "/permissions", params={
            "filter[policy][_eq]": politique["id"], "limit": -1, "fields": "id",
        })
        if anciens:
            d.appel("DELETE", "/permissions", json=[p["id"] for p in anciens])
        if droits():
            d.appel("POST", "/permissions", json=[
                {"policy": politique["id"], "fields": ["*"], "permissions": {}, "validation": {},
                 **droit}
                for droit in droits()
            ])
        if d.premier("/roles", "name", nom) is None:
            d.appel("POST", "/roles", json={
                "name": nom, "icon": icone, "description": description,
                "policies": [{"policy": politique["id"]}],
            })
        print(f"Rôle « {nom} » configuré ({len(droits())} droits).")


def main() -> None:
    d = Directus(
        os.environ.get("DIRECTUS_URL", "http://localhost:8055"),
        os.environ["DIRECTUS_ADMIN_EMAIL"],
        os.environ["DIRECTUS_ADMIN_MDP"],
    )
    configurer_collections(d)
    print("Collections configurées.")
    configurer_calendrier(d, os.environ.get("API_URL", "http://localhost:8000"))
    configurer_roles(d)


if __name__ == "__main__":
    main()
