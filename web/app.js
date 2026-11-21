"use strict";
// 网页客户端：进房间、选人、对战、观战、聊天、看回放。
// 网页不懂规则：服务器发来“你现在能看到什么、需要做什么”，这里只负责显示和把选择发回去。
// 对战画面和动画在 stage.js 里。

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};
// 座位凭证按“这个页面”保存：刷新页面能坐回原位；同一个浏览器开两个页面可以分别当 A 和 B。
const seatStore = {
  get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} },
};

let ws = null;
let me = null;            // {room, side, role, token, name}。role：play 上场，watch 观战，replay 看回放；后两种 side 是 null
let S = null;             // 服务器发来的最新局面
let replay = null;        // 正在看的回放（一局的完整记录）
let replayDone = false;   // 回放有没有放完
let catalog = [];         // 可以选的人物
let scenes = [];          // [{name, height}]
let ART = new Set();      // 有图的人物名字；没有图的用圆圈加名字顶替
let DEF_ART = new Set();  // 有的防御手绘图标；没有的只显示文字
let FX_ART = new Set();   // 有的技能特效贴图（web/assets/effects/）；没有的用代码画的简单特效顶替
let PAGE_STAMP = null;    // 这个页面加载时，服务器上网页文件的版本
// 本机素材的清单。进房间、看回放、刚打开页面时各拿一次。
function useAssets(m) {
  ART = new Set(m.art || []); DEF_ART = new Set(m.defense_art || []); FX_ART = new Set(m.effects || []);
  BACKDROPS = m.backgrounds || [];
  const title = (m.ui || []).includes("title");
  document.body.classList.toggle("has-title", title);
  // 服务器上的网页文件比这个页面新（我改了代码）：自己刷新一次
  if (PAGE_STAMP == null) PAGE_STAMP = m.stamp || 0;
  else if (m.stamp && m.stamp !== PAGE_STAMP) location.reload();
}
// 用哪一种防御能防住：招上写的“防”对应的图标和名字。j 是平面镜，s 是憋神技。
const DEF_ICON = { 1: "d1", 2: "d2", 3: "d3", 4: "d4", j: "dhands", s: "dinf" };
const DEF_NAME = { 1: "防御1", 2: "防御2", 3: "防御3", 4: "防御4", j: "平面镜", s: "憋神技" };
const DEF_OF_ACTION = { d1: 1, d2: 2, d3: 3, d4: 4, dj: "j", ds: "s" };      // 防御按钮自己是哪一种
function defIcon(code, hint) {
  const file = DEF_ICON[code];
  if (!file || !DEF_ART.has(file)) return "";
  return `<img class="deficon" src="assets/defense/${file}.png" alt="${esc(DEF_NAME[code])}" title="${esc(hint)}">`;
}
let events = [];          // 从开局到现在的全部事件
let stage = null;         // 对战舞台（stage.js）
let played = 0;           // 已经播过动画的事件条数
let playing = false;
let run = 0;              // 第几轮播放。换了一局以后，上一轮还没播完的动画不再往下播
function resetPlayback() { stage = null; played = 0; playing = false; run++; }
// aim：这一招打对手还是打自己。mode：操作区现在显示什么（战斗、物品、换人）。
const ui = { picked: [], touched: false, tab: "全部", mode: "moves", search: "", sceneAction: null, wanted: null, aim: "foe" };
const HAND_NAMES = ["石头", "剪刀", "布"];
const HAND_GLYPH = { "石头": "✊", "剪刀": "✌", "布": "✋" };

function toast(text) {
  const el = $("#toast");
  el.textContent = text; el.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 3500);
}
function send(message) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(message)); }

// 选人物、对战、弹出的窗口都画在一块 1600×900 的画面上（.frame，和设计稿一样大），按窗口大小整体等比缩放。
function fitFrames() {
  const k = Math.min(window.innerWidth / 1600, window.innerHeight / 900);
  if (document.documentElement && k > 0) document.documentElement.style.setProperty("--k", String(k));
}
if (window.addEventListener) window.addEventListener("resize", fitFrames);
fitFrames();
const X_ICON = `<svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round"><path d="M5 5 L19 19 M19 5 L5 19"></path></svg>`;
// 小标签。kind：plain（默认）、bad、good、inner、on（金色）
const chipHtml = (text, kind = "", attrs = "") => `<span class="chip ${kind}"${attrs ? " " + attrs : ""}>${esc(text)}</span>`;

// 画面左边站谁：上场的人自己在左边；观战和回放时 A 在左边。
const inGame = () => !!me && me.role === "play";
const leftSide = () => (me && me.side) || "A";
const rightSide = () => (leftSide() === "A" ? "B" : "A");
const seatName = (side) => (S && S.seats && S.seats[side] ? S.seats[side].name : side);
// 怎么称呼一方：上场的人看到“你”和“对手”，旁观的人看到名字。
const who = (side) => (inGame() ? (side === me.side ? "你" : "对手") : seatName(side));
// 把“A的武圣”这种写法换成“你的武圣”“对手的武圣”。
// 也管“A先出手”“A出剪刀，B出石头，B赢”这几种写法。
const personal = (text) => (inGame()
  ? String(text || "").replace(/([AB])(?=的|先出手|出(?:石头|剪刀|布)|赢)/g, (_, side) => (side === me.side ? "你" : "对手"))
  : String(text || ""));

// ---------- 说明文字：悬浮描述框、人物详情、图鉴用的是同一份（服务器的 /api/codex） ----------

let CODEX = null;
const codexIndex = { skill: {}, char: {}, inner: {}, status: {}, parasite: {}, scene: {} };
async function loadCodex() {
  try {
    const c = await (await fetch("api/codex")).json();
    for (const x of c.skills) codexIndex.skill[x.id] = x;
    for (const x of c.characters) codexIndex.char[x.name] = x;
    for (const x of c.inner) codexIndex.inner[x.name] = x;
    for (const x of c.statuses) codexIndex.status[x.name] = x;
    for (const x of c.parasites) codexIndex.parasite[x.name] = x;
    for (const x of c.scenes) codexIndex.scene[x.name] = x;
    CODEX = c;
  } catch (e) { /* 读不到说明文字：悬浮框不出，别的照常 */ }
}
const tipLines = (lines) => (lines || []).map(([style, text]) => `<span class="t-${style}">${esc(text)}</span>`).join("");
const tipHead = (name, tag) => `<span class="t-head"><b>${esc(name)}</b>${tag ? "（" + esc(tag) + "）" : ""}</span>`;
const innerLine = (name, level) => {
  const c = codexIndex.inner[name];
  return c && c.lines[level - 1] ? c.lines[level - 1][1].replace(/^\d 级：/, "") : "";
};

// 鼠标停在一样东西上要显示什么。key 的写法：“act:招的编号”“soul:人物名”“inner:内功名:级别”“status:状态名”等等。
function tipHtml(key) {
  const cut = key.indexOf(":"), kind = cut < 0 ? key : key.slice(0, cut), id = cut < 0 ? "" : key.slice(cut + 1);
  if (kind === "text") return `<span class="t-text">${esc(id)}</span>`;
  if (kind === "act") {                          // 选招时的一张卡：说明文字，加上现在能不能用
    const live = !!S && S.need === "choose" && !playing;
    const a = ((S && (live ? S.actions : ui.lastActions)) || []).find((x) => x.id === id);
    if (!a) return "";
    const self = ui.aim === "self", ok = self ? a.self_ok : a.legal, why = self ? a.self_reason : a.reason;
    let html;
    if (a.action_kind === "learn") {
      const c = codexIndex.inner[a.inner];
      html = tipHead(a.name, "内功") + `<span class="t-stat">现在 ${a.level} 级，学了 ${a.progress} 下${a.next ? "，到 " + a.next + " 下升级" : ""}。</span>
        <span class="t-text">学一次内功占这个回合的出招。</span>` + tipLines(c && c.lines.filter(([style]) => style === "text"));
    } else if (a.action_kind === "switch") {
      const c = codexIndex.char[a.name.replace(/^换上/, "")];
      html = tipHead(a.name, "换人") + `<span class="t-text">换人占这个回合的出招，比所有的招都先生效。</span>` + tipLines(c && c.lines);
    } else {
      const c = codexIndex.skill[a.id];
      html = c ? tipHead(c.name, c.tag) + tipLines(c.lines)
        : tipHead(a.name, (a.attributes || []).join("+")) + (a.description ? `<span class="t-text">${esc(a.description)}</span>` : "");
      if (/^已经造了/.test(a.description || "")) html += `<span class="t-stat">${esc(a.description.split("。")[0])}。</span>`;
    }
    if (live && !ok && why) html += `<span class="t-bad">现在不能用：${esc(personal(why))}。</span>`;
    else if (live && !self && a.warning) html += `<span class="t-warn">${esc(a.warning)}。</span>`;
    return html;
  }
  if (kind === "skill") { const c = codexIndex.skill[id]; return c ? tipHead(c.name, c.tag) + tipLines(c.lines) : ""; }
  if (kind === "soul") { const c = codexIndex.char[id]; return c ? tipHead(c.name, "魂印") + tipLines(c.lines) : ""; }
  if (kind === "inner") {
    const [name, level] = id.split(":"), c = codexIndex.inner[name];
    return c ? tipHead(name + " " + level + " 级", "内功") + tipLines(c.lines.map(([, text], i) => [i === level - 1 ? "stat" : "text", text])) : "";
  }
  if (kind === "inners") {                       // 内功太多的人物：一个标签列出全部
    const p = S && S.view && S.view.players[id], f = p && p.team[p.active];
    if (!f) return "";
    return tipHead(f.name + "的内功", "") + Object.entries(f.inner || {}).filter(([, v]) => v > 0)
      .map(([k, v]) => `<span class="${innerOff(f, k) ? "t-bad" : "t-text"}">${esc(k)} ${v} 级${innerOff(f, k)}：${esc(innerLine(k, v))}</span>`).join("");
  }
  if (kind === "status") { const c = codexIndex.status[id]; return c ? tipHead(id, c.good ? "好状态" : "不良状态") + `<span class="t-text">${esc(c.text)}</span>` : ""; }
  if (kind === "parasite") { const c = codexIndex.parasite[id]; return c ? tipHead(id, "虫子") + `<span class="t-text">${esc(c.text)}</span>` : ""; }
  if (kind === "scene") { const c = codexIndex.scene[id]; return c ? tipHead(id, "场景") + tipLines(c.lines) : ""; }
  return "";
}

