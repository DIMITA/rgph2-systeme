"""Configure Directus pour la base de connaissances du RGPH-2.

Les tables sont créées par les migrations de l'API ; ce script règle seulement
leur présentation dans Directus et crée les rôles et droits :

- Rédacteur : rédige et modifie les contenus en « brouillon » ou « en revue ».
  Il ne peut ni publier, ni modifier un contenu publié, ni toucher aux formulations.
- Validateur BCR : seul habilité à passer un contenu ou une traduction à « publié ».
- Lecteur : consultation seule.

Idempotent : on peut le relancer après chaque mise à jour (les droits des trois
rôles sont recréés à l'identique).

Variables : DIRECTUS_URL, DIRECTUS_ADMIN_EMAIL, DIRECTUS_ADMIN_MDP
"""

import os
import sys
import time

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
    ("contenus_traductions", "statut"): CHAMP_STATUT,
    ("contenus_traductions", "date_maj"): {"special": ["date-updated"], "readonly": True, "width": "half"},
    ("formulations", "id"): {"hidden": True, "readonly": True},
    ("formulations", "contenu_id"): {"interface": "select-dropdown-m2o", "width": "half", "required": True,
                                     "options": {"template": "{{cle}}"}},
    ("formulations", "langue_code"): {"interface": "select-dropdown-m2o", "width": "half", "required": True,
                                      "options": {"template": "{{nom}}"}},
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
    for collection in ("contenus", "contenus_traductions"):
        droits.append({"collection": collection, "action": "create", "validation": FILTRE_NON_PUBLIE})
        droits.append({
            "collection": collection, "action": "update",
            "permissions": FILTRE_NON_PUBLIE, "validation": FILTRE_NON_PUBLIE,
        })
    return droits


def droits_validateur() -> list[dict]:
    droits = [{"collection": c, "action": a} for c in TOUTES for a in ("create", "read", "update")]
    droits += [{"collection": c, "action": "delete"} for c in ("contenus_traductions", "formulations")]
    return droits


def droits_lecteur() -> list[dict]:
    return [{"collection": c, "action": "read"} for c in TOUTES]


ROLES = {
    "Rédacteur": ("edit_note", "Rédige les contenus ; ne peut pas publier.", droits_redacteur),
    "Validateur BCR": ("verified", "Valide et publie les contenus au nom du BCR.", droits_validateur),
    "Lecteur": ("visibility", "Consultation seule.", droits_lecteur),
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
        d.appel("POST", "/permissions", json=[
            {"policy": politique["id"], "fields": ["*"], "permissions": {}, "validation": {}, **droit}
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
    configurer_roles(d)


if __name__ == "__main__":
    main()
