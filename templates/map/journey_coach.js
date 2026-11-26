    // map.html part (owner: B; A's additions are marked A:): walking modes, safety alerts, heart-rate zone, cool-down quest.
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ B: walking modes (modes.py)

    // ------------------------------------------------------------ B: safety alerts (safety.py)

    // Checked at least every 10 s while you walk (part of the live update)
    const safetyBox = document.getElementById("safetyAlert");
    const jSafety = document.getElementById("jSafety");
    function showSafety(s) {
      jSafety.hidden = s.level !== "caution";
      jSafety.textContent = s.level === "caution" ? `${s.title}: ${s.text}` : "";
      if (s.level === "stop" && journeyActive()) safetyStop(s);
    }

    function safetyStop(s) {
      finishJourney(false);   // stop the clock; the hunt is not saved
      endServerJourney();     // nothing to carry on after a reload
      jSaved.textContent = "Hunt stopped for your safety.";
      jSaved.classList.add("is-bad");
      jSaved.hidden = false;
      document.getElementById("safetyTitle").textContent = s.title;
      document.getElementById("safetyText").textContent = s.text;
      document.getElementById("safetyAdvice").replaceChildren(...s.advice.map(line => {
        const li = document.createElement("li");
        li.textContent = line;
        return li;
      }));
      safetyBox.hidden = false;
      document.getElementById("safetyOk").focus();
      if (navigator.vibrate) navigator.vibrate([400, 150, 400]);
    }

    document.getElementById("safetyOk").addEventListener("click", () => { safetyBox.hidden = true; });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !safetyBox.hidden) safetyBox.hidden = true;
    });

    let walkMode = "normal";
    const calmById = new Map();  // treasure id -> {kind, where, prompt}, from /api/calm-spots
    const modePicker = document.getElementById("modePicker");
    const modeText = document.getElementById("modeText");

    function showMode(data) {
      walkMode = data.mode;
      modePicker.hidden = false;
      for (const b of modePicker.querySelectorAll(".mode-pick")) {
        b.classList.toggle("is-on", b.dataset.mode === walkMode);
        b.setAttribute("aria-pressed", b.dataset.mode === walkMode ? "true" : "false");
      }
      modeText.textContent = walkMode === "normal" ? "" : data.text;
      modeText.hidden = walkMode === "normal";
      applyMode();
    }

    async function loadMode() {
      try {
        const [mode, calm] = await Promise.all([fetch("/api/mode"), fetch("/api/calm-spots")]);
        if (calm.ok) for (const s of (await calm.json()).spots) calmById.set(s.id, s);
        if (mode.ok) showMode(await mode.json());  // logged out: no picker
      } catch (err) {
        console.error("Mode failed:", err);
      }
    }

    modePicker.addEventListener("click", async event => {
      const pick = event.target.closest(".mode-pick");
      if (!pick || pick.dataset.mode === walkMode) return;
      if (journeyActive()) { journeyNote("Finish this journey before you change mode."); return; }
      try {
        const res = await fetch("/api/mode", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: pick.dataset.mode })
        });
        if (res.ok) showMode(await res.json());
      } catch (err) {
        console.error("Mode change failed:", err);
      }
    });

    // Calm walk: calm spots glow green, the others fade a little.
    function applyMode() {
      for (const [id, marker] of markersById) {
        const pin = marker.getElement();
        if (!pin) continue;
        pin.classList.toggle("pin--calm", walkMode === "calm" && calmById.has(id));
        pin.classList.toggle("pin--dim", walkMode === "calm" && !calmById.has(id));
      }
      if (selectedTreasure) showBoardCalm(selectedTreasure.id);
    }

    function showBoardCalm(treasureId) {
      const line = document.getElementById("boardCalm");
      const spot = calmById.get(treasureId);
      line.hidden = walkMode !== "calm";
      line.textContent = !spot ? "Not a calm spot. Green pins are parks, water and quiet places."
        : `Mindful moment, ${spot.where}: ${spot.prompt}`;
    }

    // During a journey: try-hard shows your pace against the target (Python decides), calm a reminder.
    const jModeLine = document.getElementById("jModeLine");
    function showModeLine(m) {
      jModeLine.hidden = !m.text;
      jModeLine.dataset.mode = m.mode;
      jModeLine.textContent = m.text;
      jModeLine.classList.toggle("is-slow", m.on_pace === false);
    }
    loadMode();

    // B: your heart-rate zone now (Python works it out from the band: zone_coach.py)
    const jZone = document.getElementById("jZone"), jZoneWarn = document.getElementById("jZoneWarn");
    function showZone(z) {
      {
        jZone.hidden = !z.has_band;
        jZoneWarn.hidden = !z.warning;
        jZoneWarn.textContent = z.warning || "";
        if (!z.has_band) return;
        const name = document.getElementById("jZoneName");
        name.textContent = z.zone_name;
        name.dataset.zone = z.zone;
        const mins = Math.floor(z.bonus_seconds / 60);
        document.getElementById("jZoneText").textContent =
          `${z.hr} bpm (${z.percent}% of max) · ${mins} min in the 60–80% zone` +
          (z.bonus_coins ? ` · +${z.bonus_coins} bonus coins` : "") +
          (z.in_bonus_zone ? " · in the zone" : "");
      }
    }

    // B: the cool-down quest: after a saved hunt, walk gently for 3 min (checked every 15 s)
    const jCool = document.getElementById("jCool");
    let coolTimer = null;
    function stopCooldown() { clearInterval(coolTimer); coolTimer = null; }
    async function checkCooldown() {
      try {
        const res = await fetch("/api/zone/cooldown", { method: "POST" });
        if (!res.ok) return stopCooldown();
        const c = await res.json();
        const text = document.getElementById("jCoolText");
        document.getElementById("jCoolFill").style.width = `${Math.round(100 * c.done_s / c.goal_s)}%`;
        jCool.hidden = false;
        if (c.state === "done") {
          text.textContent = c.paid ? `Done! +${c.paid} coins. Well cooled down.` : "Done for this hunt.";
          return stopCooldown();
        }
        if (c.state === "missed") {
          text.textContent = "Missed this time: the cool-down must be within 20 minutes of finishing.";
          return stopCooldown();
        }
        if (c.state === "no_band") {
          text.textContent = `Wear your band, then walk gently for 3 min under ${c.below_bpm} bpm for +${c.reward} coins.`;
          return;
        }
        const left = c.goal_s - c.done_s;
        text.textContent = `Walk gently under ${c.below_bpm} bpm: ` +
          `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} to go for +${c.reward} coins.`;
      } catch (err) {
        console.error("Cool-down failed:", err);
      }
    }
    function startCooldown() {
      stopCooldown();
      checkCooldown();
      coolTimer = setInterval(checkCooldown, 15000);
    }

    function journeyTick() {
      const now = Date.now();
      if (journey.state === "running") journey.elapsedMs += now - journey.tickAt;
      journey.tickAt = now;
      if (journey.state === "running" && now - journey.progressAt >= PROGRESS_EVERY_MS) {
        if (journey.kind === "trail") keepTrail(); else sendProgress();  // B: trails are kept too
      }
      // B: the live update: every 5 s while you move, and at least every 10 s when you stand still
      // (calories grow with time, and the safety check must not wait longer than that)
      if (journey.state === "running" && now - journey.statsAt >= STATS_EVERY_MS
          && (journey.meters !== journey.statsMeters || now - journey.statsAt >= LIVE_STILL_MS)) loadJourneyStats();
      renderJourney();
    }

    async function keepScreenOn(on) {
      try {
        if (on && "wakeLock" in navigator && !wakeLock) wakeLock = await navigator.wakeLock.request("screen");
        else if (!on && wakeLock) { await wakeLock.release(); wakeLock = null; }
      } catch (err) {
        wakeLock = null;  // not allowed or not supported: the journey still works
      }
    }
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && journey.state === "running") keepScreenOn(true);
    });

    // restored = the numbers the server kept (resumeJourney), or null for a brand-new journey
    function startJourney(t, restored = null) {
      Object.assign(journey, {
        kind: t.kind || "treasure",  // B: "trail" for a Treasure Trail
        state: "running", targetId: t.id, name: t.name, target: [t.lat, t.lon],
        elapsedMs: restored ? restored.elapsedMs : 0, meters: restored ? restored.meters : 0,
        steps: 0, calories: 0, statsAt: 0, statsMeters: -1, saveStarted: false, progressAt: Date.now(),
        tickAt: Date.now(), last: currentPos ? { pos: currentPos, time: Date.now() } : null
      });
      if (!restored && journey.kind === "treasure") tellServerJourneyStarted(t);
      closeBoard();
      document.body.classList.add("is-journey");
      journeyBox.hidden = false;
      jEls.msg.textContent = statusBox.textContent;
      jSaved.hidden = true;
      clearInterval(journeyTimer);
      journeyTimer = setInterval(journeyTick, 1000);
      keepScreenOn(true);
      updateStartButton();
      renderJourney();
      loadJourneyStats();  // B: the zone, mode line and safety check from the start
      // Zoom so the whole route shows above the panel (the panel is now on screen to measure).
      const shown = journey.kind === "trail" ? trailLayer : routeLine;
      if (shown) map.fitBounds(shown.getBounds(), routePadding());
    }

    // Less / More: hide the extra numbers and messages, or show them again.
    const jFold = document.getElementById("jFold");
    jFold.addEventListener("click", () => {
      const folded = journeyBox.classList.toggle("is-folded");
      document.getElementById("jFoldLabel").textContent = folded ? "More" : "Less";  // A: the chevron flips in CSS
      jFold.setAttribute("aria-expanded", folded ? "false" : "true");
    });

    function pauseOrResume() {
      if (journey.state === "running") {
        journey.state = "paused";
      } else if (journey.state === "paused") {
        journey.state = "running";
        journey.tickAt = Date.now();
        journey.last = currentPos ? { pos: currentPos, time: Date.now() } : null;  // don't count the pause
      }
      renderJourney();
    }

    // arrived = Python said you are within 20 m of the treasure. Only then is the hunt saved
    // (the Finish button on its own just stops the clock).
    function finishJourney(arrived = false) {
      if (!journeyActive()) return;
      if (journey.kind === "trail") forgetTrail();  // B: a stopped or finished trail can't be carried on
      journey.state = "finished";
      clearInterval(journeyTimer);
      keepScreenOn(false);
      loadJourneyStats();
      updateStartButton();
      renderJourney();
      if (arrived) saveJourney();
    }

    // Save the finished hunt. Python checks it again (you must be within 20 m of the treasure,
    // and the speed must be a walk or a run) and works out the steps and calories itself.
    async function saveJourney() {
      if (journey.saveStarted || !currentPos) return;
      journey.saveStarted = true;
      const body = {
        treasure_id: journey.targetId, distance_m: Math.round(journey.meters),
        duration_s: Math.max(1, Math.round(journey.elapsedMs / 1000)),
        lat: currentPos[0], lon: currentPos[1]
      };
      let ok = false, answered = false, text = "Could not save this hunt.";
      try {
        const res = await fetch("/api/journeys", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
        });
        answered = true;  // saved or refused: either way this journey is over
        const data = await res.json();
        ok = res.ok;
        text = ok ? "Hunt saved." : (data.error || text);
        // B: coins for steady effort in the 60–80% heart-rate zone, then the cool-down quest
        if (ok && data.zone_bonus) text += ` +${data.zone_bonus} bonus coins for your heart-rate zone.`;
        if (ok && data.mode_bonus) text += ` ${data.mode_bonus.text}`;  // B: try-hard or calm walk
        if (ok) startCooldown();
      } catch (err) {
        // A: no connection: keep it and send it when the phone is back online
        queueForLater("/api/journeys", body);
        queueForLater("/api/journeys/active", {}, "DELETE");
        text = "No connection: this hunt will be saved as soon as you are back online.";
      }
      if (answered) endServerJourney();  // A: the server shouldn't offer to "carry on" a finished journey
      jSaved.textContent = text;
      jSaved.classList.toggle("is-bad", !ok);
      if (ok) {
        const link = document.createElement("a");
        link.href = "/community";
        link.textContent = " See the Community";
        jSaved.append(link);
      }
      jSaved.hidden = false;
    }

    function closeJourney() {
      journey.state = "idle";
      journeyBox.hidden = true;
      jSaved.hidden = true;
      jCool.hidden = true;  // B
      jZone.hidden = true;
      jZoneWarn.hidden = true;
      jModeLine.hidden = true;  // B
      jSafety.hidden = true;
      stopCooldown();
      document.body.classList.remove("is-journey");
      updateStartButton();
    }

    startBtn.addEventListener("click", () => {
      if (!journeyActive() && currentPos && selectedTreasure) startJourney(selectedTreasure);
    });
    jPause.addEventListener("click", pauseOrResume);
    jFinish.addEventListener("click", () => {
      if (journey.state === "finished") return closeJourney();
      finishJourney(false);
      endServerJourney();  // A: stopped on purpose: nothing to carry on
    });

    // The status card is hidden during a journey, so its messages ("123 m to Library",
    // "You found it", the coins you got) are copied into the panel.
    new MutationObserver(() => {
      if (journey.state !== "idle" && journey.kind !== "trail") jEls.msg.textContent = statusBox.textContent;
    })
      .observe(statusBox, { childList: true, characterData: true, subtree: true });

    // Python says you are within 20 m of the treasure (the status card turns gold): the journey is over.
    new MutationObserver(() => {
      if (sheet.classList.contains("is-found") && journeyActive() && journey.kind === "treasure"
          && huntId === journey.targetId) finishJourney(true);
    }).observe(sheet, { attributes: true, attributeFilter: ["class"] });

    // Closing the tab in the middle of a walk would lose it, so ask first.
    window.addEventListener("beforeunload", event => {
      if (journeyActive()) { event.preventDefault(); event.returnValue = ""; }
    });

