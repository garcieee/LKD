// Where the user is along the trip: which leg, how far to the end of it and of the trip, how far off the line,
// what is left of the line, and the next turn. Pure maths on the legs the server sent and a GPS fix, so it is
// tested without a phone. Re-planning when the user is off the line is TripState's job (state/trip_state.dart).
//
// ponytail: only the current leg and the next are considered, and the leg only ever advances, so shared hub points
// and the straight-line ride cannot flip the trip backwards.
import 'dart:math' as math;

import '../api/api_client.dart';

const arriveM = 25.0; // this close to the end of a leg, it is done
const offRouteM = 30.0; // farther than this from a walking line, the user has left it (GPS is good to ~10 m)
const _mPerDegLat = 111320.0; // a flat-earth projection is exact enough over one leg in one city

class TripProgress {
  const TripProgress({
    required this.leg,
    required this.legLeftM,
    required this.leftM,
    required this.leftS,
    required this.offM,
    required this.arrived,
    required this.walking,
    required this.alongM,
    required this.ahead,
    required this.street,
    this.turn,
    this.turnInM,
  });

  final int leg; // index of the leg being travelled
  final double legLeftM; // along the line, to the end of that leg
  final double leftM; // to the end of the trip
  final double leftS; // time left: the leg's remainder pro rata, plus the legs after it
  final double offM; // from the user to the line
  final bool arrived; // at the end of the last leg
  final bool walking; // the leg being travelled is a walk
  final double alongM; // already travelled on this leg
  final List<List<double>> ahead; // [[lng, lat], ...]: this leg's line from the user's spot on it to its end
  final String street; // the street the user is on, per the leg's steps; empty when unknown or unnamed
  final RouteStep? turn; // the next manoeuvre on this leg, null when the leg has no steps or none is left
  final double? turnInM; // along the line to [turn]

  /// Off the path. Only a walk can be: a ride is a straight line between two hubs, not where the vehicle goes.
  bool get offRoute => walking && offM > offRouteM;
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
  final line = legs[leg].line, along = fix.length - fix.leftM;
  // The next manoeuvre is the first step whose spot is still ahead; the street is the last one already reached.
  RouteStep? turn, here;
  double? turnInM;
  for (final s in legs[leg].steps) {
    if (s.at >= fix.cum.length) continue;
    final spot = fix.cum[s.at];
    if (spot <= along + 1) {
      here = s;
    } else {
      turn = s;
      turnInM = spot - along;
      break;
    }
  }
  return TripProgress(
    leg: leg,
    legLeftM: fix.leftM,
    leftM: leftM,
    leftS: leftS,
    offM: fix.offM,
    arrived: leg == last && fix.leftM < arriveM,
    walking: legs[leg].isWalk,
    alongM: along,
    ahead: line.length < 2 ? line : [fix.at, ...line.skip(fix.seg + 1)],
    street: here?.name ?? '',
    turn: turn,
    turnInM: turnInM,
  );
}

typedef _Fix = ({double offM, double leftM, double length, int seg, List<double> at, List<double> cum});

/// The nearest point on [leg]'s line to the fix: how far off it is, how far along it is left, its length, where
/// that nearest point is ([at], lng/lat, on segment [seg]) and how far along the line each of its points is ([cum]).
_Fix _along(CommuteLeg leg, double lat, double lng) {
  final mPerDegLng = _mPerDegLat * math.cos(lat * math.pi / 180);
  // Metres east and north of the fix.
  final pts = [for (final p in leg.line) ((p[0] - lng) * mPerDegLng, (p[1] - lat) * _mPerDegLat)];
  if (pts.length < 2) return (offM: double.infinity, leftM: 0, length: 0, seg: 0, at: [lng, lat], cum: const []);
  var length = 0.0, bestOff = double.infinity, bestAlong = 0.0, bestSeg = 0;
  var bestAt = [lng, lat];
  final cum = [0.0];
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
      bestSeg = i;
      bestAt = [lng + (ax + t * dx) / mPerDegLng, lat + (ay + t * dy) / _mPerDegLat];
    }
    length += segLen;
    cum.add(length);
  }
  return (offM: bestOff, leftM: length - bestAlong, length: length, seg: bestSeg, at: bestAt, cum: cum);
}
