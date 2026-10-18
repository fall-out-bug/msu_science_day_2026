if (window.mermaid) {
  window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
  window.mermaid.run({ querySelector: ".mermaid" });
}

const screens = document.querySelectorAll("button[data-screen-image]");
if (screens.length) {
  const dialog = document.createElement("dialog");
  dialog.className = "screen-preview";
  dialog.innerHTML = '<button type="button" class="screen-preview-close" aria-label="Закрыть">×</button><img alt="Экран схемы">';
  const image = dialog.querySelector("img");
  dialog.querySelector("button").addEventListener("click", () => dialog.close());
  screens.forEach((button) => button.addEventListener("click", () => {
    image.src = button.dataset.screenImage;
    image.alt = button.dataset.screenTitle || button.getAttribute("aria-label") || "Экран схемы";
    dialog.showModal();
  }));
  document.body.append(dialog);
}
