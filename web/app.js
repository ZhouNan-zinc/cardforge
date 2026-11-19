const $ = (id) => document.getElementById(id);

let appState = null;
let lastStats = null;
let toastTimer = null;

const SOURCE_LABEL = {
  fallback: "本地稿",
  llm: "模型稿",
  balanced: "校准稿",
};

const TYPE_LABEL = {
  attack: "攻击",
  skill: "技能",
  power: "能力",
};

const ELEMENT_LABEL = {
  ice: "冰",
  wind: "风",
  dragon: "龙",
  neutral: "无",
};

const ELEMENT_ICON = {
  ice: "❄",
  wind: "🌪",
  dragon: "🐉",
  neutral: "✦",
};

const ART = {
  ice: ["ice1", "ice2", "ice3"],
  wind: ["wind1", "wind2", "wind3"],
  dragon: ["dragon1", "dragon2", "dragon3"],
  neutral: ["neutral1", "neutral2", "neutral3"],
};

const ENEMY_ART = {
  "霜原噬影": "enemy1",
  "极光狐": "enemy2",
  "冰晶巨像": "enemy3",
  "雪原狼": "enemy2",
  "极光巨像": "enemy3",
};

const SCARF_ICON = { ice: "❄", wind: "🌪", dragon: "🐉", guard: "🛡", focus: "👁", berserk: "⚔" };

function artFor(card) {
  if (card.art) return `/static/art/${card.art}`;
  const element = card.element || "neutral";
  const pool = ART[element] || ART.neutral;
  let hash = 0;
  for (const ch of String(card.id || card.name || "")) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return `/static/art/${pool[Math.abs(hash) % pool.length]}.png`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.error || `请求失败：${response.status}`);
  }
  return data;
}

function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.className = "toast";
  }, 3600);
}

function statusText(combatant) {
  const parts = [];
  if (combatant.strength) parts.push(`力量 +${combatant.strength}`);
  if (combatant.weak) parts.push(`虚弱 ${combatant.weak}`);
  if (combatant.vulnerable) parts.push(`易伤 ${combatant.vulnerable}`);
  if (combatant.poison) parts.push(`中毒 ${combatant.poison}`);
  return parts.join(" · ");
}

function renderCombatant(prefix, combatant) {
  if (prefix === "enemy") {
    const portrait = $("enemy-portrait");
    if (portrait) {
      const key = ENEMY_ART[combatant.name] || "enemy1";
      portrait.src = `/static/art/${key}.png`;
    }
  }
  $(`${prefix}-name`).textContent = combatant.name;
  $(`${prefix}-hp`).textContent = `${combatant.hp} / ${combatant.max_hp}`;
  $(`${prefix}-block`).textContent = `🛡 ${combatant.block}`;
  $(`${prefix}-hp-fill`).style.width = `${Math.max(0, (combatant.hp / combatant.max_hp) * 100)}%`;
  const status = statusText(combatant);
  $(`${prefix}-status`).textContent = status;
  $(`${prefix}-status`).className = status ? "status" : "";
}

