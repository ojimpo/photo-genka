const $ = (id) => document.getElementById(id);
const yen = (v, digits = 1) =>
  "¥" + Number(v).toLocaleString("ja-JP", { maximumFractionDigits: digits, minimumFractionDigits: v < 100 ? digits : 0 });

const DAY_MS = 86400000;
const WD = ["日", "月", "火", "水", "木", "金", "土"];
// "YYYY-MM-DD" はローカル日付として解釈する（new Date(str) の UTC 解釈だと日付がずれる）
const parseDay = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (dt, n) => new Date(dt.getFullYear(), dt.getMonth(), dt.getDate() + n);
const dayKey = (dt) =>
  `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
const fmtMD = (dt) => `${dt.getMonth() + 1}/${dt.getDate()}`;
// 草は月曜始まり。土日が隣り合うので「週末に撮る」パターンが1本の帯として読める
const mondayIndex = (dt) => (dt.getDay() + 6) % 7; // 月=0 … 日=6

let STATS = null;
let HISTORY = [];
let DAILY = [];
let grassSummary = "";
let logScale = false;

async function load() {
  const [stats, history, daily] = await Promise.all([
    fetch("/api/stats").then((r) => r.json()),
    fetch("/api/history").then((r) => r.json()),
    fetch("/api/daily-shots").then((r) => r.json()),
  ]);
  STATS = stats;
  HISTORY = history;
  DAILY = daily;
  render();
}

function render() {
  const s = STATS;
  $("mock-badge").hidden = !s.mock;

  // ヒーロー
  $("since").textContent = `SINCE ${s.purchase_date.replaceAll("-", "/")}`;
  $("price").textContent = yen(s.price_per_shot);
  $("breakdown").textContent = `${yen(s.total_price, 0)} ÷ ${s.count.toLocaleString()}枚`;
  const d = $("delta");
  if (s.delta_from_prev != null) {
    const down = s.delta_from_prev <= 0;
    d.textContent = `${down ? "↓" : "↑"} 前日比 ${down ? "−" : "+"}${yen(Math.abs(s.delta_from_prev))}`;
    d.classList.toggle("up", !down);
  } else {
    d.textContent = "";
  }

  // キラキラ（時間ベース減衰）とアタリ（枚数ベース出現）
  $("sparkle").setAttribute("opacity", s.sparkle_opacity * 0.85);
  document.querySelectorAll(".wear").forEach((g) => {
    g.setAttribute("opacity", s.atari.level >= Number(g.dataset.level) ? 1 : 0);
  });
  $("atari-note").textContent = s.atari.shots_to_next != null
    ? `次のアタリまで ${s.atari.shots_to_next.toLocaleString()}枚`
    : "アタリ全解放 — 完全に相棒";

  // 分割払い進捗（演出専用）
  const ins = s.installments;
  $("installment-fill").style.width = `${(ins.ratio * 100).toFixed(1)}%`;
  $("installment-label").textContent =
    `自己保有比率 ${(ins.ratio * 100).toFixed(0)}% ・ 残り${ins.total - ins.paid}回（分割 ${ins.paid}/${ins.total}）`;

  // 数字カード
  $("count").textContent = `${s.count.toLocaleString()}枚`;
  $("trivia").textContent = s.trivia ? `≒ ${s.trivia.text}` : "";
  $("roll-shots").textContent = s.film.shots_per_roll;
  $("film-roll-price").textContent = yen(s.price_per_shot * s.film.shots_per_roll, 0);
  const ratioEl = $("film-ratio");
  if (s.film.cheaper_than_film) {
    ratioEl.textContent = `${s.film.ratio}倍お得`;
    ratioEl.classList.add("good");
    $("film-note").textContent = `フィルム${s.film.rolls_saved}本分お得`;
  } else {
    ratioEl.textContent = `あと${s.film.shots_to_breakeven.toLocaleString()}枚`;
    ratioEl.classList.remove("good");
    $("film-note").textContent = `フィルム(${yen(s.film.film_price_per_shot)}/枚)より安くなるまで`;
  }

  renderLastShot();
  drawChart();
  drawGrass();
}

// ④-1 最後に撮った日。撮影日時は JST の壁時計なので、そのまま桁を出す（閲覧側TZで換算しない）
function renderLastShot() {
  const ls = STATS.last_shot;
  const when = $("last-shot-when");
  const note = $("last-shot-note");
  if (!ls) {
    when.textContent = "—";
    note.textContent = "";
    return;
  }
  const dt = ls.at ? new Date(ls.at) : parseDay(ls.day);
  const hhmm = ls.at
    ? ` ${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`
    : "";
  when.textContent = `${fmtMD(dt)}(${WD[dt.getDay()]})${hhmm}`;
  const ago = ls.days_ago === 0 ? "今日" : ls.days_ago === 1 ? "昨日" : `${ls.days_ago}日前`;
  note.textContent = ls.shots ? `${ago} ・ その日 ${ls.shots.toLocaleString()}枚` : ago;
}

// ④-2 草: 日ごとの撮影枚数。濃さはフィルム換算（半本 / 1本 / 3本 / それ以上）で刻む
function grassLevel(shots, roll) {
  if (shots <= 0) return 0;
  if (shots < roll / 2) return 1;
  if (shots < roll) return 2;
  if (shots < roll * 3) return 3;
  return 4;
}

function drawGrass() {
  const s = STATS;
  const svg = $("grass-svg");
  const roll = s.film.shots_per_roll;
  const shots = new Map(DAILY.map((d) => [d.day, d.shots]));

  const end = parseDay(s.as_of);
  const purchase = parseDay(s.purchase_date);
  // 購入直後は購入週から始まり、1年を超えたら直近53週の移動窓になる
  const windowStart = addDays(end, -52 * 7);
  const start = purchase > windowStart ? purchase : windowStart;
  const gridStart = addDays(start, -mondayIndex(start)); // 週の頭（月曜）に揃える
  const weeks = Math.floor(Math.round((end - gridStart) / DAY_MS) / 7) + 1;

  const LBL = 16, GAP = 3;
  const avail = (svg.parentElement.clientWidth || 420) - 24; // section の左右パディング分
  const cell = Math.max(6, Math.min(16, Math.floor((avail - LBL) / weeks) - GAP));
  const step = cell + GAP;
  const TOP = cell + 4; // 月ラベル1行分
  const font = Math.min(9, Math.max(7, cell - 2));

  let cells = "", months = "", labelledAt = -99, prevMonth = -1;
  for (let w = 0; w < weeks; w++) {
    const colFirst = addDays(gridStart, w * 7);
    const x = LBL + w * step;
    if (colFirst.getMonth() !== prevMonth) {
      prevMonth = colFirst.getMonth();
      if (x - labelledAt >= 24) { // 詰まりすぎる月ラベルは省く
        labelledAt = x;
        months += `<text x="${x}" y="${cell - 1}" font-size="${font}" fill="#8F8C84">${prevMonth + 1}月</text>`;
      }
    }
    for (let d = 0; d < 7; d++) {
      const dt = addDays(colFirst, d);
      if (dt < purchase || dt > end) continue; // 購入前と未来は描かない
      const key = dayKey(dt);
      const v = shots.get(key);
      // スナップショットが飛んだ日は「記録なし」として薄く置く（0枚と区別する）
      const fill = v == null ? "var(--g0)" : `var(--g${grassLevel(v, roll)})`;
      cells +=
        `<rect x="${x}" y="${TOP + d * step}" width="${cell}" height="${cell}" rx="2" fill="${fill}"` +
        `${v == null ? ' opacity="0.4"' : ""} data-day="${key}" data-shots="${v ?? ""}">` +
        `<title>${fmtMD(dt)}(${WD[dt.getDay()]}) ${v == null ? "記録なし" : v + "枚"}</title></rect>`;
    }
  }
  const wdLabels = [0, 2, 4] // 月・水・金の行だけラベルを出す
    .map((d) => `<text x="${LBL - 4}" y="${TOP + d * step + cell * 0.85}" text-anchor="end" ` +
                `font-size="${font}" fill="#8F8C84">${WD[d + 1]}</text>`)
    .join("");

  svg.setAttribute("width", LBL + weeks * step);
  svg.setAttribute("height", TOP + 7 * step);
  svg.innerHTML = months + wdLabels + cells;

  const active = DAILY.filter((d) => d.shots > 0);
  const best = active.reduce((a, b) => (b.shots > a.shots ? b : a), { shots: 0 });
  grassSummary =
    `撮影した日 ${active.length}日 / ${DAILY.length}日` +
    (best.shots ? ` ・ 最多 ${best.shots.toLocaleString()}枚（${fmtMD(parseDay(best.day))}）` : "");
  $("grass-caption").textContent = grassSummary;
}

// タップで1日分の内訳を出す（モバイルには hover が無いため）
$("grass-svg").addEventListener("click", (e) => {
  const r = e.target.closest("rect");
  if (!r) {
    $("grass-caption").textContent = grassSummary;
    return;
  }
  const dt = parseDay(r.dataset.day);
  const v = r.dataset.shots;
  $("grass-caption").textContent =
    `${fmtMD(dt)}(${WD[dt.getDay()]}) ${v === "" ? "記録なし" : Number(v).toLocaleString() + "枚"}`;
});

let resizeTimer;
addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (STATS) drawGrass(); }, 150);
});

// ③ グラフ: 縦軸=1枚単価、横軸=時系列。緑の双曲線＋フィルム基準線＋損益分岐マーカー
function drawChart() {
  const s = STATS;
  const svg = $("chart-svg");
  const W = 440, H = 180, L = 44, R = 430, T = 15, B = 145;
  const film = s.film.film_price_per_shot;

  let points = HISTORY.map((h) => ({ t: new Date(h.day).getTime(), price: h.price }));
  if (points.length === 0) {
    // 履歴がまだ無い間は購入日→今日を現在値への双曲線で補間表示
    const t0 = new Date(s.purchase_date).getTime();
    const t1 = new Date(s.as_of).getTime() || t0 + 86400e3;
    for (let i = 1; i <= 24; i++) {
      const f = i / 24;
      points.push({ t: t0 + (t1 - t0) * f, price: s.total_price / Math.max(1, s.count * f) });
    }
  }
  const t0 = new Date(s.purchase_date).getTime();
  const t1 = Math.max(points[points.length - 1].t, t0 + 86400e3);
  const maxP = Math.max(...points.map((p) => p.price), film) * 1.15;
  const minP = logScale ? Math.min(...points.map((p) => p.price), film) * 0.8 : 0;

  const x = (t) => L + ((t - t0) / (t1 - t0)) * (R - L);
  const y = (p) => {
    if (logScale) {
      const lo = Math.log(minP), hi = Math.log(maxP);
      return B - ((Math.log(p) - lo) / (hi - lo)) * (B - T);
    }
    return B - ((p - minP) / (maxP - minP)) * (B - T);
  };

  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.price).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];

  // 損益分岐点: 単価がフィルム単価を初めて下回った点
  const cross = points.find((p) => p.price <= film);
  const fmtDay = (t) => fmtMD(new Date(t));

  svg.innerHTML = `
    <line x1="${L}" y1="${B}" x2="${R}" y2="${B}" stroke="#C9C5BC"/>
    <line x1="${L}" y1="${T}" x2="${L}" y2="${B}" stroke="#C9C5BC"/>
    ${film < maxP && film > minP ? `
      <line x1="${L}" y1="${y(film)}" x2="${R}" y2="${y(film)}" stroke="#B97A1B" stroke-dasharray="5 4"/>
      <text x="${R - 4}" y="${y(film) - 6}" text-anchor="end" font-size="10" fill="#B97A1B">フィルム単価 ${yen(film)}/枚</text>` : ""}
    <path d="${path}" fill="none" stroke="#3E6B4F" stroke-width="2"/>
    ${cross ? `
      <circle cx="${x(cross.t)}" cy="${y(cross.price)}" r="4" fill="#3E6B4F"/>
      <text x="${x(cross.t) + 8}" y="${y(cross.price) - 10}" font-size="10" fill="#6E6C66">${fmtDay(cross.t)} フィルム超え</text>` : ""}
    <circle cx="${x(last.t)}" cy="${y(last.price)}" r="4" fill="#3E6B4F"/>
    <text x="${x(last.t) - 6}" y="${Math.max(T + 8, y(last.price) - 10)}" text-anchor="end" font-size="10" fill="#2B2A28">${yen(last.price)}</text>
    <text x="${L - 6}" y="${T + 8}" text-anchor="end" font-size="10" fill="#8F8C84">${yen(maxP, 0)}</text>
    <text x="${L - 6}" y="${B + 4}" text-anchor="end" font-size="10" fill="#8F8C84">${yen(minP, 0)}</text>
    <text x="${L + 4}" y="${B + 16}" font-size="10" fill="#8F8C84">${fmtDay(t0)}（購入）</text>
    <text x="${R}" y="${B + 16}" text-anchor="end" font-size="10" fill="#8F8C84">今日</text>`;
}

$("scale-toggle").addEventListener("click", () => {
  logScale = !logScale;
  $("scale-toggle").textContent = logScale ? "線形スケール ⇄" : "対数スケール ⇄";
  drawChart();
});

// ④ ドロップゾーン: 写真 → 何枚目・撮影時点の単価（画像は保存されない）
const drop = $("drop");
const input = $("file-input");
drop.addEventListener("click", () => input.click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("hover"); });
drop.addEventListener("dragleave", () => drop.classList.remove("hover"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("hover");
  if (e.dataTransfer.files[0]) inspect(e.dataTransfer.files[0]);
});
input.addEventListener("change", () => { if (input.files[0]) inspect(input.files[0]); });

async function inspect(file) {
  const result = $("drop-result");
  result.hidden = false;
  result.innerHTML = "読み取り中…";
  const form = new FormData();
  form.append("file", file);
  try {
    const r = await fetch("/api/inspect", { method: "POST", body: form });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "読み取りに失敗しました");
    result.innerHTML =
      `<div>この写真は <span class="big">${j.image_count.toLocaleString()}枚目</span></div>` +
      `<div>撮影時点の単価 <span class="big">${yen(j.price_then)}</span> → 現在 <span class="big">${yen(j.price_now)}</span></div>`;
  } catch (err) {
    result.innerHTML = `<span class="err">${err.message}</span>`;
  }
}

load();
