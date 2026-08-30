const $ = (id) => document.getElementById(id);

let current = {
  videoId: null,
  markdown: "",
  title: "",
  bullets_en: [],
  bullets_zh: [],
  exec_zh: [],
  vision: null,
  status: "idle",
};
let lang = "zh";
let pollTimer = null;
let visionPollTimer = null;
let comparePollTimer = null;

function stopVisionPoll() {
  if (visionPollTimer) {
    clearInterval(visionPollTimer);
    visionPollTimer = null;
  }
}

function stopComparePoll() {
  if (comparePollTimer) {
    clearInterval(comparePollTimer);
    comparePollTimer = null;
  }
}

async function loadVision(videoId) {
  if (!videoId) return;
  try {
    const data = await fetch(`/api/vision/${videoId}`).then((r) => r.json());
    current.vision = data;
    const btn = $("visionBtn");
    if (btn) btn.disabled = false;
    const job = data.job || {};
    if (data.ready) {
      stopVisionPoll();
      if (current.status !== "whisper_running") {
        renderTimeline(activeBullets(), videoId);
      }
      return data;
    }
    if (job.status === "running" || job.status === "starting") {
      setHint(
        `畫面核對進行中：${job.step || "download_video"}（下載 360p 片再截圖，唔止音訊）。`
      );
    }
    return data;
  } catch (_) {
    return null;
  }
}

async function startVision() {
  if (!current.videoId) {
    setStatus("先 Analyze／開一條已存摘要", "err");
    return;
  }
  $("visionBtn").disabled = true;
  setStatus("開始下載畫面（360p）＋截圖核對 ticker…");
  try {
    await fetch(`/api/vision/${current.videoId}`, { method: "POST" });
    stopVisionPoll();
    await loadVision(current.videoId);
    visionPollTimer = setInterval(() => loadVision(current.videoId), 8000);
  } catch (e) {
    setStatus(String(e.message || e), "err");
  } finally {
    $("visionBtn").disabled = false;
  }
}

function fmtSec(s) {
  const n = Math.max(0, Math.round(Number(s) || 0));
  const m = Math.floor(n / 60);
  const r = n % 60;
  return m ? `${m}分${r}秒` : `${r}秒`;
}

