"use strict";
// 对战舞台：两个人物、血条和状态、高度标尺，以及把服务器发来的事件一条一条播成动画。
// 这里不懂规则。它只知道“某一方掉了多少血”“某一方用了什么招”这类已经发生的事。

const ATTR_COLOR = {
  "物理": "#b5482f", "魔法": "#7a4fd1", "特技": "#d9822b", "地理": "#2f7fa8",
  "化学": "#8a9a1c", "生物": "#3d8f4f", "神技": "#d4a514", "物品": "#6b7280",
};
const GOOD_STATUS = ["氪", "真空", "狂龙", "道威", "无敌"];
const BEAM_EFFECTS = ["xray", "gamma", "aurora", "sound_wave", "sunspot"];

// 每个招用哪一种通用动画。以后想给某个招单独做动画，在 SIGNATURE_ANIMS 里按招的 id 加一项。
const SIGNATURE_ANIMS = {};
function animOf(ev) {
  if (SIGNATURE_ANIMS[ev.id]) return SIGNATURE_ANIMS[ev.id];
  const a = ev.attributes || [];
  if (["switch", "defense", "skip"].includes(ev.action_kind) || ev.effect === "swap_character") return "none";
  if (["collect", "build", "scene", "learn"].includes(ev.action_kind)) return "collect";
  if (ev.target === ev.side) return "self";
  if (BEAM_EFFECTS.includes(ev.effect)) return "beam";
  if (a.includes("神技")) return "shen";
  if (a.includes("地理")) return "field";
  if (a.includes("生物")) return "swarm";
  if (a.includes("魔法") || a.includes("化学") || a.includes("特技")) return "projectile";
  return "melee";
}

// ---------- 音效：用浏览器自带的合成器现做，不需要任何声音文件 ----------
const Sfx = {
  ctx: null, muted: false,
  tone(freq, ms, type = "square", gain = 0.06, slide = 0) {
    if (this.muted) return;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      const t = this.ctx.currentTime, o = this.ctx.createOscillator(), g = this.ctx.createGain();
      o.type = type; o.frequency.setValueAtTime(freq, t);
      if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq + slide), t + ms / 1000);
      g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + ms / 1000);
      o.connect(g).connect(this.ctx.destination); o.start(t); o.stop(t + ms / 1000);
    } catch (e) { /* 没有声音设备也不影响游戏 */ }
  },
  cast() { this.tone(420, 140, "triangle", 0.05, 300); },
  hit() { this.tone(160, 120, "sawtooth", 0.08, -90); },
  heal() { this.tone(660, 180, "sine", 0.05, 240); },
  block() { this.tone(900, 80, "square", 0.04, -300); },
  down() { this.tone(220, 420, "sawtooth", 0.07, -170); },
  zei() { this.tone(520, 70, "square", 0.04); },
  win() { [523, 659, 784].forEach((f, i) => setTimeout(() => this.tone(f, 200, "triangle", 0.06), i * 140)); },
};

class Stage {
  constructor(root, mySide, sceneList) {
    this.root = root; this.me = mySide; this.foe = mySide === "A" ? "B" : "A";
    this.speed = 1; this.skipping = false; this.model = null; this.spriteName = {};
    this.labels = null;       // 观战和回放时两边显示玩家的名字，不显示“你”和“对手”
    const heights = {};
    for (const s of sceneList) (heights[s.height] = heights[s.height] || []).push(s.name);
    this.layers = Object.keys(heights).map(Number).sort((a, b) => b - a).map((h) => ({ h, names: heights[h] }));
    // 每一方：左上角或右上角一块牌子（头像、名字、血条、状态），下面是人物。
    // .extra 那一格归 app.js 填（内功、场下的人物、物品）。
    const fighter = (side, where) => `<div class="fighter ${where}" data-side="${side}">
        <div class="corner"><div class="hud"></div><div class="extra" data-extra="${side}"></div></div>
        <div class="sprite"></div></div>`;
    root.innerHTML = `${fighter(this.me, "left")}<div class="gauge"></div>${fighter(this.foe, "right")}
      <div class="fx"></div><div class="banner" hidden></div><div class="zeibox" hidden></div>`;
    this.fx = root.querySelector(".fx");
  }
  // 怎么称呼一方：上场的人看到“你”“对手”，观战和回放看到名字。
  who(side) { return this.labels ? this.labels[side] : (side === this.me ? "你" : "对手"); }
  // 把“A的武圣”这种写法换成“你的武圣”“对手的武圣”。
  personal(text) {
    if (this.labels) return String(text || "");
    return String(text || "").split(this.me + "的").join("你的").split(this.foe + "的").join("对手的");
  }

