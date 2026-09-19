"""Faithful Chinese translation of spoken English ASR excerpts."""
from __future__ import annotations

import re


# Longest-first. Only render meaning that is in the English.
# Chinese is written as \\u escapes so the source stays ASCII-safe.
_PHRASE_RAW: list[tuple[str, str]] = [
    (
        r"and then the semi this semi short i think i took the (?:exit|exti) short first\.?\s*this is the rally into the (?:anchor v|anchored vwap) from the swing high\.?\s*i think the all[\s-]?time high the[.\s]*and also this recent swing high as well",
        "\u7136\u5f8c\u4fc2 semis\uff0c\u5462\u624b semis \u7a7a\u5009\uff0c\u6211\u60f3\u6211\u5148\u5e73\u5497\u5462\u624b\u7a7a\u3002\u5462\u500b\u4fc2\u7531 swing high \u53cd\u5f48\u53bb\u5230 anchored VWAP\u3002\u6211\u89ba\u5f97\u4fc2\u6b77\u53f2\u9ad8\u4f4d\u3002\u540c\u57cb\u6700\u8fd1\u5462\u500b swing high\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09\u90fd\u4fc2",
    ),
    (r"i think i took the (?:exit|exti) short first", "\u6211\u60f3\u6211\u5148\u5e73\u5497\u5462\u624b\u7a7a"),
    (r"i took the (?:exit|exti) short first", "\u6211\u5148\u5e73\u5497\u5462\u624b\u7a7a"),
    (r"took the (?:exit|exti) short", "\u5e73\u5497\u7a7a\u5009"),
    (r"the rally into the (?:anchor v|anchored vwap) from the swing high", "\u7531 swing high \u53cd\u5f48\u53bb\u5230 anchored VWAP"),
    (r"rally into the (?:anchor v|anchored vwap) from the swing high", "\u7531 swing high \u53cd\u5f48\u53bb\u5230 anchored VWAP"),
    (r"this semi shorts?", "\u5462\u624b semis \u7a7a\u5009"),
    (r"the semi shorts?", "semis \u7a7a\u5009"),
    (r"semi shorts?", "semis \u7a7a\u5009"),
    (r"(?:exit|exti) short", "\u5e73\u5497\u7a7a\u5009"),
    (r"anchored vwap|anchor(?:ed)? vwap|\bavwap\b|anchor v\b", "anchored VWAP"),
    (r"swing highs?(?!\uff08)", "swing high\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09"),
    (r"all[\s-]?time highs?", "\u6b77\u53f2\u9ad8\u4f4d"),
    (r"\bath\b", "\u6b77\u53f2\u9ad8\u4f4d"),
    (r"rally(?:ing)? into", "\u53cd\u5f48\u53bb\u5230"),
    (r"take profits?", "\u6e1b\u5009"),
    (r"flip(?:ping)? short", "\u8f49\u7a7a"),
    (r"i shorted (\w+) instead of (\w+)", "我短咗 \\1 而唔係 \\2"),
    (r"i think i'?m going to short", "我今日會短"),
    (r"tesla stops me out at the open", "Tesla 開市 stop 我出嚟"),
    (r"tesla is so weak", "Tesla 好弱"),
    (r"i love to short (\w+) too, but i but i ran off buying power again", "我都想短 \\1，但係又冇晒 buying power"),
    (r"ran off buying power", "冇晒 buying power"),
    (r"reddit is pretty strong today", "Reddit 今日幾強"),
    (r"the breakdown on spacex \(spcx\)", "SpaceX（SPCX）破位"),
    (r"shorting here is definitely very aggressive", "呢度短好進取"),
    (r"i'?m going to short", "我會短"),
    (r"cues is getting rejected at this unfilled gap that we got a few days ago", "QQQ 喺幾日前未填嘅 gap 被 reject"),
    (r"i would also like to short tesla, but i just can'?t because i i i got no buying power left after shorting intel and", "我都想短 Tesla，但係 short 咗 Intel 之後冇晒 buying power"),
    (r"let'?s see whether i will get stopped out on sndk or um sk hynix", "睇下 SNDK／SK Hynix 會唔會 stop 我出嚟"),
    (r"axti right here could be a like a more aggressive short entry because it'?s ringing into both the previous swing lows as the and the 60 minute 9 ema but it is very extended from the daily ema", "AXTI 可以做進取啲嘅短倉入場，因為撞住前低同 60 分鐘 9 EMA，但係已經離 daily EMA 好遠"),
    (r"so far we get a rejection uh on the cues at the hourly 9 declining 9 ema and also this spy is gapping down and", "目前 QQQ 喺 hourly 9（跌緊嘅 9 EMA）被 reject，SPY 都 gap down"),
    (r"at the hourly 9 declining 9 ema and also this spy is gapping down and", "hourly 9 跌緊，SPY 都 gap down"),
    (r"wanted to short seemingly strong stocks like spacex \(spcx\) and dell", "想短睇落強嘅股票，例如 SpaceX（SPCX）同 Dell"),
    (r"i am short sndk", "我短緊 SNDK"),
    (r"asts looks pretty strong", "ASTS 睇落幾強"),
    (r"tesla is pushing into the weekly 9 and also a daily 50 again", "Tesla 頂緊 weekly 9，daily 50 又嚟多次"),
    (r"and also showing relative strength\.? uh in the semi sector as well", "semi 板塊都有相對強勢"),
    (r"let'?s see whether the overall market can gives find some strength in in the software sector", "睇下大市可唔可以喺 software 板塊搵到強勢"),
    (r"got no buying power left", "冇剩 buying power"),
    (r"i would also like to short", "我都想短"),
    (r"more aggressive short entry", "進取啲嘅短倉入場"),
    (r"are also closing weak", "都收市偏弱"),
    (r"closing weak", "收市偏弱"),
    (r"getting rejected", "被 reject"),
    (r"unfilled gap", "未填 gap"),
    (r"gapping down", "gap down"),
    (r"looks pretty strong", "睇落幾強"),
    (r"relative strength", "相對強勢"),
    (r"wanted to short", "想短"),
    (r"pushing into the weekly 9", "頂緊 weekly 9"),
    (r"a few days ago", "幾日前"),
    (r"so far", "目前"),
    (r"i'?m not going to participate for the longs", "long 邊我唔會參與"),
    (r"i'?m short sndk", "我短緊 SNDK"),
    (r"i am considering(?: like)? to flipping short on", "\u6211\u800c\u5bb6\u8003\u616e\u8f49\u7a7a"),
    (r"not looking very encouraging", "\u7747\u843d\u5514\u9f13\u52f5"),
    (r"it closed fairly weak yesterday", "\u5c0b\u65e5\u6536\u5e02\u5e7e\u5f31"),
    (r"found resistance at the daily 9 and 21", "\u649e\u5230 daily 9 \u540c 21 \u963b\u529b"),
    (r"probably not consider buying it today", "\u4eca\u65e5\u53ef\u80fd\u5514\u8003\u616e\u8cb7"),
    (r"it will be a good stock to track", "\u4fc2\u4e00\u96bb\u503c\u5f97\u8ddf\u8e64\u5605\u80a1"),
    (r"do you think", "\u4f60\u89ba\u5f97"),
    (r"good short position", "\u4fc2\u54aa good short \u4f4d"),
    (r"i tried too many times on them", "\u6211\u55ba\u4f62\u54cb\u8eab\u4e0a\u8a66\u592a\u591a\u6b21"),
    (r"the qs especially", "Qs \u5c24\u5176"),
    (r"core vvc", "CRWV"),
    (
        r"i would say(?: yeah)? i think that would be a pretty my observations from (?:from )*(?:the )*(?:from )?this",
        "\u6211\u6703\u8a71\uff0c\u6211\u89ba\u5f97\u5462\u500b\u4fc2\u6211\u5c0d\u5462\u6b21",
    ),
    (
        r"there will be(?: like)? a higher probability of this thing,? this stock,? but this one is",
        "\u5462\u96bb\u6703\u6709\u8f03\u9ad8\u6a5f\u6703",
    ),
    (
        r"the strength in the software and the weakness in the semis can go together at the same time",
        "software \u5605\u5f37\u52e2\u540c semis \u5605\u5f31\u52e2\u53ef\u4ee5\u540c\u6642\u51fa\u73fe",
    ),
    (
        r"something like this light and (\w+) are one of the few examples of the stronger semi-?names",
        "\u597d\u4f3c this light \u540c \\1 \u4fc2\u5c11\u6578\u8f03\u5f37 semi \u4e4b\u4e00",
    ),
    (
        r"there are also some strengths showing up across the different themes",
        "\u5514\u540c\u4e3b\u984c\u90fd\u6709\u5f37\u52e2\u51fa\u73fe",
    ),
    (
        r"worried about the weakness in the semis spread to other sectors",
        "\u64d4\u5fc3 semis \u5f31\u52e2\u64f4\u6563\u53bb\u5176\u4ed6\u677f\u584a",
    ),
    (
        r"(?:it'?s gonna|it will) bring some weakness into the(?: into the)? semi sector",
        "\u6703\u5e36\u5f31\u52e2\u5165 semi \u677f\u584a",
    ),
    (
        r"today we got a gap down in the software sector as a whole",
        "\u4eca\u65e5 software \u677f\u584a\u6574\u9ad4\u6709 gap down",
    ),
    (
        r"today we got a gap down into the hourly 50 ema",
        "\u4eca\u65e5\u6211\u54cb\u6709 gap down \u53bb\u5230 hourly 50 EMA",
    ),
    (r"today we got a gap down", "\u4eca\u65e5\u6211\u54cb\u6709 gap down"),
    (r"wait for (?:the\\s+)*gap down", "\u7b49 gap down"),
    (r"it would be better to wait for", "\u6700\u597d\u7b49"),
    (r"better to wait(?: for)?", "\u6700\u597d\u7b49"),
    (r"instead of(?: like)? buying near(?: near)?(?: the)?", "\u800c\u5514\u597d\u55ba\u63a5\u8fd1\u55f0\u5ea6\u8cb7"),
    (r"into the (?:unfilled|then field) gap(?: level)?", "\u53bb\u5230\u672a\u586b\u7f3a\u53e3\u4f4d"),
    (r"into the hourly 50 ema", "\u53bb\u5230 hourly 50 EMA"),
    (r"early morning flush", "\u65e9\u5e02 flush"),
    (r"buy the dip", "\u8cb7 dip"),
    (r"a decent spot to(?: to)? buy", "\u4e00\u500b\u53ef\u4ee5\u8cb7\u5605\u4f4d"),
    (r"i am considering(?: like)? to flipping short on", "\u6211\u800c\u5bb6\u8003\u616e\u8f49\u7a7a"),
    (r"considering(?: like)? to flipping short", "\u8003\u616e\u8f49\u7a7a"),
    (r"flipping short", "\u8f49\u7a7a"),
    (r"yesterday also close(?: like)? fairly weak", "\u5c0b\u65e5\u6536\u5e02\u90fd\u5e7e\u5f31"),
    (r"(?:the )?quantum'?s looking a little bit shortable today", "quantum \u4eca\u65e5\u7747\u843d\u6709\u5572 shortable"),
    (r"looking a little bit shortable today", "\u4eca\u65e5\u7747\u843d\u6709\u5572 shortable"),
    (r"at the same time", "\u540c\u4e00\u6642\u9593"),
    (
        r"(?:his )?(\w+) is breaking out today after stopping me out a few times in a row",
        "\\1 \u4eca\u65e5\u7834\u4f4d\u5411\u4e0a\uff0c\u4e4b\u524d\u9023\u7e8c\u5e7e\u6b21 stop \u6211\u51fa\u569f",
    ),
    (r"looks like i'?m too early on the (\w+) longs", "\u7747\u569f\u6211\u55ba \\1 long \u5165\u5f97\u592a\u65e9"),
    (r"too early on the (\w+) longs", "\\1 long \u5165\u5f97\u592a\u65e9"),
    (r"finding support with the software sector", "\u9760 software \u677f\u584a\u6435\u5230\u652f\u6301"),
    (r"finding support on the 21(?:\\s*ema)?", "\u55ba 21 EMA \u6435\u5230\u652f\u6301"),
    (r"semis are looking really bad", "semis \u7747\u843d\u597d\u5dee"),
    (r"you'?re right now a little bit", "\u4f60\u800c\u5bb6\u6709\u5c11\u5c11"),
    (r"today we got the nvidia earnings after hours", "\u4eca\u65e5\u6709 Nvidia \u76e4\u5f8c\u696d\u7e3e"),
    (r"give another new direction", "\u5e36\u65b0\u65b9\u5411"),
    (r"in the general market as well", "\u5927\u5e02\u90fd\u4fc2"),
    (r"the market can go polar", "\u5927\u5e02\u53ef\u4ee5\u5169\u6975\u5316"),
    (r"(\w+) is reclaiming its opening and", "\\1 \u55ba reclaim \u958b\u5e02\u540c"),
    (r"looks strong,? showing good strength", "\u7747\u843d\u597d\u5f37\uff0c\u6709\u597d\u5605\u5f37\u52e2"),
    (r"bouncing higher bouncing back", "\u53cd\u5f48\u7dca\u3001\u5f48\u8fd4\u4e0a"),
    (r"see whether we can(?: uh)? whether it can sustain the strength", "\u7747\u4e0b\u53ef\u5514\u53ef\u4ee5\u7dad\u6301\u5462\u80a1\u5f37\u52e2"),
    (r"re-?entering", "\u518d\u5165\u5834"),
    (r"looking back(?: like this)?", "\u7747\u8fd4"),
    (r"i would say(?: yeah)? i think", "\u6211\u6703\u8a71\uff0c\u6211\u89ba\u5f97"),
    (r"oops,?\s*i got stopped on (\w+)", "\u5443\u5440\uff0c\u6211\u55ba \\1 \u88ab stop \u51fa\u569f"),
    (r"i got stopped on (\w+)", "\u6211\u55ba \\1 \u88ab stop \u51fa\u569f"),
    (r"oops,?\s*i got stopped on", "\u5443\u5440\uff0c\u6211\u88ab stop \u51fa\u569f\uff0c\u55ba"),
    (r"i got stopped on", "\u6211\u88ab stop \u51fa\u569f\uff0c\u55ba"),
    (r"i'?m thinking to whether i should(?: like)? close my", "\u6211諗\u7dca\u61c9\u5514\u61c9\u8a72\u55ba\u5ea6\u5e73"),
    (r"i'?m not a fan of(?: like)? the crypto sections? right now", "\u800c\u5bb6\u5514\u9418\u610f crypto \u677f\u584a"),
    (r"follow through to the downside", "\u8ddf\u4f4f\u5411\u4e0b\u8ddf\u8e64"),
    (r"or at least just going to have a slight bounce,?\\s*a weak bounce(?: at the)?", "\u6216\u8005\u81f3\u5c11\u53ea\u4fc2\u8f15\u5fae\u53cd\u5f48\u3001\u5f31\u53cd\u5f48"),
    (r"and apart from that actually right now(?: like)?", "\u9664\u6b64\u4e4b\u5916\u800c\u5bb6"),
    (r"(?:is )?(?:like )?also at the flat 50 and also at the weekly 9 as well", "\u4ea6\u90fd\u55ba flat 50\uff0c\u4ea6\u90fd\u55ba weekly 9"),
    (r"the spy and iwm is stronger against 21", "SPY \u540c IWM \u76f8\u5c0d 21 \u8f03\u5f37"),
    (r"still showing strength doing pretty well", "\u4ecd\u7136\u6709\u5f37\u52e2\u3001\u505a\u5f97\u5514\u932f"),
    (r"and particularly(?: like)?", "\u5c24\u5176\u4fc2"),
    (r"so probably it would be", "\u6240\u4ee5\u53ef\u80fd"),
    (r"so maybe it will", "\u6240\u4ee5\u6216\u8005\u6703"),
    (r"or like it'?s gonna", "\u6216\u8005\u6703"),
    (r"and also maybe", "\u800c\u4e14\u6216\u8005"),
    (r"right here", "\u55ba\u5ea6"),
    (r"as a whole", "\u6574\u9ad4"),
    (r"now they are", "\u800c\u5bb6\u4f62\u54cb"),
    (r"seems like the semi is", "semis \u597d\u4f3c"),
    (r"yeah,? i mean", ""),
    (r"wow,? quantum are stopping me out at the open", "哇，quantum 開市 stop 我出嚟"),
    (r"stopping me out at the open", "開市 stop 我出嚟"),
    (r"path is not finding support so far", "PATH 到而家未搵到支持"),
    (r"not finding support so far", "到而家未搵到支持"),
    (r"software are getting a little bit(?: little bit)? weak today", "software 今日有少少弱"),
    (r"getting a little bit(?: little bit)? weak on the softwares", "software 有少少弱"),
    (r"getting a little bit(?: little bit)? weak today", "今日有少少弱"),
    (
        r"like if the quantums are getting rejected today and then goes lower that will be very unfortunate",
        "如果 quantum 今日被 reject 然後向下，會好唔好彩",
    ),
    (r"you think spacex \(spcx\) is a is the good position to short today\??", "你覺得 SPCX 今日係咪好嘅短倉位？"),
    (r"is (?:a is )?the good position to short today\??", "今日係咪好嘅短倉位？"),
    (r"it looks like semi is still it'?s really strong today", "semis 今日睇落仍然好強"),
    (r"still it'?s really strong today", "今日仍然好強"),
    (r"we found some strength in semis", "semis 有啲強勢"),
    (r"also finding some resistance on semis", "semis 都撞到阻力"),
    (r"finding some resistance on semis", "semis 撞到阻力"),
    (r"a lot of rejection today", "今日好多 rejection"),
    (r"pulling back into the support area", "回測支持區"),
    (r"above 9 and 21", "喺 9 同 21 之上"),
]


