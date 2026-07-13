const themeToggle = document.querySelector(".theme-toggle");

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("theme", theme);
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    setTheme(currentTheme() === "dark" ? "light" : "dark");
  });
}

document.querySelectorAll(".file-input").forEach((input) => {
  const label = input.closest(".file-drop")?.querySelector("[data-file-label]");
  const title = input.closest(".file-drop")?.querySelector(".file-drop-title");
  const fileField = input.closest(".file-field");
  const previewList = fileField?.querySelector("[data-file-preview-list]");
  const defaultLabel = label?.dataset.defaultLabel || "JPG, PNG oder WebP";
  let selectedFiles = [];

  function syncFiles() {
    const transfer = new DataTransfer();
    selectedFiles.forEach((file) => transfer.items.add(file));
    input.files = transfer.files;
  }

  function renderPreview() {
    if (!previewList) {
      return;
    }

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
      image.src = URL.createObjectURL(file);
      image.addEventListener("load", () => URL.revokeObjectURL(image.src), { once: true });

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

  const savedName = localStorage.getItem("usage_person_name");
  const savedHouseNumber = localStorage.getItem("usage_house_number");
  const savedHouseGroup = localStorage.getItem("usage_house_group");
  const hasServerValues = form.dataset.hasFormValues === "1";

  if (!hasServerValues && nameInput && !nameInput.value && savedName) {
    nameInput.value = savedName;
  }
  if (!hasServerValues && houseNumberInput && !houseNumberInput.value && savedHouseNumber) {
    houseNumberInput.value = savedHouseNumber;
  }
  if (!hasServerValues && savedHouseGroup) {
    houseGroupInputs.forEach((input) => {
      input.checked = input.value === savedHouseGroup;
    });
  }

  form.addEventListener("submit", () => {
    if (nameInput?.value.trim()) {
      localStorage.setItem("usage_person_name", nameInput.value.trim());
    }
    if (houseNumberInput?.value.trim()) {
      localStorage.setItem("usage_house_number", houseNumberInput.value.trim());
    }
    const checkedHouseGroup = houseGroupInputs.find((input) => input.checked);
    if (checkedHouseGroup) {
      localStorage.setItem("usage_house_group", checkedHouseGroup.value);
    }
  });
});

document.querySelectorAll(".clickable-row").forEach((row) => {
  function eventStartedInControl(event) {
    return Boolean(event.target.closest("a, button, input, textarea, select, summary, [data-card-menu]"));
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

document.addEventListener("click", (event) => {
  document.querySelectorAll("[data-card-menu][open]").forEach((menu) => {
    if (!menu.contains(event.target)) {
      menu.removeAttribute("open");
    }
  });
});

const viewer = document.querySelector("[data-image-viewer]");

if (viewer) {
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
    viewerImage.src = `/uploads/${images[currentIndex]}`;
    viewerCount.textContent = `${currentIndex + 1} von ${images.length}`;
    prevButton.hidden = images.length < 2;
    nextButton.hidden = images.length < 2;
  }

  function openViewer(nextImages, trigger) {
    images = nextImages;
    lastTrigger = trigger ?? null;
    viewer.hidden = false;
    document.body.style.overflow = "hidden";
    showImage(0);
    closeButton.focus();
  }

  function closeViewer() {
    viewer.hidden = true;
    viewerImage.removeAttribute("src");
    document.body.style.overflow = "";
    lastTrigger?.focus();
  }

  document.querySelectorAll("[data-viewer-images]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openViewer(JSON.parse(button.dataset.viewerImages), button);
    });
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

  document.addEventListener("keydown", (event) => {
    if (viewer.hidden) {
      return;
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
