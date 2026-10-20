// Console des agents : téléphone dans le navigateur (JsSIP / WebRTC) et outils d'appel.
// Configuration lue dans les attributs data-* de #console. Aucun innerHTML : tout le
// texte venant du serveur est inséré avec textContent.
(function () {
  "use strict";
  var racine = document.getElementById("console");
  if (!racine || !window.JsSIP) return;
  var d = racine.dataset;
  function $(id) { return document.getElementById(id); }

  var session = null;          // appel en cours (entrant ou sortant)
  var sortant = false;         // l'appel en cours est un rappel passé par l'agent
  var enPause = false;
  var aQualifier = false;      // un appel entrant terminé attend sa qualification
  var appelCourant = null;     // { reference, langue_nom } fourni par le serveur
  var sondage = null;

  // ---------- État affiché ----------

  function etat(code, texte) {
    var el = $("etat");
    el.dataset.etat = code;
    el.textContent = texte;
  }

  function boutons(visibles) {
    ["decrocher", "raccrocher", "muet"].forEach(function (id) {
      $(id).hidden = !visibles[id];
    });
  }

  function etatRepos() {
    if (aQualifier) return;
    if (!ua.isRegistered()) return etat("hors_ligne", "Non connecté au serveur téléphonique.");
    etat(enPause ? "pause" : "disponible",
      enPause ? "En pause : aucun appel ne vous sera présenté."
              : "Disponible : en attente d'un appel.");
  }

  // ---------- Connexion SIP ----------

  var ua = new JsSIP.UA({
    sockets: [new JsSIP.WebSocketInterface(d.wsUrl)],
    uri: d.sipUri,
    password: d.motDePasse,
    register: true,
    session_timers: false,
    user_agent: "RGPH2-Console"
  });
  // À la connexion, le poste est remis en service : un agent précédent a pu le laisser
  // en pause (navigateur fermé), et l'écran doit refléter l'état réel de la file.
  var premiereConnexion = true;
  ua.on("registered", function () {
    if (premiereConnexion) {
      premiereConnexion = false;
      codeService("*2", false);
    }
    etatRepos();
  });
  ua.on("unregistered", etatRepos);
  ua.on("registrationFailed", function (e) {
    etat("hors_ligne", "Connexion refusée par le serveur téléphonique (" + (e.cause || "?") + ").");
  });
  ua.on("disconnected", function () {
    etat("hors_ligne", "Serveur téléphonique injoignable. Nouvel essai automatique…");
  });

  ua.on("newRTCSession", function (e) {
    if (e.originator === "local") return;  // appels passés par l'agent : gérés à part
    if (session || aQualifier) {           // occupé : Asterisk passera au poste suivant
      e.session.terminate({ status_code: 486 });
      return;
    }
    sortant = false;
    suivre(e.session);
    etat("sonnerie", "Appel entrant…");
    boutons({ decrocher: true, raccrocher: true });
  });

  function suivre(s) {
    session = s;
    s.on("peerconnection", function (ev) {
      ev.peerconnection.addEventListener("track", function (t) {
        $("audio-distant").srcObject = t.streams[0];
      });
    });
    s.on("confirmed", function () {
      etat("communication", sortant ? "Rappel en cours." : "En communication.");
      boutons({ raccrocher: true, muet: true });
      if (!sortant) demarrerSondage();
    });
    s.on("ended", terminer);
    s.on("failed", terminer);
  }

  function terminer() {
    arreterSondage();
    var etaitEntrant = !sortant && appelCourant;
    session = null;
    boutons({});
    $("muet").textContent = "Couper le micro";
    if (etaitEntrant) {
      aQualifier = true;
      $("qualification").hidden = false;
      etat("qualification", "Appel terminé : indiquez son issue avant le suivant.");
    } else {
      $("appel-info").textContent = "";
      etatRepos();
    }
  }

  var MEDIA = { mediaConstraints: { audio: true, video: false } };
  $("decrocher").onclick = function () { if (session) session.answer(MEDIA); };
  $("raccrocher").onclick = function () { if (session) session.terminate(); };
  $("muet").onclick = function () {
    if (!session) return;
    if (session.isMuted().audio) { session.unmute({ audio: true }); this.textContent = "Couper le micro"; }
    else { session.mute({ audio: true }); this.textContent = "Rétablir le micro"; }
  };

  // Pause : codes *1 / *2 composés vers Asterisk (PauseQueueMember / UnpauseQueueMember).
  function codeService(code, pause) {
    ua.call(code, {
      mediaConstraints: { audio: true, video: false },
      eventHandlers: {
        ended: function () { enPause = pause; $("pause").hidden = pause; $("reprendre").hidden = !pause; etatRepos(); },
        failed: function () { etat("hors_ligne", "Impossible de changer l'état du poste."); }
      }
    });
  }
  $("pause").onclick = function () { codeService("*1", true); };
  $("reprendre").onclick = function () { codeService("*2", false); };

  // ---------- Appel en cours : langue choisie par le citoyen ----------

  function demarrerSondage() {
    var lire = function () {
      fetch("/tableau-de-bord/agent/appel-courant").then(function (r) { return r.json(); })
        .then(function (j) {
          if (!j.appel) return;
          appelCourant = j.appel;
          $("appel-info").textContent = "Langue choisie par l'appelant : " + j.appel.langue_nom
            + " — décroché à " + j.appel.decroche_a;
        }).catch(function () {});
    };
    appelCourant = null;
    lire();
    sondage = setInterval(lire, 3000);
  }
  function arreterSondage() { if (sondage) clearInterval(sondage); sondage = null; }

  $("qualification").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!appelCourant) return;
    var donnees = new FormData(this);
    donnees.append("appel", appelCourant.reference);
    fetch("/tableau-de-bord/agent/qualification", { method: "POST", body: donnees })
      .then(function (r) {
        if (!r.ok) throw new Error();
        aQualifier = false;
        appelCourant = null;
        $("qualification").hidden = true;
        $("qualification").reset();
        $("appel-info").textContent = "";
        etatRepos();
      }).catch(function () { alert("Enregistrement impossible, réessayez."); });
  });

  // ---------- Recherche dans les réponses validées ----------

  $("recherche").addEventListener("submit", function (e) {
    e.preventDefault();
    var params = new URLSearchParams(new FormData(this));
    var zone = $("resultats");
    fetch("/tableau-de-bord/agent/recherche?" + params).then(function (r) { return r.json(); })
      .then(function (liste) {
        zone.textContent = "";
        if (!liste.length) {
          var vide = document.createElement("p");
          vide.className = "vide";
          vide.textContent = "Aucune réponse validée ne correspond.";
          zone.appendChild(vide);
        }
        liste.forEach(function (c) {
          var bloc = document.createElement("details");
          var titre = document.createElement("summary");
          titre.textContent = c.question + (c.repli_langue ? " (en français)" : "");
          var texte = document.createElement("p");
          texte.textContent = c.reponse;
          bloc.appendChild(titre);
          bloc.appendChild(texte);
          zone.appendChild(bloc);
        });
        if (zone.firstChild && zone.firstChild.tagName === "DETAILS") zone.firstChild.open = true;
      });
  });

  // ---------- Signalement ----------

  $("signalement").addEventListener("submit", function (e) {
    e.preventDefault();
    var formulaire = this;
    fetch("/tableau-de-bord/agent/signalement", { method: "POST", body: new FormData(formulaire) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        $("signalement-resultat").textContent = res.ok
          ? "Signalement n° " + res.j.id + " enregistré."
          : "Vérifiez le type et le territoire.";
        if (res.ok) formulaire.reset();
      });
  });

  // ---------- Rappels ----------

  function bouton(texte, classe, action) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = texte;
    b.className = classe || "";
    b.onclick = action;
    return b;
  }

  function cloturer(id, statut) {
    var donnees = new FormData();
    donnees.append("statut", statut);
    fetch("/tableau-de-bord/agent/rappels/" + id + "/cloturer", { method: "POST", body: donnees })
      .then(chargerRappels);
  }

  function prendre(id, cellule) {
    fetch("/tableau-de-bord/agent/rappels/" + id + "/prendre", { method: "POST" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        cellule.textContent = "";
        if (!res.ok) { cellule.textContent = res.j.detail || "Indisponible."; return; }
        var numero = document.createElement("strong");
        numero.textContent = res.j.numero + " ";
        cellule.appendChild(numero);
        cellule.appendChild(bouton("Appeler", "", function () {
          if (session) return;
          sortant = true;
          suivre(ua.call(res.j.numero, MEDIA));
          etat("communication", "Appel du citoyen en cours…");
          boutons({ raccrocher: true });
        }));
        cellule.appendChild(bouton("Rappelé", "secondaire", function () { cloturer(id, "rappele"); }));
        cellule.appendChild(bouton("Injoignable", "secondaire", function () { cloturer(id, "injoignable"); }));
      });
  }

  function chargerRappels() {
    fetch("/tableau-de-bord/agent/rappels").then(function (r) { return r.json(); })
      .then(function (liste) {
        var corps = $("rappels");
        corps.textContent = "";
        if (!liste.length) {
          var ligne = corps.insertRow();
          var cellule = ligne.insertCell();
          cellule.className = "vide";
          cellule.textContent = "Aucun rappel en attente.";
          return;
        }
        liste.forEach(function (r) {
          var ligne = corps.insertRow();
          ligne.insertCell().textContent = r.cree_a;
          ligne.insertCell().textContent = r.langue_nom + " · " + r.origine;
          var action = ligne.insertCell();
          if (r.statut === "en_cours" && !r.pris_par_moi) action.textContent = "Pris par un autre agent";
          else action.appendChild(bouton(r.pris_par_moi ? "Reprendre" : "Prendre", "",
            function () { prendre(r.id, action); }));
        });
      });
  }
  $("actualiser-rappels").onclick = chargerRappels;
  chargerRappels();
  setInterval(function () { if (!session) chargerRappels(); }, 30000);

  ua.start();
  window.addEventListener("beforeunload", function () { ua.stop(); });
})();
