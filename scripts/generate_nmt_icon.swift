// Generate the NMT icon locally. Run: swift scripts/generate_nmt_icon.swift
import AppKit
import Foundation

let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let directory = root.appendingPathComponent("assets/icons/nmt.iconset")
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
func drawIcon(_ size: Int) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let scale = CGFloat(size) / 64
    let transform = NSAffineTransform()
    transform.scale(by: scale)
    transform.concat()
    NSColor(calibratedRed: 0.71, green: 0.635, blue: 0.98, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 5, y: 5, width: 54, height: 54),
        xRadius: 13, yRadius: 13).fill()
    NSColor(calibratedRed: 0.137, green: 0.125, blue: 0.184, alpha: 1).setStroke()
    let path = NSBezierPath()
    path.lineWidth = 4.2
    path.lineCapStyle = .round
    path.move(to: NSPoint(x: 20, y: 23)); path.line(to: NSPoint(x: 20, y: 40))
    path.move(to: NSPoint(x: 28, y: 23)); path.line(to: NSPoint(x: 28, y: 37))
    path.curve(to: NSPoint(x: 44, y: 37), controlPoint1: NSPoint(x: 28, y: 49), controlPoint2: NSPoint(x: 44, y: 49))
    path.line(to: NSPoint(x: 44, y: 23)); path.stroke()
    let ticks = NSBezierPath(); ticks.lineWidth = 2.5; ticks.lineCapStyle = .round
    for x in [CGFloat(13), CGFloat(51)] {
        ticks.move(to: NSPoint(x: x, y: 31)); ticks.line(to: NSPoint(x: x, y: 34))
    }
    ticks.stroke()
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}
for size in [16, 32, 128, 256, 512] {
    try drawIcon(size).write(to: directory.appendingPathComponent("icon_\(size)x\(size).png"))
    try drawIcon(size * 2).write(to: directory.appendingPathComponent("icon_\(size)x\(size)@2x.png"))
}
try drawIcon(1024).write(to: root.appendingPathComponent("assets/icons/nmt.png"))
let tool = Process(); tool.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
tool.arguments = ["-c", "icns", directory.path, "-o", root.appendingPathComponent("assets/icons/nmt.icns").path]
try tool.run(); tool.waitUntilExit()
if tool.terminationStatus != 0 { exit(tool.terminationStatus) }
print("Generated assets/icons/nmt.icns")
