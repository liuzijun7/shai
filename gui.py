"""Tkinter 可视化界面。只使用 Python 标准库。"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from engine import GameEngine, RuleError
from game_data import CHARACTERS, SCENES


COLORS = {
    "bg": "#0f172a",
    "panel": "#172033",
    "panel2": "#1e293b",
    "text": "#e5edf8",
    "muted": "#93a4b8",
    "accent": "#38bdf8",
    "green": "#34d399",
    "red": "#fb7185",
    "yellow": "#fbbf24",
    "border": "#334155",
}

EFFECT_TEXTS = {
    "meteor": "每拳后有50%概率继续攻击。",
    "rise_self": "使用后自身向上移动一层。",
    "death_note": "令目标进入黑暗之城，并有12.5%概率杀死目标当前命。",
    "flood": "水面上升一层。",
    "lower_target": "令目标下降一层。",
    "antarctic": "令目标前往南极，并立即附加昏睡。",
    "sound_wave": "目标处于真空环境时无效。",
    "aurora": "只能在南极使用。",
    "pork_tapeworm": "附加猪带绦虫：每条每回合吸取体力上限10%，每5回合繁殖。",
    "sleep_tapeworm": "附加昏睡绦虫，并立即触发一次昏睡。",
    "leech": "附加蚂蟥：每条每回合吸取体力上限20%。",
    "ultimate_drain": "吸取目标体力上限80%的血量。",
    "xray": "给目标增加5点辐射。",
    "drop_ground": "目标若高于地面则掉落到地面。",
    "sunspot": "消耗3星体能量；高处目标落地，全部内功降一级。",
    "gamma": "消耗1超新星和5星体能量；造成15辐射并杀死当前人物所有命。",
    "self_status": "给自身附加对应状态。",
    "self_status_and_damage": "造成伤害，并给自身附加对应强化状态。",
    "sulfuric_acid": "附加点燃；生化大师使用时改为50%概率秒杀。",
    "ether": "两回合后附加昏睡5；目标烧伤或点燃时额外损失上限50%。",
    "rebirth": "清除除辐射外的不良状态和寄生虫，体力回满，当回合无敌。",
    "panacea": "消耗1个万灵丹，清除不良状态和寄生虫。",
    "collect_supernova": "收集超新星，占用本回合行动。",
    "collect_star": "收集星体能量，占用本回合行动。",
    "collect_oxygen": "收集氧气，占用本回合行动。",
    "collect_panacea": "收集万灵丹，占用本回合行动。",
    "collect_glue": "收集后当回合直接获得万能胶5。",
    "collect_wine": "收集酒，占用本回合行动。",
    "drink_wine": "消耗1个酒，当回合无敌，下一回合伤害和特效时长×2。",
    "defend": "防御字段与本动作相同的技能，无视先后手。",
    "mirror": "把防御字段为j的技能完整反弹给使用者，无视先后手。",
    "block_divine": "本回合所有神技变成普通攻击，使用者获得封神3。",
    "choose_scene": "选择并移动到任意场景。",
    "build_yueyang": "建造进度达到5后，全部内功升一级。",
    "build_pyramid": "建造进度达到5后，全部内功升一级。",
    "taotie_fang": "连续攻击2次，造成的伤害加入自身血量。",
    "leech_wave": "视为给目标附加3条蚂蟥。",
    "typhoon": "令目标失去全部物品。",
}


class ShaiGameApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("《晒》双角色规则测试器")
        self.root.geometry("1440x900")
        self.root.minsize(1180, 720)
        self.root.configure(bg=COLORS["bg"])
        self.engine: GameEngine | None = None
        self.action_rows: dict[str, dict] = {}
        self.action_buttons: dict[str, ttk.Button] = {}
        self.hover_action_id: str | None = None
        self.cards: dict[str, dict] = {}
        self._configure_style()
        self._build_setup()

    def run(self):
        self.root.mainloop()

    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"], relief="flat")
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Turn.TLabel", background=COLORS["panel"], foreground=COLORS["accent"], font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("CardTitle.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Muted.Panel.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 7))
        style.configure("Accent.TButton", background=COLORS["accent"], foreground="#06121f", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#7dd3fc"), ("disabled", "#475569")])
        style.configure("Skill.TButton", font=("Microsoft YaHei UI", 9), padding=(4, 4), anchor="center")
        style.configure("Defense.Skill.TButton", background="#334155", foreground="#dbeafe", font=("Microsoft YaHei UI", 9, "bold"), padding=(4, 4))
        style.configure("Collect.Skill.TButton", background="#244535", foreground="#dcfce7", font=("Microsoft YaHei UI", 9), padding=(4, 4))
        style.map("Skill.TButton", background=[("active", "#155e75"), ("disabled", "#293548")], foreground=[("disabled", "#708198")])
        style.map("Defense.Skill.TButton", background=[("active", "#475569"), ("disabled", "#293548")], foreground=[("disabled", "#708198")])
        style.map("Collect.Skill.TButton", background=[("active", "#2f6b4a"), ("disabled", "#293548")], foreground=[("disabled", "#708198")])
        style.configure(
            "HP.Horizontal.TProgressbar",
            troughcolor="#3f1d2a",
            background=COLORS["red"],
            bordercolor=COLORS["panel"],
            thickness=7,
        )
        style.configure("Treeview", background=COLORS["panel2"], fieldbackground=COLORS["panel2"], foreground=COLORS["text"], rowheight=28, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", background="#263449", foreground=COLORS["text"], font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#155e75")], foreground=[("selected", "#ffffff")])
        style.configure("TCombobox", fieldbackground="#ffffff", font=("Microsoft YaHei UI", 10))

    # ---------- setup ----------

    def _build_setup(self):
        self.setup_frame = ttk.Frame(self.root, padding=36)
        self.setup_frame.pack(fill="both", expand=True)
        center = ttk.Frame(self.setup_frame, style="Panel.TFrame", padding=36)
        center.place(relx=0.5, rely=0.46, anchor="center", width=780, height=500)

        ttk.Label(center, text="《晒》双角色规则测试器", style="CardTitle.TLabel").pack(pady=(0, 8))
        ttk.Label(center, text="自己控制 A、B 两个角色，轮流选择动作并核对结算。", style="Muted.Panel.TLabel").pack(pady=(0, 28))

        names = [CHARACTERS[key]["name"] for key in sorted(CHARACTERS, key=lambda x: int(x))]
        form = ttk.Frame(center, style="Panel.TFrame")
        form.pack(fill="x", padx=80)
        ttk.Label(form, text="A 角色", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=10)
        ttk.Label(form, text="B 角色", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=10)
        ttk.Label(form, text="随机种子", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=10)
        self.char_a_var = tk.StringVar(value="陶渊明")
        self.char_b_var = tk.StringVar(value="武圣")
        self.seed_var = tk.StringVar(value="1")
        ttk.Combobox(form, textvariable=self.char_a_var, values=names, state="readonly", width=28).grid(row=0, column=1, sticky="ew", padx=(24, 0))
        ttk.Combobox(form, textvariable=self.char_b_var, values=names, state="readonly", width=28).grid(row=1, column=1, sticky="ew", padx=(24, 0))
        ttk.Entry(form, textvariable=self.seed_var, width=30).grid(row=2, column=1, sticky="ew", padx=(24, 0))
        form.columnconfigure(1, weight=1)

        ttk.Button(center, text="开始测试", style="Accent.TButton", command=self._start_game).pack(pady=(30, 14), ipadx=32)
        ttk.Label(
            center,
            text="A、B依次选招，双方都选完后统一按防御与先制结算。灰色动作表示当前不可执行。",
            style="Muted.Panel.TLabel",
            wraplength=620,
            justify="center",
        ).pack()

    def _start_game(self):
        try:
            seed = int(self.seed_var.get().strip()) if self.seed_var.get().strip() else None
            self.engine = GameEngine(self.char_a_var.get(), self.char_b_var.get(), seed)
        except (ValueError, RuleError) as exc:
            messagebox.showerror("无法开始", str(exc), parent=self.root)
            return
        self.setup_frame.destroy()
        self._build_battle()
        self._refresh_all()

    # ---------- battle layout ----------

    def _build_battle(self):
        self.battle_frame = ttk.Frame(self.root, padding=14)
        self.battle_frame.pack(fill="both", expand=True)

        top = ttk.Frame(self.battle_frame, style="Panel.TFrame", padding=(18, 12))
        top.pack(fill="x", pady=(0, 12))
        self.turn_label = ttk.Label(top, text="", style="Turn.TLabel")
        self.turn_label.pack(side="left")
        ttk.Button(top, text="重新选角", command=self._back_to_setup).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="重开本局", command=self._restart_same).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="保存记录", command=self._save_log).pack(side="right", padx=(8, 0))

        cards = ttk.Frame(self.battle_frame)
        cards.pack(fill="x", pady=(0, 8))
        cards.columnconfigure(0, weight=1, uniform="cards")
        cards.columnconfigure(1, weight=1, uniform="cards")
        self.cards["A"] = self._build_character_card(cards, "A", 0)
        self.cards["B"] = self._build_character_card(cards, "B", 1)

        body = ttk.Panedwindow(self.battle_frame, orient="horizontal")
        body.pack(fill="both", expand=True)

        action_panel = ttk.Frame(body, style="Panel.TFrame", padding=12)
        log_panel = ttk.Frame(body, style="Panel.TFrame", padding=12)
        body.add(action_panel, weight=3)
        body.add(log_panel, weight=2)

        action_header = ttk.Frame(action_panel, style="Panel.TFrame")
        action_header.pack(fill="x", pady=(0, 8))
        ttk.Label(action_header, text="技能与操作", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(action_header, text="悬停查看详情，单击完成选招", style="Muted.Panel.TLabel").pack(side="right")

        action_content = ttk.Frame(action_panel, style="Panel.TFrame")
        action_content.pack(fill="both", expand=True)

        skill_area = ttk.Frame(action_content, style="Panel.TFrame")
        skill_area.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.skill_canvas = tk.Canvas(skill_area, bg=COLORS["panel"], highlightthickness=0, bd=0)
        skill_scroll = ttk.Scrollbar(skill_area, orient="vertical", command=self.skill_canvas.yview)
        self.skill_canvas.configure(yscrollcommand=skill_scroll.set)
        self.skill_canvas.pack(side="left", fill="both", expand=True)
        skill_scroll.pack(side="right", fill="y")
        self.skill_grid = ttk.Frame(self.skill_canvas, style="Panel.TFrame")
        self.skill_window = self.skill_canvas.create_window((0, 0), window=self.skill_grid, anchor="nw")
        self.skill_grid.bind("<Configure>", lambda _event: self.skill_canvas.configure(scrollregion=self.skill_canvas.bbox("all")))
        self.skill_canvas.bind("<Configure>", lambda event: self.skill_canvas.itemconfigure(self.skill_window, width=event.width))

        detail_panel = ttk.Frame(action_content, style="Panel.TFrame", padding=(12, 8), width=285)
        detail_panel.pack(side="right", fill="y")
        detail_panel.pack_propagate(False)
        ttk.Label(detail_panel, text="技能详情", style="CardTitle.TLabel").pack(anchor="w")
        self.detail_title = tk.StringVar(value="把鼠标放在技能上")
        self.detail_state = tk.StringVar(value="")
        self.detail_body = tk.StringVar(value="这里会显示伤害、属性、效果、防御方式、距离、先制和角色特殊效果。")
        ttk.Label(detail_panel, textvariable=self.detail_title, style="Turn.TLabel", wraplength=255, justify="left").pack(anchor="w", pady=(10, 4))
        ttk.Label(detail_panel, textvariable=self.detail_state, style="Muted.Panel.TLabel", wraplength=255, justify="left").pack(anchor="w", pady=(0, 8))
        ttk.Separator(detail_panel, orient="horizontal").pack(fill="x", pady=(0, 8))
        ttk.Label(detail_panel, textvariable=self.detail_body, style="Panel.TLabel", wraplength=255, justify="left").pack(anchor="w", fill="x")
        ttk.Label(detail_panel, text="目标场景", style="Panel.TLabel").pack(anchor="w", pady=(14, 4))
        self.destination_var = tk.StringVar(value="地面")
        self.destination_box = ttk.Combobox(detail_panel, textvariable=self.destination_var, values=list(SCENES), state="disabled", width=18)
        self.destination_box.pack(anchor="w")

        ttk.Label(log_panel, text="对战记录", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.log_text = ScrolledText(
            log_panel, wrap="word", bg="#0b1220", fg=COLORS["text"], insertbackground="white",
            relief="flat", font=("Microsoft YaHei UI", 10), padx=12, pady=10, state="disabled",
        )
        self.log_text.pack(fill="both", expand=True)

    def _build_character_card(self, parent, side, column):
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=(12, 9))
        frame.grid(row=0, column=column, sticky="nsew", padx=(0, 6) if column == 0 else (6, 0))
        title = ttk.Label(frame, text="", style="CardTitle.TLabel")
        title.pack(anchor="w")
        subtitle = ttk.Label(frame, text="", style="Muted.Panel.TLabel")
        subtitle.pack(anchor="w", pady=(1, 5))

        metrics = ttk.Frame(frame, style="Panel.TFrame")
        metrics.pack(fill="x", pady=(0, 5))
        hp_label = ttk.Label(metrics, text="", style="Panel.TLabel")
        hp_label.grid(row=0, column=0, sticky="w")
        hp_bar = ttk.Progressbar(metrics, maximum=100, style="HP.Horizontal.TProgressbar", length=130)
        hp_bar.grid(row=0, column=1, sticky="ew", padx=(7, 16))
        shield_label = ttk.Label(metrics, text="", style="Panel.TLabel")
        shield_label.grid(row=0, column=2, sticky="w", padx=(0, 16))
        radiation_label = ttk.Label(metrics, text="", style="Panel.TLabel")
        radiation_label.grid(row=0, column=3, sticky="w")
        metrics.columnconfigure(1, weight=1)

        details = ttk.Label(frame, text="", style="Muted.Panel.TLabel", justify="left", wraplength=650)
        details.pack(anchor="w", fill="x")
        return {
            "frame": frame, "title": title, "subtitle": subtitle,
            "hp_label": hp_label, "hp_bar": hp_bar,
            "shield_label": shield_label,
            "radiation_label": radiation_label,
            "details": details,
        }

    # ---------- refresh / actions ----------

    def _refresh_all(self):
        if not self.engine:
            return
        current = self.engine.fighters[self.engine.current_side]
        if self.engine.done:
            result = f"对战结束：{self.engine.winner + ' 获胜' if self.engine.winner else '平局'}"
        else:
            selected = "、".join(f"{side}已选招" for side in ("A", "B") if side in self.engine.pending_actions)
            prefix = f"{selected} · " if selected else ""
            result = f"第 {self.engine.round_number} 回合 · {prefix}等待 {self.engine.current_side} 的 {current.name} 选招"
        self.turn_label.configure(text=result)
        self._refresh_card("A")
        self._refresh_card("B")
        self._refresh_actions()
        self._refresh_log()

    def _refresh_card(self, side):
        fighter = self.engine.fighters[side]
        card = self.cards[side]
        current_mark = "  ◀ 当前选招" if not self.engine.done and self.engine.current_side == side else ""
        card["title"].configure(text=f"{side} · {fighter.name}{current_mark}")
        distance = "无穷" if fighter.distance == float("inf") else int(fighter.distance)
        card["subtitle"].configure(text=f"场景：{fighter.scene}（高度{fighter.scene_height}）  人物距离：{distance}  生命：{fighter.lives_remaining}/{fighter.lives_total}")
        hp_percent = fighter.hp / max(1, fighter.max_hp) * 100
        card["hp_label"].configure(text=f"体力 {fighter.hp:,}/{fighter.max_hp:,}")
        card["hp_bar"]["value"] = hp_percent
        card["shield_label"].configure(text=f"盾牌 {fighter.shield:,}/{fighter.max_shield:,}")
        card["radiation_label"].configure(text=f"辐射 {fighter.radiation}/15")

        statuses = "、".join(f"{name}({status.turns})" for name, status in fighter.statuses.items()) or "无"
        parasites = "、".join(f"{name}×{value.count}" for name, value in fighter.parasites.items()) or "无"
        inner = "、".join(f"{name}{level}" for name, level in fighter.inner.items() if level) or "无"
        resources = "、".join(f"{name}:{value}" for name, value in fighter.resources.items())
        counters = "、".join(f"{name}:{value}" for name, value in fighter.counters.items() if name not in {"delayed_effects"}) or "无"
        card["details"].configure(text=f"状态：{statuses}\n寄生虫：{parasites}\n内功：{inner}\n资源：{resources}\n计数：{counters}")

    def _refresh_actions(self):
        for child in self.skill_grid.winfo_children():
            child.destroy()
        self.action_rows.clear()
        self.action_buttons.clear()
        self.hover_action_id = None
        self.detail_title.set("把鼠标放在技能上")
        self.detail_state.set("")
        self.detail_body.set("这里会显示伤害、属性、效果、防御方式、距离、先制和角色特殊效果。")
        self.destination_box.configure(state="disabled")
        if self.engine.done:
            return
        actions = self.engine.legal_actions()
        columns = 4
        for column in range(columns):
            self.skill_grid.columnconfigure(column, weight=1, uniform="skills")
        for index, action in enumerate(actions):
            row, column = divmod(index, columns)
            style = "Defense.Skill.TButton" if action["action_kind"] == "defense" else ("Collect.Skill.TButton" if action["action_kind"] == "collect" else "Skill.TButton")
            button = ttk.Button(
                self.skill_grid,
                text=action["name"],
                style=style,
                command=lambda action_id=action["id"]: self._choose_action(action_id),
                state="normal" if action["legal"] else "disabled",
                takefocus=False,
            )
            button.grid(row=row, column=column, sticky="ew", padx=2, pady=2)
            button.bind("<Enter>", lambda _event, item=action: self._show_action_detail(item))
            button.bind("<MouseWheel>", self._scroll_skills)
            self.action_rows[action["id"]] = action
            self.action_buttons[action["id"]] = button
        self.skill_grid.update_idletasks()
        self.skill_canvas.configure(scrollregion=self.skill_canvas.bbox("all"))

    def _refresh_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        for index, line in enumerate(self.engine.log, start=1):
            self.log_text.insert("end", f"{index:03d}  {line}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _show_action_detail(self, action):
        self.hover_action_id = action["id"]
        state_text = "可执行" if action["legal"] else f"不可执行：{action['reason']}"
        statuses = "、".join(f"{name}（{turns}回合）" for name, turns in action["statuses"]) or "无"
        defense = action["defense"] if action["defense"] is not None else "无对应防御"
        effect = EFFECT_TEXTS.get(action["effect"], "")
        descriptions = [text for text in (effect, action["description"]) if text]
        special = action.get("special_effect") or "无"
        self.detail_title.set(action["name"])
        self.detail_state.set(state_text)
        self.detail_body.set(
            f"属性：{action['attributes_text']}\n"
            f"基础伤害：{action['damage']:,}\n"
            f"附加状态：{statuses}\n"
            f"对应防御：{defense}\n"
            f"技能距离：{action['distance']}\n"
            f"先制：{action.get('initiative', 0)}\n\n"
            f"效果：{' '.join(descriptions) or '无额外效果'}\n\n"
            f"当前角色特殊效果：{special}"
        )
        self.destination_box.configure(state="readonly" if action["effect"] == "choose_scene" and action["legal"] else "disabled")

    def _scroll_skills(self, event):
        self.skill_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _choose_action(self, action_id):
        if not self.engine or self.engine.done:
            return
        action = self.action_rows.get(action_id)
        if not action or not action["legal"]:
            return
        destination = self.destination_var.get() if action["effect"] == "choose_scene" else None
        try:
            self.engine.step(action_id, destination)
        except RuleError as exc:
            messagebox.showwarning("动作不能执行", str(exc), parent=self.root)
            return
        self._refresh_all()
        if self.engine.done:
            messagebox.showinfo("对战结束", f"{self.engine.winner} 获胜！" if self.engine.winner else "双方同时失去全部生命。", parent=self.root)

    # ---------- commands ----------

    def _restart_same(self):
        if not self.engine:
            return
        self.engine.reset(self.engine.fighters["A"].name, self.engine.fighters["B"].name, self.engine.seed)
        self._refresh_all()

    def _back_to_setup(self):
        if messagebox.askyesno("重新选角", "当前对战记录将被清空，是否继续？", parent=self.root):
            self.battle_frame.destroy()
            self.cards.clear()
            self._build_setup()

    def _save_log(self):
        if not self.engine:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="保存对战记录",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("JSON", "*.json")],
            initialfile="晒_对战记录.txt",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(self.engine.observation(), handle, ensure_ascii=False, indent=2)
            else:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("\n".join(self.engine.log))
            messagebox.showinfo("保存成功", path, parent=self.root)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