function makeCard(card, { clickable = false, disabled = false, onClick = null } = {}) {
  const el = document.createElement("article");
  const element = card.element || "neutral";
  el.className = `card ${card.type} element-${element}${disabled ? " disabled" : ""}`;
  el.title = card.description;

  const cost = document.createElement("div");
  cost.className = "cost";
  cost.textContent = card.cost;
  cost.title = `费用 ${card.cost} · ${TYPE_LABEL[card.type] || card.type}牌`;
  cost.setAttribute("aria-label", cost.title);
  el.appendChild(cost);

  const artImg = document.createElement("img");
  artImg.className = "card-art-img";
  artImg.src = artFor(card);
  artImg.alt = "";
  artImg.loading = "lazy";
  el.appendChild(artImg);

  const type = document.createElement("span");
  type.className = "type";
  type.textContent = `${TYPE_LABEL[card.type] || card.type} · ${card.rarity}`;
  const elementBadge = document.createElement("span");
  elementBadge.className = `element-badge ${element}`;
  elementBadge.textContent = `${ELEMENT_ICON[element] || "✦"} ${ELEMENT_LABEL[element] || element}`;
  type.appendChild(elementBadge);
  (card.keywords || []).forEach((keyword) => {
    const kw = document.createElement("span");
    kw.className = "keyword-badge";
    kw.textContent = keyword;
    const keywordHelp = {
      "连击": "本回合此前已打过牌时，伤害/格挡 +2",
      "消耗": "打出后本场战斗不再回到牌堆",
      "保留": "回合结束时留在手中，不被弃掉",
      "中毒": "回合开始时造成无视格挡的伤害",
    };
    kw.title = keywordHelp[keyword] || keyword;
    type.appendChild(kw);
  });
  el.appendChild(type);

  const name = document.createElement("h3");
  name.textContent = card.upgraded ? `${card.name} +` : card.name;
  if (card.upgraded) {
    const up = document.createElement("span");
    up.className = "upgraded-badge";
    up.textContent = "强化";
    el.appendChild(up);
  }
  el.appendChild(name);

  const desc = document.createElement("p");
  desc.className = "desc";
  desc.textContent = card.description;
  el.appendChild(desc);

  if (card.flavor) {
    const flavor = document.createElement("p");
    flavor.className = "flavor";
    flavor.textContent = card.flavor;
    el.appendChild(flavor);
  }

  if (clickable && !disabled && onClick) {
    el.addEventListener("click", onClick);
  }
  return el;
}

function choiceOption(iconText, titleText, description, hintText, onClick) {
  const el = document.createElement("article");
  el.className = "map-option";
  const icon = document.createElement("div");
  icon.className = "map-icon";
  icon.textContent = iconText;
  const title = document.createElement("h3");
  title.textContent = titleText;
  const desc = document.createElement("p");
  desc.textContent = description;
  const hint = document.createElement("small");
  hint.textContent = hintText;
  el.append(icon, title, desc, hint);
  el.addEventListener("click", onClick);
  return el;
}

