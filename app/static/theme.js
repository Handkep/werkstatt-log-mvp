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
  row.addEventListener("click", () => {
    window.location.href = row.dataset.href;
  });

  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      window.location.href = row.dataset.href;
    }
  });
});

const viewer = document.querySelector("[data-image-viewer]");

if (viewer) {
  const viewerImage = viewer.querySelector("[data-viewer-image]");
  const viewerCount = viewer.querySelector("[data-viewer-count]");
  const prevButton = viewer.querySelector("[data-viewer-prev]");
  const nextButton = viewer.querySelector("[data-viewer-next]");
  let images = [];
  let currentIndex = 0;

  function showImage(index) {
    if (images.length === 0) {
      return;
    }

    currentIndex = (index + images.length) % images.length;
    viewerImage.src = `/uploads/${images[currentIndex]}`;
    viewerCount.textContent = `${currentIndex + 1} / ${images.length}`;
    prevButton.hidden = images.length < 2;
    nextButton.hidden = images.length < 2;
  }

  function openViewer(nextImages) {
    images = nextImages;
    viewer.hidden = false;
    showImage(0);
  }

  function closeViewer() {
    viewer.hidden = true;
    viewerImage.removeAttribute("src");
  }

  document.querySelectorAll("[data-viewer-images]").forEach((button) => {
    button.addEventListener("click", () => {
      openViewer(JSON.parse(button.dataset.viewerImages));
    });
  });

  viewer.querySelectorAll("[data-viewer-close]").forEach((button) => {
    button.addEventListener("click", closeViewer);
  });

  prevButton.addEventListener("click", () => showImage(currentIndex - 1));
  nextButton.addEventListener("click", () => showImage(currentIndex + 1));

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !viewer.hidden) {
      closeViewer();
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
