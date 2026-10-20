// Service worker de l'application de terrain : l'application s'ouvre sans réseau.
//
// - Coquille (page, script, style, charte) : servie depuis le cache, puis rafraîchie
//   en arrière-plan quand le réseau répond. Une nouvelle version de l'application
//   s'affiche donc au lancement suivant.
// - Audio des réponses (autre domaine) : servi depuis le cache rempli par app.js.
// - API (/v1/) : jamais interceptée. app.js gère lui-même l'absence de réseau.
"use strict";

var CACHE_APPLICATION = "terrain-application-v1";
var CACHE_MEDIAS = "terrain-medias";
var COQUILLE = [
  "/terrain/", "/terrain/app.js", "/terrain/app.css", "/terrain/manifest.webmanifest",
  "/charte/charte.css", "/charte/cooper-hewitt-medium.woff2", "/charte/cooper-hewitt-semibold.woff2",
  "/charte/armoiries-blanc-54.png", "/charte/armoiries-blanc-54@2x.png", "/charte/favicon.png",
  "/charte/icone-192.png", "/charte/icone-512.png"
];

self.addEventListener("install", function (evenement) {
  evenement.waitUntil(caches.open(CACHE_APPLICATION).then(function (cache) {
    return cache.addAll(COQUILLE);
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (evenement) {
  evenement.waitUntil(caches.keys().then(function (noms) {
    return Promise.all(noms.filter(function (nom) {
      return nom.indexOf("terrain-application-") === 0 && nom !== CACHE_APPLICATION;
    }).map(function (nom) { return caches.delete(nom); }));
  }).then(function () { return self.clients.claim(); }));
});

function coquille(requete) {
  // /terrain/index.html et /terrain/?… : même page.
  var url = new URL(requete.url);
  var cle = url.pathname === "/terrain/index.html" ? "/terrain/" : url.pathname;
  return caches.open(CACHE_APPLICATION).then(function (cache) {
    return cache.match(cle).then(function (enCache) {
      var reseau = fetch(requete).then(function (reponse) {
        if (reponse.ok) cache.put(cle, reponse.clone());
        return reponse;
      });
      if (enCache) {
        reseau.catch(function () {});
        return enCache;
      }
      return reseau;
    });
  });
}

// Lecture partielle (Range) d'un audio en cache : les lecteurs la demandent souvent.
function partielle(requete, reponse) {
  var plage = /bytes=(\d*)-(\d*)/.exec(requete.headers.get("range") || "");
  if (!plage || reponse.type === "opaque") return reponse;
  return reponse.blob().then(function (contenu) {
    var debut = plage[1] ? Number(plage[1]) : 0;
    var fin = plage[2] ? Number(plage[2]) : contenu.size - 1;
    return new Response(contenu.slice(debut, fin + 1), {
      status: 206,
      headers: {
        "Content-Type": reponse.headers.get("Content-Type") || "audio/mpeg",
        "Content-Range": "bytes " + debut + "-" + fin + "/" + contenu.size,
        "Content-Length": String(fin - debut + 1)
      }
    });
  });
}

self.addEventListener("fetch", function (evenement) {
  var requete = evenement.request;
  if (requete.method !== "GET") return;
  var url = new URL(requete.url);
  if (url.origin === self.location.origin) {
    if (url.pathname.indexOf("/terrain/") === 0 || url.pathname.indexOf("/charte/") === 0) {
      evenement.respondWith(coquille(requete));
    }
    return;
  }
  evenement.respondWith(caches.open(CACHE_MEDIAS).then(function (cache) {
    return cache.match(requete.url).then(function (enCache) {
      return enCache ? partielle(requete, enCache) : fetch(requete);
    });
  }));
});