  // ---------- 显示当前局面 ----------

  setModel(model) {
    this.model = JSON.parse(JSON.stringify(model));
    for (const side of ["A", "B"]) { this.hud(side); this.sprite(side); }
    this.gauge();
  }
  box(side) { return this.root.querySelector(`.fighter[data-side="${side}"]`); }
  f(side) { return this.model[side]; }

  hud(side) {
    const f = this.f(side), el = this.box(side).querySelector(".hud");
    if (!f) { el.innerHTML = ""; return; }
    const pct = (a, b) => Math.max(0, Math.min(100, (100 * a) / Math.max(1, b)));
    const chips = [];
    for (const [n, s] of Object.entries(f.statuses || {})) chips.push(`<span class="chip ${GOOD_STATUS.includes(n) ? "good" : "bad"}" data-tip="status:${esc(n)}">${esc(n)} ${s.turns} 回合</span>`);
    for (const [n, p] of Object.entries(f.parasites || {})) {
      // 控制绦虫每到第 5 个回合才控制一次：写出还差几回合，不然看不出它什么时候起作用
      const left = n === "控制绦虫" && p.age != null ? 4 - (p.age % 5) : null;
      const when = left == null ? "" : left === 0 ? "（这回合控制）" : `（再过 ${left} 回合控制）`;
      chips.push(`<span class="chip bad" data-tip="parasite:${esc(n)}">${esc(n)}×${p.count}${when}</span>`);
    }
    if (f.radiation) chips.push(`<span class="chip bad" data-tip="text:辐射满 15 次丢一条命，大难不死救不回来。">辐射 ${f.radiation}/15</span>`);
    const lives = f.lives_total > 1 ? `<span class="lives" title="还有 ${Math.max(0, f.lives_remaining)} 条命，一共 ${f.lives_total} 条">${"●".repeat(Math.max(0, f.lives_remaining))}${"○".repeat(Math.max(0, f.lives_total - f.lives_remaining))}</span>` : "";
    const shown = f.name || "？";
    const face = ART.has(f.name) ? `<img alt="" src="assets/characters/${encodeURIComponent(f.name)}.png">` : `<i>${esc(shown.slice(0, 1))}</i>`;
    // 头像：鼠标放上去出这个人物的魂印
    el.innerHTML = `
      <div class="plate">
        <button class="face" data-tip="soul:${esc(f.name)}" data-detail="${side}" aria-label="${esc(shown)}的魂印">${face}</button>
        <div class="vit">
          <div class="who-row"><b class="name">${esc(shown)}</b>${lives}<span class="who">${esc(this.labels ? this.labels[side] : (side === this.me ? "你" : "对手"))}</span></div>
          ${f.max_shield ? `<div class="bar shield"><i style="width:${pct(f.shield, f.max_shield)}%"></i><span>盾 ${f.shield} / ${f.max_shield}</span></div>` : ""}
          <div class="bar"><i style="width:${pct(f.hp, f.max_hp)}%"></i><span>${f.hp} / ${f.max_hp}</span></div>
          <div class="where"><span data-tip="scene:${esc(f.scene)}">${esc(f.scene)} · 高度 ${f.height}</span></div>
        </div>
      </div>
      <div class="chips">${chips.join("")}</div>`;
  }

  sprite(side) {
    const f = this.f(side), el = this.box(side).querySelector(".sprite");
    if (!f) { el.innerHTML = ""; this.spriteName[side] = null; return; }
    el.classList.toggle("down", !!f.defeated);
    if (this.spriteName[side] === f.name) return;
    this.spriteName[side] = f.name;
    const shown = f.name || "？";
    // 鼠标放到人物身上出魂印，点一下看详情
    const hover = `data-tip="soul:${esc(f.name)}" data-detail="${side}"`;
    const standIn = `<div class="stand-in" ${hover}><span>${esc(shown.slice(0, 1))}</span><small>${esc(shown)}</small></div>`;
    // 原画是白底黑线的线稿。放在深色舞台上：线反成亮色，人物的轮廓里垫一层深蓝（用原画自己当蒙版）。
    const src = `assets/characters/${encodeURIComponent(f.name)}.png`;
    el.innerHTML = ART.has(f.name)
      ? `<div class="cutout" ${hover} style="--art:url('${src}')"><img alt="${esc(f.name)}" src="${src}"></div>` : standIn;
  }

