import Foundation
import ScreenCaptureKit
import CoreMedia
import CoreAudio

struct Request: Decodable {
    let id: Int?
    let action: String
    let window_id: UInt32?
}

final class AudioOutput: NSObject, SCStreamOutput {
    var onChunk: ((String) -> Void)?

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, CMSampleBufferIsValid(sampleBuffer),
              let format = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(format)?.pointee,
              let block = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }
        var length = 0
        var dataPointer: UnsafeMutablePointer<Int8>?
        guard CMBlockBufferGetDataPointer(
            block, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length,
            dataPointerOut: &dataPointer
        ) == noErr, let dataPointer else { return }

        let channels = max(1, Int(asbd.mChannelsPerFrame))
        let bytesPerSample = max(1, Int(asbd.mBitsPerChannel / 8))
        let frames = length / (channels * bytesPerSample)
        guard frames > 0 else { return }
        var output = Data(capacity: frames * 2)
        for frame in 0..<frames {
            var sum: Int32 = 0
            for channel in 0..<channels {
                let offset = (frame * channels + channel) * bytesPerSample
                let sample: Int32
                if bytesPerSample >= 4 && (asbd.mFormatFlags & kAudioFormatFlagIsFloat) != 0 {
                    let value = dataPointer.advanced(by: offset)
                        .withMemoryRebound(to: Float.self, capacity: 1) { $0.pointee }
                    sample = Int32(max(-1, min(1, value)) * 32767)
                } else if bytesPerSample >= 4 {
                    sample = Int32(
                        littleEndian: dataPointer.advanced(by: offset)
                            .withMemoryRebound(to: Int32.self, capacity: 1) { $0.pointee }
                    ) >> 16
                } else {
                    sample = Int32(Int16(
                        littleEndian: dataPointer.advanced(by: offset)
                            .withMemoryRebound(to: Int16.self, capacity: 1) { $0.pointee }
                    ))
                }
                sum += sample
            }
            var mono = Int16(max(-32768, min(32767, sum / Int32(channels))))
            withUnsafeBytes(of: &mono) { output.append(contentsOf: $0) }
        }
        onChunk?(output.base64EncodedString())
    }
}

@available(macOS 13.0, *)
final class Capture: NSObject, SCStreamDelegate {
    var stream: SCStream?
    let output = AudioOutput()
    var emit: (([String: Any]) -> Void)!

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        emit(["type": "error", "message": "系统音频采集已停止：\(error.localizedDescription)"])
    }

    func list() async throws -> [[String: Any]] {
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: true
        )
        return content.windows.compactMap { window in
            guard let app = window.owningApplication else { return nil }
            return [
                "id": window.windowID,
                "title": window.title ?? "",
                "application": app.applicationName,
                "bundle_id": app.bundleIdentifier
            ]
        }
    }

    func start(windowID: UInt32) async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: true
        )
        guard let window = content.windows.first(where: { $0.windowID == windowID }) else {
            throw NSError(
                domain: "NMTSystemAudio", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "找不到所选窗口，请重新选择"]
            )
        }
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let configuration = SCStreamConfiguration()
        configuration.capturesAudio = true
        configuration.sampleRate = 16_000
        configuration.channelCount = 1
        configuration.excludesCurrentProcessAudio = true
        configuration.width = 2
        configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        output.onChunk = { [weak self] base64 in
            self?.emit([
                "type": "audio", "audio_base64": base64,
                "sample_rate": 16_000, "channels": 1
            ])
        }
        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        try stream.addStreamOutput(
            output, type: .audio, sampleHandlerQueue: DispatchQueue(label: "nmt.system-audio")
        )
        try await stream.startCapture()
        self.stream = stream
        emit(["type": "started", "window_id": windowID, "message": "系统音频已开始采集"])
    }

    func stop() async {
        if let stream { try? await stream.stopCapture() }
        stream = nil
        emit(["type": "stopped"])
    }
}

@main
struct SystemAudioBridge {
    static func emit(_ body: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: body),
              let line = String(data: data, encoding: .utf8) else { return }
        print(line)
        fflush(stdout)
    }

    static func main() async {
        guard #available(macOS 13.0, *) else {
            emit(["type": "error", "message": "系统音频采集需要 macOS 13 或更高版本"])
            return
        }
        let capture = Capture()
        capture.emit = emit
        while let line = readLine() {
            guard let data = line.data(using: .utf8),
                  let request = try? JSONDecoder().decode(Request.self, from: data) else { continue }
            do {
                switch request.action {
                case "list":
                    emit(["id": request.id as Any, "type": "windows", "items": try await capture.list()])
                case "start":
                    guard let id = request.window_id else {
                        throw NSError(
                            domain: "NMTSystemAudio", code: 2,
                            userInfo: [NSLocalizedDescriptionKey: "缺少窗口编号"]
                        )
                    }
                    try await capture.start(windowID: id)
                case "stop":
                    await capture.stop()
                    emit(["id": request.id as Any, "ok": true])
                default:
                    emit(["id": request.id as Any, "type": "error", "message": "未知系统音频指令"])
                }
            } catch {
                emit(["id": request.id as Any, "type": "error", "message": error.localizedDescription])
            }
        }
    }
}
