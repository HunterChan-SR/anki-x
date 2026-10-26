"""Readable vocabulary fields and a conservative HTML-to-terminal fallback."""

import re
import unicodedata
from html.parser import HTMLParser


def clean(text):
    return "".join(c for c in text if c in "\n\t" or unicodedata.category(c) not in ("Cc", "Cf", "Cs"))


class TextParser(HTMLParser):
    BREAKS = {"p", "div", "li", "tr", "h1", "h2", "h3", "section", "blockquote", "ul", "ol", "table"}
    VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr", "embed", "area", "base", "col", "param", "track"}

    def __init__(self, css=""):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.hidden_selectors = set()
        for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", declarations, re.I):
                self.hidden_selectors.update(s.strip() for s in selectors.split(",") if re.fullmatch(r"[.#]?[\w-]+", s.strip()))

    @property
    def hidden(self):
        return any(item[1] for item in self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        selectors = {tag, "#" + attrs.get("id", "")}
        selectors.update("." + c for c in attrs.get("class", "").split())
        hide = (tag in {"script", "style", "head", "noscript", "button"}
                or "hidden" in attrs or bool(selectors & self.hidden_selectors)
                or bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", attrs.get("style", ""), re.I)))
        if not self.hidden and not hide:
            if tag in self.BREAKS or tag in {"br", "hr"}:
                self.parts.append("\n")
            elif tag == "img":
                self.parts.append(" [图片" + ("：" + attrs["alt"] if attrs.get("alt") else "") + "] ")
        if tag not in self.VOID:
            self.stack.append((tag, hide))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        was_hidden = self.hidden
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if tag in self.BREAKS and not was_hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def text_from_html(value, css=""):
    parser = TextParser(css)
    parser.feed(re.sub(r"\[sound:[^\]]*\]", "", value or ""))
    text = clean("".join(parser.parts)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


WORD_FIELDS = {"word", "expression", "单词", "词汇", "英文单词", "英语单词", "英文"}
PHONETIC_FIELDS = {"phonetic", "phonetics", "ipa", "pronunciation", "音标", "英音", "美音", "英美音标", "英式音标", "美式音标"}


def card_text(state, note, layout="auto"):
    """Use explicit vocabulary fields only for a forward vocabulary card."""
    fields = (note or {}).get("fields", {})
    word_key = next((k for k in fields if k.lower() in WORD_FIELDS), None)
    vocabulary = layout != "template" and word_key and state["card"]["templateIndex"] == 0
    if vocabulary:
        word = text_from_html(fields[word_key])
        phonetics = [text_from_html(v) for k, v in fields.items() if k.lower() in PHONETIC_FIELDS]
        front = "\n\n".join([word] + [p for p in phonetics if p])
        if state["side"] == "question":
            return front
        if layout == "details" and fields.get("Back"):
            return front + "\n\n" + text_from_html(fields["Back"])
        if fields.get("中文释义"):
            parts = [front, "释义\n" + text_from_html(fields["中文释义"])]
            english = [v for v in text_from_html(fields.get("英语例句", "")).splitlines() if v]
            chinese = [v for v in text_from_html(fields.get("中文例句", "")).splitlines() if v]
            examples = []
            for i, sentence in enumerate(english):
                examples.append(sentence)
                if i < len(chinese):
                    examples.append(chinese[i])
                examples.append("")
            if examples:
                parts.append("例句\n" + "\n".join(examples).strip())
            if fields.get("笔记"):
                parts.append("笔记\n" + text_from_html(fields["笔记"]))
            return "\n\n".join(parts)
        parts = [front]
        for key, value in fields.items():
            if key == word_key or key.lower() in PHONETIC_FIELDS or key.lower() in {"front", "id", "guid", "sort", "排序", "序号"}:
                continue
            text = text_from_html(value)
            if text:
                parts.append(key + "\n" + text)
        return "\n\n".join(parts)
    rendered = state.get("rendered") or {}
    side = "questionHtml" if state.get("side") == "question" else "answerHtml"
    return text_from_html(rendered.get(side, ""), rendered.get("css", ""))


def width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def clip(text, columns):
    result = ""
    for char in clean(text):
        if width(result + char) > columns:
            break
        result += char
    return result


def wrap(text, columns):
    columns = max(columns, 4)
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        while width(paragraph) > columns:
            part = clip(paragraph, columns)
            split = part.rfind(" ")
            if split > len(part) // 2:
                part = part[:split]
            lines.append(part)
            paragraph = paragraph[len(part):].lstrip()
        lines.append(paragraph)
    return lines