  gauge() {
    const m = this.model, water = m.water;
    this.root.querySelector(".gauge").innerHTML = this.layers.map((l) => {
      const mark = (side) => (m[side] && m[side].height === l.h && !m[side].defeated ? `<i class="mark ${side === this.me ? "mine" : "theirs"}"></i>` : `<i class="mark"></i>`);
      const here = (name) => ["A", "B"].some((s) => m[s] && m[s].scene === name);
      const wet = l.h >= 0 && l.h <= water;
      // 地面这一层有好几个场景：只写有人在的那几个，没人在就写“地面这一层”
      const busy = l.names.filter(here);
      const label = l.names.length > 2
        ? (busy.length ? busy.map((n) => `<b>${esc(n)}</b>`).join(" · ") : "地面这一层")
        : l.names.map((n) => (here(n) ? `<b>${esc(n)}</b>` : esc(n))).join(" · ");
      return `<div class="layer ${wet ? "wet" : ""}">${mark(this.me)}<span>${label}</span>${mark(this.foe)}</div>`;
    }).join("");
  }

  // ---------- 动画的小工具 ----------

  // 页面在后台（切到别的标签页）时浏览器会把计时器拖得很慢，所以这时不播动画，直接跳到结果。
  get fast() { return this.skipping || document.hidden; }
  wait(ms) { return this.fast ? Promise.resolve() : new Promise((r) => setTimeout(r, ms / this.speed)); }
  anim(el, frames, ms, easing = "ease-out") {
    if (this.fast || !el || !el.animate) return Promise.resolve();
    const duration = ms / this.speed;
    const done = el.animate(frames, { duration, easing }).finished.catch(() => {});
    // 浏览器不画这个页面的时候（窗口被完全挡住，或者标签页在后台），动画不会走完。
    // 多等一小会儿还没完就不等了，免得整个界面卡在“正在播放”。
    return Promise.race([done, new Promise((r) => setTimeout(r, duration + 400))]);
  }
  center(side) {
    const a = this.box(side).querySelector(".sprite").getBoundingClientRect(), b = this.root.getBoundingClientRect();
    return { x: a.left - b.left + a.width / 2, y: a.top - b.top + a.height / 2 };
  }
  dir(side) { return side === this.me ? 1 : -1; }
  spawn(cls, x, y, html = "") {
    const el = document.createElement("div");
    el.className = cls; el.style.left = x + "px"; el.style.top = y + "px"; el.innerHTML = html;
    this.fx.appendChild(el);
    return el;
  }
  // 人物头顶在舞台里的位置。原画是靠下摆放、按比例缩小的，所以要按图片的长宽比算出它实际有多高。
  head(side) {
    const box = this.box(side).querySelector(".sprite"), a = box.getBoundingClientRect(), b = this.root.getBoundingClientRect();
    const img = box.querySelector("img"), inner = box.firstElementChild;
    let height = a.height;
    if (img && img.naturalWidth) height = Math.min(a.height, a.width * img.naturalHeight / img.naturalWidth);
    else if (inner) height = inner.getBoundingClientRect().height || a.height;
    return { x: a.left - b.left + a.width / 2, y: a.bottom - b.top - height };
  }
  // 头顶上跳出来的字：掉血、回血、状态、MISS。字大，先弹出来，停一会儿，再往上飘走。
  pop(side, text, cls = "") {
    if (this.fast) return;
    const h = this.head(side), n = this.fx.querySelectorAll(".pop").length;
    const el = this.spawn("pop " + cls, h.x + ((n % 3) - 1) * 54, Math.max(86, h.y - 30) - (n % 4) * 30, esc(text));
    const frames = [
      { transform: "translate(-50%, 8px) scale(.5)", opacity: 0, offset: 0 },
      { transform: "translate(-50%, 0) scale(1.18)", opacity: 1, offset: 0.1 },
      { transform: "translate(-50%, 0) scale(1)", opacity: 1, offset: 0.18 },
      { transform: "translate(-50%, -16px) scale(1)", opacity: 1, offset: 0.78 },
      { transform: "translate(-50%, -40px) scale(1)", opacity: 0, offset: 1 },
    ];
    this.anim(el, frames, 2000, "ease-out").then(() => el.remove());
  }
  async say(side, text, color) {
    if (this.fast) return;
    const c = this.center(side);
    const el = this.spawn("say", c.x, c.y - 96, esc(text));
    if (color) el.style.borderColor = el.style.color = color;
    await this.anim(el, [{ transform: "translate(-50%, 8px) scale(.8)", opacity: 0 }, { transform: "translate(-50%, 0) scale(1)", opacity: 1 }], 160);
    this.wait(650).then(() => this.anim(el, [{ opacity: 1 }, { opacity: 0 }], 200)).then(() => el.remove());
  }
  shake(side) {
    const s = this.box(side).querySelector(".sprite");
    return this.anim(s, [{ transform: "translateX(0)" }, { transform: "translateX(-9px)" }, { transform: "translateX(8px)" }, { transform: "translateX(-5px)" }, { transform: "translateX(0)" }], 260);
  }
  flash(side, color = "#fff") {
    const s = this.box(side).querySelector(".sprite");
    return this.anim(s, [{ filter: "none" }, { filter: `drop-shadow(0 0 14px ${color}) brightness(1.6)` }, { filter: "none" }], 300);
  }
  // 贼出了结果：把双方每一把出的拳、谁赢了、赢了以后怎么样，摆在舞台中间给大家看。
  async zeiResult(ev) {
    Sfx.zei();
    const el = this.root.querySelector(".zeibox"), L = this.me, R = this.foe, rounds = ev.rounds || [];
    if (this.fast) { el.hidden = true; return; }
    const rows = rounds.slice(-4).map((r) => `<div class="zr"><span>${HAND_GLYPH[r[L]] || "？"}<small>${esc(r[L] || "")}</small></span>
      <i>${r[L] === r[R] ? "打平" : "对"}</i><span>${HAND_GLYPH[r[R]] || "？"}<small>${esc(r[R] || "")}</small></span></div>`).join("");
    const result = ev.winner == null ? "打平" : this.who(ev.winner) + "赢";
    const tone = ev.winner === L ? "win" : ev.winner === R ? "lose" : "";
    const open = !el.hidden;                     // 出拳的时候这个框就开着：结果接着写在同一个框里
    el.innerHTML = `<div class="zt">贼：${esc(this.personal(ev.reason))}</div>
      <div class="zn"><b>${esc(this.who(L))}</b><b>${esc(this.who(R))}</b></div>${rows}
      <div class="zw ${tone}">${esc(result)}${ev.outcome ? "：" + esc(this.personal(ev.outcome)) : ""}</div>`;
    el.hidden = false;
    if (!open) await this.anim(el, [{ opacity: 0 }, { opacity: 1 }], 160);
    await this.wait(1600);
    el.hidden = true;
  }
  async announce(text, ms = 700) {
    if (this.fast) return;
    const el = this.root.querySelector(".banner");
    el.textContent = text; el.hidden = false;
    await this.anim(el, [{ opacity: 0, transform: "translate(-50%, -8px)" }, { opacity: 1, transform: "translate(-50%, 0)" }], 160);
    await this.wait(ms);
    el.hidden = true;
  }

