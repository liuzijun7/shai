// 在 Node 里用一个假的页面跑网页客户端拼文字的那些函数，抓运行时的错误。
// 由 tests/test_client.py 调用：node tests/client_check.js <一个 json 文件>，文件里是一局的局面和图鉴。
const fs = require("fs"), vm = require("vm"), path = require("path");
const root = path.join(__dirname, "..");
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

const el = () => ({
  innerHTML: "", textContent: "", hidden: false, value: "", dataset: {}, style: {}, className: "", offsetWidth: 10, offsetHeight: 10,
  classList: { toggle() {}, add() {}, remove() {} }, querySelector: () => el(), querySelectorAll: () => [], insertAdjacentHTML() {},
  appendChild() {}, scrollIntoView() {}, focus() {}, remove() {}, contains: () => true, addEventListener() {}, getAttribute: () => null,
  getBoundingClientRect: () => ({ left: 0, top: 0, right: 10, bottom: 10, width: 10, height: 10 }), animate: () => ({ finished: Promise.resolve() }),
});
const ctx = {
  console, setInterval() {}, setTimeout, clearTimeout, performance: { now: () => 0 },
  fetch: async () => ({ ok: true, json: async () => input.codex }),
  location: { hash: "", protocol: "http:", host: "x", reload() {} }, localStorage: { getItem: () => null, setItem() {} },
  sessionStorage: { getItem: () => null, setItem() {} }, WebSocket: function () {},
  window: { innerWidth: 1200, innerHeight: 800 },
  document: { querySelector: () => el(), createElement: () => el(), addEventListener() {}, body: el(), hidden: false, activeElement: null },
};
vm.createContext(ctx);
const code = fs.readFileSync(path.join(root, "web/stage.js"), "utf8") + "\n" + fs.readFileSync(path.join(root, "web/app.js"), "utf8") + `
;globalThis.__check = async (state, who, art) => {
  await loadCodex();
  me = who; S = state; S.at = 0; playing = false; replay = null; ART = new Set(art.characters); DEF_ART = new Set(art.defense);
  const out = { problems: [], cards: 0 };
  const need = (ok, what) => { if (!ok) out.problems.push(what); };
  for (const mode of ["moves", "items", "switch"]) { ui.mode = mode; ui.search = ""; need(actionsHtml().length > 0, "操作区是空的：" + mode); }
  ui.mode = "moves";
  for (const a of S.actions) {
    const card = cardHtml(a, "", false), tip = tipHtml("act:" + a.id);
    out.cards++;
    need(card.includes("mvname"), "卡片没有名字：" + a.name);
    need(tip.includes("t-head"), "描述框没有标题：" + a.name);
    need(/t-(stat|text|flag|note)/.test(tip), "描述框没有内容：" + a.name);
    need(!/undefined|NaN|\\[object/.test(card + tip), "出现了 undefined 之类的字：" + a.name);
  }
  ui.search = "hc";
  const found = actionsHtml();
  need(found.includes("寒") && found.indexOf("寒") < 400, "打 hc 没有先搜到寒潮");
  ui.search = "";
  for (const side of ["A", "B"]) {
    need(!/undefined|NaN/.test(extraHtml(side)), "牌子下面那一行小标签有问题：" + side);
    need(!/undefined|NaN/.test(benchHtml(side)), "场下的人物那一排有问题：" + side);
  }
  ui.mode = "switch";
  const team = teamHtml();
  need(team.includes('class="tm now"') && !/undefined|NaN/.test(team), "换人卡拼不出来");
  need(centerText() === "换谁上场", "换人的时候正中间的字不对");
  ui.mode = "moves";
  need(/class="edge"/.test(cardHtml(S.actions[0], "", false)), "技能卡没有切角的边");
  need(barHtml(117000, 150000, { right: true }).includes("--p:78%"), "血条的长短不对");
  need(typeof hintHtml() === "string", "页签旁边的小字拼不出来");
  showDetail("A"); showDetail("B");
  for (const key of ["soul:武圣", "inner:幻影:4", "status:昏睡", "parasite:蚂蟥", "scene:南极", "text:随便一句"]) need(tipHtml(key).length > 0, "没有描述：" + key);
  need(defenseRowHtml().split("<button").length === 7, "防御那一排不是六个");
  need(topHtml().includes("回合") && sideHtml().includes("战报") && centerText() === "请选招", "舞台上方的字不对");
  need(typeof promptHtml() === "string" && typeof zeiPanelHtml() === "string" && typeof clockText() === "string", "提示文字拼不出来");
  for (const tab of CODEX_TABS) { cx.tab = tab; cx.q = ""; cx.key = null; need(codexHtml().includes("cxname"), "图鉴这一页是空的：" + tab); }
  cx.tab = "招式"; cx.q = "hc";
  need(codexHtml().includes("寒潮"), "图鉴里打 hc 搜不到寒潮");
  const st = new Stage(document.querySelector("#stage"), "A", [{ name: "地面", height: 0 }]);
  st.setModel(modelOf(S.view));
  await st.zeiResult({ reason: "A的武圣先出手", winner: "A", rounds: [{ A: "石头", B: "石头" }, { A: "布", B: "石头" }], outcome: "A的武圣先出手" });
  return out;
};`;
vm.runInContext(code, ctx);
ctx.__check(input.state, { side: "A", role: "play", room: "1", name: "甲" }, input.art).then((out) => {
  console.log(JSON.stringify(out));
}).catch((error) => { console.log(JSON.stringify({ problems: ["运行出错：" + (error && error.stack || error)], cards: 0 })); });
