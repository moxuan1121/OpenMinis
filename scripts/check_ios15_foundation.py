"""Run the actual iOS 15 Foundation matchers against boundary cases (requires Swift)."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
env = (root / "src/ios/Shared/EnvVarStore.swift").read_text()
matcher = re.search(r"static let keyRegex = .*?\n.*?static func isValidKey.*?\n    }", env, re.S).group()
markdown = (root / "src/ios/Views/Chat/MarkdownPrepRegex.swift").read_text()
image = re.search(r"static let image = .*", markdown).group().removeprefix("static ")
source = '''import Foundation
enum Keys {
''' + matcher + '''
}
for key in ["A", "API_KEY", "a1", "Z_9"] { precondition(Keys.isValidKey(key), key) }
for key in ["", "_A", "1A", "A-B", "A B", "é", "中文", "A\\n", "A\\r\\n", "A\\0"] {
    precondition(!Keys.isValidKey(key), "Invalid key accepted: \\(key.debugDescription)")
}
''' + image + '''
let text = "😀中文 ![图片](minis://image.png) and ![](https://example.com/a.jpg)"
let matches = image.matches(in: text, range: NSRange(text.startIndex..., in: text))
    .compactMap { Range($0.range, in: text) }.map { String(text[$0]) }
precondition(matches == ["![图片](minis://image.png)", "![](https://example.com/a.jpg)"])
precondition(image.numberOfMatches(in: "![unfinished", range: NSRange(location: 0, length: 12)) == 0)
print("iOS 15 Foundation boundary checks passed")
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "check.swift"
    path.write_text(source)
    subprocess.run(["swift", str(path)], check=True)
