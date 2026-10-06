import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/search/place_search.dart';

Place place(String label) => Place.fromJson({'label': label, 'lat': 14.55, 'lng': 121.02});

const pause = Duration(milliseconds: 20);
Future<void> settle() => Future.delayed(const Duration(milliseconds: 60));

void main() {
  test('only the last keystroke of a burst is searched, after the pause', () async {
    final asked = <String>[];
    final s = PlaceSearch((text, near) async {
      asked.add(text);
      return [place(text)];
    }, delay: pause);
    s.onChanged('Aya');
    s.onChanged('Ayal');
    s.onChanged('Ayala');
    expect(s.loading, isTrue);
    expect(asked, isEmpty, reason: 'still inside the pause');
    await settle();
    expect(asked, ['Ayala']);
    expect(s.loading, isFalse);
    expect(s.results!.single.label, 'Ayala');
    s.dispose();
  });

  test('under three characters is not searched and clears what was shown', () async {
    var calls = 0;
    final s = PlaceSearch((text, near) async {
      calls++;
      return [place(text)];
    }, delay: pause);
    s.onChanged('Ayala');
    await settle();
    expect(s.results, isNotNull);
    s.onChanged('Ay');
    expect(s.results, isNull);
    expect(s.loading, isFalse);
    await settle();
    expect(calls, 1);
    s.onChanged('  a  '); // spaces do not count
    await settle();
    expect(calls, 1);
    s.dispose();
  });

  test('passes the nearby point along, and trims the text', () async {
    String? text;
    Near? got;
    final s = PlaceSearch((t, near) async {
      text = t;
      got = near;
      return [];
    }, delay: pause);
    s.onChanged('  Greenbelt ', near: (lat: 14.55, lng: 121.02));
    await settle();
    expect(text, 'Greenbelt');
    expect(got, (lat: 14.55, lng: 121.02));
    expect(s.results, isEmpty, reason: 'searched, found nothing, which is not the same as not searched');
    s.dispose();
  });

  test('a slow answer to an older keystroke never overwrites the newer one', () async {
    final slow = Completer<List<Place>>();
    final s = PlaceSearch((text, near) => text == 'Ayala' ? slow.future : Future.value([place(text)]), delay: pause);
    s.onChanged('Ayala');
    await Future.delayed(const Duration(milliseconds: 30)); // the Ayala search is now in flight
    s.onChanged('Greenbelt');
    await settle();
    expect(s.results!.single.label, 'Greenbelt');
    slow.complete([place('Ayala')]);
    await settle();
    expect(s.results!.single.label, 'Greenbelt');
    s.dispose();
  });

  test('a failed search shows the server message and no stale results', () async {
    var fail = false;
    final s = PlaceSearch((text, near) async {
      if (fail) throw const ApiException('Place search is unavailable. Try again.');
      return [place(text)];
    }, delay: pause);
    s.onChanged('Ayala');
    await settle();
    fail = true;
    s.onChanged('Ayala Ave');
    await settle();
    expect(s.error, 'Place search is unavailable. Try again.');
    expect(s.results, isNull);
    expect(s.loading, isFalse);
    s.onChanged('Ayala Ave 2'); // typing again clears the message while it searches
    expect(s.error, isNull);
    s.dispose();
  });

  test('clear forgets everything, and a disposed search stays quiet', () async {
    final s = PlaceSearch((text, near) async => [place(text)], delay: pause);
    s.onChanged('Ayala');
    await settle();
    s.clear();
    expect(s.results, isNull);
    s.onChanged('Ayala');
    s.dispose(); // the timer is cancelled: no notify after dispose
    await settle();
  });
}
