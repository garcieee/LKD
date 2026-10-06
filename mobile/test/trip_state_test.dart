import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/state/trip_state.dart';

const here = (lat: 14.5547, lng: 121.0244);
Place place(String label) => Place.fromJson({'label': label, 'lat': 14.553, 'lng': 121.021});
WalkRoute route(String mode, {double m = 480}) => WalkRoute.fromJson({
  'mode': mode,
  'distance_m': m,
  'duration_s': 300,
  'geometry': [
    [121.0244, 14.5547],
    [121.021, 14.553],
  ],
  'hazard_ids': <String>[],
  'avoids_hazards': mode != 'fastest',
});

CommuteOption option(String id, {bool earliest = false}) => CommuteOption.fromJson({
  'id': id,
  'total_s': 1200,
  'walk_s': 300,
  'tags': [if (earliest) 'earliest'],
  'legs': [
    {
      'kind': 'walk',
      'duration_s': 300,
      'distance_m': 400,
      'label': 'Walk',
      'geometry': [
        [121.0244, 14.5547],
        [121.021, 14.553],
      ],
    },
  ],
});

void main() {
  test('picking a place with a start fetches all three modes, each showing as it lands', () async {
    final pending = {for (final m in routeModes.keys) m: Completer<WalkRoute>()};
    final asked = <String>[];
    final trip = TripState((from, to, mode) {
      asked.add(mode);
      expect(from, here);
      expect(to, (lat: 14.553, lng: 121.021));
      return pending[mode]!.future;
    });
    trip.setDestination(place('Greenbelt'), from: here);
    expect(asked, ['fastest', 'walkable', 'accessible']);
    expect(trip.loading, isTrue);
    expect(trip.route, isNull);

    pending['walkable']!.complete(route('walkable', m: 520));
    await Future<void>.delayed(Duration.zero);
    expect(trip.route!.distanceM, 520, reason: 'the shown mode (walkable) is there before the others');
    expect(trip.loading, isTrue);

    pending['fastest']!.complete(route('fastest'));
    pending['accessible']!.complete(route('accessible'));
    await Future<void>.delayed(Duration.zero);
    expect(trip.loading, isFalse);
    expect(trip.routes.keys, containsAll(routeModes.keys));
    trip.dispose();
  });

  test('one mode failing keeps its message and leaves the others', () async {
    final trip = TripState((from, to, mode) async {
      if (mode == 'accessible') throw const ApiException('No walking route found between those points.');
      return route(mode);
    });
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    expect(trip.routes.keys, unorderedEquals(['fastest', 'walkable']));
    expect(trip.loading, isFalse);
    trip.setMode('accessible');
    expect(trip.route, isNull);
    expect(trip.error, 'No walking route found between those points.');
    trip.setMode('walkable');
    expect(trip.error, isNull);
    trip.dispose();
  });

  test('without a start nothing is fetched until plan() gets one', () async {
    final asked = <String>[];
    final trip = TripState((from, to, mode) async {
      asked.add(mode);
      return route(mode);
    });
    trip.setDestination(place('Greenbelt'));
    expect(asked, isEmpty);
    expect(trip.planned, isFalse);
    await trip.plan(here);
    expect(asked.length, 3);
    expect(trip.planned, isTrue);
    await trip.plan(here);
    expect(asked.length, 3, reason: 'asked once per destination');
    trip.dispose();
  });

  test('a new destination drops answers still coming for the old one', () async {
    final slow = Completer<WalkRoute>();
    var first = true;
    final trip = TripState((from, to, mode) {
      if (first && mode == 'walkable') return slow.future;
      return Future.value(route(mode, m: first ? 1 : 2));
    });
    trip.setDestination(place('Old'), from: here);
    first = false;
    trip.setDestination(place('New'), from: here);
    await Future<void>.delayed(Duration.zero);
    expect(trip.route!.distanceM, 2);
    slow.complete(route('walkable', m: 1));
    await Future<void>.delayed(Duration.zero);
    expect(trip.route!.distanceM, 2, reason: 'the old walkable answer arrived late and is ignored');
    trip.dispose();
  });

  test('clear forgets the destination and its routes; unknown modes are ignored', () async {
    final trip = TripState((from, to, mode) async => route(mode));
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    trip.setMode('teleport');
    expect(trip.mode, 'walkable');
    trip.clear();
    expect(trip.destination, isNull);
    expect(trip.routes, isEmpty);
    expect(trip.loading, isFalse);
    expect(trip.planned, isFalse);
    trip.dispose();
  });

  test('the trip starts on the walking step and fetches no commute options until asked', () async {
    final asked = <String>[];
    final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) async {
      asked.add(mode);
      return [option('a')];
    });
    expect(trip.step, TripStep.walk);
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    expect(trip.routes.length, 3);
    expect(asked, isEmpty, reason: 'the commute options wait for a walking mode to be picked');
    expect(trip.commute, isEmpty);
    trip.dispose();
  });

  test('toCommute asks with the picked mode, and the options show once they land', () async {
    final pending = Completer<List<CommuteOption>>();
    final asked = <String>[];
    final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) {
      asked.add(mode);
      expect(from, here);
      expect(to, (lat: 14.553, lng: 121.021));
      return pending.future;
    });
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    trip.setMode('accessible');
    final done = trip.toCommute();
    expect(trip.step, TripStep.commute);
    expect(trip.commuteLoading, isTrue);
    expect(asked, ['accessible']);
    pending.complete([option('a', earliest: true), option('b')]);
    await done;
    expect(trip.commuteLoading, isFalse);
    expect(trip.commute.map((o) => o.id), ['a', 'b']);
    expect(trip.option!.id, 'a');
    trip.select(1);
    expect(trip.option!.id, 'b');
    trip.select(9);
    expect(trip.selected, 1, reason: 'an index with no option is ignored');
    trip.dispose();
  });

  test('going back and forward keeps the options; a different mode asks again', () async {
    final asked = <String>[];
    final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) async {
      asked.add(mode);
      return [option(mode)];
    });
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    await trip.toCommute();
    trip.select(0);
    trip.backToWalk();
    expect(trip.step, TripStep.walk);
    await trip.toCommute();
    expect(asked, ['walkable'], reason: 'same mode: nothing to ask');
    expect(trip.commute.single.id, 'walkable');
    trip.backToWalk();
    trip.setMode('fastest');
    await trip.toCommute();
    expect(asked, ['walkable', 'fastest']);
    expect(trip.commute.single.id, 'fastest');
    trip.dispose();
  });

  test('a failed commute ask keeps the message, leaves the walks, and is asked again next time', () async {
    var fail = true;
    final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) async {
      if (fail) throw const ApiException('Both ends of the trip must be in Makati.');
      return [option('a')];
    });
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    await trip.toCommute();
    expect(trip.commute, isEmpty);
    expect(trip.commuteError, 'Both ends of the trip must be in Makati.');
    expect(trip.commuteLoading, isFalse);
    expect(trip.routes.length, 3, reason: 'the walking routes are untouched');
    fail = false;
    trip.backToWalk();
    await trip.toCommute();
    expect(trip.commuteError, isNull);
    expect(trip.commute.single.id, 'a');
    trip.dispose();
  });

  test('without a start there is nothing to ask: toCommute just moves to the step', () async {
    var calls = 0;
    final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) async {
      calls++;
      return [option('a')];
    });
    trip.setDestination(place('Greenbelt'));
    await trip.toCommute();
    expect(trip.step, TripStep.commute);
    expect(calls, 0);
    expect(trip.commuteLoading, isFalse);
    trip.dispose();
  });

  test('a new destination returns to the walking step and drops the old options and any answer still coming', () async {
    final slow = Completer<List<CommuteOption>>();
    var first = true;
    final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) {
      if (first) return slow.future;
      return Future.value([option('new')]);
    });
    trip.setDestination(place('Old'), from: here);
    await Future<void>.delayed(Duration.zero);
    final late = trip.toCommute();
    first = false;
    trip.setDestination(place('New'), from: here);
    expect(trip.step, TripStep.walk);
    expect(trip.commuteLoading, isFalse);
    await Future<void>.delayed(Duration.zero);
    await trip.toCommute();
    expect(trip.commute.single.id, 'new');
    slow.complete([option('old')]);
    await late;
    expect(trip.commute.single.id, 'new', reason: 'the old answer arrived late and is ignored');
    trip.select(0);
    trip.clear();
    expect(trip.commute, isEmpty);
    expect(trip.option, isNull);
    expect(trip.selected, 0);
    expect(trip.step, TripStep.walk);
    trip.dispose();
  });

  test('Start needs a route, and on the commute step the options too; the legs are the chosen option, or the walk alone', () async {
    final trip = TripState((from, to, mode) async => route(mode, m: mode == 'accessible' ? 700 : 480), (
      from,
      to,
      mode,
    ) async {
      return [option('a'), option('b')];
    });
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    expect(trip.canStart, isTrue, reason: 'a walk all the way needs no commute step');
    trip.start();
    expect(trip.started, isTrue);
    expect(trip.activeLegs.single.isWalk, isTrue);
    trip.end();

    await trip.toCommute();
    expect(trip.canStart, isTrue);
    trip.select(1);
    expect(trip.activeLegs, same(trip.commute[1].legs), reason: 'the chosen option is the trip');
    trip.start();
    expect(trip.started, isTrue);
    trip.end();
    expect(trip.started, isFalse);
    trip.dispose();
  });

  test('with no ride found the trip is the chosen walking route, as one walk leg', () async {
    final trip = TripState((from, to, mode) async => route(mode, m: mode == 'accessible' ? 700 : 480), (
      from,
      to,
      mode,
    ) async {
      return <CommuteOption>[];
    });
    trip.setDestination(place('Greenbelt'), from: here);
    await Future<void>.delayed(Duration.zero);
    trip.setMode('accessible');
    await trip.toCommute();
    expect(trip.commute, isEmpty);
    expect(trip.canStart, isTrue);
    final leg = trip.activeLegs.single;
    expect(leg.isWalk, isTrue);
    expect(leg.distanceM, 700, reason: 'the walk in the picked mode');
    expect(leg.label, 'Walk to Greenbelt');
    expect(leg.line.first, [121.0244, 14.5547]);
    trip.start();
    expect(trip.started, isTrue);
    trip.dispose();
  });

  test('Start waits for the commute options, and a new destination ends the trip', () async {
    final pending = Completer<List<CommuteOption>>();
    final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) => pending.future);
    trip.setDestination(place('Old'), from: here);
    await Future<void>.delayed(Duration.zero);
    final asking = trip.toCommute();
    expect(trip.canStart, isFalse, reason: 'the options are still on their way');
    pending.complete([option('a')]);
    await asking;
    trip.start();
    expect(trip.started, isTrue);
    trip.setDestination(place('New'));
    expect(trip.started, isFalse);
    trip.dispose();
  });

  group('live position', () {
    // Two legs straight up the 121.0 meridian: walk 14.5000 to 14.5020, then ride to 14.5100.
    CommuteOption twoLegs() => CommuteOption.fromJson({
      'id': 'a',
      'total_s': 1000,
      'walk_s': 200,
      'tags': <String>[],
      'legs': [
        for (final (kind, from, to, secs) in [('walk', 14.5000, 14.5020, 200), ('city_bus', 14.5020, 14.5100, 800)])
          {
            'kind': kind,
            'duration_s': secs,
            'distance_m': (to - from) * 111320,
            'label': kind,
            'geometry': [
              [121.0, from],
              [121.0, to],
            ],
          },
      ],
    });

    Future<TripState> started() async {
      final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) async => [twoLegs()]);
      trip.setDestination(place('Greenbelt'), from: here);
      await Future<void>.delayed(Duration.zero);
      await trip.toCommute();
      trip.start();
      return trip;
    }

    test('a fix before Start is ignored, and Start begins with no progress', () async {
      final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) async => [twoLegs()]);
      trip.setDestination(place('Greenbelt'), from: here);
      await Future<void>.delayed(Duration.zero);
      await trip.toCommute();
      trip.update(14.5000, 121.0);
      expect(trip.progress, isNull);
      trip.start();
      expect(trip.progress, isNull, reason: 'nothing is known until a fix comes in');
      trip.dispose();
    });

    test('fixes update the progress, and listeners hear only of changes worth showing', () async {
      final trip = await started();
      var heard = 0;
      trip.addListener(() => heard++);
      trip.update(14.5000, 121.0);
      expect(heard, 1, reason: 'the first fix');
      expect(trip.progress!.leg, 0);
      trip.update(14.5000 + 2 / 111320, 121.0);
      expect(heard, 1, reason: '2 m is not worth a rebuild');
      trip.update(14.5000 + 40 / 111320, 121.0);
      expect(heard, 2, reason: '40 m is');
      expect(trip.progress!.legLeftM, closeTo(222.64 - 40, 1));
      trip.update(14.5000 + 40 / 111320, 121.0 + 0.002);
      expect(trip.progress!.offRoute, isTrue);
      expect(heard, 3, reason: 'going off the line is news');
      trip.update(14.5020, 121.0);
      expect(heard, 4);
      expect(trip.progress!.leg, 1, reason: 'reaching the hub starts the ride');
      trip.update(14.5020, 121.0 + 0.002);
      expect(trip.progress!.offRoute, isFalse, reason: 'the ride is a straight guess: no such thing as off it');
      trip.dispose();
    });

    test('the leg only advances, even if a later fix lands back on the walk', () async {
      final trip = await started();
      trip.update(14.5020, 121.0);
      expect(trip.progress!.leg, 1);
      trip.update(14.5005, 121.0);
      expect(trip.progress!.leg, 1);
      trip.dispose();
    });

    test('arriving is reported, and End or a new destination forgets the trip', () async {
      final trip = await started();
      trip.update(14.5100, 121.0);
      expect(trip.progress!.arrived, isTrue);
      expect(trip.started, isTrue, reason: 'it ends when the user says so');
      trip.end();
      expect(trip.progress, isNull);
      trip.start();
      trip.update(14.5020, 121.0);
      expect(trip.progress!.leg, 1);
      trip.setDestination(place('Elsewhere'));
      expect(trip.progress, isNull);
      expect(trip.started, isFalse);
      trip.dispose();
    });

    group('rerouting', () {
      // The new walk the server answers with: from 200 m east of the path, back to the end of the leg.
      WalkRoute fresh() => WalkRoute.fromJson({
        'mode': 'walkable',
        'distance_m': 222,
        'duration_s': 160,
        'geometry': [
          [121.002, 14.5005],
          [121.0, 14.5020],
        ],
        'steps': [
          {'type': 11, 'text': 'Head west on Paseo', 'name': 'Paseo', 'distance_m': 222.0, 'at': 0},
        ],
        'hazard_ids': <String>[],
        'avoids_hazards': true,
      });

      late List<({({double lat, double lng}) from, ({double lat, double lng}) to, String mode})> calls;
      late Completer<WalkRoute> answer;
      late DateTime now;

      Future<TripState> trip() async {
        calls = [];
        answer = Completer<WalkRoute>();
        now = DateTime(2026, 10, 7, 12);
        final t = TripState((from, to, mode) {
          if (from.lat == here.lat) return Future.value(route(mode)); // the planner's asks
          calls.add((from: from, to: to, mode: mode));
          return answer.future;
        }, (from, to, mode) async => [twoLegs()]);
        t.clock = () => now;
        t.setDestination(place('Greenbelt'), from: here);
        await Future<void>.delayed(Duration.zero);
        await t.toCommute();
        t.start();
        return t;
      }

      // 200 m east of the walk, part way up it.
      void off(TripState t, {bool weak = false}) => t.update(14.5005, 121.002, weak: weak);

      test('three good fixes off the path in a row ask for a new walk from here to the end of the leg', () async {
        final t = await trip();
        off(t);
        off(t);
        expect(calls, isEmpty);
        off(t);
        expect(calls, hasLength(1));
        expect(calls.single.from, (lat: 14.5005, lng: 121.002));
        expect(calls.single.to, (lat: 14.5020, lng: 121.0), reason: 'where the leg ended');
        expect(calls.single.mode, 'walkable');
        expect(t.rerouting, isTrue);

        final planned = t.activeLegs.first.line;
        answer.complete(fresh());
        await Future<void>.delayed(Duration.zero);
        expect(t.rerouting, isFalse);
        expect(t.legs.first.line.first, [121.002, 14.5005], reason: 'the leg now starts where the user was');
        expect(t.legs.first.steps.single.name, 'Paseo');
        expect(t.legs.first.label, 'walk', reason: 'the leg keeps its name');
        expect(t.legs[1], same(t.activeLegs[1]), reason: 'the ride is untouched');
        expect(t.activeLegs.first.line, planned, reason: 'the planned route is not rewritten');
        expect(t.progress!.offRoute, isFalse, reason: 'they are on the new line');
        t.dispose();
      });

      test('a fix back on the path, or a rough one, does not count', () async {
        final t = await trip();
        off(t);
        off(t);
        t.update(14.5005, 121.0); // back on the line
        off(t);
        off(t);
        expect(calls, isEmpty, reason: 'the count started over');
        for (var i = 0; i < 5; i++) {
          off(t, weak: true);
        }
        expect(calls, isEmpty, reason: 'a weak fix is a guess');
        off(t);
        expect(calls, hasLength(1));
        t.dispose();
      });

      test('one ask at a time, and not again within 15 seconds, even if it failed', () async {
        final t = await trip();
        for (var i = 0; i < 6; i++) {
          off(t);
        }
        expect(calls, hasLength(1), reason: 'still waiting for the first');
        answer.completeError(const ApiException('down'));
        await Future<void>.delayed(Duration.zero);
        expect(t.rerouting, isFalse);
        expect(t.legs.first.line, t.activeLegs.first.line, reason: 'the old line stays');
        expect(t.progress!.offRoute, isTrue, reason: 'and the bar still says so');
        off(t);
        expect(calls, hasLength(1), reason: 'too soon');
        now = now.add(const Duration(seconds: 16));
        answer = Completer<WalkRoute>();
        off(t);
        expect(calls, hasLength(2), reason: 'still off the path: try again');
        t.dispose();
      });

      test('an answer that lands after End is dropped', () async {
        final t = await trip();
        for (var i = 0; i < 3; i++) {
          off(t);
        }
        t.end();
        answer.complete(fresh());
        await Future<void>.delayed(Duration.zero);
        expect(t.rerouting, isFalse);
        expect(t.legs.first.line, t.activeLegs.first.line);
        t.start();
        expect(t.legs.first.line.first, [121.0, 14.5000], reason: 'the next trip starts from the planned route');
        t.dispose();
      });

      test('the ride is never rerouted', () async {
        final t = await trip();
        t.update(14.5020, 121.0); // on the ride
        for (var i = 0; i < 6; i++) {
          t.update(14.5050, 121.002);
        }
        expect(calls, isEmpty);
        t.dispose();
      });
    });

    test('a walk-only trip is tracked along the walking route', () async {
      final trip = TripState((from, to, mode) async => route(mode), (from, to, mode) async => <CommuteOption>[]);
      trip.setDestination(place('Greenbelt'), from: here);
      await Future<void>.delayed(Duration.zero);
      await trip.toCommute();
      trip.start();
      trip.update(14.5547, 121.0244);
      expect(trip.progress!.leg, 0);
      expect(trip.progress!.legLeftM, greaterThan(300));
      trip.update(14.553, 121.021);
      expect(trip.progress!.arrived, isTrue);
      trip.dispose();
    });
  });
}
