import Foundation
import PDFKit
import Vision
import AppKit
import CoreGraphics

// usage: grid <pdf> <pageNo1based> <outjson> <dpi> [x0,y0,x1,y1 in points]
let a = CommandLine.arguments
guard a.count >= 5 else { exit(2) }
let pageNo = Int(a[2])! - 1
let outPath = a[3]
let dpi = Double(a[4]) ?? 300
var clip: CGRect? = nil
if a.count >= 6 {
    let p = a[5].split(separator: ",").map { Double($0)! }
    clip = CGRect(x: p[0], y: p[1], width: p[2] - p[0], height: p[3] - p[1])
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: a[1])), let page = doc.page(at: pageNo) else { exit(1) }
let box = page.bounds(for: .mediaBox)
let scale = dpi / 72.0
let W = Int(box.width * scale), H = Int(box.height * scale)
guard let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W * 4,
                          space: CGColorSpaceCreateDeviceRGB(),
                          bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue) else { exit(1) }
ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: W, height: H))
ctx.scaleBy(x: scale, y: scale); page.draw(with: .mediaBox, to: ctx)
guard let img = ctx.makeImage() else { exit(1) }

// 取像素
guard let data = img.dataProvider?.data, let ptr = CFDataGetBytePtr(data) else { exit(1) }
let bpr = img.bytesPerRow
func isDark(_ x: Int, _ y: Int) -> Bool {
    let o = y * bpr + x * 4
    let r = Int(ptr[o+1]), g = Int(ptr[o+2]), b = Int(ptr[o+3])
    return (r + g + b) / 3 < 128
}
// 裁剪区（点→像素，y 翻转）
let cx0 = Int((clip?.minX ?? 0) * scale), cx1 = Int((clip?.maxX ?? box.width) * scale)
let cy0 = H - Int((clip?.maxY ?? box.height) * scale), cy1 = H - Int((clip?.minY ?? 0) * scale)
let x0 = max(0, cx0), x1 = min(W, cx1), y0 = max(0, cy0), y1 = min(H, cy1)
let rw = x1 - x0, rh = y1 - y0

// 投影找线
var hLines: [Int] = [], vLines: [Int] = []
for y in y0..<y1 {
    var c = 0
    for x in stride(from: x0, to: x1, by: 2) where isDark(x, y) { c += 1 }
    if Double(c) > Double(rw / 2) * 0.45 { hLines.append(y) }
}
for x in x0..<x1 {
    var c = 0
    for y in stride(from: y0, to: y1, by: 2) where isDark(x, y) { c += 1 }
    if Double(c) > Double(rh / 2) * 0.45 { vLines.append(x) }
}
func merge(_ v: [Int], tol: Int = 6) -> [Int] {
    var out: [Int] = []
    for x in v.sorted() { if let last = out.last, x - last <= tol { continue }; out.append(x) }
    return out
}
let Hs = merge(hLines), Vs = merge(vLines)

// 逐格 OCR
struct Cell: Codable { let r: Int; let c: Int; let x: Int; let y: Int; let w: Int; let h: Int; let text: String; let conf: Float }
var cells: [Cell] = []
if Hs.count >= 2 && Vs.count >= 2 {
    for i in 0..<(Hs.count - 1) {
        for j in 0..<(Vs.count - 1) {
            let rx = Vs[j] + 2, ry = Hs[i] + 2
            let rwid = Vs[j+1] - Vs[j] - 4, rhei = Hs[i+1] - Hs[i] - 4
            if rwid < 8 || rhei < 8 { continue }
            guard let sub = img.cropping(to: CGRect(x: rx, y: ry, width: rwid, height: rhei)) else { continue }
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            req.recognitionLanguages = ["zh-Hans", "en-US"]
            let handler = VNImageRequestHandler(cgImage: sub, options: [:])
            try? handler.perform([req])
            let texts = (req.results ?? []).compactMap { $0.topCandidates(1).first }.map { $0.string }
            let conf = (req.results ?? []).compactMap { $0.topCandidates(1).first?.confidence }.min() ?? 0
            cells.append(Cell(r: i, c: j, x: rx, y: ry, w: rwid, h: rhei,
                              text: texts.joined(separator: " "), conf: conf))
        }
    }
}
let payload: [String: Any] = ["page": pageNo + 1, "image": [W, H], "clip": [x0, y0, x1, y1],
                              "h_lines": Hs, "v_lines": Vs,
                              "n_rows": max(0, Hs.count - 1), "n_cols": max(0, Vs.count - 1),
                              "cells": cells.map { ["r": $0.r, "c": $0.c, "x": $0.x, "y": $0.y,
                                                    "w": $0.w, "h": $0.h, "text": $0.text, "conf": $0.conf] }]
let js = try! JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
try! js.write(to: URL(fileURLWithPath: outPath))
FileHandle.standardError.write("h_lines=\(Hs.count) v_lines=\(Vs.count) cells=\(cells.count)\n".data(using: .utf8)!)
