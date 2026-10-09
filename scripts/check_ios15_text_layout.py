"""Exercise the actual legacy intrinsic-size override in UIKit on a simulator.

Requires Xcode. Forces only the OS availability branch so newer simulators can
check the iOS 15 sizing logic; this does not replace iOS 15 device testing.
"""
from pathlib import Path
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
swift = '''import UIKit
final class ProbeTextView: UITextView {
''' + sizing + '''
}
@main final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
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
        let result = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("result.txt")
        try! "PASS: UIKit legacy wrapping, streaming growth, width changes and font scaling".write(to: result, atomically: true, encoding: .utf8)
        return true
    }
}
'''
devices = json.loads(run("xcrun", "simctl", "list", "devices", "available", "--json"))["devices"]
device = next(d["udid"] for group in devices.values() for d in group if "iPhone" in d["name"])
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
    run("xcrun", "simctl", "launch", device, "com.openminis.layoutprobe")
    data = Path(run("xcrun", "simctl", "get_app_container", device, "com.openminis.layoutprobe", "data"))
    report = data / "Documents/result.txt"
    for _ in range(30):
        if report.exists():
            print(report.read_text(encoding="utf-8"))
            break
        time.sleep(1)
    else:
        raise AssertionError("UIKit text layout probe failed; inspect the simulator crash report")