function renderHand(data) {
  const hand = $("hand");
  const optionPhases = new Set(["scarf", "map", "rest", "shop", "remove", "event", "upgrade", "boon", "reward", "victory", "defeat"]);
  hand.className = optionPhases.has(data.phase) ? "hand options" : "hand";
  hand.innerHTML = "";
  $("reward-banner").hidden = true;
  const game = data.game;
  const player = game.player;

  if (data.phase === "scarf") {
    (data.scarf_options || []).forEach((scarf, index) => {
      const el = document.createElement("article");
      el.className = "scarf-option";
      const icon = document.createElement("div");
      icon.className = "scarf-icon";
      icon.textContent = SCARF_ICON[scarf.id] || "❄";
      const title = document.createElement("h3");
      title.textContent = scarf.name;
      const desc = document.createElement("p");
      desc.textContent = scarf.description;
      const hint = document.createElement("small");
      hint.textContent = "点击选择这个徽记，开始第一战";
      el.append(icon, title, desc, hint);
      el.addEventListener("click", () => chooseScarf(index));
      hand.appendChild(el);
    });
    return;
  }

  if (data.phase === "map") {
    const banner = $("reward-banner");
    banner.hidden = false;
    banner.innerHTML = `<span>🗺 选择前路</span><small>路线会影响下一战的难度与收益</small>`;
    (data.map_options || []).forEach((node, index) => {
      const el = document.createElement("article");
      el.className = "map-option";
      const icon = document.createElement("div");
      icon.className = "map-icon";
      icon.textContent = node.icon || "◆";
      const title = document.createElement("h3");
      title.textContent = node.name;
      const desc = document.createElement("p");
      desc.textContent = node.description;
      const hint = document.createElement("small");
      hint.textContent = "点击选择这条路线";
      el.append(icon, title, desc, hint);
      el.addEventListener("click", () => chooseMap(index));
      hand.appendChild(el);
    });
    return;
  }

  if (data.phase === "rest") {
    const banner = $("reward-banner");
    banner.hidden = false;
    banner.innerHTML = `<span>🔥 休息点</span><small>回复生命，或强化一张牌</small>`;
    (data.rest_options || []).forEach((option, index) => {
      hand.appendChild(choiceOption("🔥", option.name, option.description, "点击选择", () => chooseRest(index)));
    });
    return;
  }

  if (data.phase === "shop") {
    const banner = $("reward-banner");
    banner.hidden = false;
    banner.innerHTML = `<span>🛒 商店</span><small>金币 ${data.gold} · 点击购买，或离开</small>`;
    (data.shop_items || []).forEach((item, index) => {
      const affordable = data.gold >= item.price;
      const el = choiceOption(
        item.kind === "card" ? "🃏" : item.kind === "relic" ? "💎" : item.kind === "potion" ? "🧪" : "🗑",
        `${item.name} · ${item.price}G`,
        item.description,
        affordable ? "点击购买" : "金币不足",
        () => buyShop(index)
      );
      if (!affordable) el.classList.add("disabled-choice");
      hand.appendChild(el);
    });
    hand.appendChild(choiceOption("🔄", "刷新商品 · 10G", "重新进货；药水、遗物和卡牌都会变化", data.gold >= 10 ? "点击刷新" : "金币不足", () => rerollShop()));
    hand.appendChild(choiceOption("🚪", "离开商店", "保留剩余金币，前往下一层", "点击离开", () => leaveShop()));
    return;
  }

  if (data.phase === "remove") {
    const banner = $("reward-banner");
    banner.hidden = false;
    banner.innerHTML = `<span>🗑 删牌服务</span><small>选择一张牌从牌组中移除</small>`;
    (data.remove_options || []).forEach((card, index) => {
      hand.appendChild(makeCard(card, { clickable: true, onClick: () => chooseRemove(index) }));
    });
    return;
  }

  if (data.phase === "event") {
    const banner = $("reward-banner");
    banner.hidden = false;
    banner.innerHTML = `<span>❓ 神秘事件</span><small>三个选项，各有代价与收益</small>`;
    (data.event_options || []).forEach((option, index) => {
      hand.appendChild(choiceOption("❓", option.name, option.description, "点击选择", () => chooseEvent(index)));
    });
    return;
  }

  if (data.phase === "upgrade") {
    const banner = $("reward-banner");
    banner.hidden = false;
    banner.innerHTML = `<span>✦ 淬炼：选择一张牌强化</span><small>只能选择未强化的牌</small>`;
    data.upgrade_options.forEach((card, index) => {
      hand.appendChild(makeCard(card, { clickable: true, onClick: () => chooseUpgrade(index) }));
    });
    return;
  }

  if (data.phase === "boon") {
    (data.boon_options || []).forEach((boon, index) => {
      const el = document.createElement("article");
      el.className = "boon-option";
      const icon = document.createElement("div");
      icon.className = "boon-icon";
      icon.textContent = "✦";
      const title = document.createElement("h3");
      title.textContent = boon.name;
      const desc = document.createElement("p");
      desc.textContent = boon.description;
      const hint = document.createElement("small");
      hint.textContent = "点击选择这个增益，进入下一战";
      el.append(icon, title, desc, hint);
      el.addEventListener("click", () => chooseBoon(index));
      hand.appendChild(el);
    });
    return;
  }

  if (data.phase === "reward") {
    const banner = $("reward-banner");
    banner.hidden = false;
    banner.innerHTML = `<span>❄ 战斗胜利，选择一张牌加入牌组</span><small>牌组 ${data.deck_size} 张 · 回复 3 HP</small>`;
    data.reward_options.forEach((card, index) => {
      hand.appendChild(makeCard(card, { clickable: true, onClick: () => chooseReward(index) }));
    });
    hand.appendChild(choiceOption("⏭", "跳过奖励", "不加入新牌，保持牌组精简，回复 3 HP", "点击跳过", () => skipReward()));
    return;
  }

  if (data.phase === "victory" || data.phase === "defeat") {
    const msg = document.createElement("p");
    msg.className = "empty-hand";
    msg.textContent = data.phase === "victory"
      ? `🏆 雪原通关！得分 ${data.score ?? 0} · ${data.rank || "C"}。点「新的一局」重新开始。`
      : `💀 挑战失败。得分 ${data.score ?? 0} · ${data.rank || "C"}。点「新的一局」再来一次。`;
    hand.appendChild(msg);
    return;
  }

  if (game.winner) {
    const msg = document.createElement("p");
    msg.className = "empty-hand";
    msg.textContent = game.winner === "player" ? "战斗胜利！" : "战斗失败…";
    hand.appendChild(msg);
    return;
  }

  if (game.active !== "player") {
    const msg = document.createElement("p");
    msg.className = "empty-hand";
    msg.textContent = "对手正在行动…";
    hand.appendChild(msg);
    return;
  }

  if (!player.hand.length) {
    const msg = document.createElement("p");
    msg.className = "empty-hand";
    msg.textContent = "手牌为空，结束回合吧。";
    hand.appendChild(msg);
    return;
  }

  player.hand.forEach((card, index) => {
    const disabled = card.cost > player.energy;
    hand.appendChild(
      makeCard(card, {
        clickable: true,
        disabled,
        onClick: () => playCard(index),
      })
    );
  });
}

