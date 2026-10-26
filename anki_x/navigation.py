"""Deck-tree navigation and profile-scoped screen bookmarks."""

import copy
import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class DeckNode:
    key: str
    name: str
    deck_id: str = None
    parent: str = None
    children: list = field(default_factory=list)

    @property
    def label(self):
        return self.name.rsplit("::", 1)[-1]


class DeckTree:
    def __init__(self, decks, selected=None, expanded=None, preferred=None):
        actual = {deck["name"]: deck for deck in decks}
        names = set()
        for name in actual:
            parts = name.split("::")
            names.update("::".join(parts[:i]) for i in range(1, len(parts) + 1))
        self.nodes, self.by_name, self.roots = {}, {}, []
        for name in sorted(names, key=str.casefold):
            deck_id = str(actual[name]["id"]) if name in actual else None
            key = deck_id or "path:" + name
            node = DeckNode(key, name, deck_id)
            self.nodes[key] = node
            self.by_name[name] = node
        for node in self.nodes.values():
            if "::" in node.name:
                parent = self.by_name[node.name.rsplit("::", 1)[0]]
                node.parent = parent.key
                parent.children.append(node.key)
            else:
                self.roots.append(node.key)
        expanded = expanded if isinstance(expanded, list) else []
        self.expanded = {key for key in expanded if isinstance(key, str) and key in self.nodes and self.nodes[key].children}
        self.selected = selected if isinstance(selected, str) and selected in self.nodes else None
        if self.selected is None:
            node = self.by_name.get(preferred)
            if node:
                while node.parent:
                    node = self.nodes[node.parent]
                self.selected = node.key
            elif self.roots:
                self.selected = self.roots[0]
        else:
            self._reveal_selection()

    @property
    def current(self):
        return self.nodes.get(self.selected)

    def _reveal_selection(self):
        node = self.current
        while node and node.parent:
            self.expanded.add(node.parent)
            node = self.nodes[node.parent]

    def rows(self):
        result = []

        def visit(key, depth):
            node = self.nodes[key]
            result.append((node, depth))
            if key in self.expanded:
                for child in node.children:
                    visit(child, depth + 1)

        for root in self.roots:
            visit(root, 0)
        return result

    def move(self, delta):
        rows = self.rows()
        if rows:
            index = next((i for i, (node, _) in enumerate(rows) if node.key == self.selected), 0)
            self.selected = rows[max(0, min(index + delta, len(rows) - 1))][0].key

    def right(self):
        node = self.current
        if node and node.children:
            if node.key not in self.expanded:
                self.expanded.add(node.key)
            else:
                self.selected = node.children[0]

    def left(self):
        node = self.current
        if node:
            if node.key in self.expanded:
                self.expanded.remove(node.key)
            elif node.parent:
                self.selected = node.parent

    def toggle(self):
        node = self.current
        if node and node.children:
            if node.key in self.expanded:
                self.expanded.remove(node.key)
            else:
                self.expanded.add(node.key)

    def select(self, key):
        if key in self.nodes:
            self.selected = key
            self._reveal_selection()

    def snapshot(self):
        return {"selected": self.selected, "expanded": sorted(self.expanded)}


class NavigationStore:
    def __init__(self, path, endpoint, profile):
        self.path = path
        self.scope = hashlib.sha256((endpoint + "\0" + profile).encode()).hexdigest()

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {"version": 1, "profiles": {}}
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("profiles"), dict):
            return {"version": 1, "profiles": {}}
        return data

    def load(self):
        value = self._read()["profiles"].get(self.scope, {})
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def save(self, state):
        data = self._read()
        data["profiles"][self.scope] = state
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def start_location(tree, saved, explicit_deck=None, force_home=False):
    if force_home:
        return "home", None
    if explicit_deck is not None:
        node = tree.by_name.get(explicit_deck)
        return ("review", node) if node and node.deck_id else ("home", None)
    bookmark = saved.get("review")
    if saved.get("view") == "review" and isinstance(bookmark, dict):
        deck_id = bookmark.get("deck_id")
        node = tree.nodes.get(deck_id) if isinstance(deck_id, str) else None
        if node and node.deck_id:
            return "review", node
    return "home", None
