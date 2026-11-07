// JSON-lines bridge for SpeechAnalyzer. Audio is PCM16 mono over stdin only.
// Apple Speech assets are managed by macOS; downloads require an explicit install command.
import Foundation
import Speech
import AVFoundation
import CoreMedia

struct BridgeFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

struct Request: Decodable {
    var id: Int?
    var action: String
    var languages: [String]?
    var language: String?
    var audio: String?
    var sample_rate: Int?
    var start_ms: Int?
}

struct Word: Codable, Sendable {
    let text: String
    let start_ms: Int
    let end_ms: Int
}

struct Candidate: Sendable {
    let text: String
    let language: String
    let confidence: Double
    let words: [Word]
}

@available(macOS 26.0, *)
enum AppleSpeech {
    static let locales = ["zh": "zh-CN", "ja": "ja-JP", "en": "en-US"]

    static func module(_ language: String) async throws -> SpeechTranscriber {
        guard let identifier = locales[language],
              let locale = await SpeechTranscriber.supportedLocale(equivalentTo: Locale(identifier: identifier)) else {
            throw BridgeFailure(message: "Apple SpeechAnalyzer 不支持所选语言：\(language)")
        }
        return SpeechTranscriber(locale: locale, transcriptionOptions: [],
                                 reportingOptions: [.volatileResults, .fastResults],
                                 attributeOptions: [.audioTimeRange, .transcriptionConfidence])
    }

    static func probe() async -> [String: Any] {
        guard SpeechTranscriber.isAvailable else {
            return ["available": false, "message": "这台 Mac 无法使用 Apple SpeechAnalyzer", "languages": []]
        }
        var rows = [[String: Any]]()
        for language in ["zh", "ja", "en"] {
            do {
                let transcriber = try await module(language)
                let status = await AssetInventory.status(forModules: [transcriber])
                let state: String
                switch status {
                case .installed: state = "installed"
                case .downloading: state = "downloading"
                case .supported: state = "missing"
                case .unsupported: state = "unsupported"
                @unknown default: state = "unknown"
                }
                rows.append(["language": language, "locale": transcriber.selectedLocales.first?.identifier ?? "",
                             "status": state, "installed": status == .installed])
            } catch {
                rows.append(["language": language, "status": "unsupported", "installed": false])
            }
        }
        return ["available": true, "languages": rows, "max_reserved_locales": AssetInventory.maximumReservedLocales,
                "storage": "macOS", "bundle_identifier": Bundle.main.bundleIdentifier ?? "", "message": "Apple 语言资源由 macOS 管理，识别在本机执行"]
    }

    static func installedModule(_ language: String) async throws -> SpeechTranscriber {
        let transcriber = try await module(language)
        guard await AssetInventory.status(forModules: [transcriber]) == .installed else {
            throw BridgeFailure(message: "Apple \(language) 语言资源尚未就绪，请在本地设置中点击准备语言资源")
        }
        return transcriber
    }

    static func prepare(_ languages: [String]) async throws {
        for language in languages {
            let transcriber = try await installedModule(language)
            let analyzer = SpeechAnalyzer(modules: [transcriber], options: .init(priority: .userInitiated, modelRetention: .processLifetime))
            do { try await analyzer.prepareToAnalyze(in: nil) }
            catch { await analyzer.cancelAndFinishNow(); throw error }
            await analyzer.cancelAndFinishNow()
        }
    }

