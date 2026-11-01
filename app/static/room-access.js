// Früh im <head>: Fragmente gelangen weder in POST-URLs noch in die Browserhistorie.
(() => {
  const exchangePath = document.currentScript.dataset.roomAccessExchange;
  function captureAccess() {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    if (!fragment.has("access")) return;
    let token = fragment.get("access");
    window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);

    async function exchange() {
      const status = document.querySelector("[data-room-access-status]");
      status.hidden = false;
      if (!window.isSecureContext) {
        status.textContent = "Der Raumzugang benötigt eine sichere Verbindung. Bitte die Administration informieren. Das Meldeformular kannst du weiterhin nutzen.";
        token = null;
        return;
      }
      status.textContent = "Raumzugang wird geprüft …";
      try {
        const response = await fetch(exchangePath, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          cache: "no-store",
          redirect: "error",
          body: JSON.stringify({ token }),
        });
        if (!response.ok) {
          status.textContent = response.status === 503
            ? "Der Raumzugang ist derzeit nicht verfügbar. Bitte die Administration informieren."
            : response.status === 429
              ? "Zu viele Zugangsversuche. Bitte warte kurz und scanne den QR-Code dann erneut."
              : "Dieser Raumzugang ist ungültig oder abgelaufen. Bitte den aktuellen QR-Code im Raum scannen.";
          return;
        }
        // Der Server entscheidet nach dem Neuladen über die sichtbaren Aktionen.
        window.location.reload();
      } catch {
        status.textContent = "Raumzugang konnte nicht geprüft werden. Bitte den QR-Code erneut scannen.";
      } finally {
        token = null;
      }
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", exchange, { once: true });
    else exchange();
  }
  captureAccess();
  window.addEventListener("hashchange", captureAccess);
})();
