// Pixel-style dropdowns for every <select> on the site (owner: A).
//
// The browser's own dropdown can't be styled, so this draws our own button and list
// on top. The real <select> stays in the page, hidden but still in the form, so saving,
// FormData and "change" events all keep working: pages need no changes.
//
//   <select data-search="Find a treasure">  adds a search box (also added for long lists).
//   select.dispatchEvent(new Event("options-changed"))  redraws after options change
//   (adding or removing <option>s is also noticed by itself).
(() => {
  const SEARCH_FROM = 9;  // lists this long get a search box even without data-search
  let openOne = null;     // only one list is open at a time

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function enhance(select) {
    if (select.dataset.fancy || select.multiple || select.size > 1) return;
    select.dataset.fancy = "1";

    const box = make("div", "fancy-select");
    const button = make("button", "fancy-select__button");
    button.type = "button";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    const label = make("span", "fancy-select__label");
    button.append(label, make("span", "fancy-select__arrow"));
    const panel = make("div", "fancy-select__panel");
    panel.hidden = true;
    const search = make("input", "fancy-select__search");
    search.type = "search";
    search.placeholder = select.dataset.search || "Search";
    const list = make("ul", "fancy-select__list");
    list.setAttribute("role", "listbox");
    const nothing = make("p", "fancy-select__nothing", "Nothing matches");
    panel.append(search, list, nothing);

    // The real select stays (for the form) but is hidden. Its <label for> now points at our button.
    select.classList.add("fancy-select__native");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
    if (select.id) {
      button.id = select.id + "-fancy";
      document.querySelectorAll(`label[for="${CSS.escape(select.id)}"]`).forEach(l => { l.htmlFor = button.id; });
    }
    select.before(box);
    box.append(button, panel, select);

    let active = -1;  // the highlighted row while using the keyboard

    function rows() {
      return [...list.children].filter(li => !li.hidden);
    }

    function draw() {
      const chosen = select.options[select.selectedIndex];
      label.textContent = chosen ? chosen.text : "Choose…";
      button.disabled = select.disabled;
      list.replaceChildren(...[...select.options].map((option, i) => {
        const li = make("li", "fancy-select__option", option.text);
        li.setAttribute("role", "option");
        li.dataset.index = i;
        li.setAttribute("aria-selected", String(i === select.selectedIndex));
        if (option.disabled) li.setAttribute("aria-disabled", "true");
        return li;
      }));
      search.hidden = !(select.dataset.search || select.options.length >= SEARCH_FROM);
    }

    function highlight(index) {
      const shown = rows();
      shown.forEach(li => li.classList.remove("is-active"));
      active = Math.max(0, Math.min(index, shown.length - 1));
      if (shown[active]) {
        shown[active].classList.add("is-active");
        shown[active].scrollIntoView({ block: "nearest" });
      }
    }

    function filter() {
      const words = search.value.trim().toLowerCase();
      for (const li of list.children) li.hidden = words !== "" && !li.textContent.toLowerCase().includes(words);
      nothing.hidden = rows().length > 0;
      highlight(0);
    }

    function open() {
      if (openOne && openOne !== close) openOne();
      openOne = close;
      draw();
      panel.hidden = false;
      box.classList.add("is-open");
      button.setAttribute("aria-expanded", "true");
      search.value = "";
      filter();
      const chosen = rows().findIndex(li => Number(li.dataset.index) === select.selectedIndex);
      highlight(chosen < 0 ? 0 : chosen);
      // open upwards when there's no room below (e.g. near the bottom of a phone screen)
      const below = innerHeight - button.getBoundingClientRect().bottom;
      box.classList.toggle("opens-up", below < 260 && button.getBoundingClientRect().top > below);
      (search.hidden ? button : search).focus();
    }

    function close() {
      panel.hidden = true;
      box.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
      if (openOne === close) openOne = null;
    }

    function choose(li) {
      if (!li || li.getAttribute("aria-disabled")) return;
      const index = Number(li.dataset.index);
      close();
      button.focus();
      if (index === select.selectedIndex) return;
      select.selectedIndex = index;
      draw();
      select.dispatchEvent(new Event("change", { bubbles: true }));  // the page reacts as usual
    }

    function keys(event) {
      const shown = rows();
      if (event.key === "ArrowDown") { event.preventDefault(); panel.hidden ? open() : highlight(active + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); panel.hidden ? open() : highlight(active - 1); }
      else if (event.key === "Enter" && !panel.hidden) { event.preventDefault(); choose(shown[active]); }
      else if (event.key === "Escape" && !panel.hidden) { event.preventDefault(); close(); button.focus(); }
      else if (event.key === "Tab") close();
    }

    button.addEventListener("click", () => (panel.hidden ? open() : close()));
    button.addEventListener("keydown", keys);
    search.addEventListener("keydown", keys);
    search.addEventListener("input", filter);
    list.addEventListener("click", event => choose(event.target.closest(".fancy-select__option")));
    list.addEventListener("mousemove", event => {
      const li = event.target.closest(".fancy-select__option");
      if (li) highlight(rows().indexOf(li));
    });
    document.addEventListener("pointerdown", event => { if (!box.contains(event.target)) close(); });

    // The page changed the options or the value: redraw
    select.addEventListener("options-changed", draw);
    select.addEventListener("change", draw);
    new MutationObserver(draw).observe(select, { childList: true, attributes: true, attributeFilter: ["disabled"] });
    draw();
  }

  function enhanceAll(root) {
    if (root.tagName === "SELECT") enhance(root);
    else if (root.querySelectorAll) root.querySelectorAll("select").forEach(enhance);
  }

  function start() {
    enhanceAll(document);
    // Selects made later by the page (e.g. inside a map popup) get the same look
    new MutationObserver(changes => {
      for (const change of changes) change.addedNodes.forEach(enhanceAll);
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