// 描述框：略透明的黑底白字，贴着鼠标停的那样东西的上边；上边放不下就放下边。
const tipEl = document.createElement("div");
tipEl.id = "tip"; tipEl.hidden = true;
let tipFor = null;
function showTip(target) {
  let html = tipHtml(target.dataset.tip || "");
  if (!html) return hideTip();
  if (target.dataset.detail) html += `<span class="t-note">点一下看详情。</span>`;
  if (!tipEl.parentNode) document.body.appendChild(tipEl);
  tipFor = target;
  tipEl.className = target.dataset.tip.startsWith("soul:") ? "soul" : "";
  tipEl.innerHTML = html; tipEl.hidden = false;
  const r = target.getBoundingClientRect(), w = tipEl.offsetWidth, h = tipEl.offsetHeight, gap = 6;
  const x = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
  let y = r.top - h - gap;
  if (y < 8) y = Math.min(r.bottom + gap, window.innerHeight - h - 8);
  tipEl.style.left = x + "px"; tipEl.style.top = Math.max(8, y) + "px";
}
function hideTip() { tipFor = null; tipEl.hidden = true; }
// 页面重画以后，鼠标原来停着的那样东西可能没了：没了就把框收起来；还在就把内容更新一下。
function refreshTip() {
  if (!tipFor) return;
  if (!document.body.contains(tipFor)) return hideTip();
  showTip(tipFor);
}
if (document.addEventListener) {
  const over = (ev) => {
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-tip]") : null;
    if (t) { if (t !== tipFor) showTip(t); } else if (tipFor) hideTip();
  };
  document.addEventListener("mouseover", over);
  document.addEventListener("focusin", over);
  document.addEventListener("scroll", hideTip, true);
  document.addEventListener("mouseleave", hideTip);
}

// ---------- 连接 ----------

function connect(room, name, watch) {
  ui.wanted = { room, name, watch: !!watch };
  const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
  ws = new WebSocket(url);
  ws.onopen = () => send({ t: "join", room, name, watch: !!watch, token: room ? seatStore.get("shai-token-" + room) : null });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.t === "error") return toast(m.message);
    if (m.t === "joined") {
      me = { room: m.room, side: m.side, role: m.role, token: m.token, name };
      catalog = m.characters; scenes = m.scenes; useAssets(m);
      events = []; resetPlayback();
      seatStore.set("shai-token-" + m.room, m.token);
      ui.wanted.room = m.room; location.hash = m.room;
      if (m.role === "watch" && !ui.wanted.watch) toast("房间里已经有两位玩家，你现在是观战。");
      return;
    }
    if (m.t === "state") {
      S = m; S.at = performance.now();
      if (m.events) {
        if (m.events_from === 0) events = [];
        if (m.events_from === events.length) events = events.concat(m.events);
      }
      if (m.phase === "lobby" && (events.length || stage)) { events = []; resetPlayback(); }
      render();
    }
  };
  ws.onclose = () => {
    if (replay) return;
    if (!me) return toast("连不上服务器。");
    toast("连接断开，正在重连…");
    setTimeout(() => connect(ui.wanted.room, ui.wanted.name, ui.wanted.watch), 1500);
  };
}

// ---------- 进房间 ----------

function renderJoin() {
  const last = seatStore.get("shai-last-room");
  $("#app").innerHTML = `<div class="login">
    <div class="logo">晒</div>
    <div class="lpanel">
      <label><span>昵称</span><input class="field" type="text" id="name" maxlength="12" value="${esc(store.get("shai-name") || "")}"></label>
      <label><span>房间号</span><input class="field" type="text" id="room" maxlength="8" placeholder="留空就开一个新房间" value="${esc(location.hash.slice(1))}"></label>
      <label class="check"><input type="checkbox" id="watch">只观战，不上场</label>
      <button class="go oct" id="go">进入房间</button>
      <button class="bluebtn oct" id="opencodex">图鉴：看全部招式、人物、内功</button>
      <p>把房间号告诉朋友，他输入同一个房间号就能进来。房间里已经有两个人的话，后来的人自动观战。</p>
      ${last ? `<p class="back">你刚才退出的房间是 <b>${esc(last)}</b>，那一局还留着：输入这个房间号可以回去接着打。</p>` : ""}
    </div>
    <div class="lreplays"><b>以前的对局</b><div id="replaylist">正在读取…</div></div>
  </div>`;
  $("#go").onclick = () => {
    const name = $("#name").value.trim() || "无名";
    store.set("shai-name", name);
    connect($("#room").value.trim(), name, $("#watch").checked);
  };
  $("#opencodex").onclick = () => openCodex();
  loadReplayList();
}

const when = (seconds) => {
  const d = new Date(seconds * 1000), two = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
};

async function loadReplayList() {
  const box = $("#replaylist");
  try {
    const list = await (await fetch("api/replays")).json();
    if (!$("#replaylist")) return;
    if (!list.length) { box.textContent = "还没有打完的对局。每一局打完会自动保存在这里。"; return; }
    box.innerHTML = list.map((r) => {
      const side = (s) => `${esc(r.names[s])}（${esc(r.teams[s].join("、"))}）`;
      const result = r.winner ? esc(r.names[r.winner]) + " 赢了" : "平局";
      return `<div class="replayrow"><div><div class="r1"><b>${when(r.ended_at)}</b>　${result}，${r.rounds} 回合</div><div class="r2">${side("A")}　对　${side("B")}</div></div>
        <div class="row"><button class="small" data-replay="${esc(r.id)}">看回放</button><button class="small" data-log="${esc(r.id)}">文字战报</button></div></div>`;
    }).join("");
    box.onclick = (ev) => {
      const b = ev.target.closest("button"); if (!b) return;
      if (b.dataset.replay) openReplay(b.dataset.replay); else if (b.dataset.log) showSavedLog(b.dataset.log);
    };
  } catch (e) {
    if ($("#replaylist")) box.textContent = "读不到以前的对局。";
  }
}

// ---------- 能复制的文字框 ----------

// 弹出一个文字框，里面的字可以直接选中复制，也可以点“复制全部”。
function showText(title, text) {
  let box = $("#textbox");
  if (!box) {
    box = document.createElement("div"); box.id = "textbox"; box.className = "modal";
    box.innerHTML = `<div class="frame"><div class="window twin" role="dialog"><div class="whead"><b></b><button class="small gold" id="copyall">复制全部</button><button class="x" id="closetext" aria-label="关掉">${X_ICON}</button></div>
      <div class="wbody"><textarea readonly spellcheck="false"></textarea></div></div></div>`;
    document.body.appendChild(box);
    box.onclick = async (ev) => {
      const area = $("textarea", box);
      if (ev.target === box || ev.target === box.firstElementChild || ev.target.closest("#closetext")) { box.hidden = true; return; }
      if (ev.target.id !== "copyall") return;
      area.focus(); area.select();
      try { await navigator.clipboard.writeText(area.value); } catch (e) { try { document.execCommand("copy"); } catch (e2) { /* 复制不了就让人自己按 Ctrl+C，文字已经全选了 */ } }
      ev.target.textContent = "已复制";
      setTimeout(() => { ev.target.textContent = "复制全部"; }, 1500);
    };
  }
  $(".whead b", box).textContent = title;
  $("textarea", box).value = text;
  box.hidden = false;
  $("textarea", box).scrollTop = 0;
}

async function showSavedLog(id) {
  try {
    const r = await fetch("api/replays/" + encodeURIComponent(id) + "/log");
    if (!r.ok) throw new Error(id);
    showText("文字战报", await r.text());
  } catch (e) { toast("这一局的战报读不出来。"); }
}

// ---------- 回放 ----------

async function openReplay(id) {
  try {
    const get = async (url) => { const r = await fetch(url); if (!r.ok) throw new Error(url); return r.json(); };
    const [record, info] = await Promise.all([get("api/replays/" + encodeURIComponent(id)), get("api/info")]);
    replay = record; scenes = info.scenes; useAssets(info);
    me = { room: record.room, side: null, role: "replay", name: "" };
    startReplay();
  } catch (e) { toast("这个回放打不开。"); }
}

function startReplay() {
  const r = replay;
  S = {
    phase: "over", room: r.room, role: "replay", need: "replay", view: r.final_view, paused: false,
    seats: { A: { name: r.names.A }, B: { name: r.names.B } }, watchers: [], chat: [], timers: null,
    settings: {}, prompt: { winner: r.winner }, at: performance.now(),
  };
  events = r.events; resetPlayback(); replayDone = false;
  $("#app").innerHTML = "";
  render();
}

// ---------- 聊天 ----------

function chatHtml() {
  return (S.chat || []).map((c) => (c.who === "sys"
    ? `<p class="sys">${esc(c.text)}</p>`
    : `<p><b class="who-${esc(c.who)}">${esc(c.name)}${c.who === "w" ? "（观战）" : ""}：</b>${esc(c.text)}</p>`)).join("")
    || `<p class="muted">还没有人说话。</p>`;
}
const chatBoxHtml = () => `<div class="chat" id="chat"></div>
  <form class="chatform" id="chatform"><input class="field" type="text" id="chattext" maxlength="200" placeholder="说点什么" autocomplete="off"><button class="small">发送</button></form>`;

function renderChat() {
  const box = $("#chat"); if (!box || !S) return;
  const list = S.chat || [], last = list.length ? list[list.length - 1].n : -1;
  if (box.dataset.last === String(last)) return;
  box.dataset.last = String(last);
  box.innerHTML = chatHtml(); box.scrollTop = box.scrollHeight;
}
function bindChat() {
  const form = $("#chatform"); if (!form) return;
  form.onsubmit = (ev) => {
    ev.preventDefault();
    const input = $("#chattext"), text = input.value.trim();
    if (text) send({ t: "chat", text });
    input.value = "";
  };
}

// ---------- 选人 ----------

