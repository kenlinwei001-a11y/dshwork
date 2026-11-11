import Foundation
import AppKit
import CoreGraphics
// usage: crop in.png out.png x y w h [scale]
let a = CommandLine.arguments
guard a.count >= 7 else { exit(2) }
let inPath = a[1], outPath = a[2]
let x = Int(a[3])!, y = Int(a[4])!, w = Int(a[5])!, h = Int(a[6])!
let sc = a.count > 7 ? (Double(a[7]) ?? 1.0) : 1.0
guard let src = NSImage(contentsOfFile: inPath),
      let tiff = src.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let cg = rep.cgImage else { exit(1) }
let rect = CGRect(x: x, y: y, width: w, height: h)
guard let cropped = cg.cropping(to: rect) else { exit(1) }
let ow = Int(Double(w) * sc), oh = Int(Double(h) * sc)
guard let ctx = CGContext(data: nil, width: ow, height: oh, bitsPerComponent: 8, bytesPerRow: 0,
                          space: CGColorSpaceCreateDeviceRGB(),
                          bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue) else { exit(1) }
ctx.interpolationQuality = .high
ctx.draw(cropped, in: CGRect(x: 0, y: 0, width: ow, height: oh))
guard let out = ctx.makeImage(),
      let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: outPath) as CFURL, "public.png" as CFString, 1, nil) else { exit(1) }
CGImageDestinationAddImage(dest, out, nil)
CGImageDestinationFinalize(dest)
