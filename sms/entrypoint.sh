#!/bin/bash
# Rend la configuration de Kannel puis lance ses deux processus (bearerbox et smsbox).
set -euo pipefail

: "${KANNEL_MDP:?KANNEL_MDP à définir dans .env}"
: "${CLES_API:?CLES_API à définir dans .env}"
API_URL="${API_URL:-http://api:8000}"
KANNEL_ADMIN_MDP="${KANNEL_ADMIN_MDP:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')}"

# La clé du canal sms est prise dans CLES_API (« sms:cle,… ») : une seule source.
CLE_SMS="$(echo "$CLES_API" | tr ',' '\n' | sed -n 's/^[[:space:]]*sms[[:space:]]*:[[:space:]]*//p' | head -n 1)"
if [ -z "$CLE_SMS" ]; then
    echo "CLES_API ne contient pas de clé pour le canal sms (sms:cle)." >&2
    exit 1
fi

MODELES=/etc/kannel/modeles
if [ "${SMS_SIMULATION:-false}" = "true" ]; then
    echo "Passerelle SMS en SIMULATION (aucun opérateur)."
    SMSC="$(cat "$MODELES/smsc-simulation.conf")"
elif [ -n "${OPERATEUR_SMPP_HOTE:-}" ]; then
    SMSC="$(cat "$MODELES/smsc-operateur.conf")"
else
    echo "Aucune liaison opérateur (OPERATEUR_SMPP_HOTE vide) : les SMS restent en file d'attente."
    SMSC=""
fi

# Échappe une valeur pour le remplacement sed (délimiteur « | »).
echapper() { printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'; }

rendre() {
    local texte="$1"
    for nom in KANNEL_MDP KANNEL_ADMIN_MDP API_URL CLE_SMS OPERATEUR_SMPP_HOTE OPERATEUR_SMPP_PORT \
               OPERATEUR_SMPP_UTILISATEUR OPERATEUR_SMPP_MDP OPERATEUR_SMPP_SYSTEM_TYPE; do
        texte="$(printf '%s' "$texte" | sed -e "s|{{$nom}}|$(echapper "${!nom:-}")|g")"
    done
    printf '%s\n' "$texte"
}

OPERATEUR_SMPP_PORT="${OPERATEUR_SMPP_PORT:-2775}"
CONF=/tmp/kannel.conf
# Kannel sépare ses groupes par une ligne vide : on la remet entre chaque partie.
{
    rendre "$(sed -n '1,/{{SMSC}}/p' "$MODELES/kannel.conf.modele" | sed '$d')"
    echo
    if [ -n "$SMSC" ]; then rendre "$SMSC"; echo; fi
    rendre "$(sed -n '/{{SMSC}}/,$p' "$MODELES/kannel.conf.modele" | sed '1d')"
} > "$CONF"
chmod 600 "$CONF"

# -v 2 : avertissements seulement à l'écran (sinon numéros et textes y apparaîtraient).
bearerbox -v 2 "$CONF" &
sleep 2
smsbox -v 2 "$CONF" &
# Si l'un des deux s'arrête, le conteneur s'arrête (et Docker le relance).
wait -n
exit 1