function renderLobby() {
  const host = me.side === "A", watch = !inGame(), size = S.settings.team_size, ready = !!S.my_team;
  // 刷新页面以后，把服务器记着的“已经点了哪几个”拿回来（自己点过以后就以网页上的为准）。
  if (!ready && !ui.touched && !ui.picked.length && S.my_draft && S.my_draft.length) ui.picked = S.my_draft.slice();
  const picked = ready ? S.my_team : (ui.picked = ui.picked.filter((n) => catalog.some((c) => c.name === n)).slice(0, size));
  const draft = $("#chattext") ? { text: $("#chattext").value, focus: document.activeElement === $("#chattext") } : null;
  const L = watch ? "A" : me.side, R = L === "A" ? "B" : "A";
  // 上面左右两块牌子：自己（观战时是 A）和对手
  const status = (x) => (!x ? `把房间号 ${S.room} 告诉朋友` : !x.connected ? "掉线了" : x.ready ? "已经选好了" : "正在选人物");
  const plate = (cls, label, side) => {
    const x = S.seats[side];
    const name = x ? x.name + (x.bot ? "（电脑）" : "") : "还没有人";
    const line = cls === "mine" && !watch ? `房间 ${S.room}${ready ? " · 已经选好了" : ""}` : status(x);
    return `<div class="plate ${cls} oct"><span class="pside">${label[0]}<br>${label[1]}</span><span class="pwho"><b>${esc(name)}</b><span>${esc(line)}</span></span></div>`;
  };
  // 人物格子：方头像加名字条。选上的写第几个上场，第一个是“首发”。
  const pc = (name, order, attrs) => `<button class="pc" data-name="${esc(name)}" data-tip="soul:${esc(name)}" aria-pressed="${!!order}" ${attrs || ""}>
      <span class="art">${ART.has(name) ? `<img alt="" src="assets/characters/${encodeURIComponent(name)}.png">` : esc(name.slice(0, 1))}</span><span class="pn">${esc(name)}</span>
      ${order ? `<span class="ord">${order}</span><span class="otag ${order === 1 ? "first" : ""}">${order === 1 ? "首发" : "出战"}</span>` : ""}</button>`;
  const unknown = `<span class="pc unknown"><span class="art">？</span><span class="pn">？？？</span></span>`;
  const empty = (i) => `<span class="pc empty"><span class="art">第 ${i + 1} 个</span><span class="pn"></span></span>`;
  const w = size <= 5 ? 120 : Math.floor((644 - (size - 1) * 11) / size);       // 一队超过 5 个人时，右边的格子缩小一点排得下
  const row = (html) => `<div class="pcs" style="--w:${w}px">${html}</div>`;
  const grid = catalog.map((c) => pc(c.name, picked.indexOf(c.name) + 1, ready || watch ? "disabled" : "")).join("");
  const right = watch
    ? `<div class="bartitle">${esc(seatName("A"))}带的人物</div>${row(unknown.repeat(size))}<span class="cap">两位玩家选了谁，要等人物上场才看得到。</span>
       <div class="sec2"><div class="bartitle">${esc(seatName("B"))}带的人物</div>${row(unknown.repeat(size))}<span class="cap">两位玩家选好人物就开始。</span></div>`
    : `<div class="bartitle">对手带的人物</div>${row(unknown.repeat(size))}<span class="cap">对手选了谁，要等他的人物上场才看得到。</span>
       <div class="sec2"><div class="bartitle">你的出战顺序</div>
         ${row(picked.map((n, i) => pc(n, i + 1, ready ? "disabled" : "")).join("") + Array.from({ length: Math.max(0, size - picked.length) }, (_, i) => empty(picked.length + i)).join(""))}
         <span class="cap">第一个选的先上场。再点一下可以取消。${S.settings.timers ? "时间到了没选满的随机补齐。" : ""}</span></div>`;
  const button = watch ? "" : ready
    ? `<button class="pkconfirm oct redo" id="unready">重新选</button>`
    : `<button class="pkconfirm oct" id="ready" ${picked.length === size ? "" : "disabled"}>确认出战</button>`;
  const dis = host ? "" : "disabled";
  const photo = BACKDROPS.length ? ` style="--photo:url('assets/backgrounds/${encodeURIComponent(BACKDROPS[0])}')"` : "";
  $("#app").innerHTML = `<div id="pick" class="screen"${photo}><div class="frame">
    <div class="pkstrip"></div>
    ${watch ? plate("mine", "A方", "A") + plate("theirs", "B方", "B") : plate("mine", "己方", L) + plate("theirs", "对方", R)}
    <div class="pktitle"><b>选择</b><span>出战人物</span></div>
    <div class="pkgrid">${grid}</div>
    <div class="pkclock"><div class="diamond"><span id="pickclock"></span></div>
      <span class="pcount">${watch ? "双方正在选" : `已选 ${picked.length} / ${size}`}<small id="pickclocksub"></small></span></div>
    <div class="pkright">${right}</div>
    ${button}
    <div class="pkset">
      <label>每人带 <select class="field" id="size" ${dis}>${Array.from({ length: S.settings.max_team }, (_, i) => `<option ${i + 1 === size ? "selected" : ""}>${i + 1}</option>`).join("")}</select> 个人物</label>
      <label><input type="checkbox" id="zei" ${S.settings.zei ? "checked" : ""} ${dis}>用贼（石头剪刀布）决定先后手和概率</label>
      <label><input type="checkbox" id="timers" ${S.settings.timers ? "checked" : ""} ${dis}>限时（选人物 ${S.settings.team_seconds} 秒，选招 ${S.settings.choose_seconds} 秒，贼 ${S.settings.zei_seconds} 秒）</label>
      ${host && !S.seats.B ? `<button class="small" id="bot">加一个电脑对手</button>` : ""}
      ${host ? "" : `<span class="muted">设置由房主（A）决定</span>`}
      <button class="small" id="opencodex">图鉴</button>
      ${S.watchers.length ? `<span class="muted">观战：${esc(S.watchers.join("、"))}</span>` : ""}
    </div>
    <div class="pkchat">${chatBoxHtml()}</div>
  </div></div>`;
  if (host) {
    $("#size").onchange = (e) => send({ t: "config", team_size: +e.target.value });
    $("#zei").onchange = (e) => send({ t: "config", zei: e.target.checked });
    $("#timers").onchange = (e) => send({ t: "config", timers: e.target.checked });
    if ($("#bot")) $("#bot").onclick = () => send({ t: "bot" });
  }
  $("#opencodex").onclick = () => openCodex();
  if ($("#ready")) $("#ready").onclick = () => send({ t: "team", names: ui.picked });
  if ($("#unready")) $("#unready").onclick = () => send({ t: "unready" });
  // 左边的格子点一下选上，再点一下取消；右边“你的出战顺序”里的点一下也是取消
  $("#pick").onclick = (ev) => {
    const card = ev.target.closest("button.pc[data-name]"); if (!card || ready || watch) return;
    const name = card.dataset.name, i = ui.picked.indexOf(name);
    if (i >= 0) ui.picked.splice(i, 1); else if (ui.picked.length < size) ui.picked.push(name);
    ui.touched = true;
    send({ t: "draft", names: ui.picked });       // 服务器记着点了哪几个：选人物超时的时候，这几个保留，剩下的随机补齐
    renderLobby();
  };
  renderChat(); bindChat();
  if (draft) { $("#chattext").value = draft.text; if (draft.focus) $("#chattext").focus(); }
  tickClock();
}

// ---------- 对战 ----------

const modelOf = (view) => ({
  A: view.players.A.team[view.players.A.active], B: view.players.B.team[view.players.B.active], water: view.water_level,
});
const choosing = () => !!S && S.need === "choose" && !playing;
const wan = (n) => (n >= 10000 ? String(Math.round(n / 100) / 100) + " 万" : String(n));
const faceHtml = (name) => (ART.has(name)
  ? `<img alt="" src="assets/characters/${encodeURIComponent(name)}.png">` : `<i>${esc((name || "？").slice(0, 1))}</i>`);

// 这种内功现在是不是不起作用：被封内，或者幸运、大难不死被华支睾吸虫吸走。不起作用就返回一句说明。
function innerOff(f, name) {
  if ((f.statuses || {})["封内"]) return "（被封内，不起作用）";
  if ((f.parasites || {})["华支睾吸虫"] && (name === "幸运" || name === "大难不死")) return "（被华支睾吸虫吸走，不起作用）";
  return "";
}

// 牌子下面那一行小标签里归这里管的：已选招、内功、物品、造的东西。状态、虫子、辐射和头像、血条是 stage.js 画的。
function extraHtml(side) {
  if (replay && !replayDone) return "";       // 记录里只存了最后的局面，放完之前不显示，免得剧透
  const p = S.view.players[side], active = p.team[p.active];
  if (!active) return "";
  const lent = new Set(active.borrowed || []), learned = new Set(active.learned || []);
  const mine = Object.entries(active.inner || {}).filter(([, v]) => v > 0);
  const sealed = (active.statuses || {})["封内"] ? "（被封内，现在都不起作用）" : (active.parasites || {})["华支睾吸虫"] ? "（幸运、大难不死被虫子吸走）" : "";
  const inner = mine.length > 4
    ? `<span class="chip inner ${sealed ? "dead" : ""}" data-tip="inners:${side}">内功 ${mine.length} 种${sealed}</span>`
    : mine.map(([k, v]) => `<span class="chip inner ${innerOff(active, k) ? "dead" : ""}" data-tip="inner:${esc(k)}:${v}">${esc(k)} ${v} 级${lent.has(k) ? "（借对手的）" : learned.has(k) ? "（学的）" : ""}${innerOff(active, k)}</span>`).join("");
  const items = Object.entries(active.resources || {}).filter(([, v]) => v > 0).map(([k, v]) => chipHtml(`${k} ${v}`)).join("");
  const devices = Object.entries(active.devices || {}).filter(([, v]) => v > 0).map(([k, v]) => chipHtml(`${k} 造了 ${v} 下`)).join("");
  const tree = p.tree ? chipHtml(`通天神树 ${p.tree}/10`) : "";
  const chosen = !replay && S.view.chosen[side] && S.need !== "over" ? chipHtml("已选招", "on") : "";
  return chosen + inner + items + devices + tree;
}
// 小标签下面一排场下的人物：小方头像。对手还没上过场的是问号。
function benchHtml(side) {
  if (replay && !replayDone) return "";
  const p = S.view.players[side];
  return p.team.map((f, i) => {
    if (i === p.active) return "";
    if (f.hidden) return `<span class="face unknown" title="还没上过场的人物">？</span>`;
    if (f.is_true_body && !f.entered) return "";
    return `<button class="face ${f.defeated ? "dim" : ""}" data-tip="soul:${esc(f.name)}" data-detail="${side}:${i}" aria-label="场下的${esc(f.name)}">${faceHtml(f.name)}</button>`;
  }).join("");
}
function renderExtras() {
  for (const side of ["A", "B"]) {
    const el = $(`[data-extra="${side}"]`), bench = $(`[data-bench="${side}"]`);
    if (el) el.innerHTML = extraHtml(side);
    if (bench) bench.innerHTML = benchHtml(side);
  }
}