    static func install(_ languages: [String]) async throws -> [String: Any] {
        for language in languages {
            let transcriber = try await module(language)
            if await AssetInventory.status(forModules: [transcriber]) != .installed {
                if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                    try await request.downloadAndInstall()
                }
            }
            guard await AssetInventory.status(forModules: [transcriber]) == .installed else {
                throw BridgeFailure(message: "Apple \(language) 语言资源尚未安装完成，请检查系统网络后重试")
            }
        }
        return ["installed": true, "languages": languages, "message": "Apple 语言资源已准备好，保存设置并重启后使用"]
    }

    static func recognize(_ pcm: Data, rate: Int, start: Int, language: String) async throws -> Candidate {
        let transcriber = try await installedModule(language)
        guard let format = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber]),
              let inputFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: Double(rate), channels: 1, interleaved: false),
              let input = AVAudioPCMBuffer(pcmFormat: inputFormat, frameCapacity: AVAudioFrameCount(pcm.count / 2)),
              let samples = input.floatChannelData?[0] else {
            throw BridgeFailure(message: "无法准备 Apple 语音识别音频格式")
        }
        input.frameLength = input.frameCapacity
        pcm.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
            for index in 0..<Int(input.frameLength) {
                let sample = raw.loadUnaligned(fromByteOffset: index * 2, as: Int16.self)
                samples[index] = Float(Int16(littleEndian: sample)) / 32768
            }
        }
        guard let converter = AVAudioConverter(from: inputFormat, to: format),
              let converted = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(ceil(Double(input.frameLength) * format.sampleRate / inputFormat.sampleRate)) + 64) else {
            throw BridgeFailure(message: "无法转换 Apple 语音识别音频")
        }
        var supplied = false
        var conversionError: NSError?
        converter.convert(to: converted, error: &conversionError) { _, status in
            if supplied { status.pointee = .endOfStream; return nil }
            supplied = true
            status.pointee = .haveData
            return input
        }
        if let conversionError { throw conversionError }
        let analyzer = SpeechAnalyzer(modules: [transcriber], options: .init(priority: .userInitiated, modelRetention: .processLifetime))
        // One bounded decode window; resident system models survive successive jobs.
        // Only finalized results are returned, so volatile revisions aren't duplicated.
        let collector = Task { () throws -> Candidate in
            var text = "", words = [Word](), scores = [Double]()
            for try await result in transcriber.results where result.isFinal {
                text += String(result.text.characters)
                for run in result.text.runs {
                    let token = String(result.text[run.range].characters)
                    if let confidence = run.transcriptionConfidence, confidence.isFinite { scores.append(confidence) }
                    if let range = run.audioTimeRange {
                        let begin = CMTimeGetSeconds(range.start), end = CMTimeGetSeconds(CMTimeRangeGetEnd(range))
                        if begin.isFinite && end.isFinite {
                            words.append(Word(text: token, start_ms: start + max(0, Int((begin * 1000).rounded())),
                                              end_ms: start + max(0, Int((end * 1000).rounded()))))
                        }
                    }
                }
            }
            return Candidate(text: text.trimmingCharacters(in: .whitespacesAndNewlines), language: language,
                             confidence: scores.isEmpty ? 0 : scores.reduce(0, +) / Double(scores.count), words: words)
        }
        do {
            try await analyzer.prepareToAnalyze(in: format)
            let (stream, continuation) = AsyncStream<AnalyzerInput>.makeStream()
            continuation.yield(AnalyzerInput(buffer: converted))
            continuation.finish()
            if let last = try await analyzer.analyzeSequence(stream) {
                try await analyzer.finalizeAndFinish(through: last)
            } else { await analyzer.cancelAndFinishNow() }
            return try await collector.value
        } catch {
            await analyzer.cancelAndFinishNow()
            collector.cancel()
            throw error
        }
    }

    static func execute(_ request: Request) async throws -> [String: Any] {
        let languages = Array(Set(request.languages ?? ["zh", "ja", "en"])).sorted()
        guard !languages.isEmpty, languages.count <= 3, languages.allSatisfy({ locales[$0] != nil }) else {
            throw BridgeFailure(message: "Apple 语音识别只支持本应用中的中文、日语、英语")
        }
        switch request.action {
        case "probe": return await probe()
        case "install": return try await install(languages)
        case "warmup":
            try await prepare(languages)
            return ["ready": true, "languages": languages]
        case "transcribe":
            guard let audio = request.audio, let pcm = Data(base64Encoded: audio), !pcm.isEmpty, pcm.count % 2 == 0,
                  let rate = request.sample_rate, (8000...48000).contains(rate), pcm.count <= rate * 2 * 10 else {
                throw BridgeFailure(message: "Apple 语音识别需要不超过 10 秒的完整 PCM16 单声道音频")
            }
            let candidates = request.language.flatMap { locales[$0] == nil ? nil : [$0] } ?? languages
            let results = try await withThrowingTaskGroup(of: Candidate.self) { group in
                for language in candidates {
                    group.addTask { try await recognize(pcm, rate: rate, start: request.start_ms ?? 0, language: language) }
                }
                var results = [Candidate]()
                for try await result in group { results.append(result) }
                return results.sorted { $0.language < $1.language }
            }
            // Return candidates, not a fabricated native language detection result.
            // The caller selects within the current meeting pair by confidence.
            let encoded = try results.map { candidate -> [String: Any] in
                ["text": candidate.text, "language": candidate.language, "confidence": candidate.confidence,
                 "words": try JSONSerialization.jsonObject(with: JSONEncoder().encode(candidate.words))]
            }
            return ["candidates": encoded]
        default: throw BridgeFailure(message: "未知 Apple 语音指令")
        }
    }
}

@main
struct AppleSpeechBridge {
    static func emit(_ body: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]),
           let line = String(data: data, encoding: .utf8) {
            print(line)
            fflush(stdout)
        }
    }
    static func main() async {
        while let line = readLine() {
            var id: Int?
            do {
                let request = try JSONDecoder().decode(Request.self, from: Data(line.utf8))
                id = request.id
                guard #available(macOS 26.0, *) else {
                    throw BridgeFailure(message: "Apple SpeechAnalyzer 需要 macOS 26 或更高版本")
                }
                let body = try await AppleSpeech.execute(request)
                emit(body.merging(["ok": true, "id": id ?? 0]) { old, _ in old })
            } catch {
                emit(["ok": false, "id": id ?? 0, "message": error.localizedDescription])
            }
        }
    }
}
