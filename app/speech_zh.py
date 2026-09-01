"""Faithful Chinese translation of spoken English ASR excerpts."""
from __future__ import annotations

import re


# Longest-first. Only render meaning that is in the English.
# Chinese is written as \\u escapes so the source stays ASCII-safe.
_PHRASE_RAW: list[tuple[str, str]] = [
    (r"and the qes and spy are also closing weak", "QQQ 同 SPY 都收市偏弱"),
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
    (r"i am considering(?: like)? to flipping short on", "\u6211\u800c\u5bb6\u8003\u616e\u8f49\u77ed"),
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
    (r"i am considering(?: like)? to flipping short on", "\u6211\u800c\u5bb6\u8003\u616e\u8f49\u77ed"),
    (r"considering(?: like)? to flipping short", "\u8003\u616e\u8f49\u77ed"),
    (r"flipping short", "\u8f49\u77ed"),
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
    "long": "long",
    "longs": "long",
    "short": "\u77ed",
    "shortable": "shortable",
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
    s = re.sub(r"\bthen field gap\b", "unfilled gap", s, flags=re.I)
    s = re.sub(r"\b21nm\b", "21 EMA", s, flags=re.I)
    s = re.sub(r"\bcofee web\b|\bcoffee web\b", "CRWV", s, flags=re.I)
    s = re.sub(r"\bcybernims\b", "cyber names", s, flags=re.I)
    s = re.sub(r"\bqc\b", "Qs", s, flags=re.I)
    s = re.sub(r"\bthe the\b", "the", s, flags=re.I)
    s = re.sub(r"\bfrom from(?: the)? from\b", "from", s, flags=re.I)
    s = re.sub(r"\bto to\b", "to", s, flags=re.I)
    s = re.sub(r"\bnear near\b", "near", s, flags=re.I)
    s = re.sub(r"\binto the into the\b", "into the", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" .,;:")


def translate_speech_zh(text: str) -> str:
    """Phrase-level Cantonese. Leftover English stays English — no word salad."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if _mostly_zh(raw):
        return raw
    s = _prep_en(raw)
    for pat, zh in _PHRASES:
        s = pat.sub(lambda m, z=zh: m.expand(z) if re.search(r"\\\d", z) else z, s)
    s = re.sub(r"\b(?:uh+|um+|yeah|you know)\b", " ", s, flags=re.I)
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    s = re.sub(r"(?:SpaceX \(SPCX\)\s*){2,}", "SpaceX (SPCX) ", s)
    if s and not re.search(r"[\u4e00-\u9fff]", s):
        return s
    return s
