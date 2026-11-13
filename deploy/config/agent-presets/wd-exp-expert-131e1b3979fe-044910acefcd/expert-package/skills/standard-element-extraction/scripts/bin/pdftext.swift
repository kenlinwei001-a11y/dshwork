import Foundation
import PDFKit
let a = CommandLine.arguments
guard a.count >= 3 else { exit(2) }
guard let doc = PDFDocument(url: URL(fileURLWithPath: a[1])) else { exit(1) }
var out = ""
for i in 0..<doc.pageCount {
    guard let p = doc.page(at: i) else { continue }
    out += "\n===== PAGE \(i+1) =====\n"
    out += p.string ?? ""
}
try? out.write(toFile: a[2], atomically: true, encoding: .utf8)
