# Passerelle SMS Kannel 1.4.5 (paquet Debian), hébergée avec le cœur.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends kannel kannel-extras ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    # Simulateur d'opérateur (tests) : envoie des SMS au bearerbox et affiche les réponses.
    && ln -s /usr/lib/kannel/test/fakesmsc /usr/local/bin/fakesmsc

COPY kannel.conf.modele smsc-simulation.conf smsc-operateur.conf /etc/kannel/modeles/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /var/spool/kannel && chown kannel /var/spool/kannel

USER kannel
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
