// "Which supply zone am I in?": the reader's position, tested in the browser against
// the boundaries the build tests pins against. The position is never sent anywhere.
(function () {
  const button = document.getElementById("where");
  const out = document.getElementById("whereOut");
  if (!button || !out || !navigator.geolocation) return;
  button.hidden = false;
  window.UISCE_ZONES = window.UISCE_ZONES || {};
  // the build's stamp, as cacheBust gives the other shards: a re-fetch can rename a zone
  const bust = location.protocol === "file:" ? "" : "?v=" + encodeURIComponent(button.dataset.v);
  const pending = {};

  // an injected <script> rather than fetch: the site has to work opened off disk
  function load(src, ready) {
    if (ready()) return Promise.resolve();
    if (!pending[src]) {
      pending[src] = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = src + bust;
        s.onload = () => (ready() ? resolve() : reject());
        s.onerror = reject;
        document.head.appendChild(s);
      }).catch(e => {
        delete pending[src];
        throw e;
      });
    }
    return pending[src];
  }

  // the build's _winding, line for line
  function winding(x, y, ring) {
    let n = 0;
    for (let k = 0; k < ring.length; k++) {
      const [x0, y0] = ring[k], [x1, y1] = ring[(k + 1) % ring.length];
      const side = (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0);
      if (y0 <= y && y < y1 && side > 0) n += 1;
      else if (y1 <= y && y < y0 && side < 0) n -= 1;
    }
    return n;
  }

  async function zoneAt(lat, lon) {
    await load("zs/index.js", () => window.UISCE_ZONE_CELLS);
    const { deg, cells } = window.UISCE_ZONE_CELLS;
    const key = `${Math.floor(lon / deg)}_${Math.floor(lat / deg)}`;
    if (!cells.includes(key)) return null;
    await load(`zs/${key}.js`, () => window.UISCE_ZONES[key]);
    // smallest zone first, as the build orders them
    return window.UISCE_ZONES[key].find(
      ([, , rings]) => rings.reduce((n, ring) => n + winding(lon, lat, ring), 0) !== 0
    ) || null;
  }

  function say(html) {
    out.innerHTML = html;
    out.hidden = false;
  }

  let asked = 0;
  button.addEventListener("click", () => {
    // only the latest press may answer: an earlier, coarser fix can land after it
    const ask = ++asked;
    let answered = false;
    const reply = html => {
      answered = true;
      if (ask === asked) say(html);
    };
    say("Finding where you are…");
    // the timeout below only starts once the reader answers the browser's prompt
    setTimeout(() => {
      if (!answered && ask === asked) say("No answer from your browser yet. Allow location for this site, or search a town instead.");
    }, 20000);
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        let zone;
        try {
          zone = await zoneAt(coords.latitude, coords.longitude);
        } catch (e) {
          reply("The zone boundaries did not load. Try again.");
          return;
        }
        // a desktop browser often places itself by network, kilometres out
        const rough = coords.accuracy > 500
          ? ` Your browser placed you to within about ${Math.round(coords.accuracy / 1000) || 1} km, so the zone may be a neighbour of yours.`
          : "";
        reply(!zone
          ? `Where you are is outside every Uisce Éireann supply zone. About one person in five is on a group or private scheme instead, which no zone covers.${rough}`
          : zone[1]
            ? `Your supply zone is <a href="${zone[1]}">${esc(zone[0])}</a>.${rough}`
            : `Where you are is in a supply zone this site has no page for yet.${rough}`);
      },
      err => reply(err.code === err.PERMISSION_DENIED
        ? "Your location was not shared. Search a town instead."
        : "Your browser could not find where you are. Search a town instead."),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 300000 }
    );
  });

  function esc(s) {
    return s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
})();
