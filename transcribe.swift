import Foundation
import Speech

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write(Data("Usage: transcribe.swift <audio-file>\n".utf8))
    exit(1)
}

let audioURL = URL(fileURLWithPath: args[1])
let locale = Locale(identifier: args.count >= 3 ? args[2] : "zh_CN")
let semaphore = DispatchSemaphore(value: 0)

func finish(_ code: Int32, _ message: String) -> Never {
    if !message.isEmpty {
        FileHandle.standardOutput.write(Data(message.utf8))
    }
    exit(code)
}

SFSpeechRecognizer.requestAuthorization { status in
    guard status == .authorized else {
        finish(2, "Speech authorization status: \(status.rawValue)\n")
    }

    guard let recognizer = SFSpeechRecognizer(locale: locale) else {
        finish(3, "Failed to create speech recognizer for locale \(locale.identifier)\n")
    }

    let request = SFSpeechURLRecognitionRequest(url: audioURL)
    request.shouldReportPartialResults = false
    request.requiresOnDeviceRecognition = false

    recognizer.recognitionTask(with: request) { result, error in
        if let error {
            finish(4, "Recognition error: \(error.localizedDescription)\n")
        }

        guard let result else { return }
        if result.isFinal {
            finish(0, result.bestTranscription.formattedString + "\n")
        }
    }
}

dispatchMain()