function renderBurst(game) {
  const counts = game.player.element_counts || {};
  for (const element of ["ice", "wind", "dragon"]) {
    const count = counts[element] || 0;
    const shown = count % 3;
    const pips = $(`burst-${element}`);
    pips.innerHTML = "";
    for (let i = 0; i < 3; i += 1) {
      const pip = document.createElement("span");
      pip.className = `pip${i < shown ? " on" : ""}`;
      pips.appendChild(pip);
    }
    $(`count-${element}`).textContent = `${shown}/3`;
  }
}

function renderLog(lines) {
  const log = $("log");
  log.innerHTML = "";
  for (const line of lines || []) {
    const p = document.createElement("p");
    p.textContent = line;
    if (line.includes("回合")) p.className = "log-turn";
    if (line.includes("伤害") || line.includes("受到")) p.className = "log-hit";
    log.appendChild(p);
  }
  log.scrollTop = log.scrollHeight;
}

function renderStats() {
  const stats = $("stats");
  stats.innerHTML = "";
  if (!lastStats) {
    stats.innerHTML = `<div class="stat"><div class="label">牌组校准</div><div class="value">—</div><div class="label">先点「推演 300 局」收集数据</div></div>`;
    return;
  }
  const items = [
    ["玩家胜率", `${(lastStats.player_win_rate * 100).toFixed(1)}%`],
    ["先手胜率", `${(lastStats.first_player_win_rate * 100).toFixed(1)}%`],
    ["平均回合", lastStats.avg_turns],
    ["模拟局数", lastStats.games],
  ];
  for (const [label, value] of items) {
    const el = document.createElement("div");
    el.className = "stat";
    const l = document.createElement("div");
    l.className = "label";
    l.textContent = label;
    const v = document.createElement("div");
    v.className = "value";
    v.textContent = value;
    el.append(l, v);
    stats.appendChild(el);
  }

  const top = Object.values(lastStats.card_stats || {})
    .filter((item) => item.plays >= 3)
    .sort((a, b) => b.win_rate - a.win_rate)
    .slice(0, 5);
  if (top.length) {
    const el = document.createElement("div");
    el.className = "stat";
    el.style.gridColumn = "1 / -1";
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = "高胜率卡（至少打出 3 次）";
    const list = document.createElement("div");
    list.className = "top-cards";
    for (const item of top) {
      const span = document.createElement("span");
      span.textContent = `${item.name} ${(item.win_rate * 100).toFixed(0)}% (${item.plays})`;
      list.appendChild(span);
    }
    el.append(label, list);
    stats.appendChild(el);
  }
}

function renderGallery(cardSet) {
  const gallery = $("card-gallery");
  gallery.innerHTML = "";
  for (const card of cardSet.cards) {
    gallery.appendChild(makeCard(card));
  }
  $("card-set-meta").textContent = `${cardSet.title} · ${cardSet.cards.length} 张 · ${SOURCE_LABEL[cardSet.source] || cardSet.source}`;
}