  // ---------- 出招的几种通用动画 ----------

  async moveAnim(ev) {
    const kind = animOf(ev), from = ev.side, to = ev.target, color = ATTR_COLOR[(ev.attributes || [])[0]] || "#444";
    const actor = this.box(from).querySelector(".sprite"), d = this.dir(from);
    if (kind === "none" || this.fast) return;
    Sfx.cast();
    if (kind === "melee") {
      const a = this.center(from), b = this.center(to), dx = (b.x - a.x) * 0.72;
      await this.anim(actor, [{ transform: "translateX(0)" }, { transform: `translateX(${-18 * d}px)` }, { transform: `translateX(${dx}px)` }], 300, "ease-in");
      this.anim(actor, [{ transform: `translateX(${dx}px)` }, { transform: "translateX(0)" }], 260);
      return;
    }
    if (kind === "self" || kind === "collect") {
      const c = this.center(from);
      const ring = this.spawn("ring", c.x, c.y);
      ring.style.borderColor = color;
      this.anim(actor, [{ transform: "scale(1)" }, { transform: "scale(1.08)" }, { transform: "scale(1)" }], 380);
      await this.anim(ring, [{ transform: "translate(-50%,-50%) scale(.3)", opacity: .9 }, { transform: "translate(-50%,-50%) scale(1.5)", opacity: 0 }], 460);
      ring.remove();
      return;
    }
    const a = this.center(from), b = this.center(to);
    await this.anim(actor, [{ transform: "translateX(0)" }, { transform: `translateX(${-10 * d}px)` }, { transform: `translateX(${8 * d}px)` }, { transform: "translateX(0)" }], 220);
    if (kind === "beam") {
      const len = Math.hypot(b.x - a.x, b.y - a.y), angle = Math.atan2(b.y - a.y, b.x - a.x);
      const beam = this.spawn("beam", a.x, a.y);
      beam.style.width = len + "px"; beam.style.background = color; beam.style.transform = `rotate(${angle}rad) scaleX(0)`;
      await this.anim(beam, [{ transform: `rotate(${angle}rad) scaleX(0)`, opacity: 1 }, { transform: `rotate(${angle}rad) scaleX(1)`, opacity: 1 }], 200);
      await this.anim(beam, [{ opacity: 1 }, { opacity: 0 }], 220);
      beam.remove();
      return;
    }
    if (kind === "field") {
      this.anim(this.root, [{ transform: "translate(0,0)" }, { transform: "translate(-6px,3px)" }, { transform: "translate(6px,-3px)" }, { transform: "translate(-4px,2px)" }, { transform: "translate(0,0)" }], 420);
      const wave = this.spawn("wave", a.x, b.y + 46);
      wave.style.background = color;
      await this.anim(wave, [{ transform: "translateX(0) scaleX(.2)", opacity: .8 }, { transform: `translateX(${b.x - a.x}px) scaleX(1.6)`, opacity: 0 }], 520);
      wave.remove();
      return;
    }
    const count = kind === "swarm" ? 3 : 1, big = kind === "shen";
    await Promise.all(Array.from({ length: count }, async (_, i) => {
      await this.wait(i * 90);
      const orb = this.spawn("orb" + (big ? " big" : ""), a.x, a.y);
      orb.style.background = color;
      const lift = kind === "swarm" ? -30 - i * 14 : -12;
      await this.anim(orb, [{ transform: "translate(-50%,-50%)" }, { transform: `translate(calc(-50% + ${(b.x - a.x) / 2}px), calc(-50% + ${lift}px))` }, { transform: `translate(calc(-50% + ${b.x - a.x}px), calc(-50% + ${b.y - a.y}px))` }], big ? 420 : 320, "linear");
      orb.remove();
    }));
    if (big) {
      const burst = this.spawn("ring", b.x, b.y);
      burst.style.borderColor = color;
      this.anim(burst, [{ transform: "translate(-50%,-50%) scale(.2)", opacity: 1 }, { transform: "translate(-50%,-50%) scale(2.2)", opacity: 0 }], 420).then(() => burst.remove());
    }
  }