def _compile_phrases() -> list[tuple[re.Pattern[str], str]]:
    items = []
    for pat, zh in _PHRASE_RAW:
        # raw patterns accidentally doubled backslashes for \\s — normalize
        pat = pat.replace(r"\\s", r"\s")
        items.append((re.compile(pat, re.I), zh))
    items.sort(key=lambda x: len(x[0].pattern), reverse=True)
    return items


_PHRASES = _compile_phrases()

# Trading glossary — applied to EVERY sentence. Google gtx is banned for this
# domain (short→短片, spy→間諜, shortened→縮短). Unknown words stay English.
_GLOSSARY_RAW: list[tuple[str, str]] = [
    (r"took the (?:exit|exti) short first", "\u6211\u5148\u5e73\u5497\u5462\u624b\u7a7a"),
    (r"took the (?:exit|exti) short", "\u5e73\u5497\u7a7a\u5009"),
    (r"(?:exit|exti) shorts?", "\u5e73\u7a7a"),
    (r"flip(?:ping)? short", "\u8f49\u7a7a"),
    (r"this semis? shorts?", "\u5462\u624b semis \u7a7a\u5009"),
    (r"semis? shorts?", "semis \u7a7a\u5009"),
    (r"on the short side", "\u7a7a\u5009\u5462\u908a"),
    (r"on the long side", "\u591a\u5009\u5462\u908a"),
    (r"precious metal shorts?", "\u8cb4\u91d1\u5c6c \u7a7a\u5009"),
    (r"my shorts", "\u6211\u5e7e\u624b\u7a7a"),
    (r"\bshorting\b", "\u505a\u7a7a"),
    (r"\bshorted it\b", "\u505a\u7a7a\u5497\u4f62"),
    (r"\bshorted\b", "\u505a\u7a7a\u5497"),
    (r"\bshortable\b", "\u53ef\u4ee5\u505a\u7a7a"),
    (r"(?<![A-Za-z-])shorts(?![A-Za-z-])", "\u7a7a\u5009"),
    (r"(?<![A-Za-z-])short(?![A-Za-z-])", "\u7a7a\u5009"),
    (r"(?<![A-Za-z-])longs(?![A-Za-z-])", "\u591a\u5009"),
    (r"(?<![A-Za-z-])long(?![A-Za-z-])(?!\s+(?:upper|wick|time|enough|way|as)\b)", "\u505a\u591a"),
    (r"anchored vwap|anchor(?:ed)? vwap|\bavwap\b|anchored VWAP", "anchored VWAP"),
    (r"swing highs?(?!\uff08)", "swing high\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09"),
    (r"swing lows?(?!\uff08)", "swing low\uff08\u6ce2\u6bb5\u4f4e\u4f4d\uff09"),
    (r"all[\s-]?time highs?", "\u6b77\u53f2\u9ad8\u4f4d"),
    (r"\baths?\b", "\u6b77\u53f2\u9ad8\u4f4d"),
    (r"rally(?:ing)? into", "\u53cd\u5f48\u53bb\u5230"),
    (r"bounce(?:ing)? into", "\u5f48\u53bb\u5230"),
    (r"pulling back into", "\u56de\u6e2c\u53bb\u5230"),
    (r"\bpullbacks?\b", "\u56de\u8abf"),
    (r"\brejections?\b", "reject"),
    (r"getting rejected", "\u88ab reject"),
    (r"stopped me out", "stop \u6211\u51fa\u569f"),
    (r"stopp(?:ed|ing) out", "\u88ab stop \u51fa"),
    (r"gap(?:ping)? down", "gap down"),
    (r"gap(?:ping)? up", "gap up"),
    (r"\bbreakdowns?\b", "\u7834\u4f4d\u5411\u4e0b"),
    (r"\bbreakouts?\b", "\u7834\u4f4d"),
    (r"undercut and rally", "undercut and rally"),
    (r"pin bars?", "pin bar"),
    (r"buying power", "buying power"),
    (r"moving averages?", "\u5747\u7dda"),
    (r"\bhourly\b", "hourly"),
    (r"\bweekly\b", "weekly"),
    (r"\bdaily\b", "daily"),
    (r"relative strength", "\u76f8\u5c0d\u5f37\u52e2"),
    (r"follow through", "\u8ddf\u8e64"),
    (r"\bweakness\b", "\u5f31\u52e2"),
    (r"\bstrength\b", "\u5f37\u52e2"),
]