function renderCompare(verifyOrReport) {
  const box = $("compareBox");
  if (!box) return;
  const report = verifyOrReport?.report || null;
  const job = verifyOrReport?.compare_job || verifyOrReport?.jobs?.compare || {};
  const jobSt = job.status || "";
  const running = jobSt === "running" || jobSt === "starting";
  const pct = Number(job.progress_pct);
  const hasPct = Number.isFinite(pct);
  const hbAge = Number(job.heartbeat_age_sec);
  const fileAge = Number(job.status_file_age_sec);
  const hung = running && Number.isFinite(hbAge) && hbAge > 90;
  // #region agent log
  fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'B',location:'app.js:renderCompare',message:'ui_compare_render',data:{jobSt,step:job.step||null,hasReport:!!report,running,hasPct,pct:hasPct?pct:null,hbAge:Number.isFinite(hbAge)?hbAge:null,fileAge:Number.isFinite(fileAge)?fileAge:null,hung,reportHint:(report&&report.summary&&report.summary.hint)||null},timestamp:Date.now()})}).catch(()=>{});
  // #endregion
  if (!report && !jobSt) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  // Prefer live job status over stale disk report (old "WhisperX 未裝" while job runs)
  if (running) {
    box.classList.remove("ok");
    box.classList.toggle("warn", !hung);
    box.classList.toggle("hang", hung);
    const step = job.step || jobSt;
    const detail = job.detail ? ` · ${escapeHtml(String(job.detail))}` : "";
    const bar = hasPct
      ? `<div class="prog" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="prog-fill" style="width:${Math.max(0, Math.min(100, pct))}%"></div></div>`
      : `<div class="prog"><div class="prog-fill" style="width:8%"></div></div>`;
    const pctTxt = hasPct ? `<b>${pct}%</b>` : "<b>—%</b>（舊 job 未報進度，要重跑先有%）";
    const elapsed = job.elapsed_sec != null ? `已用 ${fmtSec(job.elapsed_sec)}` : "";
    const eta = job.eta_sec != null && hasPct ? ` · 約剩 ${fmtSec(job.eta_sec)}` : "";
    const beat = Number.isFinite(hbAge)
      ? `${hbAge}秒前有心跳`
      : Number.isFinite(fileAge)
        ? `狀態檔 ${fileAge}秒前更新`
        : "未有心跳";
    const hangNote = hung
      ? `<div class="hang-note">超過 90 秒無心跳／狀態檔無更新，可能 hang 或者 Python GIL 卡住。開 Task Manager 睇 CPU：有用量＝仲跑緊。</div>`
      : "";
    box.innerHTML = `<div><b>三重對比進行中</b>：${escapeHtml(String(step))}${detail}</div>
      ${bar}
      <div>${pctTxt}${elapsed ? ` · ${elapsed}` : ""}${eta}</div>
      <div class="muted">${escapeHtml(beat)} · CPU 會長跑 WhisperX，% 係估算唔係逐字準。</div>
      ${hangNote}`;
    return;
  }
  if (!report) {
    box.classList.remove("ok");
    box.classList.add("warn");
    box.innerHTML = `<div><b>三重對比</b>：等結果…（${escapeHtml(jobSt || "idle")}）</div>`;
    return;
  }
  const sum = report.summary || {};
  const actions = report.actions || {};
  const asr = report.asr || {};
  const screen = report.screen || {};
  const dropN = sum.exec_drop ?? actions.drop ?? 0;
  const singleN = sum.exec_single ?? actions.single_asr ?? 0;
  const scrN = sum.screen_mismatch || 0;
  const ok = !dropN && !scrN;
  box.classList.toggle("ok", ok);
  box.classList.toggle("warn", !ok);
  const dualN = actions.dual_count ?? sum.dual_count;
  const wxN = actions.wx_only_count ?? 0;
  const hint =
    actions.hint ||
    sum.hint ||
    (Number.isFinite(dualN) ? `雙ASR確認 ${dualN} 行` : "") ||
    (ok ? "語音＋畫面大致一致；摘要已按雙ASR核實" : "");
  const dualRows = (actions.dual_rows || []).slice(0, 20);
  const dualListHtml = dualRows.length
    ? `<div style="margin-top:8px"><b>雙ASR確認（faster∩WhisperX）</b><ul>${dualRows
        .map(
          (r) =>
            `<li><code>${escapeHtml(r.t || "")}</code> <b>${escapeHtml(r.ticker || "")}</b> ${escapeHtml(r.side || "")}</li>`
        )
        .join("")}</ul></div>`
    : "";
  const execActs = (actions.exec || [])
    .filter((a) =>
      ["drop", "ok_a", "ok_b", "ok_a_screen", "ok_b_screen", "screen_diff"].includes(a.status) || a.t !== a.new_t
    )
    .slice(0, 14);
  const actHtml = execActs.length
    ? `<div style="margin-top:8px"><b>已核實／改正</b><ul>${execActs
        .map((a) => {
          const ticks = (a.tickers || []).join("/");
          const scr = a.screen ? `畫面 ${a.screen}` : "無畫面標";
          const st =
            a.status === "drop"
              ? (String(a.flag || "").includes("faster") ? "已刪（只得 faster-whisper）" : "移出主表（雙ASR未見）")
              : a.status === "ok_a_screen" || a.status === "ok_b_screen"
                ? `單邊ASR＋${scr} 確認`
                : a.status === "screen_diff"
                  ? `語音≠畫面（${scr}）`
                  : a.status === "ok_b"
                    ? `WhisperX 有 · ${scr}`
                    : a.t !== a.new_t
                      ? `時間 ${a.t}→${a.new_t}`
                      : a.status;
          return `<li><code>${escapeHtml(a.t || "")}</code> <b>${escapeHtml(ticks)}</b> — ${escapeHtml(st)}</li>`;
        })
        .join("")}</ul></div>`
    : "";
  // Don't surface only_a/only_b ticker lists — mostly VAD/coverage noise, reads as "all wrong"
  const tickHtml = "";
  const actionable = (asr.desync_actionable || []).filter((d) => d.kind === "ticker_desync" || d.kind === "content_desync").slice(0, 6);
  const desyncHtml = actionable.length
    ? `<div style="margin-top:8px"><b>有用分歧（ticker／內容）</b><ul>${actionable
        .map((d) => {
          const ta = (d.tickers_only_a || []).join(",") || "—";
          const tb = (d.tickers_only_b || []).join(",") || "—";
          return `<li><code>${escapeHtml(d.t || "")}</code> ${escapeHtml(d.kind || "")} · A:${escapeHtml(ta)} / X:${escapeHtml(tb)}</li>`;
        })
        .join("")}</ul></div>`
    : "";
  const mism = (screen.mismatches || []).slice(0, 8);
  const scrHtml = mism.length
    ? `<div style="margin-top:8px"><b>畫面／語音分歧</b><ul>${mism
        .map(
          (m) =>
            `<li><code>${escapeHtml(m.t || "")}</code> <b>${escapeHtml(m.claimed || "")}</b> → 畫面 ${escapeHtml(m.screen || "—")} — ${escapeHtml(m.note || "")}</li>`
        )
        .join("")}</ul></div>`
    : "";
  box.innerHTML = `<div><b>三重對比→已改摘要</b>：${escapeHtml(hint)}</div>
    <div class="muted">雙ASR ${Number.isFinite(dualN) ? dualN : "—"} · WhisperX獨有 ${wxN} · 畫面分歧 ${scrN}${screen.has_labels ? "" : " · 未有 labels"}</div>
    ${dualListHtml}${tickHtml}${actHtml}${desyncHtml}${scrHtml}`;
}