function renderMapBoard(data) {
  const board = $("map-board");
  if (data.phase !== "map" || !data.map_preview) {
    board.hidden = true;
    board.innerHTML = "";
    return;
  }
  board.hidden = false;
  const layers = data.map_preview;
  const W = 1100;
  const H = 370;
  const x0 = 100;
  const layersCount = layers.length;
  const xStep = (W - x0 * 2) / Math.max(1, layersCount - 1);
  const y0 = 90;
  const yStep = 105;
  const coords = layers.map((layer, li) =>
    layer.nodes.map((node, ni) => ({
      x: x0 + li * xStep,
      y: y0 + ni * yStep,
      node,
      layer: layer.layer,
      chosen: layer.chosen === node.id,
      current: layer.layer === (data.layer || 1),
    }))
  );
  const graph = data.map_edges || [];
  let edges = "";
  for (let li = 0; li < coords.length - 1; li += 1) {
    const layerEdges = graph[li] || [];
    coords[li].forEach((a, sourceIndex) => {
      const targets = layerEdges[sourceIndex] || [];
      targets.forEach((targetIndex) => {
        const b = coords[li + 1][targetIndex];
        if (b) edges += `<line class="map-edge" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />`;
      });
    });
  }
  let path = "";
  for (let li = 0; li < coords.length - 1; li += 1) {
    const a = coords[li].find((n) => n.chosen);
    const b = coords[li + 1].find((n) => n.chosen);
    if (a && b) path += `<line class="map-edge chosen" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />`;
  }
  const reachable = new Set((data.map_options || []).map((node) => node.id));
  let nodes = "";
  for (const layer of coords) {
    for (let index = 0; index < layer.length; index += 1) {
      const item = layer[index];
      const optionIndex = (data.map_options || []).findIndex((node) => node.id === item.node.id);
      const isReachable = !item.current || optionIndex >= 0;
      const cls = `map-svg-node${item.chosen ? " chosen" : ""}${item.current ? " current" : ""}${item.current && !isReachable ? " unreachable" : ""}`;
      const clickable = item.current && isReachable && !item.chosen;
      nodes += `<g class="${cls}" ${clickable ? `data-index="${optionIndex}"` : ""}>
        <circle cx="${item.x}" cy="${item.y}" r="25"></circle>
        <text class="map-svg-icon" x="${item.x}" y="${item.y + 8}" text-anchor="middle">${item.node.icon || "◆"}</text>
        <text class="map-svg-label" x="${item.x}" y="${item.y + 45}" text-anchor="middle">${item.node.name}</text>
      </g>`;
    }
  }
  const layerTitles = coords.map((layer, i) => {
    const current = (i + 1) === (data.layer || 1);
    return `<text class="map-svg-layer${current ? " current" : ""}" x="${x0 + i * xStep}" y="30" text-anchor="middle">第 ${i + 1} 层${current ? " · 当前" : ""}</text>`;
  }).join("");
  board.innerHTML = `
    <div class="map-board-head">
      <div><span class="map-kicker">雪原行记 · 路线图</span><h2>选择下一段路</h2></div>
      <p>第 <b>${data.layer}/${data.layers - 1}</b> 层 · 每个节点最多 2 条出边 · 未连通节点不可选</p>
    </div>
    <svg class="map-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="雪原路线图">
      ${layerTitles}
      <g class="map-edges">${edges}</g>
      <g class="map-edges">${path}</g>
      ${nodes}
    </svg>`;
  board.querySelectorAll(".map-svg-node.current[data-index]").forEach((el) => {
    el.addEventListener("click", () => chooseMap(Number(el.dataset.index)));
  });
}

