// RunPodBar: メニューバーに RunPod の Pod 稼働状態を出す常駐アプリ
//  ● 緑 = RUNNING（課金中）/ 灰 = 停止 / 橙 = 起動中 / 赤 = ERROR / 白抜き = 未設定
//  マウスを乗せるとツールチップで Pod・課金・ギャラリーのジョブを表示、クリックでメニュー（起動・停止・ジョブ一覧）
//  設定: ~/.config/krea2/runpod.env に RUNPOD_API_KEY=...（必須）、GALLERY_URL=...（任意）、RUNPOD_POD_ID=...（任意・絞り込み）
import AppKit
import Foundation

struct Config {
    var apiKey = ""
    var gallery = "https://pi5-home-1.tail8ec65a.ts.net:8452"
    var podId = ""
    static let path = NSString(string: "~/.config/krea2/runpod.env").expandingTildeInPath
    static func load() -> Config {
        var c = Config()
        guard let text = try? String(contentsOfFile: path, encoding: .utf8) else { return c }
        for line in text.split(separator: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("#") || !t.contains("=") { continue }
            let kv = t.split(separator: "=", maxSplits: 1).map { String($0).trimmingCharacters(in: .whitespaces) }
            guard kv.count == 2 else { continue }
            switch kv[0] {
            case "RUNPOD_API_KEY": c.apiKey = kv[1]
            case "GALLERY_URL": c.gallery = kv[1]
            case "RUNPOD_POD_ID": c.podId = kv[1]
            default: break
            }
        }
        return c
    }
}

struct Pod {
    let id: String, name: String, status: String, gpu: String, cost: Double, uptime: Int?, util: Int?, dc: String
    init(_ j: [String: Any]) {
        id = j["id"] as? String ?? "?"
        name = j["name"] as? String ?? id
        status = j["status"] as? String ?? "?"
        gpu = (j["gpu"] as? [String: Any])?["id"] as? String ?? ""
        cost = j["cost"] as? Double ?? 0
        dc = j["dataCenterId"] as? String ?? ""
        let rt = j["runtime"] as? [String: Any]
        uptime = rt?["uptime"] as? Int
        util = ((rt?["gpus"] as? [[String: Any]])?.first)?["util"] as? Int
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    var cfg = Config.load()
    var pods: [Pod] = []
    var jobs: [[String: Any]] = []
    var worker: [String: Any] = [:]
    var podError: String?
    var balance: Double?          // 残高 USD
    var spendPerHr: Double?       // 現在の消費 USD/h（GraphQL myself）
    var galleryError: String?
    var timer: Timer?
    var sessionStart: [String: Date] = [:]   // 自分が見ていた RUNNING の開始（目安の課金表示用）

    lazy var baseIcon: NSImage? = {
        // RunPod のロゴ（Resources/runpod_18.png, @2x）。無ければ ● にフォールバック
        let dir = Bundle.main.resourceURL ?? Bundle.main.bundleURL
        for name in ["runpod_18.png"] {
            if let img = NSImage(contentsOf: dir.appendingPathComponent(name)) {
                if let hi = NSImage(contentsOf: dir.appendingPathComponent("runpod_18@2x.png")), let rep = hi.representations.first {
                    img.addRepresentation(rep)
                }
                img.size = NSSize(width: 18, height: 18)
                return img
            }
        }
        return nil
    }()

    func tinted(_ color: NSColor) -> NSImage? {
        guard let base = baseIcon else { return nil }
        let img = NSImage(size: base.size, flipped: false) { rect in
            base.draw(in: rect)
            color.set()
            rect.fill(using: .sourceAtop)
            return true
        }
        img.isTemplate = false
        return img
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.imagePosition = .imageLeading
        item.menu = NSMenu()
        render()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.refresh() }
    }

    // ---------- 取得 ----------
    func refresh() {
        cfg = Config.load()
        fetchPods()
        fetchBalance()
        fetchGallery()
    }

    func fetchBalance() {
        guard !cfg.apiKey.isEmpty else { return }
        request("https://api.runpod.io/graphql", method: "POST", bearer: cfg.apiKey,
                body: ["query": "{ myself { clientBalance currentSpendPerHr } }"]) { obj, _ in
            let me = ((obj as? [String: Any])?["data"] as? [String: Any])?["myself"] as? [String: Any]
            self.balance = me?["clientBalance"] as? Double
            self.spendPerHr = me?["currentSpendPerHr"] as? Double
            self.render()
        }
    }

