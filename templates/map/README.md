# The map page's script, in parts (B)

`templates/map.html` has one `<script>`. To keep it easy to work on (and to stop A, B and C
editing the same 1,900-line file at once), its code lives in these files. `map.html` pulls them
in with `{% include "map/....js" %}` when Flask builds the page, so the browser still gets ONE
script, exactly as before: every part shares the same variables, in this order.

| File | What | Owner |
|---|---|---|
| `map_view.js` | the map, treasure pins, the info board, walking routes | A |
| `trail.js` | the compact status card and Treasure Trails | B |
| `journey.js` | the journey panel (live stats, like a run tracker) | A |
| `journey_coach.js` | walking modes, safety alerts, heart-rate zone, cool-down | B |
| `hunt_race.js` | hunt race mode | A |
| `crossings.js` | street crossings | A |
| `offline.js` | lost connection: the outbox | A |
| `coins_rating.js` | coins for a find, rating a treasure | B |
| `position.js` | GPS, drag mode, fake positions | A |
| `not_found.js` | "I couldn't find it" reports, maybe-missing pins, rain and night treasures | B |

Rules:
- No Jinja tags (`{{`, `{%`, `{#`) in these files: Flask would run them. Values from Python go in
  `map.html` itself (like `const treasure = {{ treasure | tojson }};`).
- The order of the includes matters: a part may only use, at load time, what earlier parts made.
- Why not separate `<script src>` files? The map fetches treasures as soon as it starts; with
  separate files that answer could arrive before a later file has loaded, and call a function that
  doesn't exist yet. Includes keep the page exactly as it was.