async function loadCompare(videoId) {
  if (!videoId) return null;
  try {
    const data = await fetch(`/api/compare/${videoId}`).then((r) => r.json());
    renderCompare({ report: data.report, compare_job: data.job });
    const job = data.job || {};
    // #region agent log
    fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'C',location:'app.js:loadCompare',message:'ui_compare_poll',data:{ready:!!data.ready,jobStatus:job.status||null,step:job.step||null,progress_pct:job.progress_pct??null,heartbeat_age_sec:job.heartbeat_age_sec??null,status_file_age_sec:job.status_file_age_sec??null,summary_patched:job.summary_patched??null},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    if (data.ready && job.status !== "running" && job.status !== "starting") {
      stopComparePoll();
      // Once: reload exec after compare/reconcile so table matches patched md
      const shouldRefresh =
        !comparePatchedOnce.has(videoId) &&
        (job.summary_patched || (data.report && data.report.actions));
      if (shouldRefresh) {
        comparePatchedOnce.add(videoId);
        try {
          const sum = await fetch(`/api/summaries/${videoId}`).then((r) => r.json());
          await showResult(sum, { skipComparePoll: true, skipCompareRender: true });
          renderCompare({ report: data.report, compare_job: data.job });
          setStatus("對比完成：摘要已按雙 ASR 核實／改正", "ok");
        } catch (_) {
          /* ignore */
        }
      }
      return data;
    }
    return data;
  } catch (_) {
    return null;
  }
}

function startComparePoll(videoId) {
  stopComparePoll();
  loadCompare(videoId);
  comparePollTimer = setInterval(() => loadCompare(videoId), 6000);
}

function setStatus(msg, kind = "") {
  const el = $("status");
  el.textContent = msg || "";
  el.className = `status muted${kind ? " " + kind : ""}`;
}

function setHint(msg) {
  const el = $("hint");
  if (!msg) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.classList.remove("hidden");
  el.textContent = msg;
}

