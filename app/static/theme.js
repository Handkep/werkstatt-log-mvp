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

  input.addEventListener("change", () => {
    if (!label || !title) {
      return;
    }

    const files = Array.from(input.files);

    if (files.length === 0) {
      title.textContent = "Bilder auswählen";
      label.textContent = "JPG, PNG oder WebP";
      return;
    }

    title.textContent = files.length === 1 ? "Bild ausgewählt" : "Bilder ausgewählt";
    label.textContent = files.length === 1 ? files[0].name : `${files.length} Bilder ausgewählt`;
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
