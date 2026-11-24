// B: make StepQuest installable (see pwa_api.py and sw.js). Loaded on every page from _head.html.
// 1. Register the service worker, so the app opens offline and can be installed.
// 2. Chrome and Android say when the app can be installed ("beforeinstallprompt"); then every
//    button with data-install appears and opens the install dialog. Safari on iPhone has no such
//    event: there you use Share > Add to Home Screen, so the buttons stay hidden.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((err) => console.warn("Service worker:", err));
  });
}

let installPrompt = null;

function installButtons() { return document.querySelectorAll("[data-install]"); }

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();  // keep the browser's own mini bar away; our button asks instead
  installPrompt = event;
  installButtons().forEach((button) => { button.hidden = false; });
});

window.addEventListener("appinstalled", () => {
  installPrompt = null;
  installButtons().forEach((button) => { button.hidden = true; });
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-install]");
  if (!button || !installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  button.hidden = true;
});