    func request(_ url: String, method: String = "GET", bearer: String? = nil, body: [String: Any]? = nil,
                 done: @escaping (Any?, String?) -> Void) {
        guard let u = URL(string: url) else { done(nil, "bad url"); return }
        var req = URLRequest(url: u, timeoutInterval: 20)
        req.httpMethod = method
        if let b = bearer { req.setValue("Bearer \(b)", forHTTPHeaderField: "Authorization") }
        if let body = body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        URLSession.shared.dataTask(with: req) { data, resp, err in
            DispatchQueue.main.async {
                if let err = err { done(nil, err.localizedDescription); return }
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                guard let data = data else { done(nil, "no data"); return }
                let obj = try? JSONSerialization.jsonObject(with: data)
                if code >= 300 { done(obj, "HTTP \(code)"); return }
                done(obj, nil)
            }
        }.resume()
    }

    func fetchPods() {
        guard !cfg.apiKey.isEmpty else { podError = "API キー未設定 (\(Config.path))"; render(); return }
        request("https://api.runpod.io/v2/pods", bearer: cfg.apiKey) { obj, err in
            if let err = err { self.podError = err; self.render(); return }
            var list: [[String: Any]] = []
            if let a = obj as? [[String: Any]] { list = a }
            else if let d = obj as? [String: Any] {
                list = (d["items"] as? [[String: Any]]) ?? (d["pods"] as? [[String: Any]]) ?? []
            }
            self.pods = list.map(Pod.init).filter { self.cfg.podId.isEmpty || $0.id == self.cfg.podId }
            for p in self.pods {
                if p.status == "RUNNING" { if self.sessionStart[p.id] == nil { self.sessionStart[p.id] = Date() } }
                else { self.sessionStart[p.id] = nil }
            }
            self.podError = nil
            self.render()
        }
    }

    func fetchGallery() {
        request("\(cfg.gallery)/api/jobs?limit=8") { obj, err in
            if let err = err { self.galleryError = err; self.render(); return }
            self.jobs = (obj as? [String: Any])?["items"] as? [[String: Any]] ?? []
            self.galleryError = nil
            self.render()
        }
        request("\(cfg.gallery)/api/worker") { obj, _ in
            self.worker = obj as? [String: Any] ?? [:]
            self.render()
        }
    }

    // ---------- 表示 ----------
    var primary: Pod? { pods.first(where: { $0.status == "RUNNING" }) ?? pods.first }
    var runningJob: [String: Any]? { jobs.first(where: { ($0["status"] as? String) == "running" }) }
    var queuedCount: Int { jobs.filter { ($0["status"] as? String) == "queued" }.count }

    // 起動中（待機）= 緑、ジョブ実行中 = RunPod 紫 #5D29F0
    static let runpodPurple = NSColor(srgbRed: 0x5D / 255.0, green: 0x29 / 255.0, blue: 0xF0 / 255.0, alpha: 1)
    var isBusy: Bool {
        if let rj = runningJob, (rj["worker"] as? String ?? "").hasPrefix("runpod") { return true }
        if let u = primary?.util, u >= 20 { return true }
        return false
    }

    func color(for status: String?) -> NSColor {
        switch status {
        case "RUNNING": return isBusy ? AppDelegate.runpodPurple : .systemGreen
        case "STARTING", "PROVISIONING": return .systemOrange
        case "ERROR": return .systemRed
        case nil: return .tertiaryLabelColor
        default: return .systemGray   // EXITED（停止中）は灰色
        }
    }

    func fmtUptime(_ s: Int?) -> String {
        guard let s = s else { return "-" }
        return s >= 3600 ? String(format: "%dh%02dm", s / 3600, (s % 3600) / 60) : String(format: "%dm", s / 60)
    }

