    // map.html part (owner: A): street crossings (Feature 7).
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ street crossings (A, Feature 7)

    // Python finds the crossings along the route (OpenStreetMap, crossings.py) and decides when
    // you are close enough to warn. The page draws a sign at each one and shows the warning.
    let routeCrossings = [];
    const warnedCrossings = new Set();  // warn once per crossing, not every 3 seconds
    const crossingLayer = L.layerGroup().addTo(map);
    const crossingAlert = document.getElementById("crossingAlert");
    const crossingInfo = document.getElementById("crossingInfo");
    const crossingIcon = L.divIcon({
      className: "crossing-sign",
      html: '<span class="sprite sprite--warning"></span>',
      iconSize: [24, 24],
      iconAnchor: [12, 22]
    });
    let crossingRequestId = 0;

    async function loadCrossings(path) {
      const requestId = ++crossingRequestId;
      try {
        const res = await fetch("/api/crossings", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path })
        });
        const data = await res.json();
        if (requestId !== crossingRequestId || !res.ok) return;  // a newer route came meanwhile
        routeCrossings = data.crossings;
        crossingLayer.clearLayers();
        for (const c of routeCrossings) {
          L.marker([c.lat, c.lon], { icon: crossingIcon, interactive: false, title: c.kind }).addTo(crossingLayer);
        }
        const n = routeCrossings.length;
        crossingInfo.textContent = data.warning
          || (n ? `${n} street crossing${n === 1 ? "" : "s"} on this route: we'll warn you before each one.`
                : "No street crossings on this route.");
        crossingInfo.hidden = false;
      } catch (err) {
        console.error("Crossings failed:", err);  // the route still works without warnings
      }
    }

    let crossingAlertTimer = null;
    async function checkCrossing(lat, lon) {
      if (!routeCrossings.length) return;
      try {
        const res = await fetch("/api/crossings/warning", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat, lon, crossings: routeCrossings })
        });
        const data = await res.json();
        const w = data.warning;
        if (!res.ok || !w || warnedCrossings.has(w.id)) return;
        warnedCrossings.add(w.id);
        crossingAlert.textContent = w.text;
        crossingAlert.hidden = false;
        if (navigator.vibrate) navigator.vibrate([200, 100, 200]);  // phones buzz, so you look up
        clearTimeout(crossingAlertTimer);
        crossingAlertTimer = setTimeout(() => { crossingAlert.hidden = true; }, 7000);
      } catch (err) { /* offline: no new warnings until the connection is back */ }
    }
    crossingAlert.addEventListener("click", () => { crossingAlert.hidden = true; });

