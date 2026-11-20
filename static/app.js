const $ = (sel) => document.querySelector(sel);

const form = $("#search-form");
const urlInput = $("#url");
const result = $("#result");
const loader = $("#loader");
const loaderText = $("#loader-text");
const alertBox = $("#alert");
const fmts = { video: $("#tab-video"), audio: $("#tab-audio") };

let currentUrl = null;
let infoCache = null;

function showAlert(msg) {
  alertBox.textContent = msg;
  alertBox.classList.remove("hidden");
}

function hideAlert() {
  alertBox.classList.add("hidden");
}

function setLoading(on, text) {
  loaderText.textContent = text || "";
  loader.classList.toggle("hidden", !on);
  $("#info-btn").disabled = on;
}

function humanSize(bytes) {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0, n = bytes;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return n.toFixed(n >= 100 || i === 0 ? 0 : 1) + " " + units[i];
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      Object.entries(fmts).forEach(([k, el]) =>
        el.classList.toggle("hidden", k !== btn.dataset.tab)
      );
    });
  });
}

function fmtRow(f, isAudioBest) {
  const row = document.createElement("div");
  row.className = "fmt";
  const badges = [
    f.progressive ? "video+audio" : "video only",
    f.fps ? f.fps + "fps" : null,
    f.hdr ? "HDR" : null,
    f.ext,
  ].filter(Boolean).map((t) => `<span class="tagchip">${esc(t)}</span>`).join("");
  const best = isAudioBest ? '<span class="mtime">✦ best</span>' : "";
  row.innerHTML = `
    <span class="q">${esc(f.label)}${best}</span>
    ${badges}
    <span class="size">${humanSize(f.filesize)}</span>
    <button class="dl" title="Download ${esc(f.label)}">⬇ Download</button>`;
  row.querySelector(".dl").addEventListener("click", (ev) => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    btn.textContent = "…preparing";
    startDownload({ url: currentUrl, fid: f.format_id, mode: f.kind === "audio" ? "audio" : "video" },
      () => { btn.disabled = false; btn.textContent = "⬇ Download"; });
  });
  return row;
}

function renderInfo(info) {
  infoCache = info;
  currentUrl = info.webpage_url;

  $("#thumb").src = info.thumbnail || "";
  $("#title").textContent = info.title || "";
  $("#byline").textContent = info.uploader || "";
  $("#stats").textContent = [
    info.duration_string ? "Length " + info.duration_string : null,
    info.view_count ? Number(info.view_count).toLocaleString() + " views" : null,
  ].filter(Boolean).join(" · ");

  const videos = info.formats.video || [];
  const audios = info.formats.audio || [];
  $("#video-count").textContent = videos.length + " qualities";
  $("#audio-count").textContent = audios.length + " streams";

  const videoList = fmts.video;
  videoList.innerHTML = "";
  videos.forEach((f) => videoList.appendChild(fmtRow(f)));

  const audioList = $("#audio-list");
  audioList.innerHTML = "";
  audios.forEach((f, i) => audioList.appendChild(fmtRow(f, i === 0)));

  result.classList.remove("hidden");
}

async function fetchInfo(url) {
  hideAlert();
  result.classList.add("hidden");
  setLoading(true, "Fetching video info…");
  try {
    const res = await fetch(`/api/info?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Failed to fetch info");
    renderInfo(data.info);
  } catch (err) {
    showAlert(err.message);
  } finally {
    setLoading(false);
  }
}

function startDownload(params, onDone) {
  const qs = new URLSearchParams({ url: params.url });
  if (params.fid) qs.set("fid", params.fid);
  if (params.mode) qs.set("mode", params.mode);
  if (params.audio_format) qs.set("audio_format", params.audio_format);
  if (params.quality) qs.set("quality", params.quality);
  hideAlert();
  const a = document.createElement("a");
  a.href = `/api/download?${qs.toString()}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(onDone, 1500);
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (url) fetchInfo(url);
});

$("#mp3-btn").addEventListener("click", (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  startDownload({ url: currentUrl, mode: "audio", audio_format: "mp3" },
    () => { btn.disabled = false; });
});
const cookieModal = $("#cookie-modal");
const cookieMsg = $("#cookie-msg");

$("#cookie-btn").addEventListener("click", () => cookieModal.classList.remove("hidden"));
$("#cookie-close").addEventListener("click", () => cookieModal.classList.add("hidden"));
cookieModal.addEventListener("click", (e) => {
  if (e.target === cookieModal) cookieModal.classList.add("hidden");
});

$("#cookie-save").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  cookieMsg.textContent = "Saving…";
  try {
    const res = await fetch("/api/cookies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        key: $("#cookie-key").value,
        cookies: $("#cookie-text").value,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Save failed");
    cookieMsg.textContent = "✅ Saved! Ab dobara Fetch dabao.";
  } catch (err) {
    cookieMsg.textContent = "❌ " + err.message;
  } finally {
    btn.disabled = false;
  }
});

$("#m4a-btn").addEventListener("click", (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  startDownload({ url: currentUrl, mode: "audio", audio_format: "m4a" },
    () => { btn.disabled = false; });
});
$("#opus-btn").addEventListener("click", (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  startDownload({ url: currentUrl, mode: "audio", audio_format: "opus" },
    () => { btn.disabled = false; });
});

bindTabs();