function parseTimestamp(t) {
  const parts = String(t).split(":").map(Number);
  if (parts.some((n) => Number.isNaN(n))) return 0;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] || 0;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function ytLink(videoId, t) {
  if (!videoId || !t) return "#";
  return `https://www.youtube.com/watch?v=${videoId}&t=${Math.floor(parseTimestamp(t))}s`;
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function parseExecRow(text) {
  const clean = String(text || "").replace(/\*\*/g, "").trim();
  const parts = clean.split(/\s*\|\s*/).map((p) => p.trim()).filter(Boolean);
  if (parts.length >= 4) {
    return {
      ticker: parts[0],
      side: parts[1],
      suggestion: parts[2],
      reason: parts.slice(3).join(" | "),
    };
  }
  return null;
}

function sideClass(side) {
  const s = String(side || "");
  if (/唔短|唔好短|不短|唔 long|skip/i.test(s)) return "side-watch";
  if (/\bshort\b/i.test(s) || /做空|偏空/.test(s)) return "side-short";
  if (/trim|賣強|賣部分|已賣/.test(s)) return "side-trim";
  if (/\blong\b/i.test(s) && !/失手/.test(s)) return "side-long";
  return "side-watch";
}

function tlKey(ticker) {
  return String(ticker || "")
    .replace(/\*\*/g, "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "");
}

function jumpToTimelineTicker(ticker) {
  const key = tlKey(ticker);
  if (!key) return;
  const root = $("timeline");
  const el =
    root?.querySelector(`[data-ticker="${key}"]`) ||
    document.getElementById(`tl-${key}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("tl-flash");
  setTimeout(() => el.classList.remove("tl-flash"), 1600);
}

function tickerJumpHtml(ticker) {
  const key = tlKey(ticker);
  return `<a href="#tl-${escapeHtml(key)}" class="tk-jump" data-jump="${escapeHtml(
    key
  )}">${escapeHtml(ticker)}</a>`;
}

function tickerTableHtml(items, videoId) {
  const notes = [];
  const rows = [];
  const seenId = new Set();
  for (const b of items) {
    const parsed = parseExecRow(b.text);
    if (parsed) rows.push({ t: b.t || "", ...parsed });
    else notes.push(b);
  }
  const noteHtml = notes.length
    ? `<ul>${notes
        .map((b) => {
          const clean = String(b.text || "").replace(/\*\*/g, "");
          const t = b.t || "";
          const chip = t
            ? `<a class="t" href="${ytLink(videoId, t)}" target="_blank" rel="noreferrer">${escapeHtml(t)}</a>`
            : "";
          return `<li>${chip}<span>${escapeHtml(clean)}</span></li>`;
        })
        .join("")}</ul>`
    : "";
  const reasonHead = lang === "en" ? "ASR English (original)" : "語音中文翻譯";
  const tableHtml = rows.length
    ? `<div class="ticker-wrap"><table class="ticker-table">
        <thead><tr><th>${lang === "en" ? "Time" : "時間"}</th><th>${lang === "en" ? "Ticker" : "股票"}</th><th>Long/Short</th><th>${lang === "en" ? "Source" : "建議"}</th><th>${reasonHead}</th></tr></thead>
        <tbody>${rows
          .map((r) => {
            if (/語音未核實/.test(String(r.reason || "") + String(r.ticker || ""))) return "";
            const key = tlKey(r.ticker);
            const idAttr = key && !seenId.has(key) ? ` id="tl-${key}"` : "";
            if (key) seenId.add(key);
            const chip =
              r.t && r.t !== "00:00"
                ? `<a class="t" href="${ytLink(videoId, r.t)}" target="_blank" rel="noreferrer">${escapeHtml(r.t)}</a>`
                : `<span class="muted">—</span>`;
            // strip leftover English dump if old md still has ｜原文：
            const reason = String(r.reason || "").replace(/\s*｜原文：[\s\S]*$/, "").trim();
            return `<tr${idAttr} data-ticker="${escapeHtml(key)}">
              <td>${chip}</td>
              <td class="tk">${escapeHtml(r.ticker)}</td>
              <td><span class="side ${sideClass(r.side)}">${escapeHtml(r.side)}</span></td>
              <td>${escapeHtml(r.suggestion)}</td>
              <td>${escapeHtml(reason)}</td>
            </tr>`;
          })
          .join("")}</tbody>
      </table></div>`
    : "";
  return { noteHtml, tableHtml, rows };
}

function renderExec(items, videoId) {
  const box = $("execBox");
  if (!items?.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    // #region agent log
    fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'B',location:'app.js:renderExec',message:'exec_hidden_empty',data:{n:items?.length||0,videoId},timestamp:Date.now(),runId:'pre'})}).catch(()=>{});
    // #endregion
    return;
  }
  const looksDigest = items.some((x) =>
    /^(今日總覽|實際操作｜|做多｜|做空｜|減倉｜|觀望｜)/.test(String(x.text || "").replace(/\*\*/g, ""))
  );
  if (looksDigest) {
    const meta = [];
    const actions = [];
    const groups = { long: [], short: [], trim: [], watch: [] };
    for (const b of items) {
      const clean = String(b.text || "").replace(/\*\*/g, "").trim();
      if (/^今日總覽/.test(clean)) {
        meta.push(clean.replace(/^今日總覽\s*—\s*/, ""));
        continue;
      }
      if (/^(可信度|缺口)/.test(clean)) continue; // meta noise — never show in digest UI
      const act = clean.match(/^實際操作｜(.+)$/);
      if (act) {
        const body = act[1];
        const parts = body.split(/\s*—\s*/);
        actions.push({ ticker: (parts[0] || "").trim(), reason: (parts.slice(1).join(" — ") || "").trim() });
        continue;
      }
      const m = clean.match(/^(做多|做空|減倉|觀望)｜(.+)$/);
      if (m) {
        const body = m[2];
        const parts = body.split(/\s*—\s*/);
        const ticker = (parts[0] || "").trim();
        const reason = (parts.slice(1).join(" — ") || "").trim();
        const key =
          m[1] === "做多" ? "long" : m[1] === "做空" ? "short" : m[1] === "減倉" ? "trim" : "watch";
        groups[key].push({ ticker, reason });
        continue;
      }
    }
    const tickLink = (ticker, cls) =>
      `<a href="#tl-${escapeHtml(tlKey(ticker))}" class="tk-jump ${cls || ""}" data-jump="${escapeHtml(
        tlKey(ticker)
      )}">${escapeHtml(ticker)}</a>`;
    const sec = (title, key, arr, cls) => {
      if (!arr.length) return "";
      return `<section class="digest-sec ${cls}">
        <h4>${title}</h4>
        <ul>${arr
          .map(
            (x) =>
              `<li>${tickLink(
                x.ticker,
                `side ${sideClass(
                  key === "long" ? "Long" : key === "short" ? "Short" : key === "trim" ? "Trim" : "Watch"
                )}`
              )} <span class="why">${escapeHtml(x.reason)}</span></li>`
          )
          .join("")}</ul>
      </section>`;
    };
    const actHtml = actions.length
      ? `<section class="digest-sec dg-action">
          <h4>實際操作（佢講過有倉／再入／平倉）· 撳名跳時間軸</h4>
          <ul>${actions
            .map(
              (x) =>
                `<li>${tickLink(x.ticker, "side side-trim")} <span class="why">${escapeHtml(
                  x.reason
                )}</span></li>`
            )
            .join("")}</ul>
        </section>`
      : "";
    const metaHtml = meta.length
      ? `<p class="digest-lede">${escapeHtml(meta.join(" "))}</p>`
      : "";
    box.classList.remove("hidden");
    box.innerHTML = `<h3>摘要（中文）· 撳股票名跳去時間軸</h3>${metaHtml}${actHtml}
      <div class="digest-grid">
        ${sec("做多 Long", "long", groups.long, "dg-long")}
        ${sec("做空 Short", "short", groups.short, "dg-short")}
        ${sec("減倉／平倉", "trim", groups.trim, "dg-trim")}
        ${sec("觀望 Watch", "watch", groups.watch, "dg-watch")}
      </div>
      <p class="digest-foot muted">詳細時間戳＋語音中文翻譯喺下面「時間軸內容」</p>`;
    box.querySelectorAll("a.tk-jump").forEach((a) => {
      a.addEventListener("click", (ev) => {
        ev.preventDefault();
        jumpToTimelineTicker(a.getAttribute("data-jump") || a.textContent);
      });
    });
    // #region agent log
    fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'B',location:'app.js:renderExec',message:'exec_digest_groups',data:{long:groups.long.length,short:groups.short.length,trim:groups.trim.length,watch:groups.watch.length,actions:actions.length,meta:meta.length},timestamp:Date.now(),runId:'post'})}).catch(()=>{});
    // #endregion
    return;
  }
  const { noteHtml, tableHtml } = tickerTableHtml(items, videoId);
  box.classList.remove("hidden");
  box.innerHTML = `<h3>真正摘要（中文）· 撳時間可跳片</h3>${noteHtml}${tableHtml}`;
  // #region agent log
  fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'B',location:'app.js:renderExec',message:'exec_painted',data:{n:items.length,pipe:items.filter(x=>String(x.text||'').includes('|')).length,noteHtmlLen:noteHtml.length,tableHtmlLen:tableHtml.length,hidden:box.classList.contains('hidden'),htmlLen:box.innerHTML.length},timestamp:Date.now(),runId:'pre'})}).catch(()=>{});
  // #endregion
}

