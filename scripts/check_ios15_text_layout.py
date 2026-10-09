"""Exercise the actual legacy intrinsic-size override in UIKit on a simulator.

Requires Xcode. Forces only the OS availability branch so newer simulators can
check the iOS 15 sizing logic; this does not replace iOS 15 device testing.
"""
from pathlib import Path
import atexit
import json
import plistlib
import re
import subprocess
import tempfile
import time


def run(*args):
    return subprocess.check_output(args, text=True).strip()


root = Path(__file__).resolve().parents[1]
source = (root / "src/ios/Views/Chat/SelectableMarkdownView.swift").read_text(encoding="utf-8")
text_view = source.split("final class SelectableMarkdownTextView:", 1)[1]
sizing = re.search(r"    override var intrinsicContentSize: CGSize \{.*?\n    \}", text_view, re.S).group()
sizing = sizing.replace("if #available(iOS 16.0, *)", "if false")
compatibility = (root / "src/ios/Shared/IOS15Compatibility.swift").read_text(encoding="utf-8")
hosting = compatibility.split("private struct LegacyHostingConfiguration:", 1)[1].split("private struct LegacyPhotosPicker:", 1)[0]
hosting = "private struct LegacyHostingConfiguration:" + hosting
# Log UIKit's actual containment chain without changing the bridge's behavior.
hosting = hosting.replace("var cell: SelfSizingCell?", "var chain: [String] = []; var cell: SelfSizingCell?")
hosting = hosting.replace("while let view = ancestor {", "while let view = ancestor { chain.append(String(describing: type(of: view)))")
hosting = hosting.replace("if let collection = view as? UICollectionView {", "if let collection = view as? UICollectionView { NSLog(\"Bridge index: %@\", String(describing: cell.flatMap { collection.indexPath(for: $0) }))")
hosting = hosting.replace("ancestor = view.superview\n            }", "ancestor = view.superview\n            }; if probeLogs < 20 { NSLog(\"Bridge chain: %@\", chain.joined(separator: \" > \")); probeLogs += 1 }")
layout = (root / "src/ios/Agent/MessageList/MessageListLayout.swift").read_text(encoding="utf-8")
# The app's layout and hosting bridge run unchanged. Only unrelated logging,
# snapshot identities and the cell's cache interface are replaced in this probe.
swift = '''import UIKit
import SwiftUI
var probeLogs = 0
struct AppLogger {
    init(category: String) {}
    func info(_ message: String) {}
    func debug(_ message: String) {}
}
enum MessageListItem: Hashable { case item(Int) }
final class SelfSizingCell: UICollectionViewCell {
    var contentKey: String?
    func clearCachedHeight() {}
    static func renderQualifiedKey(_ key: String, for cell: UIView) -> String { key }
}
''' + layout + hosting + '''
final class ProbeTextView: UITextView {
''' + sizing + '''
}
@main final class AppDelegate: UIResponder, UIApplicationDelegate, UICollectionViewDataSource {
    var window: UIWindow?
    var collection: UICollectionView!
    let listLayout = MessageListLayout()
    var rows = ["Minis", "回复正文应该完整显示，并让下一条消息排列在下方。", "下一条消息"]
    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int { rows.count }
    func configure(_ cell: SelfSizingCell, at index: Int) {
        cell.contentKey = "b:row\\(index)"
        cell.contentConfiguration = LegacyHostingConfiguration(content: AnyView(
            Text(rows[index]).font(.system(size: 16.5))
                .frame(maxWidth: .infinity, alignment: .leading).padding(16)
        ))
    }
    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "row", for: indexPath) as! SelfSizingCell
        configure(cell, at: indexPath.item)
        return cell
    }
    func verifyList() -> CGFloat {
        collection.layoutIfNeeded()
        let path = IndexPath(item: 1, section: 0)
        let cell = collection.cellForItem(at: path)!
        let hosted = (cell.contentView as? LegacyHostingContentView)
            ?? cell.contentView.subviews.compactMap { $0 as? LegacyHostingContentView }.first!
        let height = hosted.intrinsicContentSize.height
        NSLog("Layout probe: hosted=%f cached=%f", height, listLayout.cachedHeight(at: 1) ?? -1)
        precondition(height > 0)
        precondition(abs(listLayout.cachedHeight(at: 1)! - height) < 1, "Hosted row grew but the list retained its old height")
        var bottom: CGFloat = 0
        for index in rows.indices {
            let attributes = listLayout.layoutAttributesForItem(at: IndexPath(item: index, section: 0))!
            precondition(attributes.frame.minY >= bottom, "Adjacent messages overlap")
            bottom = attributes.frame.maxY
        }
        return height
    }
    func application(_ app: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.rootViewController = UIViewController()
        window?.makeKeyAndVisible()
        let storage = NSTextStorage()
        let manager = NSLayoutManager()
        let container = NSTextContainer()
        container.lineFragmentPadding = 0
        container.widthTracksTextView = true
        container.lineBreakMode = .byWordWrapping
        manager.addTextContainer(container)
        storage.addLayoutManager(manager)
        let view = ProbeTextView(frame: .zero, textContainer: container)
        view.isScrollEnabled = false
        view.textContainerInset = UIEdgeInsets(top: 4, left: 0, bottom: 4, right: 0)
        precondition(view.intrinsicContentSize.width == UIView.noIntrinsicMetric)
        let paragraph = String(repeating: "已安装 ponytail 主技能。之后可以直接说用 ponytail 处理这个项目，回复应该在屏幕内自动换行。", count: 8)
        func height(_ width: CGFloat, _ text: String, _ fontSize: CGFloat = 16.5) -> CGFloat {
            view.bounds = CGRect(x: 0, y: 0, width: width, height: 30)
            view.attributedText = NSAttributedString(string: text, attributes: [.font: UIFont.systemFont(ofSize: fontSize)])
            let size = view.intrinsicContentSize
            precondition(size.width == UIView.noIntrinsicMetric)
            precondition(size.height.isFinite && size.height >= 8)
            let used = manager.usedRect(for: container)
            precondition(used.width <= width + 0.5, "Text extends beyond the available width")
            precondition(size.height >= ceil(used.height) + 8, "Trailing lines are clipped")
            return size.height
        }
        let compact = height(288, paragraph)
        precondition(compact > 100, "Long Chinese reply remained a single line")
        precondition(height(568, paragraph) < compact, "Width changes did not reflow text")
        precondition(height(288, paragraph + paragraph) > compact, "Appended tokens did not grow the reply")
        precondition(height(288, paragraph, 26) > compact, "Font scaling clipped the reply")
        _ = height(288, "")
        collection = UICollectionView(frame: CGRect(x: 0, y: 80, width: 320, height: 700), collectionViewLayout: listLayout)
        collection.register(SelfSizingCell.self, forCellWithReuseIdentifier: "row")
        collection.dataSource = self
        for index in rows.indices { listLayout.setCachedHeight(24, at: index) }
        window!.rootViewController!.view.addSubview(collection)
        collection.reloadData()
        collection.layoutIfNeeded()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            let initial = self.verifyList()
            self.rows[1] = String(repeating: "长回复继续追加，聊天列表必须更新消息高度，避免正文与后续消息重叠。", count: 8)
            self.configure(self.collection.cellForItem(at: IndexPath(item: 1, section: 0)) as! SelfSizingCell, at: 1)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                let grown = self.verifyList()
                precondition(grown > initial + 100, "Streaming growth was not committed to the list")
                self.rows[1] = "收起后的短消息"
                self.configure(self.collection.cellForItem(at: IndexPath(item: 1, section: 0)) as! SelfSizingCell, at: 1)
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                    precondition(self.verifyList() < grown, "Collapsed content retained a stale height")
                    let result = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("result.txt")
                    try! "PASS: legacy UIKit text sizing and hosted message-list growth/collapse without overlap".write(to: result, atomically: true, encoding: .utf8)
                }
            }
        }
        return true
    }
}
'''
devices = json.loads(run("xcrun", "simctl", "list", "devices", "available", "--json"))["devices"]
candidate = next(d for group in devices.values() for d in group if "iPhone" in d["name"])
device = candidate["udid"]
if candidate["state"] != "Booted":
    atexit.register(lambda: subprocess.run(["xcrun", "simctl", "shutdown", device], check=False))
