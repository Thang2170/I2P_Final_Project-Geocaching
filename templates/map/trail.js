    // map.html part (owner: B): the compact status card and Treasure Trails (plan, walk, carry on).
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ B: compact status card
    // The card shows the essentials; "More" opens coins, walking mode, team and crossings.
    // The choice is remembered on this phone.
    const sheetMore = document.getElementById("sheetMore");
    const sheetMoreBtn = document.getElementById("sheetMoreBtn");
    function setSheetMore(open) {
      sheetMore.hidden = !open;
      sheet.classList.toggle("is-more", open);
      sheetMoreBtn.setAttribute("aria-expanded", String(open));
      document.getElementById("sheetMoreLabel").textContent = open ? "Less" : "More";  // A: the chevron flips in CSS
      try { localStorage.setItem("sheetMore", open ? "1" : "0"); } catch (err) { /* private mode */ }
    }
    sheetMoreBtn.addEventListener("click", () => setSheetMore(sheetMore.hidden));
    try { setSheetMore(localStorage.getItem("sheetMore") === "1"); } catch (err) { setSheetMore(false); }

    // ------------------------------------------------------------ Treasure Trail (B)
    // You pick a goal; Python plans a loop through treasures you haven't found (trail_planner.py).
    // The map shows ONE leg at a time: the next checkpoint and the route to it. Python decides
    // when you reached it (/api/trail/progress); then the next leg appears. The last checkpoint
    // is back where you started.
    let trailActive = false;
    let trailLayer = null;
    let trail = null;  // {checkpoints: [{lat, lon, name, label}], index, legFrom}
    const trailBtn = document.getElementById("trailBtn");
    const trailBox = document.getElementById("trailBox");
    const trailMsg = document.getElementById("trailMsg");
    const trailEnd = document.getElementById("trailEnd");
    const trailStartBtn = document.getElementById("trailStartBtn");

    function trailSay(text) {
      trailMsg.textContent = text;
      trailMsg.hidden = !text;
      // During a timed trail the status card is hidden: show the checkpoint line in the panel
      if (journey.kind === "trail" && journey.state !== "idle" && text) jEls.msg.textContent = text;
    }

    trailBtn.addEventListener("click", () => {
      trailBox.hidden = !trailBox.hidden;
      trailBtn.setAttribute("aria-expanded", String(!trailBox.hidden));
    });

    // B: loop back here, or one way (ends at the last treasure, so the same steps reach further)
    let trailShape = "loop";
    for (const btn of document.querySelectorAll(".trail-shape__btn")) {
      btn.addEventListener("click", () => {
        trailShape = btn.dataset.shape;
        for (const b of document.querySelectorAll(".trail-shape__btn")) {
          b.classList.toggle("is-on", b === btn);
          b.setAttribute("aria-pressed", String(b === btn));
        }
        document.getElementById("trailShapeText").textContent = trailShape === "loop"
          ? "The loop starts and ends here." : "It starts here and ends at the last treasure.";
      });
    }

    function stopIcon(label, kind = "") {
      const number = document.createElement("span");  // an element, so no HTML text is ever parsed
      number.className = "trail-stop__n";
      number.textContent = String(label);
      const size = kind ? 22 : 30;  // the other checkpoints are smaller than the next one
      return L.divIcon({ className: `trail-stop ${kind}`.trim(), html: number, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
    }

    // B: "Show all checkpoints": the other checkpoints as small pins, with no route to them.
    // Ones you already reached get a tick. The choice is remembered on this phone.
    const trailToggle = document.getElementById("trailToggle");
    const trailShowAll = document.getElementById("trailShowAll");
    let trailOthers = null;
    try { trailShowAll.checked = localStorage.getItem("trailShowAll") === "1"; } catch (err) { /* private mode */ }
    function drawTrailOthers() {
      if (trailOthers) { trailOthers.remove(); trailOthers = null; }
      if (!trail || !trailShowAll.checked) return;
      trailOthers = L.layerGroup(trail.checkpoints
        .map((cp, i) => i === trail.index ? null : L.marker([cp.lat, cp.lon], {
          icon: stopIcon(i < trail.index ? "" : cp.label, i < trail.index ? "trail-stop--done" : "trail-stop--later"),
          interactive: false, zIndexOffset: 400
        }))
        .filter(Boolean)).addTo(map);
    }
    trailShowAll.addEventListener("change", () => {
      try { localStorage.setItem("trailShowAll", trailShowAll.checked ? "1" : "0"); } catch (err) { /* private mode */ }
      drawTrailOthers();
    });

    function endTrail(message = "") {
      if (journey.kind === "trail" && journeyActive()) finishJourney(false);  // stopped early: not saved
      trailActive = false;
      trail = null;
      if (trailLayer) { trailLayer.remove(); trailLayer = null; }
      trailEnd.hidden = true;
      trailStartBtn.hidden = true;
      trailToggle.hidden = true;  // B
      drawTrailOthers();          // (trail is gone, so this removes the pins)
      trailBtn.hidden = false;
      trailSay(message);
      if (currentPos && routeTarget) drawRoute(currentPos, routeTarget, !message);
    }
    trailEnd.addEventListener("click", () => endTrail());

    // Draw only the next checkpoint and the walking route from you to it.
    async function drawTrailLeg(fit = false) {
      if (!trail || !currentPos) return;
      const cp = trail.checkpoints[trail.index];
      const requestId = ++routeRequestId;  // an older route still on its way must not replace this leg
      trail.legFrom = currentPos;
      const total = trail.checkpoints.length;
      trailSay(`Checkpoint ${trail.index + 1} of ${total}: ${cp.name}`);
      try {
        const res = await fetch(`/api/route?points=${currentPos[0]},${currentPos[1]};${cp.lat},${cp.lon}`);
        const data = await res.json();
        if (requestId !== routeRequestId || !trail) return;
        if (!res.ok) throw new Error(data.error || "Route request failed");
        if (trailLayer) trailLayer.remove();
        const dash = data.warning ? "10 10" : null;
        trailLayer = L.featureGroup([
          L.polyline(data.path, { color: "#14231f", weight: 10, opacity: 0.9, dashArray: dash, lineCap: "square", lineJoin: "miter" }),
          L.polyline(data.path, { color: "#4fc3b0", weight: 6, opacity: 1, dashArray: dash, lineCap: "square", lineJoin: "miter" }),
          L.marker([cp.lat, cp.lon], { icon: stopIcon(cp.label), interactive: false, zIndexOffset: 500 })
        ]).addTo(map);
        if (fit) map.fitBounds(trailLayer.getBounds(), routePadding());
        drawTrailOthers();  // B: the other checkpoints, if you chose to see them
        const m = Math.round(data.distance_m);
        trailSay(`Checkpoint ${trail.index + 1} of ${total}: ${cp.name} · ${m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`}` +
                 ` · about ${Math.max(1, Math.round(data.duration_s / 60))} min${data.warning ? " (straight line)" : ""}`);
        showWeather(data.weather);
      } catch (err) {
        if (requestId === routeRequestId) trailSay(`Could not get the route to the next checkpoint: ${err.message}`);
      }
    }

    // Python checks whether you reached the checkpoint; if so, the next leg is drawn.
    async function checkTrail(lat, lon) {
      if (!trail) return;
      const asked = trail;
      try {
        const res = await fetch("/api/trail/progress", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat, lon, index: asked.index,
                                 checkpoints: asked.checkpoints.map(c => [c.lat, c.lon]) })
        });
        const data = await res.json();
        if (!res.ok || trail !== asked) return;
        // Every checkpoint you just reached: collect its treasure (Python checks you are there)
        for (const cp of asked.checkpoints.slice(asked.index, data.index)) {
          if (cp.id) claimCoins(cp.id, cp.name, lat, lon);
          trailSplit(cp);
        }
        if (data.done) { finishTrailWalk(lat, lon); return; }
        if (data.reached) {
          trail.index = data.index;
          trailJourneyTarget();
          drawTrailLeg(true);
          if (journey.kind === "trail" && journeyActive()) keepTrail();  // B: keep the new checkpoint
        } else if (trail.legFrom && map.distance(trail.legFrom, [lat, lon]) > REROUTE_DISTANCE_M) {
          drawTrailLeg();  // you walked off the route: a fresh route to the same checkpoint
        }
      } catch (err) {
        console.error("Trail check failed:", err);
      }
    }

    for (const pick of document.querySelectorAll(".trail-pick")) {
      pick.addEventListener("click", async () => {
        if (!currentPos) { trailSay("Waiting for your location…"); return; }
        const goal = pick.dataset.steps ? { steps: Number(pick.dataset.steps) } : { minutes: Number(pick.dataset.minutes) };
        trailSay(trailShape === "loop" ? "Planning your loop…" : "Planning your trail…");
        try {
          const res = await fetch("/api/trail", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lat: currentPos[0], lon: currentPos[1], ...goal, shape: trailShape,
                                   skip_low: document.getElementById("trailSkipLow").checked })
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || "Could not plan a trail");
          if (!data.stops.length) { trailSay(data.message); return; }
          showPlannedTrail(data);
        } catch (err) {
          trailSay(err.message);
        }
      });
    }

    // Put a planned trail on the map (from Plan a trail, or Walk it again on My trails).
    function showPlannedTrail(data) {
          trailActive = true;
          if (routeLine) { routeLine.remove(); routeLine = null; }
          routeInfo.hidden = true;     // the one-treasure route summary doesn't apply now
          newRouteBtn.hidden = true;   // (both come back with the route when the trail ends)
          trail = {
            index: 0,
            legFrom: null,
            checkpoints: [
              ...data.stops.map(stop => ({ id: stop.id, lat: stop.lat, lon: stop.lon, name: stop.name, label: stop.order })),
              // a loop ends back here; a one-way trail ends at its last treasure
              ...(data.shape === "oneway" ? [] : [{ lat: data.start[0], lon: data.start[1], name: "back to the start", label: "S" }])
            ]
          };
          trail.shape = data.shape || "loop";
          trailBox.hidden = true;
          trailBtn.setAttribute("aria-expanded", "false");
          trail.start = data.start;
          trailBtn.hidden = true;
          trailEnd.hidden = false;
          trailStartBtn.hidden = false;  // B: walk it with the live panel
          trailToggle.hidden = false;
          if (data.message) trailSay(data.message);
          drawTrailLeg(true);
    }

    // B: /?trail=<walk id>, from "Walk it again" on My trails: the same treasures in the same
    // order, from where you are now, so you can beat your time. Asked once the GPS answers.
    let againId = Number(params.get("trail")) || null;
    async function walkAgain() {
      const id = againId;
      againId = null;
      trailSay("Setting up your trail again…");
      try {
        const res = await fetch(`/api/trail/walks/${id}/again?lat=${currentPos[0]}&lon=${currentPos[1]}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Could not set up that trail again");
        showPlannedTrail(data);
      } catch (err) {
        trailSay(err.message);
      }
    }

    // ---- B: walk a trail with the live panel, like a run tracker (time, pace, splits)
    function trailJourneyTarget() {
      if (journey.kind !== "trail" || !trail) return;
      const cp = trail.checkpoints[trail.index];
      Object.assign(journey, { name: cp.name, target: [cp.lat, cp.lon], checkpoint: trail.index + 1 });
      renderJourney();
    }

    function trailSplit(cp) {
      if (journey.kind !== "trail" || !journeyActive()) return;
      journey.splits.push(Math.round(journey.elapsedMs / 1000));
      journeyNote(`Checkpoint ${cp.label}: ${cp.name} at ${fmtTime(journey.elapsedMs)}`);
    }

    trailStartBtn.addEventListener("click", () => {
      if (!trail || journeyActive() || !currentPos) return;
      const cp = trail.checkpoints[trail.index];
      startJourney({ kind: "trail", id: null, name: cp.name, lat: cp.lat, lon: cp.lon });
      Object.assign(journey, { checkpoint: trail.index + 1, checkpoints: trail.checkpoints.length, splits: [] });
      trailStartBtn.hidden = true;
      jEls.msg.textContent = trailMsg.textContent;
      renderJourney();
      keepTrail();  // B: the server keeps it, so a reload can carry on
    });

    // ---- B: carry on a timed trail after a reload or a closed browser (trail_api.py)
    function keepTrail() {
      if (!trail || journey.kind !== "trail" || !journeyActive()) return;
      journey.progressAt = Date.now();
      fetch("/api/trail/active", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          checkpoints: trail.checkpoints, index: trail.index, start: trail.start, splits: journey.splits, shape: trail.shape,
          meters: Math.round(journey.meters), elapsed_s: Math.round(journey.elapsedMs / 1000)
        })
      }).catch(() => {});  // offline: the next try in 30 s
    }

    function forgetTrail() {
      fetch("/api/trail/active", { method: "DELETE" }).catch(() => queueForLater("/api/trail/active", {}, "DELETE"));
    }

    async function resumeTrail() {
      if (journeyActive() || trail) return;
      try {
        const res = await fetch("/api/trail/active");
        if (!res.ok) return;
        const data = await res.json();
        if (data.expired) { showNet("Your trail ran out of time (no news for 30 minutes)."); return; }
        const a = data.active;
        if (!a || journeyActive()) return;
        trail = { checkpoints: a.checkpoints, index: a.index, start: a.start, shape: a.shape, legFrom: null };
        trailActive = true;
        if (routeLine) { routeLine.remove(); routeLine = null; }
        routeInfo.hidden = true;
        newRouteBtn.hidden = true;
        trailBtn.hidden = true;
        trailEnd.hidden = false;
        trailToggle.hidden = false;
        const cp = trail.checkpoints[trail.index];
        startJourney({ kind: "trail", id: null, name: cp.name, lat: cp.lat, lon: cp.lon },
                     { meters: a.meters, elapsedMs: (a.elapsed_s + a.since_update_s) * 1000 });
        Object.assign(journey, { checkpoint: trail.index + 1, checkpoints: trail.checkpoints.length, splits: a.splits });
        renderJourney();
        journeyNote(`Welcome back! Carrying on your trail: checkpoint ${trail.index + 1} of ${trail.checkpoints.length}.`);
        if (currentPos) drawTrailLeg(true);  // otherwise the first GPS fix draws it
      } catch (err) {
        console.error("Could not check for a trail to carry on:", err);
      }
    }

    // Back at the start: stop the clock and let Python check and save the walk.
    async function finishTrailWalk(lat, lon) {
      const walked = trail;
      const timed = journey.kind === "trail" && journeyActive();
      endTrail(walked.shape === "oneway" ? "Trail complete: you reached the last treasure"
                                         : "Trail complete: you walked the whole loop");
      if (!timed) return;  // the trail was walked without the panel: nothing to save
      const body = {
        distance_m: Math.round(journey.meters), duration_s: Math.max(1, Math.round(journey.elapsedMs / 1000)),
        lat, lon, shape: walked.shape, splits: journey.splits,
        end: [walked.checkpoints.at(-1).lat, walked.checkpoints.at(-1).lon],  // where the trail finishes
        checkpoints: walked.checkpoints.filter(cp => cp.id).length,         // the treasures (not "back to the start")
        treasure_ids: walked.checkpoints.filter(cp => cp.id).map(cp => cp.id)  // which trail: for personal bests
      };
      let text = "Could not save this trail.", ok = false;
      try {
        const res = await fetch("/api/trail/walks", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
        });
        const data = await res.json();
        ok = res.ok;
        text = ok ? "Trail saved and posted." : (data.error || text);
        // B: personal best on this same trail (Python compares the times)
        if (ok && data.best && data.best.personal_best && !data.best.first_time) {
          text = `New personal best: ${fmtTime(data.best.faster_by_s * 1000)} faster! ` + text;
        }
        if (ok) startCooldown();  // B: the cool-down quest after a trail too
      } catch (err) {
        queueForLater("/api/trail/walks", body);  // A's outbox: sent when you are back online
        text = "No connection: this trail will be saved as soon as you are back online.";
      }
      jSaved.textContent = text;
      jSaved.classList.toggle("is-bad", !ok);
      if (ok) {
        const link = document.createElement("a");
        link.href = "/trails";  // B: your trail history and personal bests
        link.textContent = " See My trails";
        jSaved.append(link);
      }
      jSaved.hidden = false;
    }