def _compile_glossary() -> list[tuple[re.Pattern[str], str]]:
    items = [(re.compile(p, re.I), z) for p, z in _GLOSSARY_RAW]
    items.sort(key=lambda x: len(x[0].pattern), reverse=True)
    return items


_GLOSSARY = _compile_glossary()

_WORDS: dict[str, str] = {
    "especially": "\u5c24\u5176",
    "encouraging": "\u9f13\u52f5",
    "closed": "\u6536\u5e02",
    "fairly": "\u5e7e",
    "found": "\u649e\u5230",
    "resistance": "\u963b\u529b",
    "daily": "daily",
    "confident": "\u6709\u4fe1\u5fc3",
    "getting": "",
    "aggressive": "\u9032\u53d6",
    "side": "\u908a",
    "consider": "\u8003\u616e",
    "good": "\u597d",
    "track": "\u8ddf\u8e64",
    "do": "",
    "position": "\u4f4d",
    "tried": "\u8a66",
    "many": "\u591a",
    "them": "\u4f62\u54cb",
    "it's": "\u4f62",
    "core": "CRWV",
    "so": "\u6240\u4ee5",
    "i": "\u6211",
    "i'm": "\u6211",
    "am": "",
    "is": "",
    "are": "",
    "was": "",
    "were": "",
    "be": "",
    "a": "",
    "an": "",
    "the": "",
    "to": "",
    "of": "",
    "for": "\u70ba",
    "from": "\u7531",
    "with": "\u540c",
    "and": "\u540c\u57cb",
    "or": "\u6216\u8005",
    "but": "\u4f46\u4fc2",
    "also": "\u90fd",
    "as": "",
    "at": "\u55ba",
    "on": "\u55ba",
    "in": "\u55ba",
    "into": "\u53bb\u5230",
    "this": "\u5462\u500b",
    "that": "\u55f0\u500b",
    "it": "\u4f62",
    "its": "\u4f62\u5605",
    "they": "\u4f62\u54cb",
    "we": "\u6211\u54cb",
    "you": "\u4f60",
    "my": "\u6211\u5605",
    "today": "\u4eca\u65e5",
    "yesterday": "\u5c0b\u65e5",
    "now": "\u800c\u5bb6",
    "here": "\u5462\u5ea6",
    "there": "",
    "some": "\u4e00\u5572",
    "like": "",
    "yeah": "",
    "yes": "",
    "uh": "",
    "um": "",
    "okay": "",
    "ok": "",
    "mean": "",
    "just": "\u53ea\u4fc2",
    "very": "\u597d",
    "pretty": "\u5e7e",
    "really": "\u771f\u4fc2",
    "still": "\u4ecd\u7136",
    "maybe": "\u6216\u8005",
    "probably": "\u53ef\u80fd",
    "whether": "\u4fc2\u54aa",
    "should": "\u61c9\u8a72",
    "would": "\u6703",
    "will": "\u6703",
    "can": "\u53ef\u4ee5",
    "got": "\u6709",
    "get": "\u6709",
    "have": "\u6709",
    "has": "\u6709",
    "looking": "\u7747\u843d",
    "looks": "\u7747\u843d",
    "look": "\u7747",
    "see": "\u7747",
    "think": "\u89ba\u5f97",
    "say": "\u8b1b",
    "close": "\u6536\u5e02",
    "weak": "\u5f31",
    "weakness": "\u5f31\u52e2",
    "strong": "\u5f37",
    "strength": "\u5f37\u52e2",
    "strengths": "\u5f37\u52e2",
    "stronger": "\u8f03\u5f37",
    "showing": "\u51fa\u73fe",
    "support": "\u652f\u6301",
    "sector": "\u677f\u584a",
    "sectors": "\u677f\u584a",
    "market": "\u5927\u5e02",
    "direction": "\u65b9\u5411",
    "new": "\u65b0",
    "another": "\u53e6\u4e00\u500b",
    "after": "\u4e4b\u5f8c",
    "hours": "\u76e4\u5f8c",
    "earnings": "\u696d\u7e3e",
    "opening": "\u958b\u5e02",
    "bounce": "\u53cd\u5f48",
    "slight": "\u8f15\u5fae",
    "higher": "\u66f4\u9ad8",
    "back": "\u8fd4",
    "downside": "\u5411\u4e0b",
    "stock": "\u5462\u96bb",
    "one": "\u4e00",
    "few": "\u5c11\u6578",
    "times": "\u6b21",
    "early": "\u65e9",
    "too": "\u592a",
    "long": "\u505a\u591a",
    "longs": "\u9577\u5009",
    "short": "\u505a\u7a7a",
    "shorts": "\u77ed\u5009",
    "shorting": "\u505a\u7a7a",
    "shorted": "\u505a\u7a7a\u5497",
    "shortable": "\u53ef\u505a\u7a7a",
    "buy": "\u8cb7",
    "buying": "\u8cb7",
    "dip": "dip",
    "flush": "flush",
    "gap": "gap",
    "down": "down",
    "wait": "\u7b49",
    "better": "\u66f4\u597d",
    "decent": "\u5e7e\u597d",
    "spot": "\u4f4d",
    "compared": "\u6bd4\u8d77",
    "observations": "\u89c0\u5bdf",
    "cyber": "cyber",
    "cypress": "cypress",
    "software": "software",
    "semis": "semis",
    "semi": "semi",
    "quantum": "quantum",
    "crypto": "crypto",
    "names": "\u55f0\u5572",
    "themes": "\u4e3b\u984c",
    "across": "\u55ba",
    "different": "\u5514\u540c",
    "particularly": "\u5c24\u5176",
    "against": "\u76f8\u5c0d",
    "weekly": "weekly",
    "hourly": "hourly",
    "flat": "flat",
    "ema": "EMA",
    "vwap": "VWAP",
    "nvidia": "Nvidia",
    "oops": "\u5443\u5440",
    "stopped": "\u88ab stop \u51fa\u569f",
    "me": "\u6211",
    "out": "",
    "his": "",
    "well": "",
    "gonna": "\u6703",
    "doing": "\u505a\u5f97",
    "together": "\u4e00\u9f4a",
    "same": "\u540c\u4e00",
    "time": "\u6642\u9593",
    "whole": "\u6574\u9ad4",
    "level": "\u4f4d",
    "unfilled": "\u672a\u586b",
    "near": "\u63a5\u8fd1",
    "instead": "\u800c\u5514\u4fc2",
    "morning": "\u65e9\u5e02",
    "not": "\u5514",
    "up": "",
}


