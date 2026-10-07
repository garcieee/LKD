// A compass chip over the map: an arrow that keeps pointing at true north as the map turns, and the cardinal
// direction at the top of the screen. While the camera follows the phone's heading that is the way the phone faces.
// The arrow follows the map. While the camera follows the phone's heading the map turns with it; off that the map stays
// north-up, so only the arrow turns. Given `onTap`, a tap on the chip starts or stops that following (the chip is navy while
// it is on); without it the chip only displays.
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:flutter/material.dart';

import '../../theme.dart';
import '../report/ar_math.dart' show compassPoint;

class CompassChip extends StatelessWidget {
  const CompassChip({super.key, required this.bearing, required this.following, this.onTap});

  final ValueListenable<double> bearing; // degrees clockwise from north that the top of the map points to
  final ValueListenable<bool> following; // the camera is turning with the phone
  final VoidCallback? onTap; // null: the chip is a display only

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([bearing, following]),
      builder: (context, _) {
        final deg = bearing.value, on = following.value;
        final color = on ? paper : ink;
        final toggle = onTap;
        final content = ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                // The map turns clockwise by `deg`, so north moves anticlockwise by the same on screen.
                Transform.rotate(
                  angle: -deg * math.pi / 180,
                  child: Icon(Icons.north, size: 18, color: color),
                ),
                const SizedBox(width: 6),
                Text(
                  compassPoint(deg),
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: color),
                ),
              ],
            ),
          ),
        );
        return Semantics(
          label:
              'Compass, facing ${compassPoint(deg)}. ${on ? 'Following your heading. ' : ''}'
              '${toggle == null
                  ? ''
                  : on
                  ? 'Tap to stop following.'
                  : 'Tap to follow your heading.'}',
          button: toggle != null,
          excludeSemantics: true,
          child: Material(
            color: on ? navy : Colors.white,
            shape: const RoundedRectangleBorder(
              borderRadius: radiusChip,
              side: BorderSide(color: hairline),
            ),
            child: toggle == null
                ? content
                : InkWell(
                    customBorder: const RoundedRectangleBorder(borderRadius: radiusChip),
                    onTap: toggle,
                    child: content,
                  ),
          ),
        );
      },
    );
  }
}
