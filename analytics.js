/* SG Alerts GA4 loader. Same behaviour as the inline gtag snippet on the homepage. */
(function () {
  "use strict";

  var host = window.location.hostname;
  if (
    !host ||
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "::1" ||
    host === "[::1]" ||
    /\.local$/.test(host)
  ) {
    return;
  }

  window.dataLayer = window.dataLayer || [];
  window.gtag =
    window.gtag ||
    function () {
      window.dataLayer.push(arguments);
    };
  window.gtag("js", new Date());
  window.gtag("config", "G-FXKD1E3N5Z");
})();
