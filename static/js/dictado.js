/* Dictado de notas con la API de voz del navegador (si existe).
   Si no está disponible, el botón no aparece: el teclado del móvil ya trae su propio micrófono. */
(function () {
  "use strict";
  var gettext = function (s) { return window.gettext ? window.gettext(s) : s; };
  var Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;

  function iniciar() {
    var botones = document.querySelectorAll("[data-dictado-para]");
    if (!botones.length) return;
    if (!Reconocimiento) {
      botones.forEach(function (b) {
        var nota = document.createElement("p");
        nota.className = "ayuda";
        nota.textContent = gettext("Consejo: usa el micrófono del teclado de tu móvil para dictar.");
        b.replaceWith(nota);
      });
      return;
    }
    botones.forEach(function (boton) {
      boton.classList.remove("oculto");
      var activo = null;
      boton.addEventListener("click", function () {
        var area = document.getElementById(boton.dataset.dictadoPara);
        if (!area) return;
        if (activo) { activo.stop(); return; }
        var rec = new Reconocimiento();
        var idioma = document.documentElement.lang;
        rec.lang = idioma === "es" ? "es-US" : idioma === "en" ? "en-US" : idioma;
        rec.continuous = true;
        rec.interimResults = false;
        var etiqueta = boton.querySelector("span");
        rec.onstart = function () { activo = rec; boton.classList.add("grabando"); if (etiqueta) etiqueta.textContent = "Escuchando… (toca para parar)"; };
        rec.onend = function () { activo = null; boton.classList.remove("grabando"); if (etiqueta) etiqueta.textContent = "Dictar"; };
        rec.onerror = function (ev) {
          if (window.estudioAvisar) window.estudioAvisar(ev.error === "not-allowed" ? gettext("Permite el micrófono para dictar.") : gettext("No se pudo usar el dictado."), "error");
        };
        rec.onresult = function (ev) {
          for (var i = ev.resultIndex; i < ev.results.length; i++) {
            if (ev.results[i].isFinal) {
              var t = ev.results[i][0].transcript.trim();
              area.value = (area.value ? area.value.replace(/\s*$/, " ") : "") + t.charAt(0).toUpperCase() + t.slice(1) + ".";
            }
          }
          if (boton.dataset.dictadoOrigen) {
            var origen = document.querySelector(boton.dataset.dictadoOrigen);
            if (origen) origen.value = "dictado";
          }
        };
        rec.start();
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar); else iniciar();
})();