    func jobLabel(_ j: [String: Any]) -> String {
        let p = j["params"] as? [String: Any] ?? [:]
        let t = j["type"] as? String ?? "?"
        let st = j["status"] as? String ?? ""
        let pct = (j["progress"] as? [String: Any])?["pct"]
        let pctS = (st == "running" && pct != nil) ? " \(Int((pct as? Double) ?? Double((pct as? Int) ?? 0)))%" : ""
        let mark = ["queued": "⏳", "running": "▶︎", "done": "✓", "failed": "✗", "cancelled": "–"][st] ?? "·"
        var desc = ""
        switch t {
        case "gen", "edit", "compare": desc = (p["prompt"] as? String ?? "").prefix(40).description
        case "train": desc = "\(p["run"] as? String ?? "") \(p["steps"] ?? "") steps"
        default: desc = t
        }
        let tl = ["gen": "生成", "edit": "編集", "train": "学習", "compare": "比較"][t] ?? t
        return "\(mark) \(tl)\(pctS): \(desc)"
    }

    func render() {
        guard let button = item.button else { return }
        let p = primary
        let status = podError != nil ? nil : p?.status
        let c = color(for: status)
        let title = NSMutableAttributedString()
        if let icon = tinted(c) { button.image = icon } else {
            title.append(NSAttributedString(string: "●", attributes: [.foregroundColor: c, .font: NSFont.systemFont(ofSize: 13)]))
        }
        var suffix = ""
        if let b = balance { suffix += String(format: " $%.2f", b) }
        if p?.status == "RUNNING" { suffix += String(format: " (-%.2f/h)", spendPerHr ?? p!.cost) }
        if let rj = runningJob, let pct = (rj["progress"] as? [String: Any])?["pct"] {
            let v = (pct as? Double) ?? Double((pct as? Int) ?? 0)
            suffix += String(format: " %d%%", Int(v))
        } else if queuedCount > 0 { suffix += " ⏳\(queuedCount)" }
        title.append(NSAttributedString(string: suffix, attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .regular)]))
        button.attributedTitle = title

        // ツールチップ（ホバー）
        var tip: [String] = []
        if let e = podError { tip.append("RunPod: \(e)") }
        for pod in pods {
            var line = "\(pod.name): \(pod.status)  \(pod.gpu) \(pod.dc)"
            if pod.status == "RUNNING" {
                line += String(format: "  $%.2f/h  稼働 %@", pod.cost, fmtUptime(pod.uptime))
                if let u = pod.util { line += "  GPU \(u)%" }
                if let s = sessionStart[pod.id] { line += String(format: "  (監視開始から約 $%.2f)", pod.cost * Date().timeIntervalSince(s) / 3600) }
            }
            tip.append(line)
        }
        if pods.isEmpty && podError == nil { tip.append("Pod なし") }
        if let b = balance {
            var line = String(format: "残高 $%.2f", b)
            if let s = spendPerHr, s > 0 { line += String(format: "  消費 $%.3f/h  → あと約 %.1f 時間", s, b / s) }
            tip.append(line)
        }
        if let e = galleryError { tip.append("ギャラリー: \(e)") } else {
            let online = (worker["online"] as? Bool) ?? false
            tip.append("WSL2 ワーカー: \(online ? "online" : "offline")")
            for j in jobs.prefix(5) { tip.append(jobLabel(j)) }
        }
        button.toolTip = tip.joined(separator: "\n")
        buildMenu()
    }

    func buildMenu() {
        let m = NSMenu()
        if let e = podError { m.addItem(withTitle: "RunPod: \(e)", action: nil, keyEquivalent: "") }
        for pod in pods {
            let head = NSMenuItem(title: "\(pod.name) — \(pod.status)" + (pod.status == "RUNNING" ? String(format: "  $%.2f/h  %@", pod.cost, fmtUptime(pod.uptime)) : ""), action: nil, keyEquivalent: "")
            m.addItem(head)
            let sub = NSMenuItem(title: "    \(pod.gpu)  \(pod.dc)", action: nil, keyEquivalent: "")
            sub.isEnabled = false
            m.addItem(sub)
            if pod.status == "RUNNING" {
                let stop = NSMenuItem(title: "    Pod を停止する", action: #selector(stopPod(_:)), keyEquivalent: "")
                stop.representedObject = pod.id; stop.target = self; m.addItem(stop)
            } else if pod.status == "EXITED" {
                let start = NSMenuItem(title: "    Pod を起動する", action: #selector(startPod(_:)), keyEquivalent: "")
                start.representedObject = pod.id; start.target = self; m.addItem(start)
            }
        }
        if let b = balance {
            var t = String(format: "残高 $%.2f", b)
            if let s = spendPerHr, s > 0 { t += String(format: "  （$%.3f/h → あと約 %.1f 時間）", s, b / s) }
            m.addItem(withTitle: t, action: nil, keyEquivalent: "")
        }
        m.addItem(.separator())
        if let e = galleryError { m.addItem(withTitle: "ギャラリー: \(e)", action: nil, keyEquivalent: "") }
        let online = (worker["online"] as? Bool) ?? false
        m.addItem(withTitle: "ギャラリー ジョブ（WSL2 ワーカー \(online ? "online" : "offline")）", action: nil, keyEquivalent: "")
        if jobs.isEmpty { m.addItem(withTitle: "    なし", action: nil, keyEquivalent: "") }
        for j in jobs.prefix(8) {
            let it = NSMenuItem(title: "    " + jobLabel(j), action: #selector(openGallery), keyEquivalent: "")
            it.target = self; m.addItem(it)
        }
        m.addItem(.separator())
        let og = NSMenuItem(title: "ギャラリーを開く", action: #selector(openGallery), keyEquivalent: "g"); og.target = self; m.addItem(og)
        let oc = NSMenuItem(title: "RunPod コンソールを開く", action: #selector(openConsole), keyEquivalent: ""); oc.target = self; m.addItem(oc)
        let rf = NSMenuItem(title: "今すぐ更新", action: #selector(refreshNow), keyEquivalent: "r"); rf.target = self; m.addItem(rf)
        let cf = NSMenuItem(title: "設定ファイルを開く (\(Config.path))", action: #selector(openConfig), keyEquivalent: ""); cf.target = self; m.addItem(cf)
        m.addItem(.separator())
        let q = NSMenuItem(title: "RunPodBar を終了", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"); m.addItem(q)
        item.menu = m
    }

    // ---------- 操作 ----------
    func podAction(_ id: String, _ action: String) {
        request("https://api.runpod.io/v2/pods/\(id)/action", method: "POST", bearer: cfg.apiKey, body: ["action": action]) { _, err in
            if let err = err { self.alert("\(action) に失敗: \(err)") }
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) { self.refresh() }
        }
    }

    @objc func stopPod(_ sender: NSMenuItem) {
        guard let id = sender.representedObject as? String else { return }
        if confirm("Pod \(id) を停止しますか？", "実行中のジョブがあれば消えます。ディスクは残り、GPU 課金が止まります。") { podAction(id, "stop") }
    }

    @objc func startPod(_ sender: NSMenuItem) {
        guard let id = sender.representedObject as? String else { return }
        if confirm("Pod \(id) を起動しますか？", "起動した瞬間から課金されます。止め忘れに注意。") { podAction(id, "start") }
    }

    @objc func openGallery() { NSWorkspace.shared.open(URL(string: cfg.gallery)!) }
    @objc func openConsole() { NSWorkspace.shared.open(URL(string: "https://console.runpod.io/pods")!) }
    @objc func refreshNow() { refresh() }
    @objc func openConfig() {
        let dir = (Config.path as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: Config.path) {
            try? "# RunPodBar 設定\nRUNPOD_API_KEY=\nGALLERY_URL=https://pi5-home-1.tail8ec65a.ts.net:8452\n#RUNPOD_POD_ID=\n".write(toFile: Config.path, atomically: true, encoding: .utf8)
        }
        NSWorkspace.shared.open(URL(fileURLWithPath: Config.path))
    }

    func confirm(_ msg: String, _ info: String) -> Bool {
        let a = NSAlert(); a.messageText = msg; a.informativeText = info
        a.addButton(withTitle: "実行"); a.addButton(withTitle: "やめる")
        NSApp.activate(ignoringOtherApps: true)
        return a.runModal() == .alertFirstButtonReturn
    }

    func alert(_ msg: String) {
        let a = NSAlert(); a.messageText = msg; NSApp.activate(ignoringOtherApps: true); a.runModal()
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // Dock に出さない
let delegate = AppDelegate()
app.delegate = delegate
app.run()
