"use strict";
// 第二步的网页：进房间、选人、对战、贼、文字战报。没有动画（第三步做）。
// 网页不懂规则：服务器发来“你现在能看到什么、需要做什么”，这里只负责显示和把选择发回去。

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
let me = null;            // {room, side, token, name}
let S = null;             // 服务器发来的最新局面
let catalog = [];         // 可以选的人物
let scenes = [];
let events = [];          // 从开局到现在的全部事件
const ui = { picked: [], tab: "全部", search: "", sceneAction: null, wanted: null };
const HAND_NAMES = ["石头", "剪刀", "布"];
const TABS = ["全部", "技能", "神技", "防御", "物品", "专属", "换人"];

function toast(text) {
  const el = $("#toast");
  el.textContent = text; el.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 3500);
}
function send(message) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(message)); }

// ---------- 连接 ----------

function connect(room, name) {
  ui.wanted = { room, name };
  const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
  ws = new WebSocket(url);
  ws.onopen = () => send({ t: "join", room, name, token: room ? seatStore.get("shai-token-" + room) : null });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.t === "error") return toast(m.message);
    if (m.t === "joined") {
      me = { room: m.room, side: m.side, token: m.token, name };
      catalog = m.characters; scenes = m.scenes; events = [];
      seatStore.set("shai-token-" + m.room, m.token);
      ui.wanted.room = m.room; location.hash = m.room;
      return;
    }
    if (m.t === "state") {
      S = m;
      if (m.events) {
        if (m.events_from === 0) events = [];
        if (m.events_from === events.length) events = events.concat(m.events);
      }
      if (m.phase === "lobby") events = [];
      render();
    }
  };
  ws.onclose = () => {
    if (!me) return toast("连不上服务器。");
    toast("连接断开，正在重连…");
    setTimeout(() => connect(ui.wanted.room, ui.wanted.name), 1500);
  };
}

// ---------- 进房间 ----------

function renderJoin() {
  $("#app").innerHTML = `
    <div class="panel join">
      <h1>晒</h1>
      <label>昵称 <input type="text" id="name" maxlength="12" value="${esc(store.get("shai-name") || "")}"></label>
      <label>房间号 <input type="text" id="room" maxlength="8" placeholder="留空就新开一个房间" value="${esc(location.hash.slice(1))}"></label>
      <button class="primary" id="go">进入房间</button>
      <p class="muted">把房间号告诉朋友，他输入同一个房间号就能进来。</p>
    </div>`;
  $("#go").onclick = () => {
    const name = $("#name").value.trim() || "无名";
    store.set("shai-name", name);
    connect($("#room").value.trim(), name);
  };
}

// ---------- 选人 ----------

