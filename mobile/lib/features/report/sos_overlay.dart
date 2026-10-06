// What the SOS hold looks like: the shutter that tells a tap from a hold, the red vignette, the arrows that point
// up to the cancel target, and the banner that says SOS mode is on. report_screen.dart owns the recording; these
// only draw it and report where the finger is. The rules (distances, times) are in sos_hold.dart.
import 'dart:async';

import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:flutter/gestures.dart' show kTouchSlop;
import 'package:flutter/material.dart';

import '../../theme.dart';
import 'sos_hold.dart';

const _shutter = 76.0;
const _target = 48.0;
const _label = 26.0;

/// The room the shutter and its cancel guide need, up from the screen's bottom edge: half the shutter, the
/// slide to the near edge of the X, the X, a gap and the label.
const sosGuideHeight = _shutter / 2 + sosCancelDistance + _target + 4 + _label;

/// The camera button. A tap is a photo ([onTap]). Held for [sosHoldDelay] it becomes an SOS: [onSosStart], then
/// [onSosMove] with how far the finger has slid (up is negative), then [onSosEnd] when it lifts, or [onSosAbort]
/// when the system takes the touch away.
///
/// ponytail: raw pointer events and a timer instead of GestureDetector's long press, because an SOS must always
/// hear how the touch ended. The gesture arena can quietly drop a long press that something else claims, and a
/// recording that never gets its "let go" would run on and send itself.
class SosShutter extends StatefulWidget {
  const SosShutter({
    super.key,
    required this.enabled,
    required this.busy,
    required this.armed,
    required this.cancelling,
    required this.onTap,
    required this.onSosStart,
    required this.onSosMove,
    required this.onSosEnd,
    required this.onSosAbort,
  });

  final bool enabled; // a new press may start; one already under way always finishes
  final bool busy; // a photo is being taken
  final bool armed; // an SOS is recording
  final bool cancelling; // ...and the finger is on the cancel target
  final VoidCallback onTap;
  final VoidCallback onSosStart;
  final ValueChanged<double> onSosMove;
  final ValueChanged<double> onSosEnd;
  final VoidCallback onSosAbort;

  @override
  State<SosShutter> createState() => _SosShutterState();
}

class _SosShutterState extends State<SosShutter> {
  int? _pointer;
  Offset _down = Offset.zero;
  Timer? _hold;
  bool _armed = false; // held long enough: an SOS
  bool _dragged = false; // moved before that: neither a tap nor an SOS

  void _reset() {
    _hold?.cancel();
    _hold = null;
    _pointer = null;
    _armed = false;
    _dragged = false;
  }

  void _onDown(PointerDownEvent e) {
    if (_pointer != null || !widget.enabled) return;
    _pointer = e.pointer;
    _down = e.position;
    _hold = Timer(sosHoldDelay, () {
      _armed = true;
      widget.onSosStart();
    });
  }

  void _onMove(PointerMoveEvent e) {
    if (e.pointer != _pointer) return;
    if (_armed) {
      widget.onSosMove(e.position.dy - _down.dy);
    } else if ((e.position - _down).distance > kTouchSlop) {
      _dragged = true;
      _hold?.cancel();
    }
  }

  void _onUp(PointerUpEvent e) {
    if (e.pointer != _pointer) return;
    final armed = _armed, tap = !_armed && !_dragged;
    final dy = e.position.dy - _down.dy;
    _reset();
    if (armed) {
      widget.onSosEnd(dy);
    } else if (tap) {
      widget.onTap();
    }
  }

  void _onCancel(PointerCancelEvent e) {
    if (e.pointer != _pointer) return;
    final armed = _armed;
    _reset();
    if (armed) widget.onSosAbort();
  }

