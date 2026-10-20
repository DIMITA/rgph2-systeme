#!/bin/sh
# Exécuté une seule fois, à la création du volume PostgreSQL.
# Trois rôles, trois niveaux de droits :
#   - $POSTGRES_USER (rgph_admin) : propriétaire, utilisé seulement pour les migrations ;
#   - rgph_directus : le CMS, lit et écrit les contenus (schéma public), ne voit pas le schéma coeur ;
#   - rgph_api : l'API, lit les contenus et écrit dans le schéma coeur.
# Les droits sur les tables sont donnés par les migrations.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE ROLE rgph_api LOGIN PASSWORD '${RGPH_API_MDP}';
	CREATE ROLE rgph_directus LOGIN PASSWORD '${RGPH_DIRECTUS_MDP}';

	REVOKE ALL ON SCHEMA public FROM PUBLIC;
	GRANT USAGE, CREATE ON SCHEMA public TO rgph_directus;
	GRANT USAGE ON SCHEMA public TO rgph_api;

	CREATE SCHEMA IF NOT EXISTS coeur AUTHORIZATION "$POSTGRES_USER";
	REVOKE ALL ON SCHEMA coeur FROM PUBLIC;
	GRANT USAGE ON SCHEMA coeur TO rgph_api;
EOSQL
