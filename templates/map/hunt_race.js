    // map.html part (owner: A): hunt race mode.
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ hunt race (A)

    // Opened from "Go to the hunt": the map aims at the hunt's treasure (the ?treasure= part does that)
    // and, once Python says you're there, tells the server. Python decides who won (hunt_game.py).
    const raceHuntId = Number(params.get("hunt")) || null;
    const raceTreasureId = Number(params.get("treasure")) || null;
    const huntInfo = document.getElementById("huntInfo");
    let raceOver = false;
    let arrivalSent = false;

    function showRace(data) {
      const name = data.name ? `"${data.name}"` : "This hunt";
      if (data.won) {
        huntInfo.textContent = `You won ${name}! +${data.bonus} coins`;
      } else if (data.state === "finished") {
        huntInfo.textContent = `${name} is over · winner: ${data.winner}`;
      } else if (data.state === "started") {
        huntInfo.textContent = data.error || `Hunt race ${name}: be the first to reach ${data.treasure.name}`;
      } else {
        huntInfo.textContent = `${name} hasn't started yet`;
      }
      raceOver = data.state === "finished";
      huntInfo.hidden = false;
    }

    async function loadRace() {
      if (!raceHuntId || raceOver) return;
      try {
        const res = await fetch(`/api/hunts/${raceHuntId}/game`);
        const data = await res.json();
        if (res.ok) showRace(data);
      } catch (err) {
        console.error("Hunt race failed:", err);
      }
    }

    async function reportArrival(lat, lon) {
      if (!raceHuntId || raceOver || arrivalSent) return;
      arrivalSent = true;  // ask once; a refusal while the race is still on lets you try again
      try {
        const res = await fetch(`/api/hunts/${raceHuntId}/arrived`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat, lon })
        });
        const data = await res.json();
        showRace(data);
        if (data.won) showBalance(data.balance, data.bonus);
        if (!res.ok && data.state === "started") arrivalSent = false;
      } catch (err) {
        arrivalSent = false;
        console.error("Hunt arrival failed:", err);
      }
    }

    // A: the other players in this hunt, as little explorers with their names.
    // Python decides who you may see (only your own hunt, only the last 2 minutes).
    const teamInfo = document.getElementById("teamInfo");
    const teammates = L.layerGroup().addTo(map);
    const teammateIcon = L.divIcon({
      className: "admin-player",
      html: '<span class="sprite sprite--explorer"></span>',
      iconSize: [48, 48],
      iconAnchor: [24, 46]
    });
    if (raceHuntId) map.createPane("teammates").style.zIndex = 650;  // above the treasure chests

    async function loadTeammates() {
      try {
        const res = await fetch(`/api/hunts/${raceHuntId}/players`);
        if (!res.ok) return;  // not playing in this hunt: nothing to show
        const data = await res.json();
        teammates.clearLayers();
        for (const p of data.players) {
          L.marker([p.lat, p.lon], { icon: teammateIcon, pane: "teammates", interactive: false })
            .bindTooltip(`${p.name} · ${p.seconds_ago}s ago`, { permanent: true, direction: "top", offset: [0, -44] })
            .addTo(teammates);
        }
        const n = data.players.length;
        teamInfo.textContent = n ? `${n} teammate${n === 1 ? "" : "s"} on the map` : "No teammates on the map right now";
        teamInfo.hidden = false;
      } catch (err) {
        console.error("Teammates failed:", err);
      }
    }

    if (raceHuntId) {
      loadRace();
      setInterval(loadRace, 10000);  // someone else may win while you walk
      loadTeammates();
      setInterval(loadTeammates, 10000);  // the same pace as positions are sent
    }

