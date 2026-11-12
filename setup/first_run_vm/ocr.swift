// Read the text on a screenshot for the first-run VM check.
// Usage: ocr <image.png>  ->  JSON [{"text", "x", "y", "w", "h"}] in image
// pixels with a top-left origin, Korean and English, accurate recognition.
import AppKit
import Vision

guard CommandLine.arguments.count == 2,
      let image = NSImage(contentsOfFile: CommandLine.arguments[1]),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write(Data("usage: ocr <image.png>\n".utf8)); exit(2)
}
let width = CGFloat(cg.width), height = CGFloat(cg.height)
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["ko-KR", "en-US"]
request.usesLanguageCorrection = false
try VNImageRequestHandler(cgImage: cg).perform([request])
var lines: [[String: Any]] = []
for observation in request.results ?? [] {
    guard let best = observation.topCandidates(1).first else { continue }
    let box = observation.boundingBox   // normalized, bottom-left origin
    lines.append(["text": best.string,
                  "x": Int(box.minX * width), "y": Int((1 - box.maxY) * height),
                  "w": Int(box.width * width), "h": Int(box.height * height)])
}
print(String(data: try JSONSerialization.data(withJSONObject: lines), encoding: .utf8)!)