function resultText(winner) {
  if (winner == null) return "平局";
  if (inGame()) return winner === me.side ? "你赢了" : "你输了";
  return esc(seatName(winner)) + " 赢了";
}

// 操作区上面那一行字：现在要你做什么。
function promptHtml() {
  const p = S.prompt || {}, R = rightSide();
  if (playing) return `<span>${replay ? "正在回放…" : "正在播放这一回合…"}</span><button class="pill" id="skip">${replay ? "跳到结尾" : "跳过动画"}</button>`;
  if (replay) {
    return `<span class="over">回放结束：${resultText(p.winner)}</span>
      <button class="primary" id="again">再放一遍</button><button class="pill" id="back">返回</button><button class="pill" data-log="${esc(replay.id)}">文字战报</button>`;
  }
  const soFar = (p.so_far || []).length ? `<ul>${p.so_far.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
  if (S.need === "over") {
    const saved = S.replay_id ? `<button class="pill" data-log="${esc(S.replay_id)}">这一局的文字战报</button>` : "";
    return `<span class="over">对战结束：${resultText(p.winner)}</span>${inGame() ? `<button class="primary" id="rematch">再来一局</button>` : ""}${saved}
      ${S.replay_id ? `<span>这一局已经保存。回到进房间的页面，在“以前的对局”里可以看回放。</span>` : ""}`;
  }
  const sees = (S.view && S.view.sees) || {};
  if (S.need === "choose") {
    if (inGame() && S.choose_for && S.choose_for !== me.side) {
      return `<b>对手这回合被你的虫子控制：现在替对手选他的招。</b><span>下面列的是对手的招。可以让他打你，也可以让他打他自己。</span>`;
    }
    const peek = S.view.peek;
    if (peek) return `<span class="peek">透视：对手这回合选了【${esc(peek.name)}】${peek.on_self ? "（打他自己）" : ""}${peek.destination ? "（去" + esc(peek.destination) + "）" : ""}。</span>`;
    return inGame() && sees[R] ? `<span>对手能透视你：你选完以后他才选，他看得到你选了什么。</span>` : "";
  }
  if (S.need === "pick") {
    return `<b>${esc(personal(p.reason))}</b>${soFar}${p.options.map((o) => `<button class="primary" data-pick="${esc(o.id)}">${esc(o.name)}</button>`).join("")}`;
  }
  if (p.mode) return `<span>正在贼：看舞台中间的框。</span>`;
  if (p.reason) return `<span>${esc(personal(p.reason))}…</span>`;
  return "";
}
// 页签右边那一行小字：没有别的要说的时候写这个
function hintHtml() {
  if (!S || S.need === "over" || replay) return "";
  if (ui.search) return `<span>搜到 ${ui.hits || 0} 个${ui.hits && choosing() ? "，按回车出第一个能用的" : ""}</span>`;
  if (ui.mode === "switch") return `<span class="sw">换谁上场？换人要用掉这一回合的出招。</span>`;
  if (ui.mode === "moves" && ui.tab === "全部") return `<span>最近用过的排在前面，往下滚是全部招式</span>`;
  return "";
}

// 舞台正中间的大字：轮到谁了。
function centerText() {
  if (!S || playing || replay) return "";
  const p = S.prompt || {};
  if (S.need === "over") return resultText(p.winner);
  if (S.need === "choose" && ui.mode === "switch" && !ui.search) return "换谁上场";
  if (S.need === "choose") return inGame() && S.choose_for && S.choose_for !== me.side ? "替对手选招" : "请选招";
  if (S.need === "pick") return "请你决定";
  if (p.mode) return "";
  if (!inGame()) return "双方正在选招…";
  const sees = (S.view && S.view.sees) || {};
  if (S.need === "wait" && !S.view.chosen[me.side] && sees[me.side]) return "你能透视：等对手先选";
  if (S.need === "wait" && S.view.control && S.view.control[me.side]) return "你被虫子控制：等对手替你选";
  return "等待对手…";
}

// 贼的框：放在舞台中间。出拳、打平再来、最后的结果都在这一个框里（结果由 stage.js 的 zeiResult 接着画）。
function zeiPanelHtml() {
  const p = (S && S.prompt) || {};
  if (!p.mode || playing || replay || S.need === "over") return "";
  const L = leftSide(), R = rightSide(), stakes = p.stakes || {}, series = p.series, rounds = p.rounds || [];
  const line = (side, cls) => (stakes[side] ? `<span class="${cls}"><b>${esc(who(side))}赢</b> → ${esc(personal(stakes[side]))}</span>` : "");
  const tie = p.mode === "single"
    ? `<span><b>打平</b> → ${esc(personal(stakes.tie || "不算赢"))}（这种贼只出一次）</span>`
    : `<span class="muted">打平就再出一次，直到分出胜负。</span>`;
  const count = series ? `<div class="series">要连赢 ${series.need} 把才算数。现在是第 ${series.index} 把。</div>` : "";
  const shown = p.choices ? `<div class="zs">${esc(who(L))}出的招是【${esc(p.choices[L].name)}】，${esc(who(R))}出的招是【${esc(p.choices[R].name)}】。</div>` : "";
  const rows = rounds.map((r) => `<div class="zr"><span>${HAND_GLYPH[r[L]]}<small>${esc(r[L])}</small></span><i>${r[L] === r[R] ? "打平" : "对"}</i><span>${HAND_GLYPH[r[R]]}<small>${esc(r[R])}</small></span></div>`).join("");
  const again = rounds.length ? `<div class="again">上一把打平了。现在出第 ${rounds.length + 1} 把。</div>` : "";
  let body;
  if (S.need === "throw") body = `${again}<div class="row hands">${HAND_NAMES.map((h) => `<button class="primary" data-hand="${h}"><span>${HAND_GLYPH[h]}</span> ${h}</button>`).join("")}</div>`;
  else if (S.need === "redo") body = `<div class="row hands"><b>这一把你输了。你有内功“重贼”，还能重来 ${p.redo_left[me.side]} 次。</b><button class="primary" data-redo="1">重贼</button><button class="small" data-redo="0">算了</button></div>`;
  else if (p.redo_side) body = `<div class="zs">${esc(who(p.redo_side))}输了，正在决定要不要用“重贼”再来一次…</div>`;
  else if (inGame()) body = `${again}<div class="zs">${p.thrown && p.thrown[me.side] ? "你已经出了，等对手出拳…" : "这一次贼不用你出拳，等结果…"}</div>`;
  else body = `${again}<div class="zs">等双方出拳…</div>`;
  return `<div class="zt">贼：${esc(personal(p.reason))}</div>${count}
    <div class="stakes">${line(L, "win")}${line(R, "lose")}${tie}</div>${shown}
    <div class="zn"><b>${esc(who(L))}</b><b>${esc(who(R))}</b></div>${rows}${body}<span class="clock" id="clock"></span>`;
}

// 倒计时。服务器每次发局面时告诉网页“每一方还剩几秒”，网页自己往下数。
function clockText() {
  if (!S || !S.timers || playing || replay) return "";
  const gone = (performance.now() - S.at) / 1000;
  const left = (side) => (S.timers[side] == null ? null : Math.max(0, Math.ceil(S.timers[side] - gone)));
  if (inGame() && S.phase === "lobby") {        // 选人物的限时
    const mine = left(me.side), theirs = left(me.side === "A" ? "B" : "A");
    if (mine != null) return `选人物还剩 ${mine} 秒，时间到了没选满的随机补齐`;
    return theirs != null ? `对手还在选，还剩 ${theirs} 秒` : "";
  }
  if (inGame()) {
    const mine = left(me.side), theirs = left(rightSide());
    if (mine != null && ["choose", "throw", "redo", "pick"].includes(S.need)) return `你还剩 ${mine} 秒`;
    return theirs != null ? `对手还剩 ${theirs} 秒` : "";
  }
  return ["A", "B"].filter((s) => left(s) != null).map((s) => `${seatName(s)}还剩 ${left(s)} 秒`).join("　");
}
function tickClock() {
  const text = clockText(), urgent = /^你还剩 \d 秒$/.test(text);
  const el = $("#clock");                       // 贼的框里的那一行
  if (el) { el.textContent = text; el.classList.toggle("urgent", urgent); }
  const ring = $("#clocknum"), sub = $("#clocksub");
  if (ring) {                                   // 舞台中间的圆环只放自己的秒数；等对手的时候在大字下面写一行“对手还剩 N 秒”
    const mine = /^你还剩 (\d+) 秒$/.exec(text);
    ring.textContent = mine ? mine[1] : "";
    ring.classList.toggle("urgent", urgent);
    if (sub) sub.textContent = mine ? "" : text;
  }
  const pick = $("#pickclock"), psub = $("#pickclocksub");
  if (pick && S && S.phase === "lobby") {        // 选人物：菱形里的倒计时
    const gone = (performance.now() - S.at) / 1000;
    const left = (side) => (S.timers && S.timers[side] != null ? Math.max(0, Math.ceil(S.timers[side] - gone)) : null);
    let num = null, note = "";
    if (!S.settings.timers) note = "不限时";
    else if (inGame()) {
      const mine = left(me.side), theirs = left(me.side === "A" ? "B" : "A");
      if (mine != null) num = mine;
      else if (theirs != null) { num = theirs; note = "对手还在选"; }
      else if (!S.my_team) note = "两个人都进来才开始计时";
    } else {
      const all = ["A", "B"].map(left).filter((x) => x != null);
      if (all.length) num = Math.max(...all);
    }
    pick.textContent = num == null ? "—" : String(num);
    pick.classList.toggle("urgent", num != null && num < 10 && !note);
    if (psub) psub.textContent = note;
  }
}
setInterval(tickClock, 250);

function category(a) {
  if (a.action_kind === "switch") return "换人";
  if (a.action_kind === "learn") return "内功";
  if (a.action_kind === "defense") return "防御";
  if (a.attributes.includes("神技")) return "神技";
  if (a.character) return "专属";
  if (a.attributes.includes("物品") || ["collect", "build", "scene"].includes(a.action_kind)) return "物品";
  return "技能";
}

// ----- 招式卡 -----

const ATTR_GLYPH = { "物理": "物", "魔法": "魔", "特技": "特", "地理": "地", "化学": "化", "生物": "生", "神技": "神", "物品": "品" };
// 属性标是深色圆盘上的亮字，所以用比 ATTR_COLOR 亮的一组颜色。
const ATTR_BRIGHT = { "物理": "#ff9a78", "魔法": "#c9a6ff", "特技": "#ffbd5c", "地理": "#6fd0ff", "化学": "#dcec62", "生物": "#84ec9a", "神技": "#ffe36e", "物品": "#d4dcf0" };
// 卡片左边的属性圆：深色圆盘上的亮字。神技的招写“神”；有两种属性的招，圆盘的圈用第二种属性的颜色。
function badgeLook(attrs, kind) {
  if (kind === "防御") return null;
  if (!attrs.length) return ["", kind === "内功" ? "功" : kind === "换人" ? "换" : "无"];
  if (attrs.length >= 8) return ["--a:#ffffff", "全"];
  const main = attrs.includes("神技") ? "神技" : attrs[0], second = attrs.find((x) => x !== main);
  return [`--a:${ATTR_BRIGHT[main] || "#d4dcf0"}${second ? ";--ring:" + (ATTR_BRIGHT[second] || "#d4dcf0") : ""}`, ATTR_GLYPH[main] || "？"];
}
function badgeHtml(a) {
  const kind = category(a);
  if (kind === "防御") {
    const code = DEF_OF_ACTION[a.id], file = DEF_ICON[code];
    return file && DEF_ART.has(file) ? `<span class="badge"><img alt="" src="assets/defense/${file}.png"></span>` : `<span class="badge">防</span>`;
  }
  const [style, glyph] = badgeLook(a.attributes || [], kind);
  return `<span class="badge"${style ? ` style="${style}"` : ""}>${glyph}</span>`;
}
// 用什么能防住这一招：有手绘图标就画图标，再写名字。
function defenseName(code) {
  const file = DEF_ICON[code];
  return (file && DEF_ART.has(file) ? `<img alt="" src="assets/defense/${file}.png">` : "") + esc(DEF_NAME[code] || "");
}
function defenseCell(a) {
  const hitsFoe = a.target === "enemy" || a.effect === "self_status_and_damage";
  if (a.action_kind !== "skill" || !hitsFoe) return "—";
  if (a.defense == null) return "防不住";
  return defenseName(a.defense);
}
const mvRow = (label, value) => `<span class="mvrow"><span>${label}</span><b>${value}</b></span>`;
// 一张技能卡（设计稿“技能卡和说明框”）：上面招式名，左边属性圆，右边两行小格。
// 样子：可以出；鼠标停着更亮（CSS 管）；已选中是金边加“已选”；现在出不了是灰蓝，第二行写原因。不是你选招的时候整排变暗（#tray.idle）。
function cardShell(cls, attrs, inside) {
  return `<button class="mv ${cls}" ${attrs}><span class="edge" aria-hidden="true"></span><span class="fill">${inside}</span></button>`;
}
function cardHtml(a, q, first) {
  const self = ui.aim === "self", idle = !choosing();
  const ok = !idle && (self ? a.self_ok : a.legal), why = self ? a.self_reason : a.reason;
  const picked = idle && !!ui.myPick && ui.myPick === a.id;
  const name = q && a.name.includes(q) ? esc(a.name).split(esc(q)).join(`<mark>${esc(q)}</mark>`) : esc(a.name);
  let row1, row2;
  if (a.action_kind === "learn") {
    row1 = mvRow("现在", a.level + " 级"); row2 = mvRow("学了", a.progress + (a.next ? " / " + a.next : "") + " 下");
  } else if (a.action_kind === "defense") {
    row1 = mvRow("防御", "挡同一类的招"); row2 = "";
  } else if (category(a) === "物品" && !a.damage) {      // 物品：写现在手里有几个
    const res = a.action_kind === "collect" ? a.name.replace(/^收集/, "") : null;
    const side = (inGame() && S.choose_for) || leftSide(), p = S.view.players[side], f = p.team[p.active] || {};
    row1 = res && f.resources && res in f.resources ? mvRow("现有", f.resources[res] + " 个") : mvRow("物品", a.action_kind === "build" ? "造一下" : "用一次");
    row2 = a.target === "enemy" ? mvRow("防御", defenseCell(a)) : "";
  } else {
    const st = (a.statuses || [])[0];
    row1 = a.damage ? mvRow("威力", wan(a.damage)) : st ? mvRow("特效", esc(st[0]) + " " + st[1] + " 回合") : mvRow("威力", "—");
    row2 = mvRow("防御", defenseCell(a));
  }
  // 现在用不了的招：第二行换成用不了的原因
  const rows = !idle && !ok && why ? row1 + `<span class="mvwhy">${esc(personal(why))}</span>` : row1 + row2;
  const look = picked ? "picked" : !idle && !ok ? "off" : "";
  return cardShell(`${look} ${idle ? "idle" : ""} ${first && ok ? "first" : ""}`,
    `data-action="${esc(a.id)}" data-tip="act:${esc(a.id)}" aria-disabled="${ok ? "false" : "true"}"`,
    `<span class="mvname">${name}</span>${badgeHtml(a)}${rows}${picked ? `<span class="tag">已选</span>` : ""}`);
}

// 搜索：汉字或拼音首字母。数字越小越靠前，-1 是没搜到。
function pyOf(a) {
  if (a.action_kind === "learn") return "x" + ((codexIndex.inner[a.inner] || {}).py || "");
  if (a.action_kind === "switch") return "hs" + ((codexIndex.char[a.name.replace(/^换上/, "")] || {}).py || "").split(" ")[0];
  return (codexIndex.skill[a.id] || {}).py || "";
}
function searchRank(name, py, q) {
  const k = q.toLowerCase(), list = String(py || "").split(" ").filter(Boolean);
  if (name.startsWith(q)) return 0;
  if (list.some((p) => p.startsWith(k))) return 1;
  if (name.includes(q)) return 2;
  if (list.some((p) => p.includes(k))) return 3;
  return -1;
}
const recentIds = () => { try { return JSON.parse(store.get("shai-recent") || "[]"); } catch (e) { return []; } };
function remember(id) {
  if (id.startsWith("switch:")) return;         // 换人按位置编号，换一局就不对了，不记
  store.set("shai-recent", JSON.stringify([id].concat(recentIds().filter((x) => x !== id)).slice(0, 8)));
}

// 换人卡（设计稿“换人”）：点“换人”的时候下面中间换成这一排。头像、名字、血条、所在场景、状态标签。
// 三种样子：出战中（灰蓝）、可以换上（蓝，鼠标停着更亮）、已倒下（暗灰）。
function teamHtml() {
  const side = (inGame() && S.choose_for) || leftSide(), p = S.view.players[side], can = choosing();
  const shown = p.team.map((f, i) => [f, i]).filter(([f]) => !f.hidden && !(f.is_true_body && !f.entered));
  ui.teamCount = shown.length;
  return shown.map(([f, i]) => {
    const act = (S.actions || []).find((a) => a.id === "switch:" + i);
    const active = i === p.active, ok = can && !!act && act.legal;
    const state = active ? "now" : f.defeated ? "down" : can && !ok ? "off" : "can";
    const tag = { now: chipHtml("出战中"), down: chipHtml("已倒下", "bad"), off: chipHtml("现在换不了"), can: chipHtml("可以换上", "good") }[state];
    const place = f.defeated ? "这个人物已经没有命了" : !f.entered ? "还没上过场" : `${f.scene} · 高度 ${f.height}`;
    const chips = Object.entries(f.statuses || {}).map(([n, s]) => chipHtml(`${n} ${s.turns} 回合`, GOOD_STATUS.includes(n) ? "good" : "bad"))
      .concat(Object.entries(f.parasites || {}).map(([n, x]) => chipHtml(`${n}×${x.count}`, "bad")))
      .concat(Object.entries(f.inner || {}).filter(([, v]) => v > 0).map(([k, v]) => chipHtml(`${k} ${v} 级`, "inner")))
      .concat(Object.entries(f.resources || {}).filter(([, v]) => v > 0).map(([k, v]) => chipHtml(`${k} ${v}`))).join("");
    const lives = f.lives_total > 1 ? `<span class="lives">${"●".repeat(Math.max(0, f.lives_remaining))}${"○".repeat(Math.max(0, f.lives_total - f.lives_remaining))}</span>` : "";
    return `<button class="tm ${state}" ${ok ? `data-action="switch:${i}"` : ""} data-tip="soul:${esc(f.name)}" aria-disabled="${ok ? "false" : "true"}" aria-label="换上${esc(f.name)}">
      <span class="edge" aria-hidden="true"></span><span class="fill"><span class="face ${f.defeated ? "dim" : ""}">${faceHtml(f.name)}</span>
      <span class="tmbody"><span class="tmhead"><b>${esc(f.name)}</b>${tag}${lives}</span>${barHtml(f.hp, f.max_hp, { kind: f.hp * 4 < f.max_hp ? "low" : "hp" })}
      <span class="tmwhere">${esc(place)}</span><span class="chips">${chips}</span></span></span></button>`;
  }).join("");
}

function actionsHtml() {
  const all = (choosing() ? S.actions : ui.lastActions) || [];
  if (!all.length && ui.mode !== "switch") return "";
  const self = ui.aim === "self", q = ui.search;
  const list = all.filter((a) => !self || a.self_ok != null);       // 打自己的时候只列能对自己用的招
  const usable = (a) => choosing() && (self ? a.self_ok : a.legal);
  // first：搜索的时候，按回车会出的那一张（第一张能用的）亮起来
  const cards = (items, empty, highlight) => {
    const firstOk = highlight ? items.findIndex(usable) : -1;
    return items.map((a, i) => cardHtml(a, q, i === firstOk)).join("") || `<span class="muted">${empty}</span>`;
  };
  if (q) {
    const hits = list.map((a) => [searchRank(a.name, pyOf(a), q), a]).filter(([r]) => r >= 0).sort((x, y) => x[0] - y[0]).map(([, a]) => a);
    ui.hits = hits.length;
    return cards(hits, "没有叫这个名字的招。", true);
  }
  if (ui.mode === "switch") return teamHtml() || `<span class="muted">没有能换上的人物。</span>`;
  if (ui.mode === "items") return cards(list.filter((a) => category(a) === "物品"), self ? "没有能对自己用的物品。" : "现在没有能用的物品。");
  const moves = list.filter((a) => !["防御", "换人", "物品"].includes(category(a)));
  if (ui.tab !== "全部") return cards(moves.filter((a) => category(a) === ui.tab), "这一类里没有招。");
  // “全部”：最近用过的排在前面，后面接着全部招式
  const recent = recentIds().map((id) => list.find((a) => a.id === id)).filter(Boolean).slice(0, 4), seen = new Set(recent.map((a) => a.id));
  return cards(recent.concat(moves.filter((a) => !seen.has(a.id))), "这一类里没有招。");
}

// 搜索框下面的一排防御：用得最多，随时一点就出。
function defenseRowHtml() {
  const all = (choosing() ? S.actions : ui.lastActions) || [], idle = !choosing();
  return ["d1", "d2", "d3", "d4", "dj", "ds"].map((id) => {
    const a = all.find((x) => x.id === id); if (!a) return "";
    const ok = !idle && a.legal, code = DEF_OF_ACTION[id], file = DEF_ICON[code];
    const inside = file && DEF_ART.has(file) ? `<img alt="" src="assets/defense/${file}.png">` : esc(DEF_NAME[code].replace("防御", "防"));
    return `<button class="def ${ok ? "" : "off"}" data-action="${id}" data-tip="act:${id}" aria-disabled="${ok ? "false" : "true"}" aria-label="${esc(DEF_NAME[code])}">${inside}<small>${esc(DEF_NAME[code].replace("防御", "防"))}</small></button>`;
  }).join("");
}

function appendLog(text) {
  const shown = personal(text), cls = /^第\d+回合：/.test(text) ? "round" : text.startsWith("贼（") ? "zei" : "";
  const log = $("#log");
  if (log) {
    const p = document.createElement("p");
    p.className = cls; p.textContent = shown;
    log.appendChild(p); log.scrollTop = log.scrollHeight;
  }
  ui.feed = (ui.feed || []).concat([shown]).slice(-3);
  const feed = $("#feed");
  if (feed) feed.innerHTML = ui.feed.map((line) => `<span>${esc(line)}</span>`).join("");
}

// 舞台上方正中：两边在哪一层、第几回合、各剩几个人。
function topHtml() {
  const v = S.view, L = leftSide(), R = rightSide();
  if (replay) return `<div class="vs"><span class="me">${esc(replay.names.A)}</span><span>对</span><span class="foe">${esc(replay.names.B)}</span></div>
    <div class="rnd"><b>回放</b><span>${when(replay.ended_at)}</span><span>共 ${replay.rounds} 回合</span></div>`;
  const now = (side) => (stage && stage.model && stage.model[side]) || v.players[side].team[v.players[side].active] || {};
  const a = now(L), b = now(R);
  const alive = (side) => v.players[side].team.filter((f) => !f.defeated && !(f.is_true_body && !f.entered)).length;
  const water = v.water_level < 0 ? "" : `<span>水面高度 ${v.water_level}</span>`;
  const watchers = S.watchers.length ? `<span>观战：${esc(S.watchers.join("、"))}</span>` : "";
  // 两边所在的场景，中间两组箭头：自己的橙色朝右，对手的蓝色朝左
  const chev = (color, flip) => `<svg aria-hidden="true" width="46" height="22" viewBox="0 0 46 22" fill="${color}"${flip ? ' style="transform: scaleX(-1)"' : ""}>`
    + [[0, ".35"], [14, ".65"], [28, "1"]].map(([x, o]) => `<path d="M${x} 1 h7 l9 10 l-9 10 h-7 l9 -10 z" opacity="${o}"></path>`).join("") + "</svg>";
  return `<div class="vs"><span class="me" data-tip="scene:${esc(a.scene || "")}">${esc(a.scene || "")}</span>${chev("#ffb060")}${chev("#8cc0ff", true)}<span class="foe" data-tip="scene:${esc(b.scene || "")}">${esc(b.scene || "")}</span></div>
    <div class="rnd"><span>${alive(L)} 人</span><b>第 ${v.round} 回合</b><span>${alive(R)} 人</span></div>
    <div class="csub"><span>房间 ${esc(S.room)}</span>${water}${inGame() ? "" : "<span>你在观战</span>"}${watchers}</div>`;
}
// 舞台右边的一列小圆钮：动画速度、声音、战报和聊天、退出。
function sideHtml() {
  const unread = replay ? 0 : Math.max(0, ((S.chat || []).filter((c) => c.who !== "sys").length) - (ui.chatSeen || 0));
  const mine = inGame() && S.view.zei_enabled ? S.seats[me.side] : null;
  const auto = mine ? `<button id="autozei" aria-pressed="${!!mine.auto_zei}" title="贼的时候电脑替我出拳：现在${mine.auto_zei ? "开着" : "关着"}">代贼</button>` : "";
  return `<button id="speed" title="动画速度">${stage && stage.speed > 1 ? "×2" : "×1"}</button>${auto}
    <button id="mute" title="声音">${Sfx.muted ? "静音" : "有声"}</button>
    ${BACKDROPS.length ? `<button id="nextbg" title="换一张背景">背景</button>` : ""}
    <button id="openlog" title="战报和聊天">战报${unread ? `<span class="dot">${unread}</span>` : ""}</button>
    <button id="back" title="${inGame() ? "退出" : "离开"}">${inGame() ? "退出" : "离开"}</button>`;
}

// 背景图：放在本机 web/assets/backgrounds/ 里的图片（不进仓库）。没有图就用画出来的深蓝擂台。
// 没选过的时候用第一张（设计稿用的就是第一张“夜色鸟居”）；选过“不要背景图”就是空字符串。
let BACKDROPS = [];
function currentBackdrop() {
  const saved = store.get("shai-backdrop");
  if (saved === null || saved === undefined) return BACKDROPS[0] || "";
  return BACKDROPS.includes(saved) ? saved : "";
}
function applyBackdrop() {
  const el = $("#backdrop"), battle = $("#battle"); if (!el || !battle) return;
  const name = currentBackdrop();
  el.style.backgroundImage = name ? `url("assets/backgrounds/${encodeURIComponent(name)}")` : "";
  battle.classList.toggle("has-photo", !!name);
}
function nextBackdrop() {
  const list = [""].concat(BACKDROPS), now = list.indexOf(currentBackdrop());
  store.set("shai-backdrop", list[(now + 1) % list.length]);
  applyBackdrop();
}

const TRAY_TABS = ["全部", "技能", "神技", "专属", "内功"];
const MODES = [["moves", "战斗"], ["items", "物品"], ["switch", "换人"], ["codex", "图鉴"]];

function renderControls() {
  if (!$("#battle") || !S || S.phase === "lobby") return;
  $("#top").innerHTML = topHtml();
  $("#side").innerHTML = sideHtml();
  const box = $("#stage .zeibox");
  if (box && !playing) {                       // 播放的时候这个框归舞台管（它要在里面亮出贼的结果）
    const html = zeiPanelHtml();
    if (html) { box.innerHTML = html; box.hidden = false; } else { box.hidden = true; box.innerHTML = ""; }
  }
  const can = choosing();
  if (can && !ui.wasChoosing) ui.myPick = null;       // 新的一回合：上一回合选的招不再标“已选”
  if (can) ui.lastActions = S.actions;
  else ui.sceneAction = null;
  // 正中间：轮到你的时候是圆环倒计时加一行字；等对手、对战结束的时候是一行大字
  const text = centerText(), center = $("#center"), waiting = !can && S.need !== "pick";
  center.hidden = playing || (box && !box.hidden) || !text;
  center.className = waiting ? "wait" : "";
  $("#ctext").textContent = text;
  $("#cwait").hidden = !waiting || S.need === "over";
  tickClock();
  const team = can && ui.mode === "switch" && !ui.search;
  $("#tray").classList.toggle("idle", !can);
  $("#tray").classList.toggle("switching", team);
  const proxy = inGame() && S.choose_for && S.choose_for !== me.side;       // 正在替被控制的对手选招
  $("#aim").innerHTML = `<span>这一招打</span><button class="pill" data-aim="foe" aria-pressed="${ui.aim === "foe"}">${proxy ? "你" : "对手"}</button><button class="pill" data-aim="self" aria-pressed="${ui.aim === "self"}">${proxy ? "他自己" : "自己"}</button>
    ${ui.aim === "self" ? `<span class="warn">打自己：不用躲，够不着也能用，伤害和特效都落在自己身上。</span>` : ""}`;
  $("#defrow").innerHTML = defenseRowHtml();
  $("#scenepick").innerHTML = ui.sceneAction ? `<b>去哪个场景？</b>${scenes.map((s) => `<button class="pill" data-scene="${esc(s.name)}">${esc(s.name)}</button>`).join("")}<button class="pill">取消</button>` : "";
  $("#tabs").innerHTML = ui.mode === "moves" && !ui.search && !ui.sceneAction
    ? TRAY_TABS.map((t) => `<button class="pill" data-tab="${t}" aria-pressed="${t === ui.tab}">${t}</button>`).join("") : "";
  $("#modes").innerHTML = MODES.map(([id, name]) => `<button class="big" data-mode="${id}" aria-pressed="${id === ui.mode && !ui.search}"><span class="edge" aria-hidden="true"></span><span class="fill">${name}</span></button>`).join("");
  const actions = $("#actions");
  actions.innerHTML = actionsHtml();
  actions.className = ui.mode === "switch" && !ui.search ? "team" + ((ui.teamCount || 0) > 3 ? " many" : "") : "";
  $("#prompt").innerHTML = promptHtml() || hintHtml();
  renderExtras();
  renderChat();
  refreshTip();
  if (can && !ui.wasChoosing && !/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || "")) $("#search").focus({ preventScroll: true });
  ui.wasChoosing = can;
}

// 把还没播过的事件一条一条播出来：战报文字直接追加，其它的交给舞台做动画。
async function pump() {
  if (playing || !stage) return;
  playing = true; renderControls();
  const mine = run, box = $("#stage .zeibox");
  if (box && !box.hidden) {                    // 刚出完拳：接下来要是贼的结果，框留着接着用；不是就收起来
    const next = events.slice(played).find((e) => e.t !== "log");
    if (next && next.t === "zei") box.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    else { box.hidden = true; box.innerHTML = ""; }
  }
  while (stage && mine === run && played < events.length) {
    const ev = events[played++];
    if (ev.t === "log") appendLog(ev.text);
    else {
      try { await stage.play(ev, S.view); } catch (error) { console.error("这条事件没播出来", ev, error); }
    }
  }
  if (mine !== run) return;                   // 中途换了一局（比如点了“再放一遍”）：这一轮播放作废
  playing = false;
  if (replay) replayDone = true;
  if (stage && S && S.view) {
    stage.clearBand();
    stage.skipping = false;
    if (!S.paused) stage.setModel(modelOf(S.view));   // 播完以后和服务器的局面对齐；停在半路时以已播的事件为准
  }
  renderControls();
}

// 退出：回到干净的入口页，可以新开房间。上场的人的座位还留着：入口页会写出刚才的房间号，输入它可以回去接着打。
function leave() {
  if (inGame() && S && S.need !== "over") seatStore.set("shai-last-room", me.room);
  location.hash = "";
  location.reload();
}

function chooseAction(id) {
  const action = (S.actions || []).find((a) => a.id === id);
  if (!action || !choosing()) return;
  if (action.effect === "choose_scene") { ui.sceneAction = id; renderControls(); return; }
  send({ t: "choose", action: id, on_self: ui.aim === "self", for: S.choose_for });
  ui.myPick = id;                               // 等对手的时候这张卡标“已选”
  remember(id);
  ui.aim = "foe"; ui.search = ""; $("#search").value = "";
  hideTip();
}

function toggleDrawer(open) {
  const drawer = $("#drawer"); if (!drawer) return;
  drawer.hidden = open === undefined ? !drawer.hidden : !open;
  if (!drawer.hidden) {
    ui.chatSeen = (S.chat || []).filter((c) => c.who !== "sys").length;
    const log = $("#log"); log.scrollTop = log.scrollHeight;
  }
  renderControls();
}

function renderBattle() {
  if (!$("#battle")) {
    document.body.classList.add("battle");
    // 整屏是背景图，上面一块 1600×900 的画面（设计稿“对战”那几张的布局）
    $("#app").innerHTML = `<div id="battle" class="screen">
      <div class="backdrop" id="backdrop"></div><div class="shadeb"></div>
      <div class="frame">
        <div class="floor"><i></i></div>
        <div id="stage"></div>
        <div id="top"></div>
        <div id="center" hidden><b class="cring" id="clocknum"></b><span class="ctext" id="ctext"></span>
          <span class="cwait" id="cwait">WAITING<svg aria-hidden="true" width="22" height="12" viewBox="0 0 22 12"><path d="M0 0 L9 6 L0 12 Z M11 0 L20 6 L11 12 Z"></path></svg></span><span class="csec" id="clocksub"></span></div>
        <div id="side"></div>
        <button id="feed" title="点开看全部战报"></button>
        <div id="tray">
          <div id="trayleft">
            <div class="searchbox">
              <input type="text" id="search" class="oct" placeholder="搜招式，可打拼音首字母" autocomplete="off" spellcheck="false" aria-label="搜招式">
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#cfe2ff" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.8-3.8"></path></svg>
            </div>
            <div class="defrow" id="defrow"></div>
            <div class="aim" id="aim"></div>
          </div>
          <div id="traymid"><div id="trayhead"><div id="scenepick"></div><div id="tabs"></div><div id="prompt"></div></div><div id="actions"></div></div>
          <div id="modes"></div>
        </div>
        <div id="drawer" hidden>
          <div class="row"><h2>战报</h2><span class="row"><button class="small" id="copylog">复制战报</button><button class="small" id="closedrawer">关闭</button></span></div>
          <div class="log" id="log"></div>
          ${replay ? "<span></span><span></span><span></span>" : `<h2>聊天</h2>${chatBoxHtml()}`}
        </div>
      </div></div>`;
    const search = $("#search");
    search.oninput = () => { ui.search = search.value.trim(); renderControls(); };
    search.onkeydown = (ev) => {
      if (ev.key === "Enter") { const first = $('#actions [data-action][aria-disabled="false"]'); if (first) chooseAction(first.dataset.action); }
      else if (ev.key === "Escape") { search.value = ""; ui.search = ""; renderControls(); }
    };
    $("#tray").onclick = (ev) => {
      const b = ev.target.closest("button"); if (!b) return;
      if (b.dataset.action) { if (b.getAttribute("aria-disabled") !== "true") chooseAction(b.dataset.action); return; }
      if (b.dataset.tab) ui.tab = b.dataset.tab;
      else if (b.dataset.aim) ui.aim = b.dataset.aim;
      else if (b.dataset.mode === "codex") return openCodex();
      else if (b.dataset.mode) { ui.mode = b.dataset.mode; ui.search = ""; $("#search").value = ""; }
      else if (b.closest("#scenepick")) {
        if (b.dataset.scene) send({ t: "choose", action: ui.sceneAction, destination: b.dataset.scene });
        ui.sceneAction = null;
      } else if (b.dataset.pick) return send({ t: "pick", option: b.dataset.pick });
      else if (b.id === "rematch") return send({ t: "rematch" });
      else if (b.id === "skip") { if (stage) stage.skipping = true; return; }
      else if (b.id === "again") return startReplay();
      else if (b.id === "back") return leave();
      else if (b.dataset.log) return showSavedLog(b.dataset.log);
      else return;
      renderControls();
    };
    $("#stage").onclick = (ev) => {             // 贼的框在舞台里：出拳、重贼的按钮在这里接；点人物或头像看详情
      const detail = ev.target.closest("[data-detail]");
      if (detail) return showDetail(detail.dataset.detail);
      const b = ev.target.closest("button"); if (!b || b.disabled) return;
      if (b.dataset.hand) send({ t: "throw", hand: b.dataset.hand });
      else if (b.dataset.redo) send({ t: "redo", yes: b.dataset.redo === "1" });
    };
    $("#side").onclick = (ev) => {
      const b = ev.target.closest("button"); if (!b) return;
      if (b.id === "speed" && stage) { stage.speed = stage.speed > 1 ? 1 : 2.2; store.set("shai-speed", String(stage.speed)); renderControls(); }
      if (b.id === "mute") { Sfx.muted = !Sfx.muted; store.set("shai-mute", Sfx.muted ? "1" : ""); renderControls(); }
      if (b.id === "autozei") send({ t: "auto", on: b.getAttribute("aria-pressed") !== "true" });
      if (b.id === "nextbg") nextBackdrop();
      if (b.id === "openlog") toggleDrawer();
      if (b.id === "back") leave();
    };
    $("#feed").onclick = () => toggleDrawer(true);
    applyBackdrop();
    $("#closedrawer").onclick = () => toggleDrawer(false);
    $("#copylog").onclick = () => showText("这一局到现在的战报", events.filter((e) => e.t === "log").map((e) => e.text).join("\n"));
    bindChat();
  }
  if (!stage) {
    stage = new Stage($("#stage"), leftSide(), scenes);
    if (!inGame()) stage.labels = { A: "A · " + seatName("A"), B: "B · " + seatName("B") };
    stage.speed = Number(store.get("shai-speed")) > 1 ? 2.2 : 1;
    Sfx.muted = store.get("shai-mute") === "1";
    stage.setModel(modelOf(replay ? replay.start_view : S.view));
    $("#log").innerHTML = ""; ui.feed = []; $("#feed").innerHTML = "";
    played = 0;
    if (!replay && events.length > 14) {      // 中途进来（比如刷新页面、半路来观战）：之前的回合不重播，只把战报补上
      for (const ev of events) if (ev.t === "log") appendLog(ev.text);
      played = events.length;
    }
  }
  renderControls();
  pump();
}

// ---------- 人物详情：点人物或头像弹出来 ----------

function closeModal() { const m = $("#modal"); if (m) m.remove(); hideTip(); }
function openModal(title, body, cls) {
  closeModal();
  const m = document.createElement("div");
  m.id = "modal"; m.className = "modal";
  // 蓝色窗口，上面一条浅一点的标题栏，右上角是关掉的叉。窗口外面点一下也关掉。
  m.innerHTML = `<div class="frame"><div class="window ${cls || ""}" role="dialog" aria-label="${esc(title)}">
    <div class="whead"><b>${esc(title)}</b><button class="x" aria-label="关掉">${X_ICON}</button></div><div class="wbody">${body}</div></div></div>`;
  // （只看点的是不是窗口外面那一层：窗口里的内容点了以后可能整个重画，点的那个东西已经不在页面上了）
  m.addEventListener("click", (ev) => { if (ev.target === m || ev.target === m.firstElementChild || ev.target.closest(".x")) closeModal(); });
  document.body.appendChild(m);
  return m;
}
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeModal(); });

// key：“A”这种是场上的人物；“A:2”是这一方的第 3 个人物。
function showDetail(key) {
  if (!S || !S.view) return;
  const [side, index] = key.split(":"), p = S.view.players[side]; if (!p) return;
  const live = index === undefined && stage && stage.model && stage.model[side];       // 场上的人物以舞台上正显示的为准
  const f = live || p.team[index === undefined ? p.active : +index];
  if (!f || f.hidden) return;
  const card = codexIndex.char[f.name] || { lines: [] };
  const lent = new Set(f.borrowed || []), learned = new Set(f.learned || []);
  const none = (text) => `<p class="none">${text}</p>`;
  const inner = Object.entries(f.inner || {}).filter(([, v]) => v > 0).map(([k, v]) => {
    const c = codexIndex.inner[k], line = c && c.lines[v - 1] ? c.lines[v - 1][1].replace(/^\d 级：/, "") : "";
    return `<p><span class="iname">${esc(k)} ${v} 级${lent.has(k) ? "（借对手的）" : learned.has(k) ? "（学的）" : ""}${innerOff(f, k)}</span><br>${esc(line)}</p>`;
  }).join("") || none("没有");
  const st = Object.entries(f.statuses || {}).map(([n, s]) => `<p><span class="${GOOD_STATUS.includes(n) ? "gname" : "sname"}">${esc(n)}，还剩 ${s.turns} 回合</span><br>${esc((codexIndex.status[n] || {}).text || "")}</p>`).join("") || none("没有");
  const bugs = Object.entries(f.parasites || {}).map(([n, x]) => `<p><span class="sname">${esc(n)} ×${x.count}</span><br>${esc((codexIndex.parasite[n] || {}).text || "")}</p>`).join("") || none("没有");
  const owner = inGame() ? (side === me.side ? "你" : "对手") : seatName(side);
  const pair = (k, v) => `<div><span>${esc(k)}</span><span>${esc(v)}</span></div>`;
  const pairs = [pair("名字", f.name), pair("属于", owner), pair("体力", `${f.hp} / ${f.max_hp}`)]
    .concat(f.max_shield ? [pair("盾牌", `${f.shield} / ${f.max_shield}`)] : [])
    .concat([pair("命", `还有 ${f.lives_remaining} 条，一共 ${f.lives_total} 条`), pair("在哪", `${f.scene} · 高度 ${f.height}`)])
    .concat(f.radiation ? [pair("累计辐射", `${f.radiation} / 15`)] : [])
    .concat(Object.entries(f.resources || {}).filter(([, v]) => v > 0).map(([k, v]) => pair(k, v + " 个"))).join("");
  // 右边两个页签：魂印、专属的招
  const own = CODEX ? CODEX.skills.filter((s) => s.character === f.name) : [];
  const panes = {
    soul: `<div class="strip">${esc(f.name)}</div><div class="dtext scroll">${tipLines(card.lines)}</div>`,
    moves: `<div class="strip">${esc(f.name)}的专属的招<small>${own.length ? own.length + " 个" : ""}</small></div><div class="dtext scroll">${own.map((s) =>
      `<div class="exm">${tipHead(s.name, s.tag)}${tipLines(s.lines)}</div>`).join("") || `<span>没有专属的招。</span>`}</div>`,
  };
  const body = `<div class="dtop"><span class="face">${faceHtml(f.name)}</span><div class="dbase"><div class="bartitle">基础信息</div><div class="pairs">${pairs}</div></div></div>
    <div class="dleft scroll"><div class="bartitle">内功</div><div class="dsecbody">${inner}</div>
      <div class="bartitle">身上的状态</div><div class="dsecbody">${st}</div>
      <div class="bartitle">身上的虫子</div><div class="dsecbody">${bugs}</div></div>
    <div class="dright"><div class="tabs2"><button class="wtab" data-dtab="soul" aria-pressed="true">魂印</button><button class="wtab" data-dtab="moves" aria-pressed="false">专属的招</button></div>
      <div class="dpane">${panes.soul}</div></div>`;
  const m = openModal("人物详情", body, "dwin");
  m.addEventListener("click", (ev) => {
    const b = ev.target.closest && ev.target.closest("[data-dtab]"); if (!b) return;
    $(".dpane", m).innerHTML = panes[b.dataset.dtab];
    m.querySelectorAll("[data-dtab]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
}

// ---------- 图鉴：全部招式、人物、内功、状态、场景 ----------

const CODEX_TABS = ["招式", "人物", "内功", "状态和虫子", "场景"];
const CODEX_KINDS = ["全部", "技能", "神技", "专属"];
const cx = { tab: "招式", q: "", key: null, kind: "全部" };
function codexItems(tab) {
  if (!CODEX) return [];
  if (tab === "招式") return CODEX.skills.map((s) => ({ key: s.id, name: s.name, py: s.py, group: s.kind, tag: s.tag, lines: s.lines, skill: s }));
  if (tab === "人物") return CODEX.characters.map((c) => ({ key: c.name, name: c.name, py: c.py, group: c.group, tag: "魂印", lines: c.lines }));
  if (tab === "内功") return CODEX.inner.map((c) => ({ key: c.name, name: c.name, py: c.py, group: "内功", tag: "内功", lines: c.lines }));
  if (tab === "场景") return CODEX.scenes.map((c) => ({ key: c.name, name: c.name, py: "", group: "场景（从高到低）", tag: "场景", lines: c.lines }));
  return CODEX.statuses.slice().sort((a, b) => Number(!!a.good) - Number(!!b.good)).map((c) => ({ key: "s:" + c.name, name: c.name, py: "", group: c.good ? "好状态" : "不良状态", tag: c.good ? "好状态" : "不良状态", lines: [["text", c.text]] }))
    .concat(CODEX.parasites.map((c) => ({ key: "p:" + c.name, name: c.name, py: "", group: "虫子", tag: "虫子", lines: [["text", c.text]] })));
}
// 图鉴里的一张招式卡：和对战时的技能卡一个样子。第一行是威力，没有威力的招写它的特效；第二行是用哪个防御能防住。
function codexCardHtml(it, on) {
  const s = it.skill;
  let row1 = mvRow("威力", s.damage ? wan(s.damage) : "—");
  if (!s.damage) {
    for (const [style, text] of s.lines) {
      const m = style === "text" && /【(.+?)】(\d+) 回合/.exec(text);
      if (m) { row1 = mvRow("特效", `${esc(m[1])} ${m[2]} 回合`); break; }
    }
  }
  const row2 = mvRow("防御", s.defense != null ? defenseName(s.defense) : s.damage ? "防不住" : "—");
  const [style, glyph] = badgeLook(s.kind === "神技" ? ["神技"] : (s.attributes || []), s.kind) || ["", "防"];
  const badge = s.kind === "防御" ? badgeHtml({ id: { 防御1: "d1", 防御2: "d2", 防御3: "d3", 防御4: "d4", 平面镜: "dj", 憋神技: "ds" }[s.name], action_kind: "defense", attributes: [] })
    : `<span class="badge"${style ? ` style="${style}"` : ""}>${glyph}</span>`;
  return cardShell(on ? "picked" : "", `data-cx="${esc(it.key)}" aria-pressed="${on}"`, `<span class="mvname">${esc(it.name)}</span>${badge}${row1}${row2}`);
}
function codexHtml() {
  let items = codexItems(cx.tab);
  if (cx.tab === "招式" && cx.kind !== "全部") items = items.filter((it) => it.group === cx.kind);
  if (cx.q) items = items.map((it) => [searchRank(it.name, it.py, cx.q), it]).filter(([r]) => r >= 0).sort((a, b) => a[0] - b[0]).map(([, it]) => it);
  const picked = items.find((it) => it.key === cx.key) || items[0];
  const on = (it) => !!picked && it.key === picked.key;
  // 左边的格子：招式是技能卡；人物是方头像加名字条；别的是只写名字的小卡。不搜的时候按类分开写小标题。
  let last = null, cls = "";
  const head = (it) => { const h = !cx.q && cx.tab !== "招式" && it.group !== last ? `<div class="grp">${esc(it.group)}</div>` : ""; last = it.group; return h; };
  const cell = (it) => {
    if (cx.tab === "招式") return codexCardHtml(it, on(it));
    if (cx.tab === "人物") {
      return `<button class="pc" data-cx="${esc(it.key)}" aria-pressed="${on(it)}"><span class="art">${ART.has(it.name) ? `<img alt="" src="assets/characters/${encodeURIComponent(it.name)}.png">` : esc(it.name.slice(0, 1))}</span><span class="pn">${esc(it.name)}</span></button>`;
    }
    return cardShell(`plain ${on(it) ? "picked" : ""}`, `data-cx="${esc(it.key)}" aria-pressed="${on(it)}"`, `<span class="mvname">${esc(it.name)}</span><small>${esc(it.tag)}</small>`);
  };
  if (cx.tab === "人物") cls = "people";
  const grid = items.map((it) => head(it) + cell(it)).join("") || `<span class="muted">没有搜到。</span>`;
  const chips = picked ? (picked.skill ? chipHtml(picked.skill.kind) + chipHtml(picked.tag, "inner") : chipHtml(picked.group)) : "";
  const detail = picked ? `<div class="cxhead"><b class="cxname">${esc(picked.name)}</b>${chips}</div><div class="dtext scroll">${tipLines(picked.lines)}</div>`
    : `<div class="cxhead"><b class="cxname">没有搜到</b></div>`;
  const kinds = cx.tab === "招式" ? CODEX_KINDS.map((k) => `<button class="pill" data-cxkind="${k}" aria-pressed="${k === cx.kind}">${k}</button>`).join("") : "";
  return `<div class="cxtabs">${CODEX_TABS.map((t) => `<button class="wtab" data-cxtab="${t}" aria-pressed="${t === cx.tab}">${t}</button>`).join("")}</div>
    <div class="cxtools"><input class="field" type="text" id="cxq" placeholder="搜名字，可打拼音首字母" value="${esc(cx.q)}" autocomplete="off" spellcheck="false" aria-label="搜图鉴">${kinds}</div>
    <div class="cxgrid scroll ${cls}">${grid}</div>
    <div class="cxdetail">${detail}</div>`;
}
function openCodex() {
  if (!CODEX) return toast("图鉴的文字还没读到，稍等一下再点。");
  const m = openModal("图鉴", codexHtml(), "cwin"), body = $(".wbody", m);
  // 点一张卡只换右边的说明：左边的格子滚到哪儿还停在哪儿
  const redraw = (focus, keep) => {
    const top = keep && $(".cxgrid", m) ? $(".cxgrid", m).scrollTop : 0;
    body.innerHTML = codexHtml();
    if (keep) $(".cxgrid", m).scrollTop = top;
    if (focus) { const q = $("#cxq", m); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  };
  body.addEventListener("click", (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.cxtab) { cx.tab = b.dataset.cxtab; cx.key = null; cx.q = ""; cx.kind = "全部"; redraw(); }
    else if (b.dataset.cxkind) { cx.kind = b.dataset.cxkind; cx.key = null; redraw(); }
    else if (b.dataset.cx) { cx.key = b.dataset.cx; redraw(false, true); }
  });
  body.addEventListener("input", (ev) => { if (ev.target.id === "cxq") { cx.q = ev.target.value.trim(); cx.key = null; redraw(true); } });
  $("#cxq", m).focus();
}

function render() {
  if (!S) return;
  if (S.phase === "lobby") { document.body.classList.remove("battle"); renderLobby(); } else renderBattle();
}

loadCodex();
fetch("api/info").then((r) => r.json()).then(useAssets).catch(() => {});
renderJoin();
