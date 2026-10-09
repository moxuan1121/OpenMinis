"""Guard the iOS 15 session-row entry point; device testing still covers gestures."""
from pathlib import Path
import re

source = (Path(__file__).resolve().parents[1] / "src/ios/Views/ContentView.swift").read_text(encoding="utf-8")
row = source.split("private func erasedSessionRow(", 1)[1].split("private func erasedFolderSectionHeader(", 1)[0]
modern, legacy = row.split("if #available(iOS 16.0, *)", 1)[1].split("} else {", 1)
assert "NavigationLink(value: session.id)" in modern
assert "NavigationLink(value:" not in legacy, "iOS 15 cannot use value-based navigation"
assert ".contentShape(Rectangle())" in legacy, "The entire session row must accept taps"
for action in ("onTapGesture", "accessibilityAction"):
    assert re.search(r"\." + action + r"\s*\{\s*openSession\(session.id\)\s*\}", legacy), action
assert ".accessibilityAddTraits(.isButton)" in legacy
assert "return AnyView(navigableRow" in legacy and ".listRowInsets" in legacy, "Render the interactive row"
assert ".swipeActions(edge: .trailing, allowsFullSwipe: false)" in legacy
assert "SessionDeleteButton(sessionId: session.id, actions: menuActions, role: nil).tint(.red)" in legacy
assert "actions.send(.delete(sessionId))" in source, "Swipe deletion must use the existing confirmation flow"
print("iOS 15 session-row navigation source checks passed")
