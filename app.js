(() => {
  // Platform badge colors and short labels. Order here = order of the chips.
  const PLATFORMS = {
    "NES":              { c: "#d42a3a", s: "NES" },
    "Game Boy":         { c: "#7c8a2e", s: "GB" },
    "SNES":             { c: "#6b4fbf", s: "SNES" },
    "Sega Genesis":     { c: "#2a2a2a", s: "GEN" },
    "Game Boy Color":   { c: "#13a39a", s: "GBC" },
    "PlayStation":      { c: "#6b7380", s: "PS1" },
    "Nintendo 64":      { c: "#1a8f3c", s: "N64" },
    "Sega Dreamcast":   { c: "#e8662a", s: "DC" },
    "Game Boy Advance": { c: "#4b3fa3", s: "GBA" },
    "PlayStation 2":    { c: "#1f3fa8", s: "PS2" },
    "GameCube":         { c: "#5b3fa0", s: "GCN" },
    "Xbox":             { c: "#3f8f2a", s: "XBOX" },
    "Nintendo DS":      { c: "#5c6878", s: "DS" },
    "PSP":              { c: "#333a48", s: "PSP" },
    "Xbox 360":         { c: "#5aa02c", s: "360" },
    "Wii":              { c: "#2f9ad6", s: "Wii" },
    "PlayStation 3":    { c: "#25292f", s: "PS3" },
    "Nintendo 3DS":     { c: "#c8102e", s: "3DS" },
    "PS Vita":          { c: "#1d4f9c", s: "VITA" },
    "Wii U":            { c: "#0f8fc4", s: "WiiU" },
    "PlayStation 4":    { c: "#003791", s: "PS4" },
    "Xbox One":         { c: "#107c10", s: "ONE" },
    "Switch":           { c: "#e60012", s: "NSW" },
    "PlayStation 5":    { c: "#2b5fd9", s: "PS5" },
    "Xbox Series X|S":  { c: "#0e7a0d", s: "XSX" },
    "Switch 2":         { c: "#e4002b", s: "NS2" },
  };
  const ORDER = Object.keys(PLATFORMS);
  const plat = (p) => PLATFORMS[p] || { c: "#555", s: p };

  const games = (window.GAMES || []).map((g) => ({
    ...g,
    year: g.release ? g.release.slice(0, 4) : null,
    hay: [g.name, g.sheetTitle, g.platform, ...(g.genres || []), ...(g.developer || []), ...(g.publisher || [])]
      .join(" ").toLowerCase(),
  }));

  const $ = (s) => document.querySelector(s);
  const lib = $("#library"), q = $("#q"), sortSel = $("#sort"), chips = $("#chips");
  const modal = $("#modal");
  const active = new Set();

  try { sortSel.value = localStorage.getItem("sort") || "oldest"; } catch {}

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (d, precision) => {
    if (!d) return "Release date unknown";
    if (precision === "year") return d.slice(0, 4);
    const opts = precision === "month" ? { year: "numeric", month: "long" }
      : { year: "numeric", month: "long", day: "numeric" };
    return new Date(d + "T12:00:00").toLocaleDateString(undefined, opts);
  };

  // ---------- header stats + chips ----------
  function renderStats() {
    const plats = new Set(games.map((g) => g.platform));
    const years = games.map((g) => g.year).filter(Boolean).sort();
    const span = years.length ? ` · ${years[0]}–${years[years.length - 1]}` : "";
    $("#stats").textContent = games.length
      ? `${games.length} games across ${plats.size} platform${plats.size === 1 ? "" : "s"}${span}`
      : "No games yet — run build_catalog.py to generate games.js";
  }

  function renderChips() {
    const counts = {};
    games.forEach((g) => (counts[g.platform] = (counts[g.platform] || 0) + 1));
    const list = Object.keys(counts).sort((a, b) => idx(a) - idx(b));
    const all = `<button class="chip" data-p="" aria-pressed="${active.size === 0}">All <small>${games.length}</small></button>`;
    chips.innerHTML = all + list.map((p) =>
      `<button class="chip" style="--c:${plat(p).c}" data-p="${esc(p)}" aria-pressed="${active.has(p)}">` +
      `<i></i>${esc(p)} <small>${counts[p]}</small></button>`).join("");
  }
  const idx = (p) => (ORDER.indexOf(p) + 1 || 999);

  chips.addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    const p = b.dataset.p;
    if (!p) active.clear();
    else active.has(p) ? active.delete(p) : active.add(p);
    renderChips();
    render();
  });

  // ---------- library ----------
  function filtered() {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    return games.filter((g) =>
      (active.size === 0 || active.has(g.platform)) && terms.every((t) => g.hay.includes(t)));
  }

  function sorted(list) {
    const byDate = (a, b) => (a.release || "9999").localeCompare(b.release || "9999") || a.name.localeCompare(b.name);
    const s = sortSel.value;
    if (s === "newest") return list.sort((a, b) => -byDate(a, b));
    if (s === "title") return list.sort((a, b) => sortTitle(a).localeCompare(sortTitle(b)));
    if (s === "platform") return list.sort((a, b) => idx(a.platform) - idx(b.platform) || byDate(a, b));
    return list.sort(byDate);
  }
  const sortTitle = (g) => g.name.replace(/^(the|a|an)\s+/i, "");

  function groupKey(g) {
    const s = sortSel.value;
    if (s === "title") {
      const ch = sortTitle(g)[0]?.toUpperCase() || "#";
      return /[A-Z]/.test(ch) ? ch : "#";
    }
    if (s === "platform") return g.platform;
    return g.year || "Unknown";
  }

  function card(g) {
    const p = plat(g.platform);
    const art = g.cover
      ? `<img src="${esc(g.cover)}" alt="" loading="lazy">`
      : `<div class="noart">${esc(g.name)}</div>`;
    return `<button class="card" data-id="${esc(g.id)}" style="--c:${p.c}">
      <div class="art">${art}<span class="plat">${esc(p.s)}</span>${g.video || g.clip ? '<span class="play"></span>' : ""}</div>
      <div class="t">${esc(g.name)}</div>
      <div class="y">${g.year || "—"}</div>
    </button>`;
  }

  function render() {
    const list = sorted(filtered());
    $("#empty").hidden = list.length > 0 || games.length === 0;
    const groups = [];
    for (const g of list) {
      const k = groupKey(g);
      if (!groups.length || groups[groups.length - 1].k !== k) groups.push({ k, items: [] });
      groups[groups.length - 1].items.push(g);
    }
    // One flowing grid; a marker tile starts each year / letter / platform.
    lib.innerHTML = `<div class="grid">` + groups.map((gr) => {
      const c = sortSel.value === "platform" ? plat(gr.k).c : "";
      return `<div class="mark"${c ? ` style="--c:${c}"` : ""}><b>${esc(gr.k)}</b>` +
        `<span>${gr.items.length} game${gr.items.length === 1 ? "" : "s"}</span></div>` +
        gr.items.map(card).join("");
    }).join("") + `</div>`;
  }

  q.addEventListener("input", render);
  sortSel.addEventListener("change", () => {
    try { localStorage.setItem("sort", sortSel.value); } catch {}
    render();
  });

  // ---------- hover clips (only for games with a clips/<id>.webm file) ----------
  lib.addEventListener("mouseover", (e) => {
    const c = e.target.closest(".card");
    if (!c || c.querySelector("video")) return;
    const g = games.find((x) => x.id === c.dataset.id);
    if (!g?.clip) return;
    const v = Object.assign(document.createElement("video"),
      { src: g.clip, muted: true, loop: true, autoplay: true, playsInline: true });
    c.querySelector(".art").appendChild(v);
    c.addEventListener("mouseleave", () => v.remove(), { once: true });
  });

  // ---------- modal ----------
  function open(g) {
    const p = plat(g.platform);
    modal.style.setProperty("--c", p.c);
    const media = $("#m-media");
    if (g.video) {
      const params = new URLSearchParams({ autoplay: 1, mute: 1, rel: 0, playsinline: 1, start: g.start || 0 });
      media.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(g.video)}?${params}"
        title="${esc(g.name)} video" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>`;
    } else {
      const search = "https://www.youtube.com/results?search_query=" + encodeURIComponent(`${g.name} ${g.platform} gameplay`);
      media.innerHTML = `<div class="novid" style="background-image:url('${esc(g.cover || "")}')"><div>
        <p>No video picked for this one yet.</p>
        <a href="${search}" target="_blank" rel="noopener">Find gameplay on YouTube</a></div></div>`;
    }
    $("#m-cover").src = g.cover || "";
    $("#m-platform").textContent = g.platform;
    $("#m-title").textContent = g.name;
    const who = [...new Set([...(g.developer || []), ...(g.publisher || [])])].slice(0, 3).join(" / ");
    $("#m-meta").textContent = [fmtDate(g.release, g.precision), who, (g.genres || []).slice(0, 3).join(", ")]
      .filter(Boolean).join("  ·  ");
    $("#m-summary").textContent = g.summary || "";
    const link = $("#m-igdb");
    link.hidden = !g.igdbUrl;
    link.href = g.igdbUrl || "#";
    if (!modal.open) modal.showModal();
    history.replaceState(null, "", "#" + g.id);
  }

  function close() {
    $("#m-media").innerHTML = ""; // stops the video
    if (modal.open) modal.close();
    history.replaceState(null, "", location.pathname + location.search);
  }

  lib.addEventListener("click", (e) => {
    const c = e.target.closest(".card");
    if (c) open(games.find((x) => x.id === c.dataset.id));
  });
  modal.querySelector(".close").addEventListener("click", close);
  modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
  modal.addEventListener("cancel", (e) => { e.preventDefault(); close(); });

  $("#surprise").addEventListener("click", () => {
    const list = filtered();
    if (list.length) open(list[Math.floor(Math.random() * list.length)]);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== q && !modal.open) {
      e.preventDefault();
      q.focus();
    }
  });

  renderStats();
  renderChips();
  render();
  const fromHash = games.find((g) => "#" + g.id === location.hash);
  if (fromHash) open(fromHash);
})();