def _mostly_zh(text: str) -> bool:
    zh = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    en = len(re.findall(r"[A-Za-z]", text or ""))
    return zh >= 8 and zh > en


def _prep_en(text: str) -> str:
    s = str(text or "").strip()
    s = re.sub(r"\bexti\b", "exit", s, flags=re.I)
    s = re.sub(r"\bshortened it\b", "shorted it", s, flags=re.I)
    s = re.sub(r"\bshortened\b", "shorted", s, flags=re.I)
    s = re.sub(
        r"\b(?:anchor(?:ed)? field(?: web)?|angle field web|anchor field)\b",
        "anchored VWAP",
        s,
        flags=re.I,
    )
    s = re.sub(r"\banchor v\b", "anchored VWAP", s, flags=re.I)
    s = re.sub(
        r"\b(?:angel|angle|ankle)\s+(?:fill|field|view)\s+up\b",
        "anchored VWAP",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\bend(?:\s+of|\s+to)?(?:\s+the)?\s+(?:web|fee\s+web|view\s+up)\b",
        "anchored VWAP",
        s,
        flags=re.I,
    )
    s = re.sub(r"\bend[\s-]+to[\s-]+(?:fee|view)\s+(?:web|up)\b", "anchored VWAP", s, flags=re.I)
    s = re.sub(r"\binterview up\b", "anchored VWAP", s, flags=re.I)
    s = re.sub(r"\bNGV(?:WAP|F)\b", "anchored VWAP", s, flags=re.I)
    s = re.sub(r"\bencovy wap\b|\buncovy wap\b", "anchored VWAP", s, flags=re.I)
    s = re.sub(r"\bankle view\b", "anchored VWAP", s, flags=re.I)
    s = re.sub(r"\bangle view\b", "anchored VWAP", s, flags=re.I)
    s = re.sub(r"\binto the end of VWAP\b", "into the anchored VWAP", s, flags=re.I)

    def _year_mate(m: re.Match[str]) -> str:
        n = m.group(1)
        if "." in n:
            a, b = n.split(".", 1)
            return f"{a}, {b} EMA"
        return f"{n} EMA"

    s = re.sub(r"\b(\d+(?:\.\d+)?)\s+year mates?\b", _year_mate, s, flags=re.I)
    s = re.sub(r"\b9gma\b", "9 EMA", s, flags=re.I)
    s = re.sub(r"\bopening range height\b", "opening range high", s, flags=re.I)
    s = re.sub(r"\b(silver|quantum|semis?)\s+shots?\b", r"\1 short", s, flags=re.I)
    s = re.sub(r"\bclose(?:ing)? the ([A-Z]{2,5})\b", r"cover \1", s)
    s = re.sub(r"\b16-minute candle\b", "60-minute candle", s, flags=re.I)
    s = re.sub(r"\bthen field gap\b", "unfilled gap", s, flags=re.I)
    s = re.sub(r"\b21nm\b", "21 EMA", s, flags=re.I)
    s = re.sub(r"\bcofee web\b|\bcoffee web\b", "CRWV", s, flags=re.I)
    s = re.sub(r"\bcybernims\b", "cyber names", s, flags=re.I)
    s = re.sub(r"\bqc\b", "Qs", s, flags=re.I)
    s = re.sub(r"\b(?:uh+|um+|yeah|you know)\b", " ", s, flags=re.I)
    s = re.sub(r"\bthe the\b", "the", s, flags=re.I)
    s = re.sub(r"\bfrom from(?: the)? from\b", "from", s, flags=re.I)
    s = re.sub(r"\bto to\b", "to", s, flags=re.I)
    s = re.sub(r"\bnear near\b", "near", s, flags=re.I)
    s = re.sub(r"\binto the into the\b", "into the", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" .,;:")


