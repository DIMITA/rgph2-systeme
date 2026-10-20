# Données de référence

## territoires.csv : échantillon, à remplacer

Ce fichier contient les **26 provinces** de la RDC et **quelques territoires et villes** pour le développement et les tests.
**Les codes sont provisoires.** Ce ne sont pas les codes officiels de l'INS.

Avant la mise en service :

1. Remplacer le contenu du fichier par le référentiel officiel de l'INS (toutes les villes et tous les territoires), en gardant les mêmes colonnes :

   | Colonne | Contenu |
   | --- | --- |
   | `province_code` | Code officiel de la province |
   | `province_nom` | Nom de la province |
   | `territoire_code` | Code officiel du territoire ou de la ville (vide pour déclarer seulement la province) |
   | `territoire_nom` | Nom du territoire ou de la ville |
   | `type` | `territoire` ou `ville` |

2. Lancer l'import (il ne crée pas de doublons : les codes existants sont mis à jour) :

   ```
   docker compose run --rm api python -m coeur.territoires importer donnees/territoires.csv
   ```

Ne jamais ajouter de niveau plus fin (secteur, chefferie, groupement, village) dans ce référentiel. Le territoire est la maille la plus fine des statistiques.
