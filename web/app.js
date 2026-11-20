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
const ui = { picked: [], tab: "全部", mode: "moves", search: "", sceneAction: null, wanted: null, aim: "foe" };
const HAND_NAMES = ["石头", "剪刀", "布"];
const HAND_GLYPH = { "石头": "✊", "剪刀": "✌", "布": "✋" };

// 人物特点在引擎里的名字比较短，这里换成看得懂的话。没列出来的照原样显示。
const TRAIT_TEXT = {
  "必中": "所有的招必中", "免疫不良": "免疫不良特效", "特效时长2": "打出的特效回合数加倍",
  "免疫水压": "不怕水压", "首次X光": "第一次上场给对手累计辐射 5 次", "体力无上限": "体力没有上限",
  "透视": "透视：上场后第一个出招的回合起，每隔一回合，对手先选招，他看到以后再选", "借内功": "回合开始时从对面场上人物的内功里选一种来借，最多借 5 回合", "神技无限": "神技不限次数",
  "龙王技能覆盖": "洪水、寒潮、地震、台风更强，回合开始可以移动对手", "生化覆盖": "化学和生物的招更强",
  "洪水覆盖": "洪水更强", "魔法2": "魔法的伤害和特效回合数加倍", "圣六式覆盖": "圣六式空凌更强",
  "收集5": "收集东西一次得 5 个", "库巴": "回合开始可以被扔，也可以自己跑", "初登场无敌3": "第一次上场无敌 3 回合",
  "真身": "体力 2 万以下自动回满",
};
const traitText = (list) => (list || []).map((t) => TRAIT_TEXT[t] || t).join("；");

