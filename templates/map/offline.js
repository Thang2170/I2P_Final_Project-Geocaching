    // map.html part (owner: A): lost connection: the outbox and saving later.
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ lost connection (A)

    // The server remembers your journey with a deadline that fits the walk (journey_resume.py),
    // so you can carry on after losing signal or reloading. Anything that must reach the server
    // while you are offline waits in an "outbox" on the phone and is sent when you are back.
    const PROGRESS_EVERY_MS = 30000;
    const OFFLINE_FOUND_M = 20;  // same as FOUND_RADIUS_M in location.py; Python checks again later
    const OUTBOX_KEY = "stepquest.outbox";
    const netInfo = document.getElementById("netInfo");

    function showNet(text) {
      netInfo.textContent = text;
      netInfo.hidden = !text;
    }

    function readOutbox() {
      try { return JSON.parse(localStorage.getItem(OUTBOX_KEY)) || []; } catch (err) { return []; }
    }
    function writeOutbox(list) {
      try { localStorage.setItem(OUTBOX_KEY, JSON.stringify(list)); } catch (err) { /* private mode */ }
    }
    function queueForLater(url, body, method = "POST") {
      const list = readOutbox();
      list.push({ url, body, method });
      writeOutbox(list);
      showNet(`No connection. ${list.length} thing(s) will be sent when you are back online.`);
    }

    // Send what waited. Any answer from the server (even "no") means it arrived; only a
    // network error or a server crash (5xx) keeps it for the next try.
    let flushing = false;
    async function flushOutbox() {
      const list = readOutbox();
      if (flushing || !list.length) return;
      flushing = true;
      const keep = [];
      const refused = [];  // the server answered "no" (too far, too fast, ...): say so, don't hide it
      for (const item of list) {
        try {
          const res = await fetch(item.url, {
            method: item.method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(item.body)
          });
          if (res.status >= 500) keep.push(item);
          else if (!res.ok) refused.push((await res.json().catch(() => ({}))).error || `refused (${res.status})`);
        } catch (err) {
          keep.push(item);
        }
      }
      writeOutbox(keep);
      flushing = false;
      if (keep.length < list.length) {
        if (keep.length) showNet(`Sent ${list.length - keep.length}, ${keep.length} still waiting.`);
        else if (refused.length) showNet(`Back online. Not saved: ${refused.join(" ")}`);
        else showNet("Back online: everything you did offline is saved.");
        loadBalance();
        if (!keep.length && !refused.length) setTimeout(() => showNet(""), 6000);
      }
    }
    window.addEventListener("online", flushOutbox);
    window.addEventListener("offline", () => showNet("No connection. Your journey keeps counting."));
    setInterval(flushOutbox, 30000);

    async function tellServerJourneyStarted(t) {
      if (!currentPos) return;
      try {
        const res = await fetch("/api/journeys/active", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ treasure_id: t.id, lat: currentPos[0], lon: currentPos[1] })
        });
        const data = await res.json();
        if (res.ok) journeyNote(`If you lose signal you can carry on for ${Math.round(data.window_s / 60)} min.`);
      } catch (err) {
        console.error("Could not tell the server about the journey:", err);  // it still runs here
      }
    }

    async function sendProgress() {
      journey.progressAt = Date.now();
      try {
        await fetch("/api/journeys/active/progress", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ meters: Math.round(journey.meters), elapsed_s: Math.round(journey.elapsedMs / 1000) })
        });
      } catch (err) { /* offline: the next try in 30 s */ }
    }

    function endServerJourney() {
      fetch("/api/journeys/active", { method: "DELETE" })
        .catch(() => queueForLater("/api/journeys/active", {}, "DELETE"));
    }

    // After a reload (or the browser closed the page while you had no signal):
    // carry on the journey the server remembers, with its distance and clock.
    async function resumeJourney() {
      if (journeyActive()) return;
      try {
        const res = await fetch("/api/journeys/active");
        if (!res.ok) return;
        const data = await res.json();
        if (data.expired) {
          showNet(`Your journey to ${data.expired.treasure} ran out of time.`);
          return;
        }
        const a = data.active;
        if (!a || !a.treasure || !markersById.has(a.treasure.id)) return;
        selectTreasure(a.treasure, markersById.get(a.treasure.id));
        startJourney(a.treasure, { meters: a.meters, elapsedMs: (a.elapsed_s + a.since_update_s) * 1000 });
        journeyNote(`Welcome back! Carrying on to ${a.treasure.name} (${Math.round(a.seconds_left / 60)} min left).`);
      } catch (err) {
        console.error("Could not check for a journey to carry on:", err);
      }
    }

    // No signal but GPS still works: if you are at the treasure, count it now. Python
    // checks the position again when the saved actions arrive.
    function arrivedWhileOffline() {
      if (!journeyActive() || !currentPos || journey.kind === "trail") return;
      if (map.distance(currentPos, journey.target) > OFFLINE_FOUND_M) return;
      const [lat, lon] = currentPos;
      queueForLater(`/api/treasures/${journey.targetId}/claim`, { lat, lon });
      if (raceHuntId && journey.targetId === raceTreasureId) queueForLater(`/api/hunts/${raceHuntId}/arrived`, { lat, lon });
      finishJourney(true);  // saveJourney queues itself when the network fails
      statusBox.textContent = `You reached ${journey.name} with no signal. Coins and saving happen when you are back online.`;
    }
    flushOutbox();

