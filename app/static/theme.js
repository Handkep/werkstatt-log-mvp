// Speicherung ist optional; blockiertes localStorage darf die UI nicht lahmlegen.
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); return true; } catch { return false; } },
  remove(key) { try { localStorage.removeItem(key); } catch { /* privat */ } },
};
const personalKeys = ["usage_person_name", "usage_house_number", "usage_house_group"];
function forgetPersonalData() {
  personalKeys.forEach((key) => storage.remove(key));
}
if (storage.get("usage_remember") === "no") forgetPersonalData();

const themeToggle = document.querySelector(".theme-toggle");

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  storage.set("theme", theme);
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    setTheme(currentTheme() === "dark" ? "light" : "dark");
  });
}

document.querySelectorAll("[data-admin-menu]").forEach((menu) => {
  const toggle = menu.querySelector("summary");
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.open) {
      menu.open = false;
      toggle.focus();
    }
  });
  menu.addEventListener("click", (event) => {
    if (event.target.closest("a")) menu.open = false;
  });
});

document.querySelectorAll(".file-input").forEach((input) => {
  const label = input.closest(".file-drop")?.querySelector("[data-file-label]");
  const title = input.closest(".file-drop")?.querySelector(".file-drop-title");
  const fileField = input.closest(".file-field");
  const previewList = fileField?.querySelector("[data-file-preview-list]");
  const defaultLabel = label?.dataset.defaultLabel || "JPG, PNG oder WebP";
  let selectedFiles = [];
  const previewUrls = new Set();
  function releasePreviews() {
    previewUrls.forEach((url) => URL.revokeObjectURL(url));
    previewUrls.clear();
  }
  window.addEventListener("pagehide", releasePreviews);

  function syncFiles() {
    const transfer = new DataTransfer();
    selectedFiles.forEach((file) => transfer.items.add(file));
    input.files = transfer.files;
  }

  function renderPreview() {
    if (!previewList) {
      return;
    }

    releasePreviews();
    previewList.innerHTML = "";
    selectedFiles.forEach((file, index) => {
      const item = document.createElement("div");
      item.className = "file-preview-item";

      const image = document.createElement("img");
      image.className = "file-preview-image";
      image.alt = "";
      image.width = 56;
      image.height = 56;
      image.style.width = "56px";
      image.style.height = "56px";
      image.style.maxWidth = "56px";
      image.style.maxHeight = "56px";
      image.style.objectFit = "cover";
      image.style.flexShrink = "0";
      const url = URL.createObjectURL(file);
      previewUrls.add(url);
      const release = () => { URL.revokeObjectURL(url); previewUrls.delete(url); };
      image.addEventListener("load", release, { once: true });
      image.addEventListener("error", release, { once: true });
      image.src = url;

      const meta = document.createElement("span");
      meta.textContent = file.name;

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "file-preview-remove";
      removeButton.textContent = "Entfernen";
      removeButton.addEventListener("click", () => {
        selectedFiles.splice(index, 1);
        syncFiles();
        updateFileDisplay();
      });

      item.append(image, meta, removeButton);
      previewList.append(item);
    });
  }

  function updateFileDisplay() {
    if (!label || !title) {
      return;
    }

    if (selectedFiles.length === 0) {
      title.textContent = "Bilder auswählen";
      label.textContent = defaultLabel;
      renderPreview();
      return;
    }

    title.textContent = selectedFiles.length === 1 ? "Bild ausgewählt" : "Bilder ausgewählt";
    label.textContent = selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} Bilder ausgewählt`;
    renderPreview();
  }

  input.addEventListener("change", () => {
    selectedFiles = Array.from(input.files);
    updateFileDisplay();
  });
});

document.querySelectorAll("[data-remember-usage-form]").forEach((form) => {
  const nameInput = form.querySelector("[data-remember-name]");
  const houseNumberInput = form.querySelector("[data-remember-house-number]");
  const houseGroupInputs = Array.from(form.querySelectorAll("[data-remember-house-group]"));
  const remember = form.querySelector("[data-remember-enabled]");
  const forgetButton = form.querySelector("[data-forget-personal]");
  const status = form.querySelector("[data-remember-status]");
  remember.checked = storage.get("usage_remember") !== "no";
  if (remember.checked && form.dataset.hasFormValues !== "1") {
    nameInput.value = storage.get("usage_person_name") || "";
    houseNumberInput.value = storage.get("usage_house_number") || "";
    const group = storage.get("usage_house_group");
    if (houseGroupInputs.some((input) => input.value === group)) {
      houseGroupInputs.forEach((input) => { input.checked = input.value === group; });
    }
  }

  function saveInputs() {
    if (!remember.checked) return;
    const saved = [
      storage.set("usage_remember", "yes"),
      storage.set("usage_person_name", nameInput.value.trim()),
      storage.set("usage_house_number", houseNumberInput.value.trim()),
      storage.set("usage_house_group", houseGroupInputs.find((input) => input.checked)?.value || ""),
    ].every(Boolean);
    status.textContent = saved ? "" : "Speichern auf diesem Gerät ist nicht verfügbar. Du kannst das Formular trotzdem nutzen.";
  }

  remember.addEventListener("change", () => {
    if (remember.checked) saveInputs();
    else {
      forgetPersonalData();
      storage.set("usage_remember", "no");
      status.textContent = "Eingaben werden auf diesem Gerät nicht gespeichert.";
    }
  });
  forgetButton.addEventListener("click", () => {
    forgetPersonalData();
    storage.set("usage_remember", "no");
    remember.checked = false;
    nameInput.value = "";
    houseNumberInput.value = "";
    houseGroupInputs.forEach((input, index) => { input.checked = index === 0; });
    status.textContent = "Gespeicherte Eingaben entfernt.";
  });
  nameInput.addEventListener("input", saveInputs);
  houseNumberInput.addEventListener("input", saveInputs);
  houseGroupInputs.forEach((input) => input.addEventListener("change", saveInputs));
  form.addEventListener("submit", saveInputs);
});

document.querySelectorAll("[data-help-form]").forEach((form) => {
  if (storage.get("usage_remember") !== "no" && form.dataset.hasFormValues !== "1") {
    form.querySelector("[data-help-name]").value = storage.get("usage_person_name") || "";
  }
});

document.querySelectorAll(".clickable-row").forEach((row) => {
  function eventStartedInControl(event) {
    return Boolean(event.target.closest("a, button, input, textarea, select, summary"));
  }

  row.addEventListener("click", (event) => {
    if (eventStartedInControl(event)) {
      return;
    }

    window.location.href = row.dataset.href;
  });

  row.addEventListener("keydown", (event) => {
    if (eventStartedInControl(event)) {
      return;
    }

    if (event.key === "Enter") {
      window.location.href = row.dataset.href;
    }
  });
});

const viewer = document.querySelector("[data-image-viewer]");

if (viewer) {
  // Der Dialog liegt außerhalb des währenddessen inerten Seiteninhalts.
  document.body.append(viewer);
  const inertSiblings = new Map();
  let previousOverflow = "";
  const viewerImage = viewer.querySelector("[data-viewer-image]");
  const viewerCount = viewer.querySelector("[data-viewer-count]");
  const prevButton = viewer.querySelector("[data-viewer-prev]");
  const nextButton = viewer.querySelector("[data-viewer-next]");
  const closeButton = viewer.querySelector(".image-viewer-close");
  let images = [];
  let currentIndex = 0;
  let lastTrigger = null;

  function showImage(index) {
    if (images.length === 0) {
      return;
    }

    currentIndex = (index + images.length) % images.length;
    viewerImage.src = `${viewer.dataset.viewerUploadBase || "/uploads/"}${encodeURIComponent(images[currentIndex])}`;
    viewerImage.alt = `Hochgeladenes Bild ${currentIndex + 1} von ${images.length}`;
    viewerImage.tabIndex = images.length > 1 ? 0 : -1;
    viewerImage.setAttribute("role", images.length > 1 ? "button" : "img");
    viewerImage.setAttribute("aria-label", images.length > 1 ? "Nächstes Bild anzeigen" : viewerImage.alt);
    viewerCount.textContent = `${currentIndex + 1} von ${images.length}`;
    prevButton.hidden = images.length < 2;
    nextButton.hidden = images.length < 2;
  }

  function openViewer(nextImages, trigger) {
    if (!Array.isArray(nextImages) || nextImages.length === 0) return;
    images = nextImages;
    lastTrigger = trigger ?? null;
    viewer.hidden = false;
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    Array.from(document.body.children).filter((item) => item !== viewer).forEach((item) => {
      inertSiblings.set(item, item.inert);
      item.inert = true;
    });
    showImage(0);
    closeButton.focus();
  }

  function closeViewer() {
    viewer.hidden = true;
    viewerImage.removeAttribute("src");
    document.body.style.overflow = previousOverflow;
    inertSiblings.forEach((wasInert, item) => { item.inert = wasInert; });
    inertSiblings.clear();
    lastTrigger?.focus();
  }

  // Auch nachgeladene Buchungskarten verwenden denselben Bildbetrachter.
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-viewer-images]");
    if (!button) return;
    event.stopPropagation();
    openViewer(JSON.parse(button.dataset.viewerImages), button);
  });

  viewer.querySelectorAll("[data-viewer-close]").forEach((button) => {
    button.addEventListener("click", closeViewer);
  });

  prevButton.addEventListener("click", () => showImage(currentIndex - 1));
  nextButton.addEventListener("click", () => showImage(currentIndex + 1));
  viewerImage.addEventListener("click", () => {
    if (images.length > 1) {
      showImage(currentIndex + 1);
    }
  });

  viewerImage.addEventListener("keydown", (event) => {
    if (["Enter", " "].includes(event.key) && images.length > 1) {
      event.preventDefault();
      showImage(currentIndex + 1);
    }
  });
  viewerImage.addEventListener("error", () => {
    viewerCount.textContent = "Bild konnte nicht geladen werden.";
  });
  document.addEventListener("keydown", (event) => {
    if (viewer.hidden) {
      return;
    }

    if (event.key === "Tab") {
      const controls = Array.from(viewer.querySelectorAll("button, [tabindex='0']"))
        .filter((item) => !item.hidden && !item.disabled);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
    if (event.key === "Escape") {
      closeViewer();
      return;
    }

    if (event.key === "ArrowLeft" && images.length > 1) {
      showImage(currentIndex - 1);
      return;
    }

    if (event.key === "ArrowRight" && images.length > 1) {
      showImage(currentIndex + 1);
    }
  });
}

const checklist = document.querySelector("[data-exit-checklist]");

if (checklist) {
  const inputs = Array.from(checklist.querySelectorAll("[data-checklist-input]"));
  const progress = checklist.querySelector("[data-checklist-progress]");
  const meter = checklist.querySelector("[data-checklist-meter]");
  const success = checklist.querySelector("[data-checklist-success]");

  function updateChecklist() {
    const completed = inputs.filter((input) => input.checked).length;
    const total = inputs.length;
    const percent = total === 0 ? 0 : (completed / total) * 100;

    progress.textContent = `${completed} / ${total} erledigt`;
    meter.style.width = `${percent}%`;
    success.hidden = completed !== total;
  }

  inputs.forEach((input) => {
    input.addEventListener("change", updateChecklist);
  });

  updateChecklist();
}


document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

document.querySelectorAll("[data-room-bookings]").forEach(async (container) => {
  function showMessage(message) {
    const note = document.createElement("p");
    note.className = "muted";
    note.setAttribute("role", "status");
    note.textContent = message;
    container.replaceChildren(note);
  }
  try {
    const response = await fetch(container.dataset.roomBookings, {
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
    });
    if (!response.ok) {
      showMessage(response.status === 403
        ? "Zum Lesen der Buchungen bitte einen aktuellen Raum-QR-Code scannen."
        : "Buchungen derzeit nicht verfügbar. Bitte später erneut versuchen.");
      return;
    }
    container.innerHTML = await response.text();
  } catch {
    showMessage("Buchungen konnten nicht geladen werden. Bitte später erneut versuchen.");
  } finally {
    container.setAttribute("aria-busy", "false");
  }
});


// Geheime Zugangslinks werden erst nach einem bewussten Klick angefordert.
document.querySelectorAll("[data-copy-access-link]").forEach((button) => {
  button.addEventListener("click", async () => {
    const status = button.closest("[data-access-link-control]").querySelector("[data-access-link-status]");
    status.hidden = false;
    status.textContent = "Zugangslink wird vorbereitet …";
    button.disabled = true;
    try {
      const csrf = button.dataset.csrfToken;
      const response = await fetch(button.dataset.copyAccessLink, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: { "Content-Type": csrf ? "application/x-www-form-urlencoded" : "application/json" },
        body: csrf ? new URLSearchParams({ csrf_token: csrf }) : "{}",
      });
      if (!response.ok) {
        status.textContent = response.status === 403
          ? "Dein Zugang ist abgelaufen oder widerrufen. Bitte einen aktuellen QR-Code scannen."
          : "Zugangslink derzeit nicht verfügbar. Bitte später erneut versuchen.";
        return;
      }
      const { url } = await response.json();
      try {
        await navigator.clipboard.writeText(url);
        status.textContent = "Zugangslink kopiert.";
      } catch {
        const input = document.createElement("input");
        input.type = "text";
        input.readOnly = true;
        input.value = url;
        input.setAttribute("aria-label", "Zugangslink zum Kopieren");
        status.textContent = "Automatisches Kopieren ist hier nicht möglich. Du kannst diesen Link kopieren:";
        status.append(input);
        input.focus();
        input.select();
      }
    } catch {
      status.textContent = "Zugangslink konnte nicht geladen werden. Bitte erneut versuchen.";
    } finally {
      button.disabled = false;
    }
  });
});