_ZH_CACHE: dict[str, str] = {}


def seed_zh_cache_from_markdown(md: str) -> int:
    """Reuse already-translated timeline lines so rebuilds don't hammer Google."""
    n = 0
    for line in (md or "").splitlines():
        if " ‖ " not in line:
            continue
        tail = line.rsplit("|", 1)[-1]
        if " ‖ " not in tail:
            continue
        en, zh = tail.split(" ‖ ", 1)
        en = en.strip()
        zh = zh.strip()
        if not en or not re.search(r"[\u4e00-\u9fff]", zh or ""):
            continue
        key = re.sub(r"\s+", " ", en).lower()
        if key not in _ZH_CACHE:
            _ZH_CACHE[key] = zh
            n += 1
    return n

# Lock trading jargon FIRST so Google cannot turn short→短片 / shorts→短褲.
# Tickers after that: spy≠間諜, semi≠半決賽, quantum≠量子.
_LOCKS: list[tuple[str, str]] = [
    (r"took the (?:exit|exti) short first", "ZZTOOKEXITZZ"),
    (r"(?:exit|exti)\s+short", "ZZEXITSHORTZZ"),
    (r"flip(?:ping)?\s+short", "ZZFLIPSHORTZZ"),
    (r"this\s+semis?\s+shorts?", "ZZTHISSEMISHORTZZ"),
    (r"semis?\s+shorts?", "ZZSEMISHORTZZ"),
    (r"anchored\s+VWAPs?", "ZZAVWAPZZ"),
    (r"anchor(?:ed)?\s+VWAPs?", "ZZAVWAPZZ"),
    (r"\bAVWAP\b", "ZZAVWAPZZ"),
    (r"\banchor(?:ed)?\s+V\b", "ZZAVWAPZZ"),
    (r"swing\s+highs?", "ZZSWINGHIZZ"),
    (r"swing\s+lows?", "ZZSWINGLOZZ"),
    (r"all[\s-]?time\s+highs?", "ZZATHZZ"),
    (r"\bATHs?\b", "ZZATHZZ"),
    (r"rally(?:ing)?\s+into", "ZZRALLYINZZ"),
    (r"take\s+profits?", "ZZTRIMZZ"),
    (r"\btrimm?(?:ing|ed|s)?\b", "ZZTRIMZZ"),
    (r"\bshorting\b", "ZZSHORTINGZZ"),
    (r"\bshorted\b", "ZZSHORTEDZZ"),
    (r"\bshortable\b", "ZZSHORTABLEZZ"),
    (r"(?<![A-Za-z-])shorts(?![A-Za-z-])", "ZZSHORTSPOSZZ"),
    (r"(?<![A-Za-z-])short(?![A-Za-z-])", "ZZSHORTZZ"),
    (r"(?<![A-Za-z-])longs(?![A-Za-z-])", "ZZLONGSPOSZZ"),
    (
        r"(?<![A-Za-z-])long(?![A-Za-z-])(?!\s+(?:upper|wick|time|enough|way|as)\b)",
        "ZZLONGZZ",
    ),
    (r"SpaceX \(SPCX\)", "ZZSPCXZZ"),
    (r"\bSPCX\b", "ZZSPCXZZ"),
    (r"\bQQQ\b|\bQs\b|\bcues?\b", "ZZQQQZZ"),
    (r"\bSPY\b|\bspy\b", "ZZSPYZZ"),
    (r"\bIWM\b", "ZZIWMZZ"),
    (r"\bsemis?\b", "ZZSEMISZZ"),
    (r"\bquantum'?s?\b", "ZZQUANTUMZZ"),
    (r"\bsoftwares?\b", "ZZSOFTZZ"),
    (r"\bmemories\b", "ZZMEMZZ"),
    (r"\bmemory\b", "ZZMEMZZ"),
    (r"\bEMA\b", "ZZEMAZZ"),
    (r"\bVWAP\b", "ZZVWAPZZ"),
    (r"\bNVDA\b|\bNvidia\b", "ZZNVDAZZ"),
    (r"\bTSLA\b|\bTesla\b", "ZZTSLAZZ"),
    (r"\bPATH\b", "ZZPATHZZ"),
    (r"\bSNDK\b", "ZZSNDKZZ"),
    (r"\bCRCL\b", "ZZCRCLZZ"),
    (r"\bASTS\b", "ZZASTSZZ"),
    (r"\bMU\b", "ZZMUZZ"),
    (r"\bIGV\b", "ZZIGVZZ"),
    (r"\bONDS\b", "ZZONDSZZ"),
    (r"\bCRWV\b", "ZZCRWVZZ"),
    (r"\bSMCI\b", "ZZSMCIZZ"),
    (r"\bAXTI\b", "ZZAXTIZZ"),
    (r"\bARM\b", "ZZARMZZ"),
    (r"Western Digital", "ZZWDCZZ"),
    (r"\bWDC\b", "ZZWDCZZ"),
    (r"\bFIG\b", "ZZFIGZZ"),
]