  @override
  void dispose() {
    _hold?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final armed = widget.armed, cancelling = widget.cancelling;
    return Semantics(
      button: true,
      enabled: widget.enabled,
      label: 'Take photo. Press and hold to record an SOS video.',
      onTap: widget.enabled ? widget.onTap : null,
      child: Listener(
        behavior: HitTestBehavior.opaque,
        onPointerDown: _onDown,
        onPointerMove: _onMove,
        onPointerUp: _onUp,
        onPointerCancel: _onCancel,
        child: AnimatedOpacity(
          opacity: !widget.enabled && !widget.busy && !armed ? 0.4 : 1,
          duration: const Duration(milliseconds: 150),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            width: _shutter,
            height: _shutter,
            padding: const EdgeInsets.all(5),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: cancelling ? Colors.white54 : Colors.white, width: 4),
              boxShadow: armed && !cancelling
                  ? [BoxShadow(color: sosRed.withValues(alpha: 0.75), blurRadius: 26, spreadRadius: 3)]
                  : null,
            ),
            child: widget.busy
                ? const CircularProgressIndicator(color: Colors.white, strokeWidth: 3)
                : AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    decoration: BoxDecoration(
                      // A white disc; while recording a red rounded square, the sign for "stop"; grey on the X.
                      color: armed ? (cancelling ? Colors.white38 : sosRed) : Colors.white,
                      borderRadius: BorderRadius.circular(armed ? 12 : 30),
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}

/// The screen reddening from its edges, an ellipse that fits any phone. [ramp] (0..1) is the slow creep; sliding
/// toward cancel ([cancel], 0..1) takes the red back.
class SosVignette extends StatelessWidget {
  const SosVignette({super.key, required this.ramp, required this.cancel});

  final Animation<double> ramp;
  final ValueListenable<double> cancel;

  @override
  Widget build(BuildContext context) => IgnorePointer(
    child: SizedBox.expand(
      child: AnimatedBuilder(
        animation: Listenable.merge([ramp, cancel]),
        builder: (context, _) => CustomPaint(painter: _VignettePainter(vignetteStrength(ramp.value, cancel.value))),
      ),
    ),
  );
}

class _VignettePainter extends CustomPainter {
  const _VignettePainter(this.strength);

  final double strength;

  @override
  void paint(Canvas canvas, Size size) {
    if (strength <= 0.002) return;
    // The gradient is drawn on a unit square and stretched to the screen, so its circle becomes an ellipse and a
    // tall phone is red on all four sides, deepest in the corners.
    canvas.save();
    canvas.translate(size.width / 2, size.height / 2);
    canvas.scale(size.width, size.height);
    const red = sosRed, deep = Color(0xFF8F000F);
    final shader = RadialGradient(
      colors: [
        red.withValues(alpha: 0),
        red.withValues(alpha: 0),
        red.withValues(alpha: 0.55 * strength),
        deep.withValues(alpha: 0.92 * strength),
      ],
      stops: const [0, 0.4, 0.7, 1],
    ).createShader(Rect.fromCircle(center: Offset.zero, radius: 0.7));
    canvas.drawRect(const Rect.fromLTWH(-0.5, -0.5, 1, 1), Paint()..shader = shader);
    canvas.restore();
  }

  @override
  bool shouldRepaint(_VignettePainter old) => old.strength != strength;
}

/// Above the shutter while an SOS records: three arrows marching up, the X to slide to, and what to do.
/// Sized by [sosGuideHeight]; the shutter sits at the bottom of the same box.
class SosGuide extends StatelessWidget {
  const SosGuide({super.key, required this.cancel, required this.reduceMotion});

  final ValueListenable<double> cancel;
  final bool reduceMotion; // arrows stand still

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<double>(
    valueListenable: cancel,
    builder: (context, progress, _) => Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: 0,
          right: 0,
          bottom: _shutter / 2 + sosCancelDistance + _target + 4,
          height: _label,
          child: Center(child: _Pill(progress >= 1 ? 'Release to cancel' : 'Slide up to cancel', bright: progress >= 1)),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: _shutter / 2 + sosCancelDistance, // its near edge is where the slide ends
          height: _target,
          child: Center(child: _CancelTarget(progress)),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: _shutter + 4,
          height: sosCancelDistance - _shutter / 2 - 8, // the gap between the button and the X, all of it arrows
          child: ExcludeSemantics(child: Center(child: _Chevrons(still: reduceMotion))),
        ),
      ],
    ),
  );
}