function renderWaitingPanel({ title, lines, spinner = true }) {
  const root = $("timeline");
  const spin = spinner ? `<div class="spinner" aria-hidden="true"></div>` : "";
  root.innerHTML = `<div class="panel-wait">
    ${spin}
    <h3>${escapeHtml(title)}</h3>
    <ul>${lines.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul>
  </div>`;
}

function visionAt(byT, t) {
  if (!byT || !t) return null;
  if (byT[t]) return byT[t];
  const n = parseTimestamp(t);
  for (const [k, v] of Object.entries(byT)) {
    if (parseTimestamp(k) === n) return v;
  }
  return null;
}

function renderTimeline(bullets, videoId) {
  const root = $("timeline");
  if (!bullets?.length) {
    root.innerHTML = `<div class="empty">呢個語言暫時未有重點。試下切換 中文／English，或者等轉寫／總結完成。</div>`;
    // #region agent log
    fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'C',location:'app.js:renderTimeline',message:'timeline_empty',data:{lang,zh:current.bullets_zh?.length||0,en:current.bullets_en?.length||0},timestamp:Date.now(),runId:'pre'})}).catch(()=>{});
    // #endregion
    return;
  }
  const SHOW_SCREEN_CHECK = false; // 暫時關閉畫面核對截圖
  const byT = SHOW_SCREEN_CHECK ? current.vision?.by_t || {} : {};
  const looksTable = bullets.filter((b) => String(b.text || "").includes("|")).length >= 3;
  let head = "";
  if (looksTable) {
    const { noteHtml, tableHtml } = tickerTableHtml(bullets, videoId);
    head = `<h3>${lang === "en" ? "Timeline content (EN · ASR original)" : "時間軸內容"}</h3>${noteHtml}${tableHtml}`;
  }
  const cards = bullets
    .map((b) => {
      const t = b.t || "00:00";
      const vis = SHOW_SCREEN_CHECK ? visionAt(byT, t) : null;
      let shot = "";
      if (vis?.header || vis?.frame) {
        const src = vis.header || vis.frame;
        const flagCls = vis.price_fail
          ? "ocr-flag bad"
          : vis.speech_split
            ? "ocr-flag warn"
            : vis.mismatch
              ? "ocr-flag bad"
              : "ocr-flag";
        const sym = vis.screen_symbol || (vis.ocr_tickers || [])[0];
        const srcLabel = vis.label_source === "cursor-agent" ? "Cursor" : "OCR";
        let flagTxt;
        if (sym) {
          const price = vis.screen_price != null ? ` ~$${vis.screen_price}` : "";
          const mm = vis.mismatch
            ? ` ≠ 摘要 ${(vis.claimed || []).join(" ")}`
            : "";
          let extra = "";
          if (vis.price_fail) {
            extra = vis.price_suggest
              ? ` ｜報價唔夾，較似 ${vis.price_suggest}`
              : " ｜報價唔夾";
          } else if (vis.speech_split && (vis.speech_tickers || []).length) {
            extra = ` ｜語音 ${(vis.speech_tickers || []).join(" ")}`;
          }
          flagTxt = `畫面 ${sym}${price}（${srcLabel}）${mm}${extra}`;
        } else if (vis.frame || vis.header) {
          flagTxt = "畫面有截圖（未標 ticker）";
        } else {
          flagTxt = "";
        }
        shot = `<div><img class="frame-thumb" src="${escapeHtml(src)}" alt="${escapeHtml(t)}" /><div class="${flagCls}">${escapeHtml(flagTxt)}</div></div>`;
      } else {
        shot = SHOW_SCREEN_CHECK ? `<div></div>` : "";
      }
      return `<div class="row${SHOW_SCREEN_CHECK ? "" : " no-shot"}">
        <a class="t" href="${ytLink(videoId, t)}" target="_blank" rel="noreferrer">${escapeHtml(t)}</a>
        <div class="txt">${escapeHtml(b.text || "")}</div>
        ${shot}
      </div>`;
    })
    .join("");
  if (looksTable) {
    // 畫面核對暫時關閉（截圖／OCR 對摘要幫助唔大）
    root.innerHTML = head;
    // #region agent log
    fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'C',location:'app.js:renderTimeline',message:'timeline_table',data:{n:bullets.length,looksTable,headLen:head.length,htmlLen:root.innerHTML.length,tableRows:root.querySelectorAll('tr').length,screenCheck:false},timestamp:Date.now(),runId:'post'})}).catch(()=>{});
    // #endregion
    return;
  }
  root.innerHTML = cards;
}

