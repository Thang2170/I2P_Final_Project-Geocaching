    // map.html part (owner: A; B's additions are marked B:): your position: GPS, drag mode and fake positions.
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ your position

    // You are a little walking explorer (the sprite is drawn in pixel.css).
    // The anchor is at the feet, so the explorer stands on your position.
    // A: the Gold pin from the shop turns your own marker gold. Python says if you own it.
    let goldPin = false;
    fetch("/api/me/perks")
      .then(res => res.ok ? res.json() : {})
      .then(data => {
        goldPin = Boolean(data.gold_pin);
        if (goldPin && userDot) userDot.setIcon(youIcon());  // the marker may already be on the map
      })
      .catch(() => {});

    function youIcon() {
      return L.divIcon({
        className: goldPin ? "you-marker you-marker--gold" : "you-marker",
        html: '<span class="sprite sprite--explorer"></span>',
        iconSize: [48, 48],
        iconAnchor: [24, 46]
      });
    }

    let userDot = null;
    let currentPos = null;  // [lat, lon] of the last known position
    let firstFix = true;
    let lastSent = 0;

    // A: tell the server where you are, so the admin's live map can show you.
    // Every 10 seconds, even if you stand still (GPS only reports when you move),
    // because the admin map hides anyone not heard from for 2 minutes.
    const POSITION_EVERY_MS = 10000;
    function sendPosition() {
      if (!currentPos) return;
      fetch("/api/me/position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat: currentPos[0], lon: currentPos[1] })
      }).catch(() => {});  // not part of the game, so never bother the player if it fails
    }
    setInterval(sendPosition, POSITION_EVERY_MS);

    async function showPosition(lat, lon, force = false) {
      currentPos = [lat, lon];
      journeyPoint(lat, lon);
      if (startBtn.disabled && !journeyActive()) updateStartButton();  // the first fix lets you start
      // In drag mode the draggable marker already shows where you are
      if (!dragMode) {
        if (userDot) userDot.setLatLng(currentPos);
        else userDot = L.marker(currentPos, {
          icon: youIcon(), interactive: false, zIndexOffset: 1000
        }).addTo(map);
      }

      // Only recenter on the first fix, or the map fights the user's panning
      if (firstFix) {
        map.setView(currentPos, 17);
        firstFix = false;
        drawRoute(currentPos, routeTarget, true);
        if (trail && !trailLayer) drawTrailLeg(true);  // B: a trail carried on before the GPS answered
        else if (againId && !trail) walkAgain();      // B: ↻ Walk it again, from My trails
        sendPosition();  // show up on the admin map straight away, not after 10 seconds
      } else if (!dragMode && routeFrom && map.distance(routeFrom, currentPos) > REROUTE_DISTANCE_M) {
        // Real GPS: the user walked away from where the route started, so make a new one.
        // (Drag mode reroutes when you let go of the marker instead, see "dragend" below.)
        drawRoute(currentPos, routeTarget);
      }

      // Ask Python at most once every 3 seconds
      const now = Date.now();
      if (!force && now - lastSent < 3000) return;
      lastSent = now;
      updateDistance(lat, lon);
      checkTrail(lat, lon);  // B: reached the next trail checkpoint?
    }

    // A: the distance is the big number on the card and the treasure's name sits after it.
    // statusBox.textContent still reads "173 m to Pond bench" (the journey panel copies it).
    const trek = document.getElementById("trek");
    let trekStart = { id: null, meters: 0 };  // how far it was when you picked this treasure

    function showDistance(meters, name, found) {
      const big = document.createElement("span");
      big.className = "sheet__meters";
      big.textContent = meters;
      const unit = document.createElement("small");
      unit.textContent = " m";
      big.append(unit);
      const to = document.createElement("span");
      to.className = "sheet__to";
      to.textContent = ` to ${name}`;
      statusBox.replaceChildren(big, to);
      // The explorer walks along the little path: 0 = where you started, 1 = at the chest
      if (trekStart.id !== huntId || meters > trekStart.meters) trekStart = { id: huntId, meters: Math.max(meters, 1) };
      const done = found ? 1 : Math.max(0, Math.min(1, 1 - meters / trekStart.meters));
      trek.style.setProperty("--done", done.toFixed(3));
      trek.hidden = false;
    }

    // Ask Python how far you are from the treasure you are hunting
    async function updateDistance(lat, lon) {
      const askedFor = huntId;
      try {
        const res = await fetch(`/api/distance?lat=${lat}&lon=${lon}&treasure_id=${huntId}`);
        const data = await res.json();
        if (askedFor !== huntId) return;  // you picked another treasure meanwhile
        if (!res.ok) throw new Error(data.error || "Distance request failed");
        if (data.found) {
          statusBox.textContent = foundText(data.treasure, askedFor);
          trek.style.setProperty("--done", "1");
        } else {
          showDistance(Math.round(data.meters), data.treasure, false);
        }
        sheet.classList.toggle("is-found", data.found);
        checkCrossing(lat, lon);  // A: about to cross a street?
        if (data.found) claimCoins(askedFor, data.treasure, lat, lon);
        if (data.found && askedFor === raceTreasureId) reportArrival(lat, lon);  // A: hunt race
      } catch (err) {
        statusBox.textContent = `Could not get distance: ${err.message}`;
        arrivedWhileOffline();  // A: no signal at the treasure? still count it
      }
    }

    if (dragMode) {
      const startLat = treasure.lat + 0.001;
      const dragMarker = L.marker([startLat, treasure.lon], {
        draggable: true,
        icon: youIcon(),
        zIndexOffset: 1000,
        title: "Drag to simulate your location"
      }).addTo(map);

      statusBox.textContent = "Drag the explorer to simulate your location";
      showPosition(startLat, treasure.lon, true);
      // While dragging: normal 3-second limit, so we don't flood the server
      dragMarker.on("drag", event => {
        const position = event.target.getLatLng();
        showPosition(position.lat, position.lng);
      });
      // Let go of the marker: exact distance now, and a new route from where you dropped it
      dragMarker.on("dragend", event => {
        const position = event.target.getLatLng();
        showPosition(position.lat, position.lng, true);
        drawRoute([position.lat, position.lng], routeTarget);
      });
    } else if (fake) {
      // Development mode: http://127.0.0.1:5000/?fake=24.7960,120.9950
      const [fLat, fLon] = fake.split(",").map(Number);
      if (!Number.isFinite(fLat) || !Number.isFinite(fLon)) {
        statusBox.textContent = "Use ?fake=lat,lon, for example ?fake=24.7960,120.9950";
      } else {
        showPosition(fLat, fLon);
      }
    } else if (!navigator.geolocation) {
      statusBox.textContent = "Location is not supported by this browser.";
    } else {
      navigator.geolocation.watchPosition(
        pos => showPosition(pos.coords.latitude, pos.coords.longitude),
        err => { statusBox.textContent = "Location problem: " + err.message; },
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 30000 }
      );
    }
