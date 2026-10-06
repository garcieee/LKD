// A compass chip over the map: an arrow that keeps pointing at true north as the map turns, and the cardinal
// direction at the top of the screen. While the camera follows the phone's heading that is the way the phone faces.
// A display only: it follows the map. On a trip the map turns with the phone, and the locate button picks that up again after a pan.
// Off a trip the map stays north-up, so only the arrow turns.
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:flutter/material.dart';

import '../../theme.dart';
import '../report/ar_math.dart' show compassPoint;

class CompassChip extends StatelessWidget {
  const CompassChip({super.key, required this.bearing, required this.following});

  final ValueListenable<double> bearing; // degrees clockwise from north that the top of the map points to
  final ValueListenable<bool> following; // the camera is turning with the phone

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([bearing, following]),
      builder: (context, _) {
        final deg = bearing.value, on = following.value;
        final color = on ? paper : ink;
        return Semantics(
          label:
              'Compass, facing ${compassPoint(deg)}. ${on ? 'Following your heading' : ''}',
          excludeSemantics: true,
          child: Material(
            color: on ? navy : Colors.white,
            shape: const RoundedRectangleBorder(
              borderRadius: radiusChip,
              side: BorderSide(color: hairline),
            ),
            child: ConstrainedBox(
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
            ),
          ),
        );
      },
    );
  }
}