function activeBullets() {
  if (lang === "zh" && current.bullets_zh?.length) return current.bullets_zh;
  if (lang === "en" && current.bullets_en?.length) return current.bullets_en;
  return current.bullets_zh?.length ? current.bullets_zh : current.bullets_en || [];
}

function setLang(next) {
  lang = next;
  $("langZh").classList.toggle("active", lang === "zh");
  $("langEn").classList.toggle("active", lang === "en");
  if (current.status === "whisper_running" || current.status === "pending_agent") return;
  renderTimeline(activeBullets(), current.videoId);
}

function showWhisperWaiting(extra = {}) {
  const step = extra.step || "download+transcribe";
  const jobStatus = extra.status || "running";
  renderWaitingPanel({
    title: "呢條片冇 YouTube 字幕 — 正在用 Whisper 轉寫",
    lines: [
      `片名：${current.title || current.videoId}`,
      `狀態：${jobStatus} · 步驟：${step}`,
      "音訊已下載後會慢慢轉成文字（約 3 小時片，CPU 可能要好耐）",
      "唔使狂撳 Analyze — 完成後會自動再試，或者你再撳一次",
      `進度 API：/api/whisper/${current.videoId}`,
    ],
  });
}

function showAgentWaiting() {
  renderWaitingPanel({
    title: "舊版「等 Chat 總結」已取消",
    spinner: false,
    lines: [
      "而家 Analyze 會自動寫摘要＋語音閘。",
      "請再撳一次 Analyze（必要時勾 Force）。",
    ],
  });
}

async function pollWhisper(videoId) {
  try {
    const st = await fetch(`/api/whisper/${videoId}`).then((r) => r.json());
    const job = st.job || {};
    if (st.transcript_ready || job.status === "done") {
      stopPoll();
      setStatus("Whisper 完成 · 自動再 Analyze…", "ok");
      setHint("轉寫完成。正在載入摘要流程…");
      // Re-run analyze without force so it uses cached transcript
      $("force").checked = false;
      await analyze({ quiet: true });
      return;
    }
    if (job.status === "error") {
      stopPoll();
      setStatus("Whisper 失敗", "err");
      setHint(job.error || "轉寫出錯，睇 data/whisper_jobs 日誌");
      renderWaitingPanel({
        title: "Whisper 轉寫失敗",
        spinner: false,
        lines: [job.error || "未知錯誤", "可喺 Chat 叫我檢查 whisper job"],
      });
      return;
    }
    showWhisperWaiting({ status: job.status || "running", step: job.step || "…" });
    setStatus(`Whisper 進行中 · ${job.step || job.status || "running"}`, "ok");
  } catch (e) {
    setStatus(`輪詢失敗：${e.message || e}`, "err");
  }
}

