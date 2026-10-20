#!/bin/sh
# Démarrage du serveur téléphonique :
#  1. configuration d'Asterisk à partir des variables d'environnement ;
#  2. première synchronisation du serveur vocal (menu lu dans l'API du cœur) ;
#  3. synchronisation périodique en arrière-plan, puis Asterisk au premier plan.
set -e

python3 /opt/rgph/synchro/configurer.py
python3 /opt/rgph/synchro/synchroniser_svi.py || echo "SVI : première synchronisation impossible, nouvel essai plus tard."
python3 /opt/rgph/synchro/synchroniser_svi.py --boucle "${SVI_SYNCHRO_SECONDES:-300}" &

exec asterisk -f -U asterisk -G asterisk