function renderPotions(data) {
  const bar = $("potions");
  bar.innerHTML = "";
  const potions = data.potions || [];
  const label = document.createElement("span");
  label.className = "potion-label";
  label.textContent = `药水 ${potions.length}/2`;
  bar.appendChild(label);
  potions.forEach((potion, index) => {
    const button = document.createElement("button");
    button.className = "potion-chip";
    button.textContent = potion.name;
    button.title = potion.description;
    button.disabled = data.phase !== "battle";
    button.addEventListener("click", () => usePotion(index));
    bar.appendChild(button);
  });
  if (!potions.length) {
    const empty = document.createElement("span");
    empty.className = "muted";
    empty.textContent = "战斗中可用";
    bar.appendChild(empty);
  }
}

function renderDeckPanel(data) {
  const panel = $("deck-panel");
  panel.innerHTML = "";
  if (!data.deck || !data.deck.length) {
    panel.innerHTML = `<p class="empty-hand">牌组为空</p>`;
    return;
  }
  const head = document.createElement("div");
  head.className = "deck-panel-head";
  head.innerHTML = `<b>当前牌组</b><span>${data.deck.length} 张 · 抽牌堆 ${data.game?.player?.draw_count ?? 0} · 弃牌堆 ${data.game?.player?.discard_count ?? 0}</span>`;
  panel.appendChild(head);
  const grid = document.createElement("div");
  grid.className = "deck-grid";
  data.deck.forEach((card) => grid.appendChild(makeCard(card)));
  panel.appendChild(grid);
}

function render() {
  if (!appState) return;
  const game = appState.game;
  const cardSet = appState.card_set;

  renderCombatant("player", game.player);
  renderCombatant("enemy", game.enemy);
  const avatar = appState.player_avatar || "player1";
  $("player-portrait").src = `/static/art/${avatar}.png`;
  $("player-energy").textContent = `⚡ ${game.player.energy} / ${game.player.max_energy}`;

  const scarfLabel = (appState.scarf_options || []).find((x) => x.id === appState.style)?.name || "未选择";
  const relicNames = (appState.relics || []).map((r) => r.name).join(" / ") || "无";
  $("run-info").innerHTML =
    `第 <b>${appState.layer || appState.battle}/${appState.layers || appState.battles}</b> 层 · 牌组 <b>${appState.deck_size}</b> 张 · HP <b>${appState.player_hp}/${appState.max_hp}</b> · 金币 <b>${appState.gold ?? 0}</b> · 流派 <b>${scarfLabel}</b> · 遗物 <b>${relicNames}</b>`;

  const intent = game.enemy_intent;
  $("enemy-intent").textContent = intent
    ? `意图：${intent.label}${game.incoming_damage ? ` · 预计受到 ${game.incoming_damage}` : ""}`
    : "意图：—";
  const phase = game.enemy_phase || 1;
  $("enemy-phase").hidden = phase < 2;
  $("enemy-panel").classList.toggle("phase2", phase >= 2);
  const elite = game.enemy_elite_modifier;
  $("enemy-elite").hidden = !elite;
  if (elite) $("enemy-elite").textContent = `精英·${elite.name}`;
  const history = appState.map_history || [];
  $("route-history").innerHTML = history.map((item) => `<span>${item}</span>`).join("");
  const contract = appState.contract;
  $("objectives").innerHTML = contract
    ? `<span class="${contract.done ? "done" : ""}">${contract.done ? "✓" : "○"} ${contract.name} · ${contract.description}</span><b>${appState.score ?? 0} 分 · ${appState.rank || "C"}</b>`
    : `<span>挑战契约载入中…</span><b>${appState.score ?? 0} 分 · ${appState.rank || "C"}</b>`;
  renderMapBoard(appState);

  const turn = $("turn-info");
  if (appState.phase === "scarf") {
    turn.textContent = "选择一种流派徽记";
    turn.className = "turn-info";
  } else if (appState.phase === "map") {
    turn.textContent = "选择前路";
    turn.className = "turn-info";
  } else if (appState.phase === "rest") {
    turn.textContent = "休息点";
    turn.className = "turn-info";
  } else if (appState.phase === "shop") {
    turn.textContent = `商店 · 金币 ${appState.gold ?? 0}`;
    turn.className = "turn-info";
  } else if (appState.phase === "remove") {
    turn.textContent = "删牌服务";
    turn.className = "turn-info";
  } else if (appState.phase === "event") {
    turn.textContent = "神秘事件";
    turn.className = "turn-info";
  } else if (appState.phase === "upgrade") {
    turn.textContent = "淬炼 · 选择一张牌强化";
    turn.className = "turn-info win";
  } else if (appState.phase === "boon") {
    turn.textContent = "战斗胜利 · 选择被动增益";
    turn.className = "turn-info win";
  } else if (appState.phase === "reward") {
    turn.textContent = "战斗胜利 · 选择奖励";
    turn.className = "turn-info win";
  } else if (appState.phase === "victory") {
    turn.textContent = "🏆 通关！";
    turn.className = "turn-info win";
  } else if (appState.phase === "defeat") {
    turn.textContent = "💀 挑战失败";
    turn.className = "turn-info win";
  } else if (game.winner) {
    turn.textContent = game.winner === "player" ? "战斗胜利！" : "战斗失败…";
    turn.className = "turn-info win";
  } else {
    turn.textContent = game.active === "player" ? `你的回合 · 第 ${game.turn} 回合` : "对手回合";
    turn.className = "turn-info";
  }

  renderBurst(game);
  renderPotions(appState);
  $("pile-info").textContent = `抽牌堆 ${game.player.draw_count} · 弃牌堆 ${game.player.discard_count}`;
  renderDeckPanel(appState);
  renderLog(game.log);
  renderHand(appState);
  renderGallery(cardSet);
  renderStats();

  $("end-turn").disabled =
    appState.phase !== "battle" || Boolean(game.winner) || game.active !== "player";
}