  vitals(side, ev) {
    const f = this.f(side); if (!f) return;
    for (const k of ["hp", "max_hp", "shield", "max_shield"]) if (ev[k] !== undefined) f[k] = ev[k];
    if (ev.lives !== undefined) { f.lives_remaining = ev.lives; f.lives_total = ev.lives_total; }
    this.hud(side);
  }

  // ---------- 播放一条事件 ----------

  async play(ev, view) {
    const f = ev.side ? this.f(ev.side) : null;
    switch (ev.t) {
      case "round":
        await this.announce(`第 ${ev.n} 回合`, 500);
        for (const side of ["A", "B"]) this.say(side, ev.choices[side].name);
        return this.wait(750);
      case "switch": {
        const sprite = this.box(ev.side).querySelector(".sprite"), d = this.dir(ev.side);
        await this.anim(sprite, [{ transform: "translateX(0)", opacity: 1 }, { transform: `translateX(${-70 * d}px)`, opacity: 0 }], 240, "ease-in");
        // 上场的人物以事件里带的为准。网页手里的局面可能还是他上场之前的（那时候对手的这个人物还没亮出来）。
        const listed = view && view.players[ev.side].team[ev.index];
        const full = ev.fighter || (listed && !listed.hidden ? listed : { name: ev.name });
        this.model[ev.side] = Object.assign(JSON.parse(JSON.stringify(full)), {
          hp: ev.hp, max_hp: ev.max_hp, shield: ev.shield, max_shield: ev.max_shield, lives_remaining: ev.lives,
          lives_total: ev.lives_total, scene: ev.scene, height: ev.height, statuses: {}, parasites: {}, defeated: false });
        this.hud(ev.side); this.sprite(ev.side); this.gauge();
        await this.anim(sprite, [{ transform: `translateX(${-70 * d}px)`, opacity: 0 }, { transform: "translateX(0)", opacity: 1 }], 260);
        return this.wait(150);
      }
      case "swap_fighters": {           // 范仲淹的换人：两边场上的人物互换
        const sprites = ["A", "B"].map((side) => [this.box(side).querySelector(".sprite"), this.dir(side)]);
        await Promise.all(sprites.map(([el, d]) =>
          this.anim(el, [{ transform: "translateX(0)", opacity: 1 }, { transform: `translateX(${90 * d}px)`, opacity: 0 }], 280, "ease-in")));
        for (const side of ["A", "B"]) {
          this.model[side] = JSON.parse(JSON.stringify(ev.fighters[side]));
          this.hud(side); this.sprite(side);
        }
        this.gauge();
        await Promise.all(sprites.map(([el, d]) =>
          this.anim(el, [{ transform: `translateX(${90 * d}px)`, opacity: 0 }, { transform: "translateX(0)", opacity: 1 }], 300)));
        this.pop(ev.side, "换人", "note");
        return this.wait(250);
      }
      case "move":
        this.say(ev.side, ev.name, ATTR_COLOR[(ev.attributes || [])[0]]);
        await this.moveAnim(ev);
        return this.wait(80);
      case "damage":
        Sfx.hit();
        this.pop(ev.side, "-" + ev.amount, ev.layer === "shield" ? "shield" : "hurt");
        this.vitals(ev.side, ev);
        this.flash(ev.side, ev.layer === "shield" ? "#6a9cf0" : "#e5533d");
        await this.shake(ev.side);
        return this.wait(120);
      case "heal":
        if (ev.amount) { Sfx.heal(); this.pop(ev.side, "+" + ev.amount, "heal"); }
        this.vitals(ev.side, ev);
        await this.flash(ev.side, "#49c27a");
        return;
      case "swap_hp":
        for (const side of ["A", "B"]) { this.vitals(side, ev.vitals[side]); this.flash(side, "#d4a514"); }
        return this.wait(400);
      case "miss": this.pop(ev.side, "MISS", "miss"); return this.anim(this.box(ev.side).querySelector(".sprite"), [{ transform: "translateY(0)" }, { transform: "translateY(-22px)" }, { transform: "translateY(0)" }], 300);
      case "immune": this.pop(ev.side, "无效", "note"); return this.wait(300);
      case "block": Sfx.block(); this.pop(ev.side, "防住了", "note"); await this.flash(ev.side, "#6a9cf0"); return;
      case "reflect": Sfx.block(); this.pop(ev.side, "反弹", "note"); await this.flash(ev.side, "#9fd8ff"); return;
      case "defend_miss": this.pop(ev.side, "没防住", "note"); return this.wait(200);
      case "sealed": this.pop(ev.side, "被憋回去", "note"); return this.wait(450);
      case "stifle": this.pop(ev.side, "神技被憋", "note"); return this.wait(450);
      case "cancel": this.pop(ev.side, "行动取消", "note"); return this.wait(300);
      case "skip": this.pop(ev.side, ev.why + "，不能出招", "note"); return this.wait(300);
      case "status":
        if (f) { f.statuses[ev.name] = { turns: ev.turns }; this.hud(ev.side); }
        this.pop(ev.side, (ev.good ? "＋" : "") + ev.name + " " + ev.turns, ev.good ? "heal" : "bad");
        return this.wait(260);
      case "status_end":
        if (f) { delete f.statuses[ev.name]; this.hud(ev.side); }
        return;
      case "parasite":
        if (f) { f.parasites[ev.name] = { count: (f.parasites[ev.name] ? f.parasites[ev.name].count : 0) + ev.count }; this.hud(ev.side); }
        this.pop(ev.side, ev.name + " ×" + ev.count, "bad");
        return this.wait(260);
      case "clash":                    // 两边出了同一个招：直接抵消
        Sfx.block();
        for (const side of ["A", "B"]) this.pop(side, "抵消", "note");
        await this.announce("同一个招，抵消", 700);
        return;
      case "parasite_end":
        if (f) { delete f.parasites[ev.name]; this.hud(ev.side); }
        this.pop(ev.side, ev.name + "没了", "heal");
        return this.wait(200);
      case "ray": Sfx.cast(); this.pop(ev.side, ev.ray + " 射线", "bad"); await this.flash(ev.side, "#b6f04a"); return;
      case "radiation":
        if (f) { f.radiation = ev.total; this.hud(ev.side); }
        this.pop(ev.side, "辐射 +" + ev.amount, "bad");
        return this.wait(260);
      case "scene":
        if (f) { f.scene = ev.scene; f.height = ev.height; this.hud(ev.side); this.gauge(); }
        this.pop(ev.side, "→ " + ev.scene, "note");
        return this.anim(this.box(ev.side).querySelector(".sprite"), [{ transform: "translateY(0)" }, { transform: "translateY(-30px)" }, { transform: "translateY(0)" }], 340);
      case "water": this.model.water = ev.level; this.gauge(); return this.announce("水面上升", 450);
      case "collect": this.pop(ev.side, "+" + ev.quantity + " " + ev.resource, "heal"); return this.wait(240);
      case "revive": Sfx.heal(); this.vitals(ev.side, ev); this.pop(ev.side, "大难不死", "heal"); await this.flash(ev.side, "#d4a514"); return;
      case "life_lost":
        Sfx.down();
        this.vitals(ev.side, ev);
        if (ev.defeated) {
          if (f) f.defeated = true;
          this.pop(ev.side, "倒下", "hurt");
          await this.anim(this.box(ev.side).querySelector(".sprite"), [{ transform: "rotate(0)", opacity: 1 }, { transform: `rotate(${70 * this.dir(ev.side)}deg) translateY(30px)`, opacity: .25 }], 480, "ease-in");
          this.sprite(ev.side);
        } else {
          this.pop(ev.side, "失去一条命", "hurt");
          await this.flash(ev.side, "#e5533d");
        }
        return this.wait(200);
      case "respawn":
        if (f) { f.statuses = {}; f.parasites = {}; f.radiation = 0; f.scene = ev.scene; f.height = ev.height; }
        this.vitals(ev.side, ev); this.gauge();
        return this.flash(ev.side, "#fff");
      case "divine": this.pop(ev.side, "占卜：" + ev.attribute, "note"); return this.wait(400);
      case "divine_hit": Sfx.heal(); this.vitals(ev.side, ev); this.pop(ev.side, "占中了", "heal"); await this.flash(ev.side, "#d4a514"); return;
      case "evolve":
        if (f) { f.name = ev.new; f.statuses = f.statuses || {}; }
        this.vitals(ev.side, ev); this.sprite(ev.side);
        this.pop(ev.side, ev.why + "：" + ev.new, "heal");
        await this.flash(ev.side, "#d4a514");
        return this.wait(300);
      case "learn":
        if (ev.leveled) Sfx.heal();
        this.pop(ev.side, ev.leveled ? ev.name + " 升到 " + ev.level + " 级" : "学" + ev.name + " " + ev.progress, ev.leveled ? "heal" : "note");
        return this.wait(300);
      case "build":
        if (f) { f.devices = f.devices || {}; f.devices[ev.name] = ev.progress; }
        this.pop(ev.side, ev.name + " " + ev.progress + "/" + ev.of, "note");
        return this.wait(300);
      case "loan": this.pop(ev.side, "借了" + ev.source + "的" + ev.name + ev.level + "级", "note"); return this.wait(350);
      case "control": this.pop(ev.side, "被虫子控制", "bad"); return this.wait(350);
      case "crit": this.pop(ev.side, "暴击", "hurt"); return this.wait(150);
      case "zei": return this.zeiResult(ev);
      case "phase": return this.wait(200);
      case "end": Sfx.win(); return this.announce("对战结束", 900);
      default: return;
    }
  }
}
