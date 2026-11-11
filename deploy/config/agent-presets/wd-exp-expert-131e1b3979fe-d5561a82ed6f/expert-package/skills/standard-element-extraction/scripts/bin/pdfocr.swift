import Foundation
import PDFKit
import Vision
import AppKit
import CoreGraphics

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: ocr <pdf> <outdir> [dpi]\n".data(using: .utf8)!)
    exit(2)
}
let pdfPath = args[1]
let outDir = args[2]
let dpi = args.count > 3 ? (Double(args[3]) ?? 300.0) : 300.0

guard let doc = PDFDocument(url: URL(fileURLWithPath: pdfPath)) else {
    FileHandle.standardError.write("cannot open pdf\n".data(using: .utf8)!)
    exit(1)
}
let scale = dpi / 72.0
try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let box = page.bounds(for: .mediaBox)
    let w = Int((box.width * scale).rounded())
    let h = Int((box.height * scale).rounded())
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue) else { continue }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    guard let cg = ctx.makeImage() else { continue }

    // save page png
    let pngPath = "\(outDir)/page-\(String(format: "%02d", i+1)).png"
    if let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: pngPath) as CFURL, "public.png" as CFString, 1, nil) {
        CGImageDestinationAddImage(dest, cg, nil)
        CGImageDestinationFinalize(dest)
    }

    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch {
        FileHandle.standardError.write("ocr fail page \(i+1)\n".data(using: .utf8)!)
        continue
    }
    guard let obs = req.results else { continue }
    var rows: [(Double, Double, Double, Double, Float, String)] = []
    for o in obs {
        guard let c = o.topCandidates(1).first else { continue }
        let bb = o.boundingBox  // normalized, origin bottom-left
        let x = Double(bb.minX) * Double(w)
        let yTop = (1.0 - Double(bb.maxY)) * Double(h)
        rows.append((x, yTop, Double(bb.width) * Double(w), Double(bb.height) * Double(h), c.confidence, c.string))
    }
    rows.sort { a, b in (abs(a.1 - b.1) < 8 ? a.0 < b.0 : a.1 < b.1) }
    var out = ""
    out += "# page \(i+1) size=\(w)x\(h)\n"
    for r in rows {
        let t = r.5.replacingOccurrences(of: "\t", with: " ")
        out += String(format: "%d\t%.0f\t%.0f\t%.0f\t%.0f\t%.2f\t%@\n", i+1, r.0, r.1, r.2, r.3, r.4, t)
    }
    try? out.write(toFile: "\(outDir)/page-\(String(format: "%02d", i+1)).tsv", atomically: true, encoding: .utf8)
    FileHandle.standardError.write("page \(i+1)/\(doc.pageCount) lines=\(rows.count)\n".data(using: .utf8)!)
}