def _lock_en(en: str) -> str:
    s = en
    for pat, tok in _LOCKS:
        s = re.sub(pat, tok, s, flags=re.I)
    return s


_UNLOCK = {
    "ZZTOOKEXITZZ": "\u6211\u5148\u5e73\u5497\u5462\u624b\u7a7a",
    "ZZEXITSHORTZZ": "\u5e73\u5497\u7a7a\u5009",
    "ZZFLIPSHORTZZ": "\u8f49\u7a7a",
    "ZZTHISSEMISHORTZZ": "\u5462\u624b semis \u7a7a\u5009",
    "ZZSEMISHORTZZ": "semis \u7a7a\u5009",
    "ZZAVWAPZZ": "anchored VWAP",
    "ZZSWINGHIZZ": "swing high\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09",
    "ZZSWINGLOZZ": "swing low\uff08\u6ce2\u6bb5\u4f4e\u4f4d\uff09",
    "ZZATHZZ": "\u6b77\u53f2\u9ad8\u4f4d",
    "ZZRALLYINZZ": "\u53cd\u5f48\u53bb\u5230",
    "ZZTRIMZZ": "\u6e1b\u5009",
    "ZZSHORTINGZZ": "\u505a\u7a7a",
    "ZZSHORTEDZZ": "\u505a\u7a7a\u5497",
    "ZZSHORTABLEZZ": "\u53ef\u505a\u7a7a",
    "ZZSHORTSPOSZZ": "\u77ed\u5009",
    "ZZSHORTZZ": "\u7a7a\u5009",
    "ZZLONGSPOSZZ": "\u9577\u5009",
    "ZZLONGZZ": "\u505a\u591a",
    "ZZSPCXZZ": "SPCX",
    "ZZQQQZZ": "QQQ",
    "ZZSPYZZ": "SPY",
    "ZZIWMZZ": "IWM",
    "ZZSEMISZZ": "semis",
    "ZZQUANTUMZZ": "quantum",
    "ZZSOFTZZ": "software",
    "ZZMEMZZ": "memory",
    "ZZEMAZZ": "EMA",
    "ZZVWAPZZ": "VWAP",
    "ZZNVDAZZ": "NVDA",
    "ZZTSLAZZ": "Tesla",
    "ZZPATHZZ": "PATH",
    "ZZSNDKZZ": "SNDK",
    "ZZCRCLZZ": "CRCL",
    "ZZASTSZZ": "ASTS",
    "ZZMUZZ": "MU",
    "ZZIGVZZ": "IGV",
    "ZZONDSZZ": "ONDS",
    "ZZCRWVZZ": "CRWV",
    "ZZSMCIZZ": "SMCI",
    "ZZAXTIZZ": "AXTI",
    "ZZARMZZ": "ARM",
    "ZZWDCZZ": "WDC",
    "ZZFIGZZ": "FIG",
}


