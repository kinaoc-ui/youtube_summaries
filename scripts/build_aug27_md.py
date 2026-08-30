# -*- coding: utf-8 -*-
"""Build bilingual summary for Long softwares short semis | 27 Aug 2026.

Timeline notes lead with 【畫面 TICKER】 from Cursor-labeled screenshots
(data/frames/5ACCeRUiR2k/labels.json). Speech content kept after when useful.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "5ACCeRUiR2k.md"

# (t, en, zh) — screen symbol is authoritative for "what's on chart"
ROWS = [
    ("00:15", "【畫面 —】Stream open / black; chat about training / Clement", "【畫面 —】開場（未開圖）；傾訓練／Clement"),
    ("05:15", "【畫面 QQQ ~711】Too many names; software strong (OKTA EP etc.) — wait pullback, don't chase; weak names gap into resistance (e.g. APLD)", "【畫面 QQQ ~711】提早開播；software 強（OKTA EP 等）— 等回抽唔追；弱勢 gap 入阻力（如 APLD）"),
    ("06:47", "【畫面 RDDT ~155】RDDT weak after bearish reversal; ASR also: CRWV(Call Vith) / BE(VE) / AOI into resistance", "【畫面 RDDT ~155】RDDT 弱反轉後仲弱；同段 ASR：CRWV（Call Vith）／BE（VE）／AOI 入阻力"),
    ("08:18", "【畫面 NVDA ~210】Not chasing strength; plan = software pullbacks OR shorts; tape selective", "【畫面 NVDA ~210】唔追強；計劃 = software 回抽 或 short；行情選擇性"),
    ("09:49", "【畫面 QQQ ~711｜watchlist 已揀 AXTI】Still on QQQ chart; AXTI highlighted in list — switches to AXTI by 09:55", "【畫面 QQQ ~711｜watchlist 已揀 AXTI】主圖仲係 QQQ，清單已揀 AXTI；09:55 先切 AXTI 主圖"),
    ("09:55", "【畫面 AXTI ~65】AXTI gap into resistance — take the short", "【畫面 AXTI ~65】AXTI gap 入阻力 — 做空"),
    ("10:10", "【畫面 TWLO ~228】TWLO: wait gap-up pullback into rising 9 for long; don't chase if software rips", "【畫面 TWLO ~228】TWLO：等 gap 後回抽 rising 9 先 long；software 直上就唔追"),
    ("11:31", "【畫面 COIN ~182】Exploring alerts (too many names); COIN pullback into prior highs finding support (ASR said 'octaves' — not OKTA)", "【畫面 COIN ~182】試 alerts（名太多）；COIN 回抽舊高搵 support（ASR 寫 octaves＝聽錯，唔係 OKTA）"),
    ("16:04", "【畫面 MU ~949】ASR SMTK(=SNDK) & MU gap then fade into rising EMAs; HPQ(HBQ) shakeout", "【畫面 MU ~949】ASR SMTK(=SNDK)、MU gap 後淡入 rising EMA；HPQ（HBQ）shakeout"),
    ("19:49", "【畫面 TEM ~69｜語音 IGV】Dislikes extended software / this IAF(=IGV) into daily 9 (chart = TEM)", "【畫面 TEM ~69｜語音 IGV】唔鍾意 software／IAF(=IGV) 太伸近 daily 9（主圖 TEM）"),
    ("24:46", "【畫面 APLD ~28】APLD into declining 9; stopped on hour-and-a-cube(=IREN) — consider re-short; SMCI super strong", "【畫面 APLD ~28】APLD 近 declining 9；止蝕 IREN（ASR hour and a cube）可再短；SMCI 超強"),
    ("27:24", "【畫面 SMCI ~39】Feels early again; 15m close strong on many names; SMCI ripping", "【畫面 SMCI ~39】又覺得入得太早；SMCI 好強；好多股 15m close 強"),
    ("30:20", "【畫面 SNDK ~1510】SNDK & MU pullback weak; software still very strong", "【畫面 SNDK ~1510】SNDK、MU 回抽弱；software 仍然好強"),
    ("40:10", "【畫面 OKLO ~43｜語音 quantum/PATH】Shorted quantums; sold some PATH into strength; hates IGV extension (chart = Oklo)", "【畫面 OKLO ~43｜語音 quantum/PATH】短咗 quantum；PATH 賣部分；討厭 IGV 伸展（主圖係 OKLO）"),
    ("47:36", "【畫面 QQQ ~717】Software holding; WODF(=HOOD) resistance; SMR/USAR strong; SMTK(=SNDK)/MU at rising EMAs", "【畫面 QQQ ~717】Software 企穩；WODF(=HOOD) 阻力；SMR／USAR 強；SMTK(=SNDK)/MU 睇 rising EMA"),
    ("49:45", "【畫面 PATH ~18】PATH spike — little volume expansion yet; sell more into strength after prolonged 9-EMA surf", "【畫面 PATH ~18】PATH 大陽；成交未大擴；沿 9 EMA 後放量 → 賣強"),
    ("52:48", "【畫面 CRWD ~222】IGV ~+6% — not shorting ETF; then CRM EP; crowd(=CRWD) strong; TASTA(=TSLA) won't go down; Armels(=ARM) strong", "【畫面 CRWD ~222】IGV +6% 唔短 ETF；CRM EP；crowd(=CRWD) 好強；TASTA(=TSLA) 唔肯落；Armels(=ARM) 強"),
    ("56:42", "【畫面 ARM ~266｜語音 DDOG】D-talk(=DDOG) expectation breaker — opened weak then cleared 15/21; chart ARM", "【畫面 ARM ~266｜語音 DDOG】D-talk(=DDOG) 例外強勢；開弱後穿 15/21；主圖 ARM"),
    ("1:04:12", "【畫面 SKHY ~161】Pullbacks into 60m EMAs uncertain; already short a lot; mega-cap services soft", "【畫面 SKHY ~161】回抽 60m EMA 唔定；已短好多；mega-cap services 軟"),
    ("1:06:44", "【畫面 SKHY ~162】Not buying here; SPY/QQQ at highs; SK Hynix still lower in range", "【畫面 SKHY ~162】而家唔買；SPY/QQQ 高位；SK Hynix 區間下半"),
    ("1:09:11", "【畫面 TSLA ~353｜語音 RDDT】Speech: RDDT short moving fast / missed ~157.30 bounce — chart is TSLA", "【畫面 TSLA ~353｜語音 RDDT】語音講 RDDT short／錯過 ~157.30 — 主圖係 TSLA"),
    ("1:21:49", "【畫面 WDC ~458】Theme: long software / short-or-chop semis; weak semis rejecting (chart = Western Digital)", "【畫面 WDC ~458】主題：long software／short 或震 semi（主圖 WDC）"),
    ("1:23:25", "【畫面 RDDT ~157】RDDT limit filled; CRWV bounce short attractive but extended from HOD", "【畫面 RDDT ~157】RDDT limit 成交；CRWV 反彈短吸引但離日高有啲伸"),
    ("1:36:17", "【畫面 CRWV ~89】Wanted more CRWV short but runoff BP; keep software longs; quantum uncertain; SPCX dangerous", "【畫面 CRWV ~89】想再短 CRWV 但買力用晒；software 留；quantum 唔定；SPCX 危險"),
    ("1:38:31", "【畫面 RGTI ~16｜語音 ONDS】All NDS(=ONDS) tight-stop short — chart RGTI", "【畫面 RGTI ~16｜語音 ONDS】All NDS(=ONDS) 窄 stop 短 — 主圖 RGTI"),
    ("1:40:33", "【畫面 IONQ ~42】Chat joke (oxytocin); then runoff BP = full margin (chart IonQ)", "【畫面 IONQ ~42】傾 oxytocin；之後講買力用晒（主圖 IONQ）"),
    ("1:41:37", "【畫面仍 IONQ｜語音 TSLA/NVDA】Tesla bouncing; NVDA(videos) continuing up; other large caps lag", "【畫面仍 IONQ｜語音 TSLA/NVDA】TSLA 彈；NVDA 續上；其他大盤滯"),
    ("1:43:50", "【畫面 TSLA ~353】Stopped out; watch 50 EMA + weekly 9; needs 15m fade for short — chart TSLA not SPCX", "【畫面 TSLA ~353】止蝕；睇 50 EMA + weekly 9；要 15m fade 先短 — 主圖 TSLA，唔係 SPCX"),
    ("1:48:00", "【畫面 SPCX ~141｜語音 QBTS】Speech explains why short QBTS (weakest quantum) — chart is SpaceX (SPCX)", "【畫面 SPCX ~141｜語音 QBTS】語音解釋點解短 QBTS — 主圖係 SPCX（SpaceX）"),
    ("1:50:05", "【畫面 RGTI ~16｜語音 MU/SK】Speech: MU vs SK Hynix relative weakness — chart is RGTI", "【畫面 RGTI ~16｜語音 MU/SK】語音講 MU vs SK Hynix — 主圖係 RGTI"),
    ("1:51:44", "【畫面 SPY ~770】Shorts logical but NVDA strong → may be early/risky", "【畫面 SPY ~770】短邏輯得但 NVDA 強 → 可能太早／風險高"),
    ("1:53:20", "【畫面 AXTI ~66】Quantum shorts lower; RDDT higher; missed CRWV short that worked", "【畫面 AXTI ~66】Quantum 短跟落；RDDT 上；錯過 CRWV 短"),
    ("1:55:11", "【畫面 BE ~219｜語音 HPQ】Speech: HPQ reject 21 — prefers not shorting wide uptrend candles (chart = Bloom Energy)", "【畫面 BE ~219｜語音 HPQ】語音講 HPQ 拒 21 — 主圖係 BE"),
    ("1:58:18", "【畫面 HPQ ~29】Russell bouncing; rejection on weak names while indices strong", "【畫面 HPQ ~29】Russell 彈；指數強同時弱勢有 rejection"),
    ("2:00:00", "【畫面 CLS ~318｜語音 ARM】Speech: ARM fade after AVWAP+21 — chart is Celestica (CLS)", "【畫面 CLS ~318｜語音 ARM】語音講 ARM fade — 主圖係 CLS"),
    ("2:01:32", "【畫面 FIG ~30｜ASR: fake→FIG】Traded FIG badly — entry too aggressive after stop-out; yesterday pullback to 21; if hold FIG, sell into strength today", "【畫面 FIG ~30｜ASR 聽成 fake】FIG 交易差 — 止蝕後入場太進取；昨日回抽 21；若持有 FIG 今日賣強"),
    ("2:04:49", "【畫面 SPCX ~141】Selling into strength is an art; trim when hyped/sharing P&L", "【畫面 SPCX ~141】賣強係藝術；開心／想分享時 trim"),
    ("2:08:36", "【畫面 SPCX ~140】Too early shorting Tuesday; SPCX longs were bad looking back; SNDK/MU lose 9&21 = upthrust risk", "【畫面 SPCX ~140】周二短太早；SPCX long 事後差；SNDK/MU 失 9&21 = 假突破風險"),
    ("2:12:38", "【畫面 ORCL ~148｜語音金銀】Don't short gold/silver too early — wait close below daily 9 (chart ORCL)", "【畫面 ORCL ~148｜語音金銀】金銀唔好太早短 — 等收低過 daily 9（主圖 ORCL）"),
    ("2:14:26", "【畫面 OKLO ~69｜語音金銀/Russell】Still waiting gold/silver close; Russell strong — awkward to short (chart OKLO)", "【畫面 OKLO ~69｜語音金銀/Russell】仲等金銀 close；Russell 仲強、短得怪（主圖 OKLO）"),
    ("2:16:37", "【畫面仍 OKLO｜語音 SOXX】socket(=SOXX) still riding 50m / near daily 9 — key direction", "【畫面仍 OKLO｜語音 SOXX】socket(=SOXX) 沿 50m／近 daily 9 — 關鍵分水嶺"),
    ("2:19:28", "【畫面 SOXX ~522】Q&A: watching streams alone won't make you profitable — must trade & study mistakes", "【畫面 SOXX ~522】Q&A：淨睇 stream 唔會賺；要自己做單、研究錯"),
    ("2:23:13", "【畫面 DOGEUSD】Crypto strong — break prior day highs; beaten-down names can spike to weekly 21/50", "【畫面 DOGEUSD】Crypto 強 — 破前高；捱打過可插 weekly 21/50"),
    ("2:25:08", "【畫面 AXTI ~66】Weekly failed breakout after enormous run (chart AXTI; no separate HTI ticker)", "【畫面 AXTI ~66】周線失敗突破後跟落（主圖 AXTI；冇獨立 HTI）"),
    ("2:28:56", "【畫面 IGV ~109】Tough August; turning off other streams; learning boredom / alone time", "【畫面 IGV ~109】八月艱難；關其他人 stream；學處理無聊／獨處"),
    ("2:31:20", "【畫面 ALAB ~298】ALAB decent short if overshoots prior highs into 50 EMA / rejects hourly 150", "【畫面 ALAB ~298】ALAB 短得：衝舊高入 50／拒 hourly 150 先短"),
    ("2:33:55", "【畫面 QQQ ~718】10–15y future unknown — only goal not blow up", "【畫面 QQQ ~718】10–15 年後唔知 — 目標淨係唔爆倉"),
    ("2:37:23", "【畫面 SPCX ~141】USIC: entered Jan with <$1M; pressure more from attention than money size", "【畫面 SPCX ~141】USIC：一月入場 <100 萬；壓力多來自目光"),
    ("2:41:01", "【畫面 SPCX ~141】Viewers not profitable until they understand own edge + deal with mistakes", "【畫面 SPCX ~141】觀眾要明白自己 edge + 處理錯誤"),
    ("2:43:45", "【畫面 MSTR ~138】MSTR +12% vs BTC +1.5% — possible re-rating / risk premium", "【畫面 MSTR ~138】MSTR +12% vs BTC +1.5% — 可能 re-rating"),
    ("2:46:31", "【畫面 SPCX ~142】Streams free to pass the torch — learned a lot from Christian & others", "【畫面 SPCX ~142】免費直播傳火炬；從 Christian 等人學好多"),
    ("2:48:30", "【畫面 QBTS】Interesting day: best technical entries mostly shorts; software followed through; semis LTF bounce", "【畫面 QBTS】有趣一日：技術最好入場多在短邊；software 跟進強；semi LTF 彈"),
    ("2:50:59", "【畫面 FROG ~102｜語音 Whisper: AMD】Chart = JFrog (FROG); speech (ASR) says AMD could short tomorrow if stays weak / failed reclaim 50&21, push to 9", "【畫面 FROG ~102｜語音 ASR 寫 AMD】主圖係 FROG（JFrog）；語音（Whisper）講 AMD 若續弱／失敗收復 50&21、壓向 9 或可明日短"),
    ("2:54:16", "【畫面 SPCX ~141】SPCX: prior two losses tiny (~0.1–0.15%) — can retry until clear weekly 9", "【畫面 SPCX ~141】SPCX：前兩次虧約 0.1–0.15%；可再試到 weekly 9 清楚"),
    ("2:55:47", "【畫面 SPCX ~141】5m ORB working today (semis/software) — but he thinks ORB win-rate often too low", "【畫面 SPCX ~141】今日 5m ORB 得；但佢覺得 ORB 勝率往往偏低"),
    ("2:59:21", "【畫面 CRM ~399】Study = scavenger-hunt charts for your own answers — that's the edge", "【畫面 CRM ~399】學習：scavenger hunt 搵自己答案 — 先係 edge"),
    ("3:00:55", "【畫面 QQQ ~718】Ends ~3h; no more trades except maybe SPCX if stopped again; thanks", "【畫面 QQQ ~718】約 3h 收播；或再試 SPCX；多謝"),
]

EN = [(t, en) for t, en, _ in ROWS]
ZH = [(t, zh) for t, _, zh in ROWS]

# Speech-first ticker board: 建議／原因 = 佢講咩（畫面只係核對用，唔入原因欄）
EXEC = [
    ("05:15", "**大方向** | Long software／Short 弱勢+semi | 等回抽；唔追開市 gap 強 | Software（OKTA EP 等）開強；弱勢股 gap 入阻力，唔好追"),
    ("05:15", "**OKTA** | Long（等） | 等回抽／唔追 EP | 開場講 OKTA EP；等 pullback（唔係 11:31）"),
    ("06:47", "**RDDT** | Short | 短 | 弱反轉後仲弱；後段 red ditch limit"),
    ("06:47", "**CRWV** | Short（想做） | 睇 gap-down／年底區 | 開場 ASR Call Vith=CRWV；1:36 Corvif 想再短但 BP 唔夠"),
    ("06:47", "**BE** | Watch／短候選 | 睇 swing high + 50 | ASR VE is going=BE"),
    ("06:47", "**AOI** | Watch／短候選 | Gap 入未填 gap + declining 9/21 | 原文有 AOI"),
    ("08:18", "**執行紀律** | — | 唔追強 | software 回抽 或 short"),
    ("09:55", "**AXTI** | Short | 做空 | Gap 入阻力；畫面 09:55 AXTI ~65"),
    ("10:10", "**TWLO** | Long（等） | 等 rising 9 先買 | 畫面 TWLO ~228；唔追直上"),
    ("11:31", "**COIN** | Watch | 回抽舊高；試 alerts | 主圖 COIN；ASR octaves≠OKTA"),
    ("16:04", "**SNDK** | Watch／偏空 | 睇 rising EMA | ASR SMTK=SNDK；同 MU"),
    ("16:04", "**MU** | Watch／相對弱 | 同 SNDK | Gap 淡入 rising EMA"),
    ("19:49", "**IGV** | Watch／唔短 ETF | 唔短 IGV | ASR this IAF；52:35 再講 +6%"),
    ("24:46", "**APLD** | Short／弱 | 睇 declining 9 | 原文 APLD"),
    ("24:46", "**IREN** | Short（再試） | 止蝕後可再短 | ASR hour and a cube=IREN"),
    ("24:46", "**SMCI** | Long／超強 | 唔逆勢短 | 原文 SMCI super strong"),
    ("40:10", "**Quantum（QBTS 等）** | Short | 短最弱量子 | 已開短；1:48 講明 QBTS 最弱"),
    ("47:45", "**HOOD** | Watch／阻力 | 唔追 | ASR WODF=HOOD"),
    ("47:45", "**SMR / USAR** | Watch／相對強 | 觀察 | ASR SMR and USA"),
    ("49:45", "**PATH** | Trim／賣強 | 賣部分；放量再賣多 | 原文 path／9 EMA"),
    ("52:48", "**CRWD** | Long／強 | 跟 software | ASR this crowd≈54:34"),
    ("54:09", "**CRM** | Long／跟進 | EP 跟進 | 原文 CRM's EP"),
    ("54:34", "**TSLA** | 唔短 | 唔逆勢 | ASR TASTA 唔肯落"),
    ("55:22", "**ARM** | Watch／強 | 早段強 | ASR Armels（AVWAP fade 係 2:00）"),
    ("56:42", "**DDOG** | Long／強 | 例外強勢 | ASR D-talk 開弱後穿 15/21"),
    ("1:06:44", "**SK Hynix** | Watch | 區間下半唔追 | ASR SK Heinz"),
    ("1:09:11", "**RDDT** | Short | 入場快 | ASR red ditch"),
    ("1:21:49", "**主題** | Long software／Short 或震 semi | 跟主題 | 弱 semi 拒；software 強"),
    ("1:36:17", "**買力** | — | 唔好再開多倉 | Runoff／margin 用晒"),
    ("1:36:17", "**CRWV** | Short（想做） | BP 唔夠唔加 | ASR Corvif"),
    ("1:38:31", "**ONDS** | Short | 窄 stop | ASR All NDS；declining 50"),
    ("1:41:37", "**TSLA** | Watch／強 | 唔逆勢短 | 原文 Tesla bouncing"),
    ("1:41:37", "**NVDA** | Watch／強 | 短 semi 可能太早 | ASR videos=NVDA 續上"),
    ("1:48:00", "**QBTS** | Short | 短最弱 quantum | 原文 QPS／QBTS"),
    ("1:48:00", "**RGTI** | Watch | 睇龍頭有冇 roll | quantum 比較；IONQ ASR 唔穩唔硬寫"),
    ("1:55:11", "**HPQ** | 唔短大波幅 | 偏 50 EMA long | 拒 21；唔鍾意短巨燭"),
    ("2:00:00", "**ARM** | Watch／錯過短 | AVWAP+21 後 fade | 主圖 CLS；語音 ARM fade"),
    ("2:01:32", "**FIG** | Watch／曾做差 | 持有就賣強 | 畫面 FIG；ASR fake→FIG"),
    ("2:08:36", "**SPCX（SpaceX）** | Watch；曾 Long 失手 | 細虧可再試 weekly 9 | 前兩次虧約 0.1–0.15%"),
    ("2:12:38", "**金／銀** | 唔好太早短 | 等 close 低過 daily 9 | 2:12–2:14；唔係 SOXX"),
    ("2:16:37", "**SOXX** | Watch／關鍵 | 沿 50m／近 daily 9 | ASR socket=SOXX"),
    ("2:31:20", "**ALAB** | Short（等） | 衝舊高入 50／拒 150 | 原文 a lap／ALAB"),
    ("2:43:45", "**MSTR** | Watch | 觀察 vs BTC | +12% vs BTC +1.5%"),
    ("2:48:30", "**收結感覺** | 短邊技術好／software 強 | 唔好只信一邊 | semi LTF 彈"),
    ("2:50:59", "**FROG** | Watch（畫面） | 睇 JFrog | 主圖 FROG ~102"),
    ("2:50:59", "**AMD** | Short（條件·語音） | 續弱／失 50&21 壓 9 可短 | 原文 AMD；主圖 FROG"),
]

assert len(EN) == len(ZH), (len(EN), len(ZH))

parts = [
    "# Long softwares short semis | 27 Aug 2026",
    "",
    "- **Video:** [5ACCeRUiR2k](https://www.youtube.com/watch?v=5ACCeRUiR2k)",
    "- **Channel:** martinlukkt",
    "- **Source:** cursor-agent（Whisper 語音 + **Cursor 畫面核對** labels.json）",
    "- **Length:** ~3h",
    "",
    "## 重點摘要（中文）",
    "",
]
parts += [f"- `{t}` {txt}" for t, txt in EXEC]
parts += ["", "## Timestamped notes (EN)", ""]
parts += [f"- `{t}` {txt}" for t, txt in EN]
parts += ["", "## 時間軸重點（中文）", ""]
parts += [f"- `{t}` {txt}" for t, txt in ZH]
parts += [
    "",
    "## 畫面核對（附錄·唔係重點原因）",
    "",
    "時間軸右邊縮圖／`labels.json` 用嚟核對主圖 ticker；**重點摘要原因欄只寫佢講嘅邏輯。**",
    "",
    "| 時間 | 畫面主圖 |",
    "|---|---|",
]
for t, en, _ in ROWS:
    sym = "—"
    if "【畫面 " in en:
        chunk = en.split("【畫面 ", 1)[1].split("】", 1)[0]
        sym = chunk.split("｜")[0].strip()
    parts.append(f"| `{t}` | {sym} |")
parts.append("")

OUT.write_text("\n".join(parts), encoding="utf-8")
print("wrote", OUT, "rows", len(ROWS), "exec", len(EXEC))