function renderLobby() {
  const host = me.side === "A", size = S.settings.team_size, ready = !!S.my_team;
  const picked = ready ? S.my_team : (ui.picked = ui.picked.filter((n) => catalog.some((c) => c.name === n)).slice(0, size));
  const seat = (side) => {
    const x = S.seats[side];
    if (!x) return `<span class="seat muted">${side}：等人进来</span>`;
    return `<span class="seat ${x.ready ? "ready" : ""}">${side}：${esc(x.name)}${side === me.side ? "（你）" : ""}${x.bot ? "（电脑）" : ""} ${x.ready ? "已选好" : "选人中"}${x.connected ? "" : "（掉线）"}</span>`;
  };
  $("#app").innerHTML = `
    <div class="panel">
      <div class="row"><h1>房间</h1><span class="code">${esc(S.room)}</span>${seat("A")}${seat("B")}</div>
      <div class="row">
        <label>每人带 <select id="size" ${host ? "" : "disabled"}>${Array.from({ length: S.settings.max_team }, (_, i) => `<option ${i + 1 === size ? "selected" : ""}>${i + 1}</option>`).join("")}</select> 个人物</label>
        <label><input type="checkbox" id="zei" ${S.settings.zei ? "checked" : ""} ${host ? "" : "disabled"}> 用贼（石头剪刀布）决定先后手和概率</label>
        ${host && !S.seats.B ? `<button id="bot">加一个电脑对手</button>` : ""}
        ${host ? "" : `<span class="muted">设置由房主（A）决定</span>`}
      </div>
    </div>
    <div class="panel">
      <div class="row"><h2>选 ${size} 个人物</h2><span class="muted">已选 ${picked.length} / ${size}。对手看不到你选了谁，第一个选的先上场。</span>
        ${ready ? `<button id="unready">重新选</button>` : `<button class="primary" id="ready" ${picked.length === size ? "" : "disabled"}>选好了</button>`}</div>
      <div class="cards">${catalog.map((c) => {
        const order = picked.indexOf(c.name);
        const inner = Object.entries(c.inner).map(([k, v]) => k + v).join(" ");
        return `<button class="card" data-name="${esc(c.name)}" aria-pressed="${order >= 0}" ${ready ? "disabled" : ""}>
          <b>${order >= 0 ? (order + 1) + ". " : ""}${esc(c.name)}</b>
          <small>体力 ${c.hp / 10000} 万${c.shield ? "　盾 " + c.shield / 10000 + " 万" : ""}${c.lives > 1 ? "　" + c.lives + " 条命" : ""}　距离 ${c.distance}</small>
          <small>${esc(inner || "没有内功")}</small><small>${esc(c.traits.join("、"))}</small></button>`;
      }).join("")}</div>
    </div>`;
  if (host) {
    $("#size").onchange = (e) => send({ t: "config", team_size: +e.target.value });
    $("#zei").onchange = (e) => send({ t: "config", zei: e.target.checked });
    if ($("#bot")) $("#bot").onclick = () => send({ t: "bot" });
  }
  if ($("#ready")) $("#ready").onclick = () => send({ t: "team", names: ui.picked });
  if ($("#unready")) $("#unready").onclick = () => send({ t: "unready" });
  $(".cards").onclick = (ev) => {
    const card = ev.target.closest(".card"); if (!card || ready) return;
    const name = card.dataset.name, i = ui.picked.indexOf(name);
    if (i >= 0) ui.picked.splice(i, 1); else if (ui.picked.length < size) ui.picked.push(name);
    renderLobby();
  };
}

// ---------- 对战 ----------

function fighterHtml(f) {
  if (!f || f.hidden) return `<div class="muted">还没露面</div>`;
  const pct = (a, b) => Math.max(0, Math.min(100, (100 * a) / Math.max(1, b)));
  const chips = [];
  for (const [n, s] of Object.entries(f.statuses)) chips.push(`<span class="chip ${["氪", "真空", "狂龙", "道威", "无敌"].includes(n) ? "good" : "bad"}">${esc(n)} ${s.turns}${s.layer === "shield" ? "（盾）" : ""}</span>`);
  for (const [n, p] of Object.entries(f.parasites)) chips.push(`<span class="chip bad">${esc(n)} ×${p.count}</span>`);
  if (f.radiation) chips.push(`<span class="chip bad">辐射 ${f.radiation}/15</span>`);
  const inner = Object.entries(f.inner).filter(([, v]) => v > 0).map(([k, v]) => `<span class="chip">${esc(k)}${v}</span>`).join("");
  const items = Object.entries(f.resources).filter(([, v]) => v > 0).map(([k, v]) => `<span class="chip">${esc(k)} ${v}</span>`).join("");
  return `<div class="fighter">
    <div class="row"><span class="name">${esc(f.name)}</span><span>${esc(f.scene)}（高度 ${f.height}）</span>${f.lives_total > 1 ? `<span>命 ${f.lives_remaining}/${f.lives_total}</span>` : ""}</div>
    <div class="bar"><i style="width:${pct(f.hp, f.max_hp)}%"></i><span>体力 ${f.hp} / ${f.max_hp}</span></div>
    ${f.max_shield ? `<div class="bar shield"><i style="width:${pct(f.shield, f.max_shield)}%"></i><span>盾 ${f.shield} / ${f.max_shield}</span></div>` : ""}
    <div class="chips">${chips.join("") || `<span class="muted">没有状态</span>`}</div>
    <div class="chips">${inner}</div><div class="chips">${items}</div></div>`;
}

