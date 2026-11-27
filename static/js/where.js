// B: where the player is, for the new ways to play (wanderer, ghost, team, travelers, eyes-free).
// Normally the phone's GPS. Add ?drag to the address for an indoor demo: no GPS, and the page
// moves a pretend position instead (tap the map, or use the page's step buttons).
// It only reports a position: Python decides what it means.
(function () {
  const pretend = new URLSearchParams(location.search).has("drag");
  let here = null, listeners = [], watching = null;
  const M_PER_DEG = 111320;

  function tell() { for (const fn of listeners) fn(here); }

  window.Where = {
    pretend,
    current: () => here,
    onChange(fn) { listeners.push(fn); if (here) fn(here); },
    set(lat, lon) { here = { lat, lon, accuracy: 0 }; tell(); },
    // Pretend mode: move `metres` towards (or away from, if negative) a point.
    step(toLat, toLon, metres) {
      if (!here) return;
      const north = (toLat - here.lat) * M_PER_DEG;
      const east = (toLon - here.lon) * M_PER_DEG * Math.cos(here.lat * Math.PI / 180);
      const dist = Math.hypot(north, east);
      if (dist < 0.5) return;
      const share = Math.min(1, metres / dist);
      this.set(here.lat + (toLat - here.lat) * share, here.lon + (toLon - here.lon) * share);
    },
    start(onProblem) {
      if (pretend || watching !== null) return;
      if (!navigator.geolocation) { onProblem && onProblem("This browser has no GPS. Add ?drag to the address to pretend."); return; }
      watching = navigator.geolocation.watchPosition(
        pos => { here = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy }; tell(); },
        err => onProblem && onProblem(err.code === 1
          ? "Location is blocked. Allow it in the browser settings (or add ?drag to the address to pretend)."
          : "Looking for GPS… Go outside if it takes long."),
        { enableHighAccuracy: true, maximumAge: 3000, timeout: 20000 });
    },
  };
})();
