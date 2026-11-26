    // map.html part (owner: A; B's additions are marked B:): the map, treasure pins, the info board and walking routes.
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ the map

    const map = L.map("map").setView([treasure.lat, treasure.lon], 17);

    // Colour satellite photos, with street and place names drawn on top
    // (photos alone have no names, which makes a walking route hard to follow).
    const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
    L.tileLayer(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, {
      maxZoom: 19,
      attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics"
    }).addTo(map);
    L.tileLayer(`${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`, {
      maxZoom: 19
    }).addTo(map);
    L.tileLayer(`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, {
      maxZoom: 19
    }).addTo(map);

    // ------------------------------------------------------------ treasure pins

    // A pixel pin, drawn in CSS. kind is "target" (a spinning gold coin: the
    // treasure the status box measures to), "treasure" (a chest: every other one)
    // or "found" (B: a green tick: one you already found).
    function pinIcon(kind) {
      return L.divIcon({
        className: `pin pin--${kind}`,
        html: '<div class="pin__grow"><div class="pin__shape"></div></div>',
        iconSize: [30, 36],
        iconAnchor: [15, 34],  // the tip of the pin sits on the treasure
      });
    }

    const markersById = new Map();  // treasure id -> its pin, so a found one can turn into a tick
    const foundIds = new Set();     // B: treasures you already found (Python says which: found_by_me)
    const ratingsById = new Map();  // B: treasure id -> {rating: {average, count}, mine}, from /api/treasures

    function addTreasurePin(t, kind) {
      const marker = L.marker([t.lat, t.lon], {
        icon: pinIcon(kind),
        title: t.name,
        zIndexOffset: kind === "target" ? 500 : 0
      }).addTo(map);
      marker.on("click", () => selectTreasure(t, marker));
      markersById.set(t.id, marker);
      addPinMarks(marker, t);
      return marker;
    }

    // A: little pixel marks on a pin: a green check if an admin verified the treasure,
    // a gem if it has a collectible to scan. Python says which (verified / collectible).
    const infoById = new Map();  // treasure id -> {verified, collectible}, from /api/treasures
    function addPinMarks(marker, t) {
      const pin = marker.getElement();
      if (!pin) return;
      pin.querySelector(".pin__marks")?.remove();
      const marks = document.createElement("span");
      marks.className = "pin__marks";
      for (const [on, sprite] of [[t.verified, "mark-verified"], [t.collectible, "mark-collectible"]]) {
        if (!on) continue;
        const mark = document.createElement("span");
        mark.className = `sprite sprite--${sprite}`;
        marks.append(mark);
      }
      if (marks.childElementCount) pin.append(marks);
    }

    // The treasure you are hunting: its pin is orange and the status card
    // measures to it. Starts as the first treasure, changes when you tap another.
    let huntId = treasure.id;
    let huntMarker = addTreasurePin(treasure, "target");

    function setHunt(t, marker) {
      // A found treasure keeps its tick, even while you look at it (replace does nothing then).
      huntMarker.getElement()?.classList.replace("pin--target", "pin--treasure");
      marker.getElement().classList.replace("pin--treasure", "pin--target");
      huntMarker = marker;
      huntId = t.id;
    }

    // Every other treasure players have hidden
    async function showOtherTreasures() {
      try {
        const res = await fetch("/api/treasures");
        const list = await res.json();
        if (!res.ok) throw new Error(list.error || "Could not load treasures");
        for (const t of list) {
          ratingsById.set(t.id, { rating: t.rating, mine: t.my_rating });
          // B: Python marks the ones you were already paid for (found_by_me); they show a tick.
          if (t.found_by_me) foundIds.add(t.id);
          infoById.set(t.id, { verified: t.verified, collectible: t.collectible, collected: t.collected_by_me,
                               appears: t.appears, notFound: t.not_found });  // B
          valueById.set(t.id, t.value);  // B: what a find pays now
          if (t.id !== treasure.id) addTreasurePin(t, t.found_by_me ? "found" : "treasure");
          else addPinMarks(huntMarker, t);  // the first pin was drawn before the list arrived
          // B: a treasure nobody has found for a while glows gold: it pays a bounty (treasure_value.py)
          if (t.value && t.value.label === "bounty" && !t.found_by_me) {
            markersById.get(t.id)?.getElement()?.classList.add("pin--bounty");
          }
          markMissingPin(t.id);  // B: "maybe missing" pins are greyed (not_found.js)
        }
        if (foundIds.has(treasure.id)) showTick(huntMarker);  // you found them all: even this one is ticked
        // B: /?treasure=<id> (from the welcome page) opens that treasure's board.
        const wanted = Number(params.get("treasure"));
        const wantedTreasure = list.find((t) => t.id === wanted);
        if (wantedTreasure && markersById.has(wanted)) selectTreasure(wantedTreasure, markersById.get(wanted));
        resumeJourney();  // A: carry on a journey the server remembers (after a reload or lost signal)
        resumeTrail();    // B: ...or a timed Treasure Trail
        applyMode();  // B: calm walks mark the calm spots
      } catch (err) {
        console.error("Treasure markers failed:", err);
      }
    }
    showOtherTreasures();

    // ------------------------------------------------------------ info board

    const board = document.getElementById("board");
    const boardKm = document.getElementById("boardKm");
    const boardMin = document.getElementById("boardMin");
    const boardSteps = document.getElementById("boardSteps");
    const boardCal = document.getElementById("boardCal");
    const boardNote = document.getElementById("boardNote");
    let selectedMarker = null;

    // Tap a treasure: grow its pin, slide the board in, and route to it.
    // textContent (not innerHTML) because names and hints come from players.
    let selectedTreasure = null;
    function selectTreasure(t, marker) {
      // While you are on a journey the map keeps measuring to that one treasure.
      if (journeyActive() && t.id !== journey.targetId) {
        journeyNote("Finish this journey before you pick another treasure.");
        return;
      }
      selectedTreasure = t;
      if (selectedMarker) selectedMarker.getElement().classList.remove("is-selected");
      selectedMarker = marker;
      marker.getElement().classList.add("is-selected");

      document.getElementById("boardName").textContent = t.name;
      document.getElementById("boardHint").textContent = t.description || "No hint for this one.";
      showBoardPhoto(t.id);
      showBoardStars(t.id);
      showBoardWorth(t.id);
      showBoardCalm(t.id);  // B
      const info = infoById.get(t.id) || {};
      const verifiedLine = document.getElementById("boardVerified");
      verifiedLine.textContent = info.verified
        ? "Verified by StepQuest"
        : "Not verified yet: hidden by a player and not checked by an admin. You can still go.";
      verifiedLine.classList.toggle("is-verified", Boolean(info.verified));
      const collectibleLine = document.getElementById("boardCollectible");
      collectibleLine.hidden = !info.collectible;
      collectibleLine.textContent = info.collected
        ? "You collected this treasure's trophy"
        : "Has a collectible: find the QR code at the spot and scan it (Collection > Scan)";
      showBoardReports(t.id);  // B: rain / night line, "maybe missing" line (not_found.js)
      boardKm.textContent = "–";
      boardMin.textContent = "–";
      boardSteps.textContent = "–";
      boardCal.textContent = "–";
      board.classList.add("is-open");
      board.setAttribute("aria-hidden", "false");

      setHunt(t, marker);
      updateStartButton();
      routeTarget = [t.lat, t.lon];
      routeVia = null;  // a new treasure starts with the normal route
      if (currentPos) {
        boardNote.textContent = "Finding a walking route…";
        drawRoute(currentPos, routeTarget, true);
        updateDistance(currentPos[0], currentPos[1]);  // status card switches right away
      } else {
        boardNote.textContent = "Waiting for your location…";
      }
    }

    // Ask for the treasure's photo; Python answers 404 when there is none, and the
    // picture stays hidden. Only reload when it is a different treasure.
    const boardPhoto = document.getElementById("boardPhoto");
    boardPhoto.addEventListener("load", () => { boardPhoto.hidden = false; });
    boardPhoto.addEventListener("error", () => { boardPhoto.hidden = true; });
    function showBoardPhoto(treasureId) {
      const url = `/api/treasures/${treasureId}/photo`;
      if (boardPhoto.getAttribute("src") === url) return;
      boardPhoto.hidden = true;
      boardPhoto.src = url;
    }

    // B: "★ 4.6 (12 ratings)" under the hint. Python works out the average.
    const boardStars = document.getElementById("boardStars");
    // B: "Worth 24 coins: nobody has found it for a while!" (Python writes the words)
    const valueById = new Map();
    const boardWorth = document.getElementById("boardWorth");
    function showBoardWorth(treasureId) {
      const value = valueById.get(treasureId);
      boardWorth.textContent = value && !foundIds.has(treasureId) ? value.note : "";
      boardWorth.className = "board__worth" + (value && value.label ? ` board__worth--${value.label}` : "");
    }
    function starsText(rating) {
      if (!rating || !rating.count) return "No ratings yet";
      return `★ ${rating.average.toFixed(1)} (${rating.count} rating${rating.count === 1 ? "" : "s"})`;
    }
    function showBoardStars(treasureId) {
      const info = ratingsById.get(treasureId);
      const stars = info ? starsText(info.rating) : "";
      boardStars.textContent = foundIds.has(treasureId) ? `You found this one · ${stars}` : stars;
    }

    function closeBoard() {
      board.classList.remove("is-open");
      board.setAttribute("aria-hidden", "true");
      if (selectedMarker) selectedMarker.getElement()?.classList.remove("is-selected");
      selectedMarker = null;
    }

    // B: a found treasure stays on the map as a green tick, so you can see where you've been.
    function showTick(marker) {
      const pin = marker.getElement();
      if (!pin) return;
      pin.classList.remove("pin--target", "pin--treasure");
      pin.classList.add("pin--found");
    }

    // B: you found it and Python paid you (or says you already had): the pin hops,
    // then turns into a tick. The route to it goes, since you are there.
    const COLLECT_DELAY_MS = 2500;  // long enough to read "You found ..." first
    function collectPin(treasureId) {
      const marker = markersById.get(treasureId);
      if (!marker || foundIds.has(treasureId)) return;
      foundIds.add(treasureId);
      setTimeout(() => {
        const pin = marker.getElement();
        pin?.classList.add("is-collected");
        setTimeout(() => {
          pin?.classList.remove("is-collected");
          showTick(marker);
          if (selectedTreasure && selectedTreasure.id === treasureId) { showBoardStars(treasureId); showBoardWorth(treasureId); }
          pin?.classList.remove("pin--bounty");  // B: found: no bounty for you any more
          if (treasureId === huntId) {
            routeTarget = null;  // nothing to walk to until you tap another treasure
            routeVia = null;
            newRouteBtn.hidden = true;
            if (routeLine) { routeLine.remove(); routeLine = null; }
          }
        }, 600);  // the length of the animation in app.css
      }, COLLECT_DELAY_MS);
    }

    document.getElementById("boardClose").addEventListener("click", closeBoard);
    map.on("click", closeBoard);  // tapping empty map closes it too

    // ------------------------------------------------------------ routes

    const sheet = document.getElementById("sheet");
    const statusBox = document.getElementById("status");
    const routeInfo = document.getElementById("routeInfo");
    let routeLine = null;
    let routeFrom = null;           // where the current route starts
    let routeTarget = [treasure.lat, treasure.lon];  // where it goes (changes when you tap a treasure)
    let routeVia = null;            // the random side-step point of a "New route", if any
    const newRouteBtn = document.getElementById("newRouteBtn");
    let routeRequestId = 0;         // so an old, slow answer can't replace a newer route
    const REROUTE_DISTANCE_M = 25;  // real GPS: ask for a new route after moving this far

    // Write the route summary in the status card and, if open, the info board.
    // A: as a row of small facts (0.31 km · 4 min · 419 steps · 10 kcal) instead of one long sentence.
    let routeFacts = {};
    function fact(value, unit) {
      const box = document.createElement("span");
      box.className = "route-fact";
      const number = document.createElement("strong");
      number.textContent = value;
      box.append(number, ` ${unit}`);
      return box;
    }
    function drawRouteFacts() {
      const f = routeFacts;
      // B: the big number above is the straight-line distance; this is the walk along paths.
      // With only a straight line they are the same, so it isn't shown twice.
      const parts = f.straight ? [fact(f.min, "min")] : [fact(f.km, "km walk"), fact(f.min, "min")];
      if (f.steps !== undefined) parts.push(fact(f.steps.toLocaleString(), "steps"), fact(f.kcal, "kcal"));
      const notes = [f.random && "new route", f.straight && "straight line", f.access && "step-free"].filter(Boolean);
      if (notes.length) {
        const note = document.createElement("span");
        note.className = "route-fact route-fact--note";
        note.textContent = notes.join(" · ");
        parts.push(note);
      }
      routeInfo.replaceChildren(...parts);
    }

    function showRoute(data) {
      const km = (data.distance_m / 1000).toFixed(2);
      const min = Math.max(1, Math.round(data.duration_s / 60));
      routeFacts = { km, min, straight: Boolean(data.warning), random: Boolean(routeVia), access: Boolean(data.access) };
      drawRouteFacts();
      routeInfo.hidden = false;
      boardKm.textContent = `${km} km`;
      boardMin.textContent = `${min} min`;
      boardNote.textContent = data.warning ? "Straight-line estimate: no walking-route service right now." : "";
      // B: step-free routes (Account page): Python writes the note (route_access.py)
      if (data.access) {
        boardNote.textContent = data.access.note;
      }
      showWalkStats(data.distance_m);
      showWeather(data.weather);
    }

    // B: the weather and how Python picked the route (none = weather unknown: the normal route)
    const weatherInfo = document.getElementById("weatherInfo");
    function showWeather(w) {
      weatherInfo.hidden = !w;
      if (!w) return;
      weatherInfo.dataset.kind = w.kind;
      // A: Python names the pixel icon (weather.py WEATHER_ICONS); no emoji in the text
      document.getElementById("weatherIcon").className =
        w.icon ? `weather-line__icon sprite sprite--icon-${w.icon}` : "weather-line__icon";
      document.getElementById("weatherHead").textContent = w.headline;
      document.getElementById("weatherTip").textContent = w.tip;
    }

    // Steps and calories: Python does the maths from the route length (/api/walk-stats).
    // The counter makes sure a slow answer for an old route can't replace a newer one.
    let statsRequestId = 0;
    async function showWalkStats(distanceM) {
      const requestId = ++statsRequestId;
      try {
        const res = await fetch(`/api/walk-stats?distance_m=${distanceM}`);
        const data = await res.json();
        if (requestId !== statsRequestId) return;
        if (!res.ok) throw new Error(data.error || "Stats request failed");
        boardSteps.textContent = data.steps.toLocaleString();
        boardCal.textContent = data.calories;
        Object.assign(routeFacts, { steps: data.steps, kcal: data.calories });
        drawRouteFacts();
        document.getElementById("boardWeight").textContent = data.weight_kg;
        document.getElementById("boardWeightNote").hidden = data.weight_source !== "default";
      } catch (err) {
        if (requestId !== statsRequestId) return;
        boardSteps.textContent = "–";
        boardCal.textContent = "–";
        console.error("Walk stats failed:", err);
      }
    }

    function showRouteError(message) {
      statsRequestId++;  // ignore any steps-and-calories answer still on its way
      routeInfo.textContent = `Could not get a route: ${message}`;
      routeInfo.hidden = false;
      boardNote.textContent = `Could not get a route: ${message}`;
    }

    // Space the map should keep free when zooming to a route: the status card
    // at the bottom, plus the open board. On a wide screen the board takes the
    // right side; on a phone it is almost full width, so it takes the top instead.
    function statusCard() { return document.querySelector(".sheet"); }

    function routePadding() {
      let top = 40, right = 40;
      if (board.classList.contains("is-open")) {
        const spaceLeft = map.getSize().x - board.offsetWidth;
        if (spaceLeft > 250) right = board.offsetWidth + 40;
        else top = board.offsetHeight + 30;
      }
      // Keep the route above whatever covers the bottom: the journey panel or the status card.
      const bottomBox = !journeyBox.hidden ? journeyBox : statusCard();
      const bottom = bottomBox ? bottomBox.offsetHeight + 40 : 150;
      return { paddingTopLeft: [40, top], paddingBottomRight: [right, bottom] };
    }

    // Ask Python for a walking route and draw it.
    // fit = true zooms the map to the whole route.
    // newRandom = true asks Python for a NEW random route to the same treasure (Feature 6).
    async function drawRoute(from, to, fit = false, newRandom = false) {
      if (!to) return;  // the treasure was collected: no route until you pick another
      if (trailActive) return;  // B: a Treasure Trail is on the map; "End trail" brings routes back
      const requestId = ++routeRequestId;
      routeFrom = from;
      const start = `${from[0]},${from[1]}`, end = `${to[0]},${to[1]}`;
      // Keep going through the random point (if any) when we reroute after you move.
      const via = routeVia ? `;${routeVia[0]},${routeVia[1]}` : "";
      const url = newRandom
        ? `/api/random-route?points=${start};${end}` + (routeVia ? `&current=${routeVia[0]},${routeVia[1]}` : "")
        : `/api/route?points=${start}${via};${end}`;
      try {
        const res = await fetch(url);
        const data = await res.json();
        if (requestId !== routeRequestId) return;  // a newer route was requested meanwhile
        if (!res.ok) throw new Error(data.error || "Route request failed");
        if (data.via) routeVia = data.via;           // Python picked a new side-step point
        if (data.via_reached) routeVia = null;      // you walked past it: straight to the treasure now
        newRouteBtn.hidden = false;
        if (routeLine) routeLine.remove();
        // Gold line with a dark edge so it stands out on satellite photos.
        // Square ends and corners so it looks drawn in pixels, like the rest of the map.
        // Dashed = straight-line fallback, so it's clear it isn't a real path.
        const dash = data.warning ? "10 10" : null;
        routeLine = L.featureGroup([
          L.polyline(data.path, { color: "#14231f", weight: 10, opacity: 0.9, dashArray: dash, lineCap: "square", lineJoin: "miter" }),
          L.polyline(data.path, { color: "#f2a93b", weight: 6, opacity: 1, dashArray: dash, lineCap: "square", lineJoin: "miter" })
        ]).addTo(map);
        if (fit) map.fitBounds(routeLine.getBounds(), routePadding());
        showRoute(data);
        loadCrossings(data.path);  // A: street crossings along this route
      } catch (err) {
        if (requestId !== routeRequestId) return;
        if (routeLine) { routeLine.remove(); routeLine = null; }  // don't leave an out-of-date line
        showRouteError(err.message);
      }
    }

    // "New route": Python picks a new random side-step point, so the same treasure gets another path.
    newRouteBtn.addEventListener("click", () => {
      if (currentPos && routeTarget) drawRoute(currentPos, routeTarget, true, true);
    });

