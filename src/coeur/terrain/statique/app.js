// Application de terrain du RGPH-2 : kiosques OKAPI et Ambassadeurs.
//
// Tout ce qu'affiche l'appareil vient du « paquet » téléchargé quand il a du réseau
// (FAQ validée, calendrier, territoires, textes) et gardé dans IndexedDB. Ce qu'il
// recueille hors ligne part dans une file d'attente (« envois »), vidée à chaque
// synchronisation. Chaque envoi porte un identifiant aléatoire : le serveur ignore
// un envoi qu'il a déjà reçu, on peut donc toujours renvoyer sans crainte de doublon.
//
// Aucun texte n'est inséré comme HTML (textContent seulement) : pas d'injection possible.
(function () {
  "use strict";

  var API = "/v1/terrain";
  var DELAI_RESEAU_MS = 20000;
  var SYNCHRO_PERIODIQUE_MS = 5 * 60 * 1000;
  // Kiosque partagé : sans action pendant ce délai, retour au choix de la langue.
  var INACTIVITE_KIOSQUE_MS = 2 * 60 * 1000;
  var LOT_ENVOIS = 200;
  var CACHE_MEDIAS = "terrain-medias";

  // --- Stockage local (IndexedDB) ------------------------------------------------------

  var baseOuverte = null;

  function base() {
    if (!baseOuverte) {
      baseOuverte = new Promise(function (resoudre, rejeter) {
        var requete = indexedDB.open("rgph2-terrain", 1);
        requete.onupgradeneeded = function () {
          requete.result.createObjectStore("etat");
          requete.result.createObjectStore("envois", { keyPath: "id" });
        };
        requete.onsuccess = function () { resoudre(requete.result); };
        requete.onerror = function () { rejeter(requete.error); };
      });
    }
    return baseOuverte;
  }

  function transaction(magasin, mode, action) {
    return base().then(function (db) {
      return new Promise(function (resoudre, rejeter) {
        var tx = db.transaction(magasin, mode);
        var resultat = action(tx.objectStore(magasin));
        tx.oncomplete = function () { resoudre(resultat && resultat.result); };
        tx.onerror = function () { rejeter(tx.error); };
        tx.onabort = function () { rejeter(tx.error); };
      });
    });
  }

  function lire(cle) { return transaction("etat", "readonly", function (m) { return m.get(cle); }); }
  function ecrire(cle, valeur) {
    return transaction("etat", "readwrite", function (m) { m.put(valeur, cle); });
  }
  function effacer(cle) { return transaction("etat", "readwrite", function (m) { m.delete(cle); }); }

  function ajouterEnvoi(envoi) {
    return transaction("envois", "readwrite", function (m) { m.put(envoi); });
  }
  function envoisEnAttente() {
    return transaction("envois", "readonly", function (m) { return m.getAll(null, LOT_ENVOIS); });
  }
  function compterEnvois() {
    return transaction("envois", "readonly", function (m) { return m.count(); });
  }
  function retirerEnvois(ids) {
    return transaction("envois", "readwrite", function (m) {
      ids.forEach(function (id) { if (id) m.delete(id); });
    });
  }

  // --- État de l'application -----------------------------------------------------------

  var etat = { jeton: null, paquet: null, etag: null, langue: null, enLigne: false,
               synchroEnCours: null };

  function identifiant() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var o = crypto.getRandomValues(new Uint8Array(16));
    o[6] = (o[6] & 0x0f) | 0x40; o[8] = (o[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(o, function (x) { return (x + 0x100).toString(16).slice(1); });
    return h.slice(0, 4).join("") + "-" + h.slice(4, 6).join("") + "-" + h.slice(6, 8).join("") +
      "-" + h.slice(8, 10).join("") + "-" + h.slice(10).join("");
  }

  function estKiosque() { return etat.paquet && etat.paquet.appareil.type === "kiosque"; }

  function t(cle, valeurs) {
    var textes = etat.paquet ? etat.paquet.textes : {};
    var texte = (textes[etat.langue] || {})[cle] || (textes.fr || {})[cle] || cle;
    Object.keys(valeurs || {}).forEach(function (k) { texte = texte.split("{" + k + "}").join(valeurs[k]); });
    return texte;
  }

  function $(id) { return document.getElementById(id); }

  function element(balise, texte, classe) {
    var e = document.createElement(balise);
    if (texte !== undefined && texte !== null) e.textContent = texte;
    if (classe) e.className = classe;
    return e;
  }

  // --- Réseau --------------------------------------------------------------------------

  function appeler(chemin, options) {
    options = options || {};
    var controle = new AbortController();
    var minuterie = setTimeout(function () { controle.abort(); }, DELAI_RESEAU_MS);
    var entetes = Object.assign({}, options.entetes || {});
    if (etat.jeton) entetes.Authorization = "Bearer " + etat.jeton;
    if (options.corps !== undefined) entetes["Content-Type"] = "application/json";
    return fetch(API + chemin, {
      method: options.methode || "GET",
      headers: entetes,
      body: options.corps !== undefined ? JSON.stringify(options.corps) : undefined,
      signal: controle.signal,
      cache: "no-store"
    }).then(function (reponse) {
      etat.enLigne = true;
      if (reponse.status === 401 && chemin !== "/activation") {
        return desactiver().then(function () { throw new Error("revoque"); });
      }
      return reponse;
    }, function (erreur) {
      etat.enLigne = false;
      throw erreur;
    }).finally(function () { clearTimeout(minuterie); });
  }

  function viderFile() {
    return envoisEnAttente().then(function (lot) {
      if (!lot.length) return;
      return appeler("/remontees", { methode: "POST", corps: lot }).then(function (reponse) {
        if (!reponse.ok) throw new Error("remontees " + reponse.status);
        return reponse.json();
      }).then(function (resultat) {
        var traites = resultat.acceptes.concat(resultat.rejetes.map(function (r) { return r.id; }));
        // Un lot entièrement refusé sans identifiant exploitable : on s'arrête pour ne pas boucler.
        if (!traites.length) return;
        return retirerEnvois(traites).then(function () {
          if (lot.length === LOT_ENVOIS) return viderFile();
        });
      });
    });
  }

  function telechargerPaquet() {
    var entetes = etat.etag && etat.paquet ? { "If-None-Match": etat.etag } : {};
    return appeler("/paquet", { entetes: entetes }).then(function (reponse) {
      if (reponse.status === 304) return false;
      if (!reponse.ok) throw new Error("paquet " + reponse.status);
      var etag = reponse.headers.get("ETag");
      return reponse.json().then(function (paquet) {
        etat.paquet = paquet;
        etat.etag = etag;
        if (!etat.langue || !paquet.langues.some(function (l) { return l.code === etat.langue; })) {
          etat.langue = paquet.langues[0].code;
        }
        return Promise.all([ecrire("paquet", paquet), ecrire("etag", etag)]).then(function () {
          garderMedias(paquet);
          return true;
        });
      });
    });
  }

  // Une synchronisation à la fois : envoie la file, puis met le paquet à jour.
  function synchroniser() {
    if (!etat.jeton) return Promise.resolve();
    if (etat.synchroEnCours) return etat.synchroEnCours;
    $("synchroniser").disabled = true;
    $("synchroniser").textContent = t("synchronisation");
    etat.synchroEnCours = viderFile().then(telechargerPaquet).then(function (change) {
      if (change) rendre();
    }).catch(function () {
      // Hors ligne ou serveur injoignable : on réessaiera plus tard.
    }).then(function () {
      etat.synchroEnCours = null;
      $("synchroniser").disabled = false;
      $("synchroniser").textContent = t("synchroniser");
      return majEtat();
    });
    return etat.synchroEnCours;
  }

  // Audio des réponses gardé pour l'écoute hors ligne (servi par le service worker).
  function garderMedias(paquet) {
    if (!window.caches) return;
    var liens = {};
    Object.keys(paquet.faq).forEach(function (langue) {
      paquet.faq[langue].forEach(function (c) { if (c.audio_url) liens[c.audio_url] = true; });
    });
    caches.open(CACHE_MEDIAS).then(function (cache) {
      return cache.keys().then(function (requetes) {
        requetes.forEach(function (r) { if (!liens[r.url]) cache.delete(r); });
        return Object.keys(liens).reduce(function (suite, lien) {
          return suite.then(function () {
            return cache.match(lien).then(function (deja) {
              if (deja) return;
              // CORS d'abord (réponse lisible, lecture partielle possible) ; sinon réponse opaque.
              return fetch(lien, { mode: "cors" }).catch(function () {
                return fetch(lien, { mode: "no-cors" });
              }).then(function (r) {
                if (r.ok || r.type === "opaque") return cache.put(lien, r);
              }).catch(function () {});
            });
          });
        }, Promise.resolve());
      });
    }).catch(function () {});
  }

  function desactiver() {
    etat.jeton = null;
    return effacer("jeton").then(function () { afficher("activation"); });
  }

  // --- Navigation ----------------------------------------------------------------------

  var SECTIONS = ["chargement", "activation", "langues", "accueil", "faq", "passage", "remontee",
                  "merci", "badge"];

  function afficher(nom) {
    SECTIONS.forEach(function (s) { $(s).hidden = s !== nom; });
    var pret = !!etat.paquet && nom !== "activation" && nom !== "chargement";
    document.querySelector('[data-aller="accueil"].nav').hidden = !pret || nom === "accueil" || nom === "langues";
    document.querySelector('[data-aller="langues"].nav').hidden =
      !pret || nom === "langues" || etat.paquet.langues.length < 2;
    $("etat").hidden = !etat.jeton || !etat.paquet;
    window.scrollTo(0, 0);
    if (nom === "faq") $("recherche").focus();
  }

  function traduire() {
    document.documentElement.lang = etat.langue || "fr";
    Array.prototype.forEach.call(document.querySelectorAll("[data-t]"), function (e) {
      e.textContent = t(e.getAttribute("data-t"));
    });
  }

  function rendre() {
    if (!etat.paquet) return;
    traduire();
    rendreLangues();
    rendreAccueil();
    rendreFaq();
    remplirProvinces();
    majEtat();
  }

  // --- Écrans --------------------------------------------------------------------------

  function rendreLangues() {
    var liste = $("liste-langues");
    liste.textContent = "";
    etat.paquet.langues.forEach(function (l) {
      var bouton = element("button", l.nom, "tuile");
      bouton.type = "button";
      bouton.lang = l.code;
      bouton.addEventListener("click", function () {
        etat.langue = l.code;
        if (!estKiosque()) ecrire("langue", l.code);
        rendre();
        afficher("accueil");
      });
      liste.appendChild(bouton);
    });
  }

  var TUILES = {
    kiosque: ["faq", "passage", "remontee:question", "remontee:menage", "badge", "remontee:agent"],
    ambassadeur: ["faq", "remontee:rumeur", "remontee:question", "passage", "remontee:menage",
                  "remontee:agent", "badge"]
  };
  var LIBELLES_TUILES = {
    faq: "faq", passage: "passage", badge: "verifier_badge",
    "remontee:menage": "signaler_menage", "remontee:agent": "signaler_agent",
    "remontee:rumeur": "remonter_rumeur"
  };

  function libelleTuile(code) {
    if (code === "remontee:question") return estKiosque() ? "question_kiosque" : "question_ambassadeur";
    return LIBELLES_TUILES[code];
  }

  function contacts() {
    var p = etat.paquet, morceaux = [];
    if (p.numero_vert) morceaux.push(t("numero_vert", { numero: p.numero_vert }));
    if (p.ussd_code) morceaux.push(t("ussd", { code: p.ussd_code }));
    return morceaux.join(" · ");
  }

  function rendreAccueil() {
    $("texte-accueil").textContent = t(estKiosque() ? "accueil_kiosque" : "accueil_ambassadeur");
    var tuiles = $("tuiles");
    tuiles.textContent = "";
    TUILES[etat.paquet.appareil.type].forEach(function (code) {
      var bouton = element("button", t(libelleTuile(code)), "tuile");
      bouton.type = "button";
      bouton.addEventListener("click", function () { ouvrir(code); });
      tuiles.appendChild(bouton);
    });
    $("contacts").textContent = contacts();
  }

  function ouvrir(code) {
    if (code.indexOf("remontee:") === 0) return ouvrirRemontee(code.split(":")[1]);
    if (code === "faq") { $("recherche").value = ""; rendreFaq(); }
    if (code === "passage") { $("resultat-passage").hidden = true; choisirTerritoireAppareil("passage"); }
    if (code === "badge") {
      $("numero-badge").value = ""; $("resultat-badge").hidden = true; $("badge-signaler").hidden = true;
    }
    afficher(code);
  }

  function normaliser(texte) {
    return texte.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function rendreFaq() {
    var contenus = etat.paquet.faq[etat.langue] || [];
    var mots = normaliser($("recherche").value).split(/\s+/).filter(Boolean);
    var liste = $("liste-faq");
    liste.textContent = "";
    var trouves = contenus.filter(function (c) {
      var texte = normaliser(c.question + " " + c.reponse);
      return mots.every(function (m) { return texte.indexOf(m) !== -1; });
    });
    trouves.forEach(function (c) {
      var details = element("details", null, "question");
      details.appendChild(element("summary", c.question));
      var bloc = element("div", null, "officielle");
      bloc.lang = c.langue;
      bloc.appendChild(element("p", t("reponse_officielle"), "auteur"));
      if (c.repli_langue) bloc.appendChild(element("p", t("repli_langue"), "repli"));
      bloc.appendChild(element("p", c.reponse, "texte-reponse"));
      if (c.audio_url) {
        var audio = document.createElement("audio");
        audio.controls = true; audio.preload = "none"; audio.src = c.audio_url;
        audio.setAttribute("aria-label", t("ecouter"));
        bloc.appendChild(audio);
      }
      details.appendChild(bloc);
      details.addEventListener("toggle", function () {
        if (details.open) {
          consigner({ type: "consultation", contenu_id: c.contenu_id, langue: etat.langue });
        }
      });
      liste.appendChild(details);
    });
    var vide = $("faq-vide");
    vide.hidden = trouves.length > 0;
    vide.textContent = contenus.length ? t("aucun_resultat") : t("aucune_faq");
  }

  // --- Territoires ---------------------------------------------------------------------

  function provinceDe(codeTerritoire) {
    var trouvee = null;
    etat.paquet.provinces.forEach(function (p) {
      p.territoires.forEach(function (te) { if (te.code === codeTerritoire) trouvee = p.code; });
    });
    return trouvee;
  }

  function remplirTerritoires(selectProvince) {
    var cible = $(selectProvince.getAttribute("data-cible"));
    cible.textContent = "";
    cible.appendChild(new Option(t("choisir"), ""));
    etat.paquet.provinces.forEach(function (p) {
      if (p.code !== selectProvince.value) return;
      p.territoires.forEach(function (te) { cible.appendChild(new Option(te.nom, te.code)); });
    });
  }

  function remplirProvinces() {
    Array.prototype.forEach.call(document.querySelectorAll(".choix-province"), function (select) {
      select.textContent = "";
      select.appendChild(new Option(t("choisir"), ""));
      etat.paquet.provinces.forEach(function (p) {
        if (p.territoires.length) select.appendChild(new Option(p.nom, p.code));
      });
      remplirTerritoires(select);
    });
  }

  // Par défaut, le territoire de l'appareil : c'est presque toujours celui du visiteur.
  function choisirTerritoireAppareil(prefixe) {
    var code = etat.paquet.appareil.territoire_code;
    var province = $(prefixe + "-province");
    province.value = provinceDe(code) || "";
    remplirTerritoires(province);
    $(prefixe + "-territoire").value = code;
  }

  function nomTerritoire(code) {
    var nom = code;
    etat.paquet.provinces.forEach(function (p) {
      p.territoires.forEach(function (te) { if (te.code === code) nom = te.nom; });
    });
    return nom;
  }

  function formaterDate(iso) {
    var morceaux = iso.split("-").map(Number);
    var date = new Date(Date.UTC(morceaux[0], morceaux[1] - 1, morceaux[2]));
    var options = { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" };
    try { return date.toLocaleDateString(etat.langue, options); }
    catch (e) { return date.toLocaleDateString("fr", options); }
  }

  // --- Remontées -----------------------------------------------------------------------

  // Ce que recueille chaque formulaire, et ce qui part au serveur.
  var REMONTEES = {
    menage: { titre: "signaler_menage", intro: "intro_menage", texte: null, lieu: true, description: true,
              envoi: function (v) { return signalement("menage_non_visite", v, v.description); } },
    agent: { titre: "signaler_agent", intro: "intro_agent", texte: null, lieu: true, description: true,
             envoi: function (v) { return signalement("agent_douteux", v, v.description); } },
    rumeur: { titre: "remonter_rumeur", intro: "intro_rumeur", texte: "rumeur", lieu: true, description: false,
              envoi: function (v) { return signalement("rumeur", v, v.texte); } },
    question: { texte: "votre_question", lieu: false, description: false,
                envoi: function (v) { return { type: "question", texte: v.texte, langue: etat.langue }; } }
  };

  function signalement(type, v, description) {
    return { type: "signalement", signalement: type, territoire_code: v.territoire,
             localite: v.localite || null, description: description || null };
  }

  var remonteeCourante = null;

  function ouvrirRemontee(nature) {
    var r = REMONTEES[nature];
    remonteeCourante = nature;
    var titre = nature === "question" ? libelleTuile("remontee:question") : r.titre;
    var intro = nature === "question"
      ? (estKiosque() ? "intro_question_kiosque" : "intro_question_ambassadeur") : r.intro;
    $("titre-remontee").textContent = t(titre);
    $("intro-remontee").textContent = t(intro);
    $("bloc-texte").hidden = !r.texte;
    if (r.texte) $("libelle-texte").textContent = t(r.texte);
    $("bloc-lieu").hidden = !r.lieu;
    $("bloc-description").hidden = !r.description;
    $("form-remontee").reset();
    $("erreur-remontee").hidden = true;
    if (r.lieu) choisirTerritoireAppareil("remontee");
    afficher("remontee");
  }

  function consigner(contenu) {
    var envoi = Object.assign({ id: identifiant(), horodatage: new Date().toISOString() }, contenu);
    return ajouterEnvoi(envoi).then(function () {
      majEtat();
      return envoi.id;
    });
  }

  function envoyerRemontee(e) {
    e.preventDefault();
    var r = REMONTEES[remonteeCourante];
    var valeurs = {
      texte: $("remontee-texte").value.trim(),
      territoire: $("remontee-territoire").value,
      localite: $("remontee-localite").value.trim(),
      description: $("remontee-description").value.trim()
    };
    if ((r.texte && !valeurs.texte) || (r.lieu && !valeurs.territoire)) {
      $("erreur-remontee").textContent = t("champ_obligatoire");
      $("erreur-remontee").hidden = false;
      return;
    }
    consigner(r.envoi(valeurs)).then(function (id) {
      // Remerciement immédiat, même hors ligne ; le texte change si l'envoi passe aussitôt.
      $("texte-merci").textContent = t("envoi_differe");
      $("contacts-merci").textContent = remonteeCourante === "question" ? contacts() : "";
      afficher("merci");
      return synchroniser().then(envoisEnAttente).then(function (restants) {
        if (!restants.some(function (x) { return x.id === id; })) {
          $("texte-merci").textContent = t("envoi_fait");
        }
      });
    });
  }

  // --- Date de passage -----------------------------------------------------------------

  function voirPassage(e) {
    e.preventDefault();
    var code = $("passage-territoire").value;
    if (!code) return;
    var periodes = etat.paquet.calendrier.filter(function (p) { return p.territoire_code === code; });
    var resultat = $("resultat-passage");
    resultat.textContent = periodes.length
      ? t("passage_prevu", { territoire: nomTerritoire(code), periodes: periodes.map(function (p) {
          return t("periode", { debut: formaterDate(p.debut), fin: formaterDate(p.fin) });
        }).join(", ") })
      : t("passage_non_publie", { territoire: nomTerritoire(code) });
    resultat.hidden = false;
    consigner({ type: "passage", territoire_code: code, langue: etat.langue,
                resultat: periodes.length ? "trouve" : "non_publie" });
  }

  // --- Badge (en ligne seulement) ------------------------------------------------------

  function verifierBadge(e) {
    e.preventDefault();
    var numero = $("numero-badge").value.trim();
    var resultat = $("resultat-badge");
    if (!numero) return;
    $("badge-signaler").hidden = true;
    appeler("/badge", { methode: "POST", corps: { numero: numero, langue: etat.langue } })
      .then(function (reponse) {
        if (reponse.status === 422) return { message: t("badge_format") };
        if (reponse.status === 429) return { message: t("trop_de_verifications") };
        if (!reponse.ok) throw new Error("badge " + reponse.status);
        return reponse.json();
      }).then(function (v) {
        if (v.message) { resultat.textContent = v.message; return; }
        resultat.textContent = t("badge_" + v.statut, { territoire: v.territoire_nom || "" });
        $("badge-signaler").hidden = v.statut === "valide";
      }, function () {
        var ussd = etat.paquet.ussd_code;
        resultat.textContent = ussd ? t("badge_hors_ligne", { ussd: ussd }) : t("badge_hors_ligne_sans_ussd");
      }).then(function () {
        resultat.hidden = false;
        majEtat();
      });
  }

  // --- Barre d'état --------------------------------------------------------------------

  function majEtat() {
    if (!etat.paquet) return Promise.resolve();
    return compterEnvois().then(function (n) {
      $("etat-reseau").textContent = t(etat.enLigne ? "en_ligne" : "hors_ligne");
      $("etat-reseau").className = etat.enLigne ? "en-ligne" : "hors-ligne";
      $("etat-paquet").textContent = t("mis_a_jour", {
        date: new Date(etat.paquet.genere_a).toLocaleDateString("fr", { day: "numeric", month: "long" }) });
      $("etat-attente").textContent = n ? t("en_attente", { n: n }) : "";
      $("etat-appareil").textContent = t("appareil", { code: etat.paquet.appareil.code });
    });
  }

  // --- Kiosque : retour à l'accueil après inactivité -----------------------------------

  var minuterieInactivite = null;

  function surveillerInactivite() {
    clearTimeout(minuterieInactivite);
    if (!estKiosque()) return;
    minuterieInactivite = setTimeout(function () {
      // Rien de ce qu'a saisi le visiteur précédent ne reste à l'écran.
      Array.prototype.forEach.call(document.querySelectorAll("form"), function (f) { f.reset(); });
      $("recherche").value = "";
      $("resultat-badge").hidden = true;
      $("resultat-passage").hidden = true;
      if (etat.paquet && $("activation").hidden) {
        etat.langue = etat.paquet.langues[0].code;
        rendre();
        afficher(etat.paquet.langues.length > 1 ? "langues" : "accueil");
      }
    }, INACTIVITE_KIOSQUE_MS);
  }

  // --- Activation et démarrage ---------------------------------------------------------

  function activer(e) {
    e.preventDefault();
    var code = $("code-activation").value.trim();
    var erreur = $("erreur-activation");
    erreur.hidden = true;
    appeler("/activation", { methode: "POST", corps: { code: code } }).then(function (reponse) {
      if (reponse.status === 429) throw new Error("Trop d'essais. Réessayez dans un quart d'heure.");
      if (!reponse.ok) throw new Error("Code invalide ou expiré. Demandez un nouveau code au Ministère.");
      return reponse.json();
    }, function () {
      throw new Error("Pas de réseau. L'activation demande une connexion.");
    }).then(function (r) {
      etat.jeton = r.jeton;
      if (navigator.storage && navigator.storage.persist) navigator.storage.persist();
      return ecrire("jeton", r.jeton).then(telechargerPaquet);
    }).then(function () {
      rendre();
      afficher(etat.paquet.langues.length > 1 && estKiosque() ? "langues" : "accueil");
    }).catch(function (err) {
      erreur.textContent = err.message;
      erreur.hidden = false;
    });
  }

  function brancher() {
    $("form-activation").addEventListener("submit", activer);
    $("form-remontee").addEventListener("submit", envoyerRemontee);
    $("form-passage").addEventListener("submit", voirPassage);
    $("form-badge").addEventListener("submit", verifierBadge);
    $("recherche").addEventListener("input", rendreFaq);
    $("synchroniser").addEventListener("click", synchroniser);
    $("nouvelle-remontee").addEventListener("click", function () { ouvrirRemontee(remonteeCourante); });
    $("badge-signaler").addEventListener("click", function () {
      ouvrirRemontee("agent");
      $("remontee-description").value = $("numero-badge").value.trim();
    });
    Array.prototype.forEach.call(document.querySelectorAll(".choix-province"), function (select) {
      select.addEventListener("change", function () { remplirTerritoires(select); });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-aller]"), function (bouton) {
      bouton.addEventListener("click", function () { afficher(bouton.getAttribute("data-aller")); });
    });
    ["pointerdown", "keydown", "input"].forEach(function (type) {
      document.addEventListener(type, surveillerInactivite, { passive: true });
    });
    window.addEventListener("online", synchroniser);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") synchroniser();
    });
    setInterval(synchroniser, SYNCHRO_PERIODIQUE_MS);
  }

  function demarrer() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/terrain/sw.js", { scope: "/terrain/" }).catch(function () {});
    }
    brancher();
    Promise.all([lire("jeton"), lire("paquet"), lire("etag"), lire("langue")]).then(function (v) {
      etat.jeton = v[0] || null;
      etat.paquet = v[1] || null;
      etat.etag = v[2] || null;
      etat.langue = v[3] || (etat.paquet ? etat.paquet.langues[0].code : "fr");
      if (!etat.jeton) return afficher("activation");
      if (!etat.paquet) {
        // Activé mais jamais téléchargé (réseau coupé juste après l'activation).
        return synchroniser().then(function () {
          if (!etat.paquet) {
            $("chargement").textContent = "Téléchargement impossible pour l'instant. Rechargez la page quand l'appareil aura du réseau.";
            return afficher("chargement");
          }
          rendre();
          afficher("accueil");
        });
      }
      rendre();
      afficher(estKiosque() && etat.paquet.langues.length > 1 ? "langues" : "accueil");
      surveillerInactivite();
      synchroniser();
    }).catch(function () {
      $("chargement").textContent = "Stockage local indisponible sur ce navigateur.";
    });
  }

  demarrer();
})();
