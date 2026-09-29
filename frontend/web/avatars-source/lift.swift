// Lift the subject out of an image with macOS's own Vision model (D-118): writes a PNG whose
// alpha is the foreground mask — what Photos' "lift subject" does. Usage: lift <in> <out.png>
import AppKit
import CoreImage
import Vision

let args = CommandLine.arguments
guard args.count == 3, let image = CIImage(contentsOf: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("usage: lift <in> <out.png>\n".data(using: .utf8)!); exit(2)
}
let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(ciImage: image)
do {
    try handler.perform([request])
    guard let result = request.results?.first else { print("no subject"); exit(1) }
    let buffer = try result.generateMaskedImage(
        ofInstances: result.allInstances, from: handler, croppedToInstancesExtent: false)
    let masked = CIImage(cvPixelBuffer: buffer)
    let context = CIContext()
    try context.writePNGRepresentation(
        of: masked, to: URL(fileURLWithPath: args[2]), format: .RGBA8,
        colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
    print("ok", args[2])
} catch { print("error", error); exit(1) }
