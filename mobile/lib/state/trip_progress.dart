// Where the user is along the trip: which leg, how far to the end of it and of the trip, and how far off the line.
// Pure maths on the legs the server sent and a GPS fix, so it is tested without a phone.
//
// ponytail: only the current leg and the next are considered, and the leg only ever advances, so shared hub points
// and the straight-line ride cannot flip the trip backwards. Nothing re-plans when the user is off the line (the
// bar says "Off route"). Upgrade: re-fetch from the fix once offRoute holds for a while.
import 'dart:math' as math;

import '../api/api_client.dart';

const arriveM = 25.0; // this close to the end of a leg, it is done
const offRouteM = 100.0; // farther than this from the line, the user has left it
const _mPerDegLat = 111320.0; // a flat-earth projection is exact enough over one leg in one city

class TripProgress {
  const TripProgress({
    required this.leg,
    required this.legLeftM,
    required this.leftM,
    required this.leftS,
    required this.offM,
    required this.arrived,
  });

  final int leg; // index of the leg being travelled
  final double legLeftM; // along the line, to the end of that leg
  final double leftM; // to the end of the trip
  final double leftS; // time left: the leg's remainder pro rata, plus the legs after it
  final double offM; // from the user to the line
  final bool arrived; // at the end of the last leg

  bool get offRoute => offM > offRouteM;
}

/// Where a fix at ([lat], [lng]) is on [legs], having been on leg [current]. Null when there are no legs.
TripProgress? tripProgress(List<CommuteLeg> legs, int current, double lat, double lng) {
  if (legs.isEmpty) return null;
  final last = legs.length - 1;
  var leg = current.clamp(0, last);
  var fix = _along(legs[leg], lat, lng);
  if (leg < last) {
    final next = _along(legs[leg + 1], lat, lng);
    if (next.offM < fix.offM) {
      // Strictly closer: at a shared hub point the current leg wins the tie.
      leg++;
      fix = next;
    }
  }
  // Done with this leg: on to the next, which starts where this one ends.
  if (fix.leftM < arriveM && leg < last) {
    leg++;
    fix = _along(legs[leg], lat, lng);
  }
  var leftM = fix.leftM, leftS = legs[leg].durationS * (fix.length == 0 ? 0 : fix.leftM / fix.length);
  for (final l in legs.skip(leg + 1)) {
    leftM += l.distanceM;
    leftS += l.durationS;
  }
  return TripProgress(
    leg: leg,
    legLeftM: fix.leftM,
    leftM: leftM,
    leftS: leftS,
    offM: fix.offM,
    arrived: leg == last && fix.leftM < arriveM,
  );
}

typedef _Fix = ({double offM, double leftM, double length});

/// The nearest point on [leg]'s line to the fix: how far off it is, how far along it is left, and its length.
_Fix _along(CommuteLeg leg, double lat, double lng) {
  final mPerDegLng = _mPerDegLat * math.cos(lat * math.pi / 180);
  // Metres east and north of the fix.
  final pts = [for (final p in leg.line) ((p[0] - lng) * mPerDegLng, (p[1] - lat) * _mPerDegLat)];
  if (pts.length < 2) return (offM: double.infinity, leftM: 0, length: 0); // not a line: never the nearest
  var length = 0.0, bestOff = double.infinity, bestAlong = 0.0;
  for (var i = 0; i + 1 < pts.length; i++) {
    final (ax, ay) = pts[i];
    final (bx, by) = pts[i + 1];
    final dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
    final t = len2 == 0 ? 0.0 : (-(ax * dx + ay * dy) / len2).clamp(0.0, 1.0);
    final off = math.sqrt(math.pow(ax + t * dx, 2) + math.pow(ay + t * dy, 2));
    final segLen = math.sqrt(len2);
    if (off < bestOff) {
      bestOff = off;
      bestAlong = length + t * segLen;
    }
    length += segLen;
  }
  return (offM: bestOff, leftM: length - bestAlong, length: length);
}
