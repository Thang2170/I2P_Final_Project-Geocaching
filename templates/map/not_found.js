    // ------------------------------------------------------------ B: "I couldn't find it"
    // A player who looked at the spot and found nothing says so. After 3 different players,
    // Python marks the treasure "maybe missing" and tells its owner (dnf.py). The next find clears it.
    // Rain and night treasures (conditions.py) get a line too. Python writes every sentence.

    const boardAppears = document.getElementById("boardAppears");
    const boardMissing = document.getElementById("boardMissing");
    const dnfBtn = document.getElementById("dnfBtn");
    const dnfNote = document.getElementById("dnfNote");

    function markMissingPin(id) {
      const info = infoById.get(id) || {};
      const missing = Boolean(info.notFound && info.notFound.missing);
      markersById.get(id)?.getElement()?.classList.toggle("pin--missing", missing);
    }

    function showBoardReports(id) {
      const info = infoById.get(id) || {};
      boardAppears.hidden = !info.appears;
      boardAppears.textContent = info.appears ? info.appears.text : "";
      const text = info.notFound ? info.notFound.text : "";
      boardMissing.hidden = !text;
      boardMissing.textContent = text;
      boardMissing.classList.toggle("is-missing", Boolean(info.notFound && info.notFound.missing));
      dnfNote.hidden = true;
      dnfNote.textContent = "";
      dnfBtn.disabled = false;
    }

    dnfBtn.addEventListener("click", async () => {
      if (!selectedTreasure) return;
      if (!currentPos) {
        dnfNote.hidden = false;
        dnfNote.textContent = "Waiting for your location: walk to the spot first.";
        return;
      }
      const id = selectedTreasure.id;
      dnfBtn.disabled = true;
      try {
        const res = await fetch(`/api/treasures/${id}/not-found`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat: currentPos[0], lon: currentPos[1] })
        });
        const data = await res.json();
        dnfNote.hidden = false;
        if (!res.ok) {
          dnfNote.textContent = data.error || "Could not save that.";
          dnfBtn.disabled = data.problem === "already";
          return;
        }
        const info = infoById.get(id) || {};
        info.notFound = { count: data.count, missing: data.missing, text: data.text };
        infoById.set(id, info);
        showBoardReports(id);
        dnfNote.hidden = false;
        dnfNote.textContent = data.thanks;
        dnfBtn.disabled = true;
        markMissingPin(id);
      } catch (err) {
        dnfNote.hidden = false;
        dnfNote.textContent = "No connection: try again in a moment.";
        dnfBtn.disabled = false;
      }
    });
