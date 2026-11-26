    // map.html part (owner: B; A's additions are marked A:): coins for a find, and rating a treasure.
    // Included into map.html's one <script> when the page is built, so every part shares the same
    // variables, in this order. No Jinja tags in here (they would be run by Flask).
    // ------------------------------------------------------------ coins

    // Python decides whether you really are within 20 m and pays the coins
    // (/api/treasures/<id>/claim). We only say where we are, and ask once per treasure.
    const coinInfo = document.getElementById("coinInfo");
    const triedClaim = new Set();  // treasure ids we already asked about
    const claimNotes = new Map();  // treasure id -> why it paid no coins (shown next to "You found")

    function foundText(name, treasureId) {
      const note = claimNotes.get(treasureId);
      return `You found ${name}` + (note ? ` · ${note}` : "");
    }

    function showBalance(balance, earned) {
      coinInfo.textContent = `${balance} coins` + (earned ? `  (+${earned})` : "");
      coinInfo.hidden = false;
    }

    async function loadBalance() {
      try {
        const res = await fetch("/api/coins");
        if (res.ok) showBalance((await res.json()).balance);
      } catch (err) {
        console.error("Coin balance failed:", err);
      }
    }
    loadBalance();

    // ------------------------------------------------------------ rating (B)

    const rateBox = document.getElementById("rateBox");
    const rateMsg = document.getElementById("rateMsg");
    const rateStars = [...rateBox.querySelectorAll(".rate-star")];
    let rateId = null;

    function paintStars(n) {
      rateStars.forEach((b, i) => b.classList.toggle("is-on", i < n));
    }

    function showRateBox(treasureId, name) {
      rateId = treasureId;
      document.getElementById("rateName").textContent = name;
      const mine = ratingsById.get(treasureId)?.mine;
      paintStars(mine || 0);
      rateMsg.textContent = mine ? `You gave it ${mine} ★. Tap to change.` : "Tap a star.";
      rateBox.hidden = false;
    }

    rateStars.forEach((button) => {
      button.addEventListener("mouseenter", () => paintStars(Number(button.dataset.stars)));
      button.addEventListener("mouseleave", () => paintStars(ratingsById.get(rateId)?.mine || 0));
      button.addEventListener("click", async () => {
        if (rateId === null) return;
        const stars = Number(button.dataset.stars);
        rateMsg.textContent = "Saving…";
        try {
          const res = await fetch(`/api/treasures/${rateId}/rating`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ stars })
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || "Could not save your rating");
          ratingsById.set(rateId, { rating: { average: data.average, count: data.count }, mine: data.mine });
          paintStars(data.mine);
          rateMsg.textContent = `Thanks! ${starsText(data)}`;
          if (selectedTreasure && selectedTreasure.id === rateId) showBoardStars(rateId);
        } catch (err) {
          rateMsg.textContent = err.message;
        }
      });
    });

    // A: arrived at a treasure with a collectible you don't have yet: the celebration
    // (templates/_celebrate.html) collects it and asks camera or skip. Python checks the 20 m.
    function maybeCelebrate(treasureId, name, lat, lon) {
      const info = infoById.get(treasureId);
      if (!info || !info.collectible || info.collected || !window.celebrateCollectible) return;
      info.collected = true;  // ask once, even if this runs again on the next GPS update
      window.celebrateCollectible(treasureId, name, lat, lon)
        .then(isNew => { if (!isNew) info.collected = false; })
        .catch(err => { info.collected = false; console.error("Collectible failed:", err); });
    }

    async function claimCoins(treasureId, name, lat, lon) {
      if (triedClaim.has(treasureId)) return;
      triedClaim.add(treasureId);
      try {
        const res = await fetch(`/api/treasures/${treasureId}/claim`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat, lon })
        });
        const data = await res.json();
        if (res.ok) {
          claimNotes.delete(treasureId);
          showBalance(data.balance, data.coins_earned);
          for (const chain of data.chains_completed || []) {  // B: this find finished a riddle chain
            coinInfo.textContent += ` · riddle chain "${chain.title}" solved: +${chain.bonus}`;
          }
          collectPin(treasureId);
          showRateBox(treasureId, name);
          maybeCelebrate(treasureId, name, lat, lon);
        } else {
          if (res.status === 409) {  // you had already found it
            collectPin(treasureId);
            showRateBox(treasureId, name);
            maybeCelebrate(treasureId, name, lat, lon);  // a collectible added after your first visit
          }
          // Refused: say why (you hid it yourself, you already found it, ...) instead of staying silent.
          claimNotes.set(treasureId, data.error || "No coins this time.");
          if (res.status === 400) triedClaim.delete(treasureId);  // e.g. too far: allow another try
        }
        if (treasureId === huntId) statusBox.textContent = foundText(name, treasureId);
      } catch (err) {
        triedClaim.delete(treasureId);  // network problem: try again on the next update
        console.error("Claim failed:", err);
      }
    }

