// The rules of the SOS hold, with no widgets so a test can run them (test/sos_hold_test.dart).
//
// Hold the shutter: it records a silent video, and the screen slowly reddens. Slide up, to the X, and let
// go: the video is thrown away. Let go anywhere else: it is sent to the city at once as an SOS.

/// How long the shutter is held before it is an SOS and not a tap for a photo.
const sosHoldDelay = Duration(milliseconds: 450);

/// How far up, in logical pixels from where the finger went down, it takes to cancel: onto the near edge of the X
/// (about 1.1 cm), so cancelling happens as the finger reaches the X, not after it has gone past. Short on purpose:
/// someone frightened should not have to aim.
const sosCancelDistance = 72.0;

/// A clip shorter than this is not sent: too little to show anything, and Android's recorder can fail to stop on less.
const sosMinRecording = Duration(seconds: 1);

/// The recording stops, and is sent, at this length: it keeps the upload to a few megabytes.
const sosMaxRecording = Duration(seconds: 30);

/// The red vignette takes this long to reach full strength.
const sosVignetteRamp = Duration(seconds: 3);

/// How far the finger has slid toward cancel: 0 at the button, 1 on the target. [dy] is up-negative, like the screen.
double cancelProgress(double dy) => (-dy / sosCancelDistance).clamp(0.0, 1.0).toDouble();

/// Whether the finger is on the cancel target.
bool inCancelZone(double dy) => dy <= -sosCancelDistance;

enum SosOutcome { send, cancel, tooShort }

/// What letting go does: the finger on the target throws the clip away, a clip under [sosMinRecording] is dropped
/// with a hint, anything else is sent. There is no confirmation step: an SOS is urgent.
SosOutcome sosOutcome({required Duration recorded, required bool cancelZone}) {
  if (cancelZone) return SosOutcome.cancel;
  return recorded < sosMinRecording ? SosOutcome.tooShort : SosOutcome.send;
}

/// How red the screen is, 0..1. [ramp] (0..1 over [sosVignetteRamp]) eases in, so it creeps; sliding toward cancel
/// takes most of it back, so the screen calms as the finger nears the X.
double vignetteStrength(double ramp, double cancel) {
  final t = ramp.clamp(0.0, 1.0).toDouble();
  return t * t * (1 - 0.8 * cancel.clamp(0.0, 1.0).toDouble());
}

/// "0:07", "1:05".
String clock(Duration d) => '${d.inMinutes}:${(d.inSeconds % 60).toString().padLeft(2, '0')}';