async function generate() {
  const theme = $("theme").value.trim() || "霜旋";
  const button = $("generate");
  button.disabled = true;
  button.textContent = "重绘中…";
  try {
    const data = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ theme, count: 36, allow_llm: true }),
    });
    appState = data;
    lastStats = null;
    render();
    toast(`牌组已重绘：${SOURCE_LABEL[data.card_set.source] || data.card_set.source}`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "重绘牌组";
  }
}

async function chooseRest(index) {
  try {
    appState = await api("/api/run/rest", { method: "POST", body: JSON.stringify({ index }) });
    render();
  } catch (error) { toast(error.message, true); }
}

async function buyShop(index) {
  try {
    appState = await api("/api/run/shop", { method: "POST", body: JSON.stringify({ index }) });
    render();
  } catch (error) { toast(error.message, true); }
}

async function leaveShop() {
  try {
    appState = await api("/api/run/shop/leave", { method: "POST" });
    render();
  } catch (error) { toast(error.message, true); }
}

async function chooseRemove(index) {
  try {
    appState = await api("/api/run/remove", { method: "POST", body: JSON.stringify({ index }) });
    render();
  } catch (error) { toast(error.message, true); }
}

async function chooseEvent(index) {
  try {
    appState = await api("/api/run/event", { method: "POST", body: JSON.stringify({ index }) });
    render();
  } catch (error) { toast(error.message, true); }
}

async function chooseMap(index) {
  try {
    appState = await api("/api/run/map", {
      method: "POST",
      body: JSON.stringify({ index }),
    });
    render();
    toast("路线已选择，进入下一战");
  } catch (error) {
    toast(error.message, true);
  }
}

async function chooseUpgrade(index) {
  try {
    appState = await api("/api/run/upgrade", {
      method: "POST",
      body: JSON.stringify({ index }),
    });
    render();
    toast("卡牌已强化，进入下一战");
  } catch (error) {
    toast(error.message, true);
  }
}

async function chooseBoon(index) {
  try {
    appState = await api("/api/run/boon", {
      method: "POST",
      body: JSON.stringify({ index }),
    });
    render();
    toast("增益已获得，进入下一战");
  } catch (error) {
    toast(error.message, true);
  }
}

