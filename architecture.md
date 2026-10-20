# Architecture du système — RGPH-2

Oct 3, 2026 · @Wilfried HOUEDANOU

Le système repose sur un cœur unique, une base de connaissances validée par le BCR, auquel six canaux se branchent. Le citoyen reçoit la même réponse officielle qu'il passe par un téléphone basique, WhatsApp, un kiosque ou un agent. Version de travail pour discussion, avant la Phase 1.

## Vue d'ensemble

&#91;embedded content: vue d'ensemble · 6 canaux, 1 cœur commun, 2 outils pour le Ministère\]

Tout ce que le citoyen demande passe par le même cœur. Le Ministère met à jour les contenus dans le CMS et suit l'usage sur le tableau de bord.

## Ce que vit le citoyen, canal par canal

| Canal | Pour qui | Ce que le citoyen peut faire | Connexion requise |
| --- | --- | --- | --- |
| USSD/SMS | Tout téléphone, même sans internet | Obtenir l'information générale, le calendrier de passage, vérifier un agent, signaler un ménage non visité | Réseau mobile seul, sans data |
| WhatsApp | Zones urbaines et semi-urbaines | Poser ses questions, recevoir des rappels de passage, voir des contenus audio et vidéo en langue locale, passer à un humain | Data mobile |
| Portail web et chatbot | Smartphones, partenaires | Les mêmes services, en texte ou en audio, en 12 langues | Data, page légère pour la 2G |
| Kiosques OKAPI | 50 territoires prioritaires | Consulter la FAQ complète hors-ligne, avec l'aide d'un Ambassadeur | Aucune ; synchronisation au retour du réseau |
| Ambassadeurs | Villages et quartiers sans accès numérique | Relais en personne, remontée des rumeurs et des doutes | Aucune |
| Centre d'écoute | Cas sensibles ou complexes | Numéro vert gratuit, réponses validées par le BCR | Téléphone |

## Six choix d'architecture et leurs raisons

| Choix | Pourquoi | Ce qu'on écarte |
| --- | --- | --- |
| Un seul cœur pour tous les canaux | Une réponse validée une fois est servie partout ; signalements et statistiques arrivent au même endroit | Un système par canal : réponses qui divergent, coûts multipliés |
| Un seul bloc logiciel découpé en modules (monolithe modulaire) | Équipe réduite, charge concentrée sur mai-juin 2027, transfert à une équipe nationale de 8 à 10 personnes : un seul déploiement à maintenir | Microservices : surcoût d'exploitation sans bénéfice à cette échelle |
| Base de connaissances fermée | Le chatbot ne répond qu'avec des contenus validés par le BCR, sinon il passe la main à un humain | IA générative libre : risque d'inventer une date de passage ou une information officielle |
| Kiosques hors-ligne d'abord | Les zones prioritaires sont les moins connectées ; le kiosque fonctionne sans réseau, sur batterie et panneau solaire | Un kiosque qui exige internet |
| Données hébergées en RDC | Exigence de localisation de l'Ordonnance-loi n° 23/010 ; arbitrage final en cadrage selon l'infrastructure disponible | Services hébergés à l'étranger, dont l'IA vocale externe |
| Briques open source éprouvées, intégration sur mesure | Moins de risque et de coût ; l'équipe du Ministère peut les reprendre. Liste proposée, à valider en Phase 1 : RapidPro, Rasa, Chatwoot, Directus ou Strapi, Matomo, PostgreSQL | Tout développer sur mesure |

## Données et conformité

- **Collecté** : numéros de téléphone, interactions, signalements localisés, statistiques d'usage par canal, langue et territoire.
- **Jamais collecté** : nom, pièce d'identité, composition du ménage.
- **Jamais croisé** avec les données du dénombrement, ni avec un fichier d'identification, fiscal ou électoral.
- **Statistiques** jamais publiées à une maille inférieure au territoire.
- **Conservation** : suppression au plus tard six mois après la publication des résultats du RGPH-2.
- **Responsable du traitement** : l'INS-BCR, avec un point focal protection des données. Audit de sécurité avant la mise en ligne de chaque canal numérique.

## Ce qui est construit, assemblé ou négocié

| Brique | Approche | Point d'attention |
| --- | --- | --- |
| USSD/SMS | Passerelle opérateur et application sur mesure | Dépend de l'accord des opérateurs (Airtel, Vodacom, Orange) et de l'accès au code court auprès de l'ARPTC |
| WhatsApp | API officielle et bot relié à la base de connaissances | Compte ouvert au nom du client |
| Chatbot web | Briques open source et base fermée | Reconnaissance des intentions à évaluer langue par langue |
| Base de connaissances et CMS | CMS open source configuré | Le Ministère modifie et valide sans passer par le prestataire |
| Kiosques | Application tablette sur mesure, hors-ligne, avec synchronisation | Brique technique la plus délicate : conflits de synchronisation, mise à jour de la FAQ |
| Tableau de bord | Sur mesure, sur le même cœur | Statistiques agrégées pour le Ministère et l'UNFPA |
| Centre d'écoute | Logiciel de centre d'appel et numéro vert | Numéro vert à négocier avec les opérateurs |

## Risques techniques et réponses

| Risque | Réponse prévue |
| --- | --- |
| Les opérateurs refusent le zero-rating USSD | Repli sur SMS générique ; kiosques et Ambassadeurs deviennent le canal principal dans les zones non connectées |
| Le chatbot donne une réponse erronée | Base fermée et validée ; escalade automatique vers le centre d'écoute quand la confiance est faible |
| La voix en langues locales est mal reconnue (très peu de données d'entraînement, de l'ordre de quelques heures pour le lingala) | Recommandation : audio en sortie uniquement, enregistré par des locuteurs natifs ; pas de reconnaissance vocale en entrée pendant le pilote |
| Kiosques volés ou vandalisés | Assurance, lieux sécurisés (écoles, mairies), remplacement rapide via la contingence |
| L'infrastructure locale est insuffisante pour l'hébergement | Hébergement redondant, plan de continuité, arbitrage en cadrage |
| L'équipe du Ministère est insuffisamment formée | Un seul bloc à maintenir, documentation exhaustive, mentorat de six mois après le dénombrement |

## À décider en Phase 1

- Où héberger exactement en RDC : centre de données local ou cloud avec région locale ?
- Quel opérateur négocier en premier pour le code USSD et le zero-rating ?
- Pour quelles langues enregistrer l'audio d'abord ?
- Quelles briques open source retenir après les prototypes ?
- Quel niveau de disponibilité exiger pendant le pic de mai-juin 2027 ?
