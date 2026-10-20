// Amélioration facultative : envoie la question sans recharger la page et garde
// la conversation affichée. Sans JavaScript, le formulaire fonctionne normalement.
// Les textes viennent des attributs data-* de #fil (déjà traduits côté serveur).
(function () {
  var form = document.getElementById("question");
  var fil = document.getElementById("fil");
  if (!form || !fil || !window.fetch || !window.JSON) return;
  var d = fil.dataset;

  function bulle(classe, auteur, lignes) {
    var div = document.createElement("div");
    div.className = "bulle " + classe;
    if (auteur) lignes.unshift({ texte: auteur, classe: "auteur" });
    lignes.forEach(function (l) {
      var p = document.createElement("p");
      p.textContent = l.texte; // jamais innerHTML : pas d'injection possible
      if (l.classe) p.className = l.classe;
      if (l.lang) p.lang = l.lang;
      div.appendChild(p);
    });
    fil.appendChild(div);
    return div;
  }

  function afficher(r) {
    if (r.type !== "reponse") return bulle("escalade", null, [{ texte: d.escalade }]);
    var c = r.contenu, lignes = [];
    if (c.repli_langue) lignes.push({ texte: d.repli, classe: "repli" });
    lignes.push({ texte: c.reponse, lang: c.langue });
    var div = bulle("officielle", d.officielle, lignes);
    if (c.audio_url) {
      var audio = document.createElement("audio");
      audio.controls = true; audio.preload = "none"; audio.src = c.audio_url;
      div.appendChild(audio);
    }
  }

  form.addEventListener("submit", function (e) {
    var champ = form.elements.texte, texte = champ.value.trim();
    if (!texte) return;
    e.preventDefault();
    var bouton = form.querySelector("button");
    bouton.disabled = true;
    bulle("vous", d.vous, [{ texte: texte }]);
    fetch("/api/portail/question", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texte: texte, langue: d.langue })
    }).then(function (rep) {
      if (rep.status === 429) throw new Error(d.trop);
      if (!rep.ok) throw new Error(d.erreur);
      return rep.json();
    }).then(function (r) {
      afficher(r);
      champ.value = "";
    }).catch(function (err) {
      bulle("escalade", null, [{ texte: err.message || d.erreur }]);
    }).then(function () {
      bouton.disabled = false;
      champ.focus();
    });
  });
})();