async function chooseScarf(index) {
  try {
    appState = await api("/api/run/scarf", {
      method: "POST",
      body: JSON.stringify({ index }),
    });
    render();
    toast("流派已选定，第一战开始");
  } catch (error) {
    toast(error.message, true);
  }
}

async function chooseReward(index) {
  try {
    appState = await api("/api/run/reward", {
      method: "POST",
      body: JSON.stringify({ index }),
    });
    render();
    toast("奖励已加入牌组，进入下一战");
  } catch (error) {
    toast(error.message, true);
  }
}

async function rerollShop() {
  try {
    appState = await api("/api/run/shop/reroll", { method: "POST" });
    render();
    toast("商品已刷新");
  } catch (error) { toast(error.message, true); }
}

async function usePotion(index) {
  try {
    appState = await api("/api/run/potion", {
      method: "POST",
      body: JSON.stringify({ index }),
    });
    render();
    toast("药水已使用");
  } catch (error) { toast(error.message, true); }
}

async function skipReward() {
  try {
    appState = await api("/api/run/reward", {
      method: "POST",
      body: JSON.stringify({ index: -1 }),
    });
    render();
    toast("已跳过奖励，牌组保持精简");
  } catch (error) { toast(error.message, true); }
}

async function newGame() {
  try {
    appState = await api("/api/new_game", { method: "POST" });
    render();
  } catch (error) {
    toast(error.message, true);
  }
}

async function playCard(index) {
  try {
    appState = await api("/api/play", {
      method: "POST",
      body: JSON.stringify({ index }),
    });
    render();
  } catch (error) {
    toast(error.message, true);
  }
}

async function endTurn() {
  try {
    appState = await api("/api/end_turn", { method: "POST" });
    render();
  } catch (error) {
    toast(error.message, true);
  }
}

async function simulate() {
  const button = $("simulate");
  button.disabled = true;
  button.textContent = "推演中…";
  try {
    lastStats = await api("/api/simulate", {
      method: "POST",
      body: JSON.stringify({ games: 300, agent: "heuristic" }),
    });
    renderStats();
    toast(`推演完成：玩家胜率 ${(lastStats.player_win_rate * 100).toFixed(1)}%`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "推演 300 局";
  }
}

async function balance() {
  if (!lastStats) {
    toast("先点「推演 300 局」", true);
    return;
  }
  const button = $("balance");
  button.disabled = true;
  button.textContent = "校准中…";
  try {
    appState = await api("/api/balance", { method: "POST" });
    lastStats = null;
    render();
    toast(`已完成一轮牌组校准（${appState.balance_source === "llm" ? "模型建议" : "规则微调"}）`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "校准牌组";
  }
}

async function generateArtPrompts() {
  const button = $("art-prompts");
  button.disabled = true;
  button.textContent = "重绘中…";
  try {
    const data = await api("/api/art-prompts", {
      method: "POST",
      body: JSON.stringify({ use_llm: true }),
    });
    const panel = $("art-prompts-panel");
    panel.hidden = false;
    panel.innerHTML = `<div class="art-prompts-head">卡面画稿 · 可复制到任意生图模型 · ${data.theme}</div>`;
    for (const item of data.prompts) {
      const row = document.createElement("div");
      row.className = "prompt-row";
      const name = document.createElement("b");
      name.textContent = item.name;
      const prompt = document.createElement("p");
      prompt.textContent = item.prompt;
      row.append(name, prompt);
      panel.appendChild(row);
    }
    toast(`已生成 ${data.prompts.length} 条卡面画稿`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "卡面画稿";
  }
}

async function boot() {
  try {
    appState = await api("/api/state");
    render();
  } catch (error) {
    toast(`加载失败：${error.message}`, true);
  }
}

$("generate").addEventListener("click", generate);
$("new-game").addEventListener("click", newGame);
$("end-turn").addEventListener("click", endTurn);
$("simulate").addEventListener("click", simulate);
$("balance").addEventListener("click", balance);
$("art-prompts").addEventListener("click", generateArtPrompts);
$("view-deck").addEventListener("click", () => {
  const panel = $("deck-panel");
  panel.hidden = !panel.hidden;
});

boot();