function startWhisperPoll(videoId) {
  stopPoll();
  pollWhisper(videoId);
  pollTimer = setInterval(() => pollWhisper(videoId), 8000);
}

function renderSpeechAudit(audit) {
  const box = $("auditBox");
  if (!box) return;
  if (!audit) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  const n = audit.suspect_count || 0;
  const ok = audit.ok_count || 0;
  fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'D',location:'app.js:renderSpeechAudit',message:'ui_audit',data:{n,ok,hidden:(audit.suspects||[]).slice(0,12)},timestamp:Date.now()})}).catch(()=>{});
  if (!n) {
    box.classList.remove("hidden");
    box.classList.add("ok");
    box.innerHTML = `語音核對通過：${ok} 行 ticker 喺附近字幕搵到（或畫面吻合）。`;
    return;
  }
  const rows = (audit.suspects || [])
    .slice(0, 12)
    .map((s) => `<li><code>${escapeHtml(s.t)}</code> <b>${escapeHtml(s.ticker)}</b></li>`)
    .join("");
  box.classList.remove("hidden");
  box.classList.remove("ok");
  box.innerHTML = `<div><b>語音核對未過 ${n} 行</b>——呢啲已從主表拎走，唔使一條條對。Analyze／save 每次都會自動跑。</div><ul>${rows}</ul>`;
}

const comparePatchedOnce = new Set();

async function showResult(data, opts = {}) {
  current.videoId = data.video_id;
  current.markdown = data.markdown || "";
  current.title = data.title || data.video_id;
  current.bullets_en = data.bullets_en || [];
  current.bullets_zh = data.bullets_zh || [];
  current.exec_zh = data.exec_zh || [];
  current.status = data.status || "ok";
  renderSpeechAudit(data.speech_audit);
  if (!opts.skipCompareRender) {
    if (data.verify) renderCompare(data.verify);
    else renderCompare(null);
  }

  $("url").value = data.url || `https://www.youtube.com/watch?v=${data.video_id}`;
  $("resultTitle").textContent = current.title;
  $("title").value = current.title;
  const link = $("resultLink");
  link.href = data.url || `https://www.youtube.com/watch?v=${data.video_id}`;
  link.textContent = link.href;

  $("copyBtn").disabled = !current.markdown;
  $("downloadBtn").disabled = !current.markdown;
  $("visionBtn").disabled = !current.videoId;
  await loadVision(current.videoId);
  setHint(data.hint || "");

  if (data.status === "whisper_running") {
    renderExec([], current.videoId);
    showWhisperWaiting();
    startWhisperPoll(data.video_id);
    return;
  }
  if (data.status === "pending_agent") {
    stopPoll();
    renderExec(current.exec_zh, current.videoId);
    if (current.bullets_zh?.length || current.bullets_en?.length) {
      setLang(current.bullets_zh?.length ? "zh" : "en");
    } else {
      showAgentWaiting();
    }
    return;
  }

  stopPoll();
  renderExec(current.exec_zh, current.videoId);
  setLang(current.bullets_zh?.length ? "zh" : "en");
  // #region agent log
  fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'E',location:'app.js:showResult',message:'showResult_ok',data:{videoId:current.videoId,status:data.status,execN:(current.exec_zh||[]).length,zhN:(current.bullets_zh||[]).length,enN:(current.bullets_en||[]).length,digestN:(data.digest_zh||[]).length,mdDigest:String(data.markdown||'').includes('真正摘要'),mdContent:String(data.markdown||'').includes('時間軸內容'),mdOld:String(data.markdown||'').includes('重點摘要'),lang,execHidden:$('execBox')?.classList.contains('hidden'),timelineEmpty:!!$('timeline')?.querySelector('.empty')},timestamp:Date.now(),runId:'pre'})}).catch(()=>{});
  // #endregion
  // Auto: keep polling vision + triple compare (Analyze already kicked jobs)
  stopVisionPoll();
  visionPollTimer = setInterval(() => loadVision(current.videoId), 8000);
  if (!opts.skipComparePoll) {
    startComparePoll(current.videoId);
  }
  // #region agent log
  fetch('http://127.0.0.1:7272/ingest/e6d3392e-d1e5-4d28-9951-8f9f929b2bc3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ec629f'},body:JSON.stringify({sessionId:'ec629f',hypothesisId:'D',location:'app.js:showResult',message:'ui_exec_timeline_stamps',data:{videoId:current.videoId,exec0949:(current.exec_zh||[]).filter(x=>x.t==='09:49'||x.t==='10:10'||/TWLO|Twilio/i.test(x.text||'')).map(x=>({t:x.t,text:(x.text||'').slice(0,160)})),zh0949:(current.bullets_zh||[]).filter(x=>x.t==='09:49'||x.t==='10:10'||/TWLO/i.test(x.text||'')).map(x=>({t:x.t,text:(x.text||'').slice(0,160)}))},timestamp:Date.now()})}).catch(()=>{});
  // #endregion
}

