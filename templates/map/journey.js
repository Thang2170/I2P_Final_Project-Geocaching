    // map.html part (owner: A; B's additions are marked B:): the journey panel (live stats, like a run tracker).
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ journey (live stats, like a run tracker)

    // Start: tap a treasure, then "Start journey". The panel shows time, pace and distance
    // while you walk. Steps and calories come from Python (/api/walk-stats), and so does
    // "you found it" (/api/distance): the browser only keeps the clock and adds up your steps.
    const MIN_STEP_M = 3;       // moves smaller than this are GPS wobble while standing still
    const MAX_SPEED_MS = 12;    // faster than this (m/s) is a GPS jump, not walking
    const STATS_EVERY_MS = 5000;   // B: the live update while you move...
    const LIVE_STILL_MS = 10000;   // ...and while you stand still (the safety check needs it this often)

    const journeyBox = document.getElementById("journey");
    const startBtn = document.getElementById("startBtn");
    const jPause = document.getElementById("jPause");
    const jFinish = document.getElementById("jFinish");
    const jNote = document.getElementById("jNote");
    const jSaved = document.getElementById("jSaved");
    const jEls = {
      time: document.getElementById("jTime"), pace: document.getElementById("jPace"),
      dist: document.getElementById("jDist"), steps: document.getElementById("jSteps"),
      cal: document.getElementById("jCal"), to: document.getElementById("jTo"),
      msg: document.getElementById("jMsg"), title: document.getElementById("jTitle")
    };

    // state: "idle" | "running" | "paused" | "finished"
    const journey = { state: "idle" };
    let journeyTimer = null;
    let wakeLock = null;
    let noteTimer = null;

    function journeyActive() { return journey.state === "running" || journey.state === "paused"; }

    function fmtTime(ms) {
      const total = Math.floor(ms / 1000);
      const h = Math.floor(total / 3600), m = Math.floor(total % 3600 / 60), s = total % 60;
      const two = n => String(n).padStart(2, "0");
      return h > 0 ? `${h}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
    }

    // Average pace as minutes:seconds per km. Not shown until you have walked 20 m.
    function fmtPace(ms, meters) {
      if (meters < 20) return "--:--";
      const perKm = Math.round((ms / 1000) / (meters / 1000));
      if (!isFinite(perKm) || perKm >= 6000) return "--:--";
      return `${Math.floor(perKm / 60)}:${String(perKm % 60).padStart(2, "0")}`;
    }

    function fmtAway(meters) {
      return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${Math.round(meters)} m`;
    }

    function updateStartButton() {
      if (journeyActive()) {
        startBtn.disabled = true;
        startBtn.textContent = "Journey in progress";
      } else {
        startBtn.disabled = !currentPos || !selectedTreasure;
        startBtn.textContent = currentPos ? "Start journey" : "Waiting for your location…";
      }
    }

    function journeyNote(text) {
      jNote.textContent = text;
      jNote.hidden = false;
      clearTimeout(noteTimer);
      noteTimer = setTimeout(() => { jNote.hidden = true; }, 4000);
    }

    function renderJourney() {
      jEls.time.textContent = fmtTime(journey.elapsedMs);
      jEls.pace.parentElement.hidden = walkMode === "calm";  // B: no clock pressure on a calm walk
      jEls.pace.textContent = fmtPace(journey.elapsedMs, journey.meters);
      jEls.dist.textContent = (journey.meters / 1000).toFixed(2);
      jEls.steps.textContent = journey.steps.toLocaleString();
      jEls.cal.textContent = journey.calories;
      jEls.to.textContent = currentPos ? fmtAway(map.distance(currentPos, journey.target)) : "–";
      jEls.to.nextElementSibling.textContent = journey.kind === "trail" ? "To checkpoint" : "To treasure";  // B
      jPause.hidden = journey.state === "finished";
      jPause.textContent = journey.state === "paused" ? "Resume" : "Pause";
      jFinish.textContent = journey.state === "finished" ? "Close" : "Finish";
      if (journey.kind === "trail") {  // B: a Treasure Trail walked with the panel
        jEls.title.textContent = journey.state === "finished" ? "Treasure Trail: done"
          : `Trail · ${journey.checkpoint} of ${journey.checkpoints}: ${journey.name}` + (journey.state === "paused" ? " (paused)" : "");
        return;
      }
      jEls.title.textContent = journey.state === "finished"
        ? `Journey to ${journey.name}: done`
        : `Journey to ${journey.name}` + (journey.state === "paused" ? " (paused)" : "");
    }

    // Called with every new position (from showPosition). Adds to your distance while running.
    function journeyPoint(lat, lon) {
      if (journey.state !== "running") return;
      const now = Date.now();
      if (journey.last) {
        const moved = map.distance(journey.last.pos, [lat, lon]);
        const seconds = (now - journey.last.time) / 1000;
        if (moved < MIN_STEP_M) return;  // keep the old anchor so slow walking still adds up
        const jump = !dragMode && seconds > 0 && moved / seconds > MAX_SPEED_MS;
        if (!jump) journey.meters += moved;  // a jump re-anchors without counting
      }
      journey.last = { pos: [lat, lon], time: now };
    }

    // B: ONE live update while you walk (/api/journey/live): steps and calories (from your speed, or
    // your band's heart rate if it's on: energy.py), the heart-rate zone, the safety check and the
    // try-hard pace. Python works all of it out; this only shows it.
    let journeyStatsId = 0;
    async function loadJourneyStats() {
      const requestId = ++journeyStatsId;
      journey.statsAt = Date.now();
      journey.statsMeters = journey.meters;
      const running = journey.state === "running";
      try {
        const seconds = Math.max(1, Math.round(journey.elapsedMs / 1000));
        const res = await fetch(`/api/journey/live?distance_m=${Math.round(journey.meters)}&duration_s=${seconds}`);
        const data = await res.json();
        if (requestId !== journeyStatsId || !res.ok) return;
        journey.steps = data.stats.steps;
        journey.calories = data.stats.calories;
        document.getElementById("jCalFrom").textContent = data.stats.source_text || "";
        renderJourney();
        if (!running) return;  // finished or paused: just the final numbers
        if (data.zone) showZone(data.zone);
        if (data.mode) showModeLine(data.mode);
        if (data.safety) showSafety(data.safety);
      } catch (err) {
        console.error("Live update failed:", err);  // no connection: the clock keeps counting
      }
    }

