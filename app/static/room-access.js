// Früh im <head>: Fragmente gelangen weder in POST-URLs noch in die Browserhistorie.
(() => {
  const exchangePath = document.currentScript.dataset.roomAccessExchange;
  let current = null;

  function showStatus(attempt, message) {
    if (current !== attempt) return;
    attempt.message = message;
    const status = document.querySelector("[data-room-access-status]");
    if (status) {
      status.hidden = false;
      status.textContent = message;
    }
    const nav = document.querySelector(".site-nav");
    if (nav) {
      if (attempt.pending) nav.setAttribute("aria-busy", "true");
      else nav.removeAttribute("aria-busy");
    }
  }

  function fail(attempt, message) {
    if (current !== attempt || !attempt.pending) return;
    attempt.pending = false;
    attempt.token = null;
    attempt.target = null;
    clearTimeout(attempt.timer);
    attempt.controller.abort();
    showStatus(attempt, message);
  }

  // Delegiert schon vor DOMContentLoaded: Auch ein sehr früher Klick bleibt erhalten.
  document.addEventListener("click", (event) => {
    const attempt = current;
    if (!attempt?.pending || event.defaultPrevented || event.button !== 0
        || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
    if (!link || link.hasAttribute("download") || link.getAttribute("href").startsWith("#")
        || (link.target && link.target !== "_self")) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || !["http:", "https:"].includes(target.protocol)) return;
    event.preventDefault();
    attempt.target = target.href;
    showStatus(attempt, "Zugang wird aktiviert …");
  }, true);

  function rejectedMessage(response) {
    return response.status === 503
      ? "Der Raumzugang ist derzeit nicht verfügbar. Bitte die Administration informieren."
      : response.status === 429
        ? "Zu viele Zugangsversuche. Bitte warte kurz und scanne den QR-Code dann erneut."
        : "Die Zugangsprüfung wurde abgelehnt. Bitte scanne den aktuellen QR-Code erneut. Bleibt das Problem bestehen, informiere die Verwaltung.";
  }

  async function exchange(attempt) {
    if (current !== attempt) return;
    showStatus(attempt, attempt.message);
    if (!attempt.pending) return;
    if (!window.isSecureContext) {
      fail(attempt, "Der Raumzugang benötigt eine sichere Verbindung. Bitte die Administration informieren. Das Meldeformular kannst du weiterhin nutzen.");
      return;
    }
    try {
      const response = await fetch(exchangePath, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: attempt.controller.signal,
        body: JSON.stringify({ token: attempt.token }),
      });
      attempt.token = null;
      if (current !== attempt || !attempt.pending) return;
      if (!response.ok) {
        fail(attempt, rejectedMessage(response));
        return;
      }
      // Ein 204 allein beweist noch nicht, dass der Browser das Cookie mitsendet.
      const confirmation = await fetch("/rooms/latest-status", {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: attempt.controller.signal,
      });
      if (current !== attempt || !attempt.pending) return;
      if (!confirmation.ok) {
        fail(attempt, [401, 403].includes(confirmation.status)
          ? "Der Zugang konnte in diesem Browser nicht gespeichert werden. Bitte Cookies zulassen und den QR-Code erneut scannen."
          : rejectedMessage(confirmation));
        return;
      }
      attempt.pending = false;
      clearTimeout(attempt.timer);
      showStatus(attempt, "Zugang aktiviert.");
      if (attempt.target) window.location.assign(attempt.target);
      else window.location.reload();
    } catch {
      fail(attempt, "Die Verbindung zur Zugangsprüfung ist fehlgeschlagen. Bitte den QR-Code erneut scannen.");
    } finally {
      attempt.token = null;
    }
  }

  function captureAccess() {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    if (!fragment.has("access")) return;
    if (current) {
      clearTimeout(current.timer);
      current.token = null;
      current.controller.abort();
    }
    const attempt = {
      token: fragment.get("access"),
      pending: true,
      controller: new AbortController(),
      target: null,
      message: "Zugang wird aktiviert …",
    };
    current = attempt;
    window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    attempt.timer = setTimeout(() => {
      fail(attempt, "Die Zugangsprüfung dauert zu lange. Bitte die Verbindung prüfen und den QR-Code erneut scannen.");
    }, 15000);
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => exchange(attempt), { once: true });
    } else exchange(attempt);
  }
  captureAccess();
  window.addEventListener("hashchange", captureAccess);
})();