def _unlock_zh(zh: str) -> str:
    s = zh or ""
    for tok, word in sorted(_UNLOCK.items(), key=lambda x: -len(x[0])):
        s = re.sub(re.escape(tok), word, s, flags=re.I)
    return s


def _sanitize_zh(zh: str) -> str:
    """Last-resort: Google still sometimes says 短片/短褲 even near locked tokens."""
    s = zh or ""
    s = s.replace("\u77ed\u7247", "\u7a7a\u5009")
    s = s.replace("\u7e2e\u77ed\u4e86\u5b83", "\u505a\u7a7a\u5497\u4f62")
    s = s.replace("\u7e2e\u77ed\u4e86", "\u505a\u7a7a\u5497")
    s = s.replace("\u7e2e\u77ed", "\u505a\u7a7a")
    s = s.replace("\u77ed\u8932", "\u77ed\u5009")
    s = re.sub(r"\u62cd\u4e86\s*", "", s)
    s = re.sub(r"\u62cd\u651d\s*", "", s)
    s = s.replace("\u9328\u5b9aV", "anchored VWAP")
    s = s.replace("\u9328\u5b9a V", "anchored VWAP")
    s = s.replace("\u9418\u5b9aV", "anchored VWAP")
    s = s.replace("\u9418\u5b9a V", "anchored VWAP")
    s = s.replace("\u64fa\u52d5\u9ad8\u9ede", "swing high\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09")
    s = s.replace("\u6ce2\u52d5\u9ad8\u9ede", "swing high\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09")
    s = s.replace("\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09", "\uff08\u6ce2\u6bb5\u9ad8\u4f4d\uff09")
    s = s.replace("\u9593\u8adc", "SPY")
    s = s.replace("\u95dc\u8adc", "SPY")
    s = s.replace("\u534a\u6e96\u6c7a\u8cfd", "semis")
    s = s.replace("\u534a\u6c7a\u8cfd", "semis")
    s = re.sub(
        r"\u95dc\u9589\s*(AXTI|ARM|SPCX|FIG|WDC|SNDK|ASTS)",
        lambda m: "\u5e73\u6389 " + m.group(1),
        s,
    )
    s = re.sub(
        r"\u5173\u95ed\s*(AXTI|ARM|SPCX|FIG|WDC|SNDK|ASTS)",
        lambda m: "\u5e73\u6389 " + m.group(1),
        s,
    )
    s = s.replace("\u689d\u76ee", "\u5165\u5834")
    s = s.replace("\u5047\u5192", "\u5047\u7a81\u7834")
    s = s.replace("\u5de8\u5927\u7684\u524a\u6e1b", "\u5927 cut")
    s = s.replace("\u5fae\u5c0f\u7684\u524a\u6e1b", "\u5c0f cut")
    return s