function toast(text) {
  const el = $("#toast");
  el.textContent = text; el.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 3500);
}
function send(message) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(message)); }

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
  $("#app").innerHTML = `
    <div class="hero"><div class="logo">晒</div></div>
    <div class="panel join">
      <label>昵称 <input type="text" id="name" maxlength="12" value="${esc(store.get("shai-name") || "")}"></label>
      <label>房间号 <input type="text" id="room" maxlength="8" placeholder="留空就新开一个房间" value="${esc(location.hash.slice(1))}"></label>
      <label class="check"><input type="checkbox" id="watch"> 只观战，不上场</label>
      <button class="primary" id="go">进入房间</button>
      <button id="opencodex">图鉴：看全部招式、人物、内功</button>
      <p class="muted">把房间号告诉朋友，他输入同一个房间号就能进来。房间里已经有两个人的话，后来的人自动观战。</p>
      ${seatStore.get("shai-last-room") ? `<p class="muted">你刚才退出的房间是 <b>${esc(seatStore.get("shai-last-room"))}</b>，那一局还留着：输入这个房间号可以回去接着打。</p>` : ""}
    </div>
    <div class="panel join replays"><h2>以前的对局</h2><div id="replaylist" class="muted">正在读取…</div></div>`;
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
    box.className = "replaylist";
    box.innerHTML = list.map((r) => {
      const side = (s) => `${esc(r.names[s])}（${esc(r.teams[s].join("、"))}）`;
      const result = r.winner ? esc(r.names[r.winner]) + " 赢" : "平局";
      return `<div class="replayrow"><div><b>${when(r.ended_at)}</b>　${result}，${r.rounds} 回合<br><span class="muted">${side("A")} 对 ${side("B")}</span></div>
        <div class="row"><button data-replay="${esc(r.id)}">看回放</button><button data-log="${esc(r.id)}">文字战报</button></div></div>`;
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
    box = document.createElement("div"); box.id = "textbox";
    box.innerHTML = `<div class="panel textpanel"><div class="row"><h2></h2><button class="primary" id="copyall">复制全部</button><button id="closetext">关闭</button></div>
      <textarea readonly spellcheck="false"></textarea></div>`;
    document.body.appendChild(box);
    box.onclick = async (ev) => {
      const area = $("textarea", box);
      if (ev.target === box || ev.target.id === "closetext") { box.hidden = true; return; }
      if (ev.target.id !== "copyall") return;
      area.focus(); area.select();
      try { await navigator.clipboard.writeText(area.value); } catch (e) { try { document.execCommand("copy"); } catch (e2) { /* 复制不了就让人自己按 Ctrl+C，文字已经全选了 */ } }
      ev.target.textContent = "已复制";
      setTimeout(() => { ev.target.textContent = "复制全部"; }, 1500);
    };
  }
  $("h2", box).textContent = title;
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
  <form class="row chatform" id="chatform"><input type="text" id="chattext" maxlength="200" placeholder="说点什么" autocomplete="off"><button>发送</button></form>`;

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
  const picked = ready ? S.my_team : (ui.picked = ui.picked.filter((n) => catalog.some((c) => c.name === n)).slice(0, size));
  const draft = $("#chattext") ? { text: $("#chattext").value, focus: document.activeElement === $("#chattext") } : null;
  const seat = (side) => {
    const x = S.seats[side];
    if (!x) return `<span class="seat muted">${side}：等人进来</span>`;
    return `<span class="seat ${x.ready ? "ready" : ""}">${side}：${esc(x.name)}${side === me.side ? "（你）" : ""}${x.bot ? "（电脑）" : ""} ${x.ready ? "已选好" : "选人中"}${x.connected ? "" : "（掉线）"}</span>`;
  };
  const head = watch
    ? `<h2>你在观战</h2><span class="muted">两位玩家选好人物就开始。</span>`
    : `<h2>选 ${size} 个人物</h2><span class="muted">已选 ${picked.length} / ${size}。对手看不到你选了谁，第一个选的先上场。</span>
        ${ready ? `<button id="unready">重新选</button>` : `<button class="primary" id="ready" ${picked.length === size ? "" : "disabled"}>选好了</button>`}`;
  $("#app").innerHTML = `
    <div class="panel">
      <div class="row"><h1>房间</h1><span class="code">${esc(S.room)}</span>${seat("A")}${seat("B")}
        ${S.watchers.length ? `<span class="muted">观战：${esc(S.watchers.join("、"))}</span>` : ""}<button id="opencodex">图鉴</button></div>
      <div class="row">
        <label>每人带 <select id="size" ${host ? "" : "disabled"}>${Array.from({ length: S.settings.max_team }, (_, i) => `<option ${i + 1 === size ? "selected" : ""}>${i + 1}</option>`).join("")}</select> 个人物</label>
        <label><input type="checkbox" id="zei" ${S.settings.zei ? "checked" : ""} ${host ? "" : "disabled"}> 用贼（石头剪刀布）决定先后手和概率</label>
        <label><input type="checkbox" id="timers" ${S.settings.timers ? "checked" : ""} ${host ? "" : "disabled"}> 限时（选招 ${S.settings.choose_seconds} 秒，贼 ${S.settings.zei_seconds} 秒）</label>
        ${host && !S.seats.B ? `<button id="bot">加一个电脑对手</button>` : ""}
        ${host ? "" : `<span class="muted">设置由房主（A）决定</span>`}
      </div>
    </div>
    <div class="lobby">
      <div class="panel">
        <div class="row">${head}</div>
        <div class="cards">${catalog.map((c) => {
          const order = picked.indexOf(c.name);
          const inner = Object.entries(c.inner).map(([k, v]) => k + v).join(" ");
          return `<button class="card" data-name="${esc(c.name)}" data-tip="soul:${esc(c.name)}" aria-pressed="${order >= 0}" ${ready || watch ? "disabled" : ""}>
            <span class="face">${ART.has(c.name) ? `<img src="assets/characters/${encodeURIComponent(c.name)}.png" alt="">` : `<i>${esc(c.name.slice(0, 1))}</i>`}</span>
            <span class="about"><b>${order >= 0 ? (order + 1) + ". " : ""}${esc(c.name)}</b>
            <small>体力 ${c.hp / 10000} 万${c.shield ? "　盾 " + c.shield / 10000 + " 万" : ""}${c.lives > 1 ? "　" + c.lives + " 条命" : ""}　距离 ${c.distance}</small>
            <small>${esc(inner || "没有内功")}</small><small>${esc(traitText(c.traits))}</small></span></button>`;
        }).join("")}</div>
      </div>
      <div class="panel chatbox"><h2>聊天</h2>${chatBoxHtml()}</div>
    </div>`;
  if (host) {
    $("#size").onchange = (e) => send({ t: "config", team_size: +e.target.value });
    $("#zei").onchange = (e) => send({ t: "config", zei: e.target.checked });
    $("#timers").onchange = (e) => send({ t: "config", timers: e.target.checked });
    if ($("#bot")) $("#bot").onclick = () => send({ t: "bot" });
  }
  $("#opencodex").onclick = () => openCodex();
  if ($("#ready")) $("#ready").onclick = () => send({ t: "team", names: ui.picked });
  if ($("#unready")) $("#unready").onclick = () => send({ t: "unready" });
  $(".cards").onclick = (ev) => {
    const card = ev.target.closest(".card"); if (!card || ready || watch) return;
    const name = card.dataset.name, i = ui.picked.indexOf(name);
    if (i >= 0) ui.picked.splice(i, 1); else if (ui.picked.length < size) ui.picked.push(name);
    renderLobby();
  };
  renderChat(); bindChat();
  if (draft) { $("#chattext").value = draft.text; if (draft.focus) $("#chattext").focus(); }
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

// 牌子下面那一格：内功、场下的人物、物品。头像和血条是 stage.js 画的。
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
  const minis = p.team.map((f, i) => {
    if (i === p.active) return "";
    if (f.hidden) return `<span class="mini unknown" title="还没上过场的人物">？</span>`;
    if (f.is_true_body && !f.entered) return "";
    return `<button class="mini ${f.defeated ? "out" : ""}" data-tip="soul:${esc(f.name)}" data-detail="${side}:${i}" aria-label="${esc(f.name)}">${faceHtml(f.name)}<small>${f.defeated ? "倒下" : wan(f.hp).replace(" ", "")}</small></button>`;
  }).join("");
  const items = Object.entries(active.resources || {}).filter(([, v]) => v > 0).map(([k, v]) => `<span class="chip">${esc(k)} ${v}</span>`).join("");
  const devices = Object.entries(active.devices || {}).filter(([, v]) => v > 0).map(([k, v]) => `<span class="chip">${esc(k)} 造了 ${v} 下</span>`).join("");
  const tree = p.tree ? `<span class="chip">通天神树 ${p.tree}/10</span>` : "";
  const chosen = !replay && S.view.chosen[side] && S.need !== "over" ? `<span class="chip on">已选招</span>` : "";
  return `<div class="chips">${chosen}${inner}</div><div class="chips">${minis}${items}${devices}${tree}</div>`;
}
function renderExtras() {
  for (const side of ["A", "B"]) {
    const el = $(`[data-extra="${side}"]`);
    if (el) el.innerHTML = extraHtml(side);
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
  if (playing) return `<span class="muted">${replay ? "正在回放…" : "正在播放这一回合…"}</span><button id="skip">${replay ? "跳到结尾" : "跳过动画"}</button>`;
  if (replay) {
    return `<span class="over">回放结束：${resultText(p.winner)}</span>
      <button class="primary" id="again">再放一遍</button><button id="back">返回</button><button data-log="${esc(replay.id)}">文字战报</button>`;
  }
  const soFar = (p.so_far || []).length ? `<ul>${p.so_far.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
  if (S.need === "over") {
    const saved = S.replay_id ? `<button data-log="${esc(S.replay_id)}">这一局的文字战报</button>` : "";
    return `<span class="over">对战结束：${resultText(p.winner)}</span>${inGame() ? `<button class="primary" id="rematch">再来一局</button>` : ""}${saved}
      ${S.replay_id ? `<span class="muted">这一局已经保存。回到进房间的页面，在“以前的对局”里可以看回放。</span>` : ""}`;
  }
  const sees = (S.view && S.view.sees) || {};
  if (S.need === "choose") {
    if (inGame() && S.choose_for && S.choose_for !== me.side) {
      return `<b>对手这回合被你的虫子控制：现在替对手选他的招。</b><span class="muted">下面列的是对手的招。可以让他打你，也可以让他打他自己。</span>`;
    }
    const peek = S.view.peek;
    if (peek) return `<span class="peek">透视：对手这回合选了【${esc(peek.name)}】${peek.on_self ? "（打他自己）" : ""}${peek.destination ? "（去" + esc(peek.destination) + "）" : ""}。</span>`;
    return inGame() && sees[R] ? `<span class="muted">对手能透视你：你选完以后他才选，他看得到你选了什么。</span>` : "";
  }
  if (S.need === "pick") {
    return `<b>${esc(personal(p.reason))}</b>${soFar}${p.options.map((o) => `<button class="primary" data-pick="${esc(o.id)}">${esc(o.name)}</button>`).join("")}`;
  }
  if (p.mode) return `<span class="muted">正在贼：看舞台中间的框。</span>`;
  if (p.reason) return `<span class="muted">${esc(personal(p.reason))}…</span>`;
  return "";
}

// 舞台正中间的大字：轮到谁了。
function centerText() {
  if (!S || playing || replay) return "";
  const p = S.prompt || {};
  if (S.need === "over") return resultText(p.winner);
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
  else if (S.need === "redo") body = `<div class="row hands"><b>这一把你输了。你有内功“重贼”，还能重来 ${p.redo_left[me.side]} 次。</b><button class="primary" data-redo="1">重贼</button><button data-redo="0">算了</button></div>`;
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
  if (ring) {                                   // 舞台中间的圆圈：只放数字
    const mine = /^(你|对手)还剩 (\d+) 秒$/.exec(text);
    ring.textContent = mine ? mine[2] : "";
    ring.classList.toggle("urgent", urgent);
    if (sub) sub.textContent = mine ? (mine[1] === "你" ? "" : "对手的时间") : text;
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
function badgeHtml(a) {
  const attrs = a.attributes || [], kind = category(a);
  if (kind === "防御") {
    const code = DEF_OF_ACTION[a.id], file = DEF_ICON[code];
    return file && DEF_ART.has(file) ? `<span class="badge big"><img alt="" src="assets/defense/${file}.png"></span>` : `<span class="badge big">防</span>`;
  }
  if (!attrs.length) return `<span class="badge" style="--c:#d4dcf0">${kind === "内功" ? "功" : kind === "换人" ? "换" : "无"}</span>`;
  if (attrs.length >= 8) return `<span class="badge" style="--c:#ffffff">全</span>`;
  // 有两种属性的招：字用第一种属性的颜色，圆盘的圈用第二种
  const first = ATTR_BRIGHT[attrs[0]] || "#d4dcf0", ring = attrs.length > 1 ? `;--ring:${ATTR_BRIGHT[attrs[1]] || first}` : "";
  return `<span class="badge" style="--c:${first}${ring}">${ATTR_GLYPH[attrs[0]] || "？"}</span>`;
}
// 用什么能防住这一招：有手绘图标就画图标，没有就写字。
function defenseCell(a) {
  const hitsFoe = a.target === "enemy" || a.effect === "self_status_and_damage";
  if (a.action_kind !== "skill" || !hitsFoe) return "—";
  if (a.defense == null) return "防不住";
  const file = DEF_ICON[a.defense];
  const icon = file && DEF_ART.has(file) ? `<img class="deficon" alt="" src="assets/defense/${file}.png">` : "";
  return icon + esc(DEF_NAME[a.defense] || "");
}
const mvRow = (label, value) => `<span class="mvrow"><span>${label}</span><b>${value}</b></span>`;
function cardHtml(a, q, first) {
  const self = ui.aim === "self", idle = !choosing();
  const ok = !idle && (self ? a.self_ok : a.legal), why = self ? a.self_reason : a.reason;
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
  return `<button class="mv ${ok ? "" : "off"} ${idle ? "idle" : ""} ${first && ok ? "first" : ""}" data-action="${esc(a.id)}" data-tip="act:${esc(a.id)}" aria-disabled="${ok ? "false" : "true"}">
    ${badgeHtml(a)}<span class="mvbody"><b class="mvname">${name}</b>${rows}</span></button>`;
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

// 队伍卡：点“换人”的时候下面换成这一排。
function teamHtml() {
  const side = (inGame() && S.choose_for) || leftSide(), p = S.view.players[side], can = choosing();
  return p.team.map((f, i) => {
    if (f.hidden || (f.is_true_body && !f.entered)) return "";
    const act = (S.actions || []).find((a) => a.id === "switch:" + i);
    const active = i === p.active, ok = can && !!act && act.legal;
    const pct = Math.max(0, Math.min(100, (100 * f.hp) / Math.max(1, f.max_hp)));
    const bad = Object.keys(f.statuses || {}).concat(Object.keys(f.parasites || {}));
    const sub = active ? "正在场上" : f.defeated ? "已经倒下" : (bad.length ? bad.join("、") : "没有不良状态");
    return `<button class="tm ${active ? "on" : ""} ${ok ? "" : "off"}" ${ok ? `data-action="switch:${i}"` : ""} data-tip="soul:${esc(f.name)}" aria-disabled="${ok ? "false" : "true"}">
      <span class="face">${faceHtml(f.name)}</span><span class="mvbody"><b class="mvname">${esc(f.name)}${f.lives_total > 1 ? ` <span class="lives">${"●".repeat(Math.max(0, f.lives_remaining))}</span>` : ""}</b>
      <span class="bar"><i style="width:${pct}%"></i><span>${f.hp} / ${f.max_hp}</span></span><span class="tmsub">${esc(sub)}</span></span></button>`;
  }).join("");
}

function actionsHtml() {
  const all = (choosing() ? S.actions : ui.lastActions) || [];
  if (!all.length && ui.mode !== "switch") return "";
  const self = ui.aim === "self", q = ui.search;
  const list = all.filter((a) => !self || a.self_ok != null);       // 打自己的时候只列能对自己用的招
  const group = (title, items, opts = {}) => (items.length || opts.always
    ? `<div class="grp">${title}</div>` + (items.map((a, i) => cardHtml(a, opts.q, opts.first && i === 0)).join("") || `<span class="muted">${opts.empty || ""}</span>`)
    : "");
  if (q) {
    const hits = list.map((a) => [searchRank(a.name, pyOf(a), q), a]).filter(([r]) => r >= 0).sort((x, y) => x[0] - y[0]).map(([, a]) => a);
    return group(`搜到 ${hits.length} 个${hits.length && choosing() ? "，按回车出第一个能用的" : ""}`, hits, { q, always: true, empty: "没有叫这个名字的招。", first: true });
  }
  if (ui.mode === "switch") return `<div class="grp">换谁上场：换人占这个回合的出招，比所有的招都先生效。</div>` + teamHtml();
  if (ui.mode === "items") return group("物品", list.filter((a) => category(a) === "物品"), { always: true, empty: self ? "没有能对自己用的物品。" : "" });
  const moves = list.filter((a) => !["防御", "换人", "物品"].includes(category(a)));
  if (ui.tab !== "全部") return group(ui.tab, moves.filter((a) => category(a) === ui.tab), { always: true, empty: "这一类里没有招。" });
  const recent = recentIds().map((id) => list.find((a) => a.id === id)).filter(Boolean).slice(0, 4);
  return group("最近用过", recent) + group("全部招式（往下滚，或者在左边搜）", moves, { always: true });
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
  if (replay) return `<div class="rnd"><b>回放</b><span>${when(replay.ended_at)}</span><span>${esc(replay.names.A)} 对 ${esc(replay.names.B)}</span><span>共 ${replay.rounds} 回合</span></div>`;
  const now = (side) => (stage && stage.model && stage.model[side]) || v.players[side].team[v.players[side].active] || {};
  const a = now(L), b = now(R);
  const alive = (side) => v.players[side].team.filter((f) => !f.defeated && !(f.is_true_body && !f.entered)).length;
  const rel = a.height === b.height ? "同一层" : a.height > b.height ? `${who(L)}在上面` : `${who(R)}在上面`;
  const water = v.water_level < 0 ? "" : `<span>水面高度 ${v.water_level}</span>`;
  const watchers = S.watchers.length ? `<span>观战：${esc(S.watchers.join("、"))}</span>` : "";
  return `<div class="vs"><div>${esc(a.scene || "")}<small>高度 ${a.height ?? ""}</small></div><i>›››</i><i>‹‹‹</i><div>${esc(b.scene || "")}<small>高度 ${b.height ?? ""}</small></div></div>
    <div class="rnd"><span>${alive(L)} 人</span><b>第 ${v.round} 回合</b><span>${alive(R)} 人</span></div>
    <div class="rnd csub"><span>${rel}</span><span>房间 ${esc(S.room)}</span>${water}${inGame() ? "" : "<span>你在观战</span>"}${watchers}</div>`;
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
let BACKDROPS = [];
function applyBackdrop() {
  const el = $("#backdrop"), battle = $("#battle"); if (!el || !battle) return;
  const saved = store.get("shai-backdrop"), name = BACKDROPS.includes(saved) ? saved : "";
  el.style.backgroundImage = name ? `url("assets/backgrounds/${encodeURIComponent(name)}")` : "";
  battle.classList.toggle("has-photo", !!name);
}
function nextBackdrop() {
  const list = [""].concat(BACKDROPS), now = list.indexOf(store.get("shai-backdrop") || "");
  store.set("shai-backdrop", list[(now + 1) % list.length]);
  applyBackdrop();
}

const TRAY_TABS = ["全部", "技能", "神技", "专属", "内功"];
const MODES = [["moves", "战斗"], ["items", "物品"], ["switch", "换人"], ["codex", "图鉴"]];

function renderControls() {
  if (!$("#battle") || !S || S.phase === "lobby") return;
  $("#top").innerHTML = topHtml();
  $("#side").innerHTML = sideHtml();
  $("#prompt").innerHTML = promptHtml();
  const box = $("#stage .zeibox");
  if (box && !playing) {                       // 播放的时候这个框归舞台管（它要在里面亮出贼的结果）
    const html = zeiPanelHtml();
    if (html) { box.innerHTML = html; box.hidden = false; } else { box.hidden = true; box.innerHTML = ""; }
  }
  const text = centerText(), center = $("#center");
  center.hidden = playing || (box && !box.hidden);
  $("#ctext").textContent = text;
  tickClock();
  const can = choosing();
  if (can) ui.lastActions = S.actions;
  else ui.sceneAction = null;
  $("#tray").classList.toggle("idle", !can);
  const proxy = inGame() && S.choose_for && S.choose_for !== me.side;       // 正在替被控制的对手选招
  $("#aim").innerHTML = `<span>这一招打</span><button data-aim="foe" aria-pressed="${ui.aim === "foe"}">${proxy ? "你" : "对手"}</button><button data-aim="self" aria-pressed="${ui.aim === "self"}">${proxy ? "他自己" : "自己"}</button>
    ${ui.aim === "self" ? `<span class="warn">打自己：不用躲，够不着也能用，伤害和特效都落在自己身上。</span>` : ""}`;
  $("#defrow").innerHTML = defenseRowHtml();
  $("#tabs").innerHTML = ui.mode === "moves" && !ui.search
    ? TRAY_TABS.map((t) => `<button data-tab="${t}" aria-pressed="${t === ui.tab}">${t}</button>`).join("") : "";
  $("#modes").innerHTML = MODES.map(([id, name]) => `<button data-mode="${id}" aria-pressed="${id === ui.mode && !ui.search}"><span>${name}</span></button>`).join("");
  $("#scenepick").innerHTML = ui.sceneAction ? `<div class="row"><b>去哪个场景？</b>${scenes.map((s) => `<button data-scene="${esc(s.name)}">${esc(s.name)}</button>`).join("")}<button>取消</button></div>` : "";
  $("#actions").innerHTML = actionsHtml();
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
    $("#app").innerHTML = `<div id="battle">
      <div class="stagewrap">
        <div class="backdrop" id="backdrop"></div>
        <div class="floor"><i></i></div>
        <div id="stage"></div>
        <div id="top"></div>
        <div id="center" hidden><b class="cring" id="clocknum"></b><span class="ctext" id="ctext"></span><span class="csub" id="clocksub"></span></div>
        <div id="side"></div>
        <button id="feed" title="点开看全部战报"></button>
      </div>
      <div id="tray">
        <div id="trayleft">
          <div class="searchbox">
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#cfe2ff" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.8-3.8"></path></svg>
            <input type="text" id="search" placeholder="搜招式，可打拼音首字母" autocomplete="off" spellcheck="false" aria-label="搜招式">
          </div>
          <div class="defrow" id="defrow"></div>
          <div class="aim" id="aim"></div>
        </div>
        <div id="traymid"><div id="prompt"></div><div class="tabs" id="tabs"></div><div id="scenepick"></div><div id="actions"></div></div>
        <div id="modes"></div>
      </div>
      <div id="drawer" hidden>
        <div class="row"><h2>战报</h2><span class="row"><button id="copylog">复制战报</button><button id="closedrawer">关闭</button></span></div>
        <div class="log" id="log"></div>
        ${replay ? "<span></span><span></span><span></span>" : `<h2>聊天</h2>${chatBoxHtml()}`}
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
  m.innerHTML = `<div class="dialog" role="dialog" aria-label="${esc(title)}"><div class="dhead"><span>${esc(title)}</span><button class="x" aria-label="关闭">×</button></div><div class="dbody ${cls || ""}">${body}</div></div>`;
  m.addEventListener("click", (ev) => { if (ev.target === m || ev.target.closest(".x")) closeModal(); });
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
  const inner = Object.entries(f.inner || {}).filter(([, v]) => v > 0).map(([k, v]) => {
    const c = codexIndex.inner[k], line = c && c.lines[v - 1] ? c.lines[v - 1][1].replace(/^\d 级：/, "") : "";
    return `<span><b>${esc(k)} ${v} 级${lent.has(k) ? "（借对手的）" : learned.has(k) ? "（学的）" : ""}${innerOff(f, k)}</b>　${esc(line)}</span>`;
  }).join("") || `<span class="muted">没有内功。</span>`;
  const st = Object.entries(f.statuses || {}).map(([n, s]) => `<span><b>${esc(n)} ${s.turns} 回合</b>　${esc((codexIndex.status[n] || {}).text || "")}</span>`)
    .concat(Object.entries(f.parasites || {}).map(([n, x]) => `<span><b>${esc(n)} ×${x.count}</b>　${esc((codexIndex.parasite[n] || {}).text || "")}</span>`)).join("")
    || `<span class="muted">没有状态，也没有虫子。</span>`;
  const items = Object.entries(f.resources || {}).filter(([, v]) => v > 0).map(([k, v]) => `${esc(k)} ${v}`).join("、") || "没有";
  const owner = inGame() ? (side === me.side ? "你" : "对手") : seatName(side);
  const body = `<div class="dcol">
      <div class="dsec">基础信息</div>
      <div class="dbase"><span class="face">${faceHtml(f.name)}</span>
        <div class="dl"><span>名字</span><b>${esc(f.name)}</b><span>谁的人物</span><b>${esc(owner)}</b>
          <span>体力</span><b>${f.hp} / ${f.max_hp}</b>${f.max_shield ? `<span>盾牌</span><b>${f.shield} / ${f.max_shield}</b>` : ""}
          <span>命</span><b>还有 ${f.lives_remaining} 条，一共 ${f.lives_total} 条</b>
          <span>在哪儿</span><b>${esc(f.scene)}（高度 ${f.height}）</b><span>累计辐射</span><b>${f.radiation || 0} / 15</b><span>物品</span><b>${items}</b></div></div>
      <div class="dsec">内功</div><div class="dlist">${inner}</div>
      <div class="dsec">身上的状态和虫子</div><div class="dlist">${st}</div>
    </div>
    <div class="dcol"><div class="dsec">魂印</div><div class="dtext">${tipLines(card.lines)}</div></div>`;
  openModal("人物详情", body);
}

// ---------- 图鉴：全部招式、人物、内功、状态、场景 ----------

const CODEX_TABS = ["招式", "人物", "内功", "状态和虫子", "场景"];
const cx = { tab: "招式", q: "", key: null };
function codexItems(tab) {
  if (!CODEX) return [];
  if (tab === "招式") return CODEX.skills.map((s) => ({ key: s.id, name: s.name, py: s.py, group: s.kind, tag: s.tag, lines: s.lines, color: ATTR_COLOR[s.attributes[0]] }));
  if (tab === "人物") return CODEX.characters.map((c) => ({ key: c.name, name: c.name, py: c.py, group: c.group, tag: "魂印", lines: c.lines }));
  if (tab === "内功") return CODEX.inner.map((c) => ({ key: c.name, name: c.name, py: c.py, group: "内功", tag: "内功", lines: c.lines }));
  if (tab === "场景") return CODEX.scenes.map((c) => ({ key: c.name, name: c.name, py: "", group: "场景（从高到低）", tag: "场景", lines: c.lines }));
  return CODEX.statuses.map((c) => ({ key: "s:" + c.name, name: c.name, py: "", group: c.good ? "好状态" : "不良状态", tag: c.good ? "好状态" : "不良状态", lines: [["text", c.text]] }))
    .concat(CODEX.parasites.map((c) => ({ key: "p:" + c.name, name: c.name, py: "", group: "虫子", tag: "虫子", lines: [["text", c.text]] })));
}
function codexHtml() {
  let items = codexItems(cx.tab);
  if (cx.q) items = items.map((it) => [searchRank(it.name, it.py, cx.q), it]).filter(([r]) => r >= 0).sort((a, b) => a[0] - b[0]).map(([, it]) => it);
  const picked = items.find((it) => it.key === cx.key) || items[0];
  let last = null;
  const list = items.map((it) => {
    const head = !cx.q && it.group !== last ? `<div class="grp">${esc(it.group)}</div>` : "";
    last = it.group;
    return `${head}<button data-cx="${esc(it.key)}" aria-pressed="${picked && it.key === picked.key}">${it.color ? `<i class="dotc" style="background:${it.color}"></i>` : ""}${esc(it.name)}</button>`;
  }).join("") || `<span class="muted">没有搜到。</span>`;
  const detail = picked ? `<div class="cxname">${esc(picked.name)} <small>（${esc(picked.tag)}）</small></div><div class="dtext">${tipLines(picked.lines)}</div>` : "";
  return `<div class="dcol"><div class="dtabs">${CODEX_TABS.map((t) => `<button data-cxtab="${t}" aria-pressed="${t === cx.tab}">${t}</button>`).join("")}</div>
      <div class="cxtools"><input type="text" id="cxq" placeholder="搜名字或拼音首字母" value="${esc(cx.q)}" autocomplete="off" spellcheck="false" aria-label="在图鉴里搜"></div>
      <div class="cxlist">${list}</div></div>
    <div class="dcol">${detail}</div>`;
}
function openCodex() {
  if (!CODEX) return toast("图鉴的文字还没读到，稍等一下再点。");
  const m = openModal("图鉴", codexHtml(), "cx"), body = $(".dbody", m);
  const redraw = (focus) => { body.innerHTML = codexHtml(); if (focus) { const q = $("#cxq", m); q.focus(); q.setSelectionRange(q.value.length, q.value.length); } };
  body.addEventListener("click", (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.cxtab) { cx.tab = b.dataset.cxtab; cx.key = null; cx.q = ""; redraw(); }
    else if (b.dataset.cx) { cx.key = b.dataset.cx; redraw(); }
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