subprocess.run(["xcrun", "simctl", "boot", device], check=False)
run("xcrun", "simctl", "bootstatus", device, "-b")
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    app = folder / "LayoutProbe.app"
    app.mkdir()
    (folder / "probe.swift").write_text(swift, encoding="utf-8")
    (app / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "com.openminis.layoutprobe", "CFBundleExecutable": "LayoutProbe",
        "CFBundlePackageType": "APPL", "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0",
        "MinimumOSVersion": "15.6", "UIDeviceFamily": [1],
    }))
    sdk = run("xcrun", "--sdk", "iphonesimulator", "--show-sdk-path")
    run("xcrun", "swiftc", "-parse-as-library", "-sdk", sdk, "-target", "arm64-apple-ios15.6-simulator",
        "-framework", "UIKit", str(folder / "probe.swift"), "-o", str(app / "LayoutProbe"))
    run("codesign", "--force", "--sign", "-", str(app))
    subprocess.run(["xcrun", "simctl", "uninstall", device, "com.openminis.layoutprobe"], check=False)
    run("xcrun", "simctl", "install", device, str(app))
    data = Path(run("xcrun", "simctl", "get_app_container", device, "com.openminis.layoutprobe", "data"))
    report = data / "Documents/result.txt"
    console = folder / "console.log"
    with console.open("w") as output:
        process = subprocess.Popen(["xcrun", "simctl", "launch", "--console", device,
                                    "com.openminis.layoutprobe"], stdout=output, stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                if report.exists():
                    print(report.read_text(encoding="utf-8"))
                    break
                if process.poll() is not None:
                    break
                time.sleep(1)
            if not report.exists():
                print(console.read_text(encoding="utf-8", errors="replace"))
                raise AssertionError("UIKit text layout probe failed; see its console output above")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