def _http_zh(en: str) -> str | None:
    """Google gtx zh-TW — used only at digest build time, not on Streamlit Cloud."""
    en = (en or "").strip()
    if len(en) < 8:
        return None
    try:
        import json
        import urllib.parse
        import urllib.request

        qs = urllib.parse.urlencode(
            {"client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": en[:480]}
        )
        req = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single?" + qs,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = [x[0] for x in (data[0] or []) if x and x[0]]
        out = "".join(parts).strip()
        return out or None
    except Exception:
        return None


def translate_speech_zh(text: str) -> str:
    """Chinese of spoken English. Lock trading jargon, then translate leftover English."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if _mostly_zh(raw):
        return _sanitize_zh(raw)
    key = re.sub(r"\s+", " ", raw).lower()
    if key in _ZH_CACHE:
        return _ZH_CACHE[key]
    s = _prep_en(raw)
    for pat, zh in _PHRASES:
        s = pat.sub(lambda m, z=zh: m.expand(z) if re.search(r"\\\d", z) else z, s)
    zh_n = len(re.findall(r"[\u4e00-\u9fff]", s))
    en_words = len(re.findall(r"\b[A-Za-z]{3,}\b", s))
    if (zh_n >= 6 and en_words <= 4) or (zh_n >= 12 and zh_n >= en_words * 2):
        out = _sanitize_zh(re.sub(r"\s+", " ", s).strip(" ,"))
        _ZH_CACHE[key] = out
        return out

    def _ok(zh: str) -> bool:
        return len(re.findall(r"[\u4e00-\u9fff]", zh or "")) >= 6

    locked = _lock_en(s)
    got = _http_zh(locked)
    if got:
        out = _sanitize_zh(_unlock_zh(got))
        if _ok(out):
            _ZH_CACHE[key] = out
            return out
    got = _http_zh(s)
    if got:
        out = _sanitize_zh(got)
        if _ok(out):
            _ZH_CACHE[key] = out
            return out
    for pat, zh in _GLOSSARY:
        s = pat.sub(zh, s)
    out = _sanitize_zh(re.sub(r"\s+", " ", s).strip(" ,"))
    _ZH_CACHE[key] = out
    return out
