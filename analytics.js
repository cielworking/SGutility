(function () {
  "use strict";

  var measurementId = "G-FXKD1E3N5Z";
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () {
    window.dataLayer.push(arguments);
  };

  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return;
  }

  window.gtag("js", new Date());
  window.gtag("config", measurementId);
})();