function sideHtml(side) {
  const p = S.view.players[side], seat = S.seats[side];
  const bench = p.team.map((f, i) => {
    if (i === p.active) return "";
    if (f.hidden) return `<span class="chip">？</span>`;
    if (f.is_true_body && !f.entered) return "";
    return `<span class="chip ${f.defeated ? "out" : ""}">${esc(f.name)}${f.defeated ? "" : " " + f.hp}</span>`;
  }).join("");
  return `<div class="panel side">
    <h2>${side === me.side ? "你" : "对手"} <span>${esc(seat ? seat.name : "")}${S.view.chosen[side] && S.need !== "over" ? "　已选招" : ""}</span></h2>
    ${fighterHtml(p.team[p.active])}
    <div class="chips"><span class="muted">场下：</span>${bench || `<span class="muted">没有</span>`}</div></div>`;
}

function promptHtml() {
  const p = S.prompt || {}, foe = me.side === "A" ? "B" : "A";
  const soFar = (p.so_far || []).length ? `<ul>${p.so_far.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
  if (S.need === "over") {
    const text = p.winner == null ? "平局" : (p.winner === me.side ? "你赢了" : "你输了");
    return `<div class="panel prompt"><div class="row"><span class="over">对战结束：${text}</span><button class="primary" id="rematch">再来一局</button></div></div>`;
  }
  if (S.need === "choose") return `<div class="panel prompt"><b>请选这回合的招。</b></div>`;
  if (S.need === "pick") {
    return `<div class="panel prompt"><b>${esc(p.reason)}</b>${soFar}<div class="row">${p.options.map((o) => `<button class="primary" data-pick="${esc(o.id)}">${esc(o.name)}</button>`).join("")}</div></div>`;
  }
  if (S.need === "throw" || S.need === "redo" || (S.need === "wait" && p.mode)) {
    const rounds = (p.rounds || []).map((r, i) => `<li>第 ${i + 1} 轮：你出${esc(r[me.side])}，对手出${esc(r[foe])}</li>`).join("");
    const shown = p.choices ? `<p>你出了【${esc(p.choices[me.side].name)}】，对手出了【${esc(p.choices[foe].name)}】。</p>` : "";
    let body;
    if (S.need === "throw") body = `<div class="row hands">${HAND_NAMES.map((h) => `<button class="primary" data-hand="${h}">${h}</button>`).join("")}</div>`;
    else if (S.need === "redo") body = `<div class="row"><b>这一轮你输了。你还能重贼 ${p.redo_left[me.side]} 次。</b><button class="primary" data-redo="1">重贼</button><button data-redo="0">算了</button></div>`;
    else if (p.redo_side) body = `<p class="muted">对手输了，正在决定要不要重贼…</p>`;
    else body = `<p class="muted">${p.thrown && p.thrown[me.side] ? "你已经出了，等对手出拳…" : "等待中…"}</p>`;
    return `<div class="panel prompt ${S.need === "wait" ? "wait" : ""}"><b>贼：${esc(p.reason)}</b>
      <span class="muted">${p.mode === "single" ? "只贼一次，打平不算赢。" : "贼到分出胜负为止。"}</span>${shown}${soFar}${rounds ? `<ul>${rounds}</ul>` : ""}${body}</div>`;
  }
  return `<div class="panel prompt wait"><span class="muted">${p.reason ? esc(p.reason) + "…" : "你已经选好了，等对手…"}</span></div>`;
}

function category(a) {
  if (a.action_kind === "switch") return "换人";
  if (a.action_kind === "defense") return "防御";
  if (a.attributes.includes("神技")) return "神技";
  if (a.character) return "专属";
  if (a.attributes.includes("物品") || ["collect", "build", "scene"].includes(a.action_kind)) return "物品";
  return "技能";
}

function actionsHtml() {
  if (S.need !== "choose") return "";
  const list = (S.actions || []).filter((a) => (ui.tab === "全部" || category(a) === ui.tab) && (!ui.search || a.name.includes(ui.search)));
  const tier = (t) => (t >= 60 ? "换人最先" : t >= 40 ? "比神技快" : t >= 30 ? "神技档" : t >= 20 ? "先手" : "");
  return list.map((a) => {
    const info = [a.attributes.join("+") || (a.action_kind === "skill" ? "无属性" : ""), a.damage ? "伤害 " + a.damage / 10000 + " 万" : "",
      a.defense ? "防 " + a.defense : "", tier(a.tier)].filter(Boolean).join(" · ");
    const extra = (a.statuses || []).map(([n, t]) => n + t).join(" ");
    return `<button class="action" data-action="${esc(a.id)}" ${a.legal ? "" : "disabled"} title="${esc(a.legal ? a.description || "" : a.reason)}">
      <b>${esc(a.name)}</b><small>${esc(info)}</small>${extra ? `<small>${esc(extra)}</small>` : ""}${a.legal ? "" : `<small>${esc(a.reason)}</small>`}</button>`;
  }).join("") || `<span class="muted">没有符合的招。</span>`;
}

function logHtml() {
  return events.filter((e) => e.t === "log").map((e) => {
    const cls = /^第\d+回合：/.test(e.text) ? "round" : e.text.startsWith("贼（") ? "zei" : "";
    return `<p class="${cls}">${esc(e.text)}</p>`;
  }).join("");
}

function renderBattle() {
  const app = $("#app");
  if (!$("#battle")) {
    app.innerHTML = `<div id="battle" style="display:grid;gap:14px">
      <div class="panel"><div class="row top" id="top"></div></div>
      <div class="sides" id="sides"></div>
      <div id="prompt"></div>
      <div class="panel" id="actionbox">
        <div class="row"><div class="row tabs" id="tabs"></div><input type="text" id="search" placeholder="搜招式名字"></div>
        <div id="scenepick"></div>
        <div class="actions" id="actions"></div>
      </div>
      <div class="panel"><h2>战报</h2><div class="log" id="log"></div></div></div>`;
    $("#search").oninput = (e) => { ui.search = e.target.value.trim(); $("#actions").innerHTML = actionsHtml(); };
    $("#tabs").onclick = (ev) => { const b = ev.target.closest("button"); if (b) { ui.tab = b.dataset.tab; renderBattle(); } };
    $("#actions").onclick = (ev) => {
      const b = ev.target.closest(".action"); if (!b || b.disabled) return;
      const action = S.actions.find((a) => a.id === b.dataset.action);
      if (action.effect === "choose_scene") { ui.sceneAction = action.id; renderBattle(); } else send({ t: "choose", action: action.id });
    };
    $("#scenepick").onclick = (ev) => {
      const b = ev.target.closest("button"); if (!b) return;
      if (b.dataset.scene) send({ t: "choose", action: ui.sceneAction, destination: b.dataset.scene });
      ui.sceneAction = null; renderBattle();
    };
    $("#prompt").onclick = (ev) => {
      const b = ev.target.closest("button"); if (!b) return;
      if (b.dataset.hand) send({ t: "throw", hand: b.dataset.hand });
      else if (b.dataset.redo) send({ t: "redo", yes: b.dataset.redo === "1" });
      else if (b.dataset.pick) send({ t: "pick", option: b.dataset.pick });
      else if (b.id === "rematch") send({ t: "rematch" });
    };
    $("#top").onchange = (ev) => { if (ev.target.id === "auto") send({ t: "auto", on: ev.target.checked }); };
  }
  const v = S.view, mine = S.seats[me.side];
  $("#top").innerHTML = `<span><b>房间 ${esc(S.room)}</b>　第 ${v.round} 回合　水面高度 ${v.water_level}　${v.zei_enabled ? "用贼" : "不用贼（电脑掷概率）"}</span>
    ${v.zei_enabled ? `<label><input type="checkbox" id="auto" ${mine.auto_zei ? "checked" : ""}> 电脑替我出拳</label>` : ""}`;
  $("#sides").innerHTML = sideHtml(me.side) + sideHtml(me.side === "A" ? "B" : "A");
  $("#prompt").innerHTML = promptHtml();
  $("#actionbox").hidden = S.need !== "choose";
  if (S.need !== "choose") ui.sceneAction = null;
  $("#tabs").innerHTML = TABS.map((t) => `<button data-tab="${t}" aria-pressed="${t === ui.tab}">${t}</button>`).join("");
  $("#scenepick").innerHTML = ui.sceneAction ? `<div class="row"><b>去哪个场景？</b>${scenes.map((s) => `<button data-scene="${esc(s)}">${esc(s)}</button>`).join("")}<button>取消</button></div>` : "";
  $("#actions").innerHTML = actionsHtml();
  const log = $("#log");
  log.innerHTML = logHtml(); log.scrollTop = log.scrollHeight;
}

function render() {
  if (!S) return;
  if (S.phase === "lobby") renderLobby(); else renderBattle();
}

renderJoin();