async function refreshSaved() {
  const list = await fetch("/api/summaries").then((r) => r.json());
  const root = $("savedList");
  if (!list.length) {
    root.innerHTML = `<div class="muted" style="font-size:13px">未有已存摘要。</div>`;
    return;
  }
  root.innerHTML = list
    .map(
      (item) => `<button class="saved-item" data-id="${escapeHtml(item.video_id)}">
        <div>${escapeHtml(item.title)}</div>
        <div class="id">${escapeHtml(item.video_id)} · ${item.bullet_count} notes</div>
      </button>`
    )
    .join("");
  root.querySelectorAll(".saved-item").forEach((btn) => {
    btn.addEventListener("click", () => openSaved(btn.dataset.id));
  });
}

async function openSaved(videoId) {
  stopPoll();
  stopComparePoll();
  stopVisionPoll();
  setStatus("Loading…");
  try {
    const data = await fetch(`/api/summaries/${videoId}`).then(async (r) => {
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    });
    await showResult(data);
    setStatus("已載入摘要", "ok");
  } catch (e) {
    setStatus(String(e.message || e), "err");
  }
}

async function prefetchTitle() {
  const url = $("url").value.trim();
  if (!url) return;
  try {
    const meta = await fetch(`/api/meta?url=${encodeURIComponent(url)}`).then((r) => r.json());
    if (meta.title) $("title").value = meta.title;
  } catch (_) {
    /* ignore */
  }
}

async function analyze(opts = {}) {
  const url = $("url").value.trim();
  if (!url) {
    setStatus("請貼 YouTube URL", "err");
    return;
  }
  const btn = $("analyzeBtn");
  btn.disabled = true;
  if (!opts.quiet) {
    setHint("");
    setStatus("拉字幕／總結中…");
    renderWaitingPanel({
      title: "處理中…",
      lines: ["正在檢查字幕／cache", "如果冇字幕會開 Whisper，主畫面會顯示進度"],
    });
  }
  try {
    await prefetchTitle();
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        title: $("title").value.trim() || null,
        provider: $("provider").value,
        force: $("force").checked,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    if (data.title) $("title").value = data.title;
    await showResult(data);
    if (data.status === "pending_agent") {
      setStatus(`字幕已備好 · 等 Cursor Agent · ${data.video_id}`, "ok");
    } else if (data.status === "whisper_running") {
      setStatus(`冇字幕 · Whisper 轉寫中 · ${data.video_id}`, "ok");
    } else if (data.status === "cached") {
      setStatus(`已載入最新摘要（未重跑）· ${data.video_id} · 撳左側 Saved 可換片`, "ok");
    } else {
      setStatus(`完成 · ${data.bullet_count} 條 · ${data.provider}`, "ok");
    }
    await refreshSaved();
  } catch (e) {
    setStatus(String(e.message || e), "err");
    renderWaitingPanel({
      title: "Analyze 失敗",
      spinner: false,
      lines: [String(e.message || e)],
    });
  } finally {
    btn.disabled = false;
  }
}

$("analyzeBtn").addEventListener("click", () => analyze());
$("visionBtn").addEventListener("click", () => startVision());
$("langZh").addEventListener("click", () => setLang("zh"));
$("langEn").addEventListener("click", () => setLang("en"));
$("url").addEventListener("change", prefetchTitle);
$("copyBtn").addEventListener("click", async () => {
  await navigator.clipboard.writeText(current.markdown);
  setStatus("Markdown copied", "ok");
});
$("downloadBtn").addEventListener("click", () => {
  const blob = new Blob([current.markdown], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${current.videoId || "summary"}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
});

async function boot() {
  await refreshSaved();
  const first = document.querySelector(".saved-item");
  if (first) {
    await openSaved(first.dataset.id);
    return;
  }
  const url = $("url").value.trim();
  if (url) await analyze({ quiet: true });
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
