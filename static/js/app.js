/* Interacciones generales. Sin dependencias (HTMX se carga aparte).
   Nada de JS en línea: todo se engancha por atributos data-* (CSP estricta). */
(function () {
  "use strict";
  var gettext = function (s) { return window.gettext ? window.gettext(s) : s; };

  /* ---------- Avisos (toasts) ---------- */
  function cerrarAviso(el) { if (el && el.parentNode) el.parentNode.removeChild(el); }

  function programarCierre(el) {
    if (el.dataset.programado) return;
    el.dataset.programado = "1";
    var ms = el.classList.contains("toast-error") || el.classList.contains("toast-warning") ? 9000 : 5000;
    setTimeout(function () { cerrarAviso(el); }, ms);
  }

  function avisar(texto, tipo) {
    var cont = document.getElementById("avisos");
    if (!cont) return;
    var el = document.createElement("div");
    el.className = "toast toast-" + (tipo || "info");
    el.setAttribute("role", tipo === "error" ? "alert" : "status");
    var span = document.createElement("span");
    span.textContent = texto;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("aria-label", "Cerrar aviso");
    btn.dataset.cerrarAviso = "";
    btn.textContent = "✕";
    el.appendChild(span);
    el.appendChild(btn);
    cont.appendChild(el);
    programarCierre(el);
  }
  window.estudioAvisar = avisar;

  function iniciarAvisos(raiz) {
    (raiz || document).querySelectorAll(".toast").forEach(programarCierre);
  }

  /* ---------- Diálogo de confirmación ---------- */
  var dialogo, textoDialogo, botonSi, alConfirmar = null;

  function prepararDialogo() {
    dialogo = document.getElementById("dialogo-confirmar");
    if (!dialogo) return;
    textoDialogo = dialogo.querySelector("[data-texto]");
    botonSi = dialogo.querySelector("[data-si]");
    botonSi.addEventListener("click", function () {
      dialogo.close();
      if (alConfirmar) { var f = alConfirmar; alConfirmar = null; f(); }
    });
    dialogo.addEventListener("close", function () { alConfirmar = null; });
  }

  function confirmar(texto, etiquetaSi, accion) {
    if (!dialogo) { if (window.confirm(texto)) accion(); return; }
    textoDialogo.textContent = texto;
    botonSi.textContent = etiquetaSi || gettext("Sí, continuar");
    alConfirmar = accion;
    dialogo.showModal();
    botonSi.focus();
  }

  document.addEventListener("submit", function (e) {
    var form = e.target;
    var emisor = e.submitter;
    var texto = (emisor && emisor.dataset.confirmar) || form.dataset.confirmar;
    if (!texto || form.dataset.confirmado === "1") return;
    e.preventDefault();
    confirmar(texto, (emisor && emisor.dataset.confirmarSi) || form.dataset.confirmarSi, function () {
      form.dataset.confirmado = "1";
      if (emisor && emisor.name) {
        var oculto = document.createElement("input");
        oculto.type = "hidden"; oculto.name = emisor.name; oculto.value = emisor.value;
        form.appendChild(oculto);
      }
      if (form.requestSubmit && !emisor) form.requestSubmit(); else form.submit();
    });
  }, true);

  // hx-confirm de HTMX usa el mismo diálogo en vez de window.confirm
  document.addEventListener("htmx:confirm", function (e) {
    if (!e.detail.question) return;
    e.preventDefault();
    var el = e.detail.elt;
    confirmar(e.detail.question, el.dataset.confirmarSi, function () { e.detail.issueRequest(true); });
  });

  /* ---------- Clics delegados ---------- */
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-cerrar-aviso],[data-copiar],[data-abrir],[data-cerrar],[data-imprimir]");
    if (!t) return;

    if (t.hasAttribute("data-cerrar-aviso")) { cerrarAviso(t.closest(".toast")); return; }

    if (t.hasAttribute("data-copiar")) {
      e.preventDefault();
      var objetivo = t.dataset.copiar ? document.querySelector(t.dataset.copiar) : null;
      var texto = t.dataset.copiarTexto || (objetivo ? (objetivo.value !== undefined && objetivo.tagName !== "DIV" ? objetivo.value : objetivo.innerText) : "");
      copiar(texto).then(function () {
        avisar(t.dataset.copiado || "Copiado al portapapeles.", "success");
        t.dispatchEvent(new CustomEvent("estudio:copiado", { bubbles: true }));
      }, function () { avisar(gettext("No se pudo copiar. Selecciona el texto y cópialo a mano."), "error"); });
      return;
    }

    if (t.hasAttribute("data-abrir")) {
      var d = document.getElementById(t.dataset.abrir);
      if (d && d.showModal) { e.preventDefault(); d.showModal(); }
      return;
    }
    if (t.hasAttribute("data-cerrar")) {
      var dlg = t.closest("dialog");
      if (dlg) { e.preventDefault(); dlg.close(); }
      return;
    }
    if (t.hasAttribute("data-imprimir")) { e.preventDefault(); window.print(); }
  });

  // Cerrar diálogos al pulsar fuera
  document.addEventListener("click", function (e) {
    if (e.target.tagName === "DIALOG" && e.target.open) e.target.close();
  });

  function copiar(texto) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texto);
    return new Promise(function (ok, ko) {
      var ta = document.createElement("textarea");
      ta.value = texto; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy") ? ok() : ko(); } catch (err) { ko(err); }
      document.body.removeChild(ta);
    });
  }
  window.estudioCopiar = copiar;


  /* ---------- Selector de cliente (autocompletado) ---------- */
  document.addEventListener("click", function (e) {
    var elegir = e.target.closest("[data-elegir-cliente]");
    var cambiar = e.target.closest("[data-cambiar-cliente]");
    if (!elegir && !cambiar) return;
    var caja = (elegir || cambiar).closest("[data-selector-cliente]");
    if (!caja) return;
    var oculto = caja.querySelector('input[type="hidden"][name="cliente"]');
    var elegido = caja.querySelector("[data-cliente-elegido]");
    var buscador = caja.querySelector("[data-buscador-cliente]");
    var nuevo = caja.querySelector("[data-nuevo-cliente]");
    var resultados = caja.querySelector(".resultados-busqueda");
    if (elegir) {
      oculto.value = elegir.dataset.id;
      elegido.querySelector("[data-nombre]").textContent = elegir.dataset.nombre;
      var ini = elegido.querySelector("[data-iniciales]");
      if (ini) ini.textContent = elegir.dataset.nombre.split(/\s+/).slice(0, 2).map(function (p) { return p.charAt(0); }).join("").toUpperCase();
      elegido.classList.remove("oculto");
      buscador.classList.add("oculto");
      if (nuevo) { nuevo.classList.add("oculto"); nuevo.open = false; }
      if (resultados) resultados.innerHTML = "";
    } else {
      oculto.value = "";
      elegido.classList.add("oculto");
      buscador.classList.remove("oculto");
      if (nuevo) nuevo.classList.remove("oculto");
      var campo = buscador.querySelector("input");
      if (campo) { campo.value = ""; campo.focus(); }
    }
    oculto.dispatchEvent(new Event("change", { bubbles: true }));
  });

  /* ---------- Duración automática según el tipo de cita ---------- */
  document.addEventListener("change", function (e) {
    if (!e.target.matches('[data-formulario-cita] select[name="tipo"]')) return;
    var datos = document.getElementById("duraciones-tipo");
    var duracion = e.target.form.querySelector('input[name="duracion"]');
    if (!datos || !duracion) return;
    try {
      var mapa = JSON.parse(datos.textContent);
      if (mapa[e.target.value]) duracion.value = mapa[e.target.value];
    } catch (err) { /* sin datos */ }
  });

  /* ---------- Rellenar un campo con un ejemplo / enlaces con texto editable ---------- */
  document.addEventListener("click", function (e) {
    var r = e.target.closest("[data-rellenar]");
    if (r) {
      var campo = document.querySelector(r.dataset.rellenar);
      if (campo) { campo.value = r.dataset.texto; campo.focus(); if (campo.form && campo.form.requestSubmit) campo.form.requestSubmit(); }
      return;
    }
    var enlace = e.target.closest("a[data-texto-desde][data-base]");
    if (enlace) {
      var area = document.querySelector(enlace.dataset.textoDesde);
      if (area) enlace.href = enlace.dataset.base + encodeURIComponent(area.value);
    }
  });

  /* ---------- Autoenvío de filtros ---------- */
  document.addEventListener("change", function (e) {
    var el = e.target.closest("[data-autoenviar]");
    if (el && el.form) { if (el.form.requestSubmit) el.form.requestSubmit(); else el.form.submit(); }
  });

  /* ---------- Atajos de teclado (escritorio) ---------- */
  var atajos = { "/": "buscar", "n": "nueva-cita", "c": "nuevo-cliente", "m": "mensajes", "a": "agenda", "h": "inicio", "?": "ayuda" };
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var el = document.activeElement;
    if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
    if (document.querySelector("dialog[open]")) return;
    var accion = atajos[e.key];
    if (!accion) return;
    if (accion === "ayuda") { var a = document.getElementById("dialogo-atajos"); if (a) { e.preventDefault(); a.showModal(); } return; }
    if (accion === "buscar") {
      var campo = document.querySelector("[data-atajo-buscar]");
      if (campo) { e.preventDefault(); campo.focus(); return; }
    }
    var destino = document.querySelector('[data-atajo="' + accion + '"]');
    if (destino && destino.href) { e.preventDefault(); window.location.href = destino.href; }
  });

  /* ---------- HTMX ---------- */
  document.addEventListener("htmx:responseError", function (e) {
    var s = e.detail.xhr ? e.detail.xhr.status : 0;
    if (s === 429) avisar("Demasiadas peticiones seguidas. Espera un momento.", "error");
    else if (s === 403) avisar("No tienes permiso para hacer eso.", "error");
    else if (s !== 401) avisar("Algo ha fallado. Vuelve a intentarlo.", "error");
  });
  document.addEventListener("htmx:sendError", function () { avisar(gettext("Sin conexión. Revisa tu red e inténtalo otra vez."), "error"); });
  document.addEventListener("htmx:afterSwap", function (e) { iniciarAvisos(e.detail.target); });
  // Avisos enviados por el servidor en la cabecera HX-Trigger: {"aviso": {"texto": "...", "tipo": "success"}}
  document.addEventListener("aviso", function (e) { if (e.detail && e.detail.texto) avisar(e.detail.texto, e.detail.tipo); });

  /* ---------- Arranque ---------- */
  function iniciar() {
    prepararDialogo();
    iniciarAvisos();
    if ("serviceWorker" in navigator && document.body.dataset.sw) {
      navigator.serviceWorker.register(document.body.dataset.sw, { scope: "/" }).catch(function () {});
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar); else iniciar();
})();
