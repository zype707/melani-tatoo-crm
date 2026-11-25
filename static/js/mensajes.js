/* Bandeja de mensajes y editor de plantillas. */
(function () {
  "use strict";
  var gettext = function (s) { return window.gettext ? window.gettext(s) : s; };

  /* Al pulsar WhatsApp / SMS / Copiar:
     1. Se actualiza el enlace con el texto tal y como está ahora en el cuadro
        (por si se editó y aún no se guardó).
     2. El navegador abre WhatsApp o Mensajes (no se impide la navegación).
     3. En paralelo se avisa al servidor para que guarde el texto y muestre
        «¿Lo enviaste?». */
  document.addEventListener("click", function (e) {
    var boton = e.target.closest("[data-abrir-canal]");
    if (!boton) return;
    var area = document.querySelector(boton.dataset.texto);
    var texto = area ? area.value : "";
    if (boton.tagName === "A" && boton.dataset.base) {
      boton.href = boton.dataset.base + encodeURIComponent(texto);
    }
    var acciones = boton.closest(".mensaje-acciones");
    if (!window.htmx || !acciones) return;
    var enviar = function () {
      window.htmx.ajax("POST", boton.dataset.abrirCanal, {
        source: boton,
        target: "#" + acciones.id,
        swap: "outerHTML",
        values: { canal: boton.dataset.canal, texto: texto }
      });
    };
    // Dar tiempo a que el navegador procese el enlace antes de cambiar el DOM
    setTimeout(enviar, boton.tagName === "A" ? 400 : 50);
  });

  /* Contador de la bandeja */
  function actualizarContador() {
    var lista = document.querySelector("[data-bandeja]");
    var contador = document.querySelector("[data-contador-bandeja]");
    if (!lista || !contador) return;
    var n = lista.querySelectorAll(".mensaje:not(.mensaje-hecho)").length;
    contador.textContent = n;
    contador.classList.toggle("cifra-critica", n > 0);
    document.querySelectorAll(".nav-enlace .insignia, .nav-inferior .insignia, .pestanas .insignia").forEach(function (ins) {
      var enlace = ins.closest("a");
      if (enlace && enlace.getAttribute("href") === "/mensajes/") {
        if (n > 0) ins.textContent = n; else ins.remove();
      }
    });
    var vacia = document.querySelector("[data-bandeja-vacia]");
    if (vacia) vacia.classList.toggle("oculto", lista.querySelectorAll(".mensaje").length > 0);
  }
  document.addEventListener("bandeja-cambio", function () { setTimeout(actualizarContador, 50); });

  /* Editor de plantillas: insertar variable en el cursor */
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-insertar-variable]");
    if (!b) return;
    var area = document.querySelector("[data-editor-plantilla]");
    if (!area) return;
    var trozo = "{" + b.dataset.insertarVariable + "}";
    var ini = area.selectionStart || area.value.length;
    var fin = area.selectionEnd || ini;
    area.value = area.value.slice(0, ini) + trozo + area.value.slice(fin);
    area.focus();
    area.selectionStart = area.selectionEnd = ini + trozo.length;
    area.dispatchEvent(new Event("insertar", { bubbles: true }));
  });

  /* Mensaje libre: cargar el texto de una plantilla para el cliente elegido */
  document.addEventListener("change", function (e) {
    var sel = e.target.closest("[data-cargar-plantilla]");
    if (!sel || !sel.value) return;
    var destino = document.querySelector(sel.dataset.destino);
    var cliente = document.querySelector('input[type="hidden"][name="cliente"]');
    var url = sel.dataset.cargarPlantilla + "?plantilla=" + encodeURIComponent(sel.value) +
      "&cliente=" + encodeURIComponent(cliente ? cliente.value : "");
    fetch(url, { credentials: "same-origin", headers: { "HX-Request": "true" } })
      .then(function (r) { return r.ok ? r.text() : ""; })
      .then(function (texto) {
        if (destino && texto && (!destino.value.trim() || window.confirm(gettext("¿Sustituir el texto actual por la plantilla?")))) {
          destino.value = texto;
        }
      });
  });
})();
