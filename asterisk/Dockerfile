# Serveur téléphonique du centre d'appels RGPH-2 : Asterisk 20 (version maintenue à long terme).
FROM alpine:3.20

RUN apk add --no-cache \
        asterisk asterisk-curl asterisk-srtp asterisk-sounds-moh \
        python3 ffmpeg espeak-ng tzdata \
    # Groupe partagé avec le conteneur de l'API, qui purge les enregistrements.
    && addgroup -g 1500 rgph-media \
    && addgroup asterisk rgph-media

COPY config/ /opt/rgph/modeles/
COPY messages/ /opt/rgph/messages/
COPY synchro/ /opt/rgph/synchro/
COPY entrypoint.sh /opt/rgph/entrypoint.sh
RUN chmod +x /opt/rgph/entrypoint.sh /opt/rgph/synchro/question_vocale.py

# 5060/udp : SIP (opérateur, simulateur) ; 8088 : WebSocket des postes d'agents ;
# 10000-10050/udp : flux audio (RTP).
EXPOSE 5060/udp 8088 10000-10050/udp
ENTRYPOINT ["/opt/rgph/entrypoint.sh"]