class _Pill extends StatelessWidget {
  const _Pill(this.text, {required this.bright});

  final String text;
  final bool bright; // on the target: white, so it reads as a button about to fire

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: bright ? Colors.white : Colors.black54,
      borderRadius: BorderRadius.circular(999),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Text(
        text,
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: bright ? ink : Colors.white),
      ),
    ),
  );
}

class _CancelTarget extends StatelessWidget {
  const _CancelTarget(this.progress);

  final double progress; // 0 far, 1 on it

  @override
  Widget build(BuildContext context) => Transform.scale(
    scale: 1 + 0.25 * progress,
    child: Container(
      width: _target,
      height: _target,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: Color.lerp(Colors.black38, Colors.white, progress),
        border: Border.all(color: Colors.white, width: 2),
      ),
      child: Icon(Icons.close, size: 24, color: Color.lerp(Colors.white, ink, progress)),
    ),
  );
}

// Three chevrons whose light climbs toward the X: the bottom one first. Still, if animations are off.
class _Chevrons extends StatefulWidget {
  const _Chevrons({required this.still});

  final bool still;

  @override
  State<_Chevrons> createState() => _ChevronsState();
}

class _ChevronsState extends State<_Chevrons> with SingleTickerProviderStateMixin {
  late final _loop = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));

  @override
  void initState() {
    super.initState();
    if (!widget.still) _loop.repeat();
  }

  @override
  void dispose() {
    _loop.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 40,
    height: 26,
    child: AnimatedBuilder(
      animation: _loop,
      builder: (context, _) => Stack(
        clipBehavior: Clip.none,
        children: [
          for (var i = 0; i < 3; i++) // i = 0 is the top one, nearest the X
            Positioned(
              left: 12,
              top: i * 5.0,
              child: Icon(
                Icons.keyboard_arrow_up_rounded,
                size: 16,
                color: Colors.white.withValues(alpha: widget.still ? 0.85 : _glow((_loop.value - (2 - i) * 0.2) % 1)),
                shadows: const [Shadow(blurRadius: 6, color: Colors.black54)],
              ),
            ),
        ],
      ),
    ),
  );

  // A triangle wave, brightest at the middle of its turn.
  static double _glow(double p) => 0.2 + 0.8 * (1 - (2 * p - 1).abs());
}

/// The pill at the top while an SOS records: SOS mode, the time, and what letting go will do.
class SosBanner extends StatelessWidget {
  const SosBanner({super.key, required this.cancel, required this.recorded});

  final ValueListenable<double> cancel;
  final ValueListenable<Duration> recorded;

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<double>(
    valueListenable: cancel,
    builder: (context, progress, _) {
      final cancelling = progress >= 1;
      return Semantics(
        container: true,
        liveRegion: true,
        label: cancelling ? 'Release to cancel the SOS' : 'SOS mode. Release to send the video.',
        child: ExcludeSemantics(
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: cancelling ? const Color(0xE6222222) : sosRed,
              borderRadius: radiusChip,
              boxShadow: const [BoxShadow(color: Color(0x66000000), blurRadius: 14, offset: Offset(0, 3))],
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(cancelling ? Icons.close : Icons.fiber_manual_record, size: 12, color: Colors.white),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          cancelling ? 'CANCEL' : 'SOS MODE',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.8,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      ValueListenableBuilder<Duration>(
                        valueListenable: recorded,
                        builder: (context, d, _) => Text(
                          clock(d),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            fontFeatures: [FontFeature.tabularFigures()],
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    cancelling ? 'Release to throw the video away' : 'Release to send it to the city',
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    },
  );
}
