/* Firma con el dedo (o ratón) en un canvas. Exporta PNG al campo oculto «firma». */
(function () {
  "use strict";

  function iniciar() {
    var form = document.querySelector("[data-formulario-firma]");
    if (!form) return;
    var lienzo = form.querySelector("[data-lienzo-firma]");
    var campo = form.querySelector('input[name="firma"]');
    var ctx = lienzo.getContext("2d");
    var trazos = 0, dibujando = false, ultimo = null;

    function ajustar() {
      var ratio = Math.max(window.devicePixelRatio || 1, 1);
      var caja = lienzo.getBoundingClientRect();
      var copia = trazos ? lienzo.toDataURL("image/png") : null;
      lienzo.width = Math.round(caja.width * ratio);
      lienzo.height = Math.round(caja.height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.lineWidth = 2.6;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#01161b";
      if (copia) {
        var img = new Image();
        img.onload = function () { ctx.drawImage(img, 0, 0, caja.width, caja.height); };
        img.src = copia;
      }
    }

    function punto(e) {
      var caja = lienzo.getBoundingClientRect();
      return { x: e.clientX - caja.left, y: e.clientY - caja.top };
    }

    lienzo.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      lienzo.setPointerCapture(e.pointerId);
      dibujando = true;
      ultimo = punto(e);
      ctx.beginPath();
      ctx.arc(ultimo.x, ultimo.y, 1.2, 0, Math.PI * 2);
      ctx.fillStyle = "#01161b";
      ctx.fill();
    });
    lienzo.addEventListener("pointermove", function (e) {
      if (!dibujando) return;
      e.preventDefault();
      var p = punto(e);
      ctx.beginPath();
      ctx.moveTo(ultimo.x, ultimo.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      ultimo = p;
    });
    function terminar() {
      if (!dibujando) return;
      dibujando = false;
      trazos += 1;
      lienzo.parentNode.classList.add("con-firma");
    }
    lienzo.addEventListener("pointerup", terminar);
    lienzo.addEventListener("pointercancel", terminar);
    lienzo.addEventListener("pointerleave", terminar);

    form.querySelector("[data-borrar-firma]").addEventListener("click", function () {
      ctx.clearRect(0, 0, lienzo.width, lienzo.height);
      trazos = 0;
      campo.value = "";
      lienzo.parentNode.classList.remove("con-firma");
    });

    form.addEventListener("submit", function (e) {
      if (!trazos) {
        e.preventDefault();
        if (window.estudioAvisar) window.estudioAvisar("Falta tu firma en el recuadro.", "error");
        lienzo.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      campo.value = lienzo.toDataURL("image/png");
    });

    ajustar();
    var temporizador;
    window.addEventListener("resize", function () { clearTimeout(temporizador); temporizador = setTimeout(ajustar, 150); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar); else iniciar();
})();
